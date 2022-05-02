import os
import sys
import json
import requests
from typing import Optional, List, Union
from functools import reduce
from fastapi import Header
from pydantic import BaseModel, Field

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from config.api import yonghe_domain
from server.interfaces.base import app
from server.definitions.suggestions import ResponseValues
from server.interfaces.data.data_search_values_by_texts import data_search_values_by_texts, QueryValueInput
from core.processor import d_field_2_info
from lib import logs
from server.interfaces.fake_sql.fake_sql_from_editor import format_value, get_condition_statement, Where, \
    filter_conditions

_LIMIT = 100


def _query(sql: str, tenant: str) -> Union[None, List[str]]:
    if not tenant:
        return

    url = f'http://{yonghe_domain}/query'
    params = {'nql': sql}

    try:
        logs.add('API', url, f'params: {params}')
        _ret = requests.get(url, params=params, headers={"accept": "application/json", "tenant": tenant})
        if _ret.status_code != 200:
            logs.add('API', url, f'status code: {_ret.status_code}', _level=logs.LEVEL_ERROR)
            return

        try:
            _content = _ret.content.decode('utf-8')
        except:
            _content = _ret.content

        logs.add('API', url, f'response: {_content}')
        data = json.loads(_ret.content)['data']['rows']

        # 解析成 List[str]
        if data:
            data = list(map(lambda x: x[0] if x else '', data))
            data = list(filter(lambda x: x, data))
            data = list(set(data))
        else:
            data = []

        return data
    except:
        logs.add('API', url, f'error occur during requesting or parsing result', _level=logs.LEVEL_ERROR)
        return


class FilterInput(BaseModel):
    column: str = Field(description='需要搜索的column')
    q: Optional[str] = Field('', description='搜索的文本')
    wheres: Optional[List[Where]] = Field({}, description='限制的域')


@app.post('/v1/search/values',
          name="v1 search values",
          response_model=ResponseValues,
          description="搜索过滤后的 value 列表")
def search_values(_input: FilterInput, tenant: Optional[str] = Header('')):
    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}')

    column = _input.column
    q = _input.q
    wheres = _input.wheres

    # 检查参数
    if not column:
        return logs.ret(log_id, logs.fn_name(), 'POST', {
            'ret': 0,
            'msg': 'column 都不能为空'
        })

    # 检查参数类型是否支持搜索
    if column not in d_field_2_info or not d_field_2_info[column].data_type.lower().startswith('string'):
        return logs.ret(log_id, logs.fn_name(), 'POST', {
            'ret': 0,
            'msg': f'column ({column}) 不支持搜索'
        })

    # 生成 domain 的条件语句
    wheres = filter_conditions(wheres)
    conditions = list(map(lambda x: get_condition_statement(x), wheres))
    conditions = reduce(lambda a, b: a + b, conditions, [])
    domain_str = ' and '.join(conditions)

    # 获取 domain 限制下 前 LIMIT 的数据 作为 初始列表数据
    domain_str = f'where {domain_str}' if domain_str else ''
    data = _query(f'SELECT {column} FROM Recruitment {domain_str} LIMIT {_LIMIT * 2}', tenant)
    data = data if data is not None else []
    data.sort()

    # 若搜索文本为空
    if not q:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 1, 'data': data[:_LIMIT]})

    # milvus 查询语义接近的数据
    ret_value = data_search_values_by_texts(QueryValueInput(
        q_texts=[q],
        column=column,
        top_k=_LIMIT * 2
    ))

    # 获取结果数据
    values = ret_value['data'][0] if ret_value['ret'] == 1 and ret_value['data'] else []

    # 过滤低分结果
    values = list(filter(lambda x: x['similarity'] > 0.6, values))
    if values:
        max_score = values[0]['similarity']
        values = list(filter(lambda x: max_score - x['similarity'] < 0.12, values))

    # 获取结果的返回文本
    values = list(map(lambda x: x['data']['text'], values))

    # 验证 milvus 返回的全局数据是否在 domain 限制下仍存在
    if values:
        # 获取需要检查该 domain 下限制的值
        check_values = list(map(lambda x: format_value(x, column), values))
        check_val_str = ', '.join(check_values)
        domain_str = f'{domain_str} and' if domain_str else ''

        sql = f'select {column} from Recruitment where {domain_str} {column} in ({check_val_str}) LIMIT {_LIMIT * 2}'
        checked_values = _query(sql, tenant)

        if checked_values is not None:
            d_val = {_v: 1 for _v in checked_values}
            values = list(filter(lambda x: x in d_val, values))

    # 对 初始列表里的数据进行 in text 判断
    len_q = len(q.replace(' ', ''))
    values_in_text = list(filter(lambda x: q in x and x not in values, data))
    values_in_text = list(map(
        lambda x: {'text': x, 'score': 0.9 * len_q / (len(x.replace(' ', '')) + 0.1)}, values_in_text))
    values_in_text.sort(key=lambda x: (-x['score'], x['text']))

    # 合并搜索结果
    values += list(map(lambda x: x['text'], values_in_text))

    return logs.ret(log_id, logs.fn_name(), 'POST', {
        'ret': 1,
        'data': values[:_LIMIT]
    })


if __name__ == '__main__':
    ret = search_values(FilterInput(column='JobJobName', q='java', domain={'FlowStageId': ['w256d', '23']}))
    for v in ret['data']:
        print(v)
