import re
from typing import List, Dict
from normalize.utils.match_zhnum import MatchingChineseNumbers
from normalize.utils.trans2num import trans
from normalize import age, degree, number, salary, time_normalize, salary_float, age_float, time_normalize_date

column_2_fn = [
    {"reg": r'((^|[_\- ])salary|(^|[a-z_\- ])Salary)[. \-_]?Months', 'fn': number},
    {"reg": r'((^|[_\- ])work|(^|[a-z_\- ])Work)[. \-_]?[yY]ear', 'fn': number},
    {"reg": r'((^|[_\- ])head|(^|[a-z_\- ])Head)[. \-_]?[cC]ount', 'fn': number},
    {"reg": r'((^|[_\- ])subordinate|(^|[a-z_\- ])Subordinate)[. \-_]?([nN]umber|[nN]um|[cC]ount)?',
     'fn': number},
    {"reg": r'((^|[_\- ])salary|(^|[a-z_\- ])Salary)', 'type': 'int', 'fn': salary},
    {"reg": r'((^|[_\- ])salary|(^|[a-z_\- ])Salary)', 'type': 'float', 'fn': salary_float},
    {"reg": r'((^|[_\- ])degree|(^|[a-z_\- ])Degree)', 'fn': degree},
    {'reg': r'((^|[_\- ])date|(^|[a-z_\- ])Date)', 'type': 'DateTime', 'fn': time_normalize},
    {'reg': r'((^|[_\- ])date|(^|[a-z_\- ])Date)', 'type': 'Date', 'fn': time_normalize_date},
    {'reg': r'((^|[_\- ])age|(^|[a-z_\- ])Age)', 'type': 'int', 'fn': age},
    {'reg': r'((^|[_\- ])age|(^|[a-z_\- ])Age)', 'type': 'float', 'fn': age_float}
]

column_2_fn = list(map(
    lambda x: {
        'reg': re.compile(x['reg']),
        'type': re.compile(x['type'], re.IGNORECASE) if 'type' in x else '',
        'fn': x['fn']
    },
    column_2_fn
))


def normalization(text) -> dict:
    text2norm = {}
    if isinstance(text, str):
        text2norm["value"] = text
        return text2norm
    if isinstance(text, dict):
        return text
    else:
        if text.gte and text.lte and text.lte == text.gte:
            text2norm["value"] = text.lte
        elif text.lte and text.gte and text.lte != text.gte:
            text2norm["lte"] = text.lte
            text2norm["gte"] = text.gte
        elif text.gte:
            text2norm["gte"] = text.gte
            text2norm["lte"] = None
        elif text.lte:
            text2norm["lte"] = text.lte
            text2norm["gte"] = None
    return text2norm


def norm(column: str, data_type: str, text: str) -> dict:
    """
    根据 column 进行 normalize
     所有字段的 normalize 函数都应该返回 {'value': xxx, 'gte': xxx, 'lte': xxx} 的格式
    """
    norm_fns = list(filter(
        lambda x: x['reg'].search(column) and (not x['type'] or x['type'].search(data_type)), column_2_fn))
    if not norm_fns:
        return {}

    # 转换中文数字
    if MatchingChineseNumbers(text):
        text_cn = MatchingChineseNumbers(text)
        text = text.replace(text_cn, str(trans(text_cn)))

    fn = norm_fns[0]['fn']
    return fn.normalize(text)


def normalize(column: str, data_type: str, comparison_op: str, texts: List[str]) -> Dict[str, List[str]]:
    """ 返回的数据形式：{ "=": ["1", "2"], ">": [xxx], "<": [xxx], ">=": [], ... } """
    if not data_type:
        return {comparison_op: texts}

    try:
        norm_list = list(map(lambda x: norm(column, data_type, x), texts))
    except Exception as e:
        print(f'Normalization Error: {e}')
        norm_list = []

    norm_list = list(map(normalization, norm_list))

    non_op_list = list(map(lambda y: y["value"], filter(lambda x: 'value' in x and x['value'], norm_list)))
    gt_texts = list(map(lambda y: y["gte"], filter(lambda x: 'gte' in x and x['gte'], norm_list)))
    lt_texts = list(map(lambda y: y["lte"], filter(lambda x: 'lte' in x and x['lte'], norm_list)))

    if comparison_op in [">", ">="]:
        # 先选 non_op_list, 再选 lt_texts，再选 gt_texts，再选 texts
        return {comparison_op: non_op_list if non_op_list else (
            lt_texts if lt_texts else (gt_texts if gt_texts else texts))}

    if comparison_op in ["<", "<="]:
        # 先选 non_op_list, 再选 gt_texts，再选 lt_texts，再选 texts
        return {comparison_op: non_op_list if non_op_list else (
            gt_texts if gt_texts else (lt_texts if lt_texts else texts))}

    d_comparison_op_2_texts = {}
    if non_op_list:
        d_comparison_op_2_texts[comparison_op] = non_op_list
    if gt_texts:
        d_comparison_op_2_texts['>='] = gt_texts
    if lt_texts:
        d_comparison_op_2_texts['<='] = lt_texts
    if not d_comparison_op_2_texts:
        d_comparison_op_2_texts[comparison_op] = texts
    return d_comparison_op_2_texts


if __name__ == "__main__":
    # test_text = norm("WorkYear", "int", "12到13年")
    test_text = normalize("HeadCount", 'int', ">", ["2w"])
    print(test_text)
