from pathlib import Path
import re
from typing import TypedDict

import pandas as pd


attendance_tables_file = Path(__file__).parent / "考勤数据表定义.md"
bpm_tables_file = Path(__file__).parent / "工单流程数据表定义.md"

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

ATTDN_TABLENAMES = table_name_matcher.findall(ATTDN_RAW)
BPM_TABLENAMES = table_name_matcher.findall(BPM_RAW)

splitter = "<br>"
ATTDN_TABLE_SCHEMAS = [i.strip() for i in ATTDN_RAW.split(splitter)]
BPM_TABLE_SCHEMAS = [i.strip() for i in BPM_RAW.split(splitter)]

ATTDN_SCHEMA_RECORDS = parse_markdown_schema_records(ATTDN_RAW)
BPM_SCHEMA_RECORDS = parse_markdown_schema_records(BPM_RAW)

ATTDN_SCHEMA_DF_MAP = build_schema_dataframe_map(ATTDN_SCHEMA_RECORDS)
BPM_SCHEMA_DF_MAP = build_schema_dataframe_map(BPM_SCHEMA_RECORDS)

ATTDN_SCHEMA_DF = build_schema_dataframe(ATTDN_SCHEMA_RECORDS)
BPM_SCHEMA_DF = build_schema_dataframe(BPM_SCHEMA_RECORDS)


if __name__ == '__main__':
    import rich
    rich.print(ATTDN_SCHEMA_RECORDS)