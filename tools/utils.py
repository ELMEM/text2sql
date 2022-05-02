import os
import re
import io
import sys
import hashlib
import traceback
from functools import reduce
from importlib import import_module

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
_tmp_dir = os.path.join(_root_dir, 'tmp')

reg_list = re.compile('\.list_\d+(?=\.|$)', re.IGNORECASE)
reg_list_end = re.compile('\.list_\d+$', re.IGNORECASE)
reg_list_no = re.compile(r'\.list_(\d+)', re.IGNORECASE)
reg_only_list = re.compile(r'\.list(?=\.|$)')
reg_remove_list = re.compile(r'\.list(_\d+)?(?=\.|$)', re.IGNORECASE)
reg_zh = re.compile(r'[\u3400-\u9FFF]')


def get_trace_back():
    fp = io.StringIO()  # 创建内存文件对象
    traceback.print_exc(file=fp)
    return fp.getvalue()


def md5(_string):
    if not isinstance(_string, bytes):
        _string = _string.encode('utf-8')
    m = hashlib.md5()
    m.update(_string)
    return m.hexdigest()


def expand_json(_json):
    expanded_json = {}
    stack = [('', _json)]

    while stack:
        parent, tmp_json = stack.pop(0)

        if isinstance(tmp_json, dict):
            for k, v in tmp_json.items():
                k = k.replace('.', '#@#')
                stack.append((f'{parent}.{k}' if parent else k, v))

        elif isinstance(tmp_json, list) or isinstance(tmp_json, tuple):
            for i, v in enumerate(tmp_json):
                stack.append((f'{parent}.list_{i}' if parent else f'list_{i}', v))

        else:
            expanded_json[parent] = tmp_json

    return expanded_json


def reconstruct_nested_json(expanded_json):
    del_keys = []
    keys = list(expanded_json.keys())
    for k in keys:
        if list(filter(lambda x: f'{k}.' in x, keys)):
            del_keys.append(k)

    for k in del_keys:
        del expanded_json[k]

    expanded_json_items = list(expanded_json.items())
    expanded_json_items.sort()

    _ret = {}
    for k, v in expanded_json_items:
        if '.' not in k:
            k = k.replace('#@#', '.')
            _ret[k] = v
        else:
            keys = k.split('.')

            last = tmp_json = _ret
            last_idx = ''

            for i, tmp_k in enumerate(keys[:-1]):
                if tmp_k == 'list':
                    tmp_k = 'list_0'
                tmp_k = tmp_k.replace('#@#', '.')

                if 'list_' in tmp_k:
                    if not isinstance(tmp_json, list):
                        last[last_idx] = []
                        tmp_json = last[last_idx]

                    last_idx = int(tmp_k.split('_')[1])
                    while len(tmp_json) <= last_idx:
                        tmp_json.append({})

                    last = tmp_json
                    tmp_json = tmp_json[last_idx]

                else:
                    if tmp_k not in tmp_json:
                        tmp_json[tmp_k] = {}
                    if isinstance(tmp_json[tmp_k], str):
                        tmp_json[tmp_k] = {}

                    last = tmp_json
                    last_idx = tmp_k
                    tmp_json = tmp_json[tmp_k]

            final_k = keys[-1]
            if final_k == 'list':
                final_k = 'list_0'
            final_k = final_k.replace('#@#', '.')

            if 'list_' in final_k:
                if not isinstance(tmp_json, list):
                    last[last_idx] = []
                    tmp_json = last[last_idx]

                last_idx = int(final_k.split('_')[1])
                while len(tmp_json) <= last_idx:
                    tmp_json.append('')
                tmp_json[last_idx] = v

            else:
                tmp_json[final_k] = v

    return _ret


def convert_field(expanded_map_schema: dict, nested_json, keep=True):
    """ 转换字段 (映射字段) """
    expanded_json = expand_json(nested_json)

    new_expanded_json = {}
    for k, v in expanded_json.items():
        tmp_k = reg_list.sub('.list', k)

        if tmp_k in expanded_map_schema:
            new_tar_keys = expanded_map_schema[tmp_k]
            if not new_tar_keys:
                if keep:
                    k = f'__extend.{k}'
                    new_expanded_json[k] = v

            else:
                for new_k in new_tar_keys:
                    if new_k in ['will_be_removed', 'unknown', 'delete']:
                        if keep:
                            k = f'__extend.{k}'
                            new_expanded_json[k] = v
                        continue

                    list_nos = reg_list_no.findall(k)
                    num_list = len(reg_remove_list.findall(new_k))

                    while len(list_nos) < num_list:
                        list_nos.append(0)

                    for i, no in enumerate(list_nos):
                        new_k = reg_only_list.subn(f'.list_{no}', new_k, count=1)[0]

                    new_expanded_json[new_k] = v

        elif keep:
            k = f'__extend.{k}'
            new_expanded_json[k] = v

    return new_expanded_json


def convert_value(expanded_json, convert_value_schema: list):
    """ 对转换后的数据的值进行类型转换，或添加模版等 """
    invalid_fns = []

    if not convert_value_schema:
        return expanded_json, invalid_fns

    for val in convert_value_schema:
        key = val['key']
        convert_fn = val['fn']

        if key == '*':
            key_value_pairs = list(expanded_json.items())
        else:
            key_value_pairs = list(filter(lambda x: key in reg_list.sub('.list', x[0]), expanded_json.items()))

        if not key_value_pairs:
            continue

        try:
            del_keys, new_key_value_pairs = convert_fn(key_value_pairs)

            for k in del_keys:
                if k in expanded_json:
                    del expanded_json[k]

            for k, v in new_key_value_pairs:
                expanded_json[k] = v
        except Exception as e:
            invalid_fns.append({'key': key, 'error': f'{e}', 'traceback': get_trace_back()})

    expanded_json_items = list(expanded_json.items())
    expanded_json_items.sort()
    return {k: v for k, v in expanded_json_items}, invalid_fns


def convert_one(nested_json, _expanded_map_schema: dict, _convert_value_schema: list, keep=False):
    new_expanded_data = convert_field(_expanded_map_schema, nested_json, keep)
    return convert_value(new_expanded_data, _convert_value_schema)


def convert_batch(list_nested_json: list, _expanded_map_schema: dict, _convert_value_schema: list, keep=False):
    data = list(map(lambda x: convert_one(x, _expanded_map_schema, _convert_value_schema, keep), list_nested_json))
    list_tar_json, list_invalid_fns = list(zip(*data))
    invalid_fns = reduce(lambda a, b: a + b, list_invalid_fns, [])
    return list_tar_json, invalid_fns


def revert_map_schema(expanded_map_schema: dict):
    expanded_map_schema_reverted = {}
    for k, v in expanded_map_schema.items():
        if not v:
            continue

        if v not in expanded_map_schema_reverted:
            expanded_map_schema_reverted[v] = []
        expanded_map_schema_reverted[v].append(k)

    expanded_map_schema_reverted = list(expanded_map_schema_reverted.items())
    expanded_map_schema_reverted.sort()
    return dict(expanded_map_schema_reverted)


def import_fn_from_str(_convert_value_schema):
    sys.path.append(_root_dir)
    new_convert_value_schema = []
    invalid_fns = []

    for i, val in enumerate(_convert_value_schema):
        key = val['key']
        fn = val['fn']

        if not isinstance(fn, str):
            new_convert_value_schema.append({'key': key, 'fn': fn})
            continue

        if 'md5' not in val:
            md5 = md5(fn)
            val['md5'] = md5
            _convert_value_schema[i] = val
        else:
            md5 = val['md5']

        tmp_file_path = os.path.join(_tmp_dir, f'{md5}.py')
        with open(tmp_file_path, 'wb') as f:
            f.write(fn.encode('utf-8'))

        try:
            tmp_module = import_module(f'tmp.{md5}')
            new_convert_value_schema.append({
                'key': key,
                'fn': lambda key_value_pairs: (
                    [],
                    list(map(lambda p: (p[0], tmp_module.convert(p[1])), key_value_pairs))
                ),
            })
        except Exception as e:
            invalid_fns.append({'key': key, 'error': f'{e}', 'traceback': get_trace_back()})

    sys.path.pop(-1)
    return new_convert_value_schema, invalid_fns


def clear_tmp_module(_convert_value_schema):
    for i, val in enumerate(_convert_value_schema):
        file_path = os.path.join(_tmp_dir, f'{val["md5"]}.py')
        if os.path.exists(file_path):
            os.remove(file_path)


def clear_parent_node(d_field_2_value: dict):
    keys = list(d_field_2_value.keys())
    del_keys = []
    for _k in keys:
        if list(filter(lambda x: f'{_k}.' in x, keys)):
            del_keys.append(_k)
    for _k in del_keys:
        del d_field_2_value[_k]
