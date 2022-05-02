import os
import sys
import time

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from typing import List, Optional
from pydantic import BaseModel, Field
from lib import logs
from server.interfaces.base import app
from server.interfaces.data.data_search_avg_values_by_texts import Response


class QueryAvgValueInput(BaseModel):
    q_vectors: List[List[float]] = Field(description='搜索的向量; 批量')
    top_k: Optional[int] = Field(10, description='返回的结果数量限制')


@app.post('/v1/data/search/avg_values/by_vectors_with_milvus',
          name="v1 data search avg values by vectors with milvus",
          response_model=Response,
          description="搜索 value 数据; 批量搜索")
def data_search_avg_values_by_vectors_with_milvus(_input: QueryAvgValueInput):
    from lib.milvus import o_milvus

    q_vectors = _input.q_vectors
    top_k = _input.top_k

    # 检查参数
    if not q_vectors:
        return {'ret': 0, 'msg': 'q_vectors 不能为空'}

    start_ = time.time()
    data = o_milvus.search(o_milvus.AVG_VALUE_NAME, q_vectors, top_k)
    end_ = time.time()
    logs.add('unknown', f'milvus_search', f'search avg values by vector : {end_ - start_:.4f}s ')
    return {'ret': 1, 'data': data}


if __name__ == '__main__':
    # 测试代码
    from core.encode import encode

    q_texts = ['本科学历'] if len(sys.argv) <= 1 else sys.argv[1:]
    ret = data_search_avg_values_by_vectors_with_milvus(QueryAvgValueInput(
        q_vectors=encode(q_texts),
    ))
    print(ret)

