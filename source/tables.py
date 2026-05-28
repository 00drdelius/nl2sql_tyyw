import re
from typing import *
from pathlib import Path

import rich


attendance_tables_file = Path(__file__).parent / "考勤数据表定义.md"
bpm_tables_file = Path(__file__).parent / "工单流程数据定义.md"

table_name_matcher = re.compile(r"(?<=# \d\. )\w+(?= \[)")

with attendance_tables_file.open('r') as f:
    attn_raw = f.read()

with bpm_tables_file.open('r') as f:
    bpm_raw = f.read()


ATT_TABLENAMES=table_name_matcher.findall(attn_raw)
BPM_TABLENAMES=table_name_matcher.findall(bpm_raw)
# rich.print(ATT_TABLENAMES)
# rich.print(BPM_TABLENAMES)

splitter="<br>"
ATTN_TABLE_SCHEMAS=[i.strip() for i in attn_raw.split(splitter)]
BPM_TABLE_SCHEMAS=[i.strip() for i in bpm_raw.split(splitter)]

