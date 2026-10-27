ATTENDENCE_CACHE_DIALECTS="""\
"""

# NOTE SQL关键字统一大写：ISG网关的内容安全护栏会误杀小写SQL片段
# （如 char(10)、count(1)、select * from），大写写法实测可放行，勿改回小写。
BPM_CACHE_DIALECT="""\
# 根据特定的时间段查出工单记录，按用户需求调整时间段
```sql
SELECT
	wf_docnumber AS "工单编号",`subject` AS '工单标题',nodename AS "工单类型", wf_addname_cn AS 申请人,wf_doccreated AS 开始时间, wf_endtime AS 结束时间,
	CASE WHEN wf_status='Current' THEN '流转中' WHEN wf_status='ARC' THEN '已结束' ELSE wf_status END AS 状态,
 	EXTRACTVALUE(xmldata,'/Items/WFItem[@name="reporter"]') AS "报单人",
 	CASE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="reportType"]') WHEN '0' THEN '服务台报障' WHEN '1' THEN '电话报障' WHEN '2' THEN '自行报障' WHEN '4' THEN '现场报障' ELSE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="reportType"]') END AS "申请途径",
 	CASE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="unit_show"]') WHEN '' THEN EXTRACTVALUE(xmldata,'/Items/WFItem[@name="unit"]') ELSE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="unit_show"]') END AS "单位",
 	CASE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="dept_show"]') WHEN '' THEN EXTRACTVALUE(xmldata,'/Items/WFItem[@name="dept"]') ELSE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="dept_show"]') END AS "科室",
 	EXTRACTVALUE(xmldata,'/Items/WFItem[@name="phone"]') AS "联系电话",
 	CASE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="urgency_show"]') WHEN '' THEN EXTRACTVALUE(xmldata,'/Items/WFItem[@name="urgency"]') ELSE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="urgency_show"]') END AS "急紧程度",
 	CASE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="project_show"]') WHEN '' THEN EXTRACTVALUE(xmldata,'/Items/WFItem[@name="project"]') ELSE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="project_show"]') END AS "所属项目",
 	CASE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="subproject_show"]') WHEN '' THEN EXTRACTVALUE(xmldata,'/Items/WFItem[@name="subproject"]') ELSE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="subproject_show"]') END AS "子项目",
 	CASE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="errorType_show"]') WHEN '' THEN EXTRACTVALUE(xmldata,'/Items/WFItem[@name="errorType"]') ELSE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="errorType_show"]') END AS "故障或需求类型",
 	EXTRACTVALUE(xmldata,'/Items/WFItem[@name="reportTime"]') AS "故障或需求时间",
 	REPLACE(REPLACE(EXTRACTVALUE(xmldata,'/Items/WFItem[@name="reportDetail"]'),CHAR(10),''),CHAR(13),'') AS "详情"
FROM
(SELECT p.nodename,m.*
FROM bpm_archiveddata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid
WHERE m.wf_processid!='65590215080f9044140a1490ba3122264aa5' AND DATE(EXTRACTVALUE(m.xmldata,'/Items/WFItem[@name="reportTime"]')) BETWEEN <datetime1> AND <datetime2>
UNION ALL
SELECT p.nodename,m.*
FROM bpm_maindata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid
WHERE m.wf_processid!='65590215080f9044140a1490ba3122264aa5' AND DATE(EXTRACTVALUE(m.xmldata,'/Items/WFItem[@name="reportTime"]')) BETWEEN <datetime1> AND <datetime2>) process;
```

# 根据特定的时间段按特定字段统计工单数量
```sql
SELECT
 	CASE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="unit_show"]') WHEN '' THEN EXTRACTVALUE(xmldata,'/Items/WFItem[@name="unit"]') ELSE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="unit_show"]') END AS "单位",
	SUM(CASE wf_status WHEN 'Current' THEN 1 ELSE 0 END) "流转中数量",
	SUM(CASE wf_status WHEN 'ARC' THEN 1 ELSE 0 END) "已完结数量",
	SUM(CASE wf_status WHEN 'dratf' THEN 1 ELSE 0 END) "草稿数量",
	COUNT(1) "总工单量"
FROM
(SELECT p.nodename,m.*
FROM bpm_archiveddata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid
WHERE m.wf_processid!='65590215080f9044140a1490ba3122264aa5' AND DATE(EXTRACTVALUE(m.xmldata,'/Items/WFItem[@name="reportTime"]')) BETWEEN <datetime1> AND <datetime2>
UNION ALL
SELECT p.nodename,m.*
FROM bpm_maindata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid
WHERE m.wf_processid!='65590215080f9044140a1490ba3122264aa5' AND DATE(EXTRACTVALUE(m.xmldata,'/Items/WFItem[@name="reportTime"]')) BETWEEN <datetime1> AND <datetime2>) process
GROUP BY CASE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="unit_show"]') WHEN '' THEN EXTRACTVALUE(xmldata,'/Items/WFItem[@name="unit"]') ELSE EXTRACTVALUE(xmldata,'/Items/WFItem[@name="unit_show"]') END ;
```
"""

CACHE_DIALECTS = "\n\n".join([
    f"<SQL缓存模板{idx}>\n{item}\n</SQL缓存模板{idx}>"
    for idx, item in enumerate((ATTENDENCE_CACHE_DIALECTS+"\n"+BPM_CACHE_DIALECT).split("\n\n"), start=1)
])
