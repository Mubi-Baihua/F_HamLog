# -*- coding: utf-8 -*-
"""
satellite_auto_update.py —— 卫星星历（TLE）自动定时更新

功能：
  在应用程序生命周期内，按用户在“设置”中指定的间隔，自动从 Celestrak
  下载业余卫星 TLE 并刷新本地缓存 file/amateur.tle。

  设计要点：
    - 不依赖任何界面：由 main.py 在启动时调用 AutoTleUpdater(parent).start()
      即可，开关完全由设置 file/m_xml.txt 的 sat_auto_update / sat_update_hours 控制；
    - 定时器每小时“巡检”一次是否到了更新时间（避免修改设置后必须重启程序才生效）；
    - 实际下载在后台线程中进行，不会阻塞主界面；
    - 上次成功（或失败）更新时间持久化到设置（sat_last_update），重启后据此判断是否立即更新。

依赖：PySide6（仅用 QTimer / QThread）、satellite_pred（fetch_amateur_tle）。
"""

import os
import time

from PySide6.QtCore import QTimer, QThread, Signal

import satellite_pred as sp


SETTINGS_PATH = sp.app_path('file/m_xml.txt')
TLE_CACHE = sp.app_path('file/amateur.tle')

# 定时器巡检粒度（毫秒）。每小时检查一次“是否到了更新时间”，
# 这样用户在设置里改了开关/间隔后无需重启即可生效。
TICK_MS = 60 * 60 * 1000

DEFAULT_INTERVAL_HOURS = 24

# 上次更新时间（epoch 秒）在设置中的键，用于跨启动判断是否该更新
_LAST_FETCH_KEY = 'sat_last_update'


# ---------------------------------------------------------------------------
#  设置读写（与 satellite_window / set 保持一致：宽松容错）
# ---------------------------------------------------------------------------

def _load_settings():
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            return eval(f.read())
    except Exception:
        return {}


def _save_last_fetch(epoch):
    try:
        try:
            s = _load_settings()
        except Exception:
            # 读取失败（如文件损坏）：不要覆盖，避免清空用户设置
            print('[卫星星历] 警告：读取设置失败，跳过时间戳写入，保留原设置文件。')
            return
        s[_LAST_FETCH_KEY] = epoch
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
            f.write(str(s))
    except Exception as e:
        print('[卫星星历] 警告：时间戳写入失败：%s' % e)


def should_update_now(settings=None, now=None):
    """判断此刻是否应该执行一次 TLE 更新（纯函数，便于测试）。

    返回 (should: bool, interval_hours: int)。
      - settings 缺省时从文件读取；
      - 未开启自动更新 -> False；
      - 距上次更新不足 interval 小时 -> False；
      - 否则 -> True。
    """
    if settings is None:
        settings = _load_settings()
    if not settings.get('sat_auto_update', False):
        return False, DEFAULT_INTERVAL_HOURS
    hours = int(settings.get('sat_update_hours', DEFAULT_INTERVAL_HOURS) or DEFAULT_INTERVAL_HOURS)
    hours = max(1, hours)
    if now is None:
        now = time.time()
    last = settings.get(_LAST_FETCH_KEY)
    if last is not None:
        try:
            last = float(last)
        except (TypeError, ValueError):
            last = 0.0
        if now - last < hours * 3600:
            return False, hours
    return True, hours


# ---------------------------------------------------------------------------
#  后台下载线程
# ---------------------------------------------------------------------------

class _FetchThread(QThread):
    """在后台线程中强制刷新 TLE 缓存。done(ok: bool, msg: str)。"""

    done = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            sp.fetch_amateur_tle(cache_path=TLE_CACHE, force=True, timeout=30)
            self.done.emit(True, '')
        except Exception as e:  # 网络失败等
            self.done.emit(False, str(e))


# ---------------------------------------------------------------------------
#  自动更新管理器
# ---------------------------------------------------------------------------

class AutoTleUpdater:
    """应用级 TLE 自动更新定时器。

    用法：
        updater = AutoTleUpdater(window)   # window 为持久存在的父窗口
        updater.start()
    不需要界面即可工作；开关与间隔由设置决定。
    """

    def __init__(self, parent=None):
        self._timer = QTimer(parent)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._thread = None
        self._busy = False

    def start(self):
        self._timer.start()
        # 启动后立即检查一次：首次运行（无 sat_last_update）或已过期时立即刷新，
        # 不再需要等待 1 小时巡检才首次触发，避免“开着几分钟就关、永远不写入”的问题。
        self._tick()

    def stop(self):
        self._timer.stop()

    def _tick(self):
        if self._busy:
            return
        should, _hours = should_update_now()
        if not should:
            return
        # 标记忙碌并启动后台下载，避免阻塞主线程
        self._busy = True
        self._thread = _FetchThread(self._timer.parent())
        self._thread.done.connect(self._on_done)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_done(self, ok, msg):
        self._busy = False
        if ok:
            epoch = time.time()
            _save_last_fetch(epoch)
            print('[卫星星历] 自动更新成功：TLE 已刷新到 %s。' % TLE_CACHE)
            print('[卫星星历] 时间戳已写入 sat_last_update=%s' % epoch)
        else:
            # 失败不更新 sat_last_update，下一小时巡检会重试；
            # 同时记录日志便于排查（多为离线 / 网络受限）。
            print('[卫星星历] 自动更新失败：%s' % msg)


if __name__ == '__main__':
    # 简单自测：直接触发一次更新并尝试启动定时器（需 PySide6 事件循环）
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    updater = AutoTleUpdater()
    print('should_update_now =', should_update_now())
    updater.start()
    app.exec()
