#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CMDB 资产实例同步脚本

功能：
  1. 调用 CMDB API 分页拉取所有资产模型的实例数据；
  2. 通过 /backend_api/cmdb/attributes/{object_id} 接口把 attribute 中的
     哈希 ID 字段名映射为可读的中文列名；
  3. 每个资产模型写入 PostgreSQL 一张独立表（cmdb_asset_<object_id>），
     并在注册表 cmdb_asset_models 中记录模型与表名的对应关系；
  4. 增量更新：以 instance_id 为主键做 upsert（存在则更新，不存在则插入）。

用法：
    python scripts/sync_cmdb_asset.py                     # 全量同步（发现全部模型）
    python scripts/sync_cmdb_asset.py --models 64c9bf804dacd   # 只同步指定模型
    python scripts/sync_cmdb_asset.py --dry-run           # 只拉取、打印 DDL 和统计，不写库
    python scripts/sync_cmdb_asset.py --dump-ddl --ddl-out scripts/create_cmdb_asset_tables.sql
                                                          # 生成全部模型的建表 SQL 文件
    python scripts/sync_cmdb_asset.py --dump-md --md-out source/资产数据表定义.md
                                                          # 生成资产表定义 markdown（供 source/tables.py 解析）

配置（环境变量优先，其次读取项目根目录 .env）：
    CMDB_BASE_URL           默认 http://172.29.8.130
    CMDB_TOKEN              Bearer Token（必填）
    CMDB_OBJECT_IDS         逗号分隔的模型 object_id 列表；未配置时尝试从
                            instance/list 响应的分类树自动发现全部模型
    CMDB_PAGE_SIZE          分页大小，默认 50
    CMDB_REQUEST_INTERVAL   每次分页请求间隔秒数，默认 0.1
    DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD 或 DATABASE_URL
                            复用 config.Settings 中已有的数据库配置

回滚说明：本脚本为纯新增文件，不修改任何现有代码；如需要回滚，删除本文件即可。
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import requests
from dotenv import load_dotenv

# 加载项目根目录 .env（不覆盖已存在的环境变量），并复用 config.Settings 的数据库配置
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402

logger = logging.getLogger("sync_cmdb_asset")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://172.29.8.130"
DEFAULT_SEED_OBJECT_ID = "64c9bf804dacd"  # 文档中的 UPS设备 模型，用于分类树发现
DEFAULT_PAGE_SIZE = 50
DEFAULT_REQUEST_INTERVAL = 0.1

REGISTRY_TABLE = "cmdb_asset_models"

# 固定列（每个模型表都有），属性列名与之冲突时自动加后缀
FIXED_COLUMNS = {
    "instance_id",
    "instance_name",
    "object_id",
    "creator",
    "create_time",
    "update_time",
    "synced_at",
    # 防止属性列名为 userid 时触发 sql_service 的 imoc_user_group 富化查询
    # （asset 模块对应的库没有该表，会整条查询失败）
    "userid",
}

# value_type -> PostgreSQL 列类型。
# scalar（char/enum/date/time/ip/single/most）统一 TEXT；
# array 多值用逗号拼接后存 TEXT；布尔/数值保留类型以便 Text2SQL 直接比较。
COLUMN_TYPE_MAP = {
    "char": "TEXT",
    "enum": "TEXT",
    "date": "TEXT",
    "time": "TEXT",
    "ip": "TEXT",
    "single": "TEXT",
    "most": "TEXT",
    "array": "TEXT",
    "bool": "BOOLEAN",
    "boolean": "BOOLEAN",
    "int": "BIGINT",
    "float": "DOUBLE PRECISION",
}
DEFAULT_COLUMN_TYPE = "TEXT"

MAX_PAGES = 10000  # 分页安全上限，防止接口异常导致死循环
MAX_IDENT_BYTES = 60  # PG 标识符上限 63 字节，留 3 字节余量


def load_config() -> dict[str, Any]:
    """组装脚本配置：CMDB 配置来自环境变量（.env 已加载），数据库复用 config.Settings。"""
    token = os.environ.get("CMDB_TOKEN", "").strip()
    if not token:
        logger.error(
            "缺少 CMDB_TOKEN（Bearer Token）。请通过环境变量或项目根目录 .env 配置，"
            "例如：export CMDB_TOKEN=xxx"
        )
        sys.exit(2)

    object_ids = [
        oid.strip()
        for oid in os.environ.get("CMDB_OBJECT_IDS", "").split(",")
        if oid.strip()
    ]
    return {
        "base_url": os.environ.get("CMDB_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "token": token,
        "object_ids": object_ids,
        "seed_object_id": object_ids[0] if object_ids else DEFAULT_SEED_OBJECT_ID,
        "page_size": int(os.environ.get("CMDB_PAGE_SIZE", DEFAULT_PAGE_SIZE)),
        "request_interval": float(
            os.environ.get("CMDB_REQUEST_INTERVAL", DEFAULT_REQUEST_INTERVAL)
        ),
    }


def build_sync_dsn() -> str:
    """基于 config.Settings 构造 psycopg2 可用的同步 DSN。"""
    if settings.DATABASE_URL:
        # 兼容 SQLAlchemy 风格的 async 前缀
        return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return (
        f"host={settings.DB_HOST} port={settings.DB_PORT} dbname={settings.DB_NAME} "
        f"user={settings.DB_USER} password={settings.DB_PASSWORD}"
    )


# ---------------------------------------------------------------------------
# CMDB API 客户端
# ---------------------------------------------------------------------------


class CmdbClient:
    """CMDB 资产 API 客户端（参考 docs/CMDB_API分析.md）。"""

    def __init__(self, base_url: str, token: str, page_size: int, interval: float) -> None:
        self.base_url = base_url
        self.page_size = page_size
        self.interval = interval
        self.session = requests.Session()
        self.session.verify = False  # 正式环境 HTTPS 证书不匹配 IP，跳过校验
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "Accept": "application/json, text/plain, */*",
                "Accept-language": "zh-CN",
                "x-requested-with": "XMLHttpRequest",
                # 正式平台 RBAC 要求请求带 Cookie 头才放行 instance/list
                "Cookie": f"accessToken={token}",
            }
        )
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _get(self, path: str) -> dict[str, Any]:
        resp = self.session.get(f"{self.base_url}{path}", timeout=30)
        return self._check(resp)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self.session.post(f"{self.base_url}{path}", json=payload, timeout=30)
        return self._check(resp)

    @staticmethod
    def _check(resp: requests.Response) -> dict[str, Any]:
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise RuntimeError(f"CMDB API 返回错误 code={body.get('code')}: {body.get('message')}")
        return body

    def fetch_page(self, object_id: str, page: int) -> dict[str, Any]:
        """分页拉取某个模型的实例列表，返回 instances 对象。"""
        payload = {
            "keyword": "",
            "object_id": object_id,
            "page": page,
            "pageSize": self.page_size,
            "senior_params": [],
        }
        body = self._post("/backend_api/cmdb/instance/list", payload)
        return body["data"]["instances"]

    def fetch_attributes(self, object_id: str) -> list[dict[str, Any]]:
        """获取模型的属性定义：[{id, name, value_type, ...}]，用于哈希 ID -> 可读列名映射。"""
        body = self._get(f"/backend_api/cmdb/attributes/{object_id}?visible=1")
        data = body.get("data")
        if not isinstance(data, list):
            raise RuntimeError(f"attributes 接口返回格式异常: {type(data).__name__}")
        return data

    def discover_models(self, seed_object_id: str) -> list[dict[str, Any]]:
        """从 instance/list 响应的分类树中递归发现全部资产模型。

        分类树节点带 type 字段：type == "model" 的节点是资产模型节点
        （id 即模型的 object_id），其余为分类节点。
        """
        payload = {
            "keyword": "",
            "object_id": seed_object_id,
            "page": 1,
            "pageSize": 1,
            "senior_params": [],
            "onlyTree": True,  # 仅返回分类树计数，不返回实例列表
        }
        body = self._post("/backend_api/cmdb/instance/list", payload)
        tree = body.get("data", {}).get("tree", [])
        if not tree:
            logger.warning("分类树为空，无法自动发现模型，请通过 CMDB_OBJECT_IDS 显式指定")
            return []

        models: dict[str, dict[str, Any]] = {}

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                # 模型节点：type == "model"，id 即模型 object_id；分类节点直接跳过
                if node.get("type") == "model":
                    object_id = node.get("id")
                    if object_id:
                        models.setdefault(
                            str(object_id),
                            {
                                "object_id": str(object_id),
                                "name": node.get("name") or node.get("label") or str(object_id),
                                "category_top": node.get("category_top"),
                                "category_next": node.get("category_next"),
                            },
                        )
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(tree)
        logger.info("从分类树发现 %d 个资产模型", len(models))
        return list(models.values())


# ---------------------------------------------------------------------------
# 字段映射与值规整
# ---------------------------------------------------------------------------


def quote_ident(ident: str) -> str:
    """把列名/表名安全地包裹为带双引号的 PG 标识符，并做长度保护。"""
    # 截断到 60 字节以内（PG 标识符上限 63 字节）
    encoded = ident.encode("utf-8")
    if len(encoded) > MAX_IDENT_BYTES:
        ident = encoded[:MAX_IDENT_BYTES].decode("utf-8", errors="ignore")
    return '"' + ident.replace('"', '""') + '"'


def extract_value_type(attr_def: dict[str, Any]) -> str:
    """从属性定义中容错地提取值类型，取不到时按 char 处理。"""
    for key in ("value_type", "type"):
        value = attr_def.get(key)
        if isinstance(value, str) and value:
            return value.lower()
    nested = attr_def.get("value")
    if isinstance(nested, dict):
        value = nested.get("type")
        if isinstance(value, str) and value:
            return value.lower()
    return "char"


def normalize_column_name(name: str, used: set[str]) -> str:
    """规整列名：去空白、截断、非空、去重（冲突时加 _2/_3 后缀）、避开固定列。"""
    name = (name or "").strip() or "unnamed"
    # 内部空白 -> 下划线：含空格的 PG 标识符必须双引号，
    # 且 LLM 生成 SQL 时易在中文名内插空格导致列名错乱
    name = re.sub(r"\s+", "_", name)
    # 截断到 56 字节（MAX_IDENT_BYTES - 4）：真实 PG 列名即按此截断，
    # 表定义 markdown / Milvus 向量必须与之一致，否则 LLM 会生成不存在的列名；
    # 预留 4 字节给 _2/_999 去重后缀，保证后缀后仍不超过 quote_ident 的 60 字节上限
    encoded = name.encode("utf-8")
    if len(encoded) > MAX_IDENT_BYTES - 4:
        name = encoded[:MAX_IDENT_BYTES - 4].decode("utf-8", errors="ignore")
    base = name
    for i in range(2, 1000):
        if name not in used and name not in FIXED_COLUMNS:
            break
        name = f"{base}_{i}"
    return name


def normalize_value(value: Any, value_type: str) -> Any:
    """把 API 返回的属性值规整为可写入对应 PG 列类型的值。

    规则：空值/空串 -> None；bool -> 布尔；int/float -> 数值（解析失败 -> None）；
    array -> 逗号拼接字符串（空数组 -> None）；其余 -> 字符串。
    """
    if value is None or value == "":
        return None

    if value_type in ("bool", "boolean"):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "是")
        return bool(value)

    if value_type == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    if value_type == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    if value_type == "array":
        if isinstance(value, (list, tuple)):
            if not value:
                return None
            return ",".join(str(item) for item in value if item is not None)
        return str(value)

    return str(value)


# ---------------------------------------------------------------------------
# 建表与同步
# ---------------------------------------------------------------------------


def render_registry_ddl() -> str:
    """模型注册表建表语句。"""
    return f"""CREATE TABLE IF NOT EXISTS {quote_ident(REGISTRY_TABLE)} (
    object_id TEXT PRIMARY KEY,
    name TEXT,
    category_top TEXT,
    category_next TEXT,
    table_name TEXT NOT NULL,
    attribute_count INT,
    instance_count INT,
    synced_at TIMESTAMP DEFAULT now()
);"""


def render_model_ddl(model: dict[str, Any], columns: list[tuple[str, str, str, str]]) -> str:
    """渲染单个模型表的完整建表语句（固定列 + 属性列，带哈希属性ID注释）。

    注意：逗号必须放在 -- 注释之前，否则会被注释吞掉导致语法错误。
    """
    object_id = model["object_id"]
    fixed = [
        "    instance_id TEXT PRIMARY KEY",
        "    instance_name TEXT",
        "    object_id TEXT",
        "    creator TEXT",
        "    create_time TEXT",
        "    update_time TEXT",
        "    synced_at TIMESTAMP DEFAULT now()",
    ]
    attr_lines = [
        f"    {quote_ident(col_name)} {pg_type}{',' if i < len(columns) - 1 else ''}"
        f"  -- 属性ID: {attr_id}"
        for i, (col_name, _, pg_type, attr_id) in enumerate(columns)
    ]
    # 固定列用 ",\n" 拼接；属性行自带行内逗号（在注释前），用 "\n" 拼接
    body = ",\n".join(fixed)
    if attr_lines:
        body += ",\n" + "\n".join(attr_lines)
    header = f"-- 模型: {model.get('name') or object_id} ({object_id})"
    if model.get("category_top"):
        header += f"，分类: {model['category_top']}"
    return (
        f"{header}\n"
        f"CREATE TABLE IF NOT EXISTS {quote_ident(f'cmdb_asset_{object_id}')} (\n"
        + body
        + "\n);"
    )


def infer_value_type_from_column(pg_type: str) -> str:
    """attribute 值对象里没有类型信息时，按列类型反推值类型。"""
    if pg_type == "BOOLEAN":
        return "bool"
    if pg_type == "BIGINT":
        return "int"
    if pg_type == "DOUBLE PRECISION":
        return "float"
    return "char"


def get_attr_columns(attr_defs: Iterable[dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    """根据属性定义生成列清单：[(列名, 引用名, PG类型, 属性ID)]。"""
    columns: list[tuple[str, str, str, str]] = []
    used: set[str] = set()
    for attr_def in attr_defs:
        attr_id = str(attr_def.get("id") or "").strip()
        raw_name = attr_def.get("name") or attr_id or "unnamed"
        name = normalize_column_name(str(raw_name), used)
        used.add(name)
        value_type = extract_value_type(attr_def)
        columns.append(
            (name, quote_ident(name), COLUMN_TYPE_MAP.get(value_type, DEFAULT_COLUMN_TYPE), attr_id)
        )
    return columns


def build_instances_rows(
    instances: list[dict[str, Any]], columns: list[tuple[str, str, str, str]]
) -> list[tuple[Any, ...]]:
    """把实例列表转换成按列清单对齐的属性值元组列表。

    attribute 的键是哈希 ID（个别字段如 main_id 原生就是可读键），
    通过列清单携带的 attr_id 取值。
    """
    rows: list[tuple[Any, ...]] = []
    for instance in instances:
        attribute = instance.get("attribute") or {}
        values: list[Any] = []
        for _, _, pg_type, attr_id in columns:
            attr = attribute.get(attr_id) or {}
            value = attr.get("value")
            value_type = (attr.get("value_type") or "").strip().lower() if isinstance(attr, dict) else ""
            if not value_type:
                value_type = infer_value_type_from_column(pg_type)
            values.append(normalize_value(value, value_type))
        rows.append(tuple(values))
    return rows


def ensure_model_table(conn, object_id: str, columns: list[tuple[str, str, str, str]]) -> None:
    """建模型表（不存在时，先建固定列骨架）并补齐新增的属性列。"""
    table_name = f"cmdb_asset_{object_id}"
    with conn.cursor() as cur:
        cur.execute(render_model_ddl({"object_id": object_id}, []))
        # 补齐属性列（模型新增属性后再次运行也能增量加列）
        for _, quoted_name, pg_type, _ in columns:
            cur.execute(
                f"ALTER TABLE {quote_ident(table_name)} "
                f"ADD COLUMN IF NOT EXISTS {quoted_name} {pg_type}"
            )
    conn.commit()


def build_upsert_sql(object_id: str, columns: list[tuple[str, str, str, str]]) -> str:
    """构造按 instance_id 的 upsert 语句（配合 execute_values 使用的 VALUES %s 模板）。"""
    fixed = ["instance_id", "instance_name", "object_id", "creator", "create_time", "update_time"]
    col_sql = ", ".join(quote_ident(name) for name in fixed + [c[0] for c in columns])
    set_sql = ", ".join(
        f"{quote_ident(name)} = EXCLUDED.{quote_ident(name)}"
        for name in fixed + [c[0] for c in columns]
        if name != "instance_id"
    ) + ", synced_at = now()"
    return (
        f"INSERT INTO {quote_ident(f'cmdb_asset_{object_id}')} ({col_sql}) VALUES %s "
        f"ON CONFLICT (instance_id) DO UPDATE SET {set_sql} "
        f"RETURNING (xmax = 0) AS inserted"
    )


def upsert_instances(
    conn, object_id: str, columns: list[tuple[str, str, str, str]], instances: list[dict[str, Any]]
) -> tuple[int, int]:
    """按 instance_id 做 upsert，返回 (inserted, updated)。"""
    # 缺少 instance_id 的实例无法做主键，跳过并告警
    valid = [inst for inst in instances if inst.get("instance_id")]
    skipped = len(instances) - len(valid)
    if skipped:
        logger.warning("模型 %s 有 %d 条实例缺少 instance_id，已跳过", object_id, skipped)
    if not valid:
        return 0, 0

    fixed = ["instance_id", "instance_name", "object_id", "creator", "create_time", "update_time"]
    attr_rows = build_instances_rows(valid, columns)
    full_rows = [
        (
            instance.get("instance_id"),
            instance.get("instance_name"),
            instance.get("object_id"),
            instance.get("creator"),
            instance.get("create_time"),
            instance.get("update_time"),
            *attr_row,
        )
        for instance, attr_row in zip(valid, attr_rows)
    ]

    sql = build_upsert_sql(object_id, columns)
    inserted = updated = 0
    with conn.cursor() as cur:
        from psycopg2.extras import execute_values

        returned = execute_values(cur, sql, full_rows, fetch=True)
        for (is_inserted,) in returned:
            if is_inserted:
                inserted += 1
            else:
                updated += 1
    conn.commit()
    return inserted, updated


def upsert_registry(
    conn, model: dict[str, Any], columns: list[tuple[str, str, str]], total: int,
    registry_table: str = REGISTRY_TABLE,
) -> None:
    """更新模型注册表。"""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO {quote_ident(registry_table)}
                (object_id, name, category_top, category_next, table_name, attribute_count, instance_count, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (object_id) DO UPDATE SET
                name = EXCLUDED.name,
                category_top = EXCLUDED.category_top,
                category_next = EXCLUDED.category_next,
                table_name = EXCLUDED.table_name,
                attribute_count = EXCLUDED.attribute_count,
                instance_count = EXCLUDED.instance_count,
                synced_at = now()
            """,
            (
                model["object_id"],
                model.get("name"),
                model.get("category_top"),
                model.get("category_next"),
                f"cmdb_asset_{model['object_id']}",
                len(columns),
                total,
            ),
        )
    conn.commit()


def sync_model(
    conn, client: CmdbClient, model: dict[str, Any], dry_run: bool,
    registry_only: bool = False, registry_table: str = REGISTRY_TABLE,
) -> dict[str, Any]:
    """同步单个模型：拉取属性定义 -> 分页拉取实例 -> 建表 -> upsert。返回统计信息。

    registry_only=True 时只拉属性定义与总数（首页）更新注册表，
    不建表、不拉全量实例（用于给服务端提供模型名解析，如正式环境）。
    """
    object_id = model["object_id"]
    name = model.get("name") or object_id
    stats = {"object_id": object_id, "name": name, "total": 0, "inserted": 0, "updated": 0}

    logger.info("同步模型 %s (%s)：拉取属性定义...", name, object_id)
    attr_defs = client.fetch_attributes(object_id)
    columns = get_attr_columns(attr_defs)
    logger.info("属性列（哈希ID -> 可读列名）共 %d 列", len(columns))

    if registry_only:
        # 只拉首页拿 total，不建表不拉全量实例
        data = client.fetch_page(object_id, 1)
        total = data.get("total") or 0
        stats["total"] = total
        upsert_registry(conn, model, columns, total, registry_table)
        logger.info("模型 %s 注册表已更新（registry-only）：实例数 %d", name, total)
        return stats

    # 分页拉取全部实例
    instances: list[dict[str, Any]] = []
    page = 1
    total: int | None = None
    while True:
        data = client.fetch_page(object_id, page)
        total = data.get("total") or 0
        items = data.get("list") or []
        instances.extend(items)
        logger.info("第 %d 页：本页 %d 条，累计 %d/%d", page, len(items), len(instances), total)
        if not items or len(instances) >= total or page >= MAX_PAGES:
            break
        page += 1
        time.sleep(client.interval)

    stats["total"] = total
    if total and len(instances) < total:
        logger.warning("模型 %s 只拉到 %d/%d 条实例", name, len(instances), total)

    if dry_run:
        logger.info("--dry-run-- 实例 %d 条，建表 DDL：\n%s", total, render_model_ddl(model, columns))
        return stats

    ensure_model_table(conn, object_id, columns)
    stats["inserted"], stats["updated"] = upsert_instances(conn, object_id, columns, instances)
    upsert_registry(conn, model, columns, total, registry_table)
    logger.info(
        "模型 %s 同步完成：共 %d 条，新增 %d，更新 %d",
        name, total, stats["inserted"], stats["updated"],
    )
    return stats


def init_registry(conn, registry_table: str = REGISTRY_TABLE) -> None:
    """创建模型注册表（幂等）。"""
    with conn.cursor() as cur:
        cur.execute(render_registry_ddl().replace(quote_ident(REGISTRY_TABLE), quote_ident(registry_table)))
    conn.commit()


def dump_ddl(client: CmdbClient, models: list[dict[str, Any]]) -> tuple[str, int]:
    """为全部模型生成完整建表 SQL（注册表 + 每个模型一张表），不写库。

    返回 (SQL 文本, 失败模型数)。
    """
    sections = [
        "-- =====================================================================",
        "-- CMDB 资产表建表语句",
        "-- 由 python scripts/sync_cmdb_asset.py --dump-ddl 生成；",
        "-- 与同步脚本 upsert 使用的表结构完全一致，可直接用 psql 执行。",
        "-- =====================================================================",
        "",
        render_registry_ddl(),
    ]
    failed = 0
    for model in models:
        try:
            attr_defs = client.fetch_attributes(model["object_id"])
            columns = get_attr_columns(attr_defs)
            sections.append("")
            sections.append(render_model_ddl(model, columns))
        except Exception as exc:  # 单个模型失败不中断整体
            failed += 1
            logger.exception(
                "模型 %s (%s) 属性拉取失败，已跳过：%s",
                model.get("name"), model["object_id"], exc,
            )
    return "\n".join(sections), failed


# ---------------------------------------------------------------------------
# 表定义 markdown 渲染（供 source/tables.py 解析，格式对齐 source/告警数据表定义.md）
# ---------------------------------------------------------------------------


def _attr_remark(attr_def: dict[str, Any]) -> str:
    """从属性定义中提取中文备注；取不到返回空串。表格单元格内管道符需转义。"""
    for key in ("description", "remark", "note", "desc", "explain"):
        value = attr_def.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().replace("|", "\\|")
    return ""


def render_model_markdown(model: dict[str, Any], attr_defs: Iterable[dict[str, Any]], index: int) -> str:
    """渲染单个模型表的 markdown 定义块，格式与 source/告警数据表定义.md 完全一致。"""
    object_id = model["object_id"]
    # 表注释用全角括号替换方括号（table_block_matcher 的 table_comment 到第一个 ] 为止）
    name = str(model.get("name") or object_id).replace("[", "（").replace("]", "）").strip()
    table_name = f"cmdb_asset_{object_id}"
    columns = get_attr_columns(attr_defs)

    lines = [f"# {index}. {table_name} [{name}]"]
    desc = f"> {name}资产模型实例表，记录{name}资产的属性与状态信息"
    if model.get("category_top"):
        desc += f"，分类：{model['category_top']}"
    lines += [desc, "", "## 表结构", ""]
    lines.append("| 字段名 | 数据类型 | 主键 | 非空 | 默认值 | 备注说明 |")
    lines.append("|--------|----------|------|------|--------|----------|")

    # 固定列（与 render_model_ddl 的 fixed 列表一一对应）
    fixed = [
        ("instance_id", "TEXT", "是", "是", "", "实例唯一ID（主键）"),
        ("instance_name", "TEXT", "否", "否", "", "实例名称"),
        ("object_id", "TEXT", "否", "是", "", "资产模型ID"),
        ("creator", "TEXT", "否", "否", "", "创建人"),
        ("create_time", "TEXT", "否", "否", "", "创建时间"),
        ("update_time", "TEXT", "否", "否", "", "更新时间"),
        ("synced_at", "TIMESTAMP", "否", "是", "now()", "同步时间"),
    ]
    for col_name, pg_type, pk, not_null, default, remark in fixed:
        lines.append(f"| {col_name} | {pg_type} | {pk} | {not_null} | {default} | {remark} |")

    attr_def_map = {str(d.get("id") or ""): d for d in attr_defs}
    for col_name, _, pg_type, attr_id in columns:
        remark = _attr_remark(attr_def_map.get(attr_id, {}))
        lines.append(f"| {col_name} | {pg_type} | 否 | 否 |  | {remark} |")
    return "\n".join(lines)


REGISTRY_MARKDOWN = """# 1. cmdb_asset_models [资产模型注册表]
> 资产模型注册表，记录每个资产模型(object_id)对应的表名(table_name)与实例统计信息，涉及具体资产类型时先在本表确认数据来源

## 表结构

| 字段名 | 数据类型 | 主键 | 非空 | 默认值 | 备注说明 |
|--------|----------|------|------|--------|----------|
| object_id | TEXT | 是 | 是 |  | 资产模型唯一ID |
| name | TEXT | 否 | 否 |  | 模型名称（如 UPS设备） |
| category_top | TEXT | 否 | 否 |  | 一级分类 |
| category_next | TEXT | 否 | 否 |  | 二级分类 |
| table_name | TEXT | 否 | 是 |  | 该模型实例数据对应的 PostgreSQL 表名 |
| attribute_count | INT | 否 | 否 |  | 属性列数量 |
| instance_count | INT | 否 | 否 |  | 实例数量 |
| synced_at | TIMESTAMP | 否 | 是 | now() | 最近同步时间 |"""


def render_markdown_definitions(client: CmdbClient, models: list[dict[str, Any]]) -> tuple[str, int]:
    """生成全部资产表的 markdown 定义文档（注册表 + 每个模型一张表），不写库。

    输出格式与 source/告警数据表定义.md 完全一致（source/tables.py 的
    table_block_matcher / markdown_table_to_dataframe 可直接解析）。
    文件首行必须是第一个表块（禁止前言），否则首个 <br> 之前的文本会成为
    ASSET_TABLE_SCHEMAS[0] 的脏文档进入 Milvus。
    返回 (markdown 文本, 失败模型数)。
    """
    blocks = [REGISTRY_MARKDOWN]
    failed = 0
    for index, model in enumerate(models, start=2):  # 注册表固定为 # 1
        try:
            attr_defs = client.fetch_attributes(model["object_id"])
            blocks.append(render_model_markdown(model, attr_defs, index))
        except Exception as exc:  # 单个模型失败不中断整体
            failed += 1
            logger.exception(
                "模型 %s (%s) 属性拉取失败，已跳过：%s",
                model.get("name"), model["object_id"], exc,
            )
    return "\n<br>\n\n".join(blocks) + "\n", failed


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    parser = argparse.ArgumentParser(description="CMDB 资产实例同步脚本")
    parser.add_argument(
        "--models",
        help="只同步指定的模型 object_id（逗号分隔），为空则同步发现的全部模型",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只拉取 API 并打印建表 DDL 与统计，不写数据库",
    )
    parser.add_argument(
        "--dump-ddl",
        action="store_true",
        help="只生成建表 SQL（注册表 + 全部模型表）并退出，不写数据库",
    )
    parser.add_argument(
        "--ddl-out",
        help="配合 --dump-ddl，把 SQL 写入指定文件（默认打印到 stdout）",
    )
    parser.add_argument(
        "--dump-md",
        action="store_true",
        help="只生成资产表定义 markdown（注册表 + 全部模型表）并退出，不写数据库",
    )
    parser.add_argument(
        "--md-out",
        help="配合 --dump-md，把 markdown 写入指定文件（默认打印到 stdout；建议写 source/资产数据表定义.md）",
    )
    parser.add_argument(
        "--registry-only",
        action="store_true",
        help="只拉属性定义与实例总数更新注册表，不建表、不拉全量实例（用于服务端模型名解析）",
    )
    parser.add_argument(
        "--registry-suffix",
        default="",
        help="注册表名后缀（如 _prod 写入 cmdb_asset_models_prod，默认无后缀写 cmdb_asset_models）",
    )
    parser.add_argument(
        "--seed-object-id",
        help="分类树自动发现用的种子 object_id（需为目标 CMDB 的有效模型ID；默认取 CMDB_OBJECT_IDS 首个或内置默认）",
    )
    args = parser.parse_args()

    config = load_config()
    client = CmdbClient(
        config["base_url"], config["token"], config["page_size"], config["request_interval"]
    )

    # 确定要同步的模型列表：--models > CMDB_OBJECT_IDS > 分类树自动发现
    if args.models:
        models = [
            {"object_id": oid.strip(), "name": oid.strip()}
            for oid in args.models.split(",")
            if oid.strip()
        ]
    elif config["object_ids"]:
        models = [
            {"object_id": oid, "name": oid} for oid in config["object_ids"]
        ]
    else:
        models = client.discover_models(args.seed_object_id or config["seed_object_id"])
        if not models:
            logger.error(
                "未发现任何资产模型。请检查 CMDB_TOKEN 是否有效，或通过 CMDB_OBJECT_IDS 显式指定模型。"
            )
            sys.exit(1)

    if args.dump_ddl:
        ddl, failed = dump_ddl(client, models)
        if args.ddl_out:
            Path(args.ddl_out).write_text(ddl + "\n", encoding="utf-8")
            logger.info(
                "建表 SQL 已写入 %s（模型 %d 个，失败 %d 个）",
                args.ddl_out, len(models), failed,
            )
        else:
            print(ddl)
        sys.exit(1 if failed else 0)

    if args.dump_md:
        md, failed = render_markdown_definitions(client, models)
        if args.md_out:
            Path(args.md_out).write_text(md, encoding="utf-8")
            logger.info(
                "表定义 markdown 已写入 %s（模型 %d 个，失败 %d 个）",
                args.md_out, len(models), failed,
            )
        else:
            print(md)
        sys.exit(1 if failed else 0)

    import psycopg2

    registry_table = REGISTRY_TABLE + args.registry_suffix
    conn = None
    if not args.dry_run:
        conn = psycopg2.connect(build_sync_dsn())
        init_registry(conn, registry_table)

    failed = 0
    try:
        for model in models:
            try:
                stats = sync_model(
                    conn, client, model, args.dry_run,
                    registry_only=args.registry_only, registry_table=registry_table,
                )
                logger.info(
                    "模型 %s (%s)：%s",
                    stats["name"],
                    stats["object_id"],
                    f"新增 {stats['inserted']}，更新 {stats['updated']}" if not args.dry_run else f"实例 {stats['total']} 条",
                )
            except Exception as exc:  # 单个模型失败不中断整体
                failed += 1
                logger.exception("模型 %s (%s) 同步失败：%s", model.get("name"), model["object_id"], exc)
    finally:
        if conn is not None:
            conn.close()

    if failed:
        logger.error("共 %d 个模型同步失败", failed)
        sys.exit(1)
    logger.info("全部模型同步完成 ✅")


if __name__ == "__main__":
    main()
