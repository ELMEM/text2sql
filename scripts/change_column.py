import json
import os
from config.path import CONF_DIR
from typing import List


def _load_config(name: str = 'text2sql_support_columns.json'):
    with open(os.path.join(CONF_DIR, name), 'rb') as f:
        data: List[dict] = json.load(f)
    return data


if __name__ == '__main__':
    _column = _load_config("text2sql_support_columns.json")
    _stand_column = _load_config("yonghe_support_columns.json")
    data = []
    for key, value in _column.items():
        value = sorted(value, key=lambda x: -x["score"])
        is_break = 0
        for _value in value:
            if is_break:
                break
            temp = _value.get('std_field')
            record = []
            column = {}
            for k, v in _stand_column.items():
                for _v in v:
                    if _v.get('std_field') == temp:
                        record.append([_v.get('score'), key, k, _v.get("std_field")])
                        is_break = 1
            record = sorted(record, key=lambda x: -x[0])
            if record:
                column["name"] = record[0][1]
                column["W_name"] = record[0][2]
                column["value"] = record[0][3]
                data.append(column)
    with open(os.path.join(CONF_DIR, "change_column.json"), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
