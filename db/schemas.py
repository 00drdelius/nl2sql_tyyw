from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def utcnow_naive() -> datetime:
    """返回不带 tzinfo 的 UTC 时间，兼容 TIMESTAMP WITHOUT TIME ZONE。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ConversationMessage(SQLModel, table=False):
    """单条对话消息，不落独立表，作为 JSON 结构嵌入历史记录。"""

    role: Literal["user", "assistant"]
    content: str


class LLMConversationHistory(SQLModel, table=True):
    """存储一次完整的大模型调用历史，不包含 system prompt。"""

    __tablename__ = "llm_conversation_history"

    id: UUID = Field(default_factory=uuid4, primary_key=True, nullable=False)
    query_id: str = Field(index=True, unique=True, max_length=64, description="请求唯一标识")
    user_id: str = Field(index=True, max_length=128, description="用户标识")
    session_id: str = Field(index=True, max_length=128, description="会话标识")
    intent: str | None = Field(default=None, index=True, max_length=64, description="识别出的业务意图")
    original_query: str = Field(description="用户原始问题")
    parsed_query: str | None = Field(default=None, description="语义补全后的问题")
    polished_query: str | None = Field(default=None, description="润色后的问题")
    generated_sql: str | None = Field(default=None, description="模型生成的 SQL")
    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False),
        description="传给大模型的历史消息，仅保留 user/assistant",
    )
    extra_payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False),
        description="扩展字段，例如结果摘要、分析文本等",
    )
    created_at: datetime = Field(
        default_factory=utcnow_naive,
        nullable=False,
        description="创建时间（UTC）",
    )
    updated_at: datetime = Field(
        default_factory=utcnow_naive,
        nullable=False,
        description="更新时间（UTC）",
    )
