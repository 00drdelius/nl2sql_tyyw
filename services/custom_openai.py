import array
import base64
from typing import *
from typing_extensions import override

import numpy as np

import httpx
from httpx import Timeout

from openai._types import Body, Omit, Query, Headers, NotGiven, SequenceNotStr, omit, not_given
from openai._streaming import AsyncStream
from openai._base_client import make_request_options

from openai.types.embedding_model import EmbeddingModel
from openai.types.create_embedding_response import CreateEmbeddingResponse
from openai.types import embedding_create_params

from openai.types.shared.chat_model import ChatModel
from openai.types.chat import completion_create_params, completion_update_params
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.shared_params.metadata import Metadata
from openai.types.shared.reasoning_effort import ReasoningEffort
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.chat.chat_completion_audio_param import ChatCompletionAudioParam
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_union_param import ChatCompletionToolUnionParam
from openai.types.chat.chat_completion_stream_options_param import ChatCompletionStreamOptionsParam
from openai.types.chat.chat_completion_prediction_content_param import ChatCompletionPredictionContentParam
from openai.types.chat.chat_completion_tool_choice_option_param import ChatCompletionToolChoiceOptionParam



from openai._compat import cached_property
from openai._extras.numpy_proxy import has_numpy
from openai._utils import required_args, async_maybe_transform, maybe_transform, is_given

from openai import AsyncOpenAI
from openai.resources.embeddings import AsyncEmbeddings
from openai.resources.chat import AsyncChat
from openai.resources.chat.completions import AsyncCompletions
from openai.resources.chat.completions.completions import validate_response_format


MODELNAME_MAPPER={
    "Qwen3-30B-A3B-Instruct-2507": "qwen3-30b-a3b",
    "Qwen3.5-397B-A17B": "qwen3-5-397b-a17b",
}


def join_full_url_and_get_extra_headers(
    _client:AsyncOpenAI,
    model:str,
    entrypoint_path_prefix:str = '/online/v1',
    entrypoint_path:str = '/chat/completions',
    extra_headers:dict|None = None,
    extra_authorization_key:str=None,
):
    """
    To convert base_url to process the frustrated model_name-in-url💩💩💩.
    Returns:
        out: the first full_url canbe like: <_client.base_url>/<model_name>/<entrypoint_path_prefix>/<entrypoint_path>,
            Like: "http://19.119.245.78/ebus/msmp/qwen3.5-27b/online/v1/chat/completions"
    """
    base = str(_client.base_url).rstrip("/")

    if _client.base_url.path.startswith("/v1"):
        full_url = f"{base}{entrypoint_path}"
    else:
        model_name = MODELNAME_MAPPER.get(model, model.lower())
        full_url = f"{base}/{model_name}{entrypoint_path_prefix}{entrypoint_path}"

    if extra_authorization_key is not not_given and extra_authorization_key is not None:
        auth_header = {"Authorization": f"Bearer {extra_authorization_key}"}
        extra_headers = {**(extra_headers or {}), **auth_header}

    return full_url, extra_headers


class CAsyncCompletions(AsyncCompletions):
    def __init__(self, client):
        super().__init__(client)

    @override
    @required_args(["messages", "model"], ["messages", "model", "stream"])
    async def create(
        self,
        *,
        messages: Iterable[ChatCompletionMessageParam],
        model: Union[str, ChatModel],
        audio: Optional[ChatCompletionAudioParam] | Omit = omit,
        frequency_penalty: Optional[float] | Omit = omit,
        function_call: completion_create_params.FunctionCall | Omit = omit,
        functions: Iterable[completion_create_params.Function] | Omit = omit,
        logit_bias: Optional[Dict[str, int]] | Omit = omit,
        logprobs: Optional[bool] | Omit = omit,
        max_completion_tokens: Optional[int] | Omit = omit,
        max_tokens: Optional[int] | Omit = omit,
        metadata: Optional[Metadata] | Omit = omit,
        modalities: Optional[List[Literal["text", "audio"]]] | Omit = omit,
        n: Optional[int] | Omit = omit,
        parallel_tool_calls: bool | Omit = omit,
        prediction: Optional[ChatCompletionPredictionContentParam] | Omit = omit,
        presence_penalty: Optional[float] | Omit = omit,
        prompt_cache_key: str | Omit = omit,
        prompt_cache_retention: Optional[Literal["in-memory", "24h"]] | Omit = omit,
        reasoning_effort: Optional[ReasoningEffort] | Omit = omit,
        response_format: completion_create_params.ResponseFormat | Omit = omit,
        safety_identifier: str | Omit = omit,
        seed: Optional[int] | Omit = omit,
        service_tier: Optional[Literal["auto", "default", "flex", "scale", "priority"]] | Omit = omit,
        stop: Union[Optional[str], SequenceNotStr[str], None] | Omit = omit,
        store: Optional[bool] | Omit = omit,
        stream: Optional[Literal[False]] | Literal[True] | Omit = omit,
        stream_options: Optional[ChatCompletionStreamOptionsParam] | Omit = omit,
        temperature: Optional[float] | Omit = omit,
        tool_choice: ChatCompletionToolChoiceOptionParam | Omit = omit,
        tools: Iterable[ChatCompletionToolUnionParam] | Omit = omit,
        top_logprobs: Optional[int] | Omit = omit,
        top_p: Optional[float] | Omit = omit,
        user: str | Omit = omit,
        verbosity: Optional[Literal["low", "medium", "high"]] | Omit = omit,
        web_search_options: completion_create_params.WebSearchOptions | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,

        #NOTE
        extra_authorization_key: str | None | NotGiven = not_given,
    ) -> ChatCompletion | AsyncStream[ChatCompletionChunk]:
        validate_response_format(response_format)

        full_url, extra_headers = join_full_url_and_get_extra_headers(
            self._client, model=model,
            entrypoint_path_prefix='/online/v1',
            entrypoint_path='/chat/completions',
            extra_headers=extra_headers,
            extra_authorization_key=extra_authorization_key,
        )

        return await self._post(
            full_url, #NOTE multi clients share identical self._client.base_url, which induces race condition in concurrent mode.
            body=await async_maybe_transform(
                {
                    "messages": messages,
                    "model": model,
                    "audio": audio,
                    "frequency_penalty": frequency_penalty,
                    "function_call": function_call,
                    "functions": functions,
                    "logit_bias": logit_bias,
                    "logprobs": logprobs,
                    "max_completion_tokens": max_completion_tokens,
                    "max_tokens": max_tokens,
                    "metadata": metadata,
                    "modalities": modalities,
                    "n": n,
                    "parallel_tool_calls": parallel_tool_calls,
                    "prediction": prediction,
                    "presence_penalty": presence_penalty,
                    "prompt_cache_key": prompt_cache_key,
                    "prompt_cache_retention": prompt_cache_retention,
                    "reasoning_effort": reasoning_effort,
                    "response_format": response_format,
                    "safety_identifier": safety_identifier,
                    "seed": seed,
                    "service_tier": service_tier,
                    "stop": stop,
                    "store": store,
                    "stream": stream,
                    "stream_options": stream_options,
                    "temperature": temperature,
                    "tool_choice": tool_choice,
                    "tools": tools,
                    "top_logprobs": top_logprobs,
                    "top_p": top_p,
                    "user": user,
                    "verbosity": verbosity,
                    "web_search_options": web_search_options,
                },
                completion_create_params.CompletionCreateParamsStreaming
                if stream
                else completion_create_params.CompletionCreateParamsNonStreaming,
            ),
            options=make_request_options(
                extra_headers=extra_headers, extra_query=extra_query, extra_body=extra_body, timeout=timeout
            ),
            cast_to=ChatCompletion,
            stream=stream or False,
            stream_cls=AsyncStream[ChatCompletionChunk],
        )


class CAsyncChat(AsyncChat):
    def __init__(self, client):
        super().__init__(client)

    @cached_property
    def completions(self) -> CAsyncCompletions:
        return CAsyncCompletions(self._client)


class CAsyncEmbeddings(AsyncEmbeddings):
    def __init__(self, client):
        super().__init__(client)
    
    @override
    async def create(
        self,
        *,
        input: Union[str, SequenceNotStr[str], Iterable[int], Iterable[Iterable[int]]],
        model: Union[str, EmbeddingModel],
        dimensions: int | Omit = omit,
        encoding_format: Literal["float", "base64"] | Omit = omit,
        user: str | Omit = omit,
        # Use the following arguments if you need to pass additional parameters to the API that aren't available via kwargs.
        # The extra values given here take precedence over values defined on the client or passed to this method.
        extra_headers: Headers | None = None,
        extra_query: Query | None = None,
        extra_body: Body | None = None,
        timeout: float | httpx.Timeout | None | NotGiven = not_given,

        #NOTE
        extra_authorization_key: str | None | NotGiven = not_given,
    ) -> CreateEmbeddingResponse:
        params = {
            "input": input,
            "model": model,
            "user": user,
            "dimensions": dimensions,
            "encoding_format": encoding_format,
        }
        if not is_given(encoding_format):
            params["encoding_format"] = "base64"

        def parser(obj: CreateEmbeddingResponse) -> CreateEmbeddingResponse:
            if is_given(encoding_format):
                # don't modify the response object if a user explicitly asked for a format
                return obj

            if not obj.data:
                raise ValueError("No embedding data received")

            for embedding in obj.data:
                data = cast(object, embedding.embedding)
                if not isinstance(data, str):
                    continue
                if not has_numpy():
                    # use array for base64 optimisation
                    embedding.embedding = array.array("f", base64.b64decode(data)).tolist()
                else:
                    embedding.embedding = np.frombuffer(  # type: ignore[no-untyped-call]
                        base64.b64decode(data), dtype="float32"
                    ).tolist()

            return obj


        full_url, extra_headers = join_full_url_and_get_extra_headers(
            self._client, model=model,
            entrypoint_path_prefix='/online/v1',
            entrypoint_path='/embeddings',
            extra_headers=extra_headers,
            extra_authorization_key=extra_authorization_key,
        )

        return await self._post(
            full_url,
            body=maybe_transform(params, embedding_create_params.EmbeddingCreateParams),
            options=make_request_options(
                extra_headers=extra_headers,
                extra_query=extra_query,
                extra_body=extra_body,
                timeout=timeout,
                post_parser=parser,
            ),
            cast_to=CreateEmbeddingResponse,
        )

DEFAULT_MAX_RETRIES=2

class CAsyncOpenAI(AsyncOpenAI):
    def __init__(
        self,
        *,
        api_key: str | Callable[[], Awaitable[str]] | None = None,
        organization: str | None = None,
        project: str | None = None,
        webhook_secret: str | None = None,
        base_url: str | httpx.URL | None = None,
        websocket_base_url: str | httpx.URL | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        # Configure a custom httpx client.
        # We provide a `DefaultAsyncHttpxClient` class that you can pass to retain the default values we use for `limits`, `timeout` & `follow_redirects`.
        # See the [httpx documentation](https://www.python-httpx.org/api/#asyncclient) for more details.
        http_client: httpx.AsyncClient | None = None,
        # Enable or disable schema validation for data returned by the API.
        # When enabled an error APIResponseValidationError is raised
        # if the API responds with invalid data for the expected schema.
        #
        # This parameter may be removed or changed in the future.
        # If you rely on this feature, please open a GitHub issue
        # outlining your use-case to help us decide if it should be
        # part of our public interface in the future.
        _strict_response_validation: bool = False,
        ) -> None:
        super().__init__(
            api_key=api_key,
            organization=organization,
            project=project,
            webhook_secret=webhook_secret,
            base_url=base_url,
            websocket_base_url=websocket_base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            default_query=default_query,
            http_client=http_client,
            _strict_response_validation=_strict_response_validation
        )
    
    @override
    @cached_property
    def chat(self) -> CAsyncChat:
        return CAsyncChat(self)
    
    @override
    @cached_property
    def embeddings(self) -> CAsyncEmbeddings:
        return CAsyncEmbeddings(self)

messages=[{'role': 'system', 'content': '你是一名MySQL语言专家。我会提供给你用户自然语言查询问题（<用户查询>）与缓存的SQL语句模板（<SQL缓存模板>），\n我需要你根据我提供的信息，判断是否有合适的<SQL缓存模板>、并根据模板输出结果。\n\n# 具体步骤\n1. 判断是否有<SQL缓存模板>能满足回答<用户问题>：\n  - 若有：缓存命中，跳转至点2\n  - 若没有：跳转至点3\n2. 提取出该模板，根据下面的命中生成要求（<命中时要求>）生成MySQL可执行的查询语句\n3. 根据下面的未命中生成要求（<未命中时要求>）生成MySQL可执行的查询语句\n\n## 命中时要求\n1. 命中时一般只需要你修改对应语句模板内"BETWEEN <datetime1> AND <datetime2>"的时间（注意时间遵循格式: "%Y-%m-%d"）、或者新增关键词过滤即可（"CASE ... WHEN ... AS ..."）\n2. 若需要在模板基础上新增查询的列，非中文时用"AS"语句转中文，也要注意中文字段要用英文双引号"""裹住\n3. 最终结果请用xml标签"<sql>"裹住，且只允许放可以执行的sql语句，不允许添加注释\n\n## 未命中时要求\n1. 请根据提供的表结构信息（<相关数据表结构>）与注意事项（<注意事项>）生成语句\n2. 禁止使用子查询\n3. 字段名若是英文，请用"AS"语句转成中文。也要注意中文字段要用英文双引号"""裹住\n4. 最终结果也请用xml标签"<sql>"裹住，且只允许放可以执行的sql语句，不允许添加注释\n\n\n# 今日时间\n2026-05-25, Monday\n\n# SQL缓存模板\n<SQL缓存模板1>\n# 查询特定时间用户异常考勤的条目\n```sql\nSELECT \n\t"用户名称", "单位名称", "排班名称", "值班日期", "考勤状态", "是否申诉", "是否请假" \nFROM imoc_attendance_all \nWHERE "考勤状态" != \'正常\' AND "值班日期" BETWEEN <dateime1> AND <datetime2>;\n```\n</SQL缓存模板1>\n\n<SQL缓存模板2>\n# 统计特定时间考勤异常用户数，根据用户提问添加关键字过滤\n```sql\nSELECT \n\t"排班名称", \n\tcount(1) AS "总人数", \n\tSUM(CASE WHEN "考勤状态" = \'迟到\' THEN 1 ELSE 0 END ) AS "迟到数",\n\tSUM(CASE WHEN "考勤状态" = \'未签退\' THEN 1 ELSE 0 END ) AS "未签退数",\n\tSUM(CASE WHEN "考勤状态" = \'早退\' THEN 1 ELSE 0 END ) AS "早退数",\n\tSUM(CASE WHEN "考勤状态" = \'缺勤\' THEN 1 ELSE 0 END ) AS "缺勤数" \nFROM imoc_attendance_all \nWHERE "考勤状态" != \'正常\' AND "值班日期" BETWEEN <dateime1> AND <dateime2> AND "排班名称" LIKE \'%%\'\nGROUP BY "排班名称";\n```\n</SQL缓存模板2>\n\n<SQL缓存模板3>\n# 统计特定时间段内考勤用户考勤状态数量，根据用户提问替换时间段，根据用户提问添加关键字过滤\n```sql\nSELECT \n\t"值班日期", \n\tcount(1) AS "总人数", \n\tSUM(CASE WHEN "考勤状态" = \'正常\' THEN 1 ELSE 0 END ) AS "正常数",\n\tSUM(CASE WHEN "考勤状态" = \'迟到\' THEN 1 ELSE 0 END ) AS "迟到数",\n\tSUM(CASE WHEN "考勤状态" = \'未签退\' THEN 1 ELSE 0 END ) AS "未签退数",\n\tSUM(CASE WHEN "考勤状态" = \'早退\' THEN 1 ELSE 0 END ) AS "早退数",\n\tSUM(CASE WHEN "考勤状态" = \'缺勤\' THEN 1 ELSE 0 END ) AS "缺勤数"\nFROM imoc_attendance_all \nWHERE "值班日期" BETWEEN <dateime1> AND <dateime2>\n\tAND "排班名称" LIKE \'%%\'\nGROUP BY "值班日期" ;\n```\n</SQL缓存模板3>\n\n<SQL缓存模板4>\n# 根据特定的时间段查出工单记录，按用户需求调整时间段\n```sql\nselect \n\twf_docnumber as "工单编号",`subject` as \'工单标题\',nodename as "工单类型", wf_addname_cn as 申请人,wf_doccreated as 开始时间, wf_endtime as 结束时间, \n\tcase when wf_status=\'Current\' then \'流转中\' when wf_status=\'ARC\' then \'已结束\' else wf_status end as 状态,\n \tExtractValue(xmldata,\'/Items/WFItem[@name="reporter"]\') as "报单人",\n \tcase ExtractValue(xmldata,\'/Items/WFItem[@name="reportType"]\') when \'0\' then \'服务台报障\' when \'1\' then \'电话报障\' when \'2\' then \'自行报障\' when \'4\' then \'现场报障\' else ExtractValue(xmldata,\'/Items/WFItem[@name="reportType"]\') end as "申请途径",\n \tcase ExtractValue(xmldata,\'/Items/WFItem[@name="unit_show"]\') when \'\' then ExtractValue(xmldata,\'/Items/WFItem[@name="unit"]\') else ExtractValue(xmldata,\'/Items/WFItem[@name="unit_show"]\') end as "单位",\n \tcase ExtractValue(xmldata,\'/Items/WFItem[@name="dept_show"]\') when \'\' then ExtractValue(xmldata,\'/Items/WFItem[@name="dept"]\') else ExtractValue(xmldata,\'/Items/WFItem[@name="dept_show"]\') end as "科室",\n \tExtractValue(xmldata,\'/Items/WFItem[@name="phone"]\') as "联系电话",\n \tcase ExtractValue(xmldata,\'/Items/WFItem[@name="urgency_show"]\') when \'\' then ExtractValue(xmldata,\'/Items/WFItem[@name="urgency"]\') else ExtractValue(xmldata,\'/Items/WFItem[@name="urgency_show"]\') end as "急紧程度",\n \tcase ExtractValue(xmldata,\'/Items/WFItem[@name="project_show"]\') when \'\' then ExtractValue(xmldata,\'/Items/WFItem[@name="project"]\') else ExtractValue(xmldata,\'/Items/WFItem[@name="project_show"]\') end as "所属项目",\n \tcase ExtractValue(xmldata,\'/Items/WFItem[@name="subproject_show"]\') when \'\' then ExtractValue(xmldata,\'/Items/WFItem[@name="subproject"]\') else ExtractValue(xmldata,\'/Items/WFItem[@name="subproject_show"]\') end as "子项目",\n \tcase ExtractValue(xmldata,\'/Items/WFItem[@name="errorType_show"]\') when \'\' then ExtractValue(xmldata,\'/Items/WFItem[@name="errorType"]\') else ExtractValue(xmldata,\'/Items/WFItem[@name="errorType_show"]\') end as "故障或需求类型",\n \tExtractValue(xmldata,\'/Items/WFItem[@name="reportTime"]\') as "故障或需求时间",\n  replace(replace(ExtractValue(xmldata,\'/Items/WFItem[@name="reportDetail"]\'),char(10),\'\'),char(13),\'\') as "详情"\nfrom \n(select p.nodename,m.*\nfrom bpm_archiveddata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid\nwhere m.wf_processid!=\'65590215080f9044140a1490ba3122264aa5\' and date(ExtractValue(m.xmldata,\'/Items/WFItem[@name="reportTime"]\')) between <datetime1> and <datetime2>\nunion all \nselect p.nodename,m.*\nfrom bpm_maindata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid\nwhere m.wf_processid!=\'65590215080f9044140a1490ba3122264aa5\' and date(ExtractValue(m.xmldata,\'/Items/WFItem[@name="reportTime"]\')) between <datetime1> and <datetime2>) process;\n```\n</SQL缓存模板4>\n\n<SQL缓存模板5>\n# 根据特定的时间段按特定字段统计工单数量\n```sql\nselect \n \tcase ExtractValue(xmldata,\'/Items/WFItem[@name="unit_show"]\') when \'\' then ExtractValue(xmldata,\'/Items/WFItem[@name="unit"]\') else ExtractValue(xmldata,\'/Items/WFItem[@name="unit_show"]\') end as "单位",\n\tsum(case wf_status when \'Current\' then 1 else 0 end) "流转中数量",\n\tsum(case wf_status when \'ARC\' then 1 else 0 end) "已完结数量",\n\tsum(case wf_status when \'dratf\' then 1 else 0 end) "草稿数量",\n\tcount(1) "总工单量"\nfrom \n(select p.nodename,m.*\nfrom bpm_archiveddata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid\nwhere m.wf_processid!=\'65590215080f9044140a1490ba3122264aa5\' and date(ExtractValue(m.xmldata,\'/Items/WFItem[@name="reportTime"]\')) between <datetime1> and <datetime2>\nunion all \nselect p.nodename,m.*\nfrom bpm_maindata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid\nwhere m.wf_processid!=\'65590215080f9044140a1490ba3122264aa5\' and date(ExtractValue(m.xmldata,\'/Items/WFItem[@name="reportTime"]\')) between <datetime1> and <datetime2>) process\ngroup by case ExtractValue(xmldata,\'/Items/WFItem[@name="unit_show"]\') when \'\' then ExtractValue(xmldata,\'/Items/WFItem[@name="unit"]\') else ExtractValue(xmldata,\'/Items/WFItem[@name="unit_show"]\') end ;\n```\n\n</SQL缓存模板5>\n# 相关数据表结构\n# 数据表1\n表名：imoc_attendance_all: 人员考勤记录表，用于记录人员每日打卡记录，包含考勤状态及申诉、请假标识。\n表字段：\n用户名称: 用户姓名，标识打卡用户\n单位名称: 用户所属单位名称\n项目名称: 用户所属项目名称\n排班名称: 排班规则名称\n班次名称: 具体班次名称\n值班日期: 值班的具体日期\n值班时间: 值班时间范围描述\n打卡时间: 实际打卡时间记录\n考勤状态: 考勤结果状态，其中早退、未签退、缺勤、迟到为考勤异常状态\n是否申诉: 标识该记录是否发起申诉\n是否请假: 标识该记录是否关联请假\n\n\n# 数据表2\n表名：imoc_class_appeal: 考勤申诉表，用于异常考勤的申诉处理，申诉通过后可订正为正常状态。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nduty_id: 值班ID，关联值班表，标识申诉对应的值班记录\ntype: 类型，记录申诉类型\nstart_time: 开始时间，记录申诉开始时间\nend_time: 结束时间，记录申诉结束时间\nreson: 请假原因，记录申诉原因\npic_url: 请假图片，记录申诉相关的图片URL\nstatus: 状态，记录申诉状态\nreject_reson: 拒绝理由，记录拒绝申诉的理由\ngov_reject_reson: 业主拒绝理由，记录业主拒绝申诉的理由\ncreate_userid: 申请人uid，记录申诉申请人\ncreate_time: 申请时间，记录申诉申请时间戳\nupdate_time: 更新时间，记录最后更新时间戳\napprove_user: 审批人员，记录审批人姓名\napprove_userid: 审批人ID，记录审批人ID\napprove_time: 审批时间，记录审批时间戳\ngov_approve_user: 业主审批人员，记录业主审批人姓名\ngov_approve_userid: 业主审批人ID，记录业主审批人ID\ngov_approve_time: 业主审批时间，记录业主审批时间戳\nis_del: 是否删除，标识数据是否已删除\n\n\n# 数据表3\n表名：imoc_checkin_user: 考勤人员打卡记录表，用于记录人员的每一次打卡记录，反映员工考勤情况。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nuserid: 用户ID，关联用户表，标识打卡人员\nproject_id: 项目ID，关联项目表，标识打卡所属项目\nduty_id: 排班ID，关联排班表，标识打卡对应的排班\nclass_id: 班次ID，关联班次表，标识打卡对应的班次\nrange_id: 时间段ID，关联时间段表，标识打卡对应的时间段\nrelated_id: 关联duty_user的ID，用于关联人员排班记录\ntype: 类型，标识打卡类型\nrange_start_time: 考勤上班时间，记录规定的上班时间\nrange_end_time: 考勤下班时间，记录规定的下班时间\ntertian: 是否隔日，标识是否跨天\nduty_date: 值班日期，记录具体的值班日期\nduty_location: 值班打卡位置，记录规定的打卡位置\nlocation: 实际打卡位置，记录实际打卡的位置\nlng: 经度，记录打卡位置的经度坐标\nlat: 纬度，记录打卡位置的纬度坐标\nstatus: 状态，记录打卡状态\ncreate_time: 创建时间，记录创建时间戳\nupdate_time: 更新时间，记录最后更新时间戳\nis_del: 是否删除，标识数据是否已删除\nis_manual: 是否手动签到，标识是否为手动签到记录\n\n\n# 数据表4\n表名：imoc_class: 考勤班次表，用于配置考勤班次，定义班次基本信息和规则。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nname: 班次名称，标识班次的名称\nendure_minutes: 容忍时间，记录打卡容忍的时间范围（分钟）\ninfo: 说明，记录班次的补充说明信息\ncreate_time: 创建时间，记录创建时间戳\ncreate_userid: 创建用户ID，记录创建该班次的用户\nupdate_time: 更新时间，记录最后更新时间戳\nupdate_userid: 更新用户ID，记录最后更新该班次的用户\nis_del: 是否删除，标识数据是否已删除\n\n\n# 数据表5\n表名：imoc_class_range: 考勤班次时段表，记录每个班次的多个上班时间段。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nclass_id: 班次ID，关联班次表，标识所属班次\nstart_time: 开始时间，记录时段开始时间\nend_time: 结束时间，记录时段结束时间\ntertian: 是否隔日，标识是否跨天\n\n# 注意事项\n1. 若是查询到表"imoc_attendance_all"(其实是视图)，思考是否可用于解决用户问题，若可以，优先使用这个视图。注意这个视图字段设置为了全中文，直接用中文字段查询即可\n\n\n# 最终输出模板\n<sql>\n<完整SQL语句>\n</sql>\n'}, {'role': 'user', 'content': '用户查询：\n请列出最近5次考勤异常的记录，包括人员姓名、所属单位、项目名称、排班名称、班次名称、值班日期、值班时间、实际打卡时间、考勤状态以及是否已发起申诉或请假等信息，按时间倒序排列，仅显示最近5条异常记录。\n'}]

async def test():
    import sys
    #NOTE 尽量别用 non-stream mode。。。运通api会返回是非标准字段`provider_specific_fields`
    client = CAsyncOpenAI(
        api_key="isg-tyyw-e35f2f75cb0d4c88af1d01f3838e3ad8",
        base_url="http://19.119.245.78/ebus/msmp",
    )
    stream=False
    for _ in range(2):
        completions = await client.chat.completions.create(
            # model="Qwen3-30B-A3B-Instruct-2507",
            model="Qwen3.5-397B-A17B",
            messages=[{"role":"user",'content':'50个字锐评下百度这家公司。'}],
            # messages=messages,
            extra_body=dict(chat_template_kwargs=dict(enable_thinking=False)),
            extra_authorization_key="isg-tyyw-e35f2f75cb0d4c88af1d01f3838e3ad8",
            stream=stream
        )
        import rich
        if not stream:
            rich.print("chat completions:")
            rich.print(completions)
        else:
            rich.print("chat completions:")
            for chunk in completions:
                rich.print(chunk)

    embd_resp = await client.embeddings.create(
        input="test "*10,
        model = "Qwen3-Embedding-4B",
        encoding_format='float',
        extra_authorization_key="isg-tyyw-d039ac95de5b4a44be9cf43af3c9ac97",
    )
    embd_resp.data[0].embedding = embd_resp.data[0].embedding[:20]
    rich.print("embeddings")
    rich.print(embd_resp)


def test2():
    import requests
    import rich
    payload={
        "model":"Qwen3.5-397B-A17B",
        "messages":messages,
        "chat_template_kwargs":{"enable_thinking":False},
    }
    url="http://19.119.245.78/ebus/msmp/qwen3-5-397b-a17b/online/v1/chat/completions"
    headers={"Authorization":"Bearer isg-tyyw-e35f2f75cb0d4c88af1d01f3838e3ad8"}
    # url="http://19.119.245.93:4000/v1/chat/completions"
    # headers={"Authorization":"Bearer sk-fX8gjKtTsoCmuNj_6-jHQQ"}
    for _ in range(4):
        with requests.post(url,json=payload,headers=headers) as resp:
            try:
                resp.raise_for_status()
                rich.print(resp.text)
            except Exception as exc:
                import traceback
                rich.print(traceback.format_exc())
                print(resp.text)


if __name__ == '__main__':
    import asyncio
    # asyncio.run(test())
    test2()
