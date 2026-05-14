from cache_dialect import CACHE_DIALECTS

# 工单、考勤识别
INTENT_RECOGNITION="""\
# 角色
你是一名人工智能助手

# 任务描述
请根据用户问题（<用户问题>），帮我判断用户是在问考勤的信息还是工单的信息。

# 回答格式
若用户问的是考勤相关的信息，请返回：
```
<考勤>
```

若用户问的是工单相关的信息，请返回：
```
<工单>
```
"""

# 2. 你可以在你的<think>中思考，但是你润色的最终结果需要用"<润色后>"这个xml标签裹住。
POLISH_SYS="""\
因为用户是不懂SQL语句的小白，所以我需要你根据给你的SQL表结构与视图结构（<SQL表与视图结构>），
润色用户用于查询的自然语言（<用户问题>）。

# 要求
1. 我不需要你生成SQL语句，我只需要你润色用户查询的自然语言，因此你的输出仍然是一串自然语言，只是丰富、具体了需要的SQL信息。
2. 你最好思考后再给出答案，但是你润色的最终结果需要用"<润色后>"这个xml标签裹住。不要漏了"</润色后>"这个尾标签

<SQL表与视图结构>
{table_view_struct}
</SQL表与视图结构>

# 示例输出
<润色后>
...
</润色后>
"""

GENERATE_SYS_V2="""\
你是一名MySQL语言专家。我会提供给你用户自然语言查询问题（<用户查询>）与缓存的SQL语句模板（<SQL缓存模板>），
我需要你根据我提供的信息，判断是否有合适的<SQL缓存模板>、并根据模板输出结果。

# 具体步骤
1. 判断是否有<SQL缓存模板>能满足回答<用户问题>：
  - 若有：缓存命中，跳转至点2
  - 若没有：跳转至点3
2. 提取出该模板，根据下面的命中生成要求（<命中时要求>）生成MySQL可执行的查询语句
3. 根据下面的未命中生成要求（<未命中时要求>）生成MySQL可执行的查询语句

## 命中时要求
1. 命中时一般只需要你修改对应语句模板内"BETWEEN <datetime1> AND <datetime2>"的时间（注意时间遵循格式: "%Y-%m-%d"）、或者新增关键词过滤即可（"CASE ... WHEN ... AS ..."）
2. 若需要在模板基础上新增查询的列，非中文时用"AS"语句转中文，也要注意中文字段要用英文双引号"\""裹住
3. 最终结果请用xml标签"<sql>"裹住，且只允许放可以执行的sql语句，不允许添加注释

## 未命中时要求
1. 请根据提供的表结构信息（<相关数据表结构>）与注意事项（<注意事项>）生成语句
2. 禁止使用子查询
3. 字段名若是英文，请用"AS"语句转成中文。也要注意中文字段要用英文双引号"\""裹住
4. 最终结果也请用xml标签"<sql>"裹住，且只允许放可以执行的sql语句，不允许添加注释


# 今日时间
{datetime_today}

# SQL缓存模板
"""+CACHE_DIALECTS+"""\

# 相关数据表结构
{table_descs}

# 注意事项
{note}

# 最终输出模板
<sql>
<完整SQL语句>
</sql>
"""


GENERATE_SYS="""\
你是一名MySQL语言专家，
请根据提供的表结构信息和查询需求，来生成可执行的MySQL支持的SQL查询语句。

# 要求
1. 你在生成前必须先思考该如何生成，并输出思路
2. 禁止使用子查询
3. 字段名若是英文，请用"AS"语句转成中文。也要注意中文字段要用英文双引号"\""裹住
4. 最终结果请用"<sql>"标签裹住，且只允许放可以执行的sql语句，不允许添加注释

# 最终输出示例
<sql>
select field1 from table1;
</sql>

# 今日时间
{datetime_today}

# 相关数据表结构
{table_descs}

# 注意
{note}
"""


FEEDBACK_SYS="""
你刚才生成的SQL在执行时发生了错误。
【报错信息】:
{error_msg}

请分析报错的原因，并重新生成正确的SQL语句。
注意：
1. 依然要先输出思考过程。
2. 修正后的SQL必须放在<sql>标签内部。
"""


# 考勤注意事项
ATTENDANCE_NOTE="""\
1. 若是查询到表"imoc_attendance_all"(其实是视图)，思考是否可用于解决用户问题，若可以，优先使用这个视图。注意这个视图字段设置为了全中文，直接用中文字段查询即可
"""

# 工单注意事项
BPM_NOTE="""\
1. 数据库为mysql数据库，版本为5.7.30
2. 表中的xmldata为xml字段，包含流程表单中用户定义的字段。其中部分常用的属性为：1）unit 为申请人单位，2）Project 为所属项目，3）package 为项目包，4）Subproject 为子项目，5）ErrorType 为故障类型或服务目录，6）Appsystem 为应用系统
3. xmldata中xml的结构为<Items><WFItem name="project"><![CDATA[项目名称]]></WFItem></Items>，xmldata取值路径为`/Items/WFItem["字段名称”]`，例如项目字段的xml取值路径为：`/Items/WFItem["project”]`
4. 默认使用extractvalue来获取xml字段的值
5. 没用要求的情况下，默认统计最近一周的数据，如果有提出具体的时间段要求则按具体的时间段统计
6. 统计时需要把当前表（bpm_maindata)和归档表(bpm_archiveddata)的数据使用union all合并统计
7. xmldata在存储下拉组件的数据时**可能**会多存储一个”字段名称_show“的字段，用于记录选中项的label的中文值，我需要你在有该字段时使用该字段作为表头，没有时再用原字段名称作为表头，请在生成SQL语句的时候注意这一点。示例：project为下拉组件时，`/Items/WFItem["project”]存储为项目的ID值，`/Items/WFItem["project_show”]`为项目的中文名称
"""
# 8. xmldata在存储下拉组件的数据时会多存储一个”字段名称_show“的字段，用于记录选中项的label中文值，强调也可能不存在”字段名称_show“，使用该字段时必须判断有没有存在该字段后再使用，例如：project为下拉组件则`/Items/WFItem["project”]存储为项目的ID值，`/Items/WFItem["project_show”]`为项目的中文名称。



ATTENDANCE_TABLE_DESCRIPTIONS = [
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


BPM_TABLE_DESCRIPTIONS = [
"### 7.1 流程模型中的流程过程属性表 (BPM_ModProcessList)\n\n流程模型中的流程过程属性\n\n| 字段名称 | 主键 | 字段类型 | 长度 | 是否为空 | 默认值 | 字段说明 |\n| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n| WF_OrUnid | Y | varchar | 50 | N | 无 | 32 位唯一 ID 号 |\n| WF_Appid | N | varchar | 50 | N | 无 | 所属应用 |\n| Processid | N | varchar | 100 | N | 无 | 流程 ID 号 |\n| Nodeid | N | varchar | 10 | N | ('Process') | 节点 id |\n| NodeType | N | varchar | 20 | N | ('Process') | 节点主类型 |\n| ExtNodeType | N | varchar | 50 | N | ('process') | 节点扩展类型 |\n| NodeName | N | varchar | 150 | N | 无 | 流程名称 |\n| ProcessNumber | N | varchar | 50 | Y | 无 | 流程编号 |\n| OtherProcessName | N | varchar | 150 | Y | ('') | 流程别名 |\n| Folderid | N | varchar | 50 | Y | 无 | 所属文件夹 |\n| Status | N | varchar | 50 | Y | ('0') | 1 表示发布，0 表示暂停 |\n| Deptid | N | varchar | 50 | Y | ('') | 所属部门 id |\n| ProcessOwner | N | varchar | 150 | Y | ('') | 流程所有者 |\n| ProcessReader | N | varchar | 1000 | Y | ('') | 流程全局读者 |\n| ProcessDesigner | N | varchar | 250 | Y | ('') | 流程设计者 |\n| ProcessStarter | N | varchar | 500 | Y | ('') | 有权启动者 |\n| FormNumber | N | varchar | 50 | Y | ('') | 所使用的表单 id |\n| FormNumberForMobile | N | varchar | 50 | Y | ('') | 移动审批表单 |\n| SortNum | N | varchar | 50 | Y | ('1001') | 同级排序号 |\n| SaveDataHistory | N | char | 1 | Y | ('0') | 1 表示存表单历史数据，0 表示不存 |\n| icons | N | varchar | 150 | Y | ('') | 流程图标地址 |\n| ExceedTime | N | varchar | 10 | Y | ('0') | 流程持继时间 |\n| AutoArchive | N | char | 1 | Y | ('1') | 1 表示自动归档空表示否 |\n| WordTemplate | N | varchar | 50 | Y | 无 | Word 正文模板 |\n| PrintTemplate | N | varchar | 50 | Y | 无 | 打印模板 |\n| WF_Version | N | varchar | 50 | Y | ('1.0') | 版本号 |\n| WF_AddName_CN | N | varchar | 50 | Y | 无 | 创建者 |\n| WF_AddName | N | varchar | 50 | Y | 无 | 创建者 |\n| WF_DocCreated | N | varchar | 50 | Y | 无 | 创建时间 |\n| WF_LastModified | N | varchar | 50 | Y | 无 | 最后更新时间 |\n| XmlData | N | xml | -1 | Y | ('') | XML 扩展数据 |",
"### 7.2 流程实例主数据表 (BPM_MainData)\n\n流程实例主数据，在流转中的流程实例存在本表中，流程结束后就会归档到 BPM_ArchivedData 表中去，这两张表必须保持一致性。\n\n| 字段名称 | 主键 | 字段类型 | 长度 | 是否为空 | 默认值 | 字段说明 |\n| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n| WF_OrUnid | Y | varchar | 50 | N | 无 | 文档 32 位唯一标识一般与 WF_DocUNID 相等 |\n| Subject | N | varchar | 300 | N | 无 | 文档标题，此字段发送待办邮件时必须 |\n| WF_Appid | N | varchar | 30 | Y | 无 | 所属应用的 ID 号 |\n| WF_Processid | N | varchar | 50 | Y | 无 | 此文档使用的流程 ID 号 |\n| WF_ProcessName | N | varchar | 250 | Y | 无 | 流程名称 |\n| WF_AddName | N | varchar | 30 | Y | 无 | 流程启动者的英文名 |\n| WF_AddName_CN | N | varchar | 50 | Y | 无 | 流程启动者的中文名 |\n| WF_Author | N | varchar | 8000 | Y | 无 | 当前审批者，此字段的内容会存入到 WF_AllAuthors 中 |\n| WF_Author_CN | N | varchar | 8000 | Y | 无 | 当前审批者的中文名，与 WF_Author 一一对应 |\n| WF_EndUser | N | varchar | 8000 | Y | 无 | 已审批结束的用户列表，此字段值会合并到 WF_AllReaders 中 |\n| WF_AllReaders | N | varchar | 8000 | Y | 无 | 所有有权访问本文档的用户列表 |\n| WF_CopyUser | N | varchar | 8000 | Y | 无 | 传阅用户列表 |\n| WF_DocNumber | N | varchar | 30 | Y | 无 | 流水单号系统自动生成，当需要自定义流水号时可以覆盖此字段 |\n| WF_CurrentNodeid | N | varchar | 100 | Y | 无 | 当前所在节点 id |\n| WF_CurrentNodeName | N | varchar | 500 | Y | 无 | 流程当前所处的节点名称，当有多个时用逗号分隔，要想得到每个用户具体在那个环节请从 WF_CurUserStatus 字段中获取 |\n| WF_Status | N | varchar | 30 | Y | 无 | 流程当前状态，Current 表示审批中，End 表示已结束，Draft 表示草稿 |\n| WF_VersionNumber | N | varchar | 30 | Y | ('') | 当前文档的版本号 |\n| WF_SourceEntrustUserid | N | varchar | 200 | Y | 无 | 参与此文档的且设置了代办的用户，显示被代办文档时用 |\n| WF_TargetEntrustUserid | N | varchar | 200 | Y | 无 | 代办的用户列表，记录那些用户是代办的 |\n| WF_ProcessNumber | N | varchar | 30 | Y | 无 | 过程属性中指定的流程编号 |\n| WF_MainNodeid | N | varchar | 50 | Y | ('') | 主流程中启动本节点 Nodeid 如果没有则为空值 |\n| WF_MainDocUnid | N | varchar | 50 | Y | ('') | 如果是子流程则有主文档的唯一编号 |\n| WF_TotalTime | N | varchar | 10 | Y | 无 | 总耗时 |\n| WF_EndTime | N | varchar | 30 | Y | ('') | 文档办结时间，文档结束后会自动生成 |\n| WF_BusinessNum | N | varchar | 50 | Y | ('') | 所属业务场景唯一标识 |\n| WF_EndBusinessid | N | varchar | 30 | Y | ('') | 对应流程结束环节的业务状态标识 |\n| WF_Folderid | N | varchar | 30 | Y | ('') | 归档时此字段从自动活动中得到指定的归档文件夹编号 |\n| WF_TransFlag | N | varchar | 30 | Y | ('N') | 数据是否已传输到其他数据库表标记位 |\n| WF_ArcFormNumber | N | varchar | 30 | Y | ('') | 归档后显示表单的编号 |\n| WF_AddDeptid | N | varchar | 50 | Y | 无 | 起草人所在部门 ID 号 |\n| WF_Systemid | N | varchar | 30 | Y | 无 | 启动本流程的业务系统的 ID 号 |\n| WF_DocCreated | N | varchar | 30 | Y | 无 | 创建时间 |\n| WF_LastModified | N | varchar | 50 | Y | ('') | 最后更新时间 |\n| XmlData | N | xml | -1 | Y | 无 | 如果流程过程属性中选择 XmlData 表为数据主表，则系统会自动把表单字段组合成 xml 存入此字段中，否则会存入到 BPM_SubData 中 |\n\n> **XmlData 字段内容说明：**\n> 1. `unit` 为申请人单位\n> 2. `Project` 为所属项目\n> 3. `package` 为项目包\n> 4. `Subproject` 为子项目\n> 5. `ErrorType` 为故障类型或服务目录\n> 6. `Appsystem` 为应用系统\n> 7. `Detail` 为详情描述",
"### 7.3 流程实例归档表 (BPM_ArchivedData)\n\n流程实例归档表，所有流程实例结束后都会从 BPM_MainData 表中迁移到本表中来，同时 BPM_MainData 表中的数据会删除掉，本表结构必须与 BPM_MainData 表保持一致。\n\n| 字段名称 | 主键 | 字段类型 | 长度 | 是否为空 | 默认值 | 字段说明 |\n| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n| WF_OrUnid | Y | varchar | 50 | N | 无 | 文档 32 位唯一标识一般与 WF_DocUNID 相等 |\n| Subject | N | varchar | 300 | N | 无 | 文档标题，此字段发送待办邮件时必须 |\n| WF_Appid | N | varchar | 30 | Y | 无 | 所属应用的 ID 号 |\n| WF_Processid | N | varchar | 50 | Y | 无 | 此文档使用的流程 ID 号 |\n| WF_ProcessName | N | varchar | 250 | Y | 无 | 流程名称 |\n| WF_AddName | N | varchar | 30 | Y | 无 | 流程启动者的英文名 |\n| WF_AddName_CN | N | varchar | 50 | Y | 无 | 流程启动者的中文名 |\n| WF_Author | N | varchar | 8000 | Y | 无 | 当前审批者，此字段的内容会存入到 WF_AllAuthors 中 |\n| WF_Author_CN | N | varchar | 8000 | Y | 无 | 当前审批者的中文名，与 WF_Author 一一对应 |\n| WF_EndUser | N | varchar | 8000 | Y | 无 | 已审批结束的用户列表，此字段值会合并到 WF_AllReaders 中 |\n| WF_AllReaders | N | varchar | 8000 | Y | 无 | 所有有权访问本文档的用户列表 |\n| WF_CopyUser | N | varchar | 8000 | Y | 无 | 拷贝用户（备用） |\n| WF_DocNumber | N | varchar | 30 | Y | 无 | 流水单号系统自动生成，当需要自定义流水号时可以覆盖此字段 |\n| WF_CurrentNodeid | N | varchar | 100 | Y | 无 | 当前节点 id |\n| WF_CurrentNodeName | N | varchar | 500 | Y | 无 | 流程当前所处的节点名称，当有多个时用逗号分隔，要想得到每个用户具体在那个环节请从 WF_CurUserStatus 字段中获取 |\n| WF_Status | N | varchar | 30 | Y | 无 | 流程当前状态，Current 表示审批中，End 表示已结束，Draft 表示草稿 |\n| WF_VersionNumber | N | varchar | 30 | Y | 无 | 当前文档的版本号 |\n| WF_SourceEntrustUserid | N | varchar | 200 | Y | 无 | 参与此文档的且设置了代办的用户，显示被代办文档时用 |\n| WF_TargetEntrustUserid | N | varchar | 200 | Y | 无 | 代办的用户列表，记录那些用户是代办的 |\n| WF_ProcessNumber | N | varchar | 30 | Y | 无 | 过程属性中指定的流程编号 |\n| WF_MainNodeid | N | varchar | 50 | Y | 无 | 父文档的编号，如果没有父文档则为空值 |\n| WF_MainDocUnid | N | varchar | 50 | Y | 无 | 主文档的唯一编号，如果没有主文档则此字段与 WF_DocUNID 相等 |\n| WF_TotalTime | N | varchar | 10 | Y | 无 | 流程结束后的总耗时 |\n| WF_EndTime | N | varchar | 30 | Y | 无 | 文档办结时间，文档结束后会自动生成 |\n| WF_BusinessNum | N | varchar | 50 | Y | ('') | 所属业务场景唯一标识 |\n| WF_EndBusinessid | N | varchar | 30 | Y | 无 | 对应流程结束环节的业务状态标识 |\n| WF_Folderid | N | varchar | 30 | Y | 无 | 归档时此字段从自动活动中得到指定的归档文件夹编号 |\n| WF_TransFlag | N | varchar | 30 | Y | ('N') | 数据是否已传输到其他数据库表标记位，如果为 E 则表示文档有错误 |\n| WF_ArcFormNumber | N | varchar | 30 | Y | 无 | 归档后显示表单的编号 |\n| WF_AddDeptid | N | varchar | 50 | Y | 无 | 起草人所在部门 ID 号 |\n| WF_Systemid | N | varchar | 30 | Y | 无 | 启动本流程的业务系统的 ID 号 |\n| WF_DocCreated | N | varchar | 30 | Y | 无 | 创建时间 |\n| WF_LastModified | N | varchar | 50 | Y | (getdate()) | 最后更新时间 |\n| XmlData | N | xml | -1 | Y | 无 | 如果流程过程属性中选择 XmlData 表为数据主表，则系统会自动把表单字段组合成 xml 存入此字段中，否则会存入到 BPM_SubData 中 |\n\n> **XmlData 字段内容说明：**\n> 1. `unit` 为申请人单位\n> 2. `Project` 为所属项目\n> 3. `package` 为项目包\n> 4. `Subproject` 为子项目\n> 5. `ErrorType` 为故障类型或服务目录\n> 6. `Appsystem` 为应用系统\n> 7. `Detail` 为详情描述",
]

