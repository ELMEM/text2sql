import os
import re
import sys
import json
import copy
import requests
from typing import List, Optional, Union
from fastapi import Header
from pydantic import BaseModel, Field

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from config.api import yonghe_domain
from server.interfaces.base import app
from server.interfaces.fake_sql.fake_sql_from_editor import Select, Where
from lib import logs
from lib.utils import md5, date2timestamp
from core.processor import get_data_type, to_zh, d_field_2_info, d_entity_2_tables
from server.interfaces.fake_sql.fake_sql_from_editor import sql_from_editor, EditorInput


class FigureInput(BaseModel):
    fig_type: str = Field('', description='图的类型；暂时只支持【 line, bar 】两种')
    x: List[Select] = Field(description='X轴的字段')
    y: List[Select] = Field(description='Y轴的字段')
    not_visualized: List[Select] = Field(description='Not visualized的字段')
    wheres: List[Where] = Field([], description='过滤的条件')


class OneSeries(BaseModel):
    name: str = Field(description='该字段的英文名称')
    zh_name: str = Field(description='该字段的中文名称')
    agg_fn: str = Field('', description='该字段的聚合函数')
    agg_fn_zh: str = Field('', description='该字段的聚合函数的中文名称')
    gb_fn: str = Field('', description='该字段的分组函数')
    gb_fn_zh: str = Field('', description='该字段的分组函数中文名称')
    type: str = Field('', description='该 series 对应的图表类型')
    data: List[Union[int, float, str]] = Field([], description='返回的该 series 的数据')
    labels: List[Union[int, float, str]] = Field([], description='对应 data 中的数据的 label')


class Response(BaseModel):
    ret: int = Field(1, description='状态码；是否成功；0 表示 失败，1 表示 成功')
    msg: Optional[str] = Field('', description='错误信息；若 ret = 1，则为空')
    x: Optional[Union[OneSeries, None]] = Field(None, description='X轴相关的数据')
    series: Optional[List[OneSeries]] = Field([], description='Y轴相关的数据 数组')
    title: Optional[str] = Field('', description='图表的标题')
    description: Optional[str] = Field('', description='图表的描述')
    not_visualized: Optional[List[OneSeries]] = Field([], description='剩余不在图表上的字段')


graph_conf = {
    'bar': [
        {'x': ['dim_actual_int', 'dim_date', 'dim_int', 'dim_str'], 'y': ['agg_float', 'agg_int']},
    ],
    'line': [
        {'x': ['dim_actual_int', 'dim_date', 'dim_int', 'dim_float'], 'y': ['agg_float', 'agg_int']},
    ],
}

d_fig_2_conf = {}

for _fig_type, _conf in graph_conf.items():
    if _fig_type not in d_fig_2_conf:
        d_fig_2_conf[_fig_type] = {}

    for val in _conf:
        for x_type in val['x']:
            for y_type in val['y']:
                d_fig_2_conf[_fig_type][f'{x_type}&&{y_type}'] = len(d_fig_2_conf[_fig_type])

_reg_int_dim = re.compile(r'(Status|Degree|Gender)(?=[A-Z \-_,\d]|$)')


def get_type(column_name: str, agg_fn: str):
    """
    获取该字段的 data type
        type 列表：
            dim_date, dim_int, dim_float, dim_actual_int, dim_str,
             agg_int, agg_float, agg_str, agg_actual_int
    """
    data_type = get_data_type(column_name).lower()

    if data_type.startswith('int') or data_type.startswith('uint'):
        data_type = 'int'
    elif data_type.startswith('float') or data_type.startswith('double'):
        data_type = 'float'
    elif data_type.startswith('date') or data_type.startswith('time'):
        data_type = 'date'
    elif _reg_int_dim.search(column_name):
        data_type = 'actual_int'
    else:
        data_type = 'str'

    if not agg_fn:
        return f'dim_{data_type}'
    else:
        agg_fn = agg_fn.lower()
        if 'count' in agg_fn:
            return 'agg_int'
        elif agg_fn in ['min', 'max', 'sum']:
            return f'agg_{data_type}'
        else:
            return 'agg_float'


def _check_not_visualized_at_final(fig_type: str, combine_type: str, final_options: list, d_column_2_data_len: dict,
                                   x_option: dict, y_option: dict, x_i: int = -1, y_i: int = -1):
    """ 校验 not visualize 是否符合要求 """

    valid_num = 0

    for tmp_fig_type in graph_conf.keys():
        if fig_type and fig_type != tmp_fig_type:
            continue

        if combine_type in d_fig_2_conf[tmp_fig_type]:
            index_incr = -1 if tmp_fig_type == 'line' and 'str' not in combine_type else 0
            if tmp_fig_type == 'bar' and 'str' not in combine_type and d_column_2_data_len[
                x_option['select'].name] > 30:
                index_incr += 1

            x_option['select'].order = x_option['select'].order if x_option['select'].order else 'ASC'
            final_options.append({
                'x': x_option,
                'y': y_option,
                'index': d_fig_2_conf[tmp_fig_type][combine_type] + index_incr,
                'x_i': x_i, 'y_i': y_i,
                'fig_type': tmp_fig_type,
            })
            valid_num += 1

    return valid_num


def query(sql: str, tenant: str) -> Union[None, List[str]]:
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
        return data
    except:
        logs.add('API', url, f'error occur during requesting or parsing result', _level=logs.LEVEL_ERROR)
        return


def get_agg_fn(old_agg_fn, column_name):
    if old_agg_fn or not d_field_2_info[column_name].aggregations:
        return ''
    else:
        if 'Avg' in d_field_2_info[column_name].aggregations:
            return 'Avg'
        else:
            return 'COUNT'


def get_zh_name(one_series: OneSeries) -> str:
    name = one_series.name
    zh_name = one_series.zh_name
    agg_fn = one_series.agg_fn
    agg_fn_zh = one_series.agg_fn_zh
    gb_fn_zh = one_series.gb_fn_zh

    fn_zh = agg_fn_zh if agg_fn_zh else gb_fn_zh
    if not fn_zh:
        return zh_name

    elif 'count' not in agg_fn.lower():
        return f'{zh_name}({fn_zh})'

    elif d_field_2_info[name].table in d_entity_2_tables['ApplicantStandardResume']:
        return '简历数量'

    elif d_field_2_info[name].table in d_entity_2_tables['Job']:
        return '职位数量'

    return f'{zh_name}({fn_zh})'


def filter_duplicate_selects(selects: list, d_select: {}, filter_internal=True):
    d_internal = {}
    for i, select in reversed(list(enumerate(selects))):
        mid = md5(select)
        if mid not in d_select and (not filter_internal or select.name not in d_internal):
            d_select[mid] = 1
            d_internal[select.name] = 1
        else:
            selects.pop(i)


@app.post('/v1/figure/fields',
          name="v1 figure fields",
          response_model=Response,
          description="预想输入 (正在输入时)，返回相近的value或column的列表(top k)")
def figure_fields(_input: FigureInput, tenant: Optional[str] = Header('')):
    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'tenant: {tenant}, payload: {_input}')

    tenant = tenant.default if not isinstance(tenant, str) else tenant

    fig_type = _input.fig_type.lower()
    x_selects = _input.x
    y_selects = _input.y
    not_visualized_selects = _input.not_visualized
    wheres = _input.wheres

    # 检查参数
    if fig_type and fig_type not in ['', 'line', 'bar']:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': 'fig_type 暂时只支持 【 line, bar 】'})

    if not x_selects and not y_selects and not not_visualized_selects:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': 'x, y, not_visualized 不能都为空'})

    if (x_selects and not y_selects and not_visualized_selects) or \
            (not x_selects and y_selects and not_visualized_selects):
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': 'x轴, y轴 必须都有值'})

    if not x_selects and not y_selects and len(not_visualized_selects) < 2:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': '字段数量至少为2才能展示图表'})

    if len(x_selects) > 1:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': 'X轴只能允许有一个字段'})

    tmp_d = {}
    filter_duplicate_selects(x_selects, tmp_d)
    filter_duplicate_selects(y_selects, tmp_d)
    filter_duplicate_selects(not_visualized_selects, tmp_d, filter_internal=False)

    d_selects = {}
    for v in copy.deepcopy(x_selects + y_selects + not_visualized_selects):
        v.aggregation = ''
        d_selects[v.name] = v
    selects = list(d_selects.values())

    ret_sql = sql_from_editor(EditorInput(selects=selects, wheres=wheres))
    if ret_sql['ret'] == 0:
        return ret_sql

    # 根据 sql 请求数据
    data = query(ret_sql['sql'] + ' limit 100', tenant)

    d_column_2_data_len = {}
    for i, select in enumerate(selects):
        tmp_data = list(map(lambda x: x[i], data))
        tmp_data = list(filter(lambda x: x and f'{x}'.strip(), tmp_data))
        d_column_2_data_len[select.name] = len(tmp_data)

    x_options = list(map(lambda x: {'select': x, 'type': get_type(x.name, x.aggregation)}, x_selects))
    y_options = list(map(lambda x: {'select': x, 'type': get_type(x.name, x.aggregation)}, y_selects))
    not_options = list(map(lambda x: {'select': x, 'type': get_type(x.name, x.aggregation)}, not_visualized_selects))

    if not x_options and not y_options:
        # 选 本来就 符合条件的情况
        valid_options = []

        for x_i, x_option in enumerate(not_options):
            _x_type = x_option['type']

            for y_i, y_option in enumerate(not_options):
                if x_i == y_i:
                    continue

                _y_type = y_option['type']
                _type = f'{_x_type}&&{_y_type}'
                _check_not_visualized_at_final(fig_type, _type, valid_options, d_column_2_data_len, x_option, y_option,
                                               x_i, y_i)

        # 选 需要改造 X/Y轴 字段 的情况
        if not valid_options:
            for x_i, x_option in enumerate(not_options):
                x_name = x_option['select'].name
                x_agg_fn = x_option['select'].aggregation
                _x_type = x_option['type']

                for y_i, y_option in enumerate(not_options):
                    if x_i == y_i:
                        continue

                    y_name = y_option['select'].name
                    y_agg_fn = y_option['select'].aggregation
                    _y_type = y_option['type']

                    # 先尝试改造 y；检验；检验 not_visualize
                    new_y_agg_fn = get_agg_fn(y_agg_fn, y_name)
                    new_y_type = get_type(y_name, new_y_agg_fn)

                    new_type = f'{_x_type}&&{new_y_type}'
                    _check_not_visualized_at_final(fig_type, new_type, valid_options, d_column_2_data_len, x_option,
                                                   y_option, x_i, y_i)

                    # 不成功，尝试改造 x；检验；检验 not_visualize
                    new_x_agg_fn = get_agg_fn(x_agg_fn, x_name)
                    new_x_type = get_type(x_name, new_x_agg_fn)

                    new_type = f'{new_x_type}&&{_y_type}'
                    _check_not_visualized_at_final(fig_type, new_type, valid_options, d_column_2_data_len, x_option,
                                                   y_option, x_i, y_i)

                    # 不成功，同时改造 x, y
                    new_type = f'{new_x_type}&&{new_y_type}'
                    _check_not_visualized_at_final(fig_type, new_type, valid_options, d_column_2_data_len, x_option,
                                                   y_option, x_i, y_i)

        # 若选取成功
        if valid_options:
            valid_options.sort(key=lambda x: (
                -d_column_2_data_len[x['x']['select'].name] + -d_column_2_data_len[x['y']['select'].name], x['index']))

            # 获取 选取的 x/y 轴的字段
            x_options.append(valid_options[0]['x'])
            y_options.append(valid_options[0]['y'])

            min_i = min(valid_options[0]['x_i'], valid_options[0]['y_i'])
            max_i = max(valid_options[0]['x_i'], valid_options[0]['y_i'])
            not_options.pop(max_i)
            not_options.pop(min_i)

            fig_type = valid_options[0]['fig_type']

        else:
            return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': '不存在符合构造图表的字段'})

    final_options = []

    for x_option in x_options:
        x_name = x_option['select'].name
        x_agg_fn = x_option['select'].aggregation
        _x_type = x_option['type']

        for y_option in y_options:
            y_name = y_option['select'].name
            y_agg_fn = y_option['select'].aggregation
            _y_type = y_option['type']
            _type = f'{_x_type}&&{_y_type}'

            valid_num = _check_not_visualized_at_final(fig_type, _type, final_options, d_column_2_data_len, x_option,
                                                       y_option)
            if valid_num:
                continue

            # 否则，改造 y_option 或 x_option 以达到图表的字段要求
            else:
                # 先尝试改造 y；检验；检验 not_visualize
                new_y_agg_fn = get_agg_fn(y_agg_fn, y_name)
                new_y_type = get_type(y_name, new_y_agg_fn)

                new_type = f'{_x_type}&&{new_y_type}'
                valid_num = _check_not_visualized_at_final(fig_type, new_type, final_options, d_column_2_data_len,
                                                           x_option, y_option)
                if valid_num:
                    for valid_i in range(1, valid_num + 1):
                        final_options[-valid_i]['y']['select'].aggregation = new_y_agg_fn
                    continue

                # 不成功，尝试改造 x；检验；检验 not_visualize
                new_x_agg_fn = get_agg_fn(x_agg_fn, x_name)
                new_x_type = get_type(x_name, new_x_agg_fn)

                new_type = f'{new_x_type}&&{_y_type}'
                valid_num = _check_not_visualized_at_final(fig_type, new_type, final_options, d_column_2_data_len,
                                                           x_option, y_option)
                if valid_num:
                    for valid_i in range(1, valid_num + 1):
                        final_options[-valid_i]['x']['select'].aggregation = new_x_agg_fn
                    continue

                # 不成功，同时改造 x, y
                new_type = f'{new_x_type}&&{new_y_type}'
                valid_num = _check_not_visualized_at_final(fig_type, new_type, final_options, d_column_2_data_len,
                                                           x_option, y_option)
                if valid_num:
                    for valid_i in range(1, valid_num + 1):
                        final_options[-valid_i]['x']['select'].aggregation = new_x_agg_fn
                        final_options[-valid_i]['y']['select'].aggregation = new_y_agg_fn
                    continue

                return logs.ret(log_id, logs.fn_name(), 'POST', {
                    'ret': 0, 'msg': f'x轴 ({x_name} {x_agg_fn})，y轴 ({y_name} {y_type}) 不符合构造图表 {fig_type} 的条件'})

    if not final_options:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': f'不存在能符合构造图表的字段'})

    # 根据 final_options 去请求 data 并 返回数据
    d_xid_2_x_y_list = {}
    for option in final_options:
        xid = md5([option['x'], option['fig_type']])
        if xid not in d_xid_2_x_y_list:
            d_xid_2_x_y_list[xid] = {'x': option['x'], 'y': {}, 'index': option['index'],
                                     'fig_type': option['fig_type']}

        yid = md5(option['y'])
        d_xid_2_x_y_list[xid]['y'][yid] = option['y']

    l_xid_2_x_y_list = list(d_xid_2_x_y_list.items())
    l_xid_2_x_y_list.sort(
        key=lambda x: (
            -d_column_2_data_len[x[1]['x']['select'].name] - (
                d_column_2_data_len[list(x[1]['y'].values())[0]['select'].name] if x[1]['y'] else 0),  # 数量
            x[1]['index'],  # index 先后
            -len(x[1]['y'])  # 多少 y 轴的数量
        )
    )

    x_y_list = l_xid_2_x_y_list[0][1]

    final_x_type: str = x_y_list['x']['type']
    final_x_select: Select = x_y_list['x']['select']
    final_y_selects: List[Select] = list(map(lambda x: x['select'], x_y_list['y'].values()))
    fig_type: str = x_y_list['fig_type']

    # 生成 sql
    selects = [final_x_select] + final_y_selects

    ret_sql = sql_from_editor(EditorInput(selects=selects, wheres=wheres))
    if ret_sql['ret'] == 0:
        return ret_sql

    # 获取 sql
    sql = ret_sql['sql'] + ' limit 100'

    # 根据 sql 请求数据
    data = query(sql, tenant)
    if data is None:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msq': 'sql query 接口报错'})

    x_values = list(map(lambda x: f'{x[0]}' if isinstance(x[0], list) else x[0], data))

    if fig_type in ['line'] and final_x_type in ['dim_actual_int']:
        x_labels = x_values
        x_values = list(range(1, len(data) + 1))

    elif fig_type in ['line'] and final_x_type in ['dim_date']:
        x_labels = x_values

        valid_values = list(filter(lambda x: x, x_labels))
        if valid_values:
            min_timestamp = date2timestamp(min(valid_values))
            x_values = list(map(
                lambda x: int((date2timestamp(x[0]) - min_timestamp) / 86400) if x[0] else -1,
                data
            ))
        else:
            x_values = list(range(1, len(data) + 1))

    else:
        x_values = list(map(lambda x: f'{x[0]}' if isinstance(x[0], list) else x[0], data))
        x_labels = []

    x_data = OneSeries(
        name=final_x_select.name,
        zh_name=to_zh(final_x_select.name),
        agg_fn=final_x_select.aggregation,
        agg_fn_zh=to_zh(final_x_select.aggregation),
        gb_fn=final_x_select.group_by,
        gb_fn_zh=to_zh(final_x_select.group_by),
        type='',
        data=x_values,
        labels=x_labels,
    )

    y_series = []
    for i, final_y_select in enumerate(final_y_selects):
        y_series.append(OneSeries(
            name=final_y_select.name,
            zh_name=to_zh(final_y_select.name),
            agg_fn=final_y_select.aggregation,
            agg_fn_zh=to_zh(final_y_select.aggregation),
            gb_fn=final_y_select.group_by,
            gb_fn_zh=to_zh(final_y_select.group_by),
            type=fig_type,
            data=list(map(lambda x: x[i + 1], data)),
            labels=[]
        ))

    x_name = get_zh_name(x_data)
    y_names = list(map(get_zh_name, y_series))
    y_name_str = ', '.join(y_names)

    x_short_name = x_name.split('.')[-1]
    y_short_name_str = ', '.join(list(map(lambda x: x.split('.')[-1], y_names)))

    title = f'{x_name} vs {y_name_str}'

    if fig_type == 'line':
        description = f'按 {x_short_name} 分组，分析随着 {x_short_name} 增长，{y_short_name_str} 的变化趋势'
    else:
        description = f'按 {x_short_name} 分组，分析不同 {x_short_name} 的 {y_short_name_str} 的分布情况'

    not_visualized = list(map(lambda x: OneSeries(
        name=x['select'].name,
        zh_name=to_zh(x['select'].name),
        agg_fn=x['select'].aggregation,
        agg_fn_zh=to_zh(x['select'].aggregation),
        gb_fn=x['select'].group_by,
        gb_fn_zh=to_zh(x['select'].group_by),
        type='',
        data=[],
        labels=[]
    ), not_options))

    return logs.ret(log_id, logs.fn_name(), 'POST', {
        'ret': 1,
        'x': x_data,
        'series': y_series,
        'title': title,
        'description': description,
        'not_visualized': not_visualized,
    })


if __name__ == '__main__':
    print('\n------------------------------')
    test_x_list = [
        # Select(name="ResumeName", aggregation=''),
        # Select(name="WorkExperienceCompanyNameLinked"),
        # Select(name="EducationExperienceDateRangeNormalizedStart", aggregation=''),
    ]

    test_y_list = [
        # Select(name="ResumeName", aggregation='Count'),
        # Select(name="ResumeName", aggregation='Count'),
        # Select(name="WorkExperienceCompanyNameLinked"),
    ]

    test_not_visualized_list = [
        # Select(name="WorkExperienceCompanyNameLinked"),
        # Select(name="ResumeName", aggregation='Count'),
        Select(name="EducationExperienceDateRangeNormalizedStart", aggregation='', group_by='ByYear'),
        Select(name="ResumeName", aggregation=''),
        # Select(name="WorkExperienceSalaryRangeNormalizedGte", aggregation=''),
        Select(name="ResumeWorkYearNormalizedGte", aggregation=''),
        # Select(name="ResumeName", aggregation=''),
        # Select(name="EducationExperienceDegreeNameNormalized", aggregation=''),
        # Select(name="WorkExperienceJobNamesLinked"),
        # Select(name="ResumeAgeNormalized"),
    ]

    ret = figure_fields(FigureInput(
        fig_type='',
        x=test_x_list,
        y=test_y_list,
        not_visualized=test_not_visualized_list,
        wheres=[],
    ))

    print(ret)

    if 'x' in ret:
        print('\n----------------- x --------------------')
        print(ret['x'])

    if 'series' in ret:
        print('\n----------------- series --------------------')
        for v in ret['series']:
            print(v)

        print('\n------------------ fig_type --------------------------')
        print(f'\nfig_type: {list(map(lambda x: x.type, ret["series"]))}')

    if 'not_visualized' in ret:
        print('\n----------------- not_visualized --------------------')
        for v in ret['not_visualized']:
            print(v)

    if 'title' in ret:
        print('\n----------------- other --------------------')
        print(ret['title'])
        print(ret['description'])
