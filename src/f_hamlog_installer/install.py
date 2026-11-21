# -*- coding: utf-8 -*-
"""运行安装包。

两种安装包，两种启动方式，不能混：

* **2.x 的 Inno Setup exe** —— 复用 :func:`f_hamlog.check_update.run_installer`
  那条链路（``/SILENT /CLOSEAPPLICATIONS /NORESTART``），与主程序「下载并安装」
  同一个入口。这里额外补两个参数：``/SUPPRESSMSGBOXES`` 让「要重启吗」这类框
  自动取默认值，不然静默安装会停在原地等一个没人看见的确认；``/LOG`` 记一份日志，
  装不上时至少有据可查。
* **1.x 的 msi** —— 用 ``msiexec /i`` 启动。直接把 .msi 丢给 ``Popen`` 会报
  「不是有效的 Win32 应用程序」，因为它得由 Windows Installer 服务来解释。

UAC 都由安装程序自己申请，这里不额外提权（双重提权会被系统拒绝）。只有当
``Popen`` 直接抛「需要提升」（WinError 740）时才退回 ``ShellExecuteEx(runas)``：
说明这个包的清单是 requireAdministrator，交给 shell 去提权是唯一的路。

注意：Inno 的 ``/SILENT`` 只藏「下一步」，进度条仍会显示；装完有「完成」页或
重启提示时照样可能停下来，所以 ``wait=True`` 可能等很久 —— 界面因此把它放进
后台线程等，命令行默认按「等」处理，``--no-wait`` 可以只拉起进程就返回。
"""

import os
import subprocess

from f_hamlog import check_update as cu

# msiexec / Inno 的常见返回码（不是 0 的时候给用户一句人话）
MSI_CODES = {
    1: '用户取消了安装',
    1602: '用户取消了安装',
    1603: '安装失败（常见原因：权限不足或另一个安装正在进行）',
    1618: '另一个安装程序正在运行，稍后再试',
    1638: '已经安装了另一个版本，需要先卸载',
    3010: '安装成功，但需要重启系统才能完成',
    1223: 'UAC 提权被取消，未安装',
}

# 静默安装**不要**加 /SUPPRESSMSGBOXES：Inno 在「已装版本比本包新」时会弹
# 「另一个版本已安装，是否继续」，抑制消息框会按默认值答「否」并直接退出（码 2），
# 用户只看到「什么都没发生」。宁可多一个能看见、能自己点的框。
#
# 也**不要**加 /LOG：Inno 的 ``/LOG=`` 不吃引号，而 subprocess 给含空格的参数
# 会自动加引号 → Inno 把引号当成文件名的一部分，直接弹
# 「Error creating log file: 文件名、目录名或卷标语法不正确」并中止安装。
# 真要排查就走完整向导（``--gui`` / 界面上的「改用安装向导」），错误会显示在
# 安装器自己的界面上。


def is_msi(path):
    return str(path or '').lower().endswith('.msi')


def _inno_args(path):
    return [path, '/SILENT', '/CLOSEAPPLICATIONS', '/NORESTART']


def _runas(path, params, cwd, wait):
    """用 shell 的 runas 动词启动（UAC 由 shell 处理），返回退出码。

    只在 ``Popen`` 因「需要提升」失败时用：Inno 生成的 setup.exe 清单一般是
    asInvoker（自己用 ShellExec 提权），正常走不到这里。留着是为了别人把清单
    改成 requireAdministrator 时，不再只得到一句 WinError 740。
    """
    import ctypes
    from ctypes import wintypes

    class ShellExecuteInfoW(ctypes.Structure):
        _fields_ = [
            ('cbSize', wintypes.DWORD),
            ('fMask', ctypes.c_ulong),
            ('hwnd', wintypes.HWND),
            ('lpVerb', wintypes.LPCWSTR),
            ('lpFile', wintypes.LPCWSTR),
            ('lpParameters', wintypes.LPCWSTR),
            ('lpDirectory', wintypes.LPCWSTR),
            ('nShow', ctypes.c_int),
            ('hInstApp', wintypes.HINSTANCE),
            ('lpIDList', ctypes.c_void_p),
            ('lpClass', wintypes.LPCWSTR),
            ('hkeyClass', wintypes.HKEY),
            ('dwHotKey', wintypes.DWORD),
            ('hIcon', wintypes.HANDLE),
            ('hProcess', wintypes.HANDLE),
        ]

    see_mask_noclose_process = 0x00000040
    info = ShellExecuteInfoW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = see_mask_noclose_process
    info.lpVerb = 'runas'
    info.lpFile = path
    info.lpParameters = params or None
    info.lpDirectory = cwd
    info.nShow = 1                  # SW_SHOWNORMAL
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        raise ctypes.WinError()
    if not info.hProcess:
        return None
    try:
        if not wait:
            return None
        kernel32 = ctypes.windll.kernel32
        kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return int(code.value)
    finally:
        ctypes.windll.kernel32.CloseHandle(info.hProcess)


def run(path, silent=True, wait=True):
    """运行安装包，返回进程退出码（``wait=False`` 时返回 ``None``）。

    ``silent``：exe 用 ``/SILENT``；msi 用 ``/qb``（基本界面 + 进度条）。
    传 ``False`` 走完整向导（要改安装路径、组件时用）。

    ``wait=True`` 会一直等到安装程序退出，**界面必须放在后台线程里调**，
    否则 UAC 一弹窗整个窗口就冻住了。
    """
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError('安装包不存在：%s' % path)

    if is_msi(path):
        args = ['msiexec', '/i', path]
        args += ['/qb', '/norestart'] if silent else ['/norestart']
        proc = subprocess.Popen(args, close_fds=True)
    else:
        try:
            proc = subprocess.Popen(_inno_args(path) if silent else [path],
                                    cwd=os.path.dirname(path) or '.',
                                    close_fds=True)
        except OSError as e:
            if getattr(e, 'winerror', None) != 740:
                raise
            # 清单要求管理员：Popen 直接启动拿不到提权，只能交给 shell
            params = ' '.join(_inno_args(path)[1:]) if silent else ''
            return _runas(path, params, os.path.dirname(path) or '.', wait)

    if not wait:
        return None
    return proc.wait()


def code_text(code):
    """退出码 → 一句说明（认不出就照实报数字）。"""
    if code is None:
        return ''
    if code == 0:
        return '安装完成'
    return MSI_CODES.get(int(code), '安装程序退出码 %s' % code)


# ---------------------------------------------------------------- 已装版本

_UNINSTALL_KEYS = (r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                   r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')


def installed_versions():
    """本机已装的 F HamLog（读注册表卸载项），返回 ``[(名称, 版本, 位置)]``。

    只用来在安装前提醒一句「本机已有 2.9.1」——**不拿它决定装不装**：
    覆盖安装是 Inno 自己的事，这里判断错了也不该挡住用户。
    """
    try:
        import winreg
    except ImportError:             # 非 Windows（理论上不会走到）
        return []
    out = []
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for sub in _UNINSTALL_KEYS:
            try:
                key = winreg.OpenKey(root, sub)
            except OSError:
                continue
            with key:
                try:
                    count = winreg.QueryInfoKey(key)[0]
                except OSError:
                    continue
                for i in range(count):
                    try:
                        child = winreg.OpenKey(key, winreg.EnumKey(key, i))
                    except OSError:
                        continue
                    with child:
                        name = _value(child, 'DisplayName')
                        if not name.startswith('F HamLog'):
                            continue
                        out.append((name, _value(child, 'DisplayVersion'),
                                    _value(child, 'InstallLocation')))
    return out


def _value(key, name):
    try:
        import winreg
        value = winreg.QueryValueEx(key, name)[0]
    except (OSError, ImportError):
        return ''
    return str(value or '')
