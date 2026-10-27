"""来源表预览页：用户点答案下方的表名，看到这张表的结构和查询当时的真实数据。

页面是后端直接渲染的 HTML，前端不用改，链接写在助手消息正文里即可。
只允许看「本次查询实际用到的表」，数据是出答案时抓的快照，不再回库查询。
"""
from __future__ import annotations

from html import escape
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse

from db.database import DatabaseOperator
from db.dependencies import get_db_operator
from services.table_catalog import get_table_meta

router = APIRouter(prefix="/api", tags=["table"])

_STYLE = """
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;padding:24px;background:#f7f8fa;color:#1f2329}
h1{font-size:20px;margin:0 0 4px}
.sub{color:#646a73;font-size:13px;margin-bottom:20px}
.card{background:#fff;border:1px solid #e5e6eb;border-radius:8px;padding:16px;margin-bottom:16px}
.card h2{font-size:14px;margin:0 0 12px;color:#1f2329}
.scroll{overflow-x:auto}
table{border-collapse:collapse;font-size:13px;white-space:nowrap}
th,td{border:1px solid #e5e6eb;padding:6px 10px;text-align:left}
th{background:#f2f3f5;font-weight:600}
td.desc{white-space:normal;color:#646a73}
.note{color:#8f959e;font-size:12px;margin-top:8px}
.warn{background:#fff7e8;border-color:#ffd591;color:#ad6800}
pre{background:#f2f3f5;padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;margin:0}
"""


def _cell(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value))


def _render_rows(columns: list[str], rows: list[list[Any]]) -> str:
    if not columns:
        return "<p class='note'>没有取到数据。</p>"
    head = "".join(f"<th>{_cell(c)}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_cell(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _render_fields(fields: list[dict[str, str]]) -> str:
    if not fields:
        return "<p class='note'>字典里没有这张表的字段说明。</p>"
    head = "<th>字段名</th><th>类型</th><th>说明</th>"
    body = "".join(
        f"<tr><td>{_cell(f.get('name'))}</td><td>{_cell(f.get('type'))}</td>"
        f"<td class='desc'>{_cell(f.get('desc'))}</td></tr>"
        for f in fields
    )
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


@router.get("/table/preview", response_class=HTMLResponse)
async def table_preview(
    query_id: str,
    table: str,
    db_operator: DatabaseOperator = Depends(get_db_operator),
) -> HTMLResponse:
    record = await db_operator.get_conversation_by_query_id(query_id)
    if record is None:
        raise HTTPException(status_code=404, detail="查询记录不存在")

    payload = record.extra_payload or {}
    previews: dict[str, Any] = payload.get("table_previews") or {}
    preview = previews.get(table)
    if preview is None:
        preview = next((v for k, v in previews.items() if k.lower() == table.lower()), None)
    if preview is None:
        raise HTTPException(status_code=404, detail="这张表不在本次查询范围内")

    meta = get_table_meta(table) or {}
    title = meta.get("title") or table
    description = meta.get("description") or ""

    if preview.get("error"):
        data_html = (
            "<div class='card warn'><h2>数据快照不可用</h2>"
            f"<p class='note'>{_cell(preview['error'])}</p>"
            "<p class='note'>表结构照常展示；真实数据需要重新问一次。</p></div>"
        )
    else:
        row_count = preview.get("row_count")
        total = f"共 {row_count} 行，" if row_count is not None else ""
        data_html = (
            "<div class='card'><h2>真实数据（"
            f"{total}显示前 {len(preview.get('rows') or [])} 行，查询当时的快照）</h2>"
            f"{_render_rows(preview.get('columns') or [], preview.get('rows') or [])}"
            "<p class='note'>这里是库里的原始物理表，不是模型加工后的结果。</p></div>"
        )

    sql_html = ""
    if record.generated_sql:
        sql_html = (
            "<div class='card'><h2>本次实际执行的 SQL</h2>"
            f"<pre>{escape(record.generated_sql)}</pre></div>"
        )

    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(table)} - 数据来源</title><style>{_STYLE}</style></head>
<body>
  <h1>{escape(table)}<span style="font-weight:400;color:#646a73"> · {escape(title)}</span></h1>
  <div class="sub">{escape(description)}<br>
    来源查询：{escape(record.original_query or '')}　|　查询编号：{escape(record.query_id)}</div>
  {data_html}
  <div class="card"><h2>表结构</h2>{_render_fields(meta.get('fields') or [])}</div>
  {sql_html}
</body></html>"""
    return HTMLResponse(content=html)
