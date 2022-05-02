import os
import sys

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from lib import logs
from lib.redis_utils import redis_keys, redis_batch_get
from lib.milvus import o_milvus
from server.interfaces.data.data_add_avg_values import data_add_avg_values, DataAvgInput

logs.MODULE = 'text2sql'
logs.PROCESS = 'update_avg_emb'

logs.add('Update_Avg_Val_Emb', 'data_add_avg_values', f'start', pre_sep='---------------------')

# 清楚旧的 avg value embeddings
o_milvus.recreate_collection(o_milvus.AVG_VALUE_NAME)

# 从 redis 中获取 moving avg value embedding 的 keys
table = 'moving_avg_embedding'
keys = redis_keys(f'{table}*')
length = len(keys)
logs.add('Update_Avg_Val_Emb', 'Redis', f'number avg value key: {length}')

columns = list(map(lambda x: x.split('____')[-1], keys))
ret_avg = redis_batch_get(columns, table)
logs.add('Update_Avg_Val_Emb', 'Redis', f'finish getting avg embedding from redis')

for i, val in enumerate(ret_avg):
    logs.add('Update_Avg_Val_Emb', 'Progress', f'{i}/{length} ... ')
    ret = data_add_avg_values(DataAvgInput(
        column=columns[i],
        embedding=val['emb'],
    ))

logs.add('Update_Avg_Val_Emb', 'Progress', f'done')
