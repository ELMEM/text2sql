import os
import sys
import json
from typing import List
from functools import reduce

os.environ['CUDA_VISIBLE_DEVICES'] = '3'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from lib import logs

logs.MODULE = 'SyncData'
logs.PROCESS = 'import_descriptions'

from server.definitions.suggestions import Column
from core.processor import fields_v2, to_zh, get_synonym, agg_fns, gb_fns, tables_v2
from lib.preprocess import preprocess, format_suffix
from config.path import DESC_DIR

# 获取 table 的同义词列表
table_synonyms = list(map(lambda x: get_synonym([x.name, x.zh_name], recur_syn=True), tables_v2))
table_synonyms = list(map(lambda l: reduce(lambda a, b: a + b, l, []), table_synonyms))
table_synonyms = reduce(lambda a, b: a + b, table_synonyms, [])

# 获取 aggregation 和 group by 函数的同义词
d_agg_fn_2_synonyms = {agg_fn: get_synonym([agg_fn], recur_syn=True)[0] for agg_fn in agg_fns}
d_gb_fn_2_synonyms = {gb_fn: get_synonym([gb_fn], recur_syn=True)[0] for gb_fn in gb_fns}


def not_noise(synonym_text: str) -> bool:
    """ 检查该同义词是否 noise """
    occur_table_count = 0

    for _text in synonym_text.split(' '):
        if _text in table_synonyms:
            occur_table_count += 1

    return occur_table_count <= 1


def synonyms(column: Column) -> List[str]:
    """ 获取某个字段的同义词 """
    texts: List[str] = [column.name, column.zh_name, column.actual_column, column.table, to_zh(column.table)]
    texts = list(map(preprocess, texts))

    texts_list: List[List[str]] = get_synonym(texts, recur_syn=True)
    texts: List[str] = reduce(lambda a, b: a + b, texts_list, [])
    texts: List[str] = list(map(preprocess, texts))
    texts: List[str] = list(set(texts))
    texts: List[str] = list(filter(not_noise, texts))
    return texts


logs.add('Initialization', 'column_desc', 'Getting synonyms for column_desc ...')
d_field_2_synonyms = {c.name: synonyms(c) for c in fields_v2}
logs.add('Initialization', 'column_desc', 'Finish getting synonyms all types of column_desc')


def drop_desc_collection():
    """ 删除已有的 描述 collection 里的数据 """
    from lib.milvus import o_milvus
    o_milvus.recreate_collection(o_milvus.DESC_NAME)


def import_descriptions():
    """ 执行动态导入描述 """
    from lib.milvus import o_milvus
    from server.interfaces.data.data_add_descriptions import data_add_descriptions, DescInput

    # 将 auto flush 关闭，加快插入数据速度
    o_milvus.AUTO_FLUSH = False

    # 动态导入 column description
    logs.add('Import', 'Progress', 'start import column descriptions ... ', pre_sep='---------------------------------')
    for field, texts in d_field_2_synonyms.items():
        data_add_descriptions(DescInput(field=field, type='column_desc', data=texts))

    logs.add('Import', 'Progress', 'start import agg fn descriptions ... ', pre_sep='---------------------------------')
    for agg_fn, texts in d_agg_fn_2_synonyms.items():
        data_add_descriptions(DescInput(field=format_suffix(agg_fn), type='agg_fn', data=texts))

    logs.add('Import', 'Progress', 'start import gb fn descriptions ... ', pre_sep='---------------------------------')
    for gb_fn, texts in d_gb_fn_2_synonyms.items():
        data_add_descriptions(DescInput(field=format_suffix(gb_fn), type='group_fn', data=texts))

    logs.add('Import', 'Progress', 'start import other descriptions ... ', pre_sep='---------------------------------')

    d_text_2_op = {'Equal': '=', 'GT': '<', 'GTE': '<=', 'LT': '>', 'LTE': '>=', 'NotEqual': '!='}

    # 遍历文件夹，插入 comparison_op, condition_op, keyword descriptions
    for _type in filter(lambda x: not x.startswith('.') and not x.startswith('old_'), os.listdir(DESC_DIR)):
        desc_dir = os.path.join(DESC_DIR, _type)
        logs.add('Import', 'Progress', f'inserting descriptions for "{_type}" (files len: {len(os.listdir(desc_dir))})')

        for file_name in filter(lambda x: not x.startswith('.'), os.listdir(desc_dir)):
            # 获取 field
            field = file_name.split(".")[0]
            field = d_text_2_op[field] if field in d_text_2_op else field

            # 读取文件
            with open(os.path.join(desc_dir, file_name), 'rb') as f:
                texts = json.load(f)

            data_add_descriptions(DescInput(
                field=field,
                type=_type,
                data=texts,
            ))

    # 将数据写入磁盘
    o_milvus.flush([o_milvus.DESC_NAME])
    logs.add('Import', 'Progress', 'Successfully inserting all description and flush, done',
             pre_sep='----------------------------------')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].lower() == '--drop_all':
        drop_desc_collection()
    import_descriptions()
