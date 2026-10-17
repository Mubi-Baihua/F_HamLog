"""后台线程的登记表 + 应用退出前的统一收尾。

为什么需要这个模块
------------------
Qt 在 QThread 的 C++ 对象被销毁而线程**仍在运行**时会走致命路径
（``qFatal`` → ``abort`` → Windows 上是异常代码 ``0xc0000409``、
事件查看器「应用程序错误 1000」出错模块 ``Qt6Core.dll``，用户看到的是
「程序突然消失」，而且 Python 的 traceback 一行都不会留下）。

各窗口自己的 ``closeEvent`` 里 ``wait()`` 只能覆盖「用户主动关掉这个窗口」
这一条路径。下面这些路径不经过 closeEvent，线程就没人管：

* 应用退出（``QApplication.quit()`` / 最后一个窗口被关掉 / 关机注销）；
* 窗口被 ``deleteLater`` 或父对象连带析构；
* 窗口切换（如多人日志「重新连接」时旧连接被整体换掉）。

所以统一在这里登记：所有长生命周期后台线程继承 :class:`BgThread`，
退出前由 :func:`stop_all` 一次性停干净。窗口自己的 ``closeEvent`` 逻辑保持不变
（它更懂各自的业务顺序，仍是第一道防线），这里是最后一道网。

只做登记与收尾，不介入线程内部逻辑，也不改变任何现有停止顺序。
"""

import logging
import weakref

from PySide6.QtCore import QThread

_log = logging.getLogger(__name__)

# 登记表存弱引用：线程对象被回收后自然从表里消失，不会把窗口一起吊住。
_live = []


def _prune():
    """清掉已经失效的弱引用（线程对象被回收），保持登记表短小。"""
    for ref in list(_live):
        try:
            alive = ref()
        except Exception:
            alive = None
        if alive is None:
            try:
                _live.remove(ref)
            except ValueError:
                pass


def live_threads():
    """仍在登记表里、且 C++ 对象还活着的线程列表。"""
    _prune()
    out = []
    for ref in list(_live):
        try:
            thread = ref()
        except Exception:
            thread = None
        if thread is not None:
            out.append(thread)
    return out


class BgThread(QThread):
    """所有长生命周期后台线程的基类。

    只做一件事：把自己登记进表。子类照常实现 ``run()``，不需要任何额外改动。
    登记用弱引用且**不连接任何信号**，避免「线程 ↔ 闭包」互相引用把对象吊住。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if len(_live) > 32:
            _prune()
        try:
            _live.append(weakref.ref(self))
        except TypeError:          # 极端情况下对象不可弱引用：放弃登记，不影响功能
            pass


def _stop_one(thread, wait_ms, terminate_wait_ms):
    """尽力停掉一个线程，返回 'stopped' / 'terminated' / ''（本来就没在跑）。"""
    try:
        if not thread.isRunning():
            return ''
    except RuntimeError:           # C++ 对象已被删除
        return ''

    # 1) 先用线程自己的停止接口（更懂业务：先置位、再断连接，避免误报错误）
    stopper = getattr(thread, 'stop', None)
    if callable(stopper):
        try:
            stopper()
        except Exception:
            _log.debug('线程 %r 的 stop() 抛异常，继续走通用流程', thread, exc_info=True)

    # 2) 请求中断 + 等待。run() 里检查 isInterruptionRequested 的会很快退出
    try:
        thread.requestInterruption()
    except Exception:
        pass
    try:
        if thread.wait(wait_ms):
            return 'stopped'
    except RuntimeError:
        return ''

    # 3) 兜底强杀：进程马上就要退，宁可变丑也不能让 Qt 析构时 abort
    _log.warning('后台线程 %r 在 %d ms 内未退出，强制终止', thread, wait_ms)
    try:
        thread.terminate()
        thread.wait(terminate_wait_ms)
        return 'terminated'
    except RuntimeError:
        return ''


def stop_all(wait_ms=3000, terminate_wait_ms=1000):
    """停掉所有仍在运行的后台线程（应用退出前必须调用；可重复调用）。

    返回 ``(正常停止数, 强制终止数)``，便于日志里核对有没有线程不肯退。
    """
    stopped = terminated = 0
    for thread in live_threads():
        try:
            result = _stop_one(thread, wait_ms, terminate_wait_ms)
        except Exception:
            _log.exception('停止后台线程 %r 时出错（已忽略，继续退出）', thread)
            continue
        if result == 'stopped':
            stopped += 1
        elif result == 'terminated':
            terminated += 1
    if stopped or terminated:
        _log.info('退出前收尾后台线程：正常停止 %d 个，强制终止 %d 个',
                  stopped, terminated)
    return stopped, terminated
