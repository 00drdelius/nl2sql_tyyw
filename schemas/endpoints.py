from typing import *
import uuid

from pydantic import BaseModel, Field



class QueryRequest(BaseModel):
    """查询请求模型"""
    query: str = Field(..., description="用户的自然语言查询")
    authorization: str = Field(..., description="认证令牌")


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


class ErrorResponse(BaseModel):
    """错误响应模型"""
    success: bool = False
    error: str


class ChunkResponse(BaseModel):
    id: Annotated[str, Field(..., default_factory=lambda: str(uuid.uuid4()))]
    type: Literal[
        'recognize_intent','polish_query','retrieve_tables',
        'flag_to_reply','stream_reply','query_success','retry_reply',
        'final_result', 'error']
    content: Annotated[Union[str, QueryResponse], "response content"]


