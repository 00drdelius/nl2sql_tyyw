"""
CMDB 资产直查服务

资产意图不走 SQL 执行网关（平台不注册 asset module），
直接调用 CMDB API（docs/CMDB_API分析.md）分页拉取实例数据，
由服务端完成字段映射（哈希ID -> 中文属性名）与聚合（分组计数/总数/明细）。
认证直接转发前端的 authorization（平台 token 对 backend_api 通用）。
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any, Dict, List, Optional

import psycopg2
import requests
import urllib3

from config import settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from logg import logger

PAGE_SIZE = 200
MAX_GROUP_INSTANCES = 5000  # group_count 聚合最多拉取的实例数（安全上限）
DEFAULT_LIST_LIMIT = 200
MAX_LIST_LIMIT = 2000
DEFAULT_TREE_SEED_OBJECT_ID = "64c9bf804dacd"  # 拉分类树时的种子 object_id（任意有效模型即可）

# 顶层固定字段（不经过 attribute 哈希映射）
TOP_LEVEL_FIELDS = {"instance_name", "object_id"}


class CMDBQueryError(ValueError):
    """CMDB 直查错误，信息会反馈给 LLM 用于重试修正。"""


def _get_registry_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
    )


class CmdbQueryService:
    """资产直查执行器：解析查询参数 -> 拉取实例 -> 过滤/聚合 -> QueryResult 形状结果。"""

    @staticmethod
    def _cmdb_base_url() -> str:
        return settings.CMDB_BASE_URL_PROD if not settings.TEST_MODE else settings.CMDB_BASE_URL_TEST

    @staticmethod
    def _resolve_token(authorization: str) -> str:
        """鉴权优先级：服务端环境 token > 前端转发 token。"""
        token = settings.CMDB_TOKEN_PROD if not settings.TEST_MODE else settings.CMDB_TOKEN_TEST
        token = token.strip()
        if token:
            return f"Bearer {token}"
        return authorization

    @staticmethod
    def _headers(authorization: str) -> Dict[str, str]:
        # 正式平台 RBAC 中间件要求请求带 Cookie 头才放行 instance/list
        # （纯 API 客户端无 cookie 会被 403；浏览器天然带 cookie）。
        # 实测任意 cookie 值均可通过，这里带上 accessToken 语义最合理。
        token = authorization[7:] if authorization.startswith("Bearer ") else authorization
        return {
            "Content-Type": "application/json",
            "Authorization": authorization,
            "Accept": "application/json, text/plain, */*",
            "Accept-language": "zh-CN",
            "x-requested-with": "XMLHttpRequest",
            "Cookie": f"accessToken={token}",
        }

    def _post(self, path: str, payload: dict, authorization: str) -> dict:
        try:
            resp = requests.post(
                f"{self._cmdb_base_url()}{path}", json=payload, headers=self._headers(authorization),
                timeout=30, verify=False,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CMDBQueryError(f"CMDB API 请求失败: {exc}") from exc
        body = resp.json()
        if body.get("code") != 0:
            raise CMDBQueryError(f"CMDB API 返回错误 code={body.get('code')}: {body.get('message')}")
        return body

    def _get(self, path: str, authorization: str) -> dict:
        try:
            resp = requests.get(
                f"{self._cmdb_base_url()}{path}", headers=self._headers(authorization),
                timeout=30, verify=False,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise CMDBQueryError(f"CMDB API 请求失败: {exc}") from exc
        body = resp.json()
        if body.get("code") != 0:
            raise CMDBQueryError(f"CMDB API 返回错误 code={body.get('code')}: {body.get('message')}")
        return body

    def fetch_attributes(self, object_id: str, authorization: str) -> Dict[str, str]:
        """拉取模型属性定义，返回 {中文属性名: 哈希ID} 映射。"""
        body = self._get(f"/backend_api/cmdb/attributes/{object_id}?visible=1", authorization)
        data = body.get("data")
        if not isinstance(data, list):
            raise CMDBQueryError(f"attributes 接口返回格式异常: {type(data).__name__}")
        name_to_id: Dict[str, str] = {}
        for attr in data:
            attr_id = attr.get("id")
            name = attr.get("name")
            if attr_id and name:
                name_to_id[str(name)] = str(attr_id)
        return name_to_id

    def fetch_page(
        self,
        object_id: str,
        page: int,
        page_size: int,
        authorization: str,
        keyword: str = "",
        senior_params: Optional[list] = None,
    ) -> dict:
        """分页拉取实例列表，返回 instances 对象（含 total/list）。"""
        payload = {
            "keyword": keyword or "",
            "object_id": object_id,
            "page": page,
            "pageSize": page_size,
            "senior_params": senior_params or [],
        }
        body = self._post("/backend_api/cmdb/instance/list", payload, authorization)
        return body["data"]["instances"]

    def fetch_all(
        self,
        object_id: str,
        authorization: str,
        keyword: str = "",
        senior_params: Optional[list] = None,
        max_instances: int = MAX_GROUP_INSTANCES,
    ) -> tuple[List[dict], int]:
        """分页拉取全部实例，返回 (实例列表, 总数)；超过 max_instances 截断并告警。"""
        instances: List[dict] = []
        page = 1
        total = 0
        while True:
            data = self.fetch_page(object_id, page, PAGE_SIZE, authorization, keyword, senior_params)
            total = data.get("total") or 0
            items = data.get("list") or []
            instances.extend(items)
            if not items or len(instances) >= total:
                break
            page += 1
            if len(instances) >= max_instances:
                logger.warning("模型 {} 实例数超过上限 {}，聚合结果被截断", object_id, max_instances)
                instances = instances[:max_instances]
                break
        return instances, total

    @staticmethod
    def _registry_table() -> str:
        """本地注册表名：正式/测试环境各一张（分别由同步脚本对各自 CMDB 生成）。"""
        return "cmdb_asset_models_prod" if not settings.TEST_MODE else "cmdb_asset_models"

    def _lookup_model(self, model: str) -> str:
        """本地注册表：模型中文名 -> object_id。"""
        registry = self._registry_table()
        try:
            conn = _get_registry_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT object_id FROM {registry} WHERE name = %s", (model,))
                    row = cur.fetchone()
            finally:
                conn.close()
        except psycopg2.Error as exc:
            raise CMDBQueryError(f"本地注册表查询失败：{exc}") from exc
        if row:
            return row[0]
        raise CMDBQueryError(
            f"注册表中不存在模型“{model}”，请从表结构说明中选择正确的模型名（分类级别问题请用 category 字段）"
        )

    @staticmethod
    def _list_known_models() -> List[str]:
        """返回注册表中实例数最多的若干模型名，用于错误提示。"""
        registry = CmdbQueryService._registry_table()
        try:
            conn = _get_registry_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT name FROM {registry} "
                        "WHERE name IS NOT NULL AND name != '' "
                        "ORDER BY instance_count DESC NULLS LAST LIMIT 20"
                    )
                    return [r[0] for r in cur.fetchall()]
            finally:
                conn.close()
        except psycopg2.Error:
            return []

    def _is_valid_object_id(self, object_id: str, authorization: str) -> bool:
        """校验 object_id：先查本地注册表，未命中再用 attributes 接口实时校验。"""
        registry = self._registry_table()
        try:
            conn = _get_registry_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT 1 FROM {registry} WHERE object_id = %s", (object_id,))
                    if cur.fetchone():
                        return True
            finally:
                conn.close()
        except psycopg2.Error as exc:
            logger.warning("注册表校验失败，改用 API 实时校验: {}", exc)
        try:
            data = self._get(f"/backend_api/cmdb/attributes/{object_id}?visible=1", authorization).get("data")
            return isinstance(data, list) and len(data) > 0
        except CMDBQueryError:
            return False

    def resolve_object_id(self, spec: dict, authorization: str) -> str:
        """解析并校验 object_id：支持 object_id 直给 / 表名形式 / 中文模型名查注册表。

        无效的 object_id（占位符/编造）直接报错反馈给 LLM，绝不静默返回空结果。
        """
        object_id = spec.get("object_id")
        if isinstance(object_id, str) and object_id.startswith("cmdb_asset_"):
            object_id = object_id[len("cmdb_asset_"):]  # LLM 可能直接给表名
        model = spec.get("model")
        if not object_id and model:
            object_id = self._lookup_model(str(model))
        if not object_id:
            raise CMDBQueryError("查询参数缺少 object_id/model/category，请从表结构说明中确定要查询的资产模型")
        object_id = str(object_id).strip()
        if not self._is_valid_object_id(object_id, authorization):
            hints = self._list_known_models()
            hint_text = f"可用模型示例：{', '.join(hints[:15])}。" if hints else ""
            raise CMDBQueryError(
                f"object_id「{object_id}」不是有效的资产模型ID（禁止占位符或编造）。{hint_text}"
                "请改用 model（模型中文名）或从表结构说明中选取真实的 object_id。"
            )
        return object_id

    @staticmethod
    def _extract_value(instance: dict, attr: dict) -> Any:
        """从 attribute 值对象中取规整后的值：空值 -> None，数组 -> 逗号拼接。"""
        value = attr.get("value")
        if value is None or value == "":
            return None
        if isinstance(value, list):
            return ",".join(str(v) for v in value if v is not None) or None
        return value

    def _build_rows(
        self, instances: List[dict], fields: List[str], name_to_id: Dict[str, str], object_id: str
    ) -> tuple[List[str], List[list]]:
        """按 fields（中文字段名）抽取实例值。"""
        rows: List[list] = []
        for inst in instances:
            row = []
            for field in fields:
                if field == "instance_name":
                    row.append(inst.get("instance_name"))
                elif field == "object_id":
                    row.append(inst.get("object_id"))
                else:
                    attr_id = name_to_id.get(field)
                    if attr_id is None:
                        raise CMDBQueryError(
                            f"模型 {object_id} 不存在字段“{field}”，请从表结构说明中选择正确的字段名"
                        )
                    attr = (inst.get("attribute") or {}).get(attr_id) or {}
                    row.append(self._extract_value(inst, attr))
            rows.append(row)
        return list(fields), rows

    def _tree_seed(self) -> str:
        """拉分类树需要一个有效 object_id 作种子，优先取注册表第一条。"""
        registry = self._registry_table()
        try:
            conn = _get_registry_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT object_id FROM {registry} LIMIT 1")
                    row = cur.fetchone()
            finally:
                conn.close()
            if row:
                return row[0]
        except psycopg2.Error:
            pass
        # 兜底种子：测试环境用 130 的 UPS设备，正式环境用正式的网络设备模型
        return "64c9bf804dacd" if settings.TEST_MODE else "6965ef4d44cf6"

    def fetch_tree(self, authorization: str) -> list:
        """拉取资产分类树（onlyTree），分类节点带实时计数 count。"""
        body = self._post(
            "/backend_api/cmdb/instance/list",
            {
                "keyword": "",
                "object_id": self._tree_seed(),
                "page": 1,
                "pageSize": 1,
                "senior_params": [],
                "onlyTree": True,
            },
            authorization,
        )
        return body.get("data", {}).get("tree") or []

    @staticmethod
    def _find_category_node(tree: list, category: str) -> Optional[dict]:
        """在分类树中按 label 精确匹配分类节点。

        刻意不做包含式模糊匹配：“软件”这类简称会静默命中“软件资产”，
        查错数据却返回成功；宁可报错，交给重试修正闭环。
        """
        exact: Optional[dict] = None

        def walk(node: Any) -> None:
            nonlocal exact
            if exact is not None:
                return
            if isinstance(node, dict):
                if node.get("type") in ("category_top", "category_next"):
                    if str(node.get("label") or "") == category:
                        exact = node
                        return
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(tree)
        return exact

    @staticmethod
    def _list_tree_categories(tree: list) -> List[str]:
        """收集分类树中实际存在的分类名（去重、保持出现顺序），用于报错时提示 LLM。"""
        labels: List[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") in ("category_top", "category_next"):
                    label = str(node.get("label") or "").strip()
                    if label and label not in labels:
                        labels.append(label)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(tree)
        return labels

    def _execute_category(self, category: str, spec: dict, authorization: str) -> dict:
        """分类级查询：用分类树的实时计数，支持 count 与按模型分组的 group_count。"""
        query_type = spec.get("query_type", "count")
        tree = self.fetch_tree(authorization)
        node = self._find_category_node(tree, category)
        if node is None:
            available = self._list_tree_categories(tree)
            hint = (
                f"分类树中实际存在的分类：{', '.join(available)}。请从中选择正确的分类名重试"
                if available
                else "请从表结构说明中选择正确的分类名"
            )
            raise CMDBQueryError(
                f"分类树中不存在分类“{category}”，禁止使用简称或编造分类名。{hint}"
            )
        if query_type == "count":
            return {
                "success": True,
                "columns": ["数量"],
                "rows": [[node.get("count") or 0]],
                "row_count": 1,
            }
        if query_type == "group_count":
            model_counts: List[tuple[str, int]] = []

            def collect(n: Any) -> None:
                if isinstance(n, dict):
                    if n.get("type") == "model":
                        model_counts.append((str(n.get("label") or n.get("id")), int(n.get("count") or 0)))
                    for value in n.values():
                        collect(value)
                elif isinstance(n, list):
                    for item in n:
                        collect(item)

            collect(node)
            model_counts.sort(key=lambda x: -x[1])
            rows = [[label, cnt] for label, cnt in model_counts]
            return {"success": True, "columns": ["模型", "数量"], "rows": rows, "row_count": len(rows)}
        if query_type == "list":
            # 分类级明细：跨模型轮流拉取，每轮每模型只取均分配额（页内偏移记忆），
            # 保证每个模型都有代表；返回 [模型, 实例名称] 两列（模型间字段异构，不做字段对齐）
            limit = min(int(spec.get("limit") or DEFAULT_LIST_LIMIT), MAX_LIST_LIMIT)
            model_nodes: List[dict] = []

            def collect_models(n: Any) -> None:
                if isinstance(n, dict):
                    if n.get("type") == "model":
                        model_nodes.append(n)
                    for value in n.values():
                        collect_models(value)
                elif isinstance(n, list):
                    for item in n:
                        collect_models(item)

            collect_models(node)
            model_nodes.sort(key=lambda x: -(int(x.get("count") or 0)))
            rows: List[list] = []
            state: Dict[str, dict] = {}  # 模型ID -> {page, items, offset}
            active = [m for m in model_nodes]
            while len(rows) < limit and active:
                per_model = max(1, (limit - len(rows)) // len(active))
                next_active: List[dict] = []
                for model_node in active:
                    if len(rows) >= limit:
                        break
                    mid = model_node["id"]
                    label = str(model_node.get("label") or mid)
                    st = state.get(mid)
                    if st is None:
                        st = {"page": 1, "items": None, "offset": 0}
                        state[mid] = st
                    if st["items"] is None or st["offset"] >= len(st["items"]):
                        data = self.fetch_page(mid, st["page"], PAGE_SIZE, authorization)
                        st["items"] = data.get("list") or []
                        st["page"] += 1
                        st["offset"] = 0
                        if not st["items"]:
                            continue  # 该模型已无更多实例
                    take = min(per_model, limit - len(rows), len(st["items"]) - st["offset"])
                    for inst in st["items"][st["offset"]:st["offset"] + take]:
                        rows.append([label, inst.get("instance_name")])
                    st["offset"] += take
                    next_active.append(model_node)
                active = next_active
            category_total = int(node.get("count") or 0)
            if category_total > len(rows):
                logger.warning(
                    "分类 {} 实例总数 {}，仅返回前 {} 条", category, category_total, len(rows)
                )
            return {"success": True, "columns": ["模型", "实例名称"], "rows": rows, "row_count": len(rows)}
        raise CMDBQueryError(f"分类级查询只支持 count / group_count / list，不支持 {query_type}")

    def execute(self, spec: dict, authorization: str) -> dict:
        """执行资产查询参数，返回 QueryResult 形状的 dict（success/columns/rows/row_count）。"""
        authorization = self._resolve_token(authorization)
        category = str(spec.get("category") or "").strip()
        if category:
            return self._execute_category(category, spec, authorization)
        object_id = self.resolve_object_id(spec, authorization)
        query_type = spec.get("query_type", "list")
        keyword = str(spec.get("keyword") or "")
        filters = spec.get("filters") or []
        for f in filters:
            if not isinstance(f, dict) or not f.get("name"):
                raise CMDBQueryError(f"filters 项格式错误: {f!r}，每项需含 name/condition/values")
        senior_params = [
            {
                "name": f["name"],
                "condition": f.get("condition", "incl"),
                "values": f.get("values") or [],
                "true_name": bool(f.get("true_name", False)),
            }
            for f in filters
        ]

        if query_type == "count":
            data = self.fetch_page(object_id, 1, 1, authorization, keyword, senior_params)
            total = data.get("total") or 0
            return {"success": True, "columns": ["数量"], "rows": [[total]], "row_count": 1}

        # 其余类型需要 中文属性名 -> 哈希ID 映射
        name_to_id = self.fetch_attributes(object_id, authorization)

        if query_type == "group_count":
            group_by = spec.get("group_by")
            if not group_by:
                raise CMDBQueryError("query_type 为 group_count 时必须提供 group_by 字段名")
            if group_by not in name_to_id:
                raise CMDBQueryError(
                    f"模型 {object_id} 不存在字段“{group_by}”，请从表结构说明中选择正确的字段名"
                )
            instances, _ = self.fetch_all(object_id, authorization, keyword, senior_params)
            counter: Counter = Counter()
            for inst in instances:
                attr = (inst.get("attribute") or {}).get(name_to_id[group_by]) or {}
                value = self._extract_value(inst, attr)
                counter[str(value) if value is not None else "未知"] += 1
            rows = [[k, v] for k, v in counter.most_common()]
            return {"success": True, "columns": [group_by, "数量"], "rows": rows, "row_count": len(rows)}

        # query_type == "list"（默认）：明细
        limit = min(int(spec.get("limit") or DEFAULT_LIST_LIMIT), MAX_LIST_LIMIT)
        fields = spec.get("fields") or ["instance_name"]
        for field in fields:
            if field not in name_to_id and field not in TOP_LEVEL_FIELDS:
                raise CMDBQueryError(
                    f"模型 {object_id} 不存在字段“{field}”，请从表结构说明中选择正确的字段名"
                )
        instances, _ = self.fetch_all(
            object_id, authorization, keyword, senior_params, max_instances=limit
        )
        columns, rows = self._build_rows(instances, list(fields), name_to_id, object_id)
        return {"success": True, "columns": columns, "rows": rows, "row_count": len(rows)}

    async def execute_query(self, spec: dict, authorization: str) -> dict:
        """异步入口。"""
        return await asyncio.to_thread(self.execute, spec, authorization)


cmdb_service = CmdbQueryService()
