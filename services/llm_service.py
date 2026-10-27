from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncGenerator, Iterable
from datetime import datetime

import openai

from services.custom_openai import CAsyncOpenAI
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam

from config import settings
from logg import logger

# 中文标识符与紧跟其后的 SQL 关键字之间必须保留空格，如 考勤状态 IN ('缺勤')；
# 若被拼成 考勤状态IN，数据库会把整体当成列名并报 Undefined column。
_SQL_KEYWORDS = frozenset({
    "AND", "OR", "NOT", "IN", "IS", "LIKE", "ILIKE", "BETWEEN", "AS", "ON",
    "WHERE", "SELECT", "FROM", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER",
    "FULL", "CROSS", "GROUP", "ORDER", "BY", "HAVING", "LIMIT", "OFFSET",
    "UNION", "ALL", "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END",
    "NULL", "TRUE", "FALSE", "ASC", "DESC", "EXISTS", "ANY", "SOME", "WITH",
    "OVER", "PARTITION", "INTERVAL", "ESCAPE", "SIMILAR", "TO", "AT", "ZONE",
    "FILTER", "WITHIN", "RECURSIVE", "LATERAL", "USING", "NATURAL", "ISNULL",
})

# 网关故障是间歇性的（pod 重启、上游读超时、瞬时 404），一次抖动不该让整个查询失败。
# 非流式调用失败后重试，流式调用只对"拿到流之前"的失败重试。
_LLM_MAX_RETRIES = 2
_LLM_RETRY_BASE_DELAY = 1.5
# 网关把上游故障包装成 404，这类 404 可以重试；模型名写错的 404 重试也没用
_GATEWAY_TRANSIENT_404_MARKERS = (
    "ISG:",
    "pods failed",
    "request processing failed",
    "Resource Not Found",
)

# 模型后端上下文只有 256K token，超了不会回 400，而是把整组 pod 标成失败、
# 回 404 "request to all pods failed"——看着像网关挂了，其实是历史里那张几千行的
# 结果表格把 prompt 撑爆了。所以发给模型的对话历史必须在这里截断：
# 助手消息会把 results 整张 markdown 表存进历史，一轮几千行轻松上百万字符。
_MAX_HISTORY_CHARS = 60000        # 历史消息总字符预算（约 45K token）
_MAX_HISTORY_MESSAGE_CHARS = 6000  # 单条历史消息上限（超长表格只留开头）
_MAX_CURRENT_MESSAGE_CHARS = 120000  # 当前消息也要兜底（NER 会把表结构塞进最后一条）


class LLMService:
    """大语言模型服务"""

    def __init__(self):
        self.client = CAsyncOpenAI(
            api_key=settings.OPENAI_API_KEY_1,
            base_url=settings.OPENAI_API_BASE_1)

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        """判断异常是否属于网关瞬时故障，值得重试一次。"""
        if isinstance(
            exc,
            (
                openai.APIConnectionError,  # 含 APITimeoutError
                openai.InternalServerError,
                openai.RateLimitError,
            ),
        ):
            return True
        if isinstance(exc, openai.APIStatusError) and exc.status_code in (502, 503, 504):
            return True
        if isinstance(exc, openai.NotFoundError):
            # 网关把上游 pod 故障包装成 404；模型名配错也是 404，但那种重试无意义
            message = str(exc)
            return any(marker in message for marker in _GATEWAY_TRANSIENT_404_MARKERS)
        return False

    async def _retry_async(self, factory, *, what: str):
        """对网关瞬时故障做有限次重试，仍然失败则抛出最后一次异常。"""
        for attempt in range(_LLM_MAX_RETRIES + 1):
            try:
                return await factory()
            except Exception as exc:
                if attempt >= _LLM_MAX_RETRIES or not self._is_retryable_error(exc):
                    raise
                delay = _LLM_RETRY_BASE_DELAY * (attempt + 1)
                logger.warning(
                    f"{what}调用失败（{type(exc).__name__}: {str(exc)[:150]}），"
                    f"{delay:.1f}s 后第 {attempt + 1} 次重试"
                )
                await asyncio.sleep(delay)

    @staticmethod
    def _truncate_history(messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """把发给模型的历史压到上下文能装下。

        最后一条是当前问题（NER 阶段还会被替换成表结构），必须原样保留；
        更早的消息逐条截断、再由新到旧丢弃，直到总量进预算。
        """
        if not messages:
            return messages

        history, current = messages[:-1], dict(messages[-1])
        if len(current.get("content") or "") > _MAX_CURRENT_MESSAGE_CHARS:
            current["content"] = (
                (current["content"])[:_MAX_CURRENT_MESSAGE_CHARS]
                + "\n…（内容过长已截断）"
            )

        trimmed: list[dict[str, str]] = []
        for message in history:
            content = message.get("content") or ""
            if len(content) > _MAX_HISTORY_MESSAGE_CHARS:
                content = (
                    content[:_MAX_HISTORY_MESSAGE_CHARS]
                    + f"\n…（历史消息共 {len(content)} 字，已截断）"
                )
            trimmed.append({**message, "content": content})

        kept: list[dict[str, str]] = []
        total = 0
        for message in reversed(trimmed):
            if kept and total + len(message["content"]) > _MAX_HISTORY_CHARS:
                break
            kept.append(message)
            total += len(message["content"])
        kept.reverse()

        # 丢掉最早的 user 之后可能只剩 assistant 开头，部分 chat template 会拒绝
        while kept and kept[0]["role"] != "user":
            kept.pop(0)

        if len(kept) < len(history):
            logger.info(
                f"历史消息过长已裁剪：{len(history)} -> {len(kept)} 条，"
                f"当前消息 {len(current.get('content') or '')} 字"
            )
        return [*kept, current]

    def prepare_messages(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        sys_prompt: str | None = None,
    ) -> list[dict[str, str]]:
        prepared_messages = [dict(message) for message in messages if message["role"] != "system"]
        prepared_messages = self._truncate_history(prepared_messages)
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
        completion = await self._retry_async(
            lambda: self.client.chat.completions.create(
                model=settings.FLASH_MODEL,
                messages=self.prepare_messages(intent_messages, sys_prompt or INTENT_RECOGNITION),
                stream=False,
                extra_body=dict(chat_template_kwargs=dict(enable_thinking=False)),
                extra_authorization_key=settings.FLASH_MODEL_KEY,
            ),
            what="意图识别",
        )
        llm_output = completion.choices[0].message.content
        if "<考勤>" in llm_output:
            return "attendance"
        elif "<工单>" in llm_output:
            return "bpm"
        elif "<告警>" in llm_output:
            return "alert"
        elif "<资产>" in llm_output:
            return "asset"
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
        yield ("entities", entities)
        yield ("semantic_reply", chunk)
        yield ("final_parsed_query", result)
        """
        from prompts import NER_SYS, DETERMINE_SEMANTICS_SYS
        from source.tables import ATTDN_RAW, BPM_RAW, ALERT_RAW, ASSET_ACTIVE_RAW
        from services.sql_service import sql_service

        original_query = self.get_latest_user_message(messages)
        if intent in ('attendance', 'attdance'):
            table_schemas = ATTDN_RAW
        elif intent == 'alert':
            table_schemas = ALERT_RAW
        elif intent == 'asset':
            table_schemas = ASSET_ACTIVE_RAW
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
        ner_completion = await self._retry_async(
            lambda: self.client.chat.completions.create(
                model=settings.GENERATE_MODEL,
                messages=self.prepare_messages(ner_messages, ner_sys_prompt or NER_SYS),
                stream=False,
                extra_authorization_key=settings.GENERATE_MODEL_KEY,
            ),
            what="NER实体识别",
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

        # 实体单独下发，供润色阶段校验实体是否被模型丢弃
        yield ("entities", entities)

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
        entities: list[str] | None = None,
    ) -> str:
        """润色用户查询

        entities 为 NER 识别出的实体。润色模型偶尔会把实体整体丢掉
        （例如「协同办公系统近三天有什么告警」被润色成「近三天有什么告警」），
        导致后面的 SQL 变成全量查询；这里做兜底校验，丢实体就退回未润色的问题。
        """
        from prompts import POLISH_SYS
        from utils.helpers import extract_last_tag_content

        # 根据意图生成领域描述
        intent_descs = {
            "alert": "设备告警监控领域。只能使用设备告警记录表(view_alert_all)、设备所属单位表(view_alert_organization)、设备所属业务表(view_alert_business)中的字段。单位名称/业务名称等文字条件必须用LIKE模糊匹配（如业务名称 LIKE '%协同办公%'），不要写成等值比较，因为用户的口语名称常与库内正式名称不完全一致。",
            "bpm": "工单流程管理领域。只能使用流程实例表(bpm_maindata/bpm_archiveddata)、流程模型表(bpm_modprocesslist)及其XmlData中的字段。",
            "attendance": "考勤管理领域。优先使用人员考勤记录表视图(imoc_attendance_all)，该视图已按人按天汇总人员、单位、项目、班次和考勤状态，字段为中文：用户名称、单位名称、项目名称、排班名称、班次名称、值班日期、值班时间、打卡时间、考勤状态、是否申诉、是否请假。考勤状态取值是中文：未到岗、早退、缺勤、未签到、正常、迟到早退、迟到、未签退，不要编造absent/late等英文值。用户的口语要保留原意，不要自己推导成\"不为正常\"之类的取反条件：\"没考勤/没打卡\"指当天没有打卡，对应缺勤/未到岗/未签到。只有用户明确要视图里没有的字段（用户ID、手机号、部门ID等）时才使用底表：考勤人员表(imoc_class_user)、排班记录表(imoc_class_duty_user)、打卡记录表(imoc_checkin_user)、排班表(imoc_class_duty)、项目表(imoc_class_project)。底表的考勤状态用status字段，duty_status是英文旧字段，禁止使用。",
            "asset": "资产管理领域。数据按模型分散在 cmdb_asset_<模型ID> 系列表中（每类资产模型一张表），模型与表名的对应关系通过注册表 cmdb_asset_models 查询；字段多为中文，直接使用表结构中的中文字段名。",
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
        # LLM 网关的内容安全策略会间歇性误杀正常请求（同请求约1/3概率返回拦截话术），
        # 被拦时重试；全部被拦则兜底用原始问题，保证润色结果永不为 None
        interception_markers = ("已被拦截", "已被阻塞", "违反公司网络安全")
        content = ""
        for attempt in range(3):
            completion = await self._retry_async(
                lambda: self.client.chat.completions.create(
                    model=settings.POLISH_MODEL,
                    messages=self.prepare_messages(polish_messages, polish_sys),
                    extra_body=dict(chat_template_kwargs=dict(enable_thinking=False)),
                    extra_authorization_key=settings.POLISH_MODEL_KEY,
                ),
                what="润色",
            )
            logger.debug(f"[POLISH QUERY COMPLETION] {completion.model_dump_json()}")
            content = completion.choices[0].message.content or ""
            if not any(marker in content for marker in interception_markers):
                break
            logger.warning(f"润色请求被网关内容安全拦截（第 {attempt + 1} 次），重试...")
        polished_query = extract_last_tag_content(content, "润色后")
        if not polished_query:
            logger.warning(f"润色未返回<润色后>标签（内容: {content[:100]}），回退使用原始查询")
            return latest_user_message

        # 实体保留校验：润色结果丢失任一实体，会让SQL变成无过滤的全量查询
        missing_entities = [
            entity
            for entity in (entities or [])
            if isinstance(entity, str) and entity and entity.lower() not in polished_query.lower()
        ]
        if missing_entities:
            logger.warning(
                f"润色结果丢失实体 {missing_entities}，回退使用未润色的问题: {latest_user_message}"
            )
            return latest_user_message

        # 润色模型偶尔把"没考勤"这类口语自行推理成一串"不为X、不为Y"的排除条件，
        # 语义被改成取反（等于把所有状态都排除掉），SQL 必然查空。
        # 用户原话没有排除意图时，直接退回未润色的问题，交给生成阶段按 ATTENDANCE_NOTE 映射。
        if intent in ("attendance", "attdance"):
            vague_no_checkin = ("没考勤", "未考勤", "没打卡", "未打卡", "没有考勤", "没来")
            exclusion_words = ("除了", "不含", "不包括", "排除", "除去")
            if (
                any(marker in latest_user_message for marker in vague_no_checkin)
                and "不为" in polished_query
                and not any(word in latest_user_message for word in exclusion_words)
            ):
                logger.warning(
                    f"润色结果把口语考勤状态改成了取反条件，回退使用未润色的问题: {latest_user_message}"
                )
                return latest_user_message
        return polished_query

    @staticmethod
    def _load_json_object(text: str) -> dict | None:
        """从模型输出里容错提取一个 JSON 对象（容忍 markdown 代码块和前后废话）。"""
        import json as jsonlib
        import re as regex

        text = (text or "").strip()
        try:
            parsed = jsonlib.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except ValueError:
            pass

        fenced = regex.search(r"```(?:json)?\s*(.*?)```", text, regex.DOTALL)
        if fenced:
            try:
                parsed = jsonlib.loads(fenced.group(1).strip())
                if isinstance(parsed, dict):
                    return parsed
            except ValueError:
                pass

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
        return None

    async def check_ambiguity(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        intent: str,
        table_descs: str,
    ) -> dict | None:
        """判断问题是否存在会改变 SQL 结果的口径歧义。

        返回 {"question": str, "options": [{"label","value","description"}, ...]}
        表示需要先让用户选口径；返回 None 表示没有歧义，正常往下走。
        """
        from prompts import AMBIGUITY_CHECK_SYS

        latest_user_message = self.get_latest_user_message(messages)
        user_block = (
            f"<领域>{intent}</领域>\n"
            f"<可用表>\n{table_descs}\n</可用表>\n"
            f"<用户问题>\n{latest_user_message}\n</用户问题>"
        )
        check_messages = self.replace_latest_user_message(messages, user_block)
        completion = await self._retry_async(
            lambda: self.client.chat.completions.create(
                model=settings.FLASH_MODEL,
                messages=self.prepare_messages(check_messages, AMBIGUITY_CHECK_SYS),
                temperature=0,
                extra_body=dict(chat_template_kwargs=dict(enable_thinking=False)),
                extra_authorization_key=settings.FLASH_MODEL_KEY,
            ),
            what="口径歧义检测",
        )
        content = completion.choices[0].message.content or ""
        logger.debug(f"[AMBIGUITY CHECK] {content[:600]}")

        data = self._load_json_object(content)
        if not data or not data.get("ambiguous"):
            return None

        question = str(data.get("question") or "").strip()
        options = []
        for item in (data.get("options") or []):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not label:
                continue
            options.append({
                "label": label,
                "value": str(item.get("value") or label).strip(),
                "description": str(item.get("description") or "").strip(),
            })

        # 选项少于 2 个就构不成"让用户选"，宁可继续查也不要问一个没法选的问题
        if not question or len(options) < 2:
            logger.warning(
                f"歧义检测结果不完整（question={bool(question)}, 选项数={len(options)}），按无疑义处理"
            )
            return None

        return {"question": question, "options": options[:4]}

    async def is_clarification_answer(
        self,
        question: str,
        options: list[dict],
        user_reply: str,
    ) -> bool | None:
        """判断用户这句话是在回答上一轮的口径澄清，还是另提了一个新问题。

        返回 True/False；模型没给出可解析结果时返回 None，由调用方兜底。
        把新问题当成口径去查会算出错误的数字，所以这里宁可判成新问题。
        """
        from prompts import CLARIFICATION_REPLY_SYS

        option_lines = []
        for index, option in enumerate(options):
            letter = chr(ord("A") + index)
            description = (option.get("description") or "").strip()
            suffix = f"（{description}）" if description else ""
            option_lines.append(f"({letter}) {option.get('label', '')}{suffix}")

        sys_prompt = CLARIFICATION_REPLY_SYS.format(
            question=question,
            options="\n".join(option_lines),
        )
        completion = await self._retry_async(
            lambda: self.client.chat.completions.create(
                model=settings.FLASH_MODEL,
                messages=self.prepare_messages(
                    [{"role": "user", "content": f"<用户消息>\n{user_reply}\n</用户消息>"}],
                    sys_prompt,
                ),
                temperature=0,
                extra_body=dict(chat_template_kwargs=dict(enable_thinking=False)),
                extra_authorization_key=settings.FLASH_MODEL_KEY,
            ),
            what="澄清回答判定",
        )
        content = completion.choices[0].message.content or ""
        logger.debug(f"[CLARIFICATION REPLY CHECK] {content[:300]}")

        data = self._load_json_object(content)
        if not isinstance(data, dict) or "is_answer" not in data:
            return None
        return bool(data.get("is_answer"))

    async def ask_llm(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        *,
        enable_thinking: bool = False,
        sys_prompt: str | None = None,
        model: str | None = None,
        authorization_key: str | None = None,
        temperature: float = 0.0,
    ):
        prepared_messages = self.prepare_messages(messages, sys_prompt)
        extra_body=dict(chat_template_kwargs=dict(enable_thinking=enable_thinking))
        self.client.base_url = settings.OPENAI_API_BASE_1
        # 只对"拿到流之前"的失败重试；流开始后再出错只能由上层处理，避免重复输出
        completion = await self._retry_async(
            lambda: self.client.chat.completions.create(
                model=model or settings.GENERATE_MODEL,
                messages=prepared_messages,
                # 用 0 而不是 0.7：同一个问题必须生成同一条 SQL，
                # 否则同一句话问两次会得到两个不同的数，用户没法信这个系统。
                temperature=temperature,
                extra_body=extra_body,
                stream=True,
                extra_authorization_key=authorization_key or settings.GENERATE_MODEL_KEY,
            ),
            what="SQL生成",
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
            # 只处理"中文+英文"组成同一个标识符的情况；若后面跟的是 SQL 关键字
            # （IN/NOT IN/AND/LIKE/AS/ORDER BY 等），空格是语法分隔符，必须保留
            extracted_sql = re.sub(
                r'([一-鿿㐀-䶿豈-﫿])\s+([A-Za-z0-9_]+)',
                lambda m: m.group(0) if m.group(2).upper() in _SQL_KEYWORDS else f"{m.group(1)}{m.group(2)}",
                extracted_sql,
            )
            # 修复LLM在中文字符之间误加空格的问题，如"设备 型号" -> "设备型号"
            # 仅匹配双引号标识符内部，避免误改字符串字面量里的中文值（如 LIKE '%动力 机房%'）
            extracted_sql = re.sub(
                r'("[一-鿿][^"]*?)\s+([^"]*?[一-鿿]")',
                r'\1\2',
                extracted_sql,
            )
        else:
            logger.error(f"未能从LLM响应中提取SQL: {sql_response[-500:]}")
            extracted_sql = sql_response  # 兜底：用原始响应
        yield None, extracted_sql  # 使用None标记结束，并返回提取的SQL

    async def generate_asset_query(
        self,
        messages: Iterable[ChatCompletionMessageParam | dict[str, str]],
        sys_prompt: str | None = None,
        enable_thinking: bool = False,
    ):
        """生成资产查询参数（CMDB 直查模式，流式响应）- 返回异步生成器

        产出文本 chunk，最后 yield (None, 提取出的查询参数文本)。
        """
        from utils.helpers import extract_last_tag_content

        response_text = ""
        agen = self.ask_llm(messages, sys_prompt=sys_prompt, enable_thinking=enable_thinking)
        async for content in agen:
            response_text += content
            yield content

        extracted_params = extract_last_tag_content(response_text, "query_params")
        if not extracted_params:
            logger.error(f"未能从LLM响应中提取查询参数: {response_text[-500:]}")
            extracted_params = response_text  # 兜底：用原始响应
        yield None, extracted_params

    async def generate_embedding(self, text: str) -> list[float]:
        """生成文本向量"""
        response = await self._retry_async(
            lambda: self.client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text,
                encoding_format="float",
                extra_authorization_key=settings.EMBEDDING_MODEL_KEY,
            ),
            what="向量生成",
        )
        return response.data[0].embedding

    def generate_data_analysis(self, query_result: dict[str, Any]) -> str:
        """生成数据推理分析"""
        from utils.helpers import dict_to_markdown_table
        return dict_to_markdown_table(query_result)


# 创建全局LLM服务实例
llm_service = LLMService()
