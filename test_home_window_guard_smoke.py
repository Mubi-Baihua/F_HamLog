# -*- coding: utf-8 -*-
"""主页窗口守卫烟囱测试（main.py）：

1) 首次点击「新建项目」时 `project_window` 尚未定义，不得抛 NameError；
2) 旧项目窗口正在多人日志会话中时，点「新建项目 / 通联日志」必须先确认，
   用户选「否」不替换（否则会把正在开着的房间一起回收，表现为日志无法同步）；
3) 选「是」才替换。
"""
import os, sys, traceback
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QMessageBox

# 注意：不要在这里创建 QApplication——main.py 的 main() 会自己创建一个，
# 重复创建会抛「Please destroy the QApplication singleton」。
LINES = []
PASS = []


def say(s):
    LINES.append(s)
    print(s)
    with open('__guard_out.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(LINES) + '\n')


def check(name, cond):
    PASS.append(bool(cond))
    say(('  PASS  ' if cond else '  FAIL  ') + name)


try:
    # 让 main() 建完界面就返回（不进入事件循环）
    QApplication.exec = lambda self, *a, **k: 0

    import project
    created = {'n': 0}
    project.main = lambda *a, **k: created.__setitem__('n', created['n'] + 1)

    import main as home
    home.main()
    win = home.window
    check('主页已建立', isinstance(win, QMainWindow))

    def btn(text):
        for b in win.findChildren(QPushButton):
            if b.text() == text:
                return b
        return None

    new_btn = btn('新建项目')
    check('找到「新建项目」按钮', new_btn is not None)

    # --- 1) 首次点击，project_window 未定义 ---
    home.project_window = None
    err = None
    try:
        new_btn.click()
    except Exception:
        err = traceback.format_exc()
    check('首次点击不抛异常（NameError 已修）', err is None)
    if err:
        say(err)
    check('首次点击后创建了窗口', created['n'] == 1 and home.project_window is not None)

    # --- 2) 旧窗口在会话中 + 用户选「否」 ---
    class _FakeConn:
        host = '192.168.1.9'
        port = 8000

    old_win = home.project_window
    old_win._remote = _FakeConn()
    old_win._is_host = True

    answers = {'v': QMessageBox.No}
    asked = {'n': 0}

    class _MB:
        Yes = QMessageBox.Yes
        No = QMessageBox.No
        Warning = QMessageBox.Warning

        @staticmethod
        def question(*a, **k):
            asked['n'] += 1
            return answers['v']

        @staticmethod
        def warning(*a, **k):
            return None

        @staticmethod
        def information(*a, **k):
            return None

    home.QMessageBox = _MB
    new_btn.click()
    check('会话中点击会先询问', asked['n'] == 1)
    check('选「否」不替换窗口（会话保住）', home.project_window is old_win and created['n'] == 1)

    # --- 3) 用户选「是」才替换 ---
    answers['v'] = QMessageBox.Yes
    new_btn.click()
    check('选「是」才替换窗口', asked['n'] == 2 and home.project_window is not old_win
          and created['n'] == 2)
except Exception:
    say('EXCEPTION:\n' + traceback.format_exc())
    sys.exit(2)

say('\n=== HOME_WINDOW_GUARD_SMOKE_OK ===' if all(PASS) else '\n=== SOME FAILED ===')
sys.exit(0 if all(PASS) else 1)
