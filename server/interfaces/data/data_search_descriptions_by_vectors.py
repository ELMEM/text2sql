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
from server.interfaces.data.data_search_descriptions_by_texts import Response


class QueryDescInput(BaseModel):
    q_vectors: List[List[float]] = Field(description='搜索的文本; 批量')
    desc_type: Optional[str] = Field(description='指定 描述类型 下搜索; 若不传，则在全部 描述类型 搜索; '
                                                 'type in [ column_desc, aggregation_column_desc, time_column_desc, '
                                                 'comparison_op_desc, condition_op_desc, group_by_trigger_desc ]')
    top_k: Optional[int] = Field(10, description='返回的结果数量限制')


@app.post('/v1/data/search/descriptions/by_vectors',
          name="v1 data search descriptions by vectors",
          response_model=Response,
          description="搜索 描述 数据; 批量搜索")
def data_search_descriptions_by_vectors(_input: QueryDescInput):
    from lib.milvus import o_milvus

    q_vectors = _input.q_vectors
    desc_type = _input.desc_type
    top_k = _input.top_k

    # 检查参数
    if not q_vectors:
        return {'ret': 0, 'msg': 'q_vectors 不能为空'}

    if desc_type and desc_type not in ['column_desc', 'aggregation_column_desc', 'comparison_op_desc',
                                       'condition_op_desc', 'group_by_trigger_desc', 'time_column_desc']:
        return {'ret': 0, 'msg': 'type 只支持 [ column_desc, aggregation_column_desc, comparison_op_desc, '
                                 'condition_op_desc, group_by_trigger_desc, time_column_desc ]'}

    partitions = [desc_type] if desc_type else None
    start_ = time.time()
    data = o_milvus.search(o_milvus.DESC_NAME, q_vectors, top_k, partitions)
    end_ = time.time()
    logs.add('unknown', f'milvus_search', f'search descriptions by vector: {end_ - start_:.4f}s ')
    return {'ret': 1, 'data': data}


if __name__ == '__main__':
    # 测试代码
    from core.encode import encode

    q_texts = ['薪资'] if len(sys.argv) <= 1 else sys.argv[1:]
    ret = data_search_descriptions_by_vectors(QueryDescInput(
        q_vectors=encode(q_texts),
        top_k=5,
    ))
    print(ret['data'])
