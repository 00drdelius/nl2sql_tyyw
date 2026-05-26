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


async def test():
    #NOTE 尽量别用 non-stream mode。。。运通api会返回是非标准字段`provider_specific_fields`
    client = CAsyncOpenAI(
        api_key="isg-tyyw-e35f2f75cb0d4c88af1d01f3838e3ad8",
        base_url="http://19.119.245.78/ebus/msmp",
    )
    completions = await client.chat.completions.create(
        # model="Qwen3-30B-A3B-Instruct-2507",
        model="Qwen3.5-397B-A17B",
        messages=[{"role":"user",'content':'50个字锐评下百度这家公司。'}],
        extra_body=dict(chat_template_kwargs=dict(enable_thinking=False)),
    )
    import rich
    rich.print("chat completions:")
    rich.print(completions)

    embd_resp = await client.embeddings.create(
        input="test test test test",
        model = "Qwen3-Embedding-4B",
        encoding_format='float',
        extra_authorization_key='isg-tyyw-d039ac95de5b4a44be9cf43af3c9ac97',
    )
    embd_resp.data[0].embedding = embd_resp.data[0].embedding[:20]
    rich.print("embeddings")
    rich.print(embd_resp)


if __name__ == '__main__':
    import asyncio
    asyncio.run(test())