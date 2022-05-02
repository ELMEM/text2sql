import os
import sys
import time
import inspect
from lib import utils
from config.path import LOG_DIR

LOG = []

MODULE = 'default'
PROCESS = 'default'

LEVEL_MSG = 'MSG'
LEVEL_NOTICE = 'NOTICE'
LEVEL_WARNING = 'WARNING'
LEVEL_ERROR = 'ERROR'

MAX_FILE_SIZE = 100 * 1024 * 1024
MAX_FILE_NO = 10

_incr_id = 100000000


def uid():
    global _incr_id
    _incr_id += 1
    return _incr_id


def fn_name():
    return inspect.stack()[1][3]


def add(_id, function, message, pre_sep='', empty_line=0, _level=LEVEL_MSG, show=True):
    # construct log message
    _time = str(time.strftime('%Y-%m-%d %H:%M:%S'))
    message = message if len(message) < 500 else message[:500] + '...'
    string = '\n' * empty_line + (
        pre_sep + '\n' if pre_sep else pre_sep) + f'{_id} : {_level} : {_time} : {function} : {message}\n'
    if show:
        print(string[:-1])
        sys.stdout.flush()

    # get correct file path
    dir_path = utils.get_relative_dir(MODULE, PROCESS, root=LOG_DIR)

    file_names = list(filter(lambda x: not x.startswith('.'), os.listdir(dir_path)))
    file_nos = list(map(lambda x: int(x.split('.')[0]), file_names))
    file_nos.sort(reverse=True)

    # 清楚过多的日志文件
    while len(file_nos) > MAX_FILE_NO:
        min_file_no = file_nos.pop()
        os.remove(os.path.join(dir_path, f'{min_file_no}.log'))

    file_no = file_nos[0] if file_nos else 1
    file_path = os.path.join(dir_path, f'{file_no}.log')

    while os.path.exists(file_path) and os.path.getsize(file_path) > MAX_FILE_SIZE:
        file_no += 1
        file_path = os.path.join(dir_path, f'{file_no}.log')

    # write log
    with open(file_path, 'ab') as f:
        f.write(string.encode('utf-8'))


def ret(_id, _fn_name, method, data):
    add(f'{_id}', f'{method} {_fn_name}', f'return {data}'[:200] + '...')
    if isinstance(data, dict):
        data['log_id'] = _id
    return data


if __name__ == "__main__":
    print(fn_name())
