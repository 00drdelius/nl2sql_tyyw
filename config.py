from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


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
    FLASH_MODEL: str = "Qwen3-30B-A3B-Instruct-2507"
    POLISH_MODEL: str = "Qwen3-32B"
    GENERATE_MODEL: str = "Qwen3.5-397B-A17B"
    EMBEDDING_MODEL: str = "Qwen3-Embedding-4B"

    FLASH_MODEL_KEY: str 
    POLISH_MODEL_KEY: str 
    GENERATE_MODEL_KEY: str 
    EMBEDDING_MODEL_KEY: str 
    
    # Milvus配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: str = "19530"
    
    # DashScope配置
    DASHSCOPE_API_URL: str = "https://dashscope.aliyuncs.com/api/v1"
    DASHSCOPE_API_KEY: str = "sk-27011a344d8546808f71d1b838f7aa7f"
    
    # 数据库配置（原Flask应用中未实际使用DB_POOL）
    DB_HOST: str = "localhost"
    DB_PORT: int = 3307
    DB_NAME: str = "myapp"
    DB_USER: str = "myapp_user"
    DB_PASSWORD: str = "myapp_password"
    
    model_config = SettingsConfigDict(env_file="docker/.env", extra="ignore")


# 创建全局配置实例
settings = Settings()
