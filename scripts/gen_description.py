import os
import sys
import re
import json
import copy
import shutil
from typing import List
from functools import reduce

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from config.path import DESC_DIR
from core.processor import d_column_2_zh_name

reg_en = re.compile('[a-zA-Z]+')
reg_zh = re.compile(r'[\u3400-\u9FFF]')

min_fn = ['min']
min_pre = ['最小', '最少', '最低', 'min']
min_suf = ['最小值', '下限', 'min']

max_fn = ['max']
max_pre = ['最大', '最高', '最多', 'max']
max_suf = ['最大值', '上限', 'max']

avg_fn = ['avg', 'mean', 'average']
avg_pre = ['avg', 'average', 'mean', '平均']
avg_suf = ['均值', '平均值', 'avg', 'average', 'mean']

sum_fn = ['sum']
sum_pre = ['sum', '总']
sum_suf = ['sum', '总数', '总量', '总额']

unique_count_fn = ["distinct_count", "distinct_number", 'unique_count', 'unique_number']
unique_count_pre = ["count", "num", "number", "unique count", "unique num", "unique number", "distinct count",
                    'distinct number', "不同的数量", "唯一数量", "多少", "多少个", "数量", "独特数量"]
unique_count_suf = ["count", "num", "number", "unique", "unique count", "unique num", "unique number", "distinct count",
                    'distinct number', "不同的数量", "唯一数量", "数量", "独特数量", "去重数量"]

count_fn = ["count", "number"]
count_pre = ["count", "num", "number", "多少", "多少个", "数量"]
count_suf = ["count", "num", "number", "数量", "个数", "数", "总数量"]

day_fn = ["by_date"]
day_pre = ['daily', 'each day', 'every day', 'by date', 'by day', '每天', '每日', '每一天', '每一日', '不同日期']
day_suf = ['daily', 'each day', 'every day', 'by date', 'by day', '每天', '每日', '每一天', '每一日', '不同日期']

week_fn = ['by_week']
week_pre = ['by week', 'every week', 'weekly', 'each week', 'all weeks', '每周', '每一周', '每星期', '每一星期', '所有周', '各星期', '各周',
            '各个星期', '所有星期', '所有周']
week_suf = copy.deepcopy(week_pre)

month_fn = ['by_month']
month_pre = ['each month', 'every month', 'by month', 'all months', '每月', '不同月份', '每个月', '每个月份', '各月', '各月份', 'monthly',
             '所有月份', '每一个月', '每一个月份']
month_suf = copy.deepcopy(month_pre)

quarter_fn = ['by_quarter']
quarter_pre = ['每个季度', '每季度', '每季', 'each quarter', 'every quarter', 'by quarter', 'quarterly', '各季度', '各个季度', '所有季度',
               '不同季度', '每一个季度', '每一季']
quarter_suf = copy.deepcopy(quarter_pre)

year_fn = ['by_year']
year_pre = ['yearly', 'each year', 'every year', 'all years', 'by year', '每年', '每一年', '每个年份', '所有年', '所有年份', '不同年份',
            '各个年份', '各年']
year_suf = copy.deepcopy(year_pre)


def show(l: List[str]) -> List[str]:
    # l = list(filter(lambda x: not (reg_en.search(x) and reg_zh.search(
    #     x)) and '(' not in x and ')' not in x and '（' not in x and '）' not in x, l))
    l = list(set(l))
    l.sort()
    # for i, v in enumerate(l):
    #     print(f'{i}: {v}')
    return l


def write(name, data, dir_path=''):
    with open(f'{dir_path}{name}.json', 'wb') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))


def _add_pre_suf(l: List[str], fn, pre, suf) -> List[str]:
    for v in suf:
        if reg_zh.search(v) and not v.startswith('的'):
            suf.append(f'的{v}')

    ll = copy.deepcopy(l)
    ll = [list(map(lambda x: f'{p}({x})', ll)) for p in fn] + \
         [
             list(map(
                 lambda x: (f'{p} {x}' if reg_en.search(p) else f'{p}{x}')
                 if not list(filter(lambda a: x.startswith(a), pre)) else x,
                 ll
             )) for p in pre
         ] + \
         [
             list(map(
                 lambda x: (f'{x} {p}' if reg_en.search(p) else f'{x}{p}')
                 if not list(filter(lambda a: x.endswith(a), pre)) else x,
                 ll
             )) for p in suf
         ]
    ll = reduce(lambda a, b: a + b, ll)
    ll = show(ll)
    return ll


def _add_sum(l: List[str]):
    return _add_pre_suf(l, sum_fn, sum_pre, sum_suf)


def _add_avg(l: List[str]):
    return _add_pre_suf(l, avg_fn, avg_pre, avg_suf)


def _add_min(l):
    return _add_pre_suf(l, min_fn, min_pre, min_suf)


def _add_max(l: List[str]):
    return _add_pre_suf(l, max_fn, max_pre, max_suf)


def _add_count(l: List[str], c_pre=[], c_next=[]):
    new_l = copy.deepcopy(count_pre if not c_pre else c_pre) + copy.deepcopy(
        count_suf if not c_next else c_next) + _add_pre_suf(l, count_fn, count_pre if not c_pre else c_pre,
                                                            count_suf if not c_next else c_next)
    return show(new_l)


def _add_unique_count(l: List[str], c_pre=[], c_next=[]):
    new_l = copy.deepcopy(unique_count_pre if not c_pre else c_pre) + copy.deepcopy(
        unique_count_suf if not c_next else c_next) + _add_pre_suf(l, unique_count_fn,
                                                                   unique_count_pre if not c_pre else c_pre,
                                                                   unique_count_suf if not c_next else c_next)
    return show(new_l)


def _add_date(l: List[str]):
    new_l = copy.deepcopy(day_pre) + _add_pre_suf(l, day_fn, day_pre, day_suf)
    return show(new_l)


def _add_week(l: List[str]):
    new_l = copy.deepcopy(week_pre) + _add_pre_suf(l, week_fn, week_pre, week_suf)
    return show(new_l)


def _add_month(l: List[str]):
    new_l = copy.deepcopy(month_pre) + _add_pre_suf(l, month_fn, month_pre, month_suf)
    return show(new_l)


def _add_quarter(l: List[str]):
    new_l = copy.deepcopy(quarter_pre) + _add_pre_suf(l, quarter_fn, quarter_pre, quarter_suf)
    return show(new_l)


def _add_year(l: List[str]):
    new_l = copy.deepcopy(year_pre) + _add_pre_suf(l, year_fn, year_pre, year_suf)
    return show(new_l)


def add_aggregation(_column_name: str):
    """ 给支持聚合的字段添加相关描述 """

    with open(os.path.join(DESC_DIR, 'column_desc', f'{_column_name}.json'), 'rb') as f:
        column_descriptions = json.load(f)

    new_dir_path = os.path.join(DESC_DIR, 'aggregation_column_desc')
    if not os.path.exists(new_dir_path):
        os.mkdir(new_dir_path)

    for agg_method, fn in {'Sum': _add_sum, 'Avg': _add_avg, 'Min': _add_min, 'Max': _add_max}.items():
        desc = fn(column_descriptions)

        with open(os.path.join(new_dir_path, f'{_column_name}{agg_method}.json'), 'wb') as f:
            f.write(json.dumps(desc, ensure_ascii=False, indent=2).encode('utf-8'))


def add_count(_column_name: str):
    with open(os.path.join(DESC_DIR, 'column_desc', f'{_column_name}.json'), 'rb') as f:
        column_descriptions = json.load(f)

    new_dir_path = os.path.join(DESC_DIR, 'count_column_desc')
    if not os.path.exists(new_dir_path):
        os.mkdir(new_dir_path)

    for agg_method, fn in {'Count': _add_count, 'UniqueCount': _add_unique_count}.items():
        desc = fn(column_descriptions)

        with open(os.path.join(new_dir_path, f'{_column_name}{agg_method}.json'), 'wb') as f:
            f.write(json.dumps(desc, ensure_ascii=False, indent=2).encode('utf-8'))


def add_time(_column_name: str):
    with open(os.path.join(DESC_DIR, 'column_desc', f'{_column_name}.json'), 'rb') as f:
        column_descriptions = json.load(f)

    new_dir_path = os.path.join(DESC_DIR, 'time_column_desc')
    if not os.path.exists(new_dir_path):
        os.mkdir(new_dir_path)

    for agg_method, fn in {'ByDate': _add_date, 'ByWeek': _add_week, 'ByMonth': _add_month, 'ByQuarter': _add_quarter,
                           'ByYear': _add_year}.items():
        desc = fn(column_descriptions)

        with open(os.path.join(new_dir_path, f'{_column_name}{agg_method}.json'), 'wb') as f:
            f.write(json.dumps(desc, ensure_ascii=False, indent=2).encode('utf-8'))


if __name__ == '__main__':
    dir_path = os.path.join(DESC_DIR, 'column_desc')

    for dir_name in ['time_column_desc', 'count_column_desc', 'aggregation_column_desc']:
        tmp_dir_path = os.path.join(DESC_DIR, dir_name)
        if os.path.exists(tmp_dir_path):
            shutil.rmtree(tmp_dir_path)
            os.mkdir(tmp_dir_path)

    for file_name in os.listdir(dir_path):
        if file_name.startswith('.'):
            continue

        column_name = file_name.split('.')[0]
        if f'{column_name}Avg' in d_column_2_zh_name:
            add_aggregation(column_name)
        if f'{column_name}Count' in d_column_2_zh_name:
            add_count(column_name)
        if f'{column_name}ByYear' in d_column_2_zh_name:
            add_time(column_name)
