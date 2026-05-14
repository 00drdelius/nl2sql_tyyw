from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from config import settings
from api.endpoints import query, health
from logg import logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行的初始化操作
    logger.info("FastAPI应用启动中...")
    # 初始化服务（服务类在导入时已自动初始化）
    logger.info("服务初始化完成")
    yield
    # 关闭时执行的清理操作
    logger.info("FastAPI应用正在关闭...")


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