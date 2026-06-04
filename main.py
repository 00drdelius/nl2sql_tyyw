from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from api.endpoints import query, health
from config import settings
from db.database import DatabaseOperator
from logg import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("FastAPI应用启动中...")
    db_operator = DatabaseOperator()
    await db_operator.init_models()
    app.state.db_operator = db_operator
    logger.info("服务初始化完成")
    yield
    logger.info("FastAPI应用正在关闭...")
    await db_operator.dispose()


# 创建FastAPI应用实例
app = FastAPI(
    title="AI Query System",
    description="基于大语言模型的自然语言转SQL查询服务",
    version="1.0.0",
    lifespan=lifespan
)

# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（生产环境应限制具体域名）
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(query.router)
app.include_router(health.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT if not settings.TEST_MODE else 10001,
    )
