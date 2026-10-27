from cache_dialect import CACHE_DIALECTS
from source.tables import ASSET_ACTIVE_SCHEMA_RECORDS, TableSchemaRecord

# 工单、考勤、告警、资产识别
INTENT_RECOGNITION="""\
# 角色
你是一名人工智能助手

# 任务描述
请根据用户问题（<用户问题>），帮我判断用户是在问考勤的信息、工单的信息、告警的信息还是资产的信息。

# 回答格式
若用户问的是考勤相关的信息，请返回：
```
<考勤>
```

若用户问的是工单相关的信息，请返回：
```
<工单>
```

若用户问的是告警相关的信息，请返回：
```
<告警>
```

若用户问的是资产相关的信息，请返回：
```
<资产>
```
"""

NER_SYS="""\
# 角色
你是nl2sql任务中的语义解析专家，你的任务不是构造SQL语句，而是解析用户问题的实体。

# 具体任务描述
我会给你用户的自然语言查询问题（<用户问题>），与相关数据表的schemas（<table_schemas>），
你需要根据<用户问题>与<table_schemas>，解析出用户问题中可能涉及到的实体，并返回解析结果。

## 注意事项
1. 你最应该识别的实体应该是可能的项目名、地区名、品牌名、公司名等，不应该包括时间等不需要的实体。你可以参考下面的<示例>
2. 你的输出可以应遵循我下面给的<输出模板>
3. 目前任务较为简单，一般只涉及一个实体

<输出模板>
```json
{
  "实体": List[str]  // 填入识别出的实体。若没有，可以返回空列表
}
```
</输出模板>

下面是你可以参考的示例
### 示例
<示例1>
<用户问题>
华北今年每个月订单量增长怎么样？</用户问题>

## 你
```json
{"实体": ["华北"]}
```
</示例1>

<示例2>
<用户问题>
查询下去年1月腾讯的工单数量</用户问题>

## 你
```json
{"实体": ["腾讯"]}
```
</示例2>

<示例3>
<用户问题>
统计下信创安全的考勤结果</用户问题>

## 你
```json
{"实体": ["信创安全"]}
```
</示例3>

<示例4>
<用户问题>
今天异常工单</用户问题>

## 你
```json
{"实体": []}
```
</示例4>
"""

DETERMINE_SEMANTICS_SYS="""\
# 角色
你是一名nl2sql的语义解析专家。我需要你通过多轮对话的方式确定用户问题的具体指代语义。

# 任务描述
因为用户问题有时可能很模糊，部分实体涉及多个数据表的多个字段，所以可能需要你、或者返回给用户判断其需要查询的语义。
我会给你用户的自然语言查询问题（<用户问题>），相关数据表的schemas（<table_schemas>），
相关实体（<entities>），以及通过模糊查询实体给出的字段名（<fuzzy_fields>），补充用户问题具体要查询的含义。

## 注意事项
1. 若你可以直接确定实体指代的语义，可以直接根据下面的<最终输出模板>给出结果
2. 若你无法直接确定结果，你可以通过多轮对话询问用户，让用户确定具体语义
但是注意，用户是不懂SQL语句以及数据表结果的人，你应该使用别名，并尽量通过单选题的方式，让用户做选择，而不是做填空
3. 注意`xmlData`字段，我给你的对应的<fuzzy_fields>模板如：`["xmlData./Items/WFItem[@name='<字段名>']"]`。
其别名写在了<table_schema>中的`XmlData 字段内容说明`
4. 若通过对话确定结果，请通过下面的<最终输出模板>给出结果
注意，没确定结果前，不需要根据<最终输出模板>返回json格式，直接给出你需要问的问题
5. 注意对于多个数据表的多个字段，若是别名不一样，他们基本就是不一样的字段，都需要使用别名列出来，让用户选择
6. 目前项目涉及的问题较为简单，一般只涉及单个实体，因此仅需确定单个实体的语义
7. 你的思考不要太长，也不要反复检查，最好一次过。可以参考下面的<示例>看下如何正确快速地思考（<think>）
8. **注意 fuzzy_fields 里的库内实际值**：条目形如 `表名.字段名=库内实际值` 时，`=` 后面是数据库里真实存储的名称。确定语义时必须把这个真实名称原样写进结果，例如 `业务名称（中山市协同办公平台）`，不要只写字段名、也不要改写这个名称。同一字段给了多个候选值时，若都明显对应同一实体（如主系统与其灾备系统），可以全部列出。

## 最终输出模板
```json
{
    "确定语义": List[str] // 填入确定要查询的语义
}
```

上述描述可能有点复杂，可以参考下面的示例：
### 示例
<示例1>
## User
<table_schemas>
...
表名: project
表结构:
|字段名 | ... | 备注说明 |
|------| ... | ------- |
|name  | ... | 项目名称 |
...
表名: public_project
表结构:
|字段名 | ... | 备注说明 |
|------| ... | ------- |
| id | ... | 公共项目ID |
| name | ... | 公共项目名称 |
...
表名: attendance
表结构:
|字段名 | ... | 备注说明 |
|------| ... | ------- |
| project_name | ... | 项目名称 |
| public_project_name | ... | 公共项目名称 |
| status | ... | 考勤状态 |
...
</table_schemas>

<用户问题>
统计下信创安全的考勤结果</用户问题>

<entities>
["信创安全"]</entities>

<fuzzy_fields>
["project.name", "public_project.name","attendance.public_project_name"]</fuzzy_fields>

## Assistant
<think>
注意到<fuzzy_fields>中有不少与"信创安全"相关的字段，但总结起来有歧义的语义就两类：项目名称与公共项目名称。
我需要用通俗的自然语言向用户确认"信创安全"具体指哪类。
</think>
您好，"信创安全"有多种语义，请问您想查询哪个？
(A) 项目名称
(B) 公共项目名称

## User
B

## Assistant
<think>用户选择了公共项目名称，则确认用户询问的"信创安全"是指公共项目名。
</think>
获取确定语义，最终结果如下：
```json
{"确定语义": ["公共项目名"]}
```
</示例1>

<示例2>
## User
<table_schemas>
...
表名: project
表结构:
|字段名 | ... | 备注说明 |
|------| ... | ------- |
|name  | ... | 项目名称 |
...
表名: company
表结构:
|字段名 | ... | 备注说明 |
|------| ... | ------- |
|name  | ... | 公司名称 |
...
表名: sales_volume
表结构:
|字段名 | ... | 备注说明 |
|------| ... | ------- |
| company_name | ... | 公司名称 |
| project_name | ... | 项目名称 |
| volume | ... | 销售量 |
...
</table_schemas>

<用户问题>
统计下信创安全这个项目的销售额</用户问题>

<entities>
["信创安全"]</entities>

<fuzzy_fields>
["project.name", "company.name","sales_volume.company_name","sales_volume.project_name"]</fuzzy_fields>

## Assistant
<think>
注意到<fuzzy_fields>中有不少与"信创安全"相关的字段，但总结起来的语义就两类：公司名称与项目名称。
而<用户问题>也明确指出了要查询的是项目的销售额，因此可以直接确定"信创安全"是指项目名。
</think>
获取确定语义，最终结果如下：
```json
{"确定语义": ["项目名"]}
```
</示例2>
"""

# 2. 你可以在你的<think>中思考，但是你润色的最终结果需要用"<润色后>"这个xml标签裹住。
POLISH_SYS="""\
因为用户是不懂SQL语句的小白，所以我需要你根据给你的SQL表结构与视图结构（<SQL表与视图结构>），
润色用户用于查询的自然语言（<用户问题>）。

# 当前查询领域
{intent_desc}

# 要求
1. 我不需要你生成SQL语句，我只需要你润色用户查询的自然语言，因此你的输出仍然是一串自然语言，只是丰富、具体了需要的SQL信息
2. 注意<SQL表与视图结构>中部分表的`XmlData 字段内容说明`中也包含了部分字段，润色时需要注意
3. 你最好思考后再给出答案，但是你润色的最终结果需要用"<润色后>"这个xml标签裹住。不要漏了"</润色后>"这个尾标签
4. **严格约束**：润色时只能使用<SQL表与视图结构>中实际存在的表名和字段名，禁止引入任何表中不存在的概念或字段。上述"当前查询领域"已经明确了你只能使用的表和字段范围，禁止混入其他领域的术语
5. **禁止指定返回字段**：除非用户原始问题中明确说了要查哪些字段，否则润色时不允许指定返回字段列表。只需描述查询条件和使用的表即可，让SQL生成阶段自行决定字段。
6. **必须保留全部实体与限定条件**：用户问题中的系统名称、设备名称、单位名称、人名、部门等专有名词，以及时间范围（近三天/近一周/本月等）和数量限制，必须原样出现在润色结果中，禁止省略、概括、替换或换成同义词。
7. **禁止推导或排除业务取值**：考勤状态、告警状态这类枚举字段，不准自己推理出"不为X、不为Y"之类的取反条件，也不准把用户的口语换成你理解的几个取值；用户怎么说就保留怎么说（如"没考勤的人"原样保留"没考勤"），具体取值映射交给后面的SQL生成阶段。

# 今日时间
{datetime_today}

<SQL表与视图结构>
{table_view_struct}
</SQL表与视图结构>

# 示例输出
<润色后>
...
</润色后>
"""


GENERATE_SYS_V2="""\
你是一名MySQL语言专家。我会提供给你用户自然语言查询问题（<用户问题>）与缓存的SQL语句模板（<SQL缓存模板>），
我需要你根据我提供的信息，判断是否有合适的<SQL缓存模板>、并根据模板输出结果。

# 具体步骤
1. 判断是否有<SQL缓存模板>能满足回答<用户问题>：
  - 若有：缓存命中，跳转至点2
  - 若没有：跳转至点3
2. 提取出该模板，根据下面的命中生成要求（<命中时要求>）生成MySQL可执行的查询语句
3. 根据下面的未命中生成要求（<未命中时要求>）生成MySQL可执行的查询语句

## 通用要求
1. **必须返回所有字段**：除非用户明确要求查询特定字段，否则必须使用SELECT * 查询所有字段，严禁自行挑选或裁剪字段。
2. 请尽量思考简洁点，不要在思考过程中复述不需要复述的内容，提高效率
3. 注意今日时间已在下<今日时间>中给出，若<用户问题>中仅说明要查询如”今年”、”最近一个月”的时间区间，请以<今日时间>为准
4. 最终结果请用xml标签”<sql>”裹住，且只允许放可以执行的sql语句，不允许添加注释。生成SQL时必须确保关键字前后有空格（如”FROM “、” ON “、” LEFT JOIN “等），严禁把字段名和关键字连在一起（如”名称FROM”是错误的，必须写成”名称 FROM”）。
5. 用户询问具体实体时，如”查询腾讯公司的年报”，生成的SQL的WHERE语句建议用LIKE，不应该直接写等号。因为数据库中的值记录的不一定是”腾讯公司”，可能是”腾讯”、”腾讯科技有限公司”等。
6. 引用中文字段名时必须保持原样，不得在字段名中插入空格。例如字段名”主机id”应写成”主机id”，不能写成”主机 ID”。直接照搬<相关数据表结构>中的字段名即可。
7. **严禁编造字段名**：WHERE条件中使用的字段名必须存在于<相关数据表结构>中，绝不能自己编造不存在的字段。如果用户的查询条件无法匹配表中任何字段，应使用LIKE在文本字段（如”设备名称”、”告警信息”等）中模糊搜索，而不是编造新字段。

## 命中时要求
1. 命中时一般只需要你修改对应语句模板内"BETWEEN <datetime1> AND <datetime2>"的时间（注意时间遵循格式: "%Y-%m-%d"）、或者新增关键词过滤即可（"CASE ... WHEN ... AS ..."）
2. 若需要在模板基础上新增查询的列，非中文时用"AS"语句转中文，也要注意中文字段要用英文双引号"\""裹住

## 未命中时要求
1. 请根据提供的表结构信息（<相关数据表结构>）与注意事项（<注意事项>）生成语句
2. 禁止使用子查询
3. 字段名若是英文，请用"AS"语句转成中文。也要注意中文字段要用英文双引号"\""裹住


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
5. 请尽量思考简洁点，不要在思考过程中复述不需要复述的内容，提高效率

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
考勤查询优先使用 imoc_attendance_all 视图（已开通访问权限）。该视图已按人按天汇总好人员、单位、项目、班次和考勤状态，一条SQL即可完成，不要再去关联底表。
视图字段（全中文）：
- 用户名称、单位名称、项目名称、排班名称、班次名称、值班日期、值班时间、打卡时间、考勤状态、是否申诉、是否请假
- 考勤状态为中文，取值：未到岗、早退、缺勤、未签到、正常、迟到早退、迟到、未签退；异常状态为：早退、未签退、缺勤、迟到
使用规则：
1. 问"谁/哪些人/人员/人员名单/姓名/迟到的人/缺勤的人"时，直接输出"用户名称"列，不需要JOIN任何人员表。
2. 过滤状态用中文，如：考勤状态 = '缺勤'、考勤状态 = '迟到'。
3. 只有当用户明确要求视图里没有的字段（如用户ID、手机号、部门ID、项目ID等）时，才改用下面的底表。
4. 口语说法到状态值的对应（用户很少说标准状态名）：
- "迟到" → 考勤状态 = '迟到'；"早退" → '早退'；"迟到早退" → '迟到早退'
- "缺勤/没来/旷工" → 考勤状态 = '缺勤'
- "没签退/没打下班卡" → 考勤状态 = '未签退'
- "没考勤/未考勤/没打卡/未打卡/没有考勤记录" → 这些口语指当天没有打卡，不止对应某一个状态，必须写成 考勤状态 IN ('缺勤','未到岗','未签到')，不要只写其中一个（单写 '未到岗' 经常当天查不到数据）。"打卡时间"为空也表示当天没有打卡记录。
- "考勤异常" → 考勤状态 IN ('早退','未签退','缺勤','迟到','迟到早退')
5. 拿不准某个中文状态当天有没有数据时，用 IN 组合覆盖多个可能状态，不要凭感觉只写一个状态值；状态名只能取自上面的中文取值，不能编造英文或近义词。

底表（仅在上面的场景下使用）：
- imoc_class_duty_user: 人员排班记录表（主表）
- imoc_class_user: 考勤人员信息表（通过userid关联）
- imoc_checkin_user: 打卡记录表（通过userid关联）
- imoc_class_duty: 排班表
- imoc_class_project: 项目表
- imoc_class_appeal: 申诉表
底表字段映射：
- 值班日期 → imoc_class_duty_user.duty_date
- 值班时间 → imoc_class_duty_user.duty_time
- 打卡时间 → imoc_class_duty_user.checkin_time
- 考勤状态 → imoc_class_duty_user.status（中文取值同视图）
- duty_status 是英文旧字段，值里没有中文"迟到""缺勤"等，任何情况下禁止使用
- 用底表问人员名单时，必须 INNER JOIN imoc_class_user ON imoc_class_duty_user.userid = imoc_class_user.userid，并输出 imoc_class_user.name 作为人员姓名
- 用户名称 → imoc_class_user.name
- 单位名称 → lwops_org_groups.name（imoc_class_user.groupid = lwops_org_groups.id）
- 项目名称 → imoc_class_project.name（imoc_class_duty_user.project_id = imoc_class_project.id）
- 班次名称 → imoc_class.name（imoc_class_duty_user.class_id = imoc_class.id）
注意：绝不可使用sys_user、users、imoc_user等表。
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
8. **工时口径（重要）**：WF_TotalTime 是 varchar 字段，**单位是分钟，不是小时**。判断"N 小时"必须换算成分钟：
   - "超过 72 小时" → `CAST(WF_TotalTime AS UNSIGNED) > 4320`（72×60），**绝不能写成 > 72**，那等于 72 分钟，结果会大 60 倍
   - 只用 WF_TotalTime 比较，不要用 TIMESTAMPDIFF 重新计算时间差
9. **WF_Status 取值**：bpm_maindata 中是 `Current`（审批中）/ `Draft`（草稿）/ `Pause`（暂停），bpm_archiveddata 中是 `ARC`。
   - 两表 union all 统计时**禁止加 wf_status 过滤条件**，否则会把 maindata 的数据全部过滤掉（maindata 里没有 ARC）
   - 只有在用户明确要求"只看审批中""只看已归档"时才分别加 Current / ARC
"""
# 8. xmldata在存储下拉组件的数据时会多存储一个”字段名称_show“的字段，用于记录选中项的label中文值，强调也可能不存在”字段名称_show“，使用该字段时必须判断有没有存在该字段后再使用，例如：project为下拉组件则`/Items/WFItem["project”]存储为项目的ID值，`/Items/WFItem["project_show”]`为项目的中文名称。



# 告警注意事项
ALERT_NOTE="""\
PostgreSQL数据库，三张视图(view_alert_all主表，view_alert_organization单位表，view_alert_business业务表)必须LEFT JOIN通过"主机id"关联。
禁止返回字段：主机id、事件id、触发器id。
严格按此SQL模板生成（字段顺序不可变），WHERE条件根据用户问题填入：

SELECT
  o."单位名称",
  b."业务名称",
  a."设备名称",
  a."告警信息",
  a."告警等级",
  a."告警时间",
  a."恢复时间",
  a."状态",
  a."确认状态",
  a."确认人",
  a."关闭人"
FROM view_alert_all a
LEFT JOIN view_alert_organization o ON a."主机id" = o."主机id"
LEFT JOIN view_alert_business b ON a."主机id" = b."主机id"
WHERE <在这里填入查询条件>

名称类条件必须用LIKE模糊匹配，禁止用等值比较：用户口语名称常与库内正式名称不完全一致
（例如用户说"协同办公系统"，库内实际为"中山市协同办公平台"），
应写成 b."业务名称" LIKE '%协同办公%' 而不是 b."业务名称" = '协同办公系统'。
"""


# 资产注意事项（CMDB 直查 API 模式，不再走 SQL 网关）
ASSET_NOTE="""\
资产数据按模型分散在多张 cmdb_asset_<object_id> 表中（每类资产模型一张表），
模型与表名的对应关系在注册表 cmdb_asset_models（object_id、name、table_name、category_top、category_next、instance_count）中维护。
规则：
1. 查询参数中只能使用表结构说明里真实存在的中文字段名（如 型号、厂家、状态、维护编号），不得编造字段。
2. 用户问到具体资产类型（如"UPS设备"）时，用 "model" 填模型中文名即可（推荐），或填表结构说明中的 object_id（表名 cmdb_asset_<object_id> 的后缀部分）。
3. 用户问的是分类级别（如 服务器、网络设备、存储设备、安全设备、机房环境设备）时，用 "category" 字段填分类名，不要用 model/object_id。分类级支持三种 query_type：count（分类总数）、group_count（按模型分组计数）、list（返回明细，结果列为「模型、实例名称」，无需指定 fields）。
4. 注册表 cmdb_asset_models 是服务端内部元数据表，不能作为查询目标，不要把它填进任何参数。
5. 禁止输出占位符或编造 object_id；不确定 object_id 时用 "model"（中文模型名）或 "category"（分类名），由服务端解析。
6. filters 的 condition 取值与含义：incl=包含、eq=等于、uneq=不等于、excl=不包含、empty=为空、unempty=不为空；empty/unempty 时 values 用空数组。
7. 数量统计用 query_type=count；按字段分组统计数量用 group_count 并给出 group_by（必须是对应模型表结构中存在的字段）；看明细列表用 list 并给出 fields。
8. 展示字段优先用 instance_name 与中文属性列；instance_id、object_id、creator、create_time、update_time、synced_at 为内部技术字段，一般不要返回。
"""


# 资产查询参数生成系统提示词（CMDB 直查模式）
ASSET_QUERY_SYS="""\
# 角色
你是资产管理领域的数据查询专家，负责把用户的查询需求转换为 CMDB 资产查询接口（instance/list）的 JSON 查询参数，由服务端执行并完成统计。

# 输入
- 今天是：{datetime_today}
- 可选资产数据表结构（表名、中文模型名与中文字段名）：
{table_descs}

# 注意事项
{note}

# 任务
根据用户问题生成 JSON 查询参数，并用 <query_params> 与 </query_params> 标签包裹。

JSON 结构说明：
{{
  "object_id": "资产模型ID（如 64c9bf804dacd），与 model 二选一即可",
  "model": "模型中文名（如 UPS设备）",
  "category": "分类名（如 服务器、网络设备），用户问分类级别的问题时使用，与 model/object_id 互斥；分类级 list 返回 模型+实例名称，不用给 fields",
  "keyword": "关键字搜索，无则空串",
  "query_type": "list / count / group_count 三选一",
  "filters": [
    {{"name": "中文字段名", "condition": "incl/eq/uneq/excl/empty/unempty", "values": ["过滤值"], "true_name": false}}
  ],
  "group_by": "分组字段的中文名（仅 group_count 需要）",
  "fields": ["要返回的中文字段名列表（仅 list 需要，缺省只返回 instance_name）"],
  "limit": 200
}}

limit 规则：默认 200；用户明确要求"全部/所有/列出"时设较大的值（最多 2000）。

# 输出格式
<query_params>
{{ ...JSON... }}
</query_params>
"""


# 资产查询参数修正反馈提示词（重试时使用，替代 SQL 版 FEEDBACK_SYS）
FEEDBACK_ASSET_SYS="""\
资产查询参数执行失败。错误信息：
{error_msg}

请分析错误原因，并重新生成正确的查询参数 JSON（放在 <query_params> 标签内）。注意：object_id 必须来自表结构说明中真实存在的表名后缀，禁止占位符；分类级别问题用 "category" 字段；model 用模型中文名。
"""


# 告警表描述
ALERT_TABLE_DESCRIPTIONS = [
'表名：view_alert_all: 设备告警记录表，用于记录设备的每一次告警信息，包含告警等级、告警时间、恢复时间、确认状态等。\n表字段：\n主机id: 设备主机的id值\n事件id: 告警事件id\n触发器id: 告警模版的id值\n设备名称: 设备名称\n告警信息: 告警信息的详细描述\n告警等级: 告警的严重等级\n告警时间: 告警发生的时间\n恢复时间: 告警恢复的时间\n状态: 告警是否恢复的状态\n确认状态: 告警确认的状态\n确认人: 确认告警人\n关闭人: 关闭告警人',
'表名：view_alert_organization: 设备所属单位表，记录设备主机所属的单位信息，通过主机id与告警记录关联。\n表字段：\n主机id: 设备主机的ID值\n单位名称: 主机所属单位的名称',
'表名：view_alert_business: 设备所属业务表，记录设备主机所属的业务信息，通过主机id与告警记录关联。\n表字段：\n主机id: 设备主机的ID值\n业务名称: 主机所属业务的名称',
]

ATTENDANCE_TABLE_DESCRIPTIONS = [
'表名：imoc_attendance_all: 人员考勤记录表（视图，已开通访问权限，考勤查询优先使用）。按人按天记录考勤，已包含人员、单位、项目、班次的中文名称，无需关联其他表。\n表字段：\n用户名称: 用户姓名\n单位名称: 单位名称\n项目名称: 项目名称\n排班名称: 排班名称\n班次名称: 班次名称\n值班日期: 值班日期\n值班时间: 值班时间\n打卡时间: 打卡时间，为空表示当天没有打卡记录\n考勤状态: 考勤状态，中文取值：未到岗，早退，缺勤，未签到，正常，迟到早退，迟到，未签退；异常状态：早退、未签退、缺勤、迟到。口语"没考勤/没打卡"对应 考勤状态 IN (缺勤,未到岗,未签到)，不要只写未到岗\n是否申诉: 是否申诉\n是否请假: 是否请假',
'表名：imoc_checkin_user: 考勤人员打卡记录表，用于记录人员的每一次打卡记录，反映员工考勤情况。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nuserid: 用户ID，关联用户表，标识打卡人员\nproject_id: 项目ID，关联项目表，标识打卡所属项目\nduty_id: 排班ID，关联排班表，标识打卡对应的排班\nclass_id: 班次ID，关联班次表，标识打卡对应的班次\nrange_id: 时间段ID，关联时间段表，标识打卡对应的时间段\nrelated_id: 关联duty_user的ID，用于关联人员排班记录\ntype: 类型，标识打卡类型\nrange_start_time: 考勤上班时间，记录规定的上班时间\nrange_end_time: 考勤下班时间，记录规定的下班时间\ntertian: 是否隔日，标识是否跨天\nduty_date: 值班日期，记录具体的值班日期\nduty_location: 值班打卡位置，记录规定的打卡位置\nlocation: 实际打卡位置，记录实际打卡的位置\nlng: 经度，记录打卡位置的经度坐标\nlat: 纬度，记录打卡位置的纬度坐标\nstatus: 状态，记录打卡状态\ncreate_time: 创建时间，记录创建时间戳\nupdate_time: 更新时间，记录最后更新时间戳\nis_del: 是否删除，标识数据是否已删除\nis_manual: 是否手动签到，标识是否为手动签到记录',
'表名：imoc_class: 考勤班次表，用于配置考勤班次，定义班次基本信息和规则。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nname: 班次名称，标识班次的名称\nendure_minutes: 容忍时间，记录打卡容忍的时间范围（分钟）\ninfo: 说明，记录班次的补充说明信息\ncreate_time: 创建时间，记录创建时间戳\ncreate_userid: 创建用户ID，记录创建该班次的用户\nupdate_time: 更新时间，记录最后更新时间戳\nupdate_userid: 更新用户ID，记录最后更新该班次的用户\nis_del: 是否删除，标识数据是否已删除',
'表名：imoc_class_duty: 考勤排班表，记录每个排班项目的排班安排，每个项目可以有多个排班。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nproject_id: 项目ID，关联项目表，标识排班所属项目\nclass_id: 班次ID，关联班次表，标识排班使用的班次\nstart_date: 开始日期，记录排班开始日期\nend_date: 结束日期，记录排班结束日期\ntype: 值班方式，记录值班的方式类型\nremark: 备注，记录排班的补充说明信息\nstatus: 状态，记录排班状态\ncreate_time: 创建时间，记录创建时间戳\ncreate_userid: 创建用户ID，记录创建该排班的用户\nupdate_time: 更新时间，记录最后更新时间戳\nupdate_userid: 更新用户ID，记录最后更新该排班的用户\nis_del: 是否删除，标识数据是否已删除',
'表名：imoc_class_duty_user: 考勤人员排班记录表，记录人员每一天具体上什么班次，反映人员排班情况。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nuserid: 用户ID，关联用户表，标识排班人员\nproject_id: 项目ID，关联项目表，标识排班所属项目\nduty_id: 排班ID，关联排班表，标识具体排班\nclass_id: 班次ID，关联班次表，标识使用的班次\nteam_id: 队伍ID，关联队伍表，标识所属队伍\nduty_date: 值班日期，记录具体的值班日期\nduty_time: 考勤时间，记录规定的考勤时间\nduty_status: 考勤状态（英文旧字段，禁止使用，考勤状态请用status）\ncheckin_time: 签到时间，记录实际签到时间\ncheckin_location: 签到位置，记录实际签到位置\ntype: 值班类型，记录值班的类型\nstatus: 考勤状态（中文，选项：未到岗，早退，缺勤，未签到，正常，迟到早退，迟到，未签退）\ncreate_time: 创建时间，记录创建时间戳\nupdate_time: 更新时间，记录最后更新时间戳\nis_del: 是否删除，标识数据是否已删除',
'表名：imoc_class_project: 考勤排班项目表，记录考勤排班项目信息。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nname: 项目名称，记录项目名称\nis_insance: 是否重保，标识是否为重要保障项目\ncreate_time: 创建时间，记录创建时间戳\ncreate_userid: 创建用户ID，记录创建该项目的用户\nupdate_time: 更新时间，记录最后更新时间戳\nupdate_userid: 更新用户ID，记录最后更新该项目的用户\nis_del: 是否删除，标识数据是否已删除\nstatus: 状态，记录项目状态',
'表名：imoc_class_range: 考勤班次时段表，记录每个班次的多个上班时间段。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nclass_id: 班次ID，关联班次表，标识所属班次\nstart_time: 开始时间，记录时段开始时间\nend_time: 结束时间，记录时段结束时间\ntertian: 是否隔日，标识是否跨天',
'表名：imoc_class_team: 考勤团队表，记录团队信息。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nuser_id: 用户ID，关联用户表，标识团队成员\nproject_id: 项目ID，关联项目表，标识团队所属项目\nclass_id: 班次ID，关联班次表，标识团队使用的班次\nduty_id: 排班ID，关联排班表，标识团队对应的排班',
'表名：imoc_class_user: 考勤人员记录表，记录考勤人员信息。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nuserid: 用户ID，关联用户表，标识考勤人员\ngroupid: 部门ID，关联部门表，标识所属部门\ntype: 适用对象，记录人员类型\nmobile: 手机号码，记录人员联系方式\nlocation: 位置，记录人员位置信息\ncreate_time: 创建时间，记录创建时间戳\ncreate_userid: 创建用户ID，记录创建该记录的用户\nupdate_time: 更新时间，记录最后更新时间戳\nupdate_userid: 更新用户ID，记录最后更新该记录的用户\nis_del: 是否删除，标识数据是否已删除\nname: 姓名，记录人员姓名',
'表名：imoc_class_appeal: 考勤申诉表，用于异常考勤的申诉处理，申诉通过后可订正为正常状态。\n表字段：\nid: 主键ID，无业务含义，用于数据唯一标识\nduty_id: 值班ID，关联值班表，标识申诉对应的值班记录\ntype: 类型，记录申诉类型\nstart_time: 开始时间，记录申诉开始时间\nend_time: 结束时间，记录申诉结束时间\nreson: 请假原因，记录申诉原因\npic_url: 请假图片，记录申诉相关的图片URL\nstatus: 状态，记录申诉状态\nreject_reson: 拒绝理由，记录拒绝申诉的理由\ngov_reject_reson: 业主拒绝理由，记录业主拒绝申诉的理由\ncreate_userid: 申请人uid，记录申诉申请人\ncreate_time: 申请时间，记录申诉申请时间戳\nupdate_time: 更新时间，记录最后更新时间戳\napprove_user: 审批人员，记录审批人姓名\napprove_userid: 审批人ID，记录审批人ID\napprove_time: 审批时间，记录审批时间戳\ngov_approve_user: 业主审批人员，记录业主审批人姓名\ngov_approve_userid: 业主审批人ID，记录业主审批人ID\ngov_approve_time: 业主审批时间，记录业主审批时间戳\nis_del: 是否删除，标识数据是否已删除',
]


BPM_TABLE_DESCRIPTIONS = [
"### 7.1 流程模型中的流程过程属性表 (BPM_ModProcessList)\n\n流程模型中的流程过程属性\n\n| 字段名称 | 主键 | 字段类型 | 长度 | 是否为空 | 默认值 | 字段说明 |\n| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n| WF_OrUnid | Y | varchar | 50 | N | 无 | 32 位唯一 ID 号 |\n| WF_Appid | N | varchar | 50 | N | 无 | 所属应用 |\n| Processid | N | varchar | 100 | N | 无 | 流程 ID 号 |\n| Nodeid | N | varchar | 10 | N | ('Process') | 节点 id |\n| NodeType | N | varchar | 20 | N | ('Process') | 节点主类型 |\n| ExtNodeType | N | varchar | 50 | N | ('process') | 节点扩展类型 |\n| NodeName | N | varchar | 150 | N | 无 | 流程名称 |\n| ProcessNumber | N | varchar | 50 | Y | 无 | 流程编号 |\n| OtherProcessName | N | varchar | 150 | Y | ('') | 流程别名 |\n| Folderid | N | varchar | 50 | Y | 无 | 所属文件夹 |\n| Status | N | varchar | 50 | Y | ('0') | 1 表示发布，0 表示暂停 |\n| Deptid | N | varchar | 50 | Y | ('') | 所属部门 id |\n| ProcessOwner | N | varchar | 150 | Y | ('') | 流程所有者 |\n| ProcessReader | N | varchar | 1000 | Y | ('') | 流程全局读者 |\n| ProcessDesigner | N | varchar | 250 | Y | ('') | 流程设计者 |\n| ProcessStarter | N | varchar | 500 | Y | ('') | 有权启动者 |\n| FormNumber | N | varchar | 50 | Y | ('') | 所使用的表单 id |\n| FormNumberForMobile | N | varchar | 50 | Y | ('') | 移动审批表单 |\n| SortNum | N | varchar | 50 | Y | ('1001') | 同级排序号 |\n| SaveDataHistory | N | char | 1 | Y | ('0') | 1 表示存表单历史数据，0 表示不存 |\n| icons | N | varchar | 150 | Y | ('') | 流程图标地址 |\n| ExceedTime | N | varchar | 10 | Y | ('0') | 流程持继时间 |\n| AutoArchive | N | char | 1 | Y | ('1') | 1 表示自动归档空表示否 |\n| WordTemplate | N | varchar | 50 | Y | 无 | Word 正文模板 |\n| PrintTemplate | N | varchar | 50 | Y | 无 | 打印模板 |\n| WF_Version | N | varchar | 50 | Y | ('1.0') | 版本号 |\n| WF_AddName_CN | N | varchar | 50 | Y | 无 | 创建者 |\n| WF_AddName | N | varchar | 50 | Y | 无 | 创建者 |\n| WF_DocCreated | N | varchar | 50 | Y | 无 | 创建时间 |\n| WF_LastModified | N | varchar | 50 | Y | 无 | 最后更新时间 |\n| XmlData | N | xml | -1 | Y | ('') | XML 扩展数据 |",
"### 7.2 流程实例主数据表 (BPM_MainData)\n\n流程实例主数据，在流转中的流程实例存在本表中，流程结束后就会归档到 BPM_ArchivedData 表中去，这两张表必须保持一致性。\n\n| 字段名称 | 主键 | 字段类型 | 长度 | 是否为空 | 默认值 | 字段说明 |\n| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n| WF_OrUnid | Y | varchar | 50 | N | 无 | 文档 32 位唯一标识一般与 WF_DocUNID 相等 |\n| Subject | N | varchar | 300 | N | 无 | 文档标题，此字段发送待办邮件时必须 |\n| WF_Appid | N | varchar | 30 | Y | 无 | 所属应用的 ID 号 |\n| WF_Processid | N | varchar | 50 | Y | 无 | 此文档使用的流程 ID 号 |\n| WF_ProcessName | N | varchar | 250 | Y | 无 | 流程名称 |\n| WF_AddName | N | varchar | 30 | Y | 无 | 流程启动者的英文名 |\n| WF_AddName_CN | N | varchar | 50 | Y | 无 | 流程启动者的中文名 |\n| WF_Author | N | varchar | 8000 | Y | 无 | 当前审批者，此字段的内容会存入到 WF_AllAuthors 中 |\n| WF_Author_CN | N | varchar | 8000 | Y | 无 | 当前审批者的中文名，与 WF_Author 一一对应 |\n| WF_EndUser | N | varchar | 8000 | Y | 无 | 已审批结束的用户列表，此字段值会合并到 WF_AllReaders 中 |\n| WF_AllReaders | N | varchar | 8000 | Y | 无 | 所有有权访问本文档的用户列表 |\n| WF_CopyUser | N | varchar | 8000 | Y | 无 | 传阅用户列表 |\n| WF_DocNumber | N | varchar | 30 | Y | 无 | 流水单号系统自动生成，当需要自定义流水号时可以覆盖此字段 |\n| WF_CurrentNodeid | N | varchar | 100 | Y | 无 | 当前所在节点 id |\n| WF_CurrentNodeName | N | varchar | 500 | Y | 无 | 流程当前所处的节点名称，当有多个时用逗号分隔，要想得到每个用户具体在那个环节请从 WF_CurUserStatus 字段中获取 |\n| WF_Status | N | varchar | 30 | Y | 无 | 流程当前状态，Current 表示审批中，End 表示已结束，Draft 表示草稿 |\n| WF_VersionNumber | N | varchar | 30 | Y | ('') | 当前文档的版本号 |\n| WF_SourceEntrustUserid | N | varchar | 200 | Y | 无 | 参与此文档的且设置了代办的用户，显示被代办文档时用 |\n| WF_TargetEntrustUserid | N | varchar | 200 | Y | 无 | 代办的用户列表，记录那些用户是代办的 |\n| WF_ProcessNumber | N | varchar | 30 | Y | 无 | 过程属性中指定的流程编号 |\n| WF_MainNodeid | N | varchar | 50 | Y | ('') | 主流程中启动本节点 Nodeid 如果没有则为空值 |\n| WF_MainDocUnid | N | varchar | 50 | Y | ('') | 如果是子流程则有主文档的唯一编号 |\n| WF_TotalTime | N | varchar | 10 | Y | 无 | 总耗时 |\n| WF_EndTime | N | varchar | 30 | Y | ('') | 文档办结时间，文档结束后会自动生成 |\n| WF_BusinessNum | N | varchar | 50 | Y | ('') | 所属业务场景唯一标识 |\n| WF_EndBusinessid | N | varchar | 30 | Y | ('') | 对应流程结束环节的业务状态标识 |\n| WF_Folderid | N | varchar | 30 | Y | ('') | 归档时此字段从自动活动中得到指定的归档文件夹编号 |\n| WF_TransFlag | N | varchar | 30 | Y | ('N') | 数据是否已传输到其他数据库表标记位 |\n| WF_ArcFormNumber | N | varchar | 30 | Y | ('') | 归档后显示表单的编号 |\n| WF_AddDeptid | N | varchar | 50 | Y | 无 | 起草人所在部门 ID 号 |\n| WF_Systemid | N | varchar | 30 | Y | 无 | 启动本流程的业务系统的 ID 号 |\n| WF_DocCreated | N | varchar | 30 | Y | 无 | 创建时间 |\n| WF_LastModified | N | varchar | 50 | Y | ('') | 最后更新时间 |\n| XmlData | N | xml | -1 | Y | 无 | 如果流程过程属性中选择 XmlData 表为数据主表，则系统会自动把表单字段组合成 xml 存入此字段中，否则会存入到 BPM_SubData 中 |\n\n> **XmlData 字段内容说明：**\n> 1. `unit` 为申请人单位\n> 2. `Project` 为所属项目\n> 3. `package` 为项目包\n> 4. `Subproject` 为子项目\n> 5. `ErrorType` 为故障类型或服务目录\n> 6. `Appsystem` 为应用系统\n> 7. `Detail` 为详情描述",
"### 7.3 流程实例归档表 (BPM_ArchivedData)\n\n流程实例归档表，所有流程实例结束后都会从 BPM_MainData 表中迁移到本表中来，同时 BPM_MainData 表中的数据会删除掉，本表结构必须与 BPM_MainData 表保持一致。\n\n| 字段名称 | 主键 | 字段类型 | 长度 | 是否为空 | 默认值 | 字段说明 |\n| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n| WF_OrUnid | Y | varchar | 50 | N | 无 | 文档 32 位唯一标识一般与 WF_DocUNID 相等 |\n| Subject | N | varchar | 300 | N | 无 | 文档标题，此字段发送待办邮件时必须 |\n| WF_Appid | N | varchar | 30 | Y | 无 | 所属应用的 ID 号 |\n| WF_Processid | N | varchar | 50 | Y | 无 | 此文档使用的流程 ID 号 |\n| WF_ProcessName | N | varchar | 250 | Y | 无 | 流程名称 |\n| WF_AddName | N | varchar | 30 | Y | 无 | 流程启动者的英文名 |\n| WF_AddName_CN | N | varchar | 50 | Y | 无 | 流程启动者的中文名 |\n| WF_Author | N | varchar | 8000 | Y | 无 | 当前审批者，此字段的内容会存入到 WF_AllAuthors 中 |\n| WF_Author_CN | N | varchar | 8000 | Y | 无 | 当前审批者的中文名，与 WF_Author 一一对应 |\n| WF_EndUser | N | varchar | 8000 | Y | 无 | 已审批结束的用户列表，此字段值会合并到 WF_AllReaders 中 |\n| WF_AllReaders | N | varchar | 8000 | Y | 无 | 所有有权访问本文档的用户列表 |\n| WF_CopyUser | N | varchar | 8000 | Y | 无 | 拷贝用户（备用） |\n| WF_DocNumber | N | varchar | 30 | Y | 无 | 流水单号系统自动生成，当需要自定义流水号时可以覆盖此字段 |\n| WF_CurrentNodeid | N | varchar | 100 | Y | 无 | 当前节点 id |\n| WF_CurrentNodeName | N | varchar | 500 | Y | 无 | 流程当前所处的节点名称，当有多个时用逗号分隔，要想得到每个用户具体在那个环节请从 WF_CurUserStatus 字段中获取 |\n| WF_Status | N | varchar | 30 | Y | 无 | 流程当前状态，Current 表示审批中，End 表示已结束，Draft 表示草稿 |\n| WF_VersionNumber | N | varchar | 30 | Y | 无 | 当前文档的版本号 |\n| WF_SourceEntrustUserid | N | varchar | 200 | Y | 无 | 参与此文档的且设置了代办的用户，显示被代办文档时用 |\n| WF_TargetEntrustUserid | N | varchar | 200 | Y | 无 | 代办的用户列表，记录那些用户是代办的 |\n| WF_ProcessNumber | N | varchar | 30 | Y | 无 | 过程属性中指定的流程编号 |\n| WF_MainNodeid | N | varchar | 50 | Y | 无 | 父文档的编号，如果没有父文档则为空值 |\n| WF_MainDocUnid | N | varchar | 50 | Y | 无 | 主文档的唯一编号，如果没有主文档则此字段与 WF_DocUNID 相等 |\n| WF_TotalTime | N | varchar | 10 | Y | 无 | 流程结束后的总耗时 |\n| WF_EndTime | N | varchar | 30 | Y | 无 | 文档办结时间，文档结束后会自动生成 |\n| WF_BusinessNum | N | varchar | 50 | Y | ('') | 所属业务场景唯一标识 |\n| WF_EndBusinessid | N | varchar | 30 | Y | 无 | 对应流程结束环节的业务状态标识 |\n| WF_Folderid | N | varchar | 30 | Y | 无 | 归档时此字段从自动活动中得到指定的归档文件夹编号 |\n| WF_TransFlag | N | varchar | 30 | Y | ('N') | 数据是否已传输到其他数据库表标记位，如果为 E 则表示文档有错误 |\n| WF_ArcFormNumber | N | varchar | 30 | Y | 无 | 归档后显示表单的编号 |\n| WF_AddDeptid | N | varchar | 50 | Y | 无 | 起草人所在部门 ID 号 |\n| WF_Systemid | N | varchar | 30 | Y | 无 | 启动本流程的业务系统的 ID 号 |\n| WF_DocCreated | N | varchar | 30 | Y | 无 | 创建时间 |\n| WF_LastModified | N | varchar | 50 | Y | (getdate()) | 最后更新时间 |\n| XmlData | N | xml | -1 | Y | 无 | 如果流程过程属性中选择 XmlData 表为数据主表，则系统会自动把表单字段组合成 xml 存入此字段中，否则会存入到 BPM_SubData 中 |\n\n> **XmlData 字段内容说明：**\n> 1. `unit` 为申请人单位\n> 2. `Project` 为所属项目\n> 3. `package` 为项目包\n> 4. `Subproject` 为子项目\n> 5. `ErrorType` 为故障类型或服务目录\n> 6. `Appsystem` 为应用系统\n> 7. `Detail` 为详情描述",
]


def _build_table_descriptions(records: list[TableSchemaRecord]) -> list[str]:
    """由表结构记录生成与 ALERT/ATTENDANCE_TABLE_DESCRIPTIONS 同格式的表描述列表。

    格式（对齐上方既有手写字面量的约定）：
      '表名：<table_name>: <描述>\\n表字段：\\n<字段名>: <备注>\\n...'
    注意：'表名：'/'表字段：' 用全角冒号；字段行分隔用半角冒号。
    api/endpoints/query.py::_strip_table_descs 依赖该约定：
    含全角冒号的行作为表头保留，字段行按第一个半角冒号截断只留字段名——
    若字段行误用全角冒号，字段名会被静默丢弃。
    """
    descs: list[str] = []
    for record in records:
        description = (record["description"] or record["table_comment"] or "").replace("\n", " ").strip()
        lines = [
            f"表名：{record['table_name']}: {description}",
            "表字段：",
        ]
        for _, row in record["schema_df"].iterrows():
            field = str(row.get("字段名") or "").strip()
            if not field:
                continue
            remark = str(row.get("备注说明") or "").strip().replace("\n", " ")
            # 备注为空也保留 "字段: " 形式：
            # _strip_table_descs 只认含半角冒号的行，裸字段名会被静默丢弃
            lines.append(f"{field}: {remark}")
        descs.append("\n".join(lines))
    return descs


# 资产表描述（由表定义 markdown 解析生成；正式/测试环境自动选择对应数据源，
# 表随同步脚本 --dump-md 更新）
ASSET_TABLE_DESCRIPTIONS = _build_table_descriptions(ASSET_ACTIVE_SCHEMA_RECORDS)



# 口径歧义检测：同一个问题存在多种合理解释、且不同解释会算出不同数字时，
# 先问用户选哪个口径，而不是让模型猜一个去生成 SQL。
AMBIGUITY_CHECK_SYS = """\
你是查询需求澄清助手。用户会用自然语言问数据库问题，你要判断：**这个问题有没有会导致不同 SQL、不同数字的歧义**。

## 什么时候需要问

只有当不同理解会**直接改变 SQL 的 WHERE / 统计字段 / 表**，并因此算出**明显不同的数字**时才问。

典型需要问的情况：
- **时间/时长口径**：按哪个字段算、"超过 N 小时"是用库里的总耗时字段还是用结束时间减创建时间
- **统计范围**：算全部历史还是只算某张表/某个状态；是否包含归档数据
- **字段口径**：同一个中文说法对应多个字段（如"处理时长"可能是总耗时字段，也可能是节点停留时间）
- **计数字段**：算条数、算去重后的人数、还是算某个字段的求和
- **状态口径**：用户说的"异常/超时/未完成"对应哪些具体状态值

## 什么时候不要问

- 能根据字段名、单位、默认习惯合理推断的（例如"今天"就是当天，"近一周"就是最近 7 天）
- 只是措辞含糊但 SQL 唯一的情况
- 只有一种解释时，一律不要问

**宁可少问，不要多问。**问题只在真的会算错数的时候提。

## 输出格式

严格输出一个 JSON 对象，不要输出任何其他文字，不要用 markdown 代码块包裹。

不需要问时：
{"ambiguous": false}

需要问时：
{"ambiguous": true, "question": "一句话说明要澄清什么（不要出现字段名以外的术语）", "options": [{"label": "选项短标题", "value": "选这个理解时等价的口径描述", "description": "这个口径具体怎么算，一句话"}]}

要求：
- options 给 2-4 个，互斥且覆盖主要合理理解
- label 不超过 12 个字，用户一眼能选
- description 说明"这样算会得到什么"，必要时带上字段名和单位
- question 里不要替用户做选择

## 示例

用户问："超72小时工单有多少张"（工单域，有时间字段 WF_TotalTime 单位分钟，也有 WF_DocCreated / WF_EndTime）
{"ambiguous": true, "question": "「超72小时」按哪个口径统计？", "options": [{"label": "按流程总耗时", "value": "WF_TotalTime（分钟）> 4320", "description": "用库里的总耗时字段，单位是分钟，72小时=4320分钟"}, {"label": "按创建到结束", "value": "TIMESTAMPDIFF(HOUR, WF_DocCreated, WF_EndTime) > 72", "description": "用结束时间减创建时间的自然时长，包含暂停和等待"}]}

用户问："今天有哪些告警"
{"ambiguous": false}
"""


CLARIFICATION_REPLY_SYS = """\
你在判断用户最新这条消息，是在回答上一轮的"口径澄清问题"，还是提出了一个新的查询问题。

<上一轮的口径问题>
{question}
</上一轮的口径问题>

<可选项>
{options}
</可选项>

判断规则：
1. 用户选了某个选项（回了字母、选项标题、或整行选项文字），或者说明了用哪个字段、哪种算法来统计 → **是在回答**（is_answer 为 true）
2. 用户只补充口径细节，如"按总耗时算""用结束时间减创建时间""不含暂停的" → **是在回答**
3. 用户换了一个查询诉求（换了对象、时间范围、指标，比如重新问数量、名单、明细） → **是新问题**（is_answer 为 false）
4. 这句话本身就是一个完整的问数据的句子（问多少、有哪些、列出、查一下），而它并不是在选口径 → **是新问题**
5. 拿不准时：看它更像"选口径"还是"换问题"，倾向按新问题处理——把新问题当口径会算出错误的数。

只输出一个 JSON 对象，不要输出任何其他文字，不要用 markdown 代码块包裹：
{{"is_answer": true}}
"""
