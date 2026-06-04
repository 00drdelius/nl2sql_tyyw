from __future__ import annotations

from typing import AsyncIterator

from fastapi import Request
from sqlmodel.ext.asyncio.session import AsyncSession

from db.database import DatabaseOperator


def get_db_operator(request: Request) -> DatabaseOperator:
    return request.app.state.db_operator


async def get_db_session(
    request: Request,
) -> AsyncIterator[AsyncSession]:
    db_operator: DatabaseOperator = request.app.state.db_operator
    async with db_operator.session() as session:
        yield session
