import os
from config.path import VALUE_DIR, DATA_ROOT
from scripts.change_column import _load_config
import pandas as pd

if __name__ == '__main__':
    column_change = _load_config("change_column.json")
    val_files = os.listdir(VALUE_DIR)
    folders = list(filter(lambda x: x != '.DS_Store', val_files))
    for column_ in column_change:
        for folder in folders:
            temp_folder = os.path.join(VALUE_DIR, folder)
            files = os.listdir(temp_folder)
            files = list(filter(lambda x: x != '.DS_Store', files))
            for file in files:
                if file.split(".csv")[0] == column_['W_name']:
                    # file = os.path.join(temp_folder, file)
                    change_file = column_['W_name'] + ".csv"
                    change_name = os.path.join(temp_folder, change_file)
                    # os.rename(file, change_name)
                    data_files = os.listdir(os.path.join(DATA_ROOT, "data_value"))
                    data_files = list(filter(lambda x: x != '.DS_Store', data_files))
                    newdata = 0
                    for data_file in data_files:
                        if data_file.split(".csv")[0] == column_['value']:
                            newdata = pd.read_csv(os.path.join(DATA_ROOT, "data_value", data_file))
                            print(f"{column_['value']}---成功---")
                    if not isinstance(newdata, int):
                        newdata.to_csv(change_name)
                    file_name = file.split("/")[-1]
                    temp_name = change_name.split("/")[-1]
                    print(f"成功将{file_name}改名为{temp_name}")
