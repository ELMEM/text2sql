import os
import re
import json
import threading
import time
import sys

os.environ['CUDA_VISIBLE_DEVICES'] = '1'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)
from typing import List, Union
from server.definitions.suggestions import Prediction, Choice, LastChoice
from core.encode import encode
from server.interfaces.data.data_search_values_by_vectors import data_search_values_by_vectors, QueryValueInput
from server.interfaces.data.data_search_descriptions_by_vectors import data_search_descriptions_by_vectors, \
    QueryDescInput
from server.interfaces.data.data_search_avg_values_by_vecotrs_with_milvus import \
    data_search_avg_values_by_vectors_with_milvus, \
    QueryAvgValueInput
from config.path import RULE_DIR
from lib.utils import convert_reg
from lib import logs
from lib.preprocess import preprocess
from core.processor import process_prediction, int_fields, float_fields, to_zh, d_field_2_info, count_fns


def _load_config(prefix: str = 'type'):
    """ 加载规则配置，并预编译正则 """
    final_rules = []

    _rule_files = list(filter(lambda x: x.startswith(prefix), os.listdir(RULE_DIR)))
    for file_name in _rule_files:
        with open(os.path.join(RULE_DIR, file_name), 'rb') as f:
            rules: List[dict] = json.load(f)

        # 提前 compile 正则
        for rule in rules:
            if 'rule' not in rule:
                rule['rule'] = []
            for v in rule['rule']:
                if 'type' in v:
                    v['type'] = re.compile(v['type'], re.IGNORECASE)
                if 'reg' in v:
                    v['reg'] = re.compile(v['reg'], re.IGNORECASE)

        final_rules += rules

    # 根据配置的历史长度排序，越长越靠前
    if final_rules:
        final_rules.sort(key=lambda x: -len(x['rule']))

    return final_rules


def _match_each_data(rule: dict,
                     choices: List[Choice],
                     is_cur: bool,
                     pre_values: List[str] = [],
                     next_values: List[str] = []):
    if not rule:
        return []

    matched_indices = []
    for i, choice in enumerate(choices):
        if 'type' in rule and not rule['type'].search(choice.type):
            continue
        if 'texts' in rule and choice.text not in rule['texts']:
            continue
        if 'values' in rule and choice.value not in rule['values']:
            continue
        if 'reg' in rule and not rule['reg'].search(choice.text):
            continue
        if 'support_fn' in rule:
            support_fn: str = rule['support_fn']
            for j, pre_v in enumerate(reversed(pre_values)):
                support_fn = support_fn.replace(f'${j + 1}', convert_reg(pre_v))
            for j, next_v in enumerate(next_values):
                support_fn = support_fn.replace(f'#{j + 1}', convert_reg(next_v))
            if choice.value not in d_field_2_info or \
                    support_fn not in d_field_2_info[choice.value].aggregations + d_field_2_info[choice.value].gb_fns:
                continue
        if 'value_reg' in rule:
            value_reg_str: str = rule['value_reg']
            for j, pre_v in enumerate(reversed(pre_values)):
                value_reg_str = value_reg_str.replace(f'${j + 1}', convert_reg(pre_v))
            for j, next_v in enumerate(next_values):
                value_reg_str = value_reg_str.replace(f'#{j + 1}', convert_reg(next_v))
            value_reg = re.compile(value_reg_str, re.IGNORECASE)
            if not value_reg.search(choice.value):
                continue

        # 只有匹配当前输入时，才会有 pre_values 传入；若不是匹配当前输入，则表示到此该 choice 匹配成功
        if not is_cur:
            matched_indices.append(i)
            continue

        # 若匹配当前输入
        if 'score' in rule and choice.score < rule['score']:
            continue
        if 'score_less' in rule and choice.score > rule['score_less']:
            continue
        matched_indices.append(i)

    return matched_indices


def _match_rule(rule: dict,
                prediction: Union[Prediction, LastChoice],
                is_cur: bool,
                pre_values: List[str] = [],
                next_values: List[str] = []):
    if prediction is None:
        return []
    if 'q_text_len_less' in rule and len(prediction.text) > rule['q_text_len_less']:
        return []
    return _match_each_data(rule, prediction.data, is_cur, pre_values, next_values)


def _match_rules(rules: List[dict], prediction: Prediction, suggestion_history: List[LastChoice],
                 cur_index: int = -1, check_all=False) -> Prediction:
    cur_index = len(suggestion_history) if cur_index < 0 else cur_index
    pre_history = suggestion_history[:cur_index]
    next_history = suggestion_history[cur_index:]
    pre_values = list(map(lambda x: x.data[0].value if x and x.data else '', pre_history))
    next_values = list(map(lambda x: x.data[0].value if x and x.data else '', next_history))
    len_pre = len(pre_values)
    len_next = len(next_values)
    len_input = len(suggestion_history) + 1
    has_match_any_rule = False  # 是否有匹配到任意一条规则

    for rule in rules:
        base_bonus = rule['bonus'] if 'bonus' in rule else 0.02
        one_rules = rule['rule']
        len_one_rule = len(one_rules)

        # 判断历史长度与规则长度
        if len_one_rule > len_input:
            continue

        # 扫描该规则的每一项，与当前输入进行匹配，确认当前输入对应规则里的位置
        for cur_i, cur_rule in enumerate(one_rules):
            if len_pre < cur_i or len_next < len_one_rule - cur_i - 1:
                continue

            matched_indices = _match_rule(cur_rule, prediction, True, pre_values, next_values)

            # 若无匹配当前输入
            if not matched_indices:
                continue

            pre_rules = one_rules[:cur_i]
            next_rules = one_rules[cur_i + 1:]
            not_match = False

            # 匹配输入前面的历史数据
            if pre_values:
                tmp_next_values = [prediction.data[0].value if prediction.data else ''] + next_values
                for i in range(-1, -len(pre_rules) - 1, -1):
                    tmp_pre_values = pre_values[i + 1:] if i != -1 else []
                    _tmp_next_values = tmp_pre_values + tmp_next_values
                    if not _match_rule(pre_rules[i], pre_history[i], False, pre_values[:i], _tmp_next_values):
                        not_match = True
                        break

            if not_match:
                continue

            # 匹配输入后面的历史数据
            if next_values:
                tmp_pre_values = pre_values + [prediction.data[0].value if prediction.data else '']
                for i in range(len(next_rules)):
                    _tmp_pre_values = tmp_pre_values + next_values[:i]
                    if not _match_rule(next_rules[i], next_history[i], False, _tmp_pre_values, next_values[i + 1:]):
                        not_match = True
                        break

            if not_match:
                continue

            has_match_any_rule = True
            bonus = cur_rule['bonus'] if 'bonus' in cur_rule else base_bonus

            # 根据匹配的 choice 位置，分别添加 bonus
            for i in matched_indices:
                prediction.data[i].score = min(max(bonus + prediction.data[i].score, 0), 1.1)
            prediction.data.sort(key=lambda x: -x.score)

        # 若匹配到一条规则，则停止匹配
        if not check_all and has_match_any_rule:
            break

    return prediction


# 加载配置
RULES = _load_config('type')
RULES_N_GRAM = _load_config('n_gram_type.json')


def combine_avg_score(avg_score, score):
    if avg_score < 0.7:
        return score * 0.85 + 0.15 * avg_score
    else:
        return score


def batch_get_type(texts: List[str]) -> List[Prediction]:
    """
    用于分词后判断 n-gram 的类型 ；此处不考虑 suggestion history
    """
    texts = list(map(preprocess, texts))

    start_ = time.time()

    embeddings = encode(texts)
    end_ = time.time()
    logs.add('unknown', f'batch_get_type', f'encode for "{texts}" : {end_ - start_:.4f}s ')

    start_ = time.time()

    result = _multi_search(embeddings, 20)
    ret_desc = result['desc'] if 'desc' in result else []
    ret_value = result['value'] if 'value' in result else []
    ret_avg_value = result['avg_value'] if 'avg_value' in result else []

    end_ = time.time()
    logs.add('unknown', f'batch_get_type', f'multi search for "{texts}" : {end_ - start_:.4f}s ')

    predictions = []
    for i, text in enumerate(texts):
        d_column_2_avg_score = {}
        if ret_avg_value:
            for v in ret_avg_value[i]:
                column = v['data']['column']
                if column not in d_column_2_avg_score:
                    d_column_2_avg_score[column] = v['similarity']

        value_choices = list(map(lambda x: Choice(
            text=x['data']['text'],
            type='value',
            value=x['data']['column'],
            score=x['similarity'] * 0.85 if x['data']['column'] not in d_column_2_avg_score else
            combine_avg_score(d_column_2_avg_score[x['data']['column']], x['similarity'])
        ), filter(lambda v: v and v['data'], ret_value[i]))) if ret_value else []

        desc_choice = list(map(lambda x: Choice(
            text=x['data']['text'],
            type=x['data']['type'],
            value=x['data']['field'],
            score=x['similarity']
        ), filter(lambda v: v and v['data'], ret_desc[i]))) if ret_desc else []

        # 添加 in text 分数干预
        for choice in desc_choice:
            if text in to_zh(choice.value) or text in choice.text:
                choice.score = min(choice.score + 0.04, 1.1)

        prediction = Prediction(id='', text=text, data=value_choices + desc_choice)
        len_text = len(text)
        prediction.data.sort(key=lambda x: (-x.score, abs(len_text - len(x.text)), len(to_zh(x.value).split('.')[-1])))

        prediction = _match_rules(RULES_N_GRAM, prediction, [], check_all=True)
        predictions.append(prediction)
    return predictions


_reg_num = re.compile(r'^\d+(\.\d+)?$')
_reg_int = re.compile(r'^\d+$')


def get_type_for_number(text: str, suggestion_history: List[LastChoice] = [], top_k: int = 20,
                        cur_index: int = -1) -> Union[Prediction, None]:
    """ 判断 text 类型，如果 输入全是数字，则不进入语义判断，直接根据 history 走规则判断 """
    text = text.strip()
    if not _reg_num.search(text):
        return

    if not _reg_int.search(text):
        num_columns = list(map(lambda x: x.name, float_fields))
    else:
        num_columns = list(map(lambda x: f'____{x}', count_fns)) + list(map(lambda x: x.name, int_fields))

    prediction = Prediction(id='', text=text, data=list(map(lambda x: Choice(
        text=text,
        type='value',
        value=x,
        score=0.85
    ), num_columns)))

    # 根据配置以及历史选择 进行修正
    prediction = _match_rules(RULES, prediction, suggestion_history, cur_index)
    # 处理 prediction 数据 (添加 可透传输入作为choice, 去除重复column的描述，添加ID，取top_k结果)
    process_prediction(prediction, text, suggestion_history, top_k)

    return prediction


def _multi_search(embeddings: List[List[float]], top_k: int) -> dict:
    result = []

    t1 = threading.Thread(target=lambda a, b: b.append(('desc', data_search_descriptions_by_vectors(a))),
                          args=(QueryDescInput(q_vectors=embeddings, top_k=2 * top_k), result))
    t2 = threading.Thread(target=lambda a, b: b.append(('value', data_search_values_by_vectors(a))),
                          args=(QueryValueInput(q_vectors=embeddings, top_k=2 * top_k), result))
    t3 = threading.Thread(target=lambda a, b: b.append(('avg_value', data_search_avg_values_by_vectors_with_milvus(a))),
                          args=(QueryAvgValueInput(q_vectors=embeddings, top_k=2 * top_k), result))

    t1.start()
    t2.start()
    t3.start()

    t1.join()
    t2.join()
    t3.join()

    result = dict(result)
    for k, v in result.items():
        result[k] = v['data'] if v['ret'] == 1 and v['data'] else []

    return result


def get_type(text: Union[str, Prediction],
             suggestion_history: List[LastChoice] = [],
             top_k: int = 15,
             cur_index: int = -1) -> Prediction:
    """
    判断 text 的类型
    :return:
        prediction
    """

    if isinstance(text, str):
        text = preprocess(text)

        start_ = time.time()
        embeddings = encode(text)
        end_ = time.time()
        logs.add('unknown', f'get type', f'encode get type for "{text}" : {end_ - start_:.4f}s ')

        start_ = time.time()

        result = _multi_search(embeddings, top_k)
        ret_desc = result['desc'][0] if 'desc' in result and result['desc'] else []
        ret_value = result['value'][0] if 'value' in result and result['value'] else []
        ret_avg_value = result['avg_value'][0] if 'avg_value' in result and result['avg_value'] else []

        end_ = time.time()
        logs.add('unknown', f'get type', f'multi search for "{text}" : {end_ - start_:.4f}s ')

        d_column_2_avg_score = {}
        for v in ret_avg_value:
            column = v['data']['column']
            if column not in d_column_2_avg_score:
                d_column_2_avg_score[column] = v['similarity']

        value_choices = list(map(lambda x: Choice(
            text=x['data']['text'],
            type='value',
            value=x['data']['column'],
            score=x['similarity'] * 0.85 if x['data']['column'] not in d_column_2_avg_score else
            combine_avg_score(d_column_2_avg_score[x['data']['column']], x['similarity'])
        ), filter(lambda v: v and v['data'], ret_value)))

        desc_choice = list(map(lambda x: Choice(
            text=x['data']['text'],
            type=x['data']['type'],
            value=x['data']['field'],
            score=x['similarity']
        ), filter(lambda v: v and v['data'], ret_desc)))

        # 添加 in text 分数干预
        for choice in desc_choice:
            if text in to_zh(choice.value) or text in choice.text:
                choice.score = min(choice.score + 0.04, 1.1)

        prediction = Prediction(id='', text=text, data=value_choices + desc_choice)
        len_text = len(text)
        prediction.data.sort(key=lambda x: (-x.score, abs(len_text - len(x.text)), len(to_zh(x.value).split('.')[-1])))

        end_2 = time.time()
        logs.add('unknown', f'get type', f'after multi search for "{text}" : {end_2 - end_:.4f}s ')

    else:
        prediction = text
        text = prediction.text

    # 根据配置以及历史选择 进行修正
    prediction = _match_rules(RULES, prediction, suggestion_history, cur_index, check_all=True)
    # 处理 prediction 数据 (添加 可透传输入作为choice, 去除重复column的描述，添加ID，取top_k结果)
    process_prediction(prediction, text, suggestion_history, top_k)
    return prediction


if __name__ == '__main__':
    # 测试代码
    from server.definitions.suggestions import Choice

    history = [
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
        # LastChoice(id='7', text='最小', data=[Choice(text='最小', type='agg_fn', value='Min', score=1.0)]),
        # LastChoice(id='6', text='工作年限上限',
        #            data=[Choice(text='工作年限上限', type='column_desc', value='ResumeWorkYearNormalizedLte', score=1.0)]),
        # # LastChoice(id='8', text='小于', data=[Choice(text='小于', type='comparison_op_desc', value='<', score=1.0)]),
        # LastChoice(id='9', text='2年', data=[
        #     Choice(text='2年', type='value', value='ResumeWorkYearNormalizedLte', score=1.0)])
        LastChoice(id='10', text='北京', data=[
            Choice(text='北京', type='value', value='JobLocationsNormalizedCity', score=1.0, zh_value=None)]),
    ]

    ret_prediction = get_type_for_number("10000", suggestion_history=history)

    print('\n-------------------------------------------------------')
    print(ret_prediction)
    if ret_prediction.data:
        for v in ret_prediction.data:
            print(v)
