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
    description="统一运维-考勤"
)

# 集合名称
collection_name = "attendance"
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
'表名：imoc_checkin_user: 考勤人员打卡记录表，用于记录人员的每一次打卡记录，反映员工考勤情况。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nuserid: 用户ID，关联用户表，标识打卡人员\nproject_id: 项目ID，关联项目表，标识打卡所属项目\nduty_id: 排班ID，关联排班表，标识打卡对应的排班\nclass_id: 班次ID，关联班次表，标识打卡对应的班次\nrange_id: 时间段ID，关联时间段表，标识打卡对应的时间段\nrelated_id: 关联duty_user的ID，用于关联人员排班记录\ntype: 类型，标识打卡类型\nrange_start_time: 考勤上班时间，记录规定的上班时间\nrange_end_time: 考勤下班时间，记录规定的下班时间\ntertian: 是否隔日，标识是否跨天\nduty_date: 值班日期，记录具体的值班日期\nduty_location: 值班打卡位置，记录规定的打卡位置\nlocation: 实际打卡位置，记录实际打卡的位置\nlng: 经度，记录打卡位置的经度坐标\nlat: 纬度，记录打卡位置的纬度坐标\nstatus: 状态，记录打卡状态\ncreate_time: 创建时间，记录创建时间戳\nupdate_time: 更新时间，记录最后更新时间戳\nis_del: 是否删除，标识数据是否已删除\nis_manual: 是否手动签到，标识是否为手动签到记录',
'表名：imoc_class: 考勤班次表，用于配置考勤班次，定义班次基本信息和规则。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nname: 班次名称，标识班次的名称\nendure_minutes: 容忍时间，记录打卡容忍的时间范围（分钟）\ninfo: 说明，记录班次的补充说明信息\ncreate_time: 创建时间，记录创建时间戳\ncreate_userid: 创建用户ID，记录创建该班次的用户\nupdate_time: 更新时间，记录最后更新时间戳\nupdate_userid: 更新用户ID，记录最后更新该班次的用户\nis_del: 是否删除，标识数据是否已删除',
'表名：imoc_class_duty: 考勤排班表，记录每个排班项目的排班安排，每个项目可以有多个排班。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nproject_id: 项目ID，关联项目表，标识排班所属项目\nclass_id: 班次ID，关联班次表，标识排班使用的班次\nstart_date: 开始日期，记录排班开始日期\nend_date: 结束日期，记录排班结束日期\ntype: 值班方式，记录值班的方式类型\nremark: 备注，记录排班的补充说明信息\nstatus: 状态，记录排班状态\ncreate_time: 创建时间，记录创建时间戳\ncreate_userid: 创建用户ID，记录创建该排班的用户\nupdate_time: 更新时间，记录最后更新时间戳\nupdate_userid: 更新用户ID，记录最后更新该排班的用户\nis_del: 是否删除，标识数据是否已删除',
'表名：imoc_class_duty_user: 考勤人员排班记录表，记录人员每一天具体上什么班次，反映人员排班情况。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nuserid: 用户ID，关联用户表，标识排班人员\nproject_id: 项目ID，关联项目表，标识排班所属项目\nduty_id: 排班ID，关联排班表，标识具体排班\nclass_id: 班次ID，关联班次表，标识使用的班次\nteam_id: 队伍ID，关联队伍表，标识所属队伍\nduty_date: 值班日期，记录具体的值班日期\nduty_time: 考勤时间，记录规定的考勤时间\nduty_status: 考勤状态，记录考勤状态\ncheckin_time: 签到时间，记录实际签到时间\ncheckin_location: 签到位置，记录实际签到位置\ntype: 值班类型，记录值班的类型\nstatus: 状态，记录记录状态\ncreate_time: 创建时间，记录创建时间戳\nupdate_time: 更新时间，记录最后更新时间戳\nis_del: 是否删除，标识数据是否已删除',
'表名：imoc_class_project: 考勤排班项目表，记录考勤排班项目信息。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nname: 项目名称，记录项目名称\nis_insance: 是否重保，标识是否为重要保障项目\ncreate_time: 创建时间，记录创建时间戳\ncreate_userid: 创建用户ID，记录创建该项目的用户\nupdate_time: 更新时间，记录最后更新时间戳\nupdate_userid: 更新用户ID，记录最后更新该项目的用户\nis_del: 是否删除，标识数据是否已删除\nstatus: 状态，记录项目状态',
'表名：imoc_class_range: 考勤班次时段表，记录每个班次的多个上班时间段。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nclass_id: 班次ID，关联班次表，标识所属班次\nstart_time: 开始时间，记录时段开始时间\nend_time: 结束时间，记录时段结束时间\ntertian: 是否隔日，标识是否跨天',
'表名：imoc_class_team: 考勤团队表，记录团队信息。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nuser_id: 用户ID，关联用户表，标识团队成员\nproject_id: 项目ID，关联项目表，标识团队所属项目\nclass_id: 班次ID，关联班次表，标识团队使用的班次\nduty_id: 排班ID，关联排班表，标识团队对应的排班',
'表名：imoc_class_user: 考勤人员记录表，记录考勤人员信息。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nuserid: 用户ID，关联用户表，标识考勤人员\ngroupid: 部门ID，关联部门表，标识所属部门\ntype: 适用对象，记录人员类型\nmobile: 手机号码，记录人员联系方式\nlocation: 位置，记录人员位置信息\ncreate_time: 创建时间，记录创建时间戳\ncreate_userid: 创建用户ID，记录创建该记录的用户\nupdate_time: 更新时间，记录最后更新时间戳\nupdate_userid: 更新用户ID，记录最后更新该记录的用户\nis_del: 是否删除，标识数据是否已删除\nname: 姓名，记录人员姓名',
'表名：imoc_class_appeal: 考勤申诉表，用于异常考勤的申诉处理，申诉通过后可订正为正常状态。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nduty_id: 值班ID，关联值班表，标识申诉对应的值班记录\ntype: 类型，记录申诉类型\nstart_time: 开始时间，记录申诉开始时间\nend_time: 结束时间，记录申诉结束时间\nreson: 请假原因，记录申诉原因\npic_url: 请假图片，记录申诉相关的图片URL\nstatus: 状态，记录申诉状态\nreject_reson: 拒绝理由，记录拒绝申诉的理由\ngov_reject_reson: 业主拒绝理由，记录业主拒绝申诉的理由\ncreate_userid: 申请人uid，记录申诉申请人\ncreate_time: 申请时间，记录申诉申请时间戳\nupdate_time: 更新时间，记录最后更新时间戳\napprove_user: 审批人员，记录审批人姓名\napprove_userid: 审批人ID，记录审批人ID\napprove_time: 审批时间，记录审批时间戳\ngov_approve_user: 业主审批人员，记录业主审批人姓名\ngov_approve_userid: 业主审批人ID，记录业主审批人ID\ngov_approve_time: 业主审批时间，记录业主审批时间戳\nis_del: 是否删除，标识数据是否已删除',

# view
'表名：imoc_attendance_all: 人员考勤记录表，用于记录人员每日打卡记录，包含考勤状态及申诉、请假标识。\n表字段：\n用户名称: 用户姓名，标识打卡用户\n单位名称: 用户所属单位名称\n项目名称: 用户所属项目名称\n排班名称: 排班规则名称\n班次名称: 具体班次名称\n值班日期: 值班的具体日期\n值班时间: 值班时间范围描述\n打卡时间: 实际打卡时间记录\n考勤状态: 考勤结果状态，其中早退、未签退、缺勤、迟到为考勤异常状态\n是否申诉: 标识该记录是否发起申诉\n是否请假: 标识该记录是否关联请假'
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

