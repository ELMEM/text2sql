import re
from functools import reduce
from typing import List, Dict
from server.definitions.suggestions import LastChoice, Relation
from core.relation_extraction import extract_relations
from core.processor import sort_select_columns, to_zh_text, is_normalizable, get_data_type
from normalize.norm import normalize
from lib.preprocess import format_suffix


def get_index_id(_id: str, suggestion_history: List[LastChoice]) -> int:
    """get index of suggestion_history id"""
    _index = [i for i, last in enumerate(suggestion_history) if _id == last.id]
    return _index[0]


def get_select_statement(suggestion_history: List[LastChoice]) -> str:
    """ 获取 select 语句 """
    columns = []
    for last_choice in suggestion_history:
        # 若类型不是 column 相关 或 没有匹配到结果
        column_data = list(filter(lambda x: x.type in ["value", "column_desc", "aggregation_column_desc",
                                                       "time_column_desc", "count_column_desc"],
                                  last_choice.data))
        columns += list(map(lambda x: x.value, column_data))
    columns = columns
    columns = sort_select_columns(columns)
    return f'SELECT {", ".join(columns)} ' if columns else 'SELECT * '


def get_orderby(suggestion_history: List[LastChoice], relations: List[Relation]) -> str:
    orderbyAsc = list(filter(lambda x: x.relation_type == "order_by_Asc", relations))
    orderbyDesc = list(filter(lambda x: x.relation_type == "order_by_Desc", relations))
    if list(map(lambda x: x.tail_id, orderbyAsc)):
        temp_list = list(map(lambda x: x.tail_id, orderbyAsc))
        temp_columns = list(filter(lambda x: x.id in temp_list, suggestion_history))
        columns = list(map(lambda x: x.data[0].type, temp_columns))
        return f'ORDER BY {", ".join(columns)}'
    if list(map(lambda x: x.tail_id, orderbyDesc)):
        temp_list = list(map(lambda x: x.tail_id, orderbyDesc))
        temp_columns = list(filter(lambda x: x.id in temp_list, suggestion_history))
        columns = list(map(lambda x: x.data[0].type, temp_columns))
        return f'ORDER BY {", ".join(columns)} Desc'
    return ''


def process_relations(relations: List[Relation]) -> Dict[str, Dict[str, str]]:
    """
    整理 抽取的关系的 数据结构，返回 d_head_2_tail 字典
        d_head_2_tail[relation.head_id][relation.tail_id] = relation.relation_type
    """
    d_head_2_tail = {}
    for relation in relations:
        if relation.head_id not in d_head_2_tail:
            d_head_2_tail[relation.head_id] = {}
        d_head_2_tail[relation.head_id][relation.tail_id] = relation.relation_type
    return d_head_2_tail


def filter_domain(domain: dict) -> dict:
    """ 过滤空限制 """
    if not domain:
        return {}

    new_domain = {}
    for k, v in domain.items():
        if isinstance(v, list):
            v = list(filter(lambda x: x, v))
        elif isinstance(v, str):
            v = v.strip()

        if v:
            new_domain[k] = v
    return new_domain


def format_value(value, column):
    """ 格式化 查询条件的值; 根据该值以及 column data-type 判断是 字符串 还是 数字  """
    v = f'{value}'
    _data_type = get_data_type(column).lower()
    return v if _reg_num.search(v) and (_data_type.startswith('int') or _data_type.startswith('float')) else f"'{v}'"


def get_equal_statement(values: List[str], column: str, comparison_op: str) -> (str, str):
    """ 获取 =, !=, in, not in 的 条件语句 """
    if not values or comparison_op not in ['', '=', 'in', '!=', 'not in']:
        return '', comparison_op

    # 格式化每个 value
    values = list(map(lambda x: format_value(x, column), values))

    if len(values) == 1 and comparison_op in ['', '=', 'in']:
        comparison_op = '='
    elif len(values) == 1 and comparison_op in ['!=', 'not in']:
        comparison_op = '!='
    elif comparison_op in ['', '=', 'in']:
        comparison_op = 'in'
    else:
        comparison_op = 'not in'

    value_str = f'[{", ".join(values)}]' if len(values) > 1 else values[0]

    return f'{column} {comparison_op} {value_str}', comparison_op


def get_compare_statements(values: List[str], column: str, comparison_op: str) -> List[str]:
    """ 获取 >, >=, <, <= 的条件语句 """
    if not values or comparison_op not in ['>', '>=', '<', '<=']:
        return []

    # 格式化每个 value
    values = list(map(lambda x: format_value(x, column), values))
    return list(map(lambda x: f'{column} {comparison_op} {x}', values))


def get_fn_statements(suggestion_history: List[LastChoice], d_head_2_tail: Dict[str, Dict[str, str]]) \
        -> List[dict]:
    """获取fn字段"""
    d_id_2_last_choice = {v.id: v for v in suggestion_history}
    for last_choice in suggestion_history:
        if last_choice.id in d_head_2_tail:
            for tail_id, relation_type in d_head_2_tail[last_choice.id].items():
                if relation_type in ['fn_param_1', 'concat']:
                    last_choice.data[0].value = format_suffix(
                        last_choice.data[0].value + d_id_2_last_choice[tail_id].data[0].value)
                if relation_type == "replace":
                    last_choice.data[0].value = format_suffix(d_id_2_last_choice[tail_id].data[0].value)
    return suggestion_history


def get_condition_statements(suggestion_history: List[LastChoice], d_head_2_tail: Dict[str, Dict[str, str]]) \
        -> List[dict]:
    """ 获取条件语句 """

    d_id_2_last_choice = {v.id: v for v in suggestion_history}
    conditions = []

    for last_choice in suggestion_history:
        value_data = list(filter(lambda x: x.type == 'value', last_choice.data))
        if not value_data:
            continue

        comparison_op = '='

        # 遍历关系，获取 where_op 的比较符号
        if last_choice.id in d_head_2_tail:
            for tail_id, relation_type in d_head_2_tail[last_choice.id].items():
                if relation_type != 'where_op':
                    continue
                comparison_op = d_id_2_last_choice[tail_id].data[0].value
                break

        # 根据 column 归并 text 值 (解决 同 column 放 in (xxx, xxx, ...) 的问题)
        d_column_2_value = {}
        for choice in last_choice.data:
            if choice.value not in d_column_2_value:
                d_column_2_value[choice.value] = []
            d_column_2_value[choice.value].append(choice.text)

        for column, texts in d_column_2_value.items():
            # 对 texts 值进行 normalize
            d_comparison_op_2_texts = normalize(column, get_data_type(column), comparison_op, texts)

            for _comparison_op, _texts in d_comparison_op_2_texts.items():
                condition_text, comparison_op = get_equal_statement(_texts, column, _comparison_op)
                if condition_text:
                    conditions.append({
                        'ids': [last_choice.id],
                        'text': condition_text,
                        'columns': [column],
                        'comparison_op': _comparison_op,
                        'values': _texts
                    })

                else:
                    condition_texts = get_compare_statements(_texts, column, _comparison_op)
                    if condition_texts:
                        conditions += [{
                            'ids': [last_choice.id],
                            'text': condition_text,
                            'columns': [column],
                            'comparison_op': _comparison_op,
                            'values': [_texts[i]]
                        } for i, condition_text in enumerate(condition_texts)]

    return conditions


def cond_index(conditions: List[dict], _id: str):
    for i, condition in enumerate(conditions):
        if _id in condition['ids']:
            return i
    return -1


_reg_num = re.compile('^\d+(\.\d+)?$')


def __combine_values(conditions: List[dict], index: str) -> List[str]:
    return list(set(reduce(lambda a, b: a + b, list(map(lambda x: x[index], conditions)), [])))


def combine_conditions_in_a_column(conditions: List[dict], condition_op: str = 'or') -> dict:
    if not conditions:
        return {}

    column = conditions[0]['columns'][0]
    equal_conditions = list(filter(lambda x: x['comparison_op'] in ['=', 'in'], conditions))
    not_equal_conditions = list(filter(lambda x: x['comparison_op'] in ['!=', 'not in'], conditions))
    other_conditions = list(filter(lambda x: x['comparison_op'] not in ['=', 'in', '!=', 'not in'], conditions))

    equal_values = reduce(lambda a, b: a + b, list(map(lambda x: x['values'], equal_conditions)), [])
    equal_text, _ = get_equal_statement(equal_values, column, '=')

    not_equal_values = reduce(lambda a, b: a + b, list(map(lambda x: x['values'], not_equal_conditions)), [])
    not_equal_text, _ = get_equal_statement(not_equal_values, column, '!=')

    other_texts = reduce(
        lambda a, b: a + b,
        map(lambda x: get_compare_statements(x['values'], column, x['comparison_op']), other_conditions), []
    )

    if equal_conditions and not not_equal_conditions and not other_conditions:
        return {
            'ids': __combine_values(equal_conditions, 'ids'),
            'text': equal_text,
            'columns': __combine_values(equal_conditions, 'columns'),
            'comparison_op': 'in',
            'values': __combine_values(equal_conditions, 'values'),
        }

    elif not equal_conditions and not_equal_conditions and not other_conditions:
        return {
            'ids': __combine_values(not_equal_conditions, 'ids'),
            'text': not_equal_text,
            'columns': __combine_values(not_equal_conditions, 'columns'),
            'comparison_op': 'not in',
            'values': __combine_values(not_equal_conditions, 'values'),
        }

    else:
        if not condition_op and is_normalizable(column):
            other_text = ' and '.join(other_texts)
        else:
            other_text = f' {condition_op} '.join(other_texts)

        if len(other_texts) > 1:
            other_text = f'( {other_text} )'

        texts = [equal_text, not_equal_text, other_text]
        texts = list(filter(lambda x: x, texts))
        text = ''.join(texts) if len(texts) <= 1 else '(' + f' {condition_op} '.join(texts) + ')'

        ids = __combine_values(equal_conditions, 'ids') + __combine_values(not_equal_conditions, 'ids') + \
              __combine_values(other_conditions, 'ids')
        ids = list(set(ids))

        columns = __combine_values(equal_conditions, 'columns') + __combine_values(not_equal_conditions, 'columns') + \
                  __combine_values(other_conditions, 'columns')
        columns = list(set(columns))

        return {
            'ids': ids,
            'text': text,
            'columns': columns,
            'comparison_op': '',
            'values': [],
        }


def combine_conditions(conditions: List[dict], relations: List[Relation]) -> str:
    if not conditions:
        return ''
    elif len(conditions) == 1:
        return conditions[0]['text']

    # 筛选 条件 relations
    relations = list(filter(lambda x: x.relation_type in ['cond_and', 'cond_or'], relations))
    relations.sort(key=lambda x: -x.priority)

    while len(conditions) > 1:
        if not relations:
            final_conditions = []
            d_column_2_condition = {}
            for condition in conditions:
                columns = condition['columns']
                if len(columns) == 1 and condition['values']:
                    column = columns[0]
                    if column not in d_column_2_condition:
                        d_column_2_condition[column] = []
                    d_column_2_condition[column].append(condition)
                else:
                    final_conditions.append(condition)

            if d_column_2_condition:
                for column, tmp_conditions in d_column_2_condition.items():
                    new_condition = combine_conditions_in_a_column(tmp_conditions)
                    final_conditions.append(new_condition)

            if len(final_conditions) == 1:
                return final_conditions[0]['text'].strip('(').strip(')')
            else:
                return ' and '.join(list(map(lambda x: x["text"], final_conditions)))

        else:
            relation = relations.pop(0)

            head_index = cond_index(conditions, relation.head_id)
            tail_index = cond_index(conditions, relation.tail_id)

            # 若找不到对应的 condition，则跳过该 条件op
            if head_index == -1 or tail_index == -1:
                continue

            head_condition = conditions[head_index]
            tail_condition = conditions[tail_index]

            # 若 两个条件的 column 一样 且只有一个 column，且 comparison_op 都是 = , in
            if len(head_condition['columns']) == 1 and head_condition['columns'] == tail_condition['columns'] and \
                    head_condition['values'] and tail_condition['values'] and relation.relation_type == 'cond_or':
                new_condition = combine_conditions_in_a_column([head_condition, tail_condition], 'or')

            else:
                # 判断条件符号
                cond_op = 'or' if relation.relation_type == 'cond_or' else 'and'
                # 判断子条件是否需要加括号
                head_text = f'( {head_condition["text"]} )' if not head_condition['values'] else head_condition['text']
                tail_text = f'( {tail_condition["text"]} )' if not tail_condition['values'] else tail_condition['text']
                # 合并条件
                text = f'{head_text} {cond_op} {tail_text}'

                new_condition = {
                    'ids': list(set(head_condition['ids'] + tail_condition['ids'])),
                    'text': text,
                    'columns': list(set(head_condition['columns'] + tail_condition['columns'])),
                    'comparison_op': '',
                    'values': []
                }

            # 合并后，删除旧条件，插入新条件
            del conditions[max(head_index, tail_index)]
            del conditions[min(head_index, tail_index)]
            conditions.append(new_condition)

    return conditions[0]['text']


def get_sql(suggestion_history: List[LastChoice], relations: List[Relation], domain: dict = None) -> dict:
    """ 根据之前的所有预测结果，生成完整的 sql """
    process_rela = process_relations(relations)
    suggestion_history_ = get_fn_statements(suggestion_history, process_rela)
    conditions = get_condition_statements(suggestion_history_, process_rela)
    order_text = get_orderby(suggestion_history_, relations)
    select_text = get_select_statement(suggestion_history_)
    print('\n--------------- conditions ----------------------')
    for c in conditions:
        print(c)

    where_text = combine_conditions(conditions, relations)

    # 先保存没有加 domain 的 where 语句，用于前端显示
    zh_where_text = f'；【过滤条件】：{to_zh_text(where_text)}' if where_text else ''
    zh_select_text = to_zh_text(select_text).replace('SELECT ', '【查询】 ').strip()
    zh_order_text = f'; {to_zh_text(order_text.replace("ORDER BY ", "【排序】 "))}'.strip() if order_text else ''

    domain = filter_domain(domain)
    # 若有 domain 限制
    if domain:
        domain_texts = list(map(
            lambda x: get_equal_statement(x[1] if isinstance(x[1], list) else [f'{x[1]}'], x[0], '=')[0],
            domain.items()
        ))
        domain_text = ' and '.join(list(filter(lambda x: x, domain_texts)))

        # 若存在 或 的 where 条件，需要添加括号
        if ' or ' in where_text:
            where_text = f'{domain_text} and ( {where_text} )'
        elif where_text:
            where_text = f'{domain_text} and {where_text}'
        else:
            where_text = domain_text

    where_text = f'WHERE {where_text}' if where_text else ''

    return {
        'sql': f'{select_text.strip()} FROM Recruitment {where_text} {order_text.strip()}'.replace('[', '(').replace(
            ']', ')'),
        'zh_sql': f'{zh_select_text}{zh_where_text}{zh_order_text}'
    }


if __name__ == '__main__':
    # 测试代码
    from server.definitions.suggestions import Choice

    history = [
        # LastChoice(id='1', text='北京',
        #            data=[Choice(text='北京', type='value', value='JobLocationsNormalizedCity', score=1.0)]),
        # LastChoice(id='2', text='and', data=[Choice(text='and', type='condition_op_desc', value='and', score=1.0)]),
        # LastChoice(id='3', text='java工程师', data=[Choice(text='java工程师', type='value', value='JobJobName', score=1.0)]),
        # LastChoice(id='4', text='or', data=[Choice(text='or', type='condition_op_desc', value='or', score=1.0)]),
        # LastChoice(id='5', text='上海',
        #            data=[Choice(text='上海', type='value', value='JobLocationsNormalizedCity', score=1.0)]),
        # LastChoice(id='6', text='and', data=[Choice(text='and', type='condition_op_desc', value='and', score=1.0)]),
        # LastChoice(id='7', text='ios工程师', data=[Choice(text='ios工程师', type='value', value='JobJobName', score=1.0)]),
        # LastChoice(id='1', text='ios程序员', data=[Choice(text='ios程序员', type='value', value='JobJobName', score=1.0)]),
        # LastChoice(id='2', text='最大', data=[Choice(text='最大', type='agg_fn', value='Max', score=1.0)]),
        # LastChoice(id='33', text='（', data=[Choice(text='（', type='keywords', value='（', score=1.0)]),
        # LastChoice(id='3', text='平均薪资', data=[
        #     Choice(text='平均薪资', type='column_desc', value='WorkExperienceSalaryRangeNormalizedGte',
        #            score=1.0)]),
        # LastChoice(id='44', text='）', data=[Choice(text='）', type='keywords', value='）', score=1.0)]),
        # LastChoice(id='4', text='大于', data=[Choice(text='大于', type='comparison_op_desc', value='>', score=1.0)]),
        # LastChoice(id='5', text='2w', data=[
        #     Choice(text='2w', type='value', value='WorkExperienceSalaryRangeNormalizedGte', score=1.0)]),
        # LastChoice(id='41', text='小于', data=[Choice(text='小于', type='comparison_op_desc', value='<', score=1.0)]),
        # LastChoice(id='51', text='4w', data=[
        #     Choice(text='4w', type='value', value='WorkExperienceSalaryRangeNormalizedGte', score=1.0)]),
        LastChoice(id='7', text='数量', data=[Choice(text='数量', type='agg_fn', value='COUNT', score=1.0)]),
        LastChoice(id='33', text='（', data=[Choice(text='（', type='keywords', value='（', score=1.0)]),
        LastChoice(id='6', text='姓名',
                   data=[Choice(text='姓名', type='column_desc', value='ResumeName', score=1.0)]),
        LastChoice(id='34', text=')', data=[Choice(text=')', type='keywords', value=')', score=1.0)]),
        LastChoice(id='8', text='小于', data=[Choice(text='小于', type='comparison_op_desc', value='<', score=1.0)]),
        LastChoice(id='9', text='4', data=[
            Choice(text='4', type='value', value='____COUNT', score=1.0)]),
        LastChoice(id='18', text='大于', data=[Choice(text='大于', type='comparison_op_desc', value='>', score=1.0)]),
        LastChoice(id='19', text='2', data=[
            Choice(text='2', type='value', value='____COUNT', score=1.0)])
        # LastChoice(id='12', text='or', data=[Choice(text='or', type='condition_op_desc', value='or', score=1.0)]),
        # LastChoice(id='13', text='小于', data=[Choice(text='小于', type='comparison_op_desc', value='<', score=1.0)]),
        # LastChoice(id='14', text='4w', data=[
        #     Choice(text='4w', type='value', value='WorkExperienceSalaryRangeNormalizedGte', score=1.0)]),
        # LastChoice(id='15', text='每月', data=[
        #     Choice(text='每月', type='column_desc', value='JobPublishedDateNormalizedByMonth', score=1.0)]),
        # LastChoice(id='16', text='北京',
        #            data=[Choice(text='北京', type='value', value='JobLocationsNormalizedCity', score=1.0)]),
        # LastChoice(id='17', text='java工程师', data=[Choice(text='java工程师', type='value', value='JobJobName', score=1.0)]),
        # LastChoice(id='18', text='平均薪资', data=[
        #     Choice(text='平均薪资', type='aggregation_column_desc', value='WorkExperienceSalaryRangeNormalizedGteAvg',
        #            score=1.0)]),
        # LastChoice(id='19', text='大于', data=[Choice(text='大于', type='comparison_op_desc', value='>', score=1.0)]),
        # LastChoice(id='20', text='2w', data=[
        #     Choice(text='2w', type='value', value='WorkExperienceSalaryRangeNormalizedGteAvg', score=1.0)]),
        # LastChoice(id='21', text='排序', data=[Choice(text='排序', type='keyword', value='OrderByAsc', score=1.0)]),
        # LastChoice(id='22', text='平均薪资', data=[
        #     Choice(text='平均薪资', type='aggregation_column_desc', value='ResumeSalaryRangeNormalizedGteAvg', scor=1.0)])
        # LastChoice(id='0', text='工作地点', data=[
        #     Choice(text='工作地点', type='column_desc', value='JobLocationsNormalizedCity', score=1.0, zh_value=None)]),
        # LastChoice(id='1', text='不在',
        #            data=[Choice(text='不在', type='comparison_op_desc', value='!=', score=1.0, zh_value=None)]),
        # LastChoice(id='99', text='(', type='keyword',
        #            data=[Choice(text='(', type='keyword', value='(', score=1.0, zh_value=None)]),
        # LastChoice(id='2', text='北京', data=[
        #     Choice(text='北京', type='value', value='JobLocationsNormalizedCity', score=1.0, zh_value=None)]),
        # LastChoice(id='3', text='深圳',
        #            data=[Choice(text='深圳', type='value', value='JobLocationsNormalizedCity', score=1.0,
        #                         zh_value=None)]),
        # LastChoice(id='4', text='上海', data=[
        #     Choice(text='上海', type='value', value='JobLocationsNormalizedCity', score=1.0, zh_value=None)]),
        # LastChoice(id='999', text=')',
        #            data=[Choice(text=')', type='keyword', value=')', score=1.0, zh_value=None)])
    ]

    _relations = extract_relations(history)

    print('\n------------ relations ---------------')
    for r in _relations:
        print(r)

    final_sql = get_sql(history, _relations)
    print(f'\nsql: {final_sql["sql"]}')
    print(f'\nzh_sql: {final_sql["zh_sql"]}')
