import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from uuid import uuid4
from datetime import datetime
from typing import Dict, Any, AsyncGenerator
import json

from api.schemas.query import QueryRequest, QueryResponse, ChunkResponse
from services.llm_service import llm_service
from services.milvus_service import milvus_service
from services.sql_service import sql_service
from prompts import (
    ATTENDANCE_TABLE_DESCRIPTIONS, BPM_TABLE_DESCRIPTIONS,
    GENERATE_SYS_V2, GENERATE_SYS, FEEDBACK_SYS,
    BPM_NOTE, ATTENDANCE_NOTE
)
from logg import logger

router = APIRouter(prefix="/api", tags=["query"])

# 存储查询历史，用于处理反馈
query_history: Dict[str, Any] = {}


async def generate_and_query_db(
query_id:str, authorization:str, intent:str, polished_query:str, table_descs:str, note:str):

    datetime_today = datetime.now().strftime("%Y-%m-%d, %A")

    gen_sys = GENERATE_SYS_V2.format(
        datetime_today=datetime_today, table_descs=table_descs, note=note)
    
    # 初始化对话历史
    messages = [
        {"role": "system", "content": gen_sys},
        {"role": "user", "content": f"用户查询：{polished_query}"}
    ]

    MAX_RETRIES = 3
    query_result = None
    sql_content = None
    
    flag_resp = ChunkResponse(id=query_id, type='flag_to_reply',content='[开始生成SQL]')
    yield f"data: {flag_resp.model_dump_json()}\n\n"

    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0:
            logger.info(f"============== 第 {attempt} 次尝试修正 SQL ==============")
        
        # 调用大模型生成SQL（流式）
        sql_response = ""
        extracted_sql = ""
        async for chunk in llm_service.generate_sql(messages):
            if isinstance(chunk, tuple) and chunk[0] is None:
                # 结束标记，提取的SQL
                extracted_sql = chunk[1]
            else:
                # 流式chunk
                sql_response += chunk
                if attempt == 0:
                    chunk_resp = ChunkResponse(id=query_id,type='stream_reply',content=chunk)
                else:
                    chunk_resp = ChunkResponse(id=query_id,type='retry_reply',content=chunk)

                # 发送SQL生成进度
                yield f"data: {chunk_resp.model_dump_json()}\n\n"
        
        sql_content = extracted_sql
        
        # 将模型回复加入对话历史
        messages.append({"role": "assistant", "content": sql_response})
        
        try:
            # 尝试执行查询
            query_result = await sql_service.execute_sql(sql_content, authorization, intent)
            logger.info(f"查询成功: 返回 {len(query_result['columns'])} 列; {query_result['row_count']} 行")

            query_resp = ChunkResponse(id=query_id,type='query_success',content='[SQL查询成功]')
            yield f"data: {query_resp.model_dump_json()}\n\n"
            break
        
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"SQL执行报错 (ValueError): {error_msg}")
            
            if attempt < MAX_RETRIES:
                feedback_prompt = FEEDBACK_SYS.format(error_msg=error_msg)
                messages.append({"role": "user", "content": feedback_prompt})
                logger.info("已将报错信息反馈给大模型，准备重试...")
            else:
                logger.warning("已达到最大重试次数，无法修正SQL。")
                raise ValueError("[SQL执行报错] 已达到最大重试次数，无法修正SQL。")
    yield sql_content, query_result


async def generate_stream(request: QueryRequest) -> AsyncGenerator[str, None]:
    """生成流式响应的异步生成器"""
    try:
        user_query = request.query
        authorization = request.authorization
        query_id = str(uuid4())
        
        # 意图识别
        intent = await llm_service.recognize_intent(user_query)
        logger.info(f"意图识别：{intent}")
        
        # 发送意图识别结果
        intent_resp = ChunkResponse(id=query_id, type='recognize_intent',content=f"[识别意图] {intent}")
        yield f"data: {intent_resp.model_dump_json()}\n\n"
        
        # 选择注意事项的提示词
        note = BPM_NOTE if intent == 'bpm' else ATTENDANCE_NOTE

        # 获取表结构描述
        table_descriptions = ATTENDANCE_TABLE_DESCRIPTIONS if intent == 'attendance' else BPM_TABLE_DESCRIPTIONS
        
        # 润色用户查询
        polished_query = await llm_service.polish_query(user_query, str(table_descriptions))
        logger.info(f"润色后的查询: {polished_query}")
        
        # 发送润色后的查询
        polish_resp = ChunkResponse(id=query_id, type='polish_query',content=f"[润色查询] {polished_query}")
        yield f"data: {polish_resp.model_dump_json()}\n\n"
        
        # 生成查询向量
        query_embedding = await llm_service.generate_embedding(polished_query)
        logger.info("完成生成查询向量")
        
        # 搜索最匹配的表结构
        collection_name = intent
        table_descs = await milvus_service.search_table_schema(query_embedding, collection_name)

        # logger.debug(f"[TABLE DESCS] {table_descs}")
        def get_table_brief_desc():
            brief_descs=re.findall('(?<=表名：).*?(?=\n)',table_descs)
            return '\n'.join(brief_descs)

        brief_descs = get_table_brief_desc()
        logger.debug(f"完成搜索匹配的表结构: \n{brief_descs}")
        # 发送表结构信息
        retrieval_resp = ChunkResponse(
            id=query_id, type='retrieve_tables', content=f"[查询到相关表结构] {brief_descs}")
        yield f"data: {retrieval_resp.model_dump_json()}\n\n"
        
        agen = generate_and_query_db(
            query_id, authorization, intent, polished_query, table_descs, note)
        async for result in agen:
            if isinstance(result, str):
                yield result
            elif isinstance(result, tuple):
                sql_content, query_result = result
        
        # 生成数据推理分析
        data_analysis = llm_service.generate_data_analysis(query_result)
        
        # 保存查询历史
        query_history[str(query_id)] = {
            'user_query': user_query,
            'polished_query': polished_query,
            'table_desc': table_descs,
            'sql': sql_content
        }
        
        # 发送最终结果
        final_resp = ChunkResponse(
            id=query_id, type='final_result',
            content=QueryResponse(
                original_query=user_query,
                polished_query=polished_query,
                sql_dialect=sql_content,
                result=None,
                natural_answer=None,
                data_analysis=data_analysis,
            )
        )
        yield f"data: {final_resp.model_dump_json()}\n\n"
        
    except Exception as e:
        import traceback
        logger.error(f"查询处理异常: {str(e)}")
        logger.error(traceback.format_exc())
        error_resp = ChunkResponse(id=query_id, type="error",content=f'[服务报错] {str(e)}')
        yield f"data: {error_resp.model_dump_json()}\n\n"

    finally:
        yield "[DONE]"


@router.post("/query")
async def handle_query(request: QueryRequest):
    """处理用户查询请求 - SSE流式响应"""
    user_query = request.query
    authorization = request.authorization
    
    if not user_query:
        raise HTTPException(
            status_code=400, detail="查询内容不能为空", headers={"Content-Type":"application/json; charset=utf-8"})
    
    if not authorization:
        raise HTTPException(
            status_code=400, detail="Authorization不能为空", headers={"Content-Type":"application/json; charset=utf-8"})

    return StreamingResponse(
        generate_stream(request),
        media_type="text/event-stream"
    )
