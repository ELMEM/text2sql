import os
import sys
import pandas as pd
import numpy as np

os.environ['CUDA_VISIBLE_DEVICES'] = '0'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from server.interfaces.data.data_add_values import data_add_values, DataInput
from server.interfaces.data.data_add_avg_values import data_add_avg_values, DataAvgInput
from config.path import VALUE_DIR
from core.processor import d_column_2_zh_name
from core.encode import encode

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == '--drop_all':
        from lib.milvus import o_milvus

        o_milvus.recreate_collection(o_milvus.VALUE_NAME)
        o_milvus.recreate_collection(o_milvus.AVG_VALUE_NAME)

    file_names = list(filter(lambda x: not x.startswith('.'), os.listdir(VALUE_DIR)))

    # 添加 avg value embeddings 到 milvus
    for file_name in file_names:
        column = file_name.split(".")[0]

        # 过滤王永和端不支持的字段
        if column not in d_column_2_zh_name:
            continue

        file_path = os.path.join(VALUE_DIR, file_name)

        df = pd.read_csv(file_path)

        # 过滤空数据
        tmp_pairs = list(map(lambda x: [f'{x[0]}' if pd.notna(x[0]) else '', x[1]], zip(df['text'], df['freq'])))
        text_freq_pairs = list(filter(lambda x: x[0].strip(), tmp_pairs))
        texts, freqs = list(zip(*text_freq_pairs))

        # encode 成 embedding
        embeddings = encode(texts)
        data = list(map(lambda x: {'emb': x[0], 'freq': x[1]}, zip(embeddings, freqs)))

        # 获取 加权平均向量
        total_freq = np.sum(np.sqrt(np.array(freqs)))
        embeddings = np.array(list(map(lambda x: np.array(x['emb']) * np.sqrt(x['freq']) / total_freq, data)))
        weighted_sum_embeddings = np.sum(embeddings, axis=0)
        weighted_sum_embeddings = list(map(float, weighted_sum_embeddings))

        # 插入 初始加权平均向量
        print(f'inserting avg embeddings for {column}')
        print(data_add_avg_values(DataAvgInput(
            column=column,
            embedding=weighted_sum_embeddings,
            count=total_freq,
        )))

    # 添加 value embeddings 到 milvus
    for file_name in file_names:
        column = file_name.split(".csv")[0]

        # 过滤王永和端不支持的字段
        if column not in d_column_2_zh_name:
            continue

        file_path = os.path.join(VALUE_DIR, file_name)

        df = pd.read_csv(file_path)
        texts = list(map(lambda x: f'{x}' if pd.notna(x) else '', df['text']))
        texts = list(filter(lambda x: x.strip(), texts))

        if texts:
            print(data_add_values(DataInput(
                column=column,
                data=texts
            )))

    print('\ndone')
