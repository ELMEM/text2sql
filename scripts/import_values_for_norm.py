import os
import re
import sys
import random

os.environ['CUDA_VISIBLE_DEVICES'] = '0'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from lib import logs

logs.MODULE = 'SyncData'
logs.PROCESS = 'import_values_for_norm'

from server.interfaces.data.data_add_values import data_add_values, DataInput
from core.processor import get_data_type, fields_v2, count_fns, is_normalizable

_reg_salary = re.compile(r'salary(?!=months)', re.IGNORECASE)
_reg_salary_months = re.compile(r'salary[ _\-]?months', re.IGNORECASE)
_reg_work_year = re.compile(r'(work|job)[ _\-]?years?', re.IGNORECASE)
_reg_date = re.compile(r'date', re.IGNORECASE)
_reg_degree = re.compile(r'Degree(?!=Requirement)', re.IGNORECASE)
_reg_subordinate = re.compile(r'subordinate', re.IGNORECASE)
_reg_age = re.compile(r'Age(?!=Requirement)', re.IGNORECASE)
_reg_headcount = re.compile(r'head[ _\-]?count', re.IGNORECASE)
_reg_count = re.compile(r'Count$')


def salary_values():
    l = ['百万', '一百万', '十万']
    for i in range(100):
        l.append(f'{int(random.random() * 100)}w')
        l.append(f'{int(random.random() * 100)}万')
        l.append(f'{random.random() * 10:.1f}w')
        l.append(f'{random.random() * 10:.1f}万')
        l.append(f'{int(random.random() * 100)}k')
        l.append(f'{int(random.random() * 100)}千')
        l.append(f'{i * 1000}')
        l.append(f'{int(random.random() * 100000)}')
    for i in list('一二三四五六七八九'):
        l += [f'{i}万', f'{i}十万', f'{i}千', f'{i}百万']
        for j in list('一二三四五六七八九'):
            l += [f'{i}十{j}万', f'{i}百{j}十万', f'{i}万{j}千']
    return l


def salary_month_values():
    l = []
    for i in list(range(13, 21)) + ['十', '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八']:
        for suffix in ['星', '个月', '月', '*', '薪', '']:
            l.append(f'{i}{suffix}')
    return l


def work_year_values():
    l = []
    for i in list(range(31)) + list('一二三四五六七八九'):
        for suffix in ['年', '年经验', '年工作经验', '年工龄', '']:
            l.append(f'{i}{suffix}')
            l.append(f'{random.random() * 20:.1f}{suffix}')
    return l


def date_values():
    l = []
    for i in range(500):
        year = random.randint(1950, 2030)
        month = random.randint(1, 12)
        date = random.randint(1, 31)
        l += [f'{year}', f'{year}年', f'{year}-{month}', f'{year}-0{str(month)[-1]}',
              f'{year}.{month}', f'{year}.0{str(month)[-1]}', f'{year}年{month}月', f'{year}年{month}月{date}日',
              f'{year}-{month}-{date}', f'{year}-0{str(month)[-1]}-{date}', f'{year}-{month}-0{str(date)[-1]}',
              f'{year}.{month}.{date}', f'{year}.0{str(month)[-1]}.{date}', f'{year}.{month}.0{str(date)[-1]}']

    for i in list(range(13)) + list('一二三四五六七八九'):
        for suffix in ['', '上', '最近', '前', '第', "近", "last ", "这"]:
            for template in ['{}天', '{}周', '{}个周', '{}星期', '{}个星期', '{}月', '{}个月', '{}年', '{}季', '{}季度',
                             '{}年半', '{}个半月', '{} week', '{} month', '{} year', '{} quarter', '{} day']:
                l.append(suffix + template.format(i))

    l += ['上周', '上季度', '上个季度', '上月', '上个月', '上上周', '上星期', '上上星期', '去年', '前年', '大前年', '今年', '后年',
          '后天', '昨天', '今天', '前天', '大前天', '这周', '这年', 'today', 'yesterday', 'tomorrow',
          'the day before yesterday', 'the day after tomorrow']
    return l


def education_degree():
    l = []
    prefix = ["高中", "中专", "大专", "本科", "研究生", "硕士", "博士",
              "high school", "bachelor", "master", "graduate", "doctor", "post doctor",
              "post doc", "phD", "ph.D.", "M.S.", "M.A.", "B.A.", "B.S.", "M.B.A.", "Ed.A"]
    for pre in prefix:
        for suffix in ["学历", "毕业", "学位", "毕业生", "在读", "在读生", "候选人", " degree", ""]:
            l.append(f"{pre}{suffix}")
    return l


def subordinate_number():
    l = []
    for i in range(1, 101):
        for suffix in ["", "个", "个人", "人", "个下属", "个部下", "个属下"]:
            l.append(f"{i}{suffix}")
    return l


def age_requirement():
    l = []
    for suffix in ['岁', '以上', '以下', '']:
        for i in range(16, 66):
            l.append(f"{i}{suffix}")
    return l


def head_count():
    l = []
    prefix = ["招聘", "招岗数", "招收", "招收岗位", ""]
    for pre in prefix:
        for i in range(1, 101):
            for suffix in ["人", "个", "位", "", "个人", "个职位", "个岗位", "人头"]:
                l.append(f"{pre}{i}{suffix}")
    return l


def count_values():
    l = []
    for i in list(range(1000)) + list('零一二三四五六七八九十'):
        for suffix in ["", "个", "份"]:
            l.append(f"{i}{suffix}")
    return l


def int_values():
    return [int(random.random() * 100) for i in range(100)]


def float_values():
    return [round(random.random() * 100, 2) for i in range(100)]


if __name__ == "__main__":
    import sys
    from lib.milvus import o_milvus

    # 将 auto flush 关闭，加快插入数据速度
    o_milvus.AUTO_FLUSH = False

    if len(sys.argv) > 1 and sys.argv[1].lower() == '--drop_all':
        o_milvus.recreate_collection(o_milvus.VALUE_NAME)
        o_milvus.recreate_collection(o_milvus.AVG_VALUE_NAME)

    for column_obj in fields_v2:
        column = column_obj.name
        _type = get_data_type(column)
        if not is_normalizable(column):
            continue

        texts = []
        if _type.lower().startswith('date') or _reg_date.search(column):
            texts = date_values()
        elif _reg_salary_months.search(column):
            texts = salary_month_values()
        elif _reg_salary.search(column):
            texts = salary_values()
        elif _reg_work_year.search(column):
            texts = work_year_values()
        elif _reg_degree.search(column):
            texts = education_degree()
        elif _reg_subordinate.search(column):
            texts = subordinate_number()
        elif _reg_age.search(column):
            texts = age_requirement()
        elif _reg_headcount.search(column):
            texts = head_count()

        if texts:
            data_add_values(DataInput(column=column, data=texts))

        if _type.lower().startswith('int'):
            data_add_values(DataInput(column=column, data=int_values()))
        elif _type.lower().startswith('float'):
            data_add_values(DataInput(column=column, data=float_values()))

    for count_fn in count_fns:
        data_add_values(DataInput(column=f'____{count_fn}', data=count_values()))

    # 将数据写入磁盘
    o_milvus.flush([o_milvus.VALUE_NAME])

    print('\ndone')
