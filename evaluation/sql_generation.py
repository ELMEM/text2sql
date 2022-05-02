import os
import sys
import json

os.environ['CUDA_VISIBLE_DEVICES'] = '1'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from config.path import TEST_DATA_PATH
from server.definitions.suggestions import Choice, LastChoice
from core.relation_extraction import extract_relations


def relation_dict(relations):
    _dict = []
    for i in range(len(relations)):
        _dict.append({
            'relation_type': relations[i].relation_type,
            'head_id': int(relations[i].head_id),
            'tail_id': int(relations[i].tail_id),
            'priority': relations[i].priority,
        })
    return _dict


def equal_list(dict_1, dict_2):
    if (dict_1["head_id"] == dict_2["head_id"]) and (dict_1["tail_id"] == dict_2["tail_id"]) and (
            dict_1["relation_type"] == dict_2["relation_type"]):
        return 1
    else:
        return 0


if __name__ == '__main__':
    pool_size = 30

    # 加载测试集
    with open(TEST_DATA_PATH, 'rb') as f:
        data = json.load(f)

    acc = 0
    for i, tmp_data in enumerate(data):
        is_wrong = 0
        input_texts = tmp_data["input"]
        _result = tmp_data["output_type"]
        _rela = tmp_data["output_rela"]
        _result_index = [[index, data] for index, data in enumerate(_result)]
        _result_index = list(map(lambda x: LastChoice(
            id=str(x[0]), text=x[1][1], type=x[1][0][0] if isinstance(x[1][0], list) else x[1][0],
            data=[Choice(text=x[1][1], value=x[1][-1][0], score=1.)])
                                 , _result_index))
        _pred_rela = extract_relations(_result_index)
        _pred_rela = relation_dict(_pred_rela)
        _rela_sort = sorted(_rela, key=lambda x: (x["priority"], x["head_id"], x["tail_id"], x["relation_type"]))
        _pred_rela_sort = sorted(_pred_rela,
                                 key=lambda x: (x["priority"], x["head_id"], x["tail_id"], x["relation_type"]))
        if not (_rela_sort or _pred_rela_sort):
            acc += 1
        elif not _rela_sort:
            acc += 0
            is_wrong = 1
        elif not _pred_rela_sort:
            acc += 0
            is_wrong = 1
        else:
            _N = len(_pred_rela_sort)
            _n = len(_rela_sort)
            temp = 0
            count = 0
            for i_ in range(_N):
                for j_ in range(temp, _n):
                    if equal_list(_pred_rela_sort[j_], _rela_sort[i_]):
                        temp = j_
                        count += 1
                        break
            acc += count / _N
            if (count / _N) != 1:
                is_wrong = 1
        if is_wrong:
            print("--------------------------------------")
            print(f"第{i}个判断错误")
            print(f"判断为{_pred_rela_sort}")
            print(f"实际为{_rela_sort}")
            print("--------------------------------------")
            temp = 0

    print(f"acc: {acc / (i + 1)}")
