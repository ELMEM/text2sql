import os
import sys
import re
from functools import reduce

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from typing import Optional, List
from pydantic import BaseModel, Field
from server.interfaces.base import app
from lib import logs
from lib.preprocess import format_suffix
from core.processor import to_zh_text
from normalize.norm import normalize
from core.processor import get_data_type
from core.complete_sql import format_value

_reg_num = re.compile('^\d+(\.\d+)?$')
_reg_num_type = re.compile('^(int|float)', re.IGNORECASE)
_reg_order_up = re.compile('\s+ASC$', re.IGNORECASE)
_reg_order_down = re.compile('\s+DESC$', re.IGNORECASE)


class Select(BaseModel):
    name: str = Field(description='字段名')
    aggregation: Optional[str] = Field('', description='聚合方式')
    group_by: Optional[str] = Field('', description='分组方式')
    order: Optional[str] = Field('', description='排序方式；升序还是降序；[ DESC, ASC ]')


class Where(BaseModel):
    name: str = Field(description='字段名')
    comparison_op: Optional[str] = Field('=', description='条件op')
    values: list = Field(description='过滤的值')


class EditorInput(BaseModel):
    selects: List[Select] = Field(description='查询的字段')
    wheres: Optional[List[Where]] = Field([], description='过滤的条件')


class SqlText(BaseModel):
    ret: int = Field(1, description='状态码；是否成功；0 表示 失败，1 表示 成功')
    msg: Optional[str] = Field('', description='错误信息；若 ret = 1，则为空')
    sql: Optional[str] = Field(description='生成的 fake sql (For 王永和 处理)')
    zh_sql: Optional[str] = Field(description='sql 的中文版')


def filter_conditions(wheres: List[Where]):
    """ 过滤不符合规范的 where 条件 """
    return list(filter(lambda x: x.name and x.values, wheres))


def get_condition_statement(where: Where) -> List[str]:
    """ 将过滤器的 where 条件变成 条件语句字符串 """

    # 对 texts 值进行 normalize
    d_comparison_op_2_texts = normalize(where.name, get_data_type(where.name), where.comparison_op, where.values)

    where_strs = []

    for _comparison_op, _texts in d_comparison_op_2_texts.items():
        if _comparison_op in ['', '=']:
            if len(_texts) > 1:
                value_str = ', '.join(list(map(lambda x: format_value(x, where.name), _texts)))
                where_strs.append(f'{where.name} in ({value_str})')
            else:
                where_strs.append(f'{where.name} = {format_value(where.values[0], where.name)}')

        elif _comparison_op == '!=':
            if len(_texts) > 1:
                value_str = ', '.join(list(map(lambda x: format_value(x, where.name), _texts)))
                where_strs.append(f'{where.name} not in ({value_str})')
            else:
                where_strs.append(f'{where.name} != {format_value(where.values[0], where.name)}')

        else:
            statements = list(map(lambda x: f'{where.name} {_comparison_op} {format_value(x, where.name)}', _texts))
            where_strs += statements

    return where_strs


@app.post('/v1/sql/from_editor',
          name="v1 sql from editor",
          response_model=SqlText,
          description="根据用户选择的输入结果，整合成 王永和 所需的 fake sql")
def sql_from_editor(_input: EditorInput):
    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}')
    selects = _input.selects
    wheres = _input.wheres

    # 检查 selects 参数
    if not selects:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': 'selects 不能为空'})

    # 拼接 select columns
    select_col = list(map(lambda x: f'{x.name}{format_suffix(x.aggregation)}{format_suffix(x.group_by)}', selects))
    selects_str = f'SELECT {", ".join(select_col)} ' if selects else 'SELECT * '
    zh_selects_str = f'【查询】: {", ".join(select_col)} ' if selects else '【查询】: * '

    # 拼接 order by
    orders = list(map(lambda x: f'{x.name}{format_suffix(x.aggregation)}{format_suffix(x.group_by)} {x.order}',
                      filter(lambda e: e.order, selects)))
    order_str = f'ORDER BY {",".join(orders)}' if orders else ""

    zh_orders = list(map(lambda x: _reg_order_up.sub('(升序)', _reg_order_down.sub('(降序)', x)), orders))
    zh_order_str = f'【排序依据】: {",".join(zh_orders)}' if zh_orders else ""

    wheres = filter_conditions(wheres)
    conditions = list(map(lambda x: get_condition_statement(x), wheres))
    conditions = reduce(lambda a, b: a + b, conditions, [])

    where_str = ' and '.join(conditions)
    zh_where_str = to_zh_text(where_str)

    sql = f'{selects_str.strip()} FROM Recruitment'
    if where_str:
        sql += f' WHERE {where_str.strip()}'
    if order_str:
        sql += f' {order_str.strip()}'

    zh_sql = f'{zh_selects_str.strip()}'
    if zh_where_str:
        zh_sql += f'; 【过滤条件】: {zh_where_str.strip()}'
    if zh_order_str:
        zh_sql += f'; {zh_order_str.strip()}'

    return logs.ret(log_id, logs.fn_name(), 'POST', {
        'ret': 1,
        'sql': sql,
        'zh_sql': zh_sql,
    })


if __name__ == '__main__':
    # 测试代码
    sel = [Select(name="JobPublishedDateNormalized", group_by="BY_YEAR"),
           Select(name="JobJobName")]
    whe = [Where(name="WorkExperienceSalaryRangeNormalizedGte", comparison_op=">", values=["2w"]),
           Where(name="WorkExperienceSalaryRangeNormalizedGte", comparison_op="<", values=["4w"]),
           Where(name="JobJobName", comparison_op="=", values=["java工程师"]),
           Where(name="JobCity", comparison_op="=", values=["北京", "上海"])]
    _input = EditorInput(selects=sel, wheres=whe, domain={'JobOpenId': ['xxx', 'ccc'], 'FlowStageId': ['234', '34']})
    ret = sql_from_editor(_input)
    print(ret['sql'])
    print(ret['zh_sql'])
