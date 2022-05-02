import os
import sys
import time
import json
import requests
from functools import reduce

os.environ['CUDA_VISIBLE_DEVICES'] = '1'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from lib import logs

logs.MODULE = 'SyncData'
logs.PROCESS = 'sync_values'

from server.interfaces.data.data_add_values import data_add_values, DataInput
from lib.redis_utils import redis_save, redis_get, redis_del
from config.api import yonghe_domain
from lib.preprocess import preprocess
from lib.milvus import o_milvus, filter_duplicate_texts
from core.processor import fields_v2


def _get_data(column_name, timestamp, page=1, page_size=100) -> (list, list):
    logs.add('API', 'get_data', f'getting data from {column_name} after {timestamp} (page: {page}, size: {page_size})')

    """ 从王永和端取数据 """
    try:
        ret = requests.get(f'http://{yonghe_domain}/suggestion_data/{column_name}/{timestamp}?'
                           f'page={page}&page_size={page_size}')
        if ret.status_code != 200:
            logs.add('API', 'get_data', f'suggestion_data code status: {ret.status_code}', _level=logs.LEVEL_ERROR)
            return {'ret': 0, 'p_ids': [], 'values': []}

        data = json.loads(ret.content)
        p_ids = list(map(lambda x: x[0], data))
        values = list(map(lambda x: x[1], data))

        # 若 value 为数组，则不支持更新，只支持插入，所以 p_id 不考虑
        if values and isinstance(values[0], list):
            values = reduce(lambda a, b: a + b, values)

        logs.add('API', 'get_data', f'finish getting data (p_ids: {len(p_ids)}, values: {len(values)})')
        return {'ret': 1, 'p_ids': p_ids, 'values': values}
    except:
        logs.add('API', 'get_data', f'Error in suggestion_data parsing result', _level=logs.LEVEL_ERROR)
        return {'ret': 0, 'p_ids': [], 'values': []}


def _filter_empty_duplicate(column_name: str, d_value_2_p_ids: dict, p_ids: list, values: list) -> dict:
    for p_id, value in zip(p_ids, values):
        if isinstance(value, list):
            for v in value:
                if v is None or not f'{v}'.strip():
                    continue
                v = preprocess(v)
                if v not in d_value_2_p_ids:
                    d_value_2_p_ids[v] = []
                d_value_2_p_ids[v].append({'id': p_id, 'type': 'list'})

        elif value is None or not f'{value}'.strip():
            continue

        else:
            value = preprocess(value)
            if value not in d_value_2_p_ids:
                d_value_2_p_ids[value] = []
            d_value_2_p_ids[value].append({'id': p_id, 'type': 'elem'})

    # 删除重复值
    values = list(d_value_2_p_ids.keys())
    info = list(map(lambda x: {'text': x, 'column': column_name}, values))
    if values:
        values, _, _ = filter_duplicate_texts(o_milvus.VALUE_NAME, values, info, partition=column_name)

        del_values = list(filter(lambda x: x not in values, d_value_2_p_ids.keys()))
        for k in del_values:
            del d_value_2_p_ids[k]

    return d_value_2_p_ids


def _inject_data(column_name: str) -> bool:
    """ 注入 column 数据 (从王永和端同步数据) 到 milvus redis """
    timestamp = redis_get(column_name, '__timestamp')
    if not timestamp:
        timestamp = '2000-01-01 00:00:00'

    page = 1
    page_size = 1000
    d_value_2_p_ids = {}

    # 获取第1页数据
    ret_data = _get_data(column_name, timestamp, page, page_size)
    if not ret_data['ret']:
        return False

    p_ids, values = ret_data['p_ids'], ret_data['values']
    has_inserted = len(values) > 0
    ret_add = {'ret': 1}

    while p_ids:
        d_value_2_p_ids = _filter_empty_duplicate(column_name, d_value_2_p_ids, p_ids, values)
        if len(d_value_2_p_ids) >= page_size:
            # 目前先只插入，不删除
            insert_p_ids = []
            insert_values = list(d_value_2_p_ids.keys())

            # 插入数据
            ret_add = data_add_values(DataInput(column=column_name, data=insert_values, p_ids=insert_p_ids))
            if ret_add['ret'] != 1:
                d_value_2_p_ids = {}
                break

            d_value_2_p_ids = {}

            # 降低写入频率
            time.sleep(1)

        # 若不满1页数据，则表示取完
        if len(p_ids) < page_size:
            break

        # 否则，继续往下一页取
        page += 1
        ret_data = _get_data(column_name, timestamp, page, page_size)
        # 若出错
        if not ret_data['ret']:
            break

        p_ids, values = ret_data['p_ids'], ret_data['values']

    # 若 d_value_2_p_ids 存有待插入数据
    if d_value_2_p_ids:
        # 目前先只插入，不删除
        insert_p_ids = []
        insert_values = list(d_value_2_p_ids.keys())

        # 插入数据
        ret_add = data_add_values(DataInput(column=column_name, data=insert_values, p_ids=insert_p_ids))

    # 若插入数据成功，并且中间没有错误，则记录这次插入数据的时间戳；避免因为接口 500 而没有请求完数据
    if has_inserted and ret_data['ret'] and ret_add['ret']:
        now = str(time.strftime('%Y-%m-%d %H:%M:%S'))
        redis_save(column_name, now, '__timestamp')
        logs.add('Redis', '__timestamp', f'set column "{column_name}" timestamp to: {now}')

    return has_inserted


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--drop_all':
        for column in fields_v2:
            redis_save(column.name, '2000-01-01 00:00:00', '__timestamp')

    # 将 auto flush 关闭，加快插入数据速度
    o_milvus.AUTO_FLUSH = False

    while True:
        for column in fields_v2:
            if _inject_data(column.name):
                # 将数据写入磁盘
                o_milvus.flush([o_milvus.VALUE_NAME])

        time.sleep(30)
