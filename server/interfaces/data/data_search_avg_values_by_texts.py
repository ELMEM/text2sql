import os
import sys
import time
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from typing import List, Optional
from pydantic import BaseModel, Field
from lib.preprocess import preprocess
from core.encode import encode
from server.interfaces.base import app
from lib import logs
from lib.redis_utils import redis_keys, redis_batch_get


class QueryAvgValueInput(BaseModel):
    q_texts: List[str] = Field(description='搜索的文本; 批量')
    top_k: Optional[int] = Field(10, description='返回的结果数量限制')


class RetData(BaseModel):
    column: str = Field(description='sql 中的 column name')
    freq: Optional[int] = Field(1, description='频率')


class Ret(BaseModel):
    data: RetData = Field(description='查询结果的相关信息')
    similarity: float = Field(description='查询结果的相似度')


class Response(BaseModel):
    ret: int = Field(1, description='状态码；是否成功；0 表示 失败，1 表示 成功')
    msg: Optional[str] = Field('', description='错误信息；若 ret = 1，则为空')
    data: Optional[List[List[Ret]]] = Field([], description='搜索到到value数据')


@app.post('/v1/data/search/avg_values/by_texts',
          name="v1 data search avg values by texts",
          response_model=Response,
          description="搜索 value 数据; 批量搜索")
def data_search_avg_values_by_texts(_input: QueryAvgValueInput):
    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}'[:200])

    q_texts = _input.q_texts
    top_k = _input.top_k

    # 检查参数
    if not q_texts:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': 'q_texts 不能为空'})

    s_time = time.time()

    # 预处理文本
    q_texts = list(map(preprocess, q_texts))

    # encode 到 vector
    q_vectors = encode(q_texts)

    table = 'moving_avg_embedding'
    keys = redis_keys(f'{table}*')

    columns = list(map(lambda x: x.split('____')[-1], keys))
    ret_avg = redis_batch_get(columns, table)

    avg_embeddings = np.array(list(map(lambda x: x['emb'], ret_avg)))
    similarities = cosine_similarity(q_vectors, avg_embeddings)

    results = []
    for scores in similarities:
        score_columns = list(zip(scores, columns))
        score_columns.sort(key=lambda x: (-x[0], x[1]))

        score_columns = list(map(lambda x: {'data': {'column': x[1]}, 'similarity': x[0]}, score_columns[:top_k]))
        results.append(score_columns)

    e_time = time.time()
    logs.add(log_id, 'milvus_search', f'search avg values by text: {e_time - s_time:.4f}s ')
    return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 1, 'data': results})


if __name__ == '__main__':
    # 测试代码
    q_texts = ['本科学历'] if len(sys.argv) <= 1 else sys.argv[1:]
    ret = data_search_avg_values_by_texts(QueryAvgValueInput(
        q_texts=q_texts,
    ))
    print(ret)
