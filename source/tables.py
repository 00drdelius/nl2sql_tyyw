from pathlib import Path
import re
from typing import TypedDict

import pandas as pd


attendance_tables_file = Path(__file__).parent / "考勤数据表定义.md"
bpm_tables_file = Path(__file__).parent / "工单流程数据表定义.md"
alert_tables_file = Path(__file__).parent / "告警数据表定义.md"
asset_tables_file = Path(__file__).parent / "资产数据表定义.md"

table_block_matcher = re.compile(
    r"^#\s+\d+\.\s+(?P<table_name>\w+)\s+\[(?P<table_comment>.+?)\]\n(?P<body>.*?)(?=^<br>\s*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
table_name_matcher = re.compile(r"^#\s+\d+\.\s+(?P<table_name>\w+)\s+\[", re.MULTILINE)
markdown_separator_matcher = re.compile(r"^:?-{3,}:?$")


class TableSchemaRecord(TypedDict):
    table_name: str
    table_comment: str
    description: str
    schema_df: pd.DataFrame
    schema_markdown: str


def _extract_markdown_table(block: str) -> str:
    """从单个表的 markdown 区块中提取 schema 表格。"""
    lines = block.splitlines()
    table_lines: list[str] = []
    collecting = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            table_lines.append(stripped)
            collecting = True
            continue

        if collecting:
            break

    if not table_lines:
        raise ValueError("未找到 markdown 表格内容")

    return "\n".join(table_lines)


def markdown_table_to_dataframe(markdown_table: str) -> pd.DataFrame:
    """将 markdown 表格转换为 DataFrame。"""
    rows: list[list[str]] = []

    for raw_line in markdown_table.splitlines():
        stripped = raw_line.strip()
        if not stripped or not stripped.startswith("|"):
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells:
            continue
        if all(markdown_separator_matcher.fullmatch(cell.replace(" ", "")) for cell in cells):
            continue
        rows.append(cells)

    if not rows:
        raise ValueError("markdown 表格为空，无法转换为 DataFrame")

    headers = rows[0]
    data_rows = rows[1:]
    normalized_rows: list[list[str | None]] = []
    header_count = len(headers)
    for row in data_rows:
        if len(row) < header_count:
            row = row + [None] * (header_count - len(row))
        elif len(row) > header_count:
            row = row[:header_count]
        normalized_rows.append(row)

    return pd.DataFrame(normalized_rows, columns=headers)


def parse_markdown_schema_records(markdown_text: str) -> list[TableSchemaRecord]:
    """解析 markdown 文档中的全部表结构，返回带元信息的记录列表。"""
    records: list[TableSchemaRecord] = []

    for match in table_block_matcher.finditer(markdown_text):
        body = match.group("body").strip()
        description_lines = [
            line.lstrip("> ").strip()
            for line in body.splitlines()
            if line.strip().startswith(">")
        ]
        schema_markdown = _extract_markdown_table(body)
        schema_df = markdown_table_to_dataframe(schema_markdown)
        records.append(
            {
                "table_name": match.group("table_name"),
                "table_comment": match.group("table_comment"),
                "description": "\n".join(description_lines),
                "schema_df": schema_df,
                "schema_markdown": schema_markdown,
            }
        )

    return records


def build_schema_dataframe(records: list[TableSchemaRecord]) -> pd.DataFrame:
    """将多张表的 schema DataFrame 合并为一个总表。"""
    merged_frames: list[pd.DataFrame] = []

    for record in records:
        schema_df = record["schema_df"].copy()
        schema_df.insert(0, "table_comment", record["table_comment"])
        schema_df.insert(0, "table_name", record["table_name"])
        merged_frames.append(schema_df)

    if not merged_frames:
        return pd.DataFrame()

    return pd.concat(merged_frames, ignore_index=True)


def build_schema_dataframe_map(records: list[TableSchemaRecord]) -> dict[str, pd.DataFrame]:
    """保留每张表各自的 schema DataFrame。"""
    return {record["table_name"]: record["schema_df"].copy() for record in records}


with attendance_tables_file.open("r", encoding="utf-8") as f:
    ATTDN_RAW = f.read()

with bpm_tables_file.open("r", encoding="utf-8") as f:
    BPM_RAW = f.read()

with alert_tables_file.open("r", encoding="utf-8") as f:
    ALERT_RAW = f.read()

with asset_tables_file.open("r", encoding="utf-8") as f:
    ASSET_RAW = f.read()

ATTDN_TABLENAMES = table_name_matcher.findall(ATTDN_RAW)
BPM_TABLENAMES = table_name_matcher.findall(BPM_RAW)
ALERT_TABLENAMES = table_name_matcher.findall(ALERT_RAW)
ASSET_TABLENAMES = table_name_matcher.findall(ASSET_RAW)

splitter = "<br>"
ATTDN_TABLE_SCHEMAS = [i.strip() for i in ATTDN_RAW.split(splitter)]
BPM_TABLE_SCHEMAS = [i.strip() for i in BPM_RAW.split(splitter)]
ALERT_TABLE_SCHEMAS = [i.strip() for i in ALERT_RAW.split(splitter)]
ASSET_TABLE_SCHEMAS = [i.strip() for i in ASSET_RAW.split(splitter)]

ATTDN_SCHEMA_RECORDS = parse_markdown_schema_records(ATTDN_RAW)
BPM_SCHEMA_RECORDS = parse_markdown_schema_records(BPM_RAW)
ALERT_SCHEMA_RECORDS = parse_markdown_schema_records(ALERT_RAW)
ASSET_SCHEMA_RECORDS = parse_markdown_schema_records(ASSET_RAW)

ATTDN_SCHEMA_DF_MAP = build_schema_dataframe_map(ATTDN_SCHEMA_RECORDS)
BPM_SCHEMA_DF_MAP = build_schema_dataframe_map(BPM_SCHEMA_RECORDS)
ALERT_SCHEMA_DF_MAP = build_schema_dataframe_map(ALERT_SCHEMA_RECORDS)
ASSET_SCHEMA_DF_MAP = build_schema_dataframe_map(ASSET_SCHEMA_RECORDS)

ATTDN_SCHEMA_DF = build_schema_dataframe(ATTDN_SCHEMA_RECORDS)
BPM_SCHEMA_DF = build_schema_dataframe(BPM_SCHEMA_RECORDS)
ALERT_SCHEMA_DF = build_schema_dataframe(ALERT_SCHEMA_RECORDS)
ASSET_SCHEMA_DF = build_schema_dataframe(ASSET_SCHEMA_RECORDS)


# ---------------------------------------------------------------------------
# 正式环境资产表定义（独立 CMDB 实例，文件由同步脚本 --dump-md 对正式 CMDB 生成；
# 文件可选：不存在时保持空值，由下方按环境回退逻辑处理，测试环境无需此文件）
# ---------------------------------------------------------------------------
asset_prod_tables_file = Path(__file__).parent / "资产数据表定义_prod.md"

if asset_prod_tables_file.exists():
    with asset_prod_tables_file.open("r", encoding="utf-8") as f:
        ASSET_PROD_RAW = f.read()
    ASSET_PROD_TABLENAMES = table_name_matcher.findall(ASSET_PROD_RAW)
    ASSET_PROD_TABLE_SCHEMAS = [i.strip() for i in ASSET_PROD_RAW.split(splitter)]
    ASSET_PROD_SCHEMA_RECORDS = parse_markdown_schema_records(ASSET_PROD_RAW)
    ASSET_PROD_SCHEMA_DF_MAP = build_schema_dataframe_map(ASSET_PROD_SCHEMA_RECORDS)
    ASSET_PROD_SCHEMA_DF = build_schema_dataframe(ASSET_PROD_SCHEMA_RECORDS)
else:
    ASSET_PROD_RAW = ""
    ASSET_PROD_TABLENAMES: list[str] = []
    ASSET_PROD_TABLE_SCHEMAS: list[str] = []
    ASSET_PROD_SCHEMA_RECORDS: list[TableSchemaRecord] = []
    ASSET_PROD_SCHEMA_DF_MAP: dict[str, pd.DataFrame] = {}
    ASSET_PROD_SCHEMA_DF = pd.DataFrame()


# 按环境选择生效的资产数据源：
# TEST_MODE=true -> 测试 CMDB（130）数据；TEST_MODE=false -> 正式 CMDB 数据
# （正式表定义缺失时回退测试数据并告警，避免服务启动失败）
from config import settings as _settings  # noqa: E402

if not _settings.TEST_MODE and ASSET_PROD_TABLENAMES:
    ASSET_ACTIVE_RAW = ASSET_PROD_RAW
    ASSET_ACTIVE_TABLENAMES = ASSET_PROD_TABLENAMES
    ASSET_ACTIVE_TABLE_SCHEMAS = ASSET_PROD_TABLE_SCHEMAS
    ASSET_ACTIVE_SCHEMA_RECORDS = ASSET_PROD_SCHEMA_RECORDS
    ASSET_ACTIVE_SCHEMA_DF_MAP = ASSET_PROD_SCHEMA_DF_MAP
    ASSET_ACTIVE_SCHEMA_DF = ASSET_PROD_SCHEMA_DF
else:
    if not _settings.TEST_MODE:
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "正式环境缺少 source/资产数据表定义_prod.md，资产表结构回退使用测试数据"
        )
    ASSET_ACTIVE_RAW = ASSET_RAW
    ASSET_ACTIVE_TABLENAMES = ASSET_TABLENAMES
    ASSET_ACTIVE_TABLE_SCHEMAS = ASSET_TABLE_SCHEMAS
    ASSET_ACTIVE_SCHEMA_RECORDS = ASSET_SCHEMA_RECORDS
    ASSET_ACTIVE_SCHEMA_DF_MAP = ASSET_SCHEMA_DF_MAP
    ASSET_ACTIVE_SCHEMA_DF = ASSET_SCHEMA_DF


if __name__ == '__main__':
    import rich
    rich.print(ATTDN_SCHEMA_RECORDS)
