from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator, Iterable
from datetime import datetime

from services.custom_openai import CAsyncOpenAI
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from config import settings
from logg import logger

class LLMService:
    """大语言模型服务"""

    def __init__(self):
        self.client = CAsyncOpenAI(
            api_key=settings.OPENAI_API_KEY_1,
            base_url=settings.OPENAI_API_BASE_1)

    def prepare_messages(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        sys_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        prepared_messages = [dict(message) for message in messages if message["role"] != "system"]
        if sys_prompt:
            return [{"role": "system", "content": sys_prompt}, *prepared_messages]
        return prepared_messages

    def get_latest_user_message(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
    ) -> str:
        prepared_messages = self.prepare_messages(messages)
        return prepared_messages[-1]["content"]

    def replace_latest_user_message(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        content: str,
    ) -> list[dict[str, str]]:
        prepared_messages = self.prepare_messages(messages)
        prepared_messages[-1] = {"role": "user", "content": content}
        return prepared_messages

    @staticmethod
    def strip_think_content(content: str) -> str:
        return re.sub(r"<think>[\s\S]*?</think>", "", content).strip()

    @staticmethod
    def extract_semantics(determine_output: str) -> list[str]:
        try:
            match = re.search(r'```json\n(.*?)\n```', determine_output, re.DOTALL)
            if not match:
                return []
            sem_json = json.loads(match.group(1))
            semantics = sem_json.get("确定语义", [])
            return semantics if isinstance(semantics, list) else []
        except Exception:
            return []

    async def recognize_intent(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        sys_prompt: str | None = None,
    ) -> str:
        """识别用户查询意图（考勤/工单/告警）"""
        from prompts import INTENT_RECOGNITION

        prepared_frontend_messages = self.prepare_messages(messages)
        latest_user_message = self.get_latest_user_message(prepared_frontend_messages)
        # 意图识别只需最新一条用户消息，发送全部历史会超出FLASH_MODEL的65536 token限制
        intent_messages = [{"role": "user", "content": f"<用户问题>\n{latest_user_message}\n</用户问题>"}]
        completion = await self.client.chat.completions.create(
            model=settings.FLASH_MODEL,
            messages=self.prepare_messages(intent_messages, sys_prompt or INTENT_RECOGNITION),
            stream=False,
            extra_body=dict(chat_template_kwargs=dict(enable_thinking=False)),
            extra_authorization_key=settings.FLASH_MODEL_KEY,
        )
        llm_output = completion.choices[0].message.content
        if "<考勤>" in llm_output:
            return "attendance"
        elif "<工单>" in llm_output:
            return "bpm"
        elif "<告警>" in llm_output:
            return "alert"
        else:
            raise ValueError(f"LLM意图识别错误. 原始输出: {llm_output}")

    async def parse_semantics(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        intent: str,
        authorization: str,
        *,
        ner_sys_prompt: str | None = None,
        determine_sys_prompt: str | None = None,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        """语义解析：提取实体 -> 模糊查询 -> 确定语义
        产出:
        yield ("ner_reply", ner_output)
        yield ("semantic_reply", chunk)
        yield ("final_parsed_query", result)
        """
        from prompts import NER_SYS, DETERMINE_SEMANTICS_SYS
        from source.tables import ATTDN_RAW, BPM_RAW, ALERT_RAW
        from services.sql_service import sql_service

        original_query = self.get_latest_user_message(messages)
        if intent in ('attendance', 'attdance'):
            table_schemas = ATTDN_RAW
        elif intent == 'alert':
            table_schemas = ALERT_RAW
        else:
            table_schemas = BPM_RAW

        # 1. 实体提取 (NER)
        ner_messages = self.replace_latest_user_message(
            messages,
            (
                f"<table_schemas>\n{table_schemas}\n</table_schemas>\n\n"
                f"<用户问题>\n{original_query}\n</用户问题>"
            ),
        )
        ner_completion = await self.client.chat.completions.create(
            model=settings.GENERATE_MODEL,
            messages=self.prepare_messages(ner_messages, ner_sys_prompt or NER_SYS),
            stream=False,
            extra_authorization_key=settings.GENERATE_MODEL_KEY,
        )

        ner_output = ner_completion.choices[0].message.content
        logger.debug(f"[NER OUTPUT] {ner_output}")
        yield ("ner_reply", ner_output)

        # 提取JSON中的实体（增强容错）
        entities = []
        try:
            # 尝试多种JSON提取模式
            json_str = None
            for pattern in [
                r'```json\s*(.*?)\s*```',
                r'```\s*(.*?)\s*```',
                r'\{[^{}]*"实体"[^{}]*\}',
            ]:
                match = re.search(pattern, ner_output, re.DOTALL)
                if match:
                    json_str = match.group(1) if '```' in pattern else match.group()
                    break
            if not json_str:
                json_str = ner_output
            json_str = json_str.strip()
            # 去掉markdown代码块残留
            json_str = re.sub(r'^```\w*\s*', '', json_str)
            json_str = re.sub(r'\s*```$', '', json_str)
            # 只取第一个完整JSON对象
            brace_start = json_str.find('{')
            if brace_start >= 0:
                brace_count = 0
                brace_end = brace_start
                for i in range(brace_start, len(json_str)):
                    if json_str[i] == '{':
                        brace_count += 1
                    elif json_str[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            brace_end = i + 1
                            break
                json_str = json_str[brace_start:brace_end]
            ner_json = json.loads(json_str)
            entities = ner_json.get("实体", [])
        except Exception as e:
            logger.error(f"Failed to parse NER JSON: {e}")

        if not entities:
            yield ("final_parsed_query", original_query)
            return

        # 2. 模糊查询
        fuzzy_fields = []
        for entity in entities:
            fields = await sql_service.fuzzy_query(entity, authorization, intent)
            fuzzy_fields.extend(fields)

        if not fuzzy_fields:
            yield ("final_parsed_query", original_query)
            return

        # 3. 确定语义
        determine_messages = self.replace_latest_user_message(
            messages,
            (
                f"<table_schemas>\n{table_schemas}\n</table_schemas>"
                f"\n\n<用户问题>\n{original_query}\n</用户问题>"
                f"\n\n<entities>\n{json.dumps(entities, ensure_ascii=False)}\n</entities>"
                f"\n\n<fuzzy_fields>\n{json.dumps(fuzzy_fields, ensure_ascii=False)}\n</fuzzy_fields>"
            ),
        )

        async for semantic_result in self.continue_semantics(
            determine_messages,
            original_query=original_query,
            entities=entities,
            determine_sys_prompt=determine_sys_prompt or DETERMINE_SEMANTICS_SYS,
        ):
            yield semantic_result

    async def continue_semantics(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        *,
        original_query: str,
        entities: list[str],
        determine_sys_prompt: str | None = None,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        from prompts import DETERMINE_SEMANTICS_SYS

        logger.debug(f"[DETERMINE SEMANTICS STAGE]")
        determine_messages = self.prepare_messages(messages)
        determine_output = ""
        agen = self.ask_llm(
            determine_messages,
            enable_thinking=False, #TODO try disabling thinking to reduce chain of thought
            sys_prompt=determine_sys_prompt or DETERMINE_SEMANTICS_SYS,
        )
        cot_flag = False
        async for content in agen:
            determine_output += content
            if "<think>" in content:
                cot_flag = True
            elif "</think>" in content:
                cot_flag = False
            if cot_flag:
                yield ("semantic_reply_cot", content)
            else:
                yield ("semantic_reply", content)

        logger.debug(f"[DETERMINE SEMANTICS OUTPUT] {determine_output}")
        semantics = self.extract_semantics(determine_output)
        if semantics:
            semantic_supplement = "；".join(
                [f"{ner_item}指{semantic}" for ner_item, semantic in zip(entities, semantics)]
            )
            yield ("final_parsed_query", f"{original_query}\n(需要补充的语义: {semantic_supplement})")
            return

        visible_output = self.strip_think_content(determine_output)
        yield (
            "semantic_waiting",
            {
                "question": visible_output,
                "resume_messages": [
                    *determine_messages,
                    {"role": "assistant", "content": visible_output},
                ],
                "entities": entities,
                "original_query": original_query,
            },
        )

    async def polish_query(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        table_view_struct: str,
        intent: str = "",
        sys_prompt: str | None = None,
    ) -> str:
        """润色用户查询"""
        from prompts import POLISH_SYS
        from utils.helpers import extract_last_tag_content

        # 根据意图生成领域描述
        intent_descs = {
            "alert": "设备告警监控领域。只能使用设备告警记录表(view_alert_all)、设备所属单位表(view_alert_organization)、设备所属业务表(view_alert_business)中的字段。",
            "bpm": "工单流程管理领域。只能使用流程实例表(bpm_maindata/bpm_archiveddata)、流程模型表(bpm_modprocesslist)及其XmlData中的字段。",
            "attendance": "考勤管理领域。优先使用imoc_attendance_all视图（字段全中文，可直接用中文字段名）。若imoc_attendance_all不可用，则基于imoc_class_duty_user表。辅助表：考勤人员表(imoc_class_user)、打卡记录表(imoc_checkin_user)、排班表(imoc_class_duty)、项目表(imoc_class_project)。",
        }
        intent_desc = intent_descs.get(intent, "")

        datetime_today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        polish_sys = sys_prompt or POLISH_SYS.format(
            table_view_struct=table_view_struct, datetime_today=datetime_today, intent_desc=intent_desc)

        latest_user_message = self.get_latest_user_message(messages)
        polish_messages = self.replace_latest_user_message(
            messages,
            f"<用户问题>\n{latest_user_message}\n</用户问题>",
        )
        completion = await self.client.chat.completions.create(
            model=settings.POLISH_MODEL,
            messages=self.prepare_messages(polish_messages, polish_sys),
            extra_body=dict(chat_template_kwargs=dict(enable_thinking=False)),
            extra_authorization_key=settings.POLISH_MODEL_KEY,
        )
        logger.debug(f"[POLISH QUERY COMPLETION] {completion.model_dump_json()}")
        polished_query = completion.choices[0].message.content
        return extract_last_tag_content(polished_query, "润色后")

    async def ask_llm(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        *,
        enable_thinking: bool = False,
        sys_prompt: str | None = None,
        model: str | None = None,
        authorization_key: str | None = None,
    ):
        prepared_messages = self.prepare_messages(messages, sys_prompt)
        extra_body=dict(chat_template_kwargs=dict(enable_thinking=enable_thinking))
        self.client.base_url = settings.OPENAI_API_BASE_1
        completion = await self.client.chat.completions.create(
            model=model or settings.GENERATE_MODEL,
            messages=prepared_messages,
            temperature=0.7,
            extra_body=extra_body,
            stream=True,
            extra_authorization_key=authorization_key or settings.GENERATE_MODEL_KEY
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
        if prepared_messages:
            logger.debug(f"[USER]\n{prepared_messages[-1]['content']}\n\n")
        logger.info(f"[ASSISTANT]\n{assistant_content}\n\n")
        logger.info(f"[USAGE] reasoning_tokens:{reasoning_tokens} completion_tokens:{completion_tokens}")


    async def generate_sql(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        sys_prompt: str | None = None,
        enable_thinking: bool = False,
    ):
        """
        生成SQL语句（流式响应）- 返回异步生成器
        缓存命中生成 && 未命中生成
        """
        from utils.helpers import extract_last_tag_content

        # 收集流式响应的所有chunk
        sql_response = ""

        agen = self.ask_llm(messages, sys_prompt=sys_prompt, enable_thinking=enable_thinking)
        async for content in agen:
            sql_response += content
            yield content

        # 返回最终提取的SQL
        import re
        extracted_sql = extract_last_tag_content(sql_response, "sql")
        if extracted_sql:
            # 修复LLM在中英文之间误加空格的问题，如"事件 ID" -> "事件ID", "触发器 ID" -> "触发器ID"
            # 匹配任何CJK字符后跟空格再跟ASCII字母/数字/下划线的情况，移除中间空格
            extracted_sql = re.sub(
                r'([一-鿿㐀-䶿豈-﫿])\s+([A-Za-z0-9_])',
                r'\1\2',
                extracted_sql,
            )
        else:
            logger.error(f"未能从LLM响应中提取SQL: {sql_response[-500:]}")
            extracted_sql = sql_response  # 兜底：用原始响应
        yield None, extracted_sql  # 使用None标记结束，并返回提取的SQL

    async def generate_embedding(self, text: str) -> list[float]:
        """生成文本向量"""
        self.client.base_url = 'https://api.siliconflow.cn/v1' #TODO temp
        response = await self.client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=text,
            encoding_format="float",
            extra_authorization_key=settings.EMBEDDING_MODEL_KEY,
        )
        return response.data[0].embedding

    def generate_data_analysis(self, query_result: dict[str, Any]) -> str:
        """生成数据推理分析"""
        from utils.helpers import dict_to_markdown_table
        return dict_to_markdown_table(query_result)


# 创建全局LLM服务实例
llm_service = LLMService()
