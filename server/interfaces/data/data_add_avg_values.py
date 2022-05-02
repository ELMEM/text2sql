from typing import List, Optional
from pydantic import BaseModel, Field
from server.interfaces.base import app
from server.definitions.common import Response
from lib import logs


# from lib.redis_utils import redis_save


class DataAvgInput(BaseModel):
    column: str = Field(description='sql 中的 column name')
    embedding: List[float] = Field(description='插入的向量')
    # count: Optional[int] = Field(description='该column下的value总数量')


@app.post('/v1/data/add/avg_values',
          name="v1 data add avg values",
          response_model=Response,
          description="注入数据，以用于预想输入的数据 value 提示")
def data_add_avg_values(_input: DataAvgInput):
    from lib.milvus import o_milvus

    log_id = logs.uid()
    logs.add(log_id, f'POST {logs.fn_name()}', f'payload: {_input}')

    column = _input.column
    embedding = _input.embedding
    # count = _input.count

    if not column or not embedding:
        return logs.ret(log_id, logs.fn_name(), 'POST', {'ret': 0, 'msg': 'column 和 embedding 都不能为空'})

    # 关联信息
    info = [{'column': column}]

    # 插入数据
    ret, insert_count = o_milvus.insert(o_milvus.AVG_VALUE_NAME, [column], [embedding], info)
    # redis_save(column, {'emb': embedding, 'count': count}, 'moving_avg_embedding')

    return logs.ret(log_id, logs.fn_name(), 'POST', {
        'ret': ret, 'msg': f'insert avg value embedding (column: {column}): {insert_count}'})


if __name__ == '__main__':
    # 测试代码
    from core.encode import encode

    data_add_avg_values(DataAvgInput(
        column='test',
        embedding=encode('你好')[0]
    ))
