import os
import re
import json
import requests
import numpy as np
from functools import reduce
from typing import List
from config.path import CONF_DIR
from lib.utils import md5
from config.api import yonghe_domain
from normalize.norm import norm
from server.definitions.suggestions import LastChoice, Prediction, Choice, Column

with open(os.path.join(CONF_DIR, 'entity_2_tables.json'), 'rb') as f:
    d_entity_2_tables = json.load(f)

with open(os.path.join(CONF_DIR, 'keywords.json'), 'rb') as f:
    keywords: list = json.load(f)

_reg_int_end = re.compile(r'Count$')
_reg_float_end = re.compile(r'(Min|Max|Sum|Avg)$')
_reg_date_end = re.compile(r'(ByYear|ByWeek|ByMonth|ByQuarter|ByDate|Date|Time)$')

reg_en = re.compile('[a-zA-Z]+')
reg_zh = re.compile(r'[\u3400-\u9FFF]')
reg_norm_type = re.compile(r'^(date|uint|int|float)', re.IGNORECASE)

agg_fn_2_zh = {"Max": "最大", "Min": "最小", "Avg": "平均", "COUNT": "数量", "UNIQUE_COUNT": '去重数量'}
gb_fn_2_zh = {'ByDate': "每日", 'ByWeek': '每周', 'ByMonth': '每月', 'ByQuarter': "每季度", 'ByYear': '每年'}


def _get_columns_v2() -> List[Column]:
    try:
        ret = requests.get(f'http://{yonghe_domain}/schemas')
        if ret.status_code != 200:
            # 从文件里获取
            with open(os.path.join(CONF_DIR, 'yonghe_columns_v2.json'), 'rb') as f:
                schema: List[dict] = json.load(f)

        else:
            schema: List[dict] = json.loads(ret.content)

    except:
        # 从文件获取
        with open(os.path.join(CONF_DIR, 'yonghe_columns_v2.json'), 'rb') as f:
            schema: List[dict] = json.load(f)

    _columns = []

    # 解析 schema 结构
    for table in schema:
        table_en_name = table['table_name'][2:]
        table_zh_name = table['name']

        _columns.append(Column(name=table_en_name, zh_name=table_zh_name, is_leaf=0))

        for column_val in table['columns']:
            c_en_name = column_val['column_name']
            c_zh_name = column_val['name']

            # 添加叶子节点
            _columns.append(Column(
                name=c_en_name,
                zh_name=c_zh_name,
                is_leaf=1,
                data_type=column_val['type'],
                aggregations=column_val['aggregations'],
                gb_fns=column_val['group_functions'],
                actual_column=column_val['r_column_name'],
                table=table_en_name,
            ))

    return _columns


def get_synonym(texts: List[str], recur_syn=False) -> List[List[str]]:
    from config.api import synonym_domain
    from lib import logs

    try:
        ret = requests.post(f'http://{synonym_domain}/v1/synonym', json={'texts': texts, 'recur_syn': recur_syn})
        if ret.status_code != 200:
            logs.add('API', 'get_synonym', f'{synonym_domain}/v1/synonym return {ret.status_code}',
                     _level=logs.LEVEL_ERROR)
            return list(map(lambda x: [x], texts))

        _synonyms: list = json.loads(ret.content)['synonyms']
        return _synonyms

    except:
        logs.add('API', 'get_synonym', f'{synonym_domain}/v1/synonym parse result error',
                 _level=logs.LEVEL_ERROR)
        return list(map(lambda x: [x], texts))


def _get_columns():
    try:
        ret = requests.get(f'http://{yonghe_domain}/keywords')
        assert ret.status_code == 200
        info: list = json.loads(ret.content)

    except:
        with open(os.path.join(CONF_DIR, 'yonghe_columns.json'), 'rb') as f:
            info = json.load(f)

    # 越长的 column_name 越靠前
    info.sort(key=lambda x: -len(x['name']))

    _d_column_2_info = {v['name']: v for v in info}
    _d_column_2_zh_name = {v['name']: v['chinese_name'] for v in info}
    return _d_column_2_info, _d_column_2_zh_name


def get_table_name(column_name: str) -> str:
    if not column_name:
        return ''

    if column_name in d_field_2_info:
        return d_field_2_info[column_name].table

    upper_s = ord('A')
    upper_e = ord('Z')

    table_name = column_name[0]
    for c in column_name[1:]:
        if upper_s <= ord(c) <= upper_e:
            break
        table_name += c

    if table_name:
        table_name = table_name[0].lower() + table_name[1:]
    return table_name


def get_data_type(column: str):
    if column in d_column_2_info:
        return d_column_2_info[column]['type']
    elif column in d_field_2_info:
        return d_field_2_info[column].data_type if d_field_2_info[column].data_type else ''
    else:
        if _reg_int_end.search(column):
            return f'Int'
        elif _reg_float_end.search(column):
            return 'Float'
        elif _reg_date_end.search(column):
            return 'Date'
        return ''


def to_zh(text: str):
    if not text:
        return text

    text = text.replace('____', '')
    if text in d_column_2_zh_name:
        return d_column_2_zh_name[text]
    elif text in agg_fn_2_zh:
        return agg_fn_2_zh[text]
    elif text in gb_fn_2_zh:
        return gb_fn_2_zh[text]
    else:
        syn_texts = get_synonym([text], recur_syn=True)[0]
        syn_texts = list(filter(lambda x: not reg_en.search(x) and reg_zh.search(x), syn_texts))
        if syn_texts:
            syn_texts.sort(key=lambda x: (len(x.replace(' ', '')), x), reverse=True)
            return syn_texts[0]
        else:
            return text


def to_zh_text(text: str):
    l_ch_zh = list(d_column_2_zh_name.items()) + list(agg_fn_2_zh.items()) + list(gb_fn_2_zh.items())
    l_ch_zh.sort(key=lambda x: -len(x[0]))

    for column, zh_column in l_ch_zh:
        text = text.replace(column, zh_column)
    return text


def filter_columns(suggestion_history: List[LastChoice] = None) -> List[str]:
    """ 输入默认可选的全部 columns (根据 history 去重) """
    if not suggestion_history:
        return list(map(lambda x: x.name, fields_v2))

    history_columns = []
    for last_choice in suggestion_history:
        history_columns += list(map(lambda x: x.value, last_choice.data))
    history_columns = list(set(history_columns))

    _fields = list(filter(lambda x: x.name not in history_columns, fields_v2))
    return list(map(lambda x: x.name, _fields))


def is_normalizable(column: str):
    return reg_norm_type.search(get_data_type(column)) or column.startswith('____')


def find_norm_choices(text: str, prediction: Prediction):
    """ 找出 value 对应的 column 是可以透传的情况 (王永和那边会对输入进行normalize的column) """
    d_indicator_2_score = {}
    for i, choice in enumerate(prediction.data):
        if choice.type == 'value' and choice.text != text and is_normalizable(choice.value):
            if choice.value not in d_indicator_2_score:
                d_indicator_2_score[choice.value] = 0.
            d_indicator_2_score[choice.value] = max(d_indicator_2_score[choice.value], float(choice.score))
    return d_indicator_2_score


def _add_norm_choices(text: str, prediction: Prediction, d_indicator_2_score: dict = None):
    """ 若有 可以透传 的 column (d_indicator_2_score 不为空)，则添加输入的文本作为查询到的 text """
    if not d_indicator_2_score:
        return

    l_column_score = list(filter(lambda x: norm(x[0], get_data_type(x[0]), text), d_indicator_2_score.items()))
    if not l_column_score:
        return

    prediction.data += list(map(
        lambda x: Choice(
            text=norm(x[0], get_data_type(x[0]), text)['value']
            if 'value' in norm(x[0], get_data_type(x[0]), text) else text,
            type='value',
            value=x[0],
            score=min(x[1] + 0.001, 1.1)
        ),
        l_column_score
    ))
    prediction.data.sort(key=lambda x: -x.score)


def remove_duplicate_column(prediction: Prediction):
    """ 一个 prediction 里的 choices，不应该有多个重复 column 的描述，只需保留最高分的那个描述即可 """
    del_indices = []
    d_type_column = {}
    for i, choice in enumerate(prediction.data):
        # 若支持 multi_choice，则 continue
        if choice.type == 'value' and not is_normalizable(choice.value):
            continue

        key = f'{choice.type}____{choice.value}'
        if key not in d_type_column:
            d_type_column[key] = True
            continue
        del_indices.append(i)

    del_indices.reverse()
    for i in del_indices:
        del prediction.data[i]


def is_multi_choice(prediction: Prediction):
    multi_choice = True
    for i, choice in enumerate(prediction.data):
        # 若支持 multi_choice，则 continue
        if choice.type == 'value' and not is_normalizable(choice.value):
            continue

        multi_choice = False
        break

    return multi_choice


def uid(text: str, suggestion_history: List[LastChoice] = None):
    """ 获取 唯一 id """
    return md5(f'{text}_{suggestion_history}' if suggestion_history else text)


def process_prediction(prediction: Prediction, text: str, suggestion_history: List[LastChoice], top_k: int):
    """ 处理 prediction 数据 (添加 可透传输入作为choice, 去除重复column的描述，添加ID，取top_k结果) """
    if prediction is None or not prediction.data:
        return

    # 处理指标数据，增加 输入本身作为选项
    _add_norm_choices(text, prediction, find_norm_choices(text, prediction))

    # 移除重复的 column 的相关描述
    remove_duplicate_column(prediction)

    # 添加 id
    prediction.id = uid(text, suggestion_history)
    # 取 top_k 个结果
    prediction.data = list(filter(lambda x: x.score >= 0.5, prediction.data[:top_k]))
    if prediction.data:
        for choice in prediction.data:
            choice.score = min(choice.score, 1.1)

        len_text = len(text)
        prediction.data.sort(key=lambda x: (-x.score, abs(len_text - len(x.text)), len(to_zh(x.value).split('.')[-1])))

        # 过滤分数差异较大的结果
        max_score = prediction.data[0].score
        std_score = np.std(list(map(lambda x: x.score, prediction.data))) * (1.5 if len_text >= 3 else 3.5)
        prediction.data = list(filter(
            lambda x: x.score >= max_score - 0.1 and x.score >= max_score - std_score,
            prediction.data
        ))

        # 若只有 condition_op_desc, comparison_op_desc
        if not list(filter(lambda x: x.type not in ['condition_op_desc', 'comparison_op_desc'], prediction.data)):
            prediction.data = prediction.data[:1]

        for choice in prediction.data:
            if choice.type in ['column_desc', 'count_column_desc', 'aggregation_column_desc', 'time_column_desc']:
                choice.text = to_zh(choice.value).split('.')[-1]

        if prediction.data[0].type.endswith('desc'):
            prediction.data = list(filter(lambda x: x.type.endswith('desc'), prediction.data))

        if prediction.data[0].type == 'keyword':
            prediction.data = list(filter(lambda x: x.type == 'keyword', prediction.data))

        # if prediction.data[0].type == 'value':
        #     prediction.data = list(filter(lambda x: x.type == 'value', prediction.data))

    # 添加 是否支持多选
    prediction.multi_choice = is_multi_choice(prediction)
    # 翻译成中文
    for v in prediction.data:
        v.zh_value = to_zh(v.value)


def _get_type_index(column: str):
    data_type = get_data_type(column).lower()
    if data_type.startswith('string'):
        return 0
    elif data_type.startswith('uint') or data_type.startswith('int') or data_type.startswith('float'):
        if column in d_field_2_info:
            return 1
        else:
            return 2
    elif '____' in column:
        return 3
    elif data_type.startswith('date'):
        return 4
    else:
        return 5


def sort_select_columns(_columns: List[str]):
    _d_columns = {c: i for i, c in reversed(list(enumerate(_columns)))}
    _columns = list(_d_columns.items())
    _columns.sort(key=lambda x: (_get_type_index(x[0]), x[1], x[0]))
    return list(map(lambda x: x[0], _columns))


# 获取 v2 版本的 column 信息
columns_v2 = _get_columns_v2()

# 字段 -> 信息 的 dict
d_field_2_info = {c.name: c for c in columns_v2}

d_column_2_info, d_column_2_zh_name = _get_columns()

# 添加 父节点 的中文名翻译
for field, info in d_field_2_info.items():
    if field not in d_column_2_info:
        d_column_2_zh_name[field] = info.zh_name

# table
tables_v2 = list(filter(lambda x: x.is_leaf == 0, columns_v2))

# 字段
fields_v2 = list(filter(lambda x: x.is_leaf == 1, columns_v2))

# 维度字段
dim_fields = list(filter(lambda x: 'COUNT' in x.aggregations, fields_v2))

# 指标字段
indicator_fields = list(filter(lambda x: 'Avg' in x.aggregations, fields_v2))

# 支持的聚合函数列表
agg_fns = list(map(lambda x: x.aggregations, fields_v2))
agg_fns: List[str] = list(set(reduce(lambda a, b: a + b, agg_fns, [])))

# 支持计数的函数列表
count_fns: List[str] = list(filter(lambda x: 'count' in x.lower(), agg_fns))

# 支持的分组函数列表
gb_fns = list(map(lambda x: x.gb_fns, fields_v2))
gb_fns: List[str] = list(set(reduce(lambda a, b: a + b, gb_fns, [])))

# 获取 int, float columns
int_fields = list(filter(lambda x: get_data_type(x.name).lower().startswith('int'), fields_v2))
float_fields = list(filter(lambda x: get_data_type(x.name).lower().startswith('float'), fields_v2))
