from fastapi import APIRouter
from schemas.endpoints import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查接口"""
    return {
        'status': 'healthy',
        'database_connected': False  # 原Flask应用中DB_POOL实际未使用
    }