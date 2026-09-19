# -*- coding: utf-8 -*-
"""探针：直接调用 key 生成 API，看异常到底出在哪。"""
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'F_HamLog_Remote_Log_Server_2.0.0')
sys.path.insert(0, SRC)
import remote_crypto

lines = []
d = os.path.join(ROOT, '__rl_probe_dir')
os.makedirs(d, exist_ok=True)
lines.append(f'suffix={remote_crypto.KEY_FILE_SUFFIX!r}')
p = remote_crypto.key_file_for_port(8000, d)
lines.append(f'path={p}')
try:
    priv, created = remote_crypto.load_or_create_server_key(p)
    lines.append(f'created={created} exists={os.path.exists(p)}')
except Exception:
    lines.append('EXC:\n' + traceback.format_exc())

lines.append(f'listdir={sorted(os.listdir(d))}')
lines.append(f'keys_listdir={sorted(os.listdir(os.path.join(d, "keys"))) if os.path.isdir(os.path.join(d, "keys")) else None}')
import shutil
shutil.rmtree(d, ignore_errors=True)
open(os.path.join(ROOT, '__rl_probe_out.txt'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('PROBE_DONE')
