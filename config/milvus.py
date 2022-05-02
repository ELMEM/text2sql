import os
from config import env

if env.ENV == env.DEV:
    milvus_server_conf = {'host': 'mesoor.f3322.net', 'port': '39530'}
elif env.ENV == env.PRE_TEST:
    milvus_server_conf = {'host': '10.10.10.202', 'port': '9530'}
else:
    _host = os.getenv('MILVUS_HOST')
    _host = _host if _host else 'dev-milvus-milvus.milvus'
    milvus_server_conf = {'host': _host, 'port': '19530'}
