import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List
from xml.etree import ElementTree as ET

from config import settings
from sql_executor import EncryptedSQLExecutor

from logg import logger


@dataclass(slots=True)
class XmlField:
    """XML 字段对象，extra 中预留扩展信息。"""

    name: str
    value: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TableSearchMeta:
    """单表模糊搜索需要的最小元信息。"""

    table: str
    primary_key: str | None
    searchable_columns: list[str]
    xml_column: str | None


class SQLService:
    """SQL执行服务"""

    TEXT_TYPE_PATTERN = re.compile(
        r"(varchar|text|char|character varying|string|clob)",
        re.IGNORECASE,
    )
    PRIMARY_KEY_TRUE_VALUES = {"y", "yes", "true", "1", "是"}
    FIELD_NAME_CANDIDATES = ("字段名", "字段名称")
    FIELD_TYPE_CANDIDATES = ("数据类型", "字段类型")
    PRIMARY_KEY_CANDIDATES = ("主键",)

    @staticmethod
    def _get_schema_column_names(schema_df, *candidates: str) -> tuple[str, ...]:
        available_columns = set(schema_df.columns)
        return tuple(candidate for candidate in candidates if candidate in available_columns)

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text.lower() == "nan" else text

    @classmethod
    def _contains_entity(cls, value: Any, entity_lower: str) -> bool:
        return bool(entity_lower) and entity_lower in cls._normalize_text(value).lower()

    @staticmethod
    def _deduplicate_keep_order(columns: list[str]) -> list[str]:
        deduplicated: list[str] = []
        seen: set[str] = set()
        for column in columns:
            if column and column not in seen:
                deduplicated.append(column)
                seen.add(column)
        return deduplicated

    @classmethod
    def _is_text_searchable_type(cls, raw_field_type: str) -> bool:
        normalized_type = raw_field_type.strip().lower()
        if not normalized_type:
            return False
        return bool(cls.TEXT_TYPE_PATTERN.search(normalized_type))

    @staticmethod
    def _get_schema_resources(intent: str):
        from source.tables import (
            ATTDN_SCHEMA_DF_MAP,
            ATTDN_TABLENAMES,
            BPM_SCHEMA_DF_MAP,
            BPM_TABLENAMES,
            ALERT_SCHEMA_DF_MAP,
            ALERT_TABLENAMES,
            ASSET_ACTIVE_SCHEMA_DF_MAP,
            ASSET_ACTIVE_TABLENAMES,
        )

        if intent in ("attendance", "attdance"):
            return ATTDN_TABLENAMES, ATTDN_SCHEMA_DF_MAP
        elif intent == "alert":
            return ALERT_TABLENAMES, ALERT_SCHEMA_DF_MAP
        elif intent == "asset":
            return ASSET_ACTIVE_TABLENAMES, ASSET_ACTIVE_SCHEMA_DF_MAP
        return BPM_TABLENAMES, BPM_SCHEMA_DF_MAP

    def _get_table_search_meta(self, table: str, intent: str) -> TableSearchMeta:
        _, schema_df_map = self._get_schema_resources(intent)
        schema_df = schema_df_map.get(table)
        if schema_df is None or schema_df.empty:
            return TableSearchMeta(
                table=table,
                primary_key=None,
                searchable_columns=[],
                xml_column=None,
            )

        field_name_columns = self._get_schema_column_names(schema_df, *self.FIELD_NAME_CANDIDATES)
        field_type_columns = self._get_schema_column_names(schema_df, *self.FIELD_TYPE_CANDIDATES)
        primary_key_columns = self._get_schema_column_names(schema_df, *self.PRIMARY_KEY_CANDIDATES)
        if not field_name_columns or not field_type_columns:
            return TableSearchMeta(
                table=table,
                primary_key=None,
                searchable_columns=[],
                xml_column=None,
            )

        field_name_column = field_name_columns[0]
        field_type_column = field_type_columns[0]
        primary_key_column = primary_key_columns[0] if primary_key_columns else None

        primary_key: str | None = None
        searchable_columns: list[str] = []
        xml_column: str | None = None

        for _, row in schema_df.iterrows():
            raw_field_name = self._normalize_text(row.get(field_name_column))
            raw_field_type = self._normalize_text(row.get(field_type_column)).lower()
            raw_primary_key = (
                self._normalize_text(row.get(primary_key_column)).lower()
                if primary_key_column is not None
                else ""
            )
            if not raw_field_name:
                continue

            if primary_key is None and raw_primary_key in self.PRIMARY_KEY_TRUE_VALUES:
                primary_key = raw_field_name

            if "xml" in raw_field_type or raw_field_name.lower() == "xmldata":
                xml_column = raw_field_name
                continue

            if self._is_text_searchable_type(raw_field_type):
                searchable_columns.append(raw_field_name)

        searchable_columns = self._deduplicate_keep_order(searchable_columns)
        if xml_column in searchable_columns:
            searchable_columns.remove(xml_column)

        return TableSearchMeta(
            table=table,
            primary_key=primary_key,
            searchable_columns=searchable_columns,
            xml_column=xml_column,
        )


    def _parse_xml_fields(self, xml_text: str) -> list[XmlField]:
        normalized_xml = self._normalize_text(xml_text)
        if not normalized_xml:
            return []

        try:
            root = ET.fromstring(normalized_xml)
        except ET.ParseError as exc:
            logger.warning(f"XML 解析失败，无法提取字段: {exc}")
            return []

        xml_fields: list[XmlField] = []
        for index, element in enumerate(root.iter()):
            if element is root:
                continue

            name = self._normalize_text(element.attrib.get("name")) or element.tag
            value = self._normalize_text(element.text)
            extra = {
                "tag": element.tag,
                "attributes": dict(element.attrib),
                "index": index,
            }
            xml_fields.append(XmlField(name=name, value=value, extra=extra))

        return xml_fields

    def _extract_xml_hits(self, xml_text: str, entity: str) -> list[XmlField]:
        entity_lower = self._normalize_text(entity).lower()
        if not entity_lower:
            return []

        xml_hits: list[XmlField] = []
        for xml_field in self._parse_xml_fields(xml_text):
            matched_on: list[str] = []
            #NOTE 没必要匹配字段名
            # if self._contains_entity(xml_field.name, entity_lower):
                # matched_on.append("name")
            if self._contains_entity(xml_field.value, entity_lower):
                matched_on.append("value")
            if not matched_on:
                continue

            xml_hits.append(
                XmlField(
                    name=xml_field.name,
                    value=xml_field.value,
                    extra={
                        **xml_field.extra,
                        "matched_on": matched_on,
                    },
                )
            )

        return xml_hits

    def _build_fuzzy_query_sql(self, table_meta: TableSearchMeta, entity: str) -> tuple[str, list[str]] | None:
        safe_entity = entity.replace("'", "''")
        select_columns = self._deduplicate_keep_order(
            [
                table_meta.primary_key or "",
                *table_meta.searchable_columns,
                table_meta.xml_column or "",
            ]
        )
        where_clauses = [f"{col} LIKE '%{safe_entity}%'" for col in table_meta.searchable_columns]
        if table_meta.xml_column:
            where_clauses.append(f"{table_meta.xml_column} LIKE '%{safe_entity}%'")

        if not select_columns or not where_clauses:
            return None

        query_sql = (
            f"SELECT {', '.join(select_columns)} "
            f"FROM {table_meta.table} "
            f"WHERE {' OR '.join(where_clauses)} "
            f"LIMIT 10"
        )
        return query_sql, select_columns

    def _build_hit_labels(
        self,
        *,
        table: str,
        normal_hits: list[str],
        xml_hits: list[XmlField],
        xml_column: str | None,
        has_raw_xml_match: bool,
    ) -> list[str]:
        labels = {f"{table}.{column}" for column in normal_hits}
        if has_raw_xml_match and xml_column:
            labels.add(f"{table}.{xml_column}")

        if xml_column:
            for xml_hit in xml_hits:
                #NOTE hit xmldata的情况不应该与普通SQL字段一样处理
                # labels.add(f"{table}.{xml_column}.{xml_hit.name}")
                labels.add(f'{table}.{xml_column}./Items/WFItem[@name="{xml_hit.name}"]')

        return sorted(labels)

    def _execute_sql_sync(self, sql: str, authorization: str, intent: str) -> Dict[str, Any]:
        """执行SQL查询（同步版本）"""
        intent = 'attdance' if intent == 'attendance' else intent

        # duty_status 是英文旧字段，不含中文状态值，用它过滤必然 0 行；
        # 这里主动报错，让现有的"报错反馈给大模型"重试机制改写成 status
        if intent == 'attdance' and re.search(
            r"\bduty_status\b\s*(?:=|!=|<>|LIKE\b|NOT\s+LIKE\b|IN\s*\(|IS\s+)",
            sql,
            re.IGNORECASE,
        ):
            raise ValueError(
                "SQL执行错误: duty_status 是英文旧字段，禁止使用。请优先改用 "
                "imoc_attendance_all 视图的\"考勤状态\"列；若必须用底表，则使用 "
                "imoc_class_duty_user.status，取值只能是中文：未到岗、早退、缺勤、"
                "未签到、正常、迟到早退、迟到、未签退。例如查缺勤用 status = '缺勤'，"
                "查迟到用 status = '迟到'。"
            )

        with EncryptedSQLExecutor(test_mode=settings.TEST_MODE) as executor:
            def get_username_by_userid(userids: List[str]) -> Dict[str, str]:
                """根据用户ID获取用户名"""
                sql_dialect = f"select * from imoc_user_group where userid in ({','.join([f"'{i}'" for i in userids])})"
                result = executor.execute(
                    sql_dialect, module=intent, authorization=authorization, timeout=20
                )
                
                if not any(result.get('data')):
                    raise ValueError(f"SQL执行错误: {result.get('message')}")
                
                column_names: List[str] = result.get('data', dict()).get('columns', [])
                rows = result.get('data', dict()).get('rows', [])
                
                userid_index = column_names.index("userid")
                username_index = column_names.index("user_name")
                
                return {str(row[userid_index]): row[username_index] for row in rows}
            
            try:
                logger.debug(f"###### SQL原始字符串: [{sql.__repr__()}]")
                result = executor.execute(
                    sql=sql,
                    module=intent,
                    authorization=authorization,
                    timeout=60
                )
                # print(f"SQL查询结果：{result}")
                # result 示例:
                # ```s
                # {
                #     "code": 0,
                #     "message": "success",
                #     "data": {
                #         "columns": ["id", "name", "status", "create_time"],
                #         "rows": [
                #             [1, "项目A", 1, "2024-01-01 10:00:00"],
                #             [2, "项目B", 1, "2024-01-02 11:00:00"]
                #         ],
                #         "meta": {
                #         "total_rows": 2,
                #         "execution_time": 25.5,
                #         "sql_hash": "a1b2c3d4e5f6..."
                #         }
                #     }
                # }
                # ```
                
                if not any(result.get('data')):
                    raise ValueError(f"SQL执行错误: {result.get('message')}")
                
                column_names: List[str] = result.get('data', dict()).get('columns', [])
                rows = result.get('data', dict()).get('rows', [])
                
                userid_to_username = None
                if "userid" in column_names:
                    userid_index = column_names.index("userid")
                    userids = [str(row[userid_index]) for row in rows]
                    userid_to_username = get_username_by_userid(userids=userids)
                
                return {
                    'success': True,
                    'columns': column_names,
                    'rows': rows,
                    'row_count': len(rows),
                    'userid_to_username': userid_to_username,
                }
            
            except ValueError:
                raise
            except Exception:
                import traceback
                traceback.print_exc()
                raise
                # return {
                #     'success': False,
                #     'error': f"未知错误: {str(exc)}",
                #     'columns': [],
                #     'rows': [],
                #     'row_count': 0,
                #     'userid_to_username': None
                # }
    
    # 模糊查询白名单：只查核心表，避免无权限/无关表的慢查询
    _FUZZY_TABLE_ALLOWLIST = {
        "attendance": {"imoc_class_duty_user", "imoc_checkin_user", "imoc_class_user", "imoc_class_duty", "imoc_class_project"},
        "alert": {"view_alert_all", "view_alert_organization", "view_alert_business"},
        "asset": None,  # None = 全部 cmdb_asset_* 表（含注册表）参与模糊：表间异构，无法只挑核心表
        "bpm": None,  # None = use all tables
    }

    # 用户口语名与库内正式名常只差一个通用后缀（如"协同办公系统"对不上"中山市协同办公平台"），
    # 整串未命中时剥掉后缀用核心词再查一次
    _ENTITY_GENERIC_SUFFIXES = ("管理系统", "信息系统", "平台系统", "系统", "平台", "项目", "工程")

    # 名称类字段：用户报的是口语名，需要拿库内真实取值来对齐
    _NAME_COLUMN_KEYWORDS = ("名称", "姓名", "标题")
    _NAME_COLUMN_EXACT = {"name", "title", "fullname", "nickname"}

    # 库内真实取值缓存：{(intent, table, column): (过期时间戳, 取值列表)}
    _DISTINCT_VALUE_CACHE: dict[tuple[str, str, str], tuple[float, List[str]]] = {}
    _DISTINCT_VALUE_TTL = 600.0
    # 名称相似度阈值与返回上限
    _NAME_MATCH_THRESHOLD = 0.7
    _NAME_MATCH_LIMIT = 3

    @classmethod
    def _entity_variants(cls, entity: str) -> List[str]:
        """生成模糊查询的候选实体：原词 + 去掉通用后缀后的核心词"""
        normalized = cls._normalize_text(entity)
        if not normalized:
            return []
        variants = [normalized]
        for suffix in cls._ENTITY_GENERIC_SUFFIXES:
            if not normalized.endswith(suffix):
                continue
            stripped = normalized[: -len(suffix)].strip()
            # 核心词过短会命中过多无关数据（如只剩"办公"）
            if len(stripped) >= 2 and stripped not in variants:
                variants.append(stripped)
        return variants

    @classmethod
    def _is_name_column(cls, column: str) -> bool:
        lowered = column.lower()
        return (
            lowered in cls._NAME_COLUMN_EXACT
            or any(keyword in column for keyword in cls._NAME_COLUMN_KEYWORDS)
        )

    @staticmethod
    def _longest_common_substring_len(a: str, b: str) -> int:
        if not a or not b:
            return 0
        best = 0
        previous = [0] * (len(b) + 1)
        for char in a:
            current = [0] * (len(b) + 1)
            for index, other in enumerate(b, 1):
                if char == other:
                    current[index] = previous[index - 1] + 1
                    if current[index] > best:
                        best = current[index]
            previous = current
        return best

    @classmethod
    def _name_similarity(cls, entity_lower: str, value_lower: str) -> float:
        """名称相似度：包含关系优先，其次按最长公共子串占实体的比例"""
        if not entity_lower or not value_lower:
            return 0.0
        if entity_lower == value_lower:
            return 1.0
        shorter, longer = sorted((entity_lower, value_lower), key=len)
        if shorter in longer:
            return 0.85 + 0.15 * len(shorter) / len(longer)
        common = cls._longest_common_substring_len(entity_lower, value_lower)
        return common / len(entity_lower)

    async def _load_distinct_values(
        self, table: str, column: str, authorization: str, intent: str
    ) -> List[str]:
        """读取字段的库内真实取值（带TTL缓存），供名称相似度匹配使用"""
        cache_key = (intent, table, column)
        now = time.monotonic()
        cached = self._DISTINCT_VALUE_CACHE.get(cache_key)
        if cached is not None and cached[0] > now:
            return cached[1]

        sql = (
            f"SELECT DISTINCT {column} FROM {table} "
            f"WHERE {column} IS NOT NULL LIMIT 5000"
        )
        try:
            result = await self.execute_sql(sql, authorization, intent)
        except Exception as e:
            logger.error(f"读取 {table}.{column} 取值失败: {e}")
            return []

        columns = result.get("columns") or [column]
        column_index = columns.index(column) if column in columns else 0
        values: List[str] = []
        for row in result.get("rows", []):
            if column_index >= len(row):
                continue
            value = self._normalize_text(row[column_index])
            if value and value not in values:
                values.append(value)

        self._DISTINCT_VALUE_CACHE[cache_key] = (now + self._DISTINCT_VALUE_TTL, values)
        return values

    async def _match_by_distinct_values(
        self,
        entity: str,
        variants: List[str],
        tables: list[str],
        authorization: str,
        intent: str,
    ) -> List[str]:
        """名称类字段的真实取值相似度匹配

        用于口语名与库内正式名差异较大、LIKE 整串/去后缀都查不到的情况，
        返回形如 `表名.字段名=库内真实值` 的标签，供后续阶段直接用真实名称生成SQL。
        """
        variant_lowers = [v.lower() for v in variants if v]
        labels: List[str] = []

        for table in tables:
            table_meta = self._get_table_search_meta(table, intent)
            name_columns = [c for c in table_meta.searchable_columns if self._is_name_column(c)]
            for column in name_columns:
                values = await self._load_distinct_values(table, column, authorization, intent)
                scored = []
                for value in values:
                    score = max(
                        (self._name_similarity(v, value.lower()) for v in variant_lowers),
                        default=0.0,
                    )
                    if score >= self._NAME_MATCH_THRESHOLD:
                        scored.append((score, value))
                if not scored:
                    continue
                scored.sort(key=lambda item: (-item[0], len(item[1])))
                for score, value in scored[: self._NAME_MATCH_LIMIT]:
                    if len(value) > 100:
                        continue
                    labels.append(f"{table}.{column}={value}")
                    logger.info(
                        f"名称相似度匹配: 实体 '{entity}' -> {table}.{column} "
                        f"取值 '{value}' (score={score:.2f})"
                    )
        return labels

    async def fuzzy_query(self, entity: str, authorization: str, intent: str) -> List[str]:
        """模糊查询数据库中对应值的字段名"""
        if intent == "asset":
            # 资产不走 SQL 网关（平台不注册 asset module），模糊查询无可用执行通道；
            # 实体到字段的映射由 NER + 表结构说明（ASSET_RAW）完成
            return []
        tables, _ = self._get_schema_resources(intent)
        allowlist = self._FUZZY_TABLE_ALLOWLIST.get(intent)
        if allowlist is not None:
            tables = [t for t in tables if t in allowlist]
        if not tables:
            return []

        variants = self._entity_variants(entity)
        for variant in variants:
            entity_lower = self._normalize_text(variant).lower()
            if not entity_lower:
                continue
            matched_fields = await self._fuzzy_match_tables(
                variant, entity_lower, tables, authorization, intent
            )
            if matched_fields:
                if variant != entity:
                    logger.info(
                        f"实体 '{entity}' 整串未命中，降级为 '{variant}' 后命中 "
                        f"{len(matched_fields)} 个字段"
                    )
                return matched_fields

        # 前两轮都查不到：拿库内真实名称做相似度匹配（如"妇幼保健院系统"→"中山市妇幼保健信息系统"）
        matched_by_value = await self._match_by_distinct_values(
            entity, variants, tables, authorization, intent
        )
        if matched_by_value:
            logger.info(f"实体 '{entity}' LIKE 未命中，改为名称相似度匹配并命中 {len(matched_by_value)} 项")
        return matched_by_value

    async def _fuzzy_match_tables(
        self,
        entity: str,
        entity_lower: str,
        tables: list[str],
        authorization: str,
        intent: str,
    ) -> List[str]:
        """在给定表集合中并发执行实体的模糊匹配"""
        matched_fields = set()

        async def query_table(table: str):
            try:
                table_meta = self._get_table_search_meta(table, intent)
                if not table_meta.searchable_columns and not table_meta.xml_column:
                    return []

                sql_bundle = self._build_fuzzy_query_sql(table_meta, entity)
                if sql_bundle is None:
                    return []

                query_sql, selected_columns = sql_bundle

                query_result = await self.execute_sql(query_sql, authorization, intent)
                result_columns = query_result.get('columns', selected_columns)
                rows = query_result.get('rows', [])

                fields = []
                for row in rows:
                    row_map = {col: val for col, val in zip(result_columns, row)}
                    normal_hits = [
                        col for col in table_meta.searchable_columns
                        if self._contains_entity(row_map.get(col), entity_lower)
                    ]

                    xml_hits: list[XmlField] = []
                    has_raw_xml_match = False
                    if table_meta.xml_column:
                        xml_raw = self._normalize_text(row_map.get(table_meta.xml_column))
                        has_raw_xml_match = self._contains_entity(xml_raw, entity_lower)
                        if has_raw_xml_match:
                            xml_hits = self._extract_xml_hits(xml_raw, entity)

                    labels = self._build_hit_labels(
                        table=table,
                        normal_hits=normal_hits,
                        xml_hits=xml_hits,
                        xml_column=table_meta.xml_column,
                        has_raw_xml_match=has_raw_xml_match,
                    )
                    # 名称类字段补充库内真实取值（如 view_alert_business.业务名称=中山市协同办公平台），
                    # 让后续阶段能直接用真实名称生成SQL，而不是拿用户的口语名去 LIKE
                    for column in normal_hits:
                        if not self._is_name_column(column):
                            continue
                        value = self._normalize_text(row_map.get(column))
                        if value and len(value) <= 100:
                            labels.append(f"{table}.{column}={value}")
                    fields.extend(labels)
                return fields
            except Exception as e:
                logger.error(f"Fuzzy query failed for table {table} with entity {entity}: {e}")
                return []

        # 并发执行所有表的查询
        tasks = [query_table(table) for table in tables]
        results = await asyncio.gather(*tasks)

        # 汇总结果
        for result in results:
            matched_fields.update(result)

        return sorted(matched_fields)

    async def execute_sql(self, sql: str, authorization: str, intent: str) -> Dict[str, Any]:
        """执行SQL查询（异步版本）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._execute_sql_sync,
            sql,
            authorization,
            intent
        )



# 创建全局SQL服务实例
sql_service = SQLService()

if __name__ == '__main__':
    import json
    import rich
    import asyncio
    dialect="""\
SELECT 
        "用户名称", 
        "项目名称", 
        "排班名称", 
        "班次名称", 
        "值班日期", 
        "值班时间", 
        "打卡时间", 
        "考勤状态", 
        "是否申诉", 
        "是否请假" 
FROM imoc_attendance_all 
WHERE "值班日期" BETWEEN '2026-05-01' AND '2026-05-31' 
        AND "用户名称" LIKE '%黄振国%'
ORDER BY "值班日期";
"""
    settings.TEST_MODE=True
    authorization = "Bearer bc30ffa601636bb9c7c7f194da2107e0eec668024e00d39920583005cc02db5c"
    intent = "attendance"
    result = asyncio.run(sql_service.execute_sql(dialect, authorization, intent))
    rich.print_json(json.dumps(result, ensure_ascii=False))
