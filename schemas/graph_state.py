from typing import *
import enum
from pydantic import BaseModel, Field
from aiohttp import ClientSession
from services.custom_openai import CAsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from .endpoints import QueryRequest

#NOTE To avoid command injection attack, pydantic modules can be deserialized must be explicitly listed.
# Define the allowed modules list exactly
allowed_pydantic_modules =[
    ('schemas.endpoints', 'QueryRequest'),
    ('schemas.endpoints', 'QueryResult'),
    ('schemas.endpoints', 'QueryResponse'),
    ('schemas.graph_state', 'StateSchema'),
]
whitelist_serializer = JsonPlusSerializer(allowed_msgpack_modules=allowed_pydantic_modules)


#NOTE custom reducer function for appending message 
def append_messages(
    existing: List[ChatCompletionMessageParam], 
    new: Union[ChatCompletionMessageParam, List[ChatCompletionMessageParam]]
) -> List[ChatCompletionMessageParam]:
    """Appends a single message dict or a list of message dicts to the existing list."""
    if existing is None:
        existing =[]
        
    if not new:
        return existing
    # If the new update is already a list, extend/add it
    if isinstance(new, list):
        return existing + new
    # If it's a single dictionary (ChatCompletionMessageParam), wrap it in a list
    else:
        return existing + [new]


class ContextSchema(TypedDict):
    """context schema stores all client sessions for every connection"""
    llm_client: CAsyncOpenAI
    http_client: ClientSession
    db_client: ...#TODO


class Intent(enum.Enum):
    BPM = "bpm"
    ATTENDANCE = "attendance"

class StateSchema(BaseModel):
    query_request: Annotated[QueryRequest, "single round, would be overrided"]
    "serialized user request"
    messages: Annotated[List[ChatCompletionMessageParam], append_messages, "comply openai standard."]
    "chat messages"
    intent: Annotated[Optional[Intent], "recognized intent is useful in later process"]
    "recognized intent"
    named_entities: Annotated[Optional[List[str]], "recognized named entities is useful in later process"]
    "recognized named entities"


