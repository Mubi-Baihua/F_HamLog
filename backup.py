"""未保存内容自动备份与恢复工具。

设计要点：
- 备份文件本身即「可恢复的未保存状态」：非空表示有可恢复内容，空文件表示无需恢复。
- project 备份：file/project_backup.fhl（沿用原项目的加密 key）。
- batch  备份：file/batch_backup.fh（始终明文，因为批量记录本身不绑定加密密钥）。
- 关闭窗口时若有未保存更改，弹出『保存 / 不保存 / 取消』；选择「不保存」时保留备份，
  下次启动 main.py 即可提示恢复。
"""

import os
import fhl_rw

PROJECT_BACKUP = os.path.join('file', 'project_backup.fhl')
BATCH_BACKUP = os.path.join('file', 'batch_backup.fh')


def _ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d)


def write_backup(path, data, key=None):
    """写入备份。data 为空（None 或空列表）时直接置空文件（表示无需恢复）。"""
    _ensure_dir(path)
    if data is None or (isinstance(data, list) and len(data) == 0):
        open(path, 'w', encoding='utf-8').close()
        return
    fhl_rw.write_fhl_file(path, data, key)


def clear_backup(path):
    """将备份文件置空（表示无需恢复）。"""
    _ensure_dir(path)
    open(path, 'w', encoding='utf-8').close()


def is_backup_nonempty(path):
    """备份文件是否存在且非空（>0 字节）。"""
    return os.path.exists(path) and os.path.getsize(path) > 0


def install_close_guard(window, callbacks):
    """在 window 上安装关闭守卫。

    callbacks 需包含：
      is_dirty()      -> bool   是否有未保存更改
      write_backup()          立即把当前状态写入备份（用于「不保存」分支）
      clear_backup()          清空备份（用于正常保存 / 无更改关闭）
      do_save()       -> bool 执行保存，返回是否成功

    关闭逻辑：
      - 无未保存更改：清空备份并直接关闭。
      - 有未保存更改：弹『保存 / 不保存 / 取消』。
          保存  -> 执行保存，成功后清空备份并关闭；失败则保持打开。
          不保存 -> 写入最新备份（含未保存内容）后关闭，便于下次恢复。
          取消  -> 保持窗口打开。
    """
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QMessageBox

    class _CloseGuard(QObject):
        def __init__(self, w, cb):
            super().__init__(w)
            self._w = w
            self._cb = cb
            self._allow = False
            w.installEventFilter(self)

        def eventFilter(self, obj, event):
            if event.type() != QEvent.Close:
                return False
            # 已获准关闭（由下方 window.close() 重新触发），放行
            if self._allow:
                self._allow = False
                return False
            # 无未保存更改：清空备份并直接关闭
            if not self._cb['is_dirty']():
                try:
                    self._cb['clear_backup']()
                except Exception:
                    pass
                return False

            event.ignore()
            msg = QMessageBox(self._w)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle('未保存的更改')
            msg.setText('当前窗口有未保存的更改，是否保存？')
            btn_save = msg.addButton('保存', QMessageBox.AcceptRole)
            btn_discard = msg.addButton('不保存', QMessageBox.DestructiveRole)
            btn_cancel = msg.addButton('取消', QMessageBox.RejectRole)
            msg.setDefaultButton(btn_save)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == btn_save:
                ok = False
                try:
                    ok = bool(self._cb['do_save']())
                except Exception:
                    ok = False
                if ok:
                    try:
                        self._cb['clear_backup']()
                    except Exception:
                        pass
                    self._allow = True
                    self._w.close()
            elif clicked == btn_discard:
                # 不保存：保留最新（含未保存）内容到备份，便于下次恢复
                try:
                    self._cb['write_backup']()
                except Exception:
                    pass
                self._allow = True
                self._w.close()
            # 取消：保持窗口打开
            return True

    return _CloseGuard(window, callbacks)
