import os
import re
import time
import random
import hashlib
from datetime import datetime

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
root_dir = os.path.split(_cur_dir)[0]


def uid():
    _id = f'{int(time.time() * 1000)}{int(random.random() * 1000000)}'
    return int(_id)


def md5(_obj):
    text = f'{_obj}'.encode('utf-8')
    m = hashlib.md5()
    m.update(text)
    return m.hexdigest()


def convert_reg(text: str):
    new_text = ''
    for c in text:
        if c in ['(', ')', '[', ']', '{', '}', '.', '?', '+', '*']:
            new_text += '\\'
        new_text += c
    return new_text


def get_relative_dir(*args, root=''):
    """ return the relative path based on the root_dir; if not exists, the dir would be created """
    dir_path = root_dir if not root else root
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)

    for i, arg in enumerate(args):
        dir_path = os.path.join(dir_path, arg)
        if not os.path.exists(dir_path) and '.' not in arg:
            os.mkdir(dir_path)
    return dir_path


reg_datetime = re.compile(
    r'([12]\d{3})([\\/.\-_: ])([01]\d|[1-9])\2([0-3]\d|[1-9])(\s*[^\d]{1,3}\s*([0-2]?\d)([:./\\])([0-6]?\d)\7([0-6]?\d)([:./\\](\d{1,3}))?)?')


def date2timestamp(date_string):
    if not isinstance(date_string, str) or not reg_datetime.search(date_string):
        from normalize.time_normalize import normalize
        date_obj = normalize(date_string)
        date_string = date_obj['gte'] if 'gte' in date_obj else date_string

    if isinstance(date_string, str) and reg_datetime.search(date_string):
        Y, _, m, d, _, H, _, M, S, _, MS = reg_datetime.findall(date_string)[0]
        args = list(map(lambda x: int(x) if x else 0, [Y, m, d, H, M, S, MS]))
        dt = datetime(*args)
        return int(dt.timestamp())
    return date_string
