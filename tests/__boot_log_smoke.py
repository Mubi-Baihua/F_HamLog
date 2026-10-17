# -*- coding: utf-8 -*-
"""启动兜底冒烟：导入链断掉时，__main__ 必须留下 boot 日志（这是「打不开还没日志」的最后防线）。

做法：造一个假的 f_hamlog 包（没有 app_log、main 故意抛 ImportError），
把真的 __main__.py 拷进去执行。真实场景就是「打包后包里没有项目模块」。
"""
import os
import shutil
import subprocess
import sys
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(PROJECT_DIR, 'src', 'f_hamlog', '__main__.py')

_passed = []
_failed = []


def ok(name, cond, detail=''):
    if cond:
        _passed.append(name)
        print('[PASS] %s' % name)
    else:
        _failed.append(name)
        print('[FAIL] %s   %s' % (name, detail))


TMP = tempfile.mkdtemp(prefix='fhl_boot_')
pkg = os.path.join(TMP, 'f_hamlog')
os.makedirs(pkg)

with open(os.path.join(pkg, '__init__.py'), 'w', encoding='utf-8') as f:
    f.write('__version__ = "0.0.0-test"\n')
# main 模块存在但导入即失败：模拟「模块没被 Nuitka 收录 / 依赖缺失」
with open(os.path.join(pkg, 'main.py'), 'w', encoding='utf-8') as f:
    f.write('raise ImportError("模拟：f_hamlog.main 无法导入")\n')
shutil.copyfile(ENTRY, os.path.join(pkg, '__main__.py'))

env = dict(os.environ)
env['LOCALAPPDATA'] = TMP          # boot 日志落到这里，别污染真实用户目录
env['PYTHONIOENCODING'] = 'utf-8'

proc = subprocess.run([sys.executable, os.path.join(pkg, '__main__.py')],
                      env=env, capture_output=True, text=True, timeout=120)

boot_dir = os.path.join(TMP, 'F_HamLog', 'log')
# 主程序优先写「exe 旁 file/log」（这里是 venv\Scripts），写不进去才退到用户目录；
# 两个位置都找一遍，测完把落到 venv 里的那份删掉。
boot_candidates = [os.path.join(os.path.dirname(sys.executable), 'file', 'log'), boot_dir]
boot_files = []
for d in boot_candidates:
    if not os.path.isdir(d):
        continue
    boot_files += [os.path.join(d, n) for n in os.listdir(d)
                   if n.startswith('F_HamLog_boot')]
content = ''
if boot_files:
    with open(boot_files[0], encoding='utf-8', errors='replace') as f:
        content = f.read()

ok('C1 导入失败时进程以非零码退出（不再静默）', proc.returncode != 0, proc.returncode)
ok('C2 生成了 boot 日志', bool(boot_files), boot_dir)
ok('C3 boot 里有启动痕迹', '[boot] 启动' in content)
ok('C4 记录了「导入 app_log 失败」', '导入 f_hamlog.app_log 失败' in content)
ok('C5 记录了「导入 f_hamlog.main 失败」', '导入 f_hamlog.main 失败' in content)
ok('C6 boot 里有完整 traceback', 'Traceback (most recent call last)' in content)
ok('C7 traceback 里有真实异常信息', 'f_hamlog.main 无法导入' in content)
ok('C8 boot 里记录了 exe / argv 环境',
   'exe=' in content and 'argv=' in content)

print('')
print('通过 %d / %d' % (len(_passed), len(_passed) + len(_failed)))
print('boot 日志：%s' % (boot_files[0] if boot_files else '(未生成)'))
print('RESULT=%s' % ('ALL PASS' if not _failed else 'FAILED'))

# 清理落到 venv\Scripts\file\log 的测试痕迹
for p in boot_files:
    try:
        os.remove(p)
    except OSError:
        pass
for d in boot_candidates:
    try:
        os.rmdir(d)
    except OSError:
        pass

sys.exit(0 if not _failed else 1)
