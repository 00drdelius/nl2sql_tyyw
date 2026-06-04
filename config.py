from typing import Optional
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置类，使用Pydantic管理环境变量"""
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 10000
    TEST_MODE: bool = False
    LOG_LEVEL:str = "INFO"
    
    # OpenAI API配置
    OPENAI_API_KEY_1: str = "sk-NO0AFfqpj-jlqpDx94RiiA"
    OPENAI_API_BASE_1: str
    
    # 模型配置
    FLASH_MODEL: str
    POLISH_MODEL: str
    GENERATE_MODEL: str
    EMBEDDING_MODEL: str

    FLASH_MODEL_KEY: str 
    POLISH_MODEL_KEY: str 
    GENERATE_MODEL_KEY: str 
    EMBEDDING_MODEL_KEY: str 
    
    # Milvus配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: str = "19530"
    
    # 数据库配置（原Flask应用中未实际使用DB_POOL）
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "myapp"
    DB_USER: str = "myapp_user"
    DB_PASSWORD: str = "myapp_password"
    DATABASE_URL: Optional[str] = None
    DB_ECHO: bool = False

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """优先使用完整 DSN，否则基于 PostgreSQL 配置拼装异步连接串。"""
        if self.DATABASE_URL:
            return self.DATABASE_URL

        password = quote_plus(self.DB_PASSWORD)
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# 创建全局配置实例
settings = Settings()
