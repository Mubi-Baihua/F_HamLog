"""bg_thread 冒烟：登记表、退出前统一收尾、以及各线程类是否都挂在基类上。

跑法（项目根目录）：
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe tests/__bg_thread_smoke.py
"""
import io
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from PySide6.QtCore import QCoreApplication

from f_hamlog import bg_thread

_app = QCoreApplication.instance() or QCoreApplication([])

_passed, _failed = [], []


def check(name, cond, extra=''):
    if cond:
        _passed.append(name)
        print('  [OK]   %s %s' % (name, extra))
    else:
        _failed.append(name)
        print('  [FAIL] %s %s' % (name, extra))


class _Cooperative(bg_thread.BgThread):
    """配合型线程：收到中断请求就退出。"""

    def __init__(self):
        super().__init__()
        self.runs = 0

    def run(self):
        while not self.isInterruptionRequested():
            self.runs += 1
            time.sleep(0.02)


class _Deaf(bg_thread.BgThread):
    """聋子线程：永不检查中断（用来确认「不会误杀仍在跑的线程」这条边界）。"""

    def __init__(self):
        super().__init__()
        self.stopped_by_itself = False

    def run(self):
        time.sleep(0.4)
        self.stopped_by_itself = True


def main():
    print('== 1. 登记与收尾 ==')
    t = _Cooperative()
    check('新线程启动前不在运行', not t.isRunning())
    check('未启动的线程也能被登记', any(x is t for x in bg_thread.live_threads()))

    t.start()
    time.sleep(0.15)
    check('启动后 isRunning', t.isRunning())
    check('run() 真的在跑', t.runs > 0, '循环次数=%d' % t.runs)

    stopped, killed = bg_thread.stop_all(wait_ms=3000)
    check('stop_all 报告正常停止 >= 1', stopped >= 1, '(stopped=%d, killed=%d)' % (stopped, killed))
    check('stop_all 后线程已退出', not t.isRunning())
    check('没有走强杀路径', killed == 0)

    print('== 2. 幂等 / 空表 ==')
    check('重复 stop_all 无副作用', bg_thread.stop_all(wait_ms=500) == (0, 0))
    check('已结束的线程不再列为运行中', not any(x.isRunning() for x in bg_thread.live_threads()))

    print('== 3. 自己会退出的线程不报强制终止 ==')
    d = _Deaf()
    d.start()
    time.sleep(0.05)
    stopped2, killed2 = bg_thread.stop_all(wait_ms=2000)
    check('等待期内自然退出，不算强杀', killed2 == 0, '(stopped=%d, killed=%d)' % (stopped2, killed2))
    check('该线程确实执行完了 run()', d.stopped_by_itself)

    print('== 4. 各线程类都挂在 BgThread 上 ==')
    from f_hamlog import project, mutual_window, satellite_window
    from f_hamlog import satellite_map_window, satellite_auto_update, tle_source_window
    pairs = [
        ('project._SyncThread', project._SyncThread),
        ('mutual_window.MutualWorker', mutual_window.MutualWorker),
        ('satellite_window.PredictWorker', satellite_window.PredictWorker),
        ('satellite_window.TleFetchWorker', satellite_window.TleFetchWorker),
        ('satellite_map_window.TrackWorker', satellite_map_window.TrackWorker),
        ('satellite_auto_update._FetchThread', satellite_auto_update._FetchThread),
        ('tle_source_window.DelayProbeWorker', tle_source_window.DelayProbeWorker),
    ]
    for label, cls in pairs:
        check('%s 继承 BgThread' % label, issubclass(cls, bg_thread.BgThread))

    print('== 5. 退出路径已接线 ==')
    main_src = io.open(os.path.join(ROOT, 'src', 'f_hamlog', 'main.py'),
                       encoding='utf-8').read()
    check('aboutToQuit 连了 stop_all', 'aboutToQuit.connect(lambda: bg_thread.stop_all())' in main_src)
    check('app.exec() 之后还有一道 stop_all', main_src.rstrip().count('bg_thread.stop_all()') >= 2)

    print('== 6. bg_thread 不依赖包内其它模块（防循环导入）==')
    src = io.open(os.path.join(ROOT, 'src', 'f_hamlog', 'bg_thread.py'),
                  encoding='utf-8').read()
    check('没有 from f_hamlog / import f_hamlog', 'from f_hamlog' not in src and 'import f_hamlog' not in src)

    print('')
    print('通过 %d / %d' % (len(_passed), len(_passed) + len(_failed)))
    print('RESULT=%s' % ('ALL PASS' if not _failed else 'FAILED: ' + ', '.join(_failed)))
    return 0 if not _failed else 1


if __name__ == '__main__':
    sys.exit(main())
