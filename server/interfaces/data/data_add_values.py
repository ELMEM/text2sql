from typing import List, Union, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from server.interfaces.base import app
from server.definitions.common import Response
from lib.preprocess import preprocess
from core.encode import encode
from lib import logs
from lib.redis_utils import redis_save, redis_get


class DataInput(BaseModel):
    column: str = Field(description='sql 中的 column name')
    data: List[Union[str, int, float]] = Field(description='插入的数据；支持批量')
    p_ids: Optional[List[int]] = Field(description='data 对应的主键 ids')


def update_moving_avg_embedding(column: str, vectors: List[List[float]]):
    """ 添加 滑动平均向量 """
    ret_avg = redis_get(column, 'moving_avg_embedding')
    # 若不存在该 moving avg embedding
    if not ret_avg:
        avg_embedding = np.mean(np.array(vectors), axis=0)
        count = len(vectors)

    # 若存在，则滑动平均
    else:
        avg_embedding = np.array(ret_avg['emb'])
        count = int(ret_avg['count'])
        for v in vectors:
            beta = min(0.001, 2 / (1 + count))
            count += 1
            avg_embedding = avg_embedding * (1 - beta) + np.array(v) * beta

    avg_embedding = list(map(float, avg_embedding))
    redis_save(column, {'emb': avg_embedding, 'count': count}, 'moving_avg_embedding')

    print(f'successfully update moving average embedding for {column} ')


@app.post('/v1/data/add/values',
          name="v1 data add values",
          response_model=Response,
          description="注入数据，以用于预想输入的数据 value 提示")
def data_add_values(_input: DataInput):
    from lib.milvus import o_milvus, filter_duplicate_texts

    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}')

    column = _input.column
    data = _input.data
    p_ids = _input.p_ids

    if not data:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': f'data 不能为空 (column: {column})'})

    # 过滤空数据
    if p_ids and len(p_ids) == len(data):
        pid_value_pairs = list(filter(lambda x: f'{x[1]}'.strip() and pd.notna(x[1]), zip(p_ids, data)))
        if not pid_value_pairs:
            return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': f'data 不能为空  (column: {column})'})

        p_ids, data = list(zip(*pid_value_pairs))
    else:
        data = list(filter(lambda x: f'{x}'.strip() and pd.notna(x), data))

    if not data:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': f'data 不能为空 (column: {column})'})

    # 转换所有数据到字符串
    texts = list(map(preprocess, data))

    # encode 到 vector
    embeddings = encode(texts)

    # 关联信息
    info = list(map(lambda x: {'text': x, 'column': column}, texts))

    partition = column

    # 过滤重复数据
    filtered_texts, filtered_info, indices = filter_duplicate_texts(o_milvus.VALUE_NAME, texts, info,
                                                                    partition=partition)
    filtered_embeddings = [embeddings[i] for i in indices]
    ret, count = o_milvus.insert(o_milvus.VALUE_NAME, filtered_texts, filtered_embeddings, filtered_info, partition)

    # 更新滑动平均向量
    update_moving_avg_embedding(column, embeddings)

    return logs.ret(log_id, logs.fn_name(), 'POST', {
        'ret': ret, 'msg': f'insert values (column: {column}): {count}/{len(data)}'})


if __name__ == '__main__':
    # 测试代码
    data_add_values(DataInput(column='JobJobName', data=['java工程师']))
