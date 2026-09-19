# -*- coding: utf-8 -*-
"""离线冒烟：独立服务端（F_HamLog_Remote_Log_Server_2.0.0）自动创建所需文件与目录。

做法：把该目录的三个模块复制到一个全新的临时目录（模拟“新目录首次运行”），
在 offscreen 下构造 ServerGUI，检查 keys/、main.fhl、password_xml.txt 是否被自动建好，
并连跑两次核对「长期密钥不会被覆盖」（同一端口身份稳定）。不会改动仓库里的真实运行数据。
"""
import os
import sys
import shutil
import tempfile
import subprocess
import py_compile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'F_HamLog_Remote_Log_Server_2.0.0')
REPORT = os.path.join(ROOT, '__rl_autocreate_out.txt')
lines = []


def log(msg):
    lines.append(str(msg))


# ---- 1) 语法检查 ----
for path in (os.path.join(ROOT, 'project.py'), os.path.join(SRC, 'main.py')):
    try:
        py_compile.compile(path, doraise=True)
        log(f'[OK] py_compile {os.path.relpath(path, ROOT)}')
    except Exception as e:
        log(f'[FAIL] py_compile {os.path.relpath(path, ROOT)}: {e}')

# ---- 2) 临时目录里跑 ServerGUI ----
tmp = tempfile.mkdtemp(prefix='rl_srv_')
for name in ('main.py', 'remote_server.py', 'remote_crypto.py'):
    shutil.copy2(os.path.join(SRC, name), os.path.join(tmp, name))

DRIVER = (
    "import os, sys\n"
    "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
    "from PySide6.QtWidgets import QApplication\n"
    "app = QApplication([])\n"
    "import main, remote_crypto\n"
    "w = main.ServerGUI()\n"
    "d = main._app_dir()\n"
    "tag = sys.argv[1]\n"
    "out = []\n"
    "out.append('app_dir=%s' % d)\n"
    "out.append('port_field=%s' % w.port_edit.text())\n"
    "out.append('password_field=%s' % w.pass_edit.text())\n"
    "out.append('keys_dir=%s' % os.path.isdir(os.path.join(d, 'keys')))\n"
    "keys = sorted(os.listdir(os.path.join(d, 'keys'))) if os.path.isdir(os.path.join(d, 'keys')) else []\n"
    "out.append('keys_files=%s' % keys)\n"
    "fhl = os.path.join(d, 'main.fhl')\n"
    "out.append('main.fhl=%s content=%r' % (os.path.exists(fhl), open(fhl, encoding='utf-8').read() if os.path.exists(fhl) else None))\n"
    "pw = os.path.join(d, 'password_xml.txt')\n"
    "out.append('password_xml=%s content=%r' % (os.path.exists(pw), open(pw, encoding='utf-8').read() if os.path.exists(pw) else None))\n"
    "kp = remote_crypto.key_file_for_port(8000, d)\n"
    "out.append('key_path=%s' % kp)\n"
    "out.append('key_bytes=%r' % (open(kp, 'rb').read() if os.path.exists(kp) else None))\n"
    "priv, created = remote_crypto.load_or_create_server_key(kp)\n"
    "out.append('load_created=%s fingerprint=%s' % (created, remote_crypto.fingerprint_short(remote_crypto.public_key_bytes(priv))))\n"
    "out.append('logbox=%r' % w.log_box.toPlainText())\n"
    "open(os.path.join(d, '_result_%s.txt' % tag), 'w', encoding='utf-8').write('\\n'.join(out))\n"
    "print('SMOKE_DONE')\n"
)
driver = os.path.join(tmp, '_driver.py')
with open(driver, 'w', encoding='utf-8') as f:
    f.write(DRIVER)

env = dict(os.environ)
env['QT_QPA_PLATFORM'] = 'offscreen'
results = {}
for tag in ('run1', 'run2'):
    try:
        p = subprocess.run([sys.executable, driver, tag], cwd=tmp, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        log(f'[子进程 {tag}] exit={p.returncode} output={p.stdout.decode("utf-8", "replace").strip()[:600]}')
    except Exception as e:
        log(f'[FAIL {tag}] 子进程异常：{e}')
    rf = os.path.join(tmp, f'_result_{tag}.txt')
    if os.path.exists(rf):
        with open(rf, encoding='utf-8') as f:
            results[tag] = f.read()
        log(f'---- {tag} ----')
        log(results[tag])
    else:
        log(f'[FAIL {tag}] 未产出结果文件')

if len(results) == 2:
    same_key = None
    for line in results['run1'].splitlines():
        if line.startswith('key_bytes='):
            k1 = line
    for line in results['run2'].splitlines():
        if line.startswith('key_bytes='):
            k2 = line
    same_key = (k1 == k2)
    log(f'[核对] 两次启动的长期密钥是否一致（应 True）：{same_key}')

# ---- 3) 仓库内的服务端目录不应被这次测试写入 ----
log('---- 仓库内服务端目录（测试不应写入）----')
log(f"keys_exists={os.path.isdir(os.path.join(SRC, 'keys'))} "
    f"main.fhl_exists={os.path.exists(os.path.join(SRC, 'main.fhl'))}")

shutil.rmtree(tmp, ignore_errors=True)
with open(REPORT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines) + '\n')
print('REPORT_WRITTEN')
