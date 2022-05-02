import os
import sys
import time

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(os.path.split(os.path.split(_cur_dir)[0])[0])[0]
sys.path.append(_root_dir)

from typing import List, Optional
from pydantic import BaseModel, Field
from lib.preprocess import preprocess
from core.encode import encode
from lib import logs
from server.interfaces.base import app


class QueryDescInput(BaseModel):
    q_texts: List[str] = Field(description='搜索的文本; 批量')
    desc_type: Optional[str] = Field(description='指定 描述类型 下搜索; 若不传，则在全部 描述类型 搜索; '
                                                 'type in [ column_desc, aggregation_column_desc, time_column_desc,'
                                                 'comparison_op_desc, condition_op_desc, group_by_trigger_desc ]')
    top_k: Optional[int] = Field(10, description='返回的结果数量限制')


class RetData(BaseModel):
    text: str = Field(description='描述文本')
    field: str = Field(description='column name 或 comparison op 或 condition op 或 "group_by_trigger"')
    type: str = Field(description='描述数据的类型; type in [ column_desc, aggregation_column_desc, time_column_desc,'
                                  'comparison_op_desc, condition_op_desc, group_by_trigger_desc ]')
    freq: Optional[int] = Field(1, description='频率')


class Ret(BaseModel):
    data: RetData = Field(description='查询结果的相关信息')
    similarity: float = Field(description='查询结果的相似度')


class Response(BaseModel):
    ret: int = Field(1, description='状态码；是否成功；0 表示 失败，1 表示 成功')
    msg: Optional[str] = Field('', description='错误信息；若 ret = 1，则为空')
    data: Optional[List[List[Ret]]] = Field([], description='搜索到到 descriptions 数据')


@app.post('/v1/data/search/descriptions/by_texts',
          name="v1 data search descriptions by texts",
          response_model=Response,
          description="搜索 描述 数据; 批量搜索")
def data_search_descriptions_by_texts(_input: QueryDescInput):
    from lib.milvus import o_milvus

    q_texts = _input.q_texts
    desc_type = _input.desc_type
    top_k = _input.top_k

    # 检查参数
    if not list(filter(lambda x: x.strip(), q_texts)):
        return {'ret': 0, 'msg': 'q_texts 不能为空'}

    if desc_type and desc_type not in ['column_desc', 'aggregation_column_desc', 'comparison_op_desc', 'keyword',
                                       'condition_op_desc', 'group_by_trigger_desc', 'time_column_desc']:
        return {'ret': 0, 'msg': 'type 只支持 [ column_desc, aggregation_column_desc, comparison_op_desc, '
                                 'condition_op_desc, group_by_trigger_desc, time_column_desc ]'}

    # 预处理文本
    q_texts = list(map(preprocess, q_texts))

    # encode 到 vector
    embeddings = encode(q_texts)

    partitions = [desc_type] if desc_type else None
    start_ = time.time()
    data = o_milvus.search(o_milvus.DESC_NAME, embeddings, top_k, partitions)
    end_ = time.time()
    logs.add('unknown', f'milvus_search', f'search descriptions: {end_ - start_:.4f}s ')
    return {'ret': 1, 'data': data}


if __name__ == '__main__':
    # 测试代码
    q_texts = ['学历'] if len(sys.argv) <= 1 else sys.argv[1:]
    ret = data_search_descriptions_by_texts(QueryDescInput(
        q_texts=q_texts,
        top_k=5,
    ))
    for v in ret['data']:
        print(v)
