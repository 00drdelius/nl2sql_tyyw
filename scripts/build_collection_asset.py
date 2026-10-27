import sys
from pathlib import Path

# 确保以 `python scripts/build_collection_asset.py` 直接运行时也能导入项目根目录模块
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import settings
from pymilvus import FieldSchema, DataType, CollectionSchema, Collection, connections, utility

# 按环境选择集合与表结构：
#   TEST_MODE=true  -> 集合 asset       （测试/130 CMDB 表定义）
#   TEST_MODE=false -> 集合 asset_prod  （正式 CMDB 表定义，需先对正式 CMDB 跑 --dump-md）
if settings.TEST_MODE:
    from source.tables import ASSET_TABLE_SCHEMAS as table_schemas
    collection_name = "asset"
    schema_description = "统一运维-资产-测试"
else:
    from source.tables import ASSET_PROD_TABLE_SCHEMAS as table_schemas
    collection_name = "asset_prod"
    schema_description = "统一运维-资产-正式"

if not table_schemas:
    raise SystemExit(f"无可用表结构（集合 {collection_name}）：请先用同步脚本 --dump-md 生成对应环境的表定义 markdown")

# 连接Milvus（确保你的Milvus服务已启动）
connections.connect(host='localhost', port='19530')
# 定义字段（只保留表结构相关字段！）
fields = [
    # 主键（自动生成）
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True, description="主键ID"),

    # 关键字段：存储表结构字符串（如"社保参保人数统计表结构"）
    # 资产表属性列多，单块可能超过既有集合的 5000 上限，本集合直接取 VARCHAR 上限
    FieldSchema(name="table_schema_str", dtype=DataType.VARCHAR, max_length=65535, description="表结构字符串（存储表结构描述）"),

    # 向量字段（用于语义搜索表结构）
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=2560, description="表结构表征向量"),
]

# 创建集合 Schema
schema = CollectionSchema(
    fields,
    description=schema_description
)

# 检查是否存在该集合
if utility.has_collection(collection_name):
    # 删除现有集合
    utility.drop_collection(collection_name)
    print(f"集合 '{collection_name}' 已删除。")

collection = Collection(name=collection_name, schema=schema)

# 创建索引
index_params = {
    "index_type": "HNSW",
    "metric_type": "COSINE",
    "params": {"M": 32, "efConstruction": 128}
}
collection.create_index("embedding", index_params)
collection.load()  # 加载到内存才能搜索

print(f"✅ 成功创建集合: {collection_name}")
print("📌 提示：后续插入数据时，'table_schema_str' 字段存表结构描述（如'CREATE TABLE ...'），'embedding' 用模型生成向量！")

# 获取集合
collection = Collection(collection_name)

# 1. 生成向量（用阿里云百炼）
from openai import OpenAI

client = OpenAI(
    api_key="sk-NO0AFfqpj-jlqpDx94RiiA",  # 替换成你的
    base_url="http://19.119.245.93:4000/v1"
)
table_descriptions = table_schemas

# 生成嵌入向量
embeddings = []
for desc in table_descriptions:
    if len(desc) > 65000:
        desc = desc[:65000]  # 兜底：避免超长导致 insert 失败
    print(f"正在生成嵌入向量：{desc}")
    response = client.embeddings.create(
        model="Qwen3-Embedding-4B",
        input=desc,
        encoding_format="float"
    )
    print(len(response.data[0].embedding))
    embeddings.append(response.data[0].embedding)

# 插入Milvus
data = [
    {"table_schema_str": desc, "embedding": emb}
    for desc, emb in zip(table_descriptions, embeddings)
]
collection.insert(data)

collection.flush()  # 确保数据持久化并可见（不 flush 则 num_entities=0 且检索不到）
print("✅ 表结构描述已插入Milvus！")
