from typing import Optional, List, Union
from pydantic import BaseModel, Field


class Relation(BaseModel):
    relation_type: str = Field(description='关系类型')
    head_id: str = Field(description='关系的头id')
    tail_id: str = Field(description='关系的尾id')
    priority: Optional[int] = Field(1, description='优先级, priority 越大，优先级越高')


class Choice(BaseModel):
    text: str = Field(description='若 type == "value", 则为查询到的相近的数据文本；'
                                  '若 type == "column_desc", 则为相近的column的描述; '
                                  '若 type == "comparison_op_desc", 则为相近的比较操作符的描述; ...')
    type: str = Field(
        description='结果类型；type = [ "column_desc", "value", "comparison_op_desc", "condition_op_desc", '
                    '"aggregation_column_desc, time_column_desc, count_column_desc " ]')
    value: str = Field(
        description='text 对应的 column 或 op 等；'
                    '如 text="java工程师", value="position", value_type="column"; '
                    '若 type in [ "column_desc", "value", "aggregation_column_desc", '
                    '"count_column_desc", "time_column_desc" ]， value 是 column_name; '
                    '若 type == "comparison_op_desc"， value in [ ">", "<", "=", ">=", "<=" ]; '
                    '若 type == "condition_op_desc", value in [ "AND", "OR" ];'
    )
    score: Optional[float] = Field(description='算法给该选项的分数')
    zh_value: Optional[str] = Field(description='value 的中文翻译')


class LastChoice(BaseModel):
    id: str = Field(description='唯一id；用于组织 relation 以及 记录数据以用于后续优化模型')
    text: str = Field(description='结果对应的输入文本')
    multi_choice: Optional[bool] = Field(description='为了和返回的 prediction 保持一样的结构；data 是否支持多选')
    data: List[Choice] = Field(description='用户选择的结果(可多选; 一般只有一个)')


class SuggestionInput(BaseModel):
    text: str = Field(description='待匹配的文本 (不包括已经匹配的文本部分)')
    full_text: Optional[str] = Field(description='完整的输入文本')
    suggestion_history: Optional[List[LastChoice]] = Field([], description='已经匹配的结果 (结构化)')
    top_k: Optional[int] = Field(20, description='返回top_k个结果')
    cur_index: Optional[int] = Field(-1, description='当前输入在 suggestion history 的位置 index '
                                                     '(prediction insert 到 history 的 index 前)')


class Prediction(BaseModel):
    id: str = Field(description='唯一id；用于组织 relation 以及 记录数据以用于后续优化模型')
    text: str = Field(description='输入的文本；若只有单个信息，则为输入文本本身；若包含多个信息，则该text为切词后对应该匹配结果的文本')
    multi_choice: Optional[bool] = Field(False, description='返回的 data 是否支持多选')
    data: List[Choice] = Field([], description='查询到的top k匹配结果')


class SuggestionResponse(BaseModel):
    ret: int = Field(1, description='状态码；是否成功；0 表示 失败，1 表示 成功')
    msg: Optional[str] = Field('', description='错误信息；若 ret = 1，则为空')
    data: Optional[List[Union[Prediction, None]]] = Field(
        description='查询到的匹配结果; 若 is_multi == False, 则 data 为查询到的 top k 匹配结果; '
                    '若 is_multi == True, 则 data 为 多个 top k 匹配列表'
    )


class Column(BaseModel):
    name: str = Field(description='字段名；唯一的，包含表名')
    zh_name: str = Field(description='字段名')
    is_leaf: int = Field(description='是否叶子节点; 0 表示是父级节点，1表示是叶子节点')
    data_type: Optional[str] = Field(description='数据类型')
    aggregations: Optional[List[str]] = Field([], description='该字段支持的聚合函数列表')
    gb_fns: Optional[List[str]] = Field([], description='该字段支持的分组函数列表')
    actual_column: Optional[str] = Field(description='实际在表中的列名')
    table: Optional[str] = Field(description='实际在库里的表名')


class ResponseColumns(BaseModel):
    ret: int = Field(1, description='状态码；是否成功；0 表示 失败，1 表示 成功')
    msg: Optional[str] = Field('', description='错误信息；若 ret = 1，则为空')
    data: Optional[List[Column]] = Field(description='全部字段列表；或搜索过滤后的字段列表')


class ResponseValues(BaseModel):
    ret: int = Field(1, description='状态码；是否成功；0 表示 失败，1 表示 成功')
    msg: Optional[str] = Field('', description='错误信息；若 ret = 1，则为空')
    data: Optional[list] = Field(description='搜索过滤后的value列表')
