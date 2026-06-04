from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings
from db.schemas import ConversationMessage, LLMConversationHistory, utcnow_naive


class DatabaseOperator:
    """基于 asyncio + asyncpg + SQLModel 的异步数据库操作类。"""

    def __init__(
        self,
        database_url: str | None = None,
        echo: bool | None = None,
    ) -> None:
        self._database_url = database_url or settings.ASYNC_DATABASE_URL
        self._engine: AsyncEngine = create_async_engine(
            self._database_url,
            echo=settings.DB_ECHO if echo is None else echo,
            future=True,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def init_models(self) -> None:
        """初始化表结构。"""
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """返回一个异步 Session，上层按需组合事务。"""
        async with self._session_factory() as session:
            yield session

    async def save_conversation(
        self,
        *,
        query_id: str,
        user_id: str,
        session_id: str,
        original_query: str,
        messages: Iterable[ConversationMessage | dict[str, Any]],
        intent: str | None = None,
        parsed_query: str | None = None,
        polished_query: str | None = None,
        generated_sql: str | None = None,
        extra_payload: dict[str, Any] | None = None,
        status: str | None = None,
        session: AsyncSession | None = None,
    ) -> LLMConversationHistory:
        """写入一条完整对话历史。"""
        payload = dict(extra_payload or {})
        if status is not None:
            payload["status"] = status

        record = LLMConversationHistory(
            query_id=query_id,
            user_id=user_id,
            session_id=session_id,
            intent=intent,
            original_query=original_query,
            parsed_query=parsed_query,
            polished_query=polished_query,
            generated_sql=generated_sql,
            messages=[self._serialize_message(message) for message in messages],
            extra_payload=payload,
        )

        if session is not None:
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

        async with self.session() as managed_session:
            managed_session.add(record)
            await managed_session.commit()
            await managed_session.refresh(record)

        return record

    async def get_conversation_by_query_id(self, query_id: str) -> LLMConversationHistory | None:
        """按查询 ID 获取单条历史。"""
        async with self.session() as session:
            statement = select(LLMConversationHistory).where(
                LLMConversationHistory.query_id == query_id
            )
            result = await session.exec(statement)
            return result.first()

    async def list_conversations(
        self,
        user_id: str,
        session_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[LLMConversationHistory]:
        """按会话列出历史记录，按时间倒序返回。"""
        async with self.session() as session:
            statement = (
                select(LLMConversationHistory)
                .where(LLMConversationHistory.user_id == user_id)
                .where(LLMConversationHistory.session_id == session_id)
                .order_by(LLMConversationHistory.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.exec(statement)
            return list(result.all())

    async def get_latest_conversation_by_session_id(
        self,
        user_id: str,
        session_id: str,
    ) -> LLMConversationHistory | None:
        """按会话获取最近一条历史记录。"""
        async with self.session() as session:
            statement = (
                select(LLMConversationHistory)
                .where(LLMConversationHistory.user_id == user_id)
                .where(LLMConversationHistory.session_id == session_id)
                .order_by(LLMConversationHistory.created_at.desc())
                .limit(1)
            )
            result = await session.exec(statement)
            return result.first()

    async def get_latest_conversation_by_status(
        self,
        user_id: str,
        session_id: str,
        status: str,
    ) -> LLMConversationHistory | None:
        """按会话获取最近一条指定状态的历史记录。"""
        conversations = await self.list_conversations(user_id=user_id, session_id=session_id, limit=50)
        for conversation in conversations:
            if conversation.extra_payload.get("status") == status:
                return conversation
        return None

    async def list_user_sessions(
        self,
        user_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LLMConversationHistory]:
        """按用户列出所有会话窗口的最近一条记录。"""
        async with self.session() as session:
            statement = (
                select(LLMConversationHistory)
                .where(LLMConversationHistory.user_id == user_id)
                .order_by(LLMConversationHistory.updated_at.desc())
            )
            result = await session.exec(statement)
            conversations = list(result.all())

        latest_by_session: dict[str, LLMConversationHistory] = {}
        for conversation in conversations:
            if conversation.session_id not in latest_by_session:
                latest_by_session[conversation.session_id] = conversation

        sessions = list(latest_by_session.values())
        return sessions[offset: offset + limit]

    async def append_message(
        self,
        query_id: str,
        message: ConversationMessage | dict[str, Any],
    ) -> LLMConversationHistory | None:
        """向已存在的对话记录追加一条 user/assistant 消息。"""
        async with self.session() as session:
            statement = select(LLMConversationHistory).where(
                LLMConversationHistory.query_id == query_id
            )
            result = await session.exec(statement)
            record = result.first()
            if record is None:
                return None

            serialized = self._serialize_message(message)
            record.messages = [*record.messages, serialized]
            record.updated_at = utcnow_naive()
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def update_generated_sql(
        self,
        query_id: str,
        generated_sql: str,
        *,
        extra_payload: dict[str, Any] | None = None,
    ) -> LLMConversationHistory | None:
        """更新生成 SQL 和附加结果。"""
        async with self.session() as session:
            statement = select(LLMConversationHistory).where(
                LLMConversationHistory.query_id == query_id
            )
            result = await session.exec(statement)
            record = result.first()
            if record is None:
                return None

            record.generated_sql = generated_sql
            if extra_payload:
                record.extra_payload = {**record.extra_payload, **extra_payload}
            record.updated_at = utcnow_naive()
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    async def update_conversation(
        self,
        query_id: str,
        *,
        messages: Iterable[ConversationMessage | dict[str, Any]] | None = None,
        user_id: str | None = None,
        intent: str | None = None,
        original_query: str | None = None,
        parsed_query: str | None = None,
        polished_query: str | None = None,
        generated_sql: str | None = None,
        extra_payload: dict[str, Any] | None = None,
        status: str | None = None,
        session: AsyncSession | None = None,
    ) -> LLMConversationHistory | None:
        """更新已有会话记录。"""
        if session is not None:
            return await self._update_conversation_with_session(
                session,
                query_id=query_id,
                messages=messages,
                user_id=user_id,
                intent=intent,
                original_query=original_query,
                parsed_query=parsed_query,
                polished_query=polished_query,
                generated_sql=generated_sql,
                extra_payload=extra_payload,
                status=status,
            )

        async with self.session() as managed_session:
            return await self._update_conversation_with_session(
                managed_session,
                query_id=query_id,
                messages=messages,
                user_id=user_id,
                intent=intent,
                original_query=original_query,
                parsed_query=parsed_query,
                polished_query=polished_query,
                generated_sql=generated_sql,
                extra_payload=extra_payload,
                status=status,
            )

    async def delete_conversation(self, query_id: str) -> bool:
        """删除单条历史记录。"""
        async with self.session() as session:
            statement = select(LLMConversationHistory).where(
                LLMConversationHistory.query_id == query_id
            )
            result = await session.exec(statement)
            record = result.first()
            if record is None:
                return False

            await session.delete(record)
            await session.commit()
            return True

    async def dispose(self) -> None:
        """释放连接池。"""
        await self._engine.dispose()

    @staticmethod
    def _serialize_message(message: ConversationMessage | dict[str, Any]) -> dict[str, Any]:
        if isinstance(message, ConversationMessage):
            return message.model_dump()
        return ConversationMessage.model_validate(message).model_dump()

    async def _update_conversation_with_session(
        self,
        session: AsyncSession,
        *,
        query_id: str,
        messages: Iterable[ConversationMessage | dict[str, Any]] | None = None,
        user_id: str | None = None,
        intent: str | None = None,
        original_query: str | None = None,
        parsed_query: str | None = None,
        polished_query: str | None = None,
        generated_sql: str | None = None,
        extra_payload: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> LLMConversationHistory | None:
        statement = select(LLMConversationHistory).where(
            LLMConversationHistory.query_id == query_id
        )
        result = await session.exec(statement)
        record = result.first()
        if record is None:
            return None

        if messages is not None:
            record.messages = [self._serialize_message(message) for message in messages]
        if user_id is not None:
            record.user_id = user_id
        if intent is not None:
            record.intent = intent
        if original_query is not None:
            record.original_query = original_query
        if parsed_query is not None:
            record.parsed_query = parsed_query
        if polished_query is not None:
            record.polished_query = polished_query
        if generated_sql is not None:
            record.generated_sql = generated_sql
        if extra_payload:
            record.extra_payload = {**record.extra_payload, **extra_payload}
        if status is not None:
            record.extra_payload = {**record.extra_payload, "status": status}

        record.updated_at = utcnow_naive()
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record


db_operator = DatabaseOperator()
