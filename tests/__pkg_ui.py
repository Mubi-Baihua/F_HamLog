"""打包版界面探针（本机调试用）：DPI 感知 / 按 PID 取窗口 / 截图 / 点击 / 悬停。

锁屏或无桌面合成时 ImageGrab 全黑，故截图走 PrintWindow(PW_RENDERFULLCONTENT)。
只在需要肉眼级别验证打包产物观感时使用，不参与回归。
"""

import ctypes
import ctypes.wintypes as wt
import sys
import time

from PIL import Image

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)

try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # PER_MONITOR_AWARE_V2
except Exception:
    pass

user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, wt.INT, wt.INT, wt.INT, wt.INT, wt.UINT]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wt.DWORD), ('biWidth', wt.LONG), ('biHeight', wt.LONG),
                ('biPlanes', wt.WORD), ('biBitCount', wt.WORD),
                ('biCompression', wt.DWORD), ('biSizeImage', wt.DWORD),
                ('biXPelsPerMeter', wt.LONG), ('biYPelsPerMeter', wt.LONG),
                ('biClrUsed', wt.DWORD), ('biClrImportant', wt.DWORD)]


def windows(pid=None, visible_only=True):
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _cb(hwnd, _lparam):
        n = user32.GetWindowTextLengthW(hwnd)
        if not n:
            return True
        if visible_only and not user32.IsWindowVisible(hwnd):
            return True
        owner = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if pid is not None and owner.value != pid:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        r = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        out.append((hwnd, buf.value, (r.left, r.top, r.right, r.bottom), owner.value))
        return True

    user32.EnumWindows(_cb, 0)
    return out


def find(title_part, pid=None):
    for hwnd, title, rect, owner in windows(pid):
        if title_part.lower() in title.lower():
            return hwnd, title, rect, owner
    return None, None, None, None


def capture(hwnd, out):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    hdc_screen = user32.GetDC(0)
    hdc = gdi32.CreateCompatibleDC(hdc_screen)
    bmp = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc, bmp)
    user32.PrintWindow(hwnd, hdc, 2)
    bi = BITMAPINFOHEADER()
    bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.biWidth, bi.biHeight = w, -h
    bi.biPlanes, bi.biBitCount = 1, 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1).convert('RGB').save(out)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(hdc)
    user32.ReleaseDC(0, hdc_screen)
    return out, (w, h)


def move(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.12)


def click(x, y):
    move(x, y)
    user32.mouse_event(0x0002, 0, 0, 0, 0)      # LEFTDOWN
    time.sleep(0.05)
    user32.mouse_event(0x0004, 0, 0, 0, 0)      # LEFTUP
    time.sleep(0.4)


def main(argv):
    cmd = argv[1]
    if cmd == 'list':
        for hwnd, title, rect, owner in windows():
            print('%08x pid=%-6d %-40s %s' % (hwnd, owner, title[:40], rect))
    elif cmd == 'find':
        print(find(argv[2], int(argv[3]) if len(argv) > 3 else None))
    elif cmd == 'move':
        hwnd = int(argv[2], 16)
        user32.SetWindowPos(hwnd, 0, int(argv[3]), int(argv[4]), 0, 0, 0x0001 | 0x0004)
        time.sleep(0.3)
        print(find_by_hwnd := [w for w in windows() if w[0] == hwnd])
    elif cmd == 'cap':
        print(capture(int(argv[2], 16), argv[3]))
    elif cmd == 'click':
        click(int(argv[2]), int(argv[3]))
    elif cmd == 'hover':
        move(int(argv[2]), int(argv[3]))
    else:
        raise SystemExit('unknown ' + cmd)


if __name__ == '__main__':
    main(sys.argv)
