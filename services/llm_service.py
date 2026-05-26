from typing import *

import rich
# from openai import AsyncOpenAI
from services.custom_openai import CAsyncOpenAI
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from config import settings
from logg import logger

class LLMService:
    """大语言模型服务"""
    
    def __init__(self):
        # 创建两个异步OpenAI客户端实例
        self.client = CAsyncOpenAI(
            api_key=settings.OPENAI_API_KEY_1,
            base_url=settings.OPENAI_API_BASE_1)
    
    async def recognize_intent(self, user_query: str) -> str:
        """识别用户查询意图（考勤/工单）"""
        from prompts import INTENT_RECOGNITION
        
        completion = await self.client.chat.completions.create(
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
            return "attendance"
        elif "<工单>" in llm_output:
            return "bpm"
        else:
            raise ValueError(f"LLM意图识别错误. 原始输出: {llm_output}")
    
    async def polish_query(self, user_query: str, table_view_struct: str) -> str:
        """润色用户查询"""
        from prompts import POLISH_SYS
        from utils.helpers import extract_last_tag_content
        
        polish_sys = POLISH_SYS.format(table_view_struct=table_view_struct)
        
        completion = await self.client.chat.completions.create(
            model=settings.FLASH_MODEL,
            messages=[
                {"role": "system", "content": polish_sys},
                {"role": "user", "content": user_query}
            ],
            extra_body=dict(chat_template_kwargs=dict(enable_thinking=False)),
            extra_authorization_key=settings.POLISH_MODEL,
        )
        logger.debug(f"[POLISH QUERY COMPLETION] {completion.model_dump_json()}")
        polished_query = completion.choices[0].message.content
        return extract_last_tag_content(polished_query, "润色后")


    async def ask_llm(self, messages:Iterable[ChatCompletionMessageParam], enable_thinking=True):
        extra_body=dict(chat_template_kwargs=dict(enable_thinking=enable_thinking))

        completion = await self.client.chat.completions.create(
            model=settings.GENERATE_MODEL,
            messages=messages,
            temperature=0.7,
            extra_body=extra_body,
            stream=True,
            extra_authorization_key=settings.GENERATE_MODEL_KEY
        )
        output_think_prefix=enable_thinking
        output_think_suffix=False
        reasoning_tokens=0
        completion_tokens=0

        assistant_content = ""
        async for chunk in completion:
            # logger.debug(f"[GENERATE SQL CHUNK] {chunk.model_dump_json()}")
            if chunk.choices:
                content=""
                if (hasattr(chunk.choices[0].delta, 'reasoning_content')
                        and chunk.choices[0].delta.reasoning_content):

                    content:str = chunk.choices[0].delta.reasoning_content
                    if output_think_prefix:
                        content = "<think>\n"+content
                        output_think_prefix=False
                        output_think_suffix=True

                    reasoning_tokens+=1

                if chunk.choices[0].delta.content:                        
                    content = chunk.choices[0].delta.content
                    if output_think_suffix:
                        content = "</think>\n"+content
                        output_think_suffix=False
                completion_tokens+=1

                yield content  # 逐块返回
                assistant_content+=content
        
        logger.debug("[GENERATE DIALOGUE]")
        logger.debug(f"[USER]\n{messages[-1]['content']}\n\n")
        logger.info(f"[ASSISTANT]\n{assistant_content}\n\n")
        logger.info(f"[USAGE] reasoning_tokens:{reasoning_tokens} completion_tokens:{completion_tokens}")


    async def generate_sql(self, messages: Iterable[ChatCompletionMessageParam]):
        """
        生成SQL语句（流式响应）- 返回异步生成器
        缓存命中生成 && 未命中生成
        """
        from utils.helpers import extract_last_tag_content
        
        # 收集流式响应的所有chunk
        sql_response = ""

        agen = self.ask_llm(messages)
        async for content in agen:
            sql_response += content
            yield content

        # 返回最终提取的SQL
        extracted_sql = extract_last_tag_content(sql_response, "sql")
        yield None, extracted_sql  # 使用None标记结束，并返回提取的SQL
    
    async def generate_embedding(self, text: str) -> List[float]:
        """生成文本向量"""
        response = await self.client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text,
            encoding_format="float",
            extra_authorization_key=settings.EMBEDDING_MODEL_KEY,
        )
        return response.data[0].embedding
    
    def generate_data_analysis(self, query_result: Dict[str, Any]) -> str:
        """生成数据推理分析"""
        from utils.helpers import dict_to_markdown_table
        return dict_to_markdown_table(query_result)


# 创建全局LLM服务实例
llm_service = LLMService()