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
    # 口径歧义检测：问题存在多种合理解释时先问用户，而不是猜一个去查
    ENABLE_AMBIGUITY_CHECK: bool = True
    # 是否额外推 semantic_waiting SSE 事件。前端没适配时保持 False：
    # 老前端遇到未知事件类型会中断解析，表现为一直卡在「查询润色」。
    # 选项已经写进助手消息正文（和 NER 消歧同格式），不发事件也不影响使用。
    CLARIFICATION_SSE_EVENT: bool = False

    # 答案下方展示「实际查询的数据库表」，点开能看到表结构和查询当时的真实数据。
    # 预览页是后端渲染的 HTML，前端不用改：链接直接写在助手消息正文里。
    ENABLE_TABLE_PREVIEW: bool = True
    # 预览链接前缀 = 前端域名 + 反代前缀，最终拼成 {BASE}/api/table/preview?query_id=..&table=..
    TABLE_PREVIEW_BASE_URL: str = "https://19.112.71.86/agent_data"
    TABLE_PREVIEW_ROWS: int = 20       # 预览展示多少行真实数据
    TABLE_PREVIEW_TIMEOUT: float = 8.0  # 单条取样 SQL 的超时，超时就只展示表结构
    
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

    # CMDB API 配置（资产直查；token 会过期，需定期更新）
    CMDB_BASE_URL_TEST: str = "http://172.29.8.130"
    CMDB_BASE_URL_PROD: str = "https://19.112.71.86"
    CMDB_TOKEN_TEST: str = ""
    CMDB_TOKEN_PROD: str = ""

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
