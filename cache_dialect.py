ATTENDENCE_CACHE_DIALECTS="""\
# 查询特定时间用户异常考勤的条目
```sql
SELECT 
	"用户名称", "单位名称", "排班名称", "值班日期", "考勤状态", "是否申诉", "是否请假" 
FROM imoc_attendance_all 
WHERE "考勤状态" != '正常' AND "值班日期" BETWEEN <dateime1> AND <datetime2>;
```

# 统计特定时间考勤异常用户数，根据用户提问添加关键字过滤
```sql
SELECT 
	"排班名称", 
	count(1) AS "总人数", 
	SUM(CASE WHEN "考勤状态" = '迟到' THEN 1 ELSE 0 END ) AS "迟到数",
	SUM(CASE WHEN "考勤状态" = '未签退' THEN 1 ELSE 0 END ) AS "未签退数",
	SUM(CASE WHEN "考勤状态" = '早退' THEN 1 ELSE 0 END ) AS "早退数",
	SUM(CASE WHEN "考勤状态" = '缺勤' THEN 1 ELSE 0 END ) AS "缺勤数" 
FROM imoc_attendance_all 
WHERE "考勤状态" != '正常' AND "值班日期" BETWEEN <dateime1> AND <dateime2> AND "排班名称" LIKE '%%'
GROUP BY "排班名称";
```

# 统计特定时间段内考勤用户考勤状态数量，根据用户提问替换时间段，根据用户提问添加关键字过滤
```sql
SELECT 
	"值班日期", 
	count(1) AS "总人数", 
	SUM(CASE WHEN "考勤状态" = '正常' THEN 1 ELSE 0 END ) AS "正常数",
	SUM(CASE WHEN "考勤状态" = '迟到' THEN 1 ELSE 0 END ) AS "迟到数",
	SUM(CASE WHEN "考勤状态" = '未签退' THEN 1 ELSE 0 END ) AS "未签退数",
	SUM(CASE WHEN "考勤状态" = '早退' THEN 1 ELSE 0 END ) AS "早退数",
	SUM(CASE WHEN "考勤状态" = '缺勤' THEN 1 ELSE 0 END ) AS "缺勤数"
FROM imoc_attendance_all 
WHERE "值班日期" BETWEEN <dateime1> AND <dateime2>
	AND "排班名称" LIKE '%%'
GROUP BY "值班日期" ;
```
"""

BPM_CACHE_DIALECT="""\
# 根据特定的时间段查出工单记录，按用户需求调整时间段
```sql
select 
	wf_docnumber as "工单编号",`subject` as '工单标题',nodename as "工单类型", wf_addname_cn as 申请人,wf_doccreated as 开始时间, wf_endtime as 结束时间, 
	case when wf_status='Current' then '流转中' when wf_status='ARC' then '已结束' else wf_status end as 状态,
 	ExtractValue(xmldata,'/Items/WFItem[@name="reporter"]') as "报单人",
 	case ExtractValue(xmldata,'/Items/WFItem[@name="reportType"]') when '0' then '服务台报障' when '1' then '电话报障' when '2' then '自行报障' when '4' then '现场报障' else ExtractValue(xmldata,'/Items/WFItem[@name="reportType"]') end as "申请途径",
 	case ExtractValue(xmldata,'/Items/WFItem[@name="unit_show"]') when '' then ExtractValue(xmldata,'/Items/WFItem[@name="unit"]') else ExtractValue(xmldata,'/Items/WFItem[@name="unit_show"]') end as "单位",
 	case ExtractValue(xmldata,'/Items/WFItem[@name="dept_show"]') when '' then ExtractValue(xmldata,'/Items/WFItem[@name="dept"]') else ExtractValue(xmldata,'/Items/WFItem[@name="dept_show"]') end as "科室",
 	ExtractValue(xmldata,'/Items/WFItem[@name="phone"]') as "联系电话",
 	case ExtractValue(xmldata,'/Items/WFItem[@name="urgency_show"]') when '' then ExtractValue(xmldata,'/Items/WFItem[@name="urgency"]') else ExtractValue(xmldata,'/Items/WFItem[@name="urgency_show"]') end as "急紧程度",
 	case ExtractValue(xmldata,'/Items/WFItem[@name="project_show"]') when '' then ExtractValue(xmldata,'/Items/WFItem[@name="project"]') else ExtractValue(xmldata,'/Items/WFItem[@name="project_show"]') end as "所属项目",
 	case ExtractValue(xmldata,'/Items/WFItem[@name="subproject_show"]') when '' then ExtractValue(xmldata,'/Items/WFItem[@name="subproject"]') else ExtractValue(xmldata,'/Items/WFItem[@name="subproject_show"]') end as "子项目",
 	case ExtractValue(xmldata,'/Items/WFItem[@name="errorType_show"]') when '' then ExtractValue(xmldata,'/Items/WFItem[@name="errorType"]') else ExtractValue(xmldata,'/Items/WFItem[@name="errorType_show"]') end as "故障或需求类型",
 	ExtractValue(xmldata,'/Items/WFItem[@name="reportTime"]') as "故障或需求时间",
  replace(replace(ExtractValue(xmldata,'/Items/WFItem[@name="reportDetail"]'),char(10),''),char(13),'') as "详情"
from 
(select p.nodename,m.*
from bpm_archiveddata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid
where m.wf_processid!='65590215080f9044140a1490ba3122264aa5' and date(ExtractValue(m.xmldata,'/Items/WFItem[@name="reportTime"]')) between <datetime1> and <datetime2>
union all 
select p.nodename,m.*
from bpm_maindata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid
where m.wf_processid!='65590215080f9044140a1490ba3122264aa5' and date(ExtractValue(m.xmldata,'/Items/WFItem[@name="reportTime"]')) between <datetime1> and <datetime2>) process;
```

# 根据特定的时间段按特定字段统计工单数量
```sql
select 
 	case ExtractValue(xmldata,'/Items/WFItem[@name="unit_show"]') when '' then ExtractValue(xmldata,'/Items/WFItem[@name="unit"]') else ExtractValue(xmldata,'/Items/WFItem[@name="unit_show"]') end as "单位",
	sum(case wf_status when 'Current' then 1 else 0 end) "流转中数量",
	sum(case wf_status when 'ARC' then 1 else 0 end) "已完结数量",
	sum(case wf_status when 'dratf' then 1 else 0 end) "草稿数量",
	count(1) "总工单量"
from 
(select p.nodename,m.*
from bpm_archiveddata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid
where m.wf_processid!='65590215080f9044140a1490ba3122264aa5' and date(ExtractValue(m.xmldata,'/Items/WFItem[@name="reportTime"]')) between <datetime1> and <datetime2>
union all 
select p.nodename,m.*
from bpm_maindata m INNER JOIN bpm_modprocesslist p ON m.wf_processid=p.processid
where m.wf_processid!='65590215080f9044140a1490ba3122264aa5' and date(ExtractValue(m.xmldata,'/Items/WFItem[@name="reportTime"]')) between <datetime1> and <datetime2>) process
group by case ExtractValue(xmldata,'/Items/WFItem[@name="unit_show"]') when '' then ExtractValue(xmldata,'/Items/WFItem[@name="unit"]') else ExtractValue(xmldata,'/Items/WFItem[@name="unit_show"]') end ;
```
"""

CACHE_DIALECTS = "\n\n".join([
    f"<SQL缓存模板{idx}>\n{item}\n</SQL缓存模板{idx}>"
    for idx, item in enumerate((ATTENDENCE_CACHE_DIALECTS+"\n"+BPM_CACHE_DIALECT).split("\n\n"), start=1)
])