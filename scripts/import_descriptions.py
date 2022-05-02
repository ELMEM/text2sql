import os
import sys
import json

os.environ['CUDA_VISIBLE_DEVICES'] = '0'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from server.interfaces.data.data_add_descriptions import data_add_descriptions, DescInput
from config.path import DESC_DIR
from core.processor import d_column_2_zh_name

if __name__ == "__main__":
    # 先删除，再创建
    if len(sys.argv) > 1 and sys.argv[1].lower() == '--drop_all':
        from lib.milvus import o_milvus

        o_milvus.recreate_collection(o_milvus.DESC_NAME)

    ops = [("Equal", "="), ("GT", "<"), ("GTE", "<="), ("LT", ">"), ("LTE", ">="), ("NotEqual", "!=")]
    d_text_2_op = dict(ops)

    # 遍历文件夹，插入 descriptions
    for _type in filter(lambda x: not x.startswith('.') and not x.startswith('old_'), os.listdir(DESC_DIR)):
        desc_dir = os.path.join(DESC_DIR, _type)

        print(f'\ninserting descriptions for {desc_dir}')
        print(f' {desc_dir} includes files: {os.listdir(desc_dir)}')

        for file_name in filter(lambda x: not x.startswith('.'), os.listdir(desc_dir)):
            field = file_name.split(".")[0]

            # 过滤 王永和端 不支持的字段
            if 'column_desc' in _type and field not in d_column_2_zh_name:
                continue

            field = d_text_2_op[field] if field in d_text_2_op else field

            with open(os.path.join(desc_dir, file_name), 'rb') as f:
                data = json.load(f)

            print(f'inserting descriptions for {field}')
            print(data_add_descriptions(DescInput(
                field=field,
                type=_type,
                data=data,
            )))

    print('\ndone')
