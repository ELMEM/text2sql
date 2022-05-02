import os
import sys
import argparse
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

os.environ['CUDA_VISIBLE_DEVICES'] = '0'

_cur_dir = os.path.split(os.path.abspath(__file__))[0]
_root_dir = os.path.split(_cur_dir)[0]
sys.path.append(_root_dir)

from lib import logs

logs.MODULE = 'text2sql'
logs.PROCESS = 'server'

from config.env import ENV, DEV
from server.interfaces.base import app
from server.interfaces.suggestions import suggestions
from server.interfaces.fake_sql import fake_sql
from server.interfaces.fake_sql import auto_select
from server.interfaces.data import data_add_values
from server.interfaces.data import data_add_descriptions
from server.interfaces.data import data_search_values_by_texts
from server.interfaces.data import data_search_values_by_vectors
from server.interfaces.data import data_search_descriptions_by_texts
from server.interfaces.data import data_search_descriptions_by_vectors
from server.interfaces.data import data_delete
from server.interfaces.search import search_values
from server.interfaces.search import search_fields
from server.interfaces.fake_sql import fake_sql_from_editor
from server.interfaces.figure import figure_fields

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Text2SQL server")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    uvicorn.run(app, host='0.0.0.0', port=80 if ENV != DEV else 999)
