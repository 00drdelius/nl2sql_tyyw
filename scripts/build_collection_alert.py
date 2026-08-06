from pymilvus import FieldSchema, DataType, CollectionSchema, Collection, connections, utility

# 连接Milvus（确保你的Milvus服务已启动）
connections.connect(host='localhost', port='19530')
# 定义字段（只保留表结构相关字段！）
fields = [
    # 主键（自动生成）
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True, description="主键ID"),

    # 关键字段：存储表结构字符串（如"社保参保人数统计表结构"）
    FieldSchema(name="table_schema_str", dtype=DataType.VARCHAR, max_length=5000, description="表结构字符串（存储表结构描述）"),

    # 向量字段（用于语义搜索表结构）
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=2560, description="表结构表征向量"),
]

# 创建集合 Schema
schema = CollectionSchema(
    fields,
    description="统一运维-告警"
)

# 集合名称
collection_name = "alert"
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
from source.tables import ALERT_TABLE_SCHEMAS

client = OpenAI(
    api_key="sk-NO0AFfqpj-jlqpDx94RiiA",  # 替换成你的
    base_url="http://19.119.245.93:4000/v1"
)
table_descriptions = ALERT_TABLE_SCHEMAS

# 生成嵌入向量
embeddings = []
for desc in table_descriptions:
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

# collection.flush()  # 确保数据持久化
print("✅ 表结构描述已插入Milvus！")
