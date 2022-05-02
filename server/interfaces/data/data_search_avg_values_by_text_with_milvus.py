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
from server.interfaces.base import app
from lib import logs


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


@app.post('/v1/data/search/avg_values/by_texts_with_milvus',
          name="v1 data search avg values by texts with milvus",
          response_model=Response,
          description="搜索 value 数据; 批量搜索")
def data_search_avg_values_by_texts_with_milvus(_input: QueryAvgValueInput):
    from lib.milvus import o_milvus

    q_texts = _input.q_texts
    top_k = _input.top_k

    # 检查参数
    if not list(filter(lambda x: x.strip(), q_texts)):
        return {'ret': 0, 'msg': 'q_texts 不能为空'}

    # 预处理文本
    q_texts = list(map(preprocess, q_texts))

    # encode 到 vector
    embeddings = encode(q_texts)

    start_ = time.time()
    data = o_milvus.search(o_milvus.AVG_VALUE_NAME, embeddings, top_k)
    end_ = time.time()
    logs.add('unknown', f'milvus_search', f'search avg values : {end_ - start_:.4f}s ')
    return {'ret': 1, 'data': data}


if __name__ == '__main__':
    # 测试代码
    q_texts = ['本科学历'] if len(sys.argv) <= 1 else sys.argv[1:]
    ret = data_search_avg_values_by_texts_with_milvus(QueryAvgValueInput(
        q_texts=q_texts,
    ))
    print(ret)
