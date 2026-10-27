"""从 source/*数据表定义*.md 里读出表的中文名、说明和字段，供「数据来源」页展示。

这些 md 是人写的字典，格式不完全统一（表头有「字段名」「字段名称」两种），
解析要宽容：认不出的表就当作没有字典，页面上只展示真实数据。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SOURCE_DIR = Path(__file__).resolve().parent.parent / "source"
_HEADING = re.compile(r"^#\s*(?:\d+\.\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\[([^\]]*)\]", re.M)

_CACHE: dict[str, dict[str, Any]] | None = None


def _split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _parse_fields(section: str) -> list[dict[str, str]]:
    header: list[str] | None = None
    fields: list[dict[str, str]] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = _split_row(line)
        if header is None:
            if "字段名" in cells or "字段名称" in cells:
                header = cells
            continue
        if all(set(cell) <= set("-: ") for cell in cells):
            continue  # |---|:--:| 这种分隔行
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        record = dict(zip(header, cells))
        name = (record.get("字段名") or record.get("字段名称") or "").strip()
        if not name or name.startswith("-"):
            continue
        fields.append({
            "name": name,
            "type": (record.get("数据类型") or record.get("字段类型") or "").strip(),
            "desc": (record.get("备注说明") or record.get("字段说明") or "").strip(),
        })
    return fields


def _parse_file(text: str) -> dict[str, dict[str, Any]]:
    parsed: dict[str, dict[str, Any]] = {}
    headings = list(_HEADING.finditer(text))
    for index, match in enumerate(headings):
        table = match.group(1)
        title = match.group(2).strip()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[match.end():end]

        description_lines = []
        for line in section.splitlines():
            stripped = line.strip()
            if stripped.startswith(">"):
                description_lines.append(stripped.lstrip("> ").strip())
            elif description_lines:
                break

        parsed[table.lower()] = {
            "table": table,
            "title": title,
            "description": " ".join(line for line in description_lines if line),
            "fields": _parse_fields(section),
        }
    return parsed


def _load() -> dict[str, dict[str, Any]]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    catalog: dict[str, dict[str, Any]] = {}
    for md in sorted(_SOURCE_DIR.glob("*数据表定义*.md")):
        try:
            parsed = _parse_file(md.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key, value in parsed.items():
            # 同名表以先解析到的为准（prod 字典排在后面，缺字段时才补）
            catalog.setdefault(key, value)
    _CACHE = catalog
    return catalog


def get_table_meta(table: str) -> dict[str, Any] | None:
    """按表名取字典信息，大小写不敏感（库里是 bpm_archiveddata，字典里写 bpm_archivedData）。"""
    return _load().get((table or "").strip().lower())
