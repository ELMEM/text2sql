import os
import sys
import copy
import json
import redis
import threading
from typing import Union, List

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from config.redis import redis_conf

_o_redis = redis.Redis(**redis_conf)


def redis_save(k: Union[str, int], v, table_name: str = ''):
    if isinstance(v, dict) or isinstance(v, list) or isinstance(v, tuple):
        v = json.dumps(v)
    _o_redis.set(f'{table_name}____{k}', v)


def redis_get(k: Union[str, int], table_name: str = '') -> Union[dict, list, str, int, float]:
    v = _o_redis.get(f'{table_name}____{k}')
    if not v or isinstance(v, int) or isinstance(v, float):
        return v

    try:
        if isinstance(v, bytes):
            v = v.decode('utf-8')
        v = json.loads(v)
    except:
        pass
    return v


def _redis_get_in_bg(keys: List[Union[str, int]], table_name, d_result: dict):
    while keys:
        k = keys.pop()
        d_result[k] = redis_get(k, table_name)


def redis_batch_get(keys: List[Union[str, int]], table_name: str = '', num_thread=10) -> List[Union[dict, list, str, int, float]]:
    d_result = {}

    pool = []
    share_keys = copy.deepcopy(keys)
    for i in range(min(num_thread, len(share_keys))):
        t = threading.Thread(target=_redis_get_in_bg, args=(share_keys, table_name, d_result))
        t.start()
        pool.append(t)

    for t in pool:
        t.join()

    return list(map(lambda x: d_result[x], keys))


def redis_keys(prefix) -> List[str]:
    return list(map(lambda x: x.decode('utf-8'), _o_redis.keys(prefix)))


def redis_drop(db_name):
    keys = _o_redis.keys(f'{db_name}____*')
    if keys:
        _o_redis.delete(*keys)


def redis_del(*keys, table_name=''):
    keys = list(map(lambda k: f'{table_name}____{k}', keys))
    if keys:
        _o_redis.delete(*keys)
