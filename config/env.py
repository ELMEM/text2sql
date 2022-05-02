import os

PRODUCT = 'product'
TEST = 'test'
PRE_TEST = 'pre_test'
DEV = 'dev'

_default_env = DEV

ENV = os.getenv('MY_DEV_ENV')
ENV = ENV if ENV else _default_env
