from __future__ import annotations
import asyncio
import re
import time
from datetime import datetime
from typing import Any, AsyncGenerator, Iterable
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from api.schemas.query import (
    ChatMessage,
    ChunkResponse,
    ConversationQueryRequest,
    DeleteSessionResponse,
    HistoryRecordResponse,
    QueryRequest,
    QueryResponse,
    QueryResult,
    SessionSummaryResponse,
)
from db.database import DatabaseOperator
from db.dependencies import get_db_operator, get_db_session
from config import settings
from services.llm_service import llm_service
from services.milvus_service import milvus_service
from services.sql_service import sql_service
from services.table_catalog import get_table_meta
from prompts import (
    ATTENDANCE_TABLE_DESCRIPTIONS, BPM_TABLE_DESCRIPTIONS,
    ALERT_TABLE_DESCRIPTIONS, ALERT_NOTE,
    ASSET_TABLE_DESCRIPTIONS, ASSET_NOTE, ASSET_QUERY_SYS, FEEDBACK_ASSET_SYS,
    FEEDBACK_SYS, GENERATE_SYS_V2,
    BPM_NOTE, ATTENDANCE_NOTE
)
from logg import logger

router = APIRouter(prefix="/api", tags=["query"])

STATUS_PROCESSING = "processing"
STATUS_SEMANTIC_REPLY = "semantic_reply"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
# 用户没回答口径问题、直接问了别的问题时，上一轮挂起的澄清按放弃处理
STATUS_ABANDONED = "abandoned"

# 意图标识 -> 展示用中文名（思考链路里给用户看的是中文）
INTENT_LABELS = {
    "attendance": "考勤",
    "attdance": "考勤",
    "alert": "告警",
    "bpm": "工单",
    "asset": "资产",
}


def _extract_sql_tables(sql: str) -> list[str]:
    """从 SQL 里提取 FROM / JOIN 引用的表名，用于展示"查了哪张表"。"""
    tables: list[str] = []
    for raw in re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w.]*)", sql or "", flags=re.IGNORECASE):
        name = raw.strip("`\"[]")
        if not name or name.lower() in {"select", "lateral"} or name in tables:
            continue
        tables.append(name)
    return tables


def _safe_table_name(name: str) -> str | None:
    """只允许普通标识符，避免把 SQL 片段拼进取样语句。"""
    name = (name or "").strip("`\"[] ")
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else None


async def _collect_table_previews(
    tables: list[str],
    intent: str,
    authorization: str,
) -> dict[str, dict[str, Any]]:
    """为答案里涉及的每张物理表取一份真实数据快照。

    取数发生在出答案的时候（此时还拿着用户的库权限），预览页只读这份快照，
    所以点开链接不需要再带 token，也不会因为库权限过期而打不开。
    """
    targets = [name for name in (_safe_table_name(t) for t in tables) if name][:3]
    if not targets:
        return {}

    async def fetch(table: str) -> tuple[str, dict[str, Any]]:
        limit = max(1, min(settings.TABLE_PREVIEW_ROWS, 100))
        # 取样和总数并发跑：总数失败不影响取样，超时就只展示结构+样例
        data_task = asyncio.create_task(
            sql_service.execute_sql(f"SELECT * FROM {table} LIMIT {limit}", authorization, intent)
        )
        count_task = asyncio.create_task(
            sql_service.execute_sql(f"SELECT COUNT(1) AS CNT FROM {table}", authorization, intent)
        )

        try:
            data = await asyncio.wait_for(data_task, timeout=settings.TABLE_PREVIEW_TIMEOUT)
        except Exception as exc:
            count_task.cancel()
            logger.warning(f"来源表取样失败 {table}: {exc}")
            return table, {"error": str(exc)[:300]}

        total = None
        try:
            counted = await asyncio.wait_for(count_task, timeout=settings.TABLE_PREVIEW_TIMEOUT)
            rows = counted.get("rows") or []
            if rows and rows[0]:
                total = rows[0][0]
        except Exception as exc:
            logger.warning(f"来源表行数统计失败 {table}: {exc}")

        # 单格截断：BPM 的 xmldata 这类字段单行就可能几 MB，整段存下来会把记录撑爆
        columns = (data.get("columns") or [])[:40]
        rows = [
            [
                (str(value)[:300] + "…") if value is not None and len(str(value)) > 300 else value
                for value in row[:40]
            ]
            for row in (data.get("rows") or [])[:limit]
        ]
        return table, {"columns": columns, "rows": rows, "row_count": total}

    results = await asyncio.gather(*(fetch(table) for table in targets))
    return dict(results)


def _build_source_section(query_id: str, tables: list[str]) -> str:
    """助手正文里追加的「数据来源」，链接指向库里那张表的结构和真实数据。"""
    if not tables:
        return ""
    base = (settings.TABLE_PREVIEW_BASE_URL or "").rstrip("/")
    if not base:
        return ""

    lines = ["数据来源（点击查看库里的这张表）："]
    for table in tables:
        meta = get_table_meta(table) or {}
        label = f"{table}（{meta['title']}）" if meta.get("title") else table
        url = f"{base}/api/table/preview?query_id={quote(query_id)}&table={quote(table)}"
        lines.append(f"- [{label}]({url})")
    return "\n".join(lines)


def _extract_table_names_from_descs(table_descs: str) -> list[str]:
    """从 Milvus 检索回来的表描述里提取表名（描述里的格式是"表名：xxx"）。"""
    names: list[str] = []
    for raw in re.findall(r"表名[:：]\s*([^\s\n]+)", table_descs or ""):
        name = raw.strip("`\"")
        if name and name not in names:
            names.append(name)
    return names


def _trace_event(query_id: str, step: str, **fields: Any) -> str:
    """构造一条思考链路事件，前端据此实时展示处理进度。"""
    resp = ChunkResponse(id=query_id, type="trace_step", content={"step": step, **fields})
    return f"data: {resp.model_dump_json()}\n\n"


async def generate_and_query_db(
    query_id: str,
    authorization: str,
    intent: str,
    messages: Iterable[dict[str, str]],
    table_descs: str,
    note: str,
    original_query: str = "",
    trace: dict[str, Any] | None = None,
) -> AsyncGenerator[str | tuple[str, dict[str, Any], list[dict[str, str]]], None]:
    trace = trace if trace is not None else {}
    datetime_today = datetime.now().strftime("%Y-%m-%d, %A")
    gen_sys = GENERATE_SYS_V2.format(
        datetime_today=datetime_today, table_descs=table_descs, note=note)
    working_messages = llm_service.prepare_messages(messages)
    # 重试时最后一条用户消息会被反馈内容覆盖，这里先留存，用于人员名单类SQL的校验；
    # 优先用用户原话，避免润色阶段把"有哪些人"改写成不含人员字样的描述
    user_question = original_query or llm_service.get_latest_user_message(working_messages)

    MAX_RETRIES = 3
    query_result = None
    sql_content = None

    flag_resp = ChunkResponse(id=query_id, type='flag_to_reply', content='[开始生成SQL]')
    yield f"data: {flag_resp.model_dump_json()}\n\n"

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            logger.info(f"============== 第 {attempt} 次尝试修正 SQL ==============")

        # 调用大模型生成SQL（流式），首次快速，重试时开思考
        sql_response = ""
        extracted_sql = ""
        async for chunk in llm_service.generate_sql(working_messages, sys_prompt=gen_sys, enable_thinking=(attempt > 0)):
            if isinstance(chunk, tuple) and chunk[0] is None:
                # 结束标记，提取的SQL
                extracted_sql = chunk[1]
            else:
                sql_response += chunk
                if attempt == 0:
                    chunk_resp = ChunkResponse(id=query_id, type='stream_reply', content=chunk)
                else:
                    chunk_resp = ChunkResponse(id=query_id, type='retry_reply', content=chunk)

                yield f"data: {chunk_resp.model_dump_json()}\n\n"

        sql_content = extracted_sql

        # SQL预校验：修正已知的常见字段名错误，避免不必要的重试
        # 大小写修正
        sql_content = re.sub(r'"主机ID"', '"主机id"', sql_content)
        sql_content = re.sub(r'"事件ID"', '"事件id"', sql_content)
        sql_content = re.sub(r'"触发器ID"', '"触发器id"', sql_content)
        # 关键字粘合修正
        sql_content = re.sub(r'(\S)(FROM\s)', r'\1 \2', sql_content)
        sql_content = re.sub(r'(\S)(LEFT JOIN\s)', r'\1 \2', sql_content)
        sql_content = re.sub(r'(\S)(WHERE\s)', r'\1 \2', sql_content)
        # 表主键名修正：LLM常编造不存在的列名
        sql_content = re.sub(r'(\b\w+\.)project_id', r'\1id', sql_content)
        sql_content = re.sub(r'(\b\w+\.)team_id', r'\1id', sql_content)
        sql_content = re.sub(r'ON\s+\w+\.id\s*=\s*\w+\.id\s+', lambda m: m.group(), sql_content)  # no-op, just checking
        # 修正 ON d.userid = u.id → ON d.userid = u.userid
        sql_content = re.sub(r'ON\s+d\.userid\s*=\s*u\.id\b', r'ON d.userid = u.userid', sql_content, flags=re.IGNORECASE)

        working_messages.append({"role": "assistant", "content": sql_response})

        # 记录本次尝试：思考链路里要能回看每一次生成的 SQL、涉及的表和执行结果
        attempt_entry: dict[str, Any] = {
            "attempt": attempt + 1,
            "sql": sql_content,
            "tables": _extract_sql_tables(sql_content),
            "status": "running",
        }
        trace.setdefault("sql_attempts", []).append(attempt_entry)
        yield _trace_event(
            query_id, "sql_generated",
            attempt=attempt + 1, sql=sql_content, tables=attempt_entry["tables"],
        )

        try:
            # 问具体人员时，SQL必须关联人员表，否则结果里没有姓名（LLM偶尔只查排班表）
            if intent in ("attendance", "attdance"):
                person_markers = ("谁", "哪些人", "人员", "名单", "姓名")
                if (
                    any(marker in user_question for marker in person_markers)
                    and re.search(r"\bimoc_class_duty_user\b", sql_content, re.IGNORECASE)
                    and not re.search(r"\bimoc_class_user\b", sql_content, re.IGNORECASE)
                ):
                    raise ValueError(
                        "SQL执行错误: 用户问的是具体人员，但SQL中没有人员姓名。"
                        "请优先改用 imoc_attendance_all 视图（该视图已包含\"用户名称\"列，"
                        "直接查询即可）；若必须用底表，则必须 INNER JOIN imoc_class_user ON "
                        "imoc_class_duty_user.userid = imoc_class_user.userid，"
                        "并输出 imoc_class_user.name 作为人员姓名。"
                    )

                # "没考勤/没打卡"这类口语只对应"当天没有打卡"，不等于某一个状态；
                # 模型偏爱写 考勤状态 = '未到岗'，该状态当天常常 0 行，导致结果为空
                vague_no_checkin = ("没考勤", "未考勤", "没打卡", "未打卡", "没有考勤", "没签到")
                if any(marker in user_question for marker in vague_no_checkin) and re.search(
                    r"""(?:考勤状态|\bstatus\b)\s*=\s*['"]?(?:未到岗|未签到)""",
                    sql_content,
                    re.IGNORECASE,
                ):
                    raise ValueError(
                        "SQL执行错误: 用户问的是“没考勤/没打卡”，口语指当天没有打卡记录，"
                        "不等于某一个考勤状态，只写 考勤状态 = '未到岗' 常常返回空。"
                        "请改为 考勤状态 IN ('缺勤','未到岗','未签到')，"
                        "或补充 打卡时间 为空的判断。"
                    )
            query_result = await sql_service.execute_sql(sql_content, authorization, intent)
            logger.info(f"查询成功: 返回 {len(query_result['columns'])} 列; {query_result['row_count']} 行")

            attempt_entry["status"] = "success"
            attempt_entry["row_count"] = query_result.get("row_count", 0)
            attempt_entry["columns"] = query_result.get("columns", [])
            yield _trace_event(
                query_id, "sql_success",
                attempt=attempt + 1,
                row_count=attempt_entry["row_count"],
                tables=attempt_entry["tables"],
            )

            query_resp = ChunkResponse(id=query_id, type='query_success', content='[SQL查询成功]')
            yield f"data: {query_resp.model_dump_json()}\n\n"
            break
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"SQL执行报错 (ValueError): {error_msg}")

            attempt_entry["status"] = "error"
            attempt_entry["error"] = error_msg
            yield _trace_event(
                query_id, "sql_error",
                attempt=attempt + 1, error=error_msg,
            )

            if attempt < MAX_RETRIES:
                feedback_prompt = FEEDBACK_SYS.format(error_msg=error_msg)
                working_messages.append({"role": "user", "content": feedback_prompt})
                logger.info("已将报错信息反馈给大模型，准备重试...")
            else:
                logger.warning("已达到最大重试次数，无法修正SQL。")
                raise ValueError("[SQL执行报错] 已达到最大重试次数，无法修正SQL。")
    yield sql_content, query_result, working_messages


def _extract_json_object(text: str) -> dict:
    """从 LLM 输出中容错提取 JSON 对象（容忍 markdown 代码块与前后文字）。"""
    import json as jsonlib
    import re as regex

    text = (text or "").strip()
    # 1. 直接解析
    try:
        parsed = jsonlib.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except ValueError:
        pass
    # 2. 剥离 ```json 代码块围栏
    fenced = regex.search(r"```(?:json)?\s*(.*?)```", text, regex.DOTALL)
    if fenced:
        try:
            parsed = jsonlib.loads(fenced.group(1).strip())
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass
    # 3. 花括号配平扫描
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = jsonlib.loads(text[start:i + 1])
                        if isinstance(parsed, dict):
                            return parsed
                    except ValueError:
                        break
    raise ValueError(f"无法从输出中解析 JSON 对象: {text[:200]!r}")


async def generate_and_query_asset(
    query_id: str,
    authorization: str,
    messages: Iterable[dict[str, str]],
    table_descs: str,
    note: str,
    trace: dict[str, Any] | None = None,
) -> AsyncGenerator[str | tuple[str, dict[str, Any], list[dict[str, str]]], None]:
    """资产意图：LLM 生成 CMDB 查询参数（JSON） -> 直查 CMDB API 执行，带重试修正。"""
    from services.cmdb_service import cmdb_service

    trace = trace if trace is not None else {}

    datetime_today = datetime.now().strftime("%Y-%m-%d, %A")
    gen_sys = ASSET_QUERY_SYS.format(
        datetime_today=datetime_today, table_descs=table_descs, note=note)
    working_messages = llm_service.prepare_messages(messages)

    MAX_RETRIES = 3
    query_result = None
    spec_text = None

    flag_resp = ChunkResponse(id=query_id, type='flag_to_reply', content='[开始生成查询参数]')
    yield f"data: {flag_resp.model_dump_json()}\n\n"

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            logger.info(f"============== 第 {attempt} 次尝试修正查询参数 ==============")

        # 调用大模型生成查询参数（流式），首次快速，重试时开思考
        response_text = ""
        extracted_params = ""
        async for chunk in llm_service.generate_asset_query(
            working_messages, sys_prompt=gen_sys, enable_thinking=(attempt > 0)
        ):
            if isinstance(chunk, tuple) and chunk[0] is None:
                extracted_params = chunk[1]
            else:
                response_text += chunk
                chunk_resp = ChunkResponse(
                    id=query_id,
                    type='stream_reply' if attempt == 0 else 'retry_reply',
                    content=chunk,
                )
                yield f"data: {chunk_resp.model_dump_json()}\n\n"

        spec_text = extracted_params
        working_messages.append({"role": "assistant", "content": response_text})

        attempt_entry: dict[str, Any] = {
            "attempt": attempt + 1,
            "params": spec_text,
            "status": "running",
        }
        trace.setdefault("cmdb_attempts", []).append(attempt_entry)
        yield _trace_event(
            query_id, "cmdb_generated",
            attempt=attempt + 1, params=spec_text,
        )

        try:
            spec = _extract_json_object(spec_text)
            query_result = await cmdb_service.execute_query(spec, authorization)
            logger.info(f"资产查询成功: 返回 {len(query_result['columns'])} 列; {query_result['row_count']} 行")

            attempt_entry["status"] = "success"
            attempt_entry["row_count"] = query_result.get("row_count", 0)
            attempt_entry["columns"] = query_result.get("columns", [])
            yield _trace_event(
                query_id, "cmdb_success",
                attempt=attempt + 1, row_count=attempt_entry["row_count"],
            )

            query_resp = ChunkResponse(id=query_id, type='query_success', content='[资产查询成功]')
            yield f"data: {query_resp.model_dump_json()}\n\n"
            break
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"资产查询报错 (ValueError): {error_msg}")

            attempt_entry["status"] = "error"
            attempt_entry["error"] = error_msg
            yield _trace_event(
                query_id, "cmdb_error",
                attempt=attempt + 1, error=error_msg,
            )

            if attempt < MAX_RETRIES:
                feedback_prompt = FEEDBACK_ASSET_SYS.format(error_msg=error_msg)
                working_messages.append({"role": "user", "content": feedback_prompt})
                logger.info("已将报错信息反馈给大模型，准备重试...")
            else:
                logger.warning("已达到最大重试次数，无法修正查询参数。")
                raise ValueError("[资产查询报错] 已达到最大重试次数，无法修正查询参数。")

    yield spec_text, query_result, working_messages
def _normalize_messages(messages: Iterable[ChatMessage | dict[str, str]]) -> list[dict[str, str]]:
    normalized = llm_service.prepare_messages(messages)
    if not normalized:
        raise ValueError("对话记录不能为空")
    if normalized[-1]["role"] != "user":
        raise ValueError("最后一条对话必须是用户消息")
    return normalized


def _format_clarification_text(clarification: dict[str, Any]) -> str:
    """把澄清问题和选项拼成前端能直接渲染的正文。

    格式必须和 NER 实体消歧的提问一致（"(A) xxx（说明）" 一行一个选项），
    前端会把这种行渲染成可点选的卡片；只发一句问题而不带选项，用户没法选。
    """
    option_lines = []
    for index, option in enumerate(clarification.get("options", [])):
        letter = chr(ord("A") + index)
        description = (option.get("description") or "").strip()
        suffix = f"（{description}）" if description else ""
        option_lines.append(f"({letter}) {option.get('label', '')}{suffix}")
    return f"{clarification['question']}\n\n" + "\n".join(option_lines)


def _resolve_clarification_choice(
    user_reply: str, options: list[dict[str, Any]]
) -> tuple[str, bool]:
    """把用户的选择（可能是 "A"、"(A) 按流程总耗时（说明）"、或直接复述选项）还原成口径描述。

    第二个返回值表示是否命中某个选项：没命中说明用户可能压根没在回答，而是问了别的问题。
    """
    raw = (user_reply or "").strip()

    # 只回了一个字母：按序号取
    letter = re.fullmatch(r"[（(]?\s*([A-Za-z])\s*[)）.、:：]?", raw)
    if letter:
        index = ord(letter.group(1).upper()) - ord("A")
        if 0 <= index < len(options):
            option = options[index]
            return option.get("value") or option.get("label") or raw, True

    # 去掉前端带回来的 "(A)" / "A." / "A、" 前缀
    cleaned = re.sub(r"^[（(]?\s*[A-Za-z]\s*[)）.、:：]\s*", "", raw).strip()

    for option in options:
        label = (option.get("label") or "").strip()
        value = (option.get("value") or "").strip()
        if not label:
            continue
        if raw in (label, value) or cleaned in (label, value) or cleaned.startswith(label):
            return value or label, True

    # 没对上任何选项，就用用户原话，交给模型自己理解
    return cleaned or raw, False


# 模型判定失败时用的兜底规则：这句话本身像不像一个新问题
_NEW_QUERY_MARKERS = (
    "多少", "几张", "几个", "几条", "哪些", "哪几", "有谁", "列出", "查询",
    "统计一下", "查一下", "看一下", "帮我", "明细", "详情", "最近", "近一周",
)


def _looks_like_new_query(text: str) -> bool:
    return any(marker in text for marker in _NEW_QUERY_MARKERS)


async def _pause_for_clarification(
    *,
    query_id: str,
    user_id: str,
    session_id: str,
    intent: str,
    original_query: str,
    parsed_query: str,
    clarification: dict[str, Any],
    messages: list[dict[str, str]],
    db_session: AsyncSession,
    db_operator: DatabaseOperator,
    existing_record: bool,
) -> None:
    """问题口径有歧义时先挂起本次查询，等用户选完方向再继续。"""
    pending_clarification = {
        "question": clarification["question"],
        "options": clarification["options"],
        "intent": intent,
        "original_query": original_query,
        "parsed_query": parsed_query,
    }
    persisted_messages = [
        *messages,
        {"role": "assistant", "content": _format_clarification_text(clarification)},
    ]
    payload = {"pending_clarification": pending_clarification}

    if existing_record:
        await db_operator.update_conversation(
            query_id=query_id,
            session=db_session,
            user_id=user_id,
            intent=intent,
            original_query=original_query,
            parsed_query=parsed_query,
            messages=persisted_messages,
            extra_payload=payload,
            status=STATUS_SEMANTIC_REPLY,
        )
    else:
        await db_operator.save_conversation(
            session=db_session,
            query_id=query_id,
            user_id=user_id,
            session_id=session_id,
            intent=intent,
            original_query=original_query,
            parsed_query=parsed_query,
            messages=persisted_messages,
            extra_payload=payload,
            status=STATUS_SEMANTIC_REPLY,
        )


async def _finalize_query(
    *,
    query_id: str,
    user_id: str,
    session_id: str,
    messages: list[dict[str, str]],
    original_query: str,
    parsed_query: str,
    intent: str,
    authorization: str,
    db_session: AsyncSession,
    db_operator: DatabaseOperator,
    existing_record: bool,
    entities: list[str] | None = None,
    trace: dict[str, Any] | None = None,
    started_at: float | None = None,
    skip_ambiguity: bool = False,
) -> AsyncGenerator[str, None]:
    trace = trace if trace is not None else {}

    def _strip_table_descs(descs: list[str]) -> str:
        """精简表描述：去掉字段的长描述，只保留表名和字段名"""
        stripped = []
        for desc in descs:
            lines = desc.split('\n')
            new_lines = []
            for line in lines:
                if line.startswith('表名：') or line.startswith('表字段：'):
                    new_lines.append(line)
                elif ':' in line and not line.startswith('表'):
                    # 字段行：只保留字段名
                    new_lines.append(line.split(':')[0].strip())
            # 把字段名用逗号连接成一行
            fields = [l for l in new_lines if '：' not in l and l]
            header = [l for l in new_lines if '：' in l]
            stripped.append('\n'.join(header + [', '.join(fields)]))
        return '\n\n'.join(stripped)

    if intent == "alert":
        note = ALERT_NOTE
        table_descriptions = ALERT_TABLE_DESCRIPTIONS
    elif intent == "asset":
        note = ASSET_NOTE
        table_descriptions = ASSET_TABLE_DESCRIPTIONS
    elif intent == "bpm":
        note = BPM_NOTE
        table_descriptions = BPM_TABLE_DESCRIPTIONS
    else:
        note = ATTENDANCE_NOTE
        table_descriptions = ATTENDANCE_TABLE_DESCRIPTIONS

    parsed_messages = llm_service.replace_latest_user_message(messages, parsed_query)
    light_table_descs = _strip_table_descs(table_descriptions)
    polished_query = await llm_service.polish_query(
        parsed_messages, light_table_descs, intent=intent, entities=entities
    )
    logger.info(f"润色后的查询: {polished_query}")

    trace.update({
        "intent": intent,
        "intent_label": INTENT_LABELS.get(intent, intent),
        "original_query": original_query,
        "parsed_query": parsed_query,
        "polished_query": polished_query,
    })

    polish_resp = ChunkResponse(id=query_id, type="polish_query", content=f"[润色查询] {polished_query}")
    yield f"data: {polish_resp.model_dump_json()}\n\n"

    # 口径歧义检测：问题有多个合理解释时，先弹卡片让用户选方向，
    # 而不是让模型自己猜一个口径去查（猜错了数据看着像真的，比查不出来更糟）。
    if settings.ENABLE_AMBIGUITY_CHECK and not skip_ambiguity:
        try:
            # 这里必须给完整表结构（含字段说明）：精简版只留字段名，
            # BPM 这类 markdown 表格定义会被抽成空串，模型看不到
            # 「总耗时字段」和「创建/结束时间字段」同时存在，就不会提示歧义。
            clarification = await llm_service.check_ambiguity(
                parsed_messages,
                intent,
                "\n\n".join(table_descriptions)[:6000],
            )
        except Exception as exc:  # 检测本身失败不能影响正常问数
            logger.warning(f"口径歧义检测失败，按无疑义继续查询: {exc}")
            clarification = None

        if clarification:
            logger.info(f"检测到口径歧义，等待用户选择: {clarification['question']}")
            trace["clarification"] = clarification
            await _pause_for_clarification(
                query_id=query_id,
                user_id=user_id,
                session_id=session_id,
                intent=intent,
                original_query=original_query,
                parsed_query=parsed_query,
                clarification=clarification,
                messages=messages,
                db_session=db_session,
                db_operator=db_operator,
                existing_record=existing_record,
            )
            # 必须用 semantic_reply 把正文推给前端（NER 消歧就是这么做的）：
            # 前端只认这个事件来渲染助手回答，没有它就一直停在「查询润色」转圈。
            clarification_text = _format_clarification_text(clarification)
            reply_resp = ChunkResponse(
                id=query_id, type="semantic_reply", content=clarification_text
            )
            yield f"data: {reply_resp.model_dump_json()}\n\n"

            # 选项已经写进助手消息正文（刷新后也能看到），这里默认不再推任何额外事件：
            # 老前端没有 semantic_waiting 分支、也不认识 clarification_required 这个 step，
            # 收到未知事件会在解析处中断，导致读不到 [DONE]、页面一直转圈。
            if settings.CLARIFICATION_SSE_EVENT:
                yield _trace_event(
                    query_id, "clarification_required",
                    question=clarification["question"],
                    options=clarification["options"],
                )
                waiting_resp = ChunkResponse(
                    id=query_id,
                    type="semantic_waiting",
                    content={
                        "kind": "clarification",
                        "question": clarification["question"],
                        "options": clarification["options"],
                    },
                )
                yield f"data: {waiting_resp.model_dump_json()}\n\n"
            return

    query_embedding = await llm_service.generate_embedding(polished_query)
    logger.info("完成生成查询向量")

    # 资产意图在正式/测试环境使用各自的 Milvus 集合（asset_prod / asset）
    collection = intent
    if intent == "asset" and not settings.TEST_MODE:
        collection = "asset_prod"
    table_descs = await milvus_service.search_table_schema(query_embedding, collection)
    retrieved_tables = _extract_table_names_from_descs(table_descs)
    trace["retrieved_tables"] = retrieved_tables
    yield _trace_event(query_id, "tables_retrieved", tables=retrieved_tables)

    polished_messages = llm_service.replace_latest_user_message(messages, polished_query)
    if intent == "asset":
        # 资产走 CMDB 直查（LLM 生成查询参数，不经 SQL 网关）
        agen = generate_and_query_asset(
            query_id=query_id,
            authorization=authorization,
            messages=polished_messages,
            table_descs=table_descs,
            note=note,
            trace=trace,
        )
    else:
        agen = generate_and_query_db(
            query_id=query_id,
            authorization=authorization,
            intent=intent,
            messages=polished_messages,
            table_descs=table_descs,
            note=note,
            original_query=original_query,
            trace=trace,
        )
    async for result in agen:
        if isinstance(result, str):
            yield result
        elif isinstance(result, tuple):
            sql_content, query_result, sql_generation_messages = result

    # 告警结果后处理
    if intent == "alert" and query_result and query_result.get("columns") and query_result.get("rows"):
        import re
        columns = query_result["columns"]

        # 1. 清洗设备名称：提取纯IP
        device_col_idx = columns.index("设备名称") if "设备名称" in columns else None
        if device_col_idx is not None:
            for row in query_result["rows"]:
                raw_name = row[device_col_idx]
                if raw_name and isinstance(raw_name, str):
                    match = re.search(r'\d+\.\d+\.\d+\.\d+', raw_name)
                    if match:
                        row[device_col_idx] = match.group()

        # 2. 清洗时间字段：去掉时区后缀 "+08"
        for time_col in ["告警时间", "恢复时间"]:
            col_idx = columns.index(time_col) if time_col in columns else None
            if col_idx is not None:
                for row in query_result["rows"]:
                    val = row[col_idx]
                    if val and isinstance(val, str):
                        row[col_idx] = re.sub(r'\+08$', '', val).strip()

        # 3. 清理空/无效的恢复时间
        restore_col_idx = columns.index("恢复时间") if "恢复时间" in columns else None
        if restore_col_idx is not None:
            for row in query_result["rows"]:
                val = row[restore_col_idx]
                if val is None or (isinstance(val, str) and val.strip() in ('', '1970-01-01 08:00:00')):
                    row[restore_col_idx] = ""

    data_analysis = llm_service.generate_data_analysis(query_result)

    # 补齐思考链路：最终 SQL、实际查询的表、返回行列数（前端在答案下方展示）
    trace["final_sql"] = sql_content
    trace["tables"] = [] if intent == "asset" else _extract_sql_tables(sql_content)

    # 来源表快照：出答案时顺手把涉及的物理表取一份数据，供用户点开核对
    table_previews: dict[str, Any] = {}
    if settings.ENABLE_TABLE_PREVIEW and trace["tables"]:
        table_previews = await _collect_table_previews(trace["tables"], intent, authorization)
        trace["table_previews"] = {
            table: {
                "row_count": preview.get("row_count"),
                "available": "error" not in preview,
            }
            for table, preview in table_previews.items()
        }
        source_section = _build_source_section(query_id, trace["tables"])
        if source_section:
            data_analysis = f"{data_analysis}\n\n{source_section}"
    trace["columns"] = query_result.get("columns", []) if query_result else []
    trace["row_count"] = query_result.get("row_count", 0) if query_result else 0
    if started_at is not None:
        trace["elapsed_ms"] = int((time.perf_counter() - started_at) * 1000)

    final_response_payload = QueryResponse(
        original_query=original_query,
        polished_query=polished_query,
        sql_dialect=sql_content,
        result=QueryResult(**query_result),
        natural_answer=None,
        data_analysis=data_analysis,
        trace=trace,
    )
    assistant_message = "\n\n".join(
        [
            "查询已完成。",
            # "```sql\n" + sql_content + "\n```",
            data_analysis,
        ]
    )
    persisted_messages = [*messages, {"role": "assistant", "content": assistant_message}]
    payload = {
        "table_desc": table_descs,
        "data_analysis": data_analysis,
        "sql_generation_messages": sql_generation_messages,
        "final_response": final_response_payload.model_dump(),
        "result_summary": {
            "columns": query_result.get("columns", []),
            "row_count": query_result.get("row_count", 0),
        },
        "pending_semantic_question": None,
        "semantic_resume_messages": None,
        "semantic_entities": None,
        "pending_clarification": None,
        # 来源表快照：/api/table/preview 只读这份数据，不再回库查询
        "table_previews": table_previews,
    }

    if existing_record:
        await db_operator.update_conversation(
            query_id=query_id,
            session=db_session,
            user_id=user_id,
            intent=intent,
            original_query=original_query,
            parsed_query=parsed_query,
            polished_query=polished_query,
            generated_sql=sql_content,
            messages=persisted_messages,
            extra_payload=payload,
            status=STATUS_COMPLETED,
        )
    else:
        await db_operator.save_conversation(
            session=db_session,
            query_id=query_id,
            user_id=user_id,
            session_id=session_id,
            intent=intent,
            original_query=original_query,
            parsed_query=parsed_query,
            polished_query=polished_query,
            generated_sql=sql_content,
            messages=persisted_messages,
            extra_payload=payload,
            status=STATUS_COMPLETED,
        )

    final_resp = ChunkResponse(
        id=query_id,
        type="final_result",
        content=final_response_payload,
    )
    yield f"data: {final_resp.model_dump_json()}\n\n"


def _serialize_session_summary(record) -> SessionSummaryResponse:
    return SessionSummaryResponse(
        session_id=record.session_id,
        query_id=record.query_id,
        user_id=record.user_id,
        intent=record.intent,
        status=record.extra_payload.get("status"),
        original_query=record.original_query,
        updated_at=record.updated_at,
        created_at=record.created_at,
    )


def _serialize_history_record(record) -> HistoryRecordResponse:
    messages = [ChatMessage.model_validate(message) for message in record.messages]
    return HistoryRecordResponse(
        query_id=record.query_id,
        session_id=record.session_id,
        user_id=record.user_id,
        intent=record.intent,
        status=record.extra_payload.get("status"),
        original_query=record.original_query,
        parsed_query=record.parsed_query,
        polished_query=record.polished_query,
        generated_sql=record.generated_sql,
        messages=messages,
        extra_payload=record.extra_payload,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


async def generate_stream(
    *,
    messages: list[dict[str, str]],
    user_id: str,
    authorization: str,
    session_id: str,
    db_session: AsyncSession,
    db_operator: DatabaseOperator,
) -> AsyncGenerator[str, None]:
    """生成流式响应的异步生成器"""
    query_id = str(uuid4())
    started_at = time.perf_counter()
    # 思考链路：贯穿整个流程收集，最后随 final_result 一起返回并入库
    trace: dict[str, Any] = {}

    try:
        normalized_messages = _normalize_messages(messages)
        pending_conversation = await db_operator.get_latest_conversation_by_status(
            user_id=user_id,
            session_id=session_id,
            status=STATUS_SEMANTIC_REPLY,
        )
        if pending_conversation is not None:
            query_id = pending_conversation.query_id
            user_reply = llm_service.get_latest_user_message(normalized_messages)
            original_query = pending_conversation.original_query
            intent = pending_conversation.intent
            if intent is None:
                raise ValueError("待恢复会话缺少 intent，无法继续语义解析")

            pending_clarification = pending_conversation.extra_payload.get("pending_clarification")
            if isinstance(pending_clarification, dict) and pending_clarification.get("options"):
                options = pending_clarification.get("options", [])
                choice_text, matched = _resolve_clarification_choice(user_reply, options)

                # 用户没点选项、而是直接问了别的问题时，绝不能把新问题当成口径塞进上一轮，
                # 否则会按老问题算出一个看着像答案的错误数字（"超三天工单"就踩过这个坑）。
                if not matched:
                    try:
                        verdict = await llm_service.is_clarification_answer(
                            pending_clarification.get("question", ""), options, user_reply
                        )
                    except Exception as exc:
                        logger.warning(f"澄清回答判定失败，按规则兜底: {exc}")
                        verdict = None

                    if verdict is False or (verdict is None and _looks_like_new_query(user_reply)):
                        logger.info(f"用户提出新问题，放弃上一轮口径澄清：{user_reply}")
                        await db_operator.update_conversation(
                            query_id=query_id,
                            session=db_session,
                            user_id=user_id,
                            extra_payload={"pending_clarification": None},
                            status=STATUS_ABANDONED,
                        )
                        # 新问题要落一条新记录，不能复用挂起记录的 query_id
                        query_id = str(uuid4())
                        pending_conversation = None

            if (
                pending_conversation is not None
                and isinstance(pending_clarification, dict)
                and pending_clarification.get("options")
            ):
                # 上一轮因为口径有歧义挂起了，这次用户消息就是用户选的方向
                clarification_intent = pending_clarification.get("intent") or intent
                base_query = (
                    pending_clarification.get("parsed_query")
                    or pending_conversation.parsed_query
                    or original_query
                )
                choice_text, _ = _resolve_clarification_choice(user_reply, options)
                parsed_query = f"{base_query}\n\n用户已明确口径：{choice_text}"
                logger.info(f"澄清恢复，用户选择：{choice_text} → 解析问题：{parsed_query}")

                visible_messages = [
                    *llm_service.prepare_messages(pending_conversation.messages),
                    {"role": "user", "content": user_reply},
                ]
                trace["clarification"] = {
                    "question": pending_clarification.get("question"),
                    "options": pending_clarification.get("options"),
                    "user_choice": choice_text,
                }
                async for payload in _finalize_query(
                    query_id=query_id,
                    user_id=user_id,
                    session_id=session_id,
                    messages=visible_messages,
                    original_query=original_query,
                    parsed_query=parsed_query,
                    intent=clarification_intent,
                    authorization=authorization,
                    db_session=db_session,
                    db_operator=db_operator,
                    existing_record=True,
                    trace=trace,
                    started_at=started_at,
                    skip_ambiguity=True,
                ):
                    yield payload
                return

            # 走到这里说明用户是在回答 NER 的语义追问（口径澄清那条分支已经 return 或已放弃）
            if pending_conversation is not None:
                semantic_resume_messages = pending_conversation.extra_payload.get("semantic_resume_messages")
                semantic_entities = pending_conversation.extra_payload.get("semantic_entities")
                if not semantic_resume_messages or not isinstance(semantic_entities, list):
                    raise ValueError("待恢复会话缺少语义恢复上下文")

                visible_messages = [
                    *llm_service.prepare_messages(pending_conversation.messages),
                    {"role": "user", "content": user_reply},
                ]
                parsed_query = None
                async for reply_type, content in llm_service.continue_semantics(
                    messages=[*semantic_resume_messages, {"role": "user", "content": user_reply}],
                    original_query=original_query,
                    entities=semantic_entities,
                ):
                    if reply_type == "semantic_reply_cot":
                        sem_cot_resp = ChunkResponse(id=query_id, type="semantic_reply_cot", content=content)
                        yield f"data: {sem_cot_resp.model_dump_json()}\n\n"
                    elif reply_type == "semantic_reply":
                        sem_resp = ChunkResponse(id=query_id, type="semantic_reply", content=content)
                        yield f"data: {sem_resp.model_dump_json()}\n\n"
                    elif reply_type == "semantic_waiting":
                        question = content["question"]
                        await db_operator.update_conversation(
                            query_id=query_id,
                            session=db_session,
                            user_id=user_id,
                            messages=[*visible_messages, {"role": "assistant", "content": question}],
                            extra_payload={
                                "pending_semantic_question": question,
                                "semantic_resume_messages": content["resume_messages"],
                                "semantic_entities": content["entities"],
                            },
                            status=STATUS_SEMANTIC_REPLY,
                        )
                        return
                    elif reply_type == "final_parsed_query":
                        parsed_query = content

                if parsed_query is None:
                    raise ValueError("语义恢复未得到最终解析结果")

                logger.info(f"语义恢复结果：{parsed_query}")
                async for payload in _finalize_query(
                    query_id=query_id,
                    user_id=user_id,
                    session_id=session_id,
                    messages=visible_messages,
                    original_query=original_query,
                    parsed_query=parsed_query,
                    intent=intent,
                    authorization=authorization,
                    db_session=db_session,
                    db_operator=db_operator,
                    existing_record=True,
                    entities=semantic_entities,
                    trace=trace,
                    started_at=started_at,
                ):
                    yield payload
                return

        original_query = llm_service.get_latest_user_message(normalized_messages)

        existing_record = await db_operator.get_latest_conversation_by_session_id(
            user_id, session_id=session_id)
        if existing_record is not None:
            #NOTE append history message to recognize current intent
            history_messages = existing_record.messages
            normalized_messages = history_messages + normalized_messages

        intent = await llm_service.recognize_intent(normalized_messages)
        logger.info(f"意图识别：{intent}")
        trace["intent"] = intent
        trace["intent_label"] = INTENT_LABELS.get(intent, intent)

        intent_resp = ChunkResponse(id=query_id, type="recognize_intent", content=f"[识别意图] {intent}")
        yield f"data: {intent_resp.model_dump_json()}\n\n"
        yield _trace_event(query_id, "intent_recognized", intent=intent, label=trace["intent_label"])

        parsed_query = original_query
        ner_entities: list[str] = []
        async for reply_type, content in llm_service.parse_semantics(
            normalized_messages,
            intent,
            authorization,
        ):
            if reply_type == "ner_reply":
                ner_resp = ChunkResponse(id=query_id, type="ner_reply", content=content)
                yield f"data: {ner_resp.model_dump_json()}\n\n"
            elif reply_type == "entities":
                ner_entities = content
            elif reply_type == "semantic_reply_cot":
                sem_cot_resp = ChunkResponse(id=query_id, type="semantic_reply_cot", content=content)
                yield f"data: {sem_cot_resp.model_dump_json()}\n\n"
            elif reply_type == "semantic_reply":
                sem_resp = ChunkResponse(id=query_id, type="semantic_reply", content=content)
                yield f"data: {sem_resp.model_dump_json()}\n\n"
            elif reply_type == "semantic_waiting":
                question = content["question"]
                await db_operator.save_conversation(
                    session=db_session,
                    query_id=query_id,
                    user_id=user_id,
                    session_id=session_id,
                    intent=intent,
                    original_query=original_query,
                    messages=[*normalized_messages, {"role": "assistant", "content": question}],
                    extra_payload={
                        "pending_semantic_question": question,
                        "semantic_resume_messages": content["resume_messages"],
                        "semantic_entities": content["entities"],
                    },
                    status=STATUS_SEMANTIC_REPLY,
                )
                return
            elif reply_type == "final_parsed_query":
                parsed_query = content

        logger.info(f"语义解析结果：{parsed_query}")
        yield _trace_event(query_id, "semantics_parsed", parsed_query=parsed_query, entities=ner_entities)
        async for payload in _finalize_query(
            query_id=query_id,
            user_id=user_id,
            session_id=session_id,
            messages=normalized_messages,
            original_query=original_query,
            parsed_query=parsed_query,
            intent=intent,
            authorization=authorization,
            db_session=db_session,
            db_operator=db_operator,
            existing_record=False,
            entities=ner_entities,
            trace=trace,
            started_at=started_at,
        ):
            yield payload
    except Exception as e:
        import traceback
        logger.error(f"查询处理异常: {str(e)}")
        logger.error(traceback.format_exc())
        await db_operator.update_conversation(
            query_id=query_id,
            session=db_session,
            extra_payload={"error": str(e)},
            status=STATUS_FAILED,
        )
        error_resp = ChunkResponse(id=query_id, type="error", content=f'[服务报错] {str(e)}')
        yield f"data: {error_resp.model_dump_json()}\n\n"
    finally:
        yield "[DONE]"


@router.post("/query")
async def handle_query(
    request: QueryRequest,
    db_session: AsyncSession = Depends(get_db_session),
    db_operator: DatabaseOperator = Depends(get_db_operator),
):
    """处理用户查询请求 - SSE流式响应"""
    user_query = request.query
    user_id = request.user_id
    authorization = request.authorization

    if not user_query:
        raise HTTPException(
            status_code=400, detail="查询内容不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    if not user_id:
        raise HTTPException(
            status_code=400, detail="user_id不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    if not authorization:
        raise HTTPException(
            status_code=400, detail="Authorization不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    return StreamingResponse(
        generate_stream(
            messages=[{"role": "user", "content": user_query}],
            user_id=user_id,
            authorization=authorization,
            session_id=request.session_id or str(uuid4()),
            db_session=db_session,
            db_operator=db_operator,
        ),
        media_type="text/event-stream"
    )


@router.post("/chat/query")
async def handle_chat_query(
    request: ConversationQueryRequest,
    db_session: AsyncSession = Depends(get_db_session),
    db_operator: DatabaseOperator = Depends(get_db_operator),
):
    """处理多轮对话查询请求 - SSE流式响应"""
    if not request.user_id:
        raise HTTPException(
            status_code=400, detail="user_id不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    if not request.authorization:
        raise HTTPException(
            status_code=400, detail="Authorization不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    if not request.messages:
        raise HTTPException(
            status_code=400, detail="messages不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    return StreamingResponse(
        generate_stream(
            messages=[message.model_dump() for message in request.messages],
            user_id=request.user_id,
            authorization=request.authorization,
            session_id=request.session_id,
            db_session=db_session,
            db_operator=db_operator,
        ),
        media_type="text/event-stream"
    )


@router.post("/history/sessions", response_model=list[SessionSummaryResponse])
async def list_history_sessions(
    user_id: str = Body(..., embed=True, description="用户ID"),
    limit: int = Body(50, description="每页数量"),
    offset: int = Body(0, description="偏移量"),
    db_operator: DatabaseOperator = Depends(get_db_operator),
):
    """查询某个用户的历史会话窗口列表。"""
    if not user_id:
        raise HTTPException(
            status_code=400, detail="user_id不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    sessions = await db_operator.list_user_sessions(user_id=user_id, limit=limit, offset=offset)
    return [_serialize_session_summary(session) for session in sessions]


@router.post("/history/session", response_model=list[HistoryRecordResponse])
async def get_history_session_records(
    session_id: str = Body(..., embed=True, description="会话窗口ID"),
    user_id: str = Body(..., embed=True, description="用户ID"),
    limit: int = Body(100, description="每页数量"),
    offset: int = Body(0, description="偏移量"),
    db_operator: DatabaseOperator = Depends(get_db_operator),
):
    """查询某个用户在指定会话窗口下的历史记录。"""
    if not user_id:
        raise HTTPException(
            status_code=400, detail="user_id不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    records = await db_operator.list_conversations(
        user_id=user_id,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    ordered_records = sorted(records, key=lambda item: item.created_at)
    return [_serialize_history_record(record) for record in ordered_records]


@router.post("/history/session/delete", response_model=DeleteSessionResponse)
async def delete_history_session(
    session_id: str = Body(..., embed=True, description="会话窗口ID"),
    user_id: str = Body(..., embed=True, description="用户ID"),
    db_operator: DatabaseOperator = Depends(get_db_operator),
):
    """删除某个用户在指定会话窗口下的所有对话记录。"""
    if not user_id:
        raise HTTPException(
            status_code=400, detail="user_id不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    if not session_id:
        raise HTTPException(
            status_code=400, detail="session_id不能为空", headers={"Content-Type": "application/json; charset=utf-8"})

    deleted_count = await db_operator.delete_session(user_id=user_id, session_id=session_id)

    if deleted_count == 0:
        raise HTTPException(
            status_code=404, detail="未找到该会话记录", headers={"Content-Type": "application/json; charset=utf-8"})

    return DeleteSessionResponse(
        success=True,
        session_id=session_id,
        deleted_count=deleted_count,
        message=f"成功删除 {deleted_count} 条对话记录",
    )
