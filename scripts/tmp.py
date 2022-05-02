import sys
import time

""" 添加常驻进程，以防部署的时候程序出错导致pod重启而没有日志 """

while True:
    print(f'\r {time.localtime()}', end='')
    sys.stdout.flush()
    time.sleep(300)
