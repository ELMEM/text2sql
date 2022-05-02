import os
from config.path import DESC_DIR, VALUE_DIR
from scripts.change_column import _load_config

if __name__ == '__main__':
    column_change = _load_config("change_column.json")
    des_files = os.listdir(DESC_DIR)
    folders = list(filter(lambda x: x != '.DS_Store', des_files))
    for column_ in column_change:
        for folder in folders:
            temp_folder = os.path.join(DESC_DIR, folder)
            files = os.listdir(temp_folder)
            files = list(filter(lambda x: x != '.DS_Store', files))
            for file in files:
                if file.split(".json")[0] == column_['name']:
                    file = os.path.join(temp_folder, file)
                    change_file = column_['W_name'] + ".json"
                    change_column = os.path.join(temp_folder, change_file)
                    os.rename(file, change_column)
                    file_name = file.split("/")[-1]
                    temp_name = change_column.split("/")[-1]
                    print(f"成功将{file_name}改名为{temp_name}")
