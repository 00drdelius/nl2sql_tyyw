import asyncio
import re
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
        )

        if intent in ("attendance", "attdance"):
            return ATTDN_TABLENAMES, ATTDN_SCHEMA_DF_MAP
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
                
                return {row[userid_index]: row[username_index] for row in rows}
            
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
                    userids = [row[userid_index] for row in rows]
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
    
    async def fuzzy_query(self, entity: str, authorization: str, intent: str) -> List[str]:
        """模糊查询数据库中对应值的字段名"""
        tables, _ = self._get_schema_resources(intent)
        entity_lower = self._normalize_text(entity).lower()
        if not entity_lower:
            return []

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

                    fields.extend(
                        self._build_hit_labels(
                            table=table,
                            normal_hits=normal_hits,
                            xml_hits=xml_hits,
                            xml_column=table_meta.xml_column,
                            has_raw_xml_match=has_raw_xml_match,
                        )
                    )
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
