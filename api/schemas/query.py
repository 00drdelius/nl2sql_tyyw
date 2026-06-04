import uuid
from typing import *
from datetime import datetime

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """前端传入的对话消息。"""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, description="消息内容")


class QueryRequest(BaseModel):
    """单轮查询请求模型"""
    query: str = Field(..., description="用户的自然语言查询")
    user_id: str = Field(..., description="用户标识")
    authorization: str = Field(..., description="db执行引擎认证令牌")
    session_id: Optional[str] = Field(default=None, description="会话标识，不传则自动生成")


class ConversationQueryRequest(BaseModel):
    """多轮对话查询请求模型"""

    messages: List[ChatMessage] = Field(..., min_length=1, description="完整历史对话，不包含 system")
    user_id: str = Field(..., description="用户标识")
    authorization: str = Field(..., description="db执行引擎认证令牌")
    session_id: str = Field(..., min_length=1, description="会话标识")


class SessionSummaryResponse(BaseModel):
    session_id: str
    query_id: str
    user_id: str
    intent: Optional[str] = None
    status: Optional[str] = None
    original_query: str
    updated_at: datetime
    created_at: datetime


class HistoryRecordResponse(BaseModel):
    query_id: str
    session_id: str
    user_id: str
    intent: Optional[str] = None
    status: Optional[str] = None
    original_query: str
    parsed_query: Optional[str] = None
    polished_query: Optional[str] = None
    generated_sql: Optional[str] = None
    messages: List[ChatMessage]
    extra_payload: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class QueryResult(BaseModel):
    """SQL查询结果模型"""
    success: bool
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    userid_to_username: Optional[Dict[str, str]] = None


class QueryResponse(BaseModel):
    """查询响应模型"""
    original_query: str
    polished_query: str
    sql_dialect: str
    result: Optional[QueryResult]=None
    natural_answer: Optional[str] = None
    data_analysis: Optional[str] = None


class HealthResponse(BaseModel):
    """健康检查响应模型"""
    status: str
    database_connected: bool = False


class DeleteSessionResponse(BaseModel):
    """删除会话响应模型"""
    success: bool = True
    session_id: str
    deleted_count: int = Field(..., description="被删除的对话记录数")
    message: str = ""


class ErrorResponse(BaseModel):
    """错误响应模型"""
    success: bool = False
    error: str


class ChunkResponse(BaseModel):
    id: Annotated[str, Field(..., default_factory=lambda: str(uuid.uuid4()))]
    type: Literal[
        'recognize_intent',
        'ner_reply','semantic_reply_cot', 'semantic_reply',
        'polish_query','retrieve_tables',
        'flag_to_reply','stream_reply','query_success','retry_reply',
        'final_result', 'error']
    content: Annotated[Union[str, QueryResponse], "response content"]


if __name__=='__main__':
    import rich
    rich.print(ConversationQueryRequest.model_json_schema())
