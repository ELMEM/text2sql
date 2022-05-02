import os

# 代码的根目录
CODE_ROOT = os.path.split(os.path.split(os.path.abspath(__file__))[0])[0]

# config 目录
CONF_DIR = os.path.join(CODE_ROOT, 'config', 'conf_files')
RULE_DIR = os.path.join(CODE_ROOT, 'config', 'rules')
DESC_DIR = os.path.join(CODE_ROOT, 'config', 'descriptions')
TEST_SET_DIR = os.path.join(CODE_ROOT, 'config', 'testset')

# 代码项目名
PRJ_NAME = os.path.split(CODE_ROOT)[1]

# 数据的根目录
DATA_ROOT = os.path.join(os.path.split(os.path.split(CODE_ROOT)[0])[0], 'data', PRJ_NAME)

# 数据库的目录
DB_DIR = os.path.join(DATA_ROOT, 'db')

MODEL_DIR = os.path.join(DATA_ROOT, 'models')

VALUE_DIR = os.path.join(DATA_ROOT, 'values')

LOG_DIR = os.path.join(DATA_ROOT, 'logs')

TEST_DATA_PATH = os.path.join(TEST_SET_DIR, 'test_data.json')

# 创建数据的根目录
_root = r'/'
for dir_name in DATA_ROOT.split(r'/'):
    if not dir_name:
        continue

    _root = os.path.join(_root, dir_name)
    if not os.path.exists(_root):
        os.mkdir(_root)

# 创建目录
for _dir_path in [DB_DIR, MODEL_DIR, VALUE_DIR, LOG_DIR]:
    if not os.path.exists(_dir_path):
        os.mkdir(_dir_path)
