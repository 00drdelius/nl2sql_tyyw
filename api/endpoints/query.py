from __future__ import annotations
from datetime import datetime
from typing import Any, AsyncGenerator, Iterable
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
    SessionSummaryResponse,
)
from db.database import DatabaseOperator
from db.dependencies import get_db_operator, get_db_session
from services.llm_service import llm_service
from services.milvus_service import milvus_service
from services.sql_service import sql_service
from prompts import (
    ATTENDANCE_TABLE_DESCRIPTIONS, BPM_TABLE_DESCRIPTIONS,
    FEEDBACK_SYS, GENERATE_SYS_V2,
    BPM_NOTE, ATTENDANCE_NOTE
)
from logg import logger

router = APIRouter(prefix="/api", tags=["query"])

STATUS_PROCESSING = "processing"
STATUS_SEMANTIC_REPLY = "semantic_reply"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


async def generate_and_query_db(
    query_id: str,
    authorization: str,
    intent: str,
    messages: Iterable[dict[str, str]],
    table_descs: str,
    note: str,
) -> AsyncGenerator[str | tuple[str, dict[str, Any], list[dict[str, str]]], None]:
    datetime_today = datetime.now().strftime("%Y-%m-%d, %A")
    gen_sys = GENERATE_SYS_V2.format(
        datetime_today=datetime_today, table_descs=table_descs, note=note)
    working_messages = llm_service.prepare_messages(messages)

    MAX_RETRIES = 3
    query_result = None
    sql_content = None

    flag_resp = ChunkResponse(id=query_id, type='flag_to_reply', content='[开始生成SQL]')
    yield f"data: {flag_resp.model_dump_json()}\n\n"

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            logger.info(f"============== 第 {attempt} 次尝试修正 SQL ==============")

        # 调用大模型生成SQL（流式）
        sql_response = ""
        extracted_sql = ""
        async for chunk in llm_service.generate_sql(working_messages, sys_prompt=gen_sys):
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
        working_messages.append({"role": "assistant", "content": sql_response})

        try:
            query_result = await sql_service.execute_sql(sql_content, authorization, intent)
            logger.info(f"查询成功: 返回 {len(query_result['columns'])} 列; {query_result['row_count']} 行")

            query_resp = ChunkResponse(id=query_id, type='query_success', content='[SQL查询成功]')
            yield f"data: {query_resp.model_dump_json()}\n\n"
            break
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"SQL执行报错 (ValueError): {error_msg}")

            if attempt < MAX_RETRIES:
                feedback_prompt = FEEDBACK_SYS.format(error_msg=error_msg)
                working_messages.append({"role": "user", "content": feedback_prompt})
                logger.info("已将报错信息反馈给大模型，准备重试...")
            else:
                logger.warning("已达到最大重试次数，无法修正SQL。")
                raise ValueError("[SQL执行报错] 已达到最大重试次数，无法修正SQL。")
    yield sql_content, query_result, working_messages
def _normalize_messages(messages: Iterable[ChatMessage | dict[str, str]]) -> list[dict[str, str]]:
    normalized = llm_service.prepare_messages(messages)
    if not normalized:
        raise ValueError("对话记录不能为空")
    if normalized[-1]["role"] != "user":
        raise ValueError("最后一条对话必须是用户消息")
    return normalized


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
) -> AsyncGenerator[str, None]:
    note = BPM_NOTE if intent == "bpm" else ATTENDANCE_NOTE
    table_descriptions = ATTENDANCE_TABLE_DESCRIPTIONS if intent == "attendance" else BPM_TABLE_DESCRIPTIONS

    parsed_messages = llm_service.replace_latest_user_message(messages, parsed_query)
    polished_query = await llm_service.polish_query(parsed_messages, str(table_descriptions))
    logger.info(f"润色后的查询: {polished_query}")

    polish_resp = ChunkResponse(id=query_id, type="polish_query", content=f"[润色查询] {polished_query}")
    yield f"data: {polish_resp.model_dump_json()}\n\n"

    query_embedding = await llm_service.generate_embedding(polished_query)
    logger.info("完成生成查询向量")

    table_descs = await milvus_service.search_table_schema(query_embedding, intent)
    polished_messages = llm_service.replace_latest_user_message(messages, polished_query)
    agen = generate_and_query_db(
        query_id=query_id,
        authorization=authorization,
        intent=intent,
        messages=polished_messages,
        table_descs=table_descs,
        note=note,
    )
    async for result in agen:
        if isinstance(result, str):
            yield result
        elif isinstance(result, tuple):
            sql_content, query_result, sql_generation_messages = result

    data_analysis = llm_service.generate_data_analysis(query_result)
    final_response_payload = QueryResponse(
        original_query=original_query,
        polished_query=polished_query,
        sql_dialect=sql_content,
        result=None,
        natural_answer=None,
        data_analysis=data_analysis,
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

        intent_resp = ChunkResponse(id=query_id, type="recognize_intent", content=f"[识别意图] {intent}")
        yield f"data: {intent_resp.model_dump_json()}\n\n"

        parsed_query = original_query
        async for reply_type, content in llm_service.parse_semantics(
            normalized_messages,
            intent,
            authorization,
        ):
            if reply_type == "ner_reply":
                ner_resp = ChunkResponse(id=query_id, type="ner_reply", content=content)
                yield f"data: {ner_resp.model_dump_json()}\n\n"
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
