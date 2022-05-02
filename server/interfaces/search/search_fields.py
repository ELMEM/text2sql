import os
import sys
import time
from typing import List, Union
from fastapi import Query
from sklearn.metrics.pairwise import cosine_similarity

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from server.interfaces.base import app
from server.definitions.suggestions import ResponseColumns
from core.encode import encode
from lib.preprocess import preprocess
from core.import_desc import d_field_2_synonyms
from core.processor import get_table_name, columns_v2, d_field_2_info, d_entity_2_tables
from lib import logs

# 获取 同义词 -> fields 的字典
d_synonym_2_fields = {}
d_synonym_2_tables = {}

for _field, _synonyms in d_field_2_synonyms.items():
    for _synonym in _synonyms:
        if _synonym not in d_synonym_2_fields:
            d_synonym_2_fields[_synonym] = []
        d_synonym_2_fields[_synonym].append(_field)

        if _synonym not in d_synonym_2_tables:
            d_synonym_2_tables[_synonym] = []
        d_synonym_2_tables[_synonym].append(d_field_2_info[_field].table)

        d_synonym_2_tables[_synonym] = list(set(d_synonym_2_tables[_synonym]))

# 获取所有的同义词列表
synonyms = list(d_synonym_2_fields.keys())

# 提前 encode 同义词
synonyms_vectors = encode(synonyms)


def check_texts_in_str(q_texts: List[str], string: str) -> bool:
    """ 检查 q_texts 是否有与 string 重合的地方 """
    for q in q_texts:
        if q in string:
            return True
    return False


def get_score_by_in_text(q: str, q_texts: List[str], _synonyms: List[str],
                         _limit_tables: Union[None, List[str]] = None) -> dict:
    """ 根据 q 是否在字段里有重合，进行搜索 """
    _tmp_synonyms = list(filter(lambda x: check_texts_in_str(q_texts, x), _synonyms))

    d_k_2_score = {}
    for s_k in _tmp_synonyms:
        _fields = d_synonym_2_fields[s_k]
        for k in _fields:
            # 过滤不在 entity 限制范围的结果
            if _limit_tables and d_field_2_info[k].table not in _limit_tables:
                continue

            if k not in d_k_2_score:
                d_k_2_score[k] = 0
            d_k_2_score[k] = max(d_k_2_score[k], 0.95 - (abs(len(s_k) - len(q)) / max(len(q), len(s_k), 1)) * 0.3)

    return d_k_2_score


def get_score_by_vector(q: str,
                        q_texts: List[str],
                        _synonyms: List[str],
                        _vectors: List[List[float]],
                        _limit_tables: Union[None, List[str]] = None) -> dict:
    """ 根据 q 的语义进行搜索 """
    q_embs = encode(q_texts)

    s_time = time.time()
    sims = cosine_similarity(q_embs, _vectors)
    print(f'cosine_similarity use time: {time.time() - s_time:.4f}s   ')

    d_k_2_score = {}

    s_time = time.time()

    for sim in sims:
        sim = list(zip(sim, _synonyms))
        for score, k in sim:
            if score < 0.7:
                continue

            _fields = d_synonym_2_fields[k]
            for _f in _fields:
                # 过滤不在 entity 限制范围的字段
                if _limit_tables and d_field_2_info[_f].table not in _limit_tables:
                    continue

                tmp_score = score

                if _f not in d_k_2_score:
                    d_k_2_score[_f] = 0.

                # 对 in text 进行加分
                if _f in d_field_2_info:
                    _column_val = d_field_2_info[_f]
                    _names = list(map(preprocess, [_column_val.name, _column_val.zh_name, _column_val.table]))
                    if q in _names:
                        d_k_2_score[_f] = 1.05
                    elif list(filter(lambda x: q in x, _names)):
                        tmp_score = min(tmp_score + 0.02, 1.05)

                d_k_2_score[_f] = max(d_k_2_score[_f], tmp_score)

    print(f'd_k_2_score use time: {time.time() - s_time:.4f}s   ')

    s_time = time.time()

    for k, score in get_score_by_in_text(q, q_texts, _synonyms, _limit_tables).items():
        d_k_2_score[k] = max(0.9 + 0.1 * d_k_2_score[k], d_k_2_score[k]) if k in d_k_2_score else score

    print(f'get_score_by_in_text use time: {time.time() - s_time:.4f}s   ')

    return d_k_2_score


@app.get('/v1/search/fields',
         name="v1 search fields",
         response_model=ResponseColumns,
         description="预想输入 (正在输入时)，返回相近的value或column的列表(top k)")
def search_fields(
        q: str = Query('', description='搜索的文本'),
        entities: str = Query('*', description='限制返回的实体；可选实体：【 Resume, Job, Flow, Tenant 】, 多个实体用 "," 连接成'),
        top_k: int = Query(15, description='搜索字段时，返回的 top_k 个结果')
):
    log_id = logs.uid()
    logs.add(log_id, f'GET {logs.fn_name()}', f'q: {q}')

    top_k = top_k.default if not isinstance(top_k, int) else top_k
    entities = entities.default if not isinstance(entities, str) else entities
    q = q.default if not isinstance(q, str) else q

    # 转换 entities 和 tables
    _limit_tables = []
    if entities and entities != '*':
        for entity in entities.split(','):
            if entity in d_entity_2_tables:
                _limit_tables += d_entity_2_tables[entity]
        _limit_tables = list(set(_limit_tables))

    # 若 q 为空，返回全部字段
    if not q:
        # 根据 table 过滤字段
        ret_columns = list(filter(lambda x: x.table in _limit_tables, columns_v2)) if _limit_tables else columns_v2
        return logs.ret(log_id, logs.fn_name(), 'GET', {
            'ret': 1,
            'data': ret_columns
        })

    q = preprocess(q)
    q_texts = [q]
    # q_texts = get_synonym([q])[0]

    if not _limit_tables:
        syn_texts = synonyms
        syn_vectors = synonyms_vectors
    else:
        syn_texts = []
        syn_vectors = []

        for i, _syn_text in enumerate(synonyms):
            tmp_tables = d_synonym_2_tables[_syn_text]
            if set(tmp_tables).intersection(_limit_tables):
                syn_texts.append(_syn_text)
                syn_vectors.append(synonyms_vectors[i])

    import time

    # 根据同义词以及语义相似度进行计数分数
    s_time = time.time()
    d_field_2_score = get_score_by_vector(q, q_texts, syn_texts, syn_vectors, _limit_tables)
    print(f'get_score_by_vector use time: {time.time() - s_time:.4f}s ')

    s_time = time.time()

    # 根据语义相似度进行排序
    l_field_score = list(d_field_2_score.items())
    l_field_score.sort(key=lambda x: (-x[1], x[0]))

    print(f'l_field_score.sort use time: {time.time() - s_time:.4f}s ')

    # 取 top_k 数据
    l_field_score = l_field_score[:top_k]

    # 过滤低分数据
    if l_field_score:
        max_score = l_field_score[0][1]
        l_field_score = list(filter(lambda x: x[1] >= max_score - 0.06, l_field_score))

    # print('\n----------------------------------')
    # for k, v in l_field_score:
    #     print(f'{k}: {v}')

    s_time = time.time()

    # 根据 层级 组织数据
    d_table_2_field_score = {}
    for field, score in l_field_score:
        table = get_table_name(field)
        if table not in d_table_2_field_score:
            d_table_2_field_score[table] = {'max_score': 0., 'table': table, 'fields': []}
        d_table_2_field_score[table]['max_score'] = max(d_table_2_field_score[table]['max_score'], score)
        d_table_2_field_score[table]['fields'].append([field, score])

    # 以第一层级的最大 score 进行排序
    l_table_field_score = list(d_table_2_field_score.values())
    l_table_field_score.sort(key=lambda x: (-x['max_score'], x['table']))

    results = []

    for v in l_table_field_score:
        # 根据 score 排序
        v['fields'].sort(key=lambda x: (-x[1], x[0]))

        # 组织返回的数据结构
        results.append(d_field_2_info[v['table']] if d_field_2_info.get(v['table']) else 'other')
        results += list(map(lambda x: d_field_2_info[x[0]] if d_field_2_info.get(x[0]) else x[0], v['fields']))

    print(f'组织数据 use time: {time.time() - s_time:.4f}s ')

    print(f'\nlen fields: {len(l_table_field_score)}')
    print(f'\nlen l_field_score: {len(l_field_score)}')
    print(f'\nlen synonyms: {len(syn_texts)}')

    return logs.ret(log_id, logs.fn_name(), 'GET', {
        'ret': 1,
        'data': results
    })


if __name__ == '__main__':
    print('\n------------------------------')
    for v in search_fields(q="")['data']:
        print(v)
