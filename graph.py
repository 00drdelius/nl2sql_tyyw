from typing import *

from langchain_core.runnables import RunnableConfig

from langgraph.graph import StateGraph, START, END
from langgraph.runtime import Runtime
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from config import settings
from schemas.graph_state import ContextSchema, StateSchema, Intent


async def recognize_intent(state:StateSchema, runtime:Runtime[ContextSchema]):
    from prompts import INTENT_RECOGNITION
    llm_client = runtime.context['llm_client']
    user_query = state.query_request.query
    
    completion = await llm_client.chat.completions.create(
        model=settings.FLASH_MODEL,
        messages=[
            {"role": "system", "content": INTENT_RECOGNITION},
            {"role": "user", "content": f"# 用户问题\n{user_query}"}
        ],
        stream=False,
        extra_authorization_key=settings.FLASH_MODEL_KEY,
    )
    llm_output = completion.choices[0].message.content
    if "<考勤>" in llm_output:
        return {"intent": Intent.ATTENDANCE}
    elif "<工单>" in llm_output:
        return {"intent": Intent.BPM}
    else:
        raise ValueError(f"LLM意图识别错误. 原始输出: {llm_output}")


async def recognize_named_entity(state:StateSchema, runtime:Runtime[ContextSchema]):
    ...

