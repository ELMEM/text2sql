import os
import sys
import threading
from queue import Queue
from functools import reduce
from datetime import datetime

os.environ['CUDA_VISIBLE_DEVICES'] = '1'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from lib import logs
from core.encode import encode
from core.processor import fields_v2
from lib.clickhouse import exec_sql, get_distinct_count


def _get_queries(thread_num=15, _limit=5000):
    logs.add('MainProcess', 'progress', 'start getting all count queries')

    _queue = Queue()
    for column in fields_v2:
        _queue.put(column)

    d_column_2_count = {}

    logs.add('MainProcess', 'progress', 'finish getting all count queries')
    logs.add('MainProcess', 'progress', 'start multi threads for getting count')

    pool = []
    for thread_id in range(thread_num):
        thread = threading.Thread(target=_get_count, args=(thread_id, _queue, d_column_2_count))
        thread.start()
        pool.append(thread)

    for thread in pool:
        thread.join()

    logs.add('MainProcess', 'progress', 'finish multi threads for getting count', pre_sep='---------------------------')

    _queries = []

    for _column in fields_v2:
        count = d_column_2_count[_column.name]
        if count == -1:
            continue

        if count < 10000:
            sql = f'select distinct {_column.actual_column} from v_{_column.table}'
            _queries.append({'column': _column, 'sql': sql})

        else:
            for i in range(0, count, _limit):
                sql = f'select distinct {_column.actual_column} from v_{_column.table} order by {_column.actual_column} ' \
                      f'limit {_limit} offset {i}'
                _queries.append({'column': _column, 'sql': sql})

    return _queries


def _get_data_by_sql(sql: str):
    data = exec_sql(sql)
    data = list(map(lambda x: x[0], data))

    if data and isinstance(data[0], list):
        data = reduce(lambda a, b: a + b, data, [])
    elif data and isinstance(data[0], datetime):
        years = list(set(list(map(lambda x: f'{x.year}', data))))
        year_months = list(set(list(map(lambda x: f'{x.year}-{x.month}', data))))
        year_month_days = list(set(list(map(lambda x: f'{x.year}-{x.month}-{x.day}', data))))
        data = years + year_months + year_month_days

    data = list(map(lambda x: f'{x}', data))
    return data


def _get_count(thread_id: int, queue: Queue, d_column_2_count: dict):
    logs.add(f'Thread_{thread_id}', '_get_count', 'start ...')

    while not queue.empty():
        column = queue.get()
        d_column_2_count[column.name] = get_distinct_count(column.actual_column, column.table)
        logs.add(f'Thread_{thread_id}', '_get_count', f'(qsize: {queue.qsize()}) getting count for "{column.name}"')

    logs.add(f'Thread_{thread_id}', '_get_count', 'end')


def _get_data(thread_id: int, queue: Queue):
    logs.add(f'Thread_{thread_id}', '_get_data', 'start ...')

    while not queue.empty():
        query = queue.get()
        column = query['column']
        sql = query['sql']

        logs.add(f'Thread_{thread_id}', '_get_data', f'(qsize: {queue.qsize()}) '
                                                     f'getting data for "{column.name}" (sql: {sql})')

        data = _get_data_by_sql(sql)
        vectors = encode(data)

    logs.add(f'Thread_{thread_id}', '_get_data', 'end')


def run(thread_num=15):
    logs.add('MainProcess', 'progress', 'Start getting all queries ... ')

    # 获取所有 queries
    queries = _get_queries()

    _queue = Queue()
    for q in queries:
        _queue.put(q)

    logs.add('MainProcess', 'progress', f'Finish getting all queries (len: {_queue.qsize()})',
             pre_sep='--------------------------------')

    pool = []

    for thread_id in range(thread_num):
        thread = threading.Thread(target=_get_data, args=(thread_id, _queue))
        thread.start()
        pool.append(thread)

    for thread in pool:
        thread.join()

    logs.add('MainProcess', 'progress', 'Done', pre_sep='------------------------------')


if __name__ == '__main__':
    # run()
    import faiss

    # dim = 384
    # index = faiss.IndexIVF(dim)
    # print(index.is_trained)
