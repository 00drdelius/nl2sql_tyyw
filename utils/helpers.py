import re
from typing import Optional, Dict, Any


def extract_last_tag_content(raw_text: str, tag_name: str) -> Optional[str]:
    """
    提取指定XML标签的最后一对中的内容。
    
    Args:
        raw_text (str): 包含XML标签的原始字符串
        tag_name (str): 标签名，如 '润色后' 或 '最终结果'
    
    Returns:
        str: 最后一对标签中的内容，如果没有匹配则返回 None
    """
    # 转义标签名中的正则特殊字符
    escaped_tag = re.escape(tag_name)
    first_tag = f"<{escaped_tag}>"
    last_tag = f"</{escaped_tag}>"
    last_first_index = raw_text.rfind(first_tag)

    # 模式：匹配完整的标签对 <tag>...</tag>
    # (?s) 让 . 匹配换行符，.*? 非贪婪匹配
    # patterns)<{escapeds)<{escaped_tag}>(.*?)</{escaped_tag}>'
    pattern = rf'(?<={first_tag})([\s\S]*?)(?={last_tag})'
    
    # 找到所有匹配
    matches = list(re.finditer(pattern, raw_text[last_first_index:]))
    
    if not matches:
        return None
    
    # 返回最后一对标签中的内容
    return matches[-1].group(1)


def dict_to_markdown_table(data_dict: Dict[str, Any]) -> str:
    """
    将包含 columns 和 rows 的字典转换为 Markdown 格式的表格
    """
    # 检查字典结构是否完整
    if not data_dict or 'columns' not in data_dict or 'rows' not in data_dict:
        return "输入数据格式不正确，缺少 'columns' 或 'rows'。"

    columns = data_dict.get('columns')
    rows = data_dict.get('rows')
    if not columns or not rows:
        return "查询结果为空"

    # 1. 生成表头 (Header)
    header = "| " + " | ".join(str(col) for col in columns) + " |"
    
    # 2. 生成分割线 (Separator)
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"
    
    # 3. 生成数据行 (Data Rows)
    row_strings = []
    for row in rows:
        # 为了防止数据项中有 None 或者非字符串格式，统一转换为字符串
        # 针对每一行的数据进行拼接
        row_str = "| " + " | ".join(str(item) if item is not None else "" for item in row) + " |"
        row_strings.append(row_str)
        
    # 4. 将表头、分割线和所有数据行使用换行符拼接起来
    markdown_table = "\n".join([header, separator] + row_strings)
    
    return markdown_table


def test_extract():
    test_cases = [
        ('<润色后>第一段内容</润色后>然后一些文字<润色后>第二段内容</润色后>', '润色后'),
        ('<最终结果>A</最终结果><中间>B</中间><最终结果>C</最终结果>', '最终结果'),
        ('无关文本<润色后>第一个</润色后><润色后>最后一个</润色后>结尾', '润色后'),
        ('没有标签的普通文本', '润色后'),
        ('<不完整标签>缺少闭合', '不完整标签'),
        ('<嵌套><润色后>内部</润色后></嵌套>', '嵌套'),
        ('<嵌套><润色后>内部</润色后></嵌套>', '润色后'),
        ('多行\n<最终结果>\n跨行内容\n</最终结果>\n结束', '最终结果'),
    ]
    
    for i, (text,tagname) in enumerate(test_cases, 1):
        content = extract_last_tag_content(text, tagname)
        print(f"用例{i}:")
        print(f"  原文: {repr(text)}")
        print(f"  结果: 标签='{tagname}', 内容='{content}'")
        print()


def test_dict_to_markdown_table():
    example_dict = {
"columns": [
    "用户名称",
    "单位名称",
    "项目名称",
    "排班名称",
    "班次名称",
    "值班日期",
    "值班时间",
    "打卡时间",
    "考勤状态"
    ],
"rows": [["何家乐","基础保障综合类","","正常班次-中山市公安局政务信息化项目运维项目","正常班","2026-04-22","08:30,17:30","08:19,","未签退"],["张志国","科技管理科","","正常班次-中山市公安局政务信息化项目运维项目","正常班","2026-04-22","08:30,17:30","08:18,","未签退"],["郑刘平","科技管理科","","正常班次-中山市公安局政务信息化项目运维项目","正常班","2026-04-22","08:30,17:30","08:35,17:32","迟到"],["胡文祥","科技管理科","","正常班次-中山市公安局政务信息化项目运维项目","正常班","2026-04-22","08:30,17:30","08:36,17:32","迟到"],["张现伟","城信所","","自然资源局24-27运维01包)城信所","自然资源局24-27运维01包_城信所","2026-04-22","09:00,18:00","08:54,","未签退"],["李勇明","统一运维","","生态统一运维项目","正常班","2026-04-22","08:30,17:30","08:29,","未签退"],["林建峰","中国移动通信集团广东有限公司中山分公司","","测试","正常班","2026-04-22","08:30,17:30","","缺勤"],["邓文超","中山市社会保险基金管理局","","【正式】基金局2024-2027年度运维项目_排班(2026年4月)","基金局2024-2027年度运维项目_正常班次","2026-04-22","08:30,17:30","08:33,17:32","迟到"],["马昊翔","中山市社会保险基金管理局","","【正式】基金局2024-2027年度运维项目_排班(2026年4月)","基金局2024-2027年度运维项目_正常班次","2026-04-22","08:30,17:30",",17:33","缺勤"],["梁键涛","统一运维","","市统一运维-包1(移动)-驻点人员排班","正常班","2026-04-22","08:30,17:30","08:10,","未签退"],["黄培彬","统一运维","","生态统一运维项目","正常班","2026-04-22","08:30,17:30","08:28,","未签退"],["陈杰","网络租用和综合布线保障维护","","中山市公安局政务信息化项目2024-2027年度运维项目（应用系统专项）（综合应用系统）","综合布线-正常班(8:30-17:30)","2026-04-22","08:30,17:30","08:22,","未签退"],["徐志林","科技管理科","","正常班次-中山市公安局政务信息化项目运维项目","正常班","2026-04-22","08:30,17:30","08:35,17:35","迟到"]
    ]
}

    markdown_output = dict_to_markdown_table(example_dict)
    print(markdown_output.__repr__())


if __name__ == "__main__":
    test_dict_to_markdown_table()
    # test_extract()
