import os
import sys
import time

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Optional
from pydantic import BaseModel, Field
from lib.redis_utils import redis_batch_get, redis_keys
from lib import logs
from server.interfaces.base import app
from server.interfaces.data.data_search_avg_values_by_texts import Response


class QueryAvgValueInput(BaseModel):
    q_vectors: List[List[float]] = Field(description='搜索的向量; 批量')
    top_k: Optional[int] = Field(10, description='返回的结果数量限制')


@app.post('/v1/data/search/avg_values/by_vectors',
          name="v1 data search avg values by vectors",
          response_model=Response,
          description="搜索 value 数据; 批量搜索")
def data_search_avg_values_by_vectors(_input: QueryAvgValueInput):
    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}'[:200])

    q_vectors = _input.q_vectors
    top_k = _input.top_k

    # 检查参数
    if not q_vectors:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': 'q_vectors 不能为空'})

    s_time = time.time()

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
    logs.add(log_id, 'milvus_search', f'search avg values by vector: {e_time - s_time:.4f}s ')
    return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 1, 'data': results})


if __name__ == '__main__':
    # 测试代码
    from core.encode import encode

    q_texts = ['本科学历'] if len(sys.argv) <= 1 else sys.argv[1:]
    ret = data_search_avg_values_by_vectors(QueryAvgValueInput(
        q_vectors=encode(q_texts),
    ))
    print(ret)
