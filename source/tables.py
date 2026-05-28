import re
from typing import *
from pathlib import Path

import rich


attendance_tables_file = Path(__file__).parent / "考勤数据表定义.md"
bpm_tables_file = Path(__file__).parent / "工单流程数据定义.md"
example_tables_file = Path(__file__).parent / "example.md"

table_name_matcher = re.compile(r"(?<=# \d\. )\w+(?= \[)")

with attendance_tables_file.open('r') as f:
    ATTDN_RAW = f.read()

with bpm_tables_file.open('r') as f:
    BPM_RAW = f.read()

with example_tables_file.open('r') as f:
    EXAMPLE_RAW = f.read()

ATTDN_TABLENAMES=table_name_matcher.findall(ATTDN_RAW)
BPM_TABLENAMES=table_name_matcher.findall(BPM_RAW)
EXAMPLE_TABLENAMES=table_name_matcher.findall(EXAMPLE_RAW)
# rich.print(ATT_TABLENAMES)
# rich.print(BPM_TABLENAMES)

splitter="<br>"
ATTDN_TABLE_SCHEMAS=[i.strip() for i in ATTDN_RAW.split(splitter)]
BPM_TABLE_SCHEMAS=[i.strip() for i in BPM_RAW.split(splitter)]
EXAMPLE_TABLE_SCHEMAS=[i.strip() for i in EXAMPLE_RAW.split(splitter)]


