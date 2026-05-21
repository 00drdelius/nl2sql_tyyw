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
    description="统一运维-工单"
)

# 集合名称
collection_name = "bpm"
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

table_descriptions = [
"表名：BPM_ModProcessList: 流程模型中的流程过程属性表，流程模型中的流程过程属性。\n\n| 字段名称 | 主键 | 字段类型 | 长度 | 是否为空 | 默认值 | 字段说明 |\n| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n| WF_OrUnid | Y | varchar | 50 | N | 无 | 32 位唯一 ID 号 |\n| WF_Appid | N | varchar | 50 | N | 无 | 所属应用 |\n| Processid | N | varchar | 100 | N | 无 | 流程 ID 号 |\n| Nodeid | N | varchar | 10 | N | ('Process') | 节点 id |\n| NodeType | N | varchar | 20 | N | ('Process') | 节点主类型 |\n| ExtNodeType | N | varchar | 50 | N | ('process') | 节点扩展类型 |\n| NodeName | N | varchar | 150 | N | 无 | 流程名称 |\n| ProcessNumber | N | varchar | 50 | Y | 无 | 流程编号 |\n| OtherProcessName | N | varchar | 150 | Y | ('') | 流程别名 |\n| Folderid | N | varchar | 50 | Y | 无 | 所属文件夹 |\n| Status | N | varchar | 50 | Y | ('0') | 1 表示发布，0 表示暂停 |\n| Deptid | N | varchar | 50 | Y | ('') | 所属部门 id |\n| ProcessOwner | N | varchar | 150 | Y | ('') | 流程所有者 |\n| ProcessReader | N | varchar | 1000 | Y | ('') | 流程全局读者 |\n| ProcessDesigner | N | varchar | 250 | Y | ('') | 流程设计者 |\n| ProcessStarter | N | varchar | 500 | Y | ('') | 有权启动者 |\n| FormNumber | N | varchar | 50 | Y | ('') | 所使用的表单 id |\n| FormNumberForMobile | N | varchar | 50 | Y | ('') | 移动审批表单 |\n| SortNum | N | varchar | 50 | Y | ('1001') | 同级排序号 |\n| SaveDataHistory | N | char | 1 | Y | ('0') | 1 表示存表单历史数据，0 表示不存 |\n| icons | N | varchar | 150 | Y | ('') | 流程图标地址 |\n| ExceedTime | N | varchar | 10 | Y | ('0') | 流程持继时间 |\n| AutoArchive | N | char | 1 | Y | ('1') | 1 表示自动归档空表示否 |\n| WordTemplate | N | varchar | 50 | Y | 无 | Word 正文模板 |\n| PrintTemplate | N | varchar | 50 | Y | 无 | 打印模板 |\n| WF_Version | N | varchar | 50 | Y | ('1.0') | 版本号 |\n| WF_AddName_CN | N | varchar | 50 | Y | 无 | 创建者 |\n| WF_AddName | N | varchar | 50 | Y | 无 | 创建者 |\n| WF_DocCreated | N | varchar | 50 | Y | 无 | 创建时间 |\n| WF_LastModified | N | varchar | 50 | Y | 无 | 最后更新时间 |\n| XmlData | N | xml | -1 | Y | ('') | XML 扩展数据 |",
"表名：BPM_MainData: 流程实例主数据表，流程实例主数据，在流转中的流程实例存在本表中，流程结束后就会归档到 BPM_ArchivedData 表中去，这两张表必须保持一致性。\n\n| 字段名称 | 主键 | 字段类型 | 长度 | 是否为空 | 默认值 | 字段说明 |\n| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n| WF_OrUnid | Y | varchar | 50 | N | 无 | 文档 32 位唯一标识一般与 WF_DocUNID 相等 |\n| Subject | N | varchar | 300 | N | 无 | 文档标题，此字段发送待办邮件时必须 |\n| WF_Appid | N | varchar | 30 | Y | 无 | 所属应用的 ID 号 |\n| WF_Processid | N | varchar | 50 | Y | 无 | 此文档使用的流程 ID 号 |\n| WF_ProcessName | N | varchar | 250 | Y | 无 | 流程名称 |\n| WF_AddName | N | varchar | 30 | Y | 无 | 流程启动者的英文名 |\n| WF_AddName_CN | N | varchar | 50 | Y | 无 | 流程启动者的中文名 |\n| WF_Author | N | varchar | 8000 | Y | 无 | 当前审批者，此字段的内容会存入到 WF_AllAuthors 中 |\n| WF_Author_CN | N | varchar | 8000 | Y | 无 | 当前审批者的中文名，与 WF_Author 一一对应 |\n| WF_EndUser | N | varchar | 8000 | Y | 无 | 已审批结束的用户列表，此字段值会合并到 WF_AllReaders 中 |\n| WF_AllReaders | N | varchar | 8000 | Y | 无 | 所有有权访问本文档的用户列表 |\n| WF_CopyUser | N | varchar | 8000 | Y | 无 | 传阅用户列表 |\n| WF_DocNumber | N | varchar | 30 | Y | 无 | 流水单号系统自动生成，当需要自定义流水号时可以覆盖此字段 |\n| WF_CurrentNodeid | N | varchar | 100 | Y | 无 | 当前所在节点 id |\n| WF_CurrentNodeName | N | varchar | 500 | Y | 无 | 流程当前所处的节点名称，当有多个时用逗号分隔，要想得到每个用户具体在那个环节请从 WF_CurUserStatus 字段中获取 |\n| WF_Status | N | varchar | 30 | Y | 无 | 流程当前状态，Current 表示审批中，End 表示已结束，Draft 表示草稿 |\n| WF_VersionNumber | N | varchar | 30 | Y | ('') | 当前文档的版本号 |\n| WF_SourceEntrustUserid | N | varchar | 200 | Y | 无 | 参与此文档的且设置了代办的用户，显示被代办文档时用 |\n| WF_TargetEntrustUserid | N | varchar | 200 | Y | 无 | 代办的用户列表，记录那些用户是代办的 |\n| WF_ProcessNumber | N | varchar | 30 | Y | 无 | 过程属性中指定的流程编号 |\n| WF_MainNodeid | N | varchar | 50 | Y | ('') | 主流程中启动本节点 Nodeid 如果没有则为空值 |\n| WF_MainDocUnid | N | varchar | 50 | Y | ('') | 如果是子流程则有主文档的唯一编号 |\n| WF_TotalTime | N | varchar | 10 | Y | 无 | 总耗时 |\n| WF_EndTime | N | varchar | 30 | Y | ('') | 文档办结时间，文档结束后会自动生成 |\n| WF_BusinessNum | N | varchar | 50 | Y | ('') | 所属业务场景唯一标识 |\n| WF_EndBusinessid | N | varchar | 30 | Y | ('') | 对应流程结束环节的业务状态标识 |\n| WF_Folderid | N | varchar | 30 | Y | ('') | 归档时此字段从自动活动中得到指定的归档文件夹编号 |\n| WF_TransFlag | N | varchar | 30 | Y | ('N') | 数据是否已传输到其他数据库表标记位 |\n| WF_ArcFormNumber | N | varchar | 30 | Y | ('') | 归档后显示表单的编号 |\n| WF_AddDeptid | N | varchar | 50 | Y | 无 | 起草人所在部门 ID 号 |\n| WF_Systemid | N | varchar | 30 | Y | 无 | 启动本流程的业务系统的 ID 号 |\n| WF_DocCreated | N | varchar | 30 | Y | 无 | 创建时间 |\n| WF_LastModified | N | varchar | 50 | Y | ('') | 最后更新时间 |\n| XmlData | N | xml | -1 | Y | 无 | 如果流程过程属性中选择 XmlData 表为数据主表，则系统会自动把表单字段组合成 xml 存入此字段中，否则会存入到 BPM_SubData 中 |\n\n> **XmlData 字段内容说明：**\n> 1. `unit` 为申请人单位\n> 2. `Project` 为所属项目\n> 3. `package` 为项目包\n> 4. `Subproject` 为子项目\n> 5. `ErrorType` 为故障类型或服务目录\n> 6. `Appsystem` 为应用系统\n> 7. `Detail` 为详情描述",
"表名：BPM_ArchivedData: 流程实例归档表，所有流程实例结束后都会从 BPM_MainData 表中迁移到本表中来，同时 BPM_MainData 表中的数据会删除掉，本表结构必须与 BPM_MainData 表保持一致。\n\n| 字段名称 | 主键 | 字段类型 | 长度 | 是否为空 | 默认值 | 字段说明 |\n| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n| WF_OrUnid | Y | varchar | 50 | N | 无 | 文档 32 位唯一标识一般与 WF_DocUNID 相等 |\n| Subject | N | varchar | 300 | N | 无 | 文档标题，此字段发送待办邮件时必须 |\n| WF_Appid | N | varchar | 30 | Y | 无 | 所属应用的 ID 号 |\n| WF_Processid | N | varchar | 50 | Y | 无 | 此文档使用的流程 ID 号 |\n| WF_ProcessName | N | varchar | 250 | Y | 无 | 流程名称 |\n| WF_AddName | N | varchar | 30 | Y | 无 | 流程启动者的英文名 |\n| WF_AddName_CN | N | varchar | 50 | Y | 无 | 流程启动者的中文名 |\n| WF_Author | N | varchar | 8000 | Y | 无 | 当前审批者，此字段的内容会存入到 WF_AllAuthors 中 |\n| WF_Author_CN | N | varchar | 8000 | Y | 无 | 当前审批者的中文名，与 WF_Author 一一对应 |\n| WF_EndUser | N | varchar | 8000 | Y | 无 | 已审批结束的用户列表，此字段值会合并到 WF_AllReaders 中 |\n| WF_AllReaders | N | varchar | 8000 | Y | 无 | 所有有权访问本文档的用户列表 |\n| WF_CopyUser | N | varchar | 8000 | Y | 无 | 拷贝用户（备用） |\n| WF_DocNumber | N | varchar | 30 | Y | 无 | 流水单号系统自动生成，当需要自定义流水号时可以覆盖此字段 |\n| WF_CurrentNodeid | N | varchar | 100 | Y | 无 | 当前节点 id |\n| WF_CurrentNodeName | N | varchar | 500 | Y | 无 | 流程当前所处的节点名称，当有多个时用逗号分隔，要想得到每个用户具体在那个环节请从 WF_CurUserStatus 字段中获取 |\n| WF_Status | N | varchar | 30 | Y | 无 | 流程当前状态，Current 表示审批中，End 表示已结束，Draft 表示草稿 |\n| WF_VersionNumber | N | varchar | 30 | Y | 无 | 当前文档的版本号 |\n| WF_SourceEntrustUserid | N | varchar | 200 | Y | 无 | 参与此文档的且设置了代办的用户，显示被代办文档时用 |\n| WF_TargetEntrustUserid | N | varchar | 200 | Y | 无 | 代办的用户列表，记录那些用户是代办的 |\n| WF_ProcessNumber | N | varchar | 30 | Y | 无 | 过程属性中指定的流程编号 |\n| WF_MainNodeid | N | varchar | 50 | Y | 无 | 父文档的编号，如果没有父文档则为空值 |\n| WF_MainDocUnid | N | varchar | 50 | Y | 无 | 主文档的唯一编号，如果没有主文档则此字段与 WF_DocUNID 相等 |\n| WF_TotalTime | N | varchar | 10 | Y | 无 | 流程结束后的总耗时 |\n| WF_EndTime | N | varchar | 30 | Y | 无 | 文档办结时间，文档结束后会自动生成 |\n| WF_BusinessNum | N | varchar | 50 | Y | ('') | 所属业务场景唯一标识 |\n| WF_EndBusinessid | N | varchar | 30 | Y | 无 | 对应流程结束环节的业务状态标识 |\n| WF_Folderid | N | varchar | 30 | Y | 无 | 归档时此字段从自动活动中得到指定的归档文件夹编号 |\n| WF_TransFlag | N | varchar | 30 | Y | ('N') | 数据是否已传输到其他数据库表标记位，如果为 E 则表示文档有错误 |\n| WF_ArcFormNumber | N | varchar | 30 | Y | 无 | 归档后显示表单的编号 |\n| WF_AddDeptid | N | varchar | 50 | Y | 无 | 起草人所在部门 ID 号 |\n| WF_Systemid | N | varchar | 30 | Y | 无 | 启动本流程的业务系统的 ID 号 |\n| WF_DocCreated | N | varchar | 30 | Y | 无 | 创建时间 |\n| WF_LastModified | N | varchar | 50 | Y | (getdate()) | 最后更新时间 |\n| XmlData | N | xml | -1 | Y | 无 | 如果流程过程属性中选择 XmlData 表为数据主表，则系统会自动把表单字段组合成 xml 存入此字段中，否则会存入到 BPM_SubData 中 |\n\n> **XmlData 字段内容说明：**\n> 1. `unit` 为申请人单位\n> 2. `Project` 为所属项目\n> 3. `package` 为项目包\n> 4. `Subproject` 为子项目\n> 5. `ErrorType` 为故障类型或服务目录\n> 6. `Appsystem` 为应用系统\n> 7. `Detail` 为详情描述",
]

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

