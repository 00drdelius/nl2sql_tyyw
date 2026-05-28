import re
import enum
from typing import *
from pydantic import BaseModel, Field
from pydantic.functional_validators import AfterValidator

from source import ATT_TABLENAMES, BPM_TABLENAMES


class ReductionOperator(enum.Enum):
    """
    数据库规约操作的枚举类。
    EXHAUSTION: 全部列出
    SUM: 对字段值算总和，即SQL的SUM()函数
    AVG: 对字段值算平均，即SQL的AVG()函数
    """
    EXHAUSTION = "exhaustion"
    SUM = "sum"
    AVG = "avg"


class FilterOperator(enum.Enum):
    """数据库WHERE语句运算符的枚举类。"""
    EQUAL="="
    LT="<"
    GT=">"
    LE="<="
    GE=">="
    IN="IN"


def check_fields_format(fields:list[str]):
    "fields in filter object must follow format: table_name.field_name"
    for f in fields:
        if not '.' in f:
            raise ValueError("filter field must contain table name.")
        table_name, field_name = f.split(".")
        if not table_name in ATT_TABLENAMES+BPM_TABLENAMES:
            raise ValueError(f"table name in filter field does not exists: {table_name}")
        #TODO checks field_name
    return fields


def check_table_name(name:str):
    if not name in ATT_TABLENAMES+BPM_TABLENAMES:
        raise ValueError(f"table name in JOIN does not exists: {name}")
    return name


def check_on_condition(on_string:str):
    "on condition must follow format: left_table.field=right_table.field"
    matcher=re.compile(r"\w+\.\w+=\w+.\w+")
    if not matcher.search(on_string):
        raise ValueError(
            f"on condition must follow format: left_table.field=right_table.field: {on_string}")
    return on_string


class FilterObject(BaseModel):
    "存储用于WHERE语句的条件过滤信息"

    value: Annotated[str, Field(description="<用户问题>中提取的实体值。用于db模糊搜索")]
    "raw value from user query, recognized by LLM"

    normalized_value: Annotated[
        Optional[str], Field(default=None, description="根据模糊搜索得出的具体值，经过字段过滤后保留的唯一值")]
    "normalized value of raw value, value stored in db"

    fields: Annotated[
        Optional[List[str]], AfterValidator(check_fields_format), Field(default=None, description="根据模糊搜索得出的多个具体值的字段列表")]
    "possible fields given by fuzzy search, should be filterred to only one. Strict format: table.field"

    operator: Annotated[
        FilterOperator, Field(default=None, description="将`normalized_value`用于WHERE语句进行准确过滤的运算符")]
    "filter operator db usually operate after WHERE, recognized by LLM"


Table_Str = Annotated[str, AfterValidator(check_table_name)]

class JoinObject(BaseModel):
    "存储用于JOIN语句的信息"

    left: Annotated[Table_Str, Field(description="左表。一般是`main_table`")]
    "left table, usually is main table"

    right: Annotated[Table_Str, Field(description="右表，一般是关联的表")]
    "right table, usually is joined table"

    on: Annotated[
        str, AfterValidator(check_on_condition),
        Field(description="两表ON的条件。必须遵循的格式: left.field=right.field")]
    "ON condition. Format must follow: left.field=right.field"


class AgentRecognition(BaseModel):

    reduction: Annotated[
        ReductionOperator, Field(description="数据库的规约操作。穷举: 直接列出全部值；还是求和: 对某字段求和，等规约操作")]
    "reduciton db usually operate after SELECT,"

    metric: Annotated[
        Optional[str],
        Field(default=None, description="需要统计的可量化的指标，可选。一般是“xx”数、额、量。如：考勤数，工单数，订单量。但规约操作为穷举时一般没有可量化指标，留空")]
    "quantified metric. Optional."

    main_table: Annotated[Table_Str, Field(description="主表。FROM语句后面的主表，需要自行判断哪张表作为主表最合适")]
    "the FROM table, recognized by LLM"

    time: Annotated[Optional[str], Field(description="时间。不管值为“上周”、“4月份”等，只需要直接提取出来即可")]
    "time interval, could be properly recognized by LLM with function tool."

    joins: Annotated[
        Optional[List[JoinObject]], Field(default=None, description="用于JOIN语句的条件列表，可选。需要自行判断哪些表需要JOIN进来给出关键信息")]
    "JOIN conditions"

    filters: Annotated[List[FilterObject], Field(description="用于WHERE语句的过滤条件列表")]
    "list of filter conditions"


def get_model_json_schema():
    src_schema = AgentRecognition.model_json_schema()
    #NOTE drop fields which perfer using code to generate instead of LLM
    drop_fields=["normalized_value","fields"]
    filter_obj = src_schema['$defs']['FilterObject']['properties']
    for field in drop_fields:
        filter_obj.pop(field, None)
    return src_schema

