from pymilvus import Collection, connections
from typing import List, Dict, Any
from config import settings
import asyncio

# 无访问权限的表/视图：检索结果中直接丢弃，避免LLM生成必然被SQL网关拒绝的语句。
# 2026-10-22：imoc_attendance_all 已开通访问权限，不再过滤（集合内本就有该视图的条目）。
INACCESSIBLE_TABLES: tuple[str, ...] = ()


class MilvusService:
    """Milvus向量数据库服务"""
    
    def __init__(self):
        # 连接Milvus（在事件循环外初始化）
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT
        )
    
    def _search_table_schema_sync(self, embedding: List[float], collection_name: str, limit: int = 5) -> str:
        """搜索最匹配的表结构（同步版本）"""
        collection = Collection(collection_name)
        collection.load()
        
        results = collection.search(
            data=[embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=limit,
            output_fields=["table_schema_str"]
        )
        
        if not results[0]:
            raise ValueError(f"未找到匹配表！")
        
        table_descs = ""
        idx = 0
        for item in results[0]:
            table_desc = item.entity.get('table_schema_str')
            if any(name in table_desc for name in INACCESSIBLE_TABLES):
                continue
            idx += 1
            table_descs += f"# 数据表{idx}\n{table_desc}\n\n\n"

        return table_descs.strip()
    
    async def search_table_schema(self, embedding: List[float], collection_name: str, limit: int = 5) -> str:
        """搜索最匹配的表结构（异步版本）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            self._search_table_schema_sync, 
            embedding, 
            collection_name, 
            limit
        )


# 创建全局Milvus服务实例
milvus_service = MilvusService()