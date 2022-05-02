import os
import sys

if __name__ == '__main__':
    os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    _cur_dir = os.path.split(os.path.abspath(__file__))[0]
    _root_dir = os.path.split(_cur_dir)[0]
    sys.path.append(_root_dir)

import torch as th
from typing import List, Union
from sqlitedict import SqliteDict
from accelerate import Accelerator
from transformers import RoFormerTokenizer, RoFormerModel
from config.path import DB_DIR, MODEL_DIR

_MAX_LEN = 64
_MAX_TEXT_LEN = 128

_accelerator = Accelerator()
_device = _accelerator.device

model_path = os.path.join(MODEL_DIR, 'roformer_chinese_sim_char_ft_small')
_tokenizer = RoFormerTokenizer.from_pretrained(model_path)
_model = RoFormerModel.from_pretrained(model_path, embedding_size=384)
_model = _accelerator.prepare(_model)


def _db(db_name: str, table_name: str = None):
    """ 使用 sqlite 作为缓存 """
    table_name = table_name if table_name else db_name
    return SqliteDict(os.path.join(DB_DIR, f'{db_name}.sqlite'), tablename=table_name, autocommit=True)


def _encode_a_batch(texts: List[str]) -> List[List[float]]:
    """ encode 一个 batch 的数据到向量表示 """
    batch_tok = _tokenizer(texts, padding=True, truncation=True, max_length=_MAX_LEN, return_tensors='pt')
    batch_tok = {k: v.to(_device) for k, v in batch_tok.items()}
    batch_out = _model(**batch_tok).last_hidden_state

    # take the mean
    att_mask = batch_tok['attention_mask']
    embs = th.sum(batch_out * att_mask[..., None], axis=1) / th.sum(att_mask, axis=1)[..., None]

    # normalize
    embs = embs / (embs ** 2).sum(axis=1).sqrt()[..., None]

    # format result to List[List[float]]
    embs = embs.cpu().detach().numpy()
    return list(map(lambda e: list(map(float, e)), embs))


def encode(texts: Union[str, List[str]], refresh=False, batch_size=64) -> List[List[float]]:
    if isinstance(texts, str):
        texts = [texts]

    # 限制长度
    texts = list(map(lambda x: x[:_MAX_TEXT_LEN], texts))

    # 过滤重复
    input_data = list(set(texts))

    # 过滤已缓存文本
    if not refresh:
        with _db('embeddings') as d:
            input_data = list(filter(lambda x: x not in d, input_data))

    # Encode
    length = float(len(input_data))
    embeddings = []
    for i in range(0, len(input_data), batch_size):
        print(f'\rprogress: {(i + 1) / length * 100.:.2f}%  ', end='')
        sys.stdout.flush()

        tmp_vectors = _encode_a_batch(input_data[i: i + batch_size])
        embeddings.extend(tmp_vectors)

    print('\rprogress: 100%      ')
    sys.stdout.flush()

    with _db('embeddings') as d:
        # 缓存结果
        for i, _text in enumerate(input_data):
            d[_text] = embeddings[i]

        # 取数据
        return [d[_text] for _text in texts]


if __name__ == '__main__':
    # 测试代码
    z = encode("不喜欢", refresh=True)
    print(z)

    # z /= (z ** 2).sum(axis=1, keepdims=True) ** 0.5
    # print((z[0]*z[1]).sum())
