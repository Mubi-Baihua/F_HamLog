# -*- coding: utf-8 -*-
"""i18n 冒烟测试（离屏）。

做两件事：
1) 翻译引擎的单元检查（精确匹配 / 模板匹配 / 反向回切 / 不误伤）；
2) 逐个真实构建各窗口（英文模式），扫描控件树，报告
   - 仍然显示中文的界面文字（漏翻）
   - 文案被容器裁掉的控件（英文比中文长）

全程不联网、不写真实数据文件（设置/星历源指向临时副本，其余数据文件先备份后还原）。
结果写 test/__i18n_smoke_out.txt。

坑位备忘（踩过）：
- ``QFileDialog.getOpen/SaveFileName`` / ``QMessageBox.information`` 等**静态**方法
  内部走 C++ 自己的模态循环，改 ``QDialog.exec`` 拦不住 → 必须直接替换静态方法。
- ``os._exit()`` 跳过缓冲区 flush → 日志必须逐行写文件并 flush。
- 卡死时要有 ``faulthandler`` 看门狗，否则只能看到"没了"。
- ``satellite_window`` / ``mutual_window`` 的 ``main()`` 无视传入窗口、自建
  QMainWindow → 必须按「新出现的顶层窗口」定位目标。
"""
import io
import os
import shutil
import sys
import tempfile
import time
import traceback

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import faulthandler  # noqa: E402
import re  # noqa: E402

CJK = re.compile(r'[\u4e00-\u9fff]')
LOG = []
OUT_PATH = os.path.join(ROOT, 'test', '__i18n_smoke_out.txt')
_OUT = io.open(OUT_PATH, 'w', encoding='utf-8', buffering=1)


def log(*a):
    line = ' '.join(str(x) for x in a)
    LOG.append(line)
    try:
        _OUT.write(line + '\n')
        _OUT.flush()
    except Exception:
        pass
    print(line, flush=True)


# 看门狗：任何一步卡超过 90 秒，dump 全部线程栈后退出（日志已落盘，不会丢）
faulthandler.dump_traceback_later(90, exit=True, file=_OUT)

# ----------------------------------------------------------------------
# 真实数据文件：先备份字节，最后还原（绝不动用户数据）
# ----------------------------------------------------------------------
DATA_FILES = ['file/m_xml.txt', 'file/project_backup.fhl', 'file/batch_backup.fhl',
              'file/amateur.tle', 'file/sat_map_markers.txt', 'file/tle_sources.txt',
              'file/main.fhl', 'file/sat_radio_dict.txt', 'file/tqsl_dict.txt']
_BACKUP = {}
TMP = tempfile.mkdtemp(prefix='fhl_i18n_')


def snapshot():
    for p in DATA_FILES:
        if os.path.exists(p):
            with open(p, 'rb') as f:
                _BACKUP[p] = f.read()


def restore():
    for p, b in _BACKUP.items():
        with open(p, 'wb') as f:
            f.write(b)
    log('[数据文件] 已按备份还原 %d 个' % len(_BACKUP))


snapshot()

import i18n            # noqa: E402
import theme           # noqa: E402
import satellite_pred as sp   # noqa: E402

# 设置/星历源 路径指向临时副本，避免污染真实文件
for name, attr in (('m_xml.txt', 'SETTINGS_PATH'),
                   ('tle_sources.txt', 'TLE_SOURCES_PATH')):
    src = os.path.join(ROOT, 'file', name)
    dst = os.path.join(TMP, name)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
    else:
        io.open(dst, 'w', encoding='utf-8').write('{}')
    setattr(sp, attr, dst)

# 临时设置里把语言改成英文：窗口构建时即为英文，验证的是真实的英文界面
try:
    _s = eval(io.open(os.path.join(TMP, 'm_xml.txt'), encoding='utf-8').read())
    if not isinstance(_s, dict):
        _s = {}
except Exception:
    _s = {}
_s['language'] = 'en'
io.open(os.path.join(TMP, 'm_xml.txt'), 'w', encoding='utf-8').write(str(_s))

# ----------------------------------------------------------------------
# 屏蔽一切阻塞/联网/弹窗入口
#
# 注意：QFileDialog.getOpen/SaveFileName 与 QMessageBox.information 等都是**静态**
# 方法，内部自带模态循环，替换 QDialog.exec 是拦不住的 —— 必须替换静态方法本身。
# ----------------------------------------------------------------------
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog,  # noqa: E402
                               QMessageBox)

QApplication.exec = lambda self=None, *a, **k: 0
QDialog.exec = lambda self, *a, **k: QDialog.DialogCode.Rejected
try:
    QDialog.exec_ = QDialog.exec
except Exception:
    pass
QMessageBox.exec = lambda self, *a, **k: QMessageBox.StandardButton.Ok
try:
    QMessageBox.exec_ = QMessageBox.exec
except Exception:
    pass


def _noop_box(*a, **k):
    return QMessageBox.StandardButton.Ok


def _no_question(*a, **k):
    # 一律回答「否」：扫描不触发任何破坏性分支
    return QMessageBox.StandardButton.No


def _no_question_yes(*a, **k):
    return QMessageBox.StandardButton.Yes


QMessageBox.information = _noop_box
QMessageBox.warning = _noop_box
QMessageBox.critical = _noop_box
QMessageBox.about = _noop_box
QMessageBox.question = _no_question

QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ('', ''))
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ''))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ('', ''))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: '')
sys.exit = lambda *a, **k: None

import backup                                     # noqa: E402
backup.is_backup_nonempty = lambda *a, **k: False  # 启动时不要弹「恢复」框

import satellite_auto_update                      # noqa: E402
satellite_auto_update.AutoTleUpdater.start = lambda self: None   # 不联网刷星历

# 语言与 QApplication 由 main.py 的启动器创建（见 main()）
app = None

# 项目窗口用的存档路径（放临时目录，避免弹「新建文件」原生对话框）
SMOKE_FHL = os.path.join(TMP, 'smoke.fhl')

# ----------------------------------------------------------------------
# 1) 翻译引擎
# ----------------------------------------------------------------------
def test_engine():
    log('\n=== 1. 翻译引擎 ===')
    ok = True

    def chk(desc, got, want):
        nonlocal ok
        good = (got == want)
        ok = ok and good
        log('  %s %-34s -> %r' % ('OK ' if good else '!! ', desc, got))
        if not good:
            log('       期望: %r' % want)

    i18n.set_language('zh')
    chk('中文下原样', i18n.tr('保存'), '保存')
    i18n.set_language('en')
    chk('精确匹配', i18n.tr('保存'), 'Save')
    chk('表头', i18n.tr('己方呼号'), 'My call')
    chk('模板-单占位', i18n.tr('已删除 3 条日志。'), 'Deleted 3 log(s).')
    chk('模板-多占位', i18n.tr('选择卫星：最多 250 颗'),
        'Select satellites: at most 250')
    chk('模板-服务端状态', i18n.tr('状态：服务端 192.168.1.5:8000'),
        'Status: server 192.168.1.5:8000')
    chk('模板-显示计数', i18n.tr('显示 12/30 颗'), 'Showing 12/30')
    chk('未收录不误伤', i18n.tr('BI8SQL@outlook.com 这类内容'),
        'BI8SQL@outlook.com 这类内容')
    chk('纯数据不动', i18n.tr('RS-44'), 'RS-44')
    chk('数字不动', i18n.tr('2026-10-02'), '2026-10-02')
    # 逐段翻译后再拼（状态栏计数/观测站信息就是这么拼的）
    chk('分段-计数+已选',
        i18n.tr('{}　已选 {} 颗').format(i18n.tr('共 30 颗'), 3),
        '30 total  Selected 3')
    chk('分段-匹配+已选',
        i18n.tr('{}　已选 {} 颗').format(i18n.tr('匹配 5 / 共 30 颗'), 3),
        'Matched 5 / 30  Selected 3')
    chk('分段-超限',
        i18n.tr('{}　已选 {} 颗').format(i18n.tr('共 30 颗'), 3)
        + i18n.tr('，超过上限 {} 颗').format(250),
        '30 total  Selected 3, over the limit of 250')
    chk('分段-状态栏',
        i18n.tr('{} ｜ 卫星 {} 颗 ｜ 可见过境 {} 次').format(
            i18n.tr('观测站: 纬1.000° 经2.000° 海拔3m')
            + i18n.tr(' ｜ 已选 5 颗'), 30, 2),
        'Station: lat 1.000° lon 2.000° alt 3 m | Selected 5'
        ' | Satellites: 30 | Visible passes: 2')
    chk('地图-全部已选', i18n.tr('全部已选卫星 (0)'),
        'All selected satellites (0)')

    i18n.set_language('zh')
    chk('反向-精确', i18n.tr('Save'), '保存')
    chk('反向-模板', i18n.tr('Deleted 3 log(s).'), '已删除 3 条日志。')
    chk('反向-未收录不动', i18n.tr('Signal report'), 'Signal report')
    # 反向：整条已译好的英文，切回中文应能还原（切语言时控件文字重译走这条路）
    chk('回切-分段状态栏',
        i18n.tr('Station: lat 1.000° lon 2.000° alt 3 m | Selected 5'
                ' | Satellites: 30 | Visible passes: 2'),
        '观测站: 纬1.000° 经2.000° 海拔3m ｜ 已选 5 颗'
        ' ｜ 卫星 30 颗 ｜ 可见过境 2 次')
    chk('回切-计数', i18n.tr('30 total  Selected 3'), '共 30 颗　已选 3 颗')
    chk('回切-超限', i18n.tr('30 total  Selected 3, over the limit of 250'),
        '共 30 颗　已选 3 颗，超过上限 250 颗')
    i18n.set_language('en')     # 后续窗口扫描都按英文
    return ok


# ----------------------------------------------------------------------
# 2) 窗口扫描
# ----------------------------------------------------------------------
SKIP_PAT = re.compile(r'^(https?://|file:|[\\/])|://|\d{4}-\d{2}-\d{2}')


def is_noise(text):
    if SKIP_PAT.search(text):
        return True
    if not CJK.search(text):
        return True
    return False


def _visible(w):
    """只统计用户真正看得见的控件：未显示的对话框/标签页里的隐藏控件不参与，
    它们一旦被 show 出来会被 QEvent.Show 补翻。"""
    try:
        return bool(w.isVisible())
    except Exception:
        return False


def scan(window, label, allow_cjk=(), mode='en'):
    """扫描控件树。

    mode='en'：报告**仍显示中文**的文字（漏翻）；
    mode='zh'：报告**仍是英文**的文字（切回中文后没还原，按词表的英文侧判定）。
    两种模式都报告被容器裁掉的文字。
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QGroupBox,
                                   QLabel, QLineEdit, QListWidget,
                                   QPlainTextEdit, QSpinBox, QTableView,
                                   QTabWidget, QTextEdit, QTreeWidget, QWidget)
    from PySide6.QtGui import QAction

    en2zh = i18n.catalog().en2zh

    def is_bad(text):
        if mode == 'zh':
            return text in en2zh
        return bool(CJK.search(text))

    leftover, clipped, squashed = [], [], []
    all_widgets = [window] + window.findChildren(QWidget)
    widgets = [w for w in all_widgets if _visible(w)]
    hidden = len(all_widgets) - len(widgets)
    targets = []
    for w in widgets:
        if isinstance(w, QGroupBox):
            targets.append(('group', w, w.title()))
        elif isinstance(w, (QLabel, QAbstractButton)):
            targets.append(('text', w, w.text()))
        if isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit)):
            targets.append(('ph', w, w.placeholderText()))
        try:
            if w.windowTitle():
                targets.append(('title', w, w.windowTitle()))
        except Exception:
            pass
        if isinstance(w, QComboBox):
            for i in range(w.count()):
                targets.append(('item', w, w.itemText(i)))
        elif isinstance(w, QListWidget):
            for i in range(w.count()):
                targets.append(('item', w, w.item(i).text()))
        elif isinstance(w, QTableView):
            m = w.model()
            if m is not None:
                for i in range(m.columnCount()):
                    targets.append(('head', w, m.headerData(
                        i, Qt.Orientation.Horizontal,
                        Qt.ItemDataRole.DisplayRole) or ''))
                if m.rowCount() <= 64:
                    for i in range(m.rowCount()):
                        targets.append(('vhead', w, m.headerData(
                            i, Qt.Orientation.Vertical,
                            Qt.ItemDataRole.DisplayRole) or ''))
    for a in window.findChildren(QAction):
        targets.append(('action', a, a.text()))

    for kind, w, text in targets:
        if not text or not text.strip() or text in allow_cjk:
            continue
        if mode == 'en' and is_noise(text):
            continue
        if not is_bad(text):
            continue
        leftover.append('%s: %r' % (kind, text))

    # 裁切检查：单行且不折行的文字，行宽不得超过控件宽度
    for w in widgets:
        if isinstance(w, QGroupBox):
            text = w.title()
        elif isinstance(w, (QLabel, QAbstractButton)):
            text = w.text()
        else:
            continue
        if not text or not text.strip() or SKIP_PAT.search(text):
            continue
        try:
            if w.wordWrap():
                continue
        except Exception:
            pass
        need = w.fontMetrics().horizontalAdvance(text)
        if need > w.width() + 2:
            clipped.append('%s(%dx%d) 需要 %dpx: %r'
                           % (type(w).__name__, w.width(), w.height(), need, text))

    # 竖向压扁检查：控件被压得比自身最小高度还矮（说明整体高度不够放新行）
    for w in widgets:
        if isinstance(w, (QGroupBox, QLabel, QAbstractButton,
                          QLineEdit, QComboBox, QSpinBox)):
            need_h = w.minimumSizeHint().height()
            if need_h > w.height() + 1:
                squashed.append('%s(%dx%d) 需要高 %dpx'
                                % (type(w).__name__, w.width(), w.height(), need_h))

    log('\n--- %s ---' % label)
    if hidden:
        log('  [已忽略] %d 个不可见控件（未显示的对话框/隐藏标签页）' % hidden)
    tag = '仍为中文' if mode == 'en' else '仍为英文'
    if leftover:
        log('  [%s] %d 处' % (tag, len(leftover)))
        for s in sorted(set(leftover))[:40]:
            log('     ' + s)
    else:
        log('  [%s] 无' % tag)
    if clipped:
        log('  [被裁切] %d 处' % len(clipped))
        for s in sorted(set(clipped))[:40]:
            log('     ' + s)
    else:
        log('  [被裁切] 无')
    if squashed:
        log('  [被压扁] %d 处' % len(squashed))
        for s in sorted(set(squashed))[:20]:
            log('     ' + s)
    else:
        log('  [被压扁] 无')
    return leftover, clipped, squashed


def _top_levels():
    return {id(w) for w in app.topLevelWidgets()}


def build_window(label, fn, allow_cjk=(), expect_new=False):
    """构建一个窗口（不扫描），返回 (label, 窗口, allow_cjk)；失败返回 None。

    expect_new=True 表示 fn 会自建 QMainWindow（无视传入的窗口），
    此时按「新出现的顶层窗口」定位目标。
    """
    from PySide6.QtWidgets import QMainWindow, QWidget
    before = _top_levels()
    t0 = time.time()
    try:
        win = QMainWindow()
        fn(win)
        win.show()
        app.processEvents()
        app.processEvents()
        target = win
        if expect_new:
            news = [w for w in app.topLevelWidgets()
                    if id(w) not in before and w is not win and w.isVisible()]
            if news:
                target = max(news, key=lambda w: len(w.findChildren(QWidget)))
        log('[构建] %s: %.1fs' % (label, time.time() - t0))
        return (label, target, allow_cjk)
    except Exception:
        log('\n--- %s ---' % label)
        log('  !! 构建失败：')
        for line in traceback.format_exc().strip().splitlines()[-6:]:
            log('     ' + line)
        return None


def scan_all(built, phase, mode):
    log('\n########## 阶段：%s（当前语言=%s） ##########'
        % (phase, i18n.current_language()))
    left, clip, squash = [], [], []
    for label, win, allow in built:
        app.processEvents()
        log('  尺寸 %-42s %dx%d' % (label, win.width(), win.height()))
        l, c, s = scan(win, '%s ｜ %s' % (phase, label), allow, mode=mode)
        left += l
        clip += c
        squash += s
    return left, clip, squash


def _language_box():
    """找到「设置」窗口里那个语言下拉框（数据为 zh / en）。"""
    from PySide6.QtWidgets import QComboBox
    for w in app.allWidgets():
        if isinstance(w, QComboBox):
            data = [w.itemData(i) for i in range(w.count())]
            if 'zh' in data and 'en' in data:
                return w
    return None


def switch_language_via_ui(lang):
    """走真实代码路径切语言：改「设置」里的下拉框（会触发 on_language_changed）。"""
    box = _language_box()
    if box is None:
        log('  [注意] 未找到语言下拉框，退回 i18n.set_language()')
        i18n.set_language(lang)
    else:
        idx = box.findData(lang)
        if idx >= 0:
            box.setCurrentIndex(idx)
        log('  切换语言 → %s（经设置窗口下拉框）' % i18n.current_language())
    for _ in range(3):
        app.processEvents()


def main():
    global app
    ok = test_engine()

    built = []

    # ---- 启动器 main.py：它会自建 QApplication，所以必须最先跑 ----
    import main as launcher
    launcher._cleanup_remote_rooms = lambda *a, **k: None   # 不删 file/remote_rooms
    sp.migrate_legacy_sat_data = lambda *a, **k: None       # 不改写转发器/TQSL 表
    sp.fetch_amateur_tle = lambda *a, **k: ''               # 不联网取星历
    try:
        launcher.main()          # 内部 exec() 已被屏蔽，建完窗即返回
    except Exception:
        log('\n--- 启动器 main.py ---')
        log('  !! 构建失败：')
        for line in traceback.format_exc().strip().splitlines()[-6:]:
            log('     ' + line)
    else:
        app = QApplication.instance()
        log('\n[启动器] 语言=%s' % i18n.current_language())
        wins = [w for w in app.topLevelWidgets()
                if w.windowTitle().startswith('F HamLog 2')]
        if wins:
            wins[0].show()
            app.processEvents()
            built.append(('启动器 main.py', wins[0], ()))
        else:
            log('\n--- 启动器 main.py --- 未找到窗口')

    def add(label, fn, allow_cjk=(), expect_new=False):
        item = build_window(label, fn, allow_cjk, expect_new)
        if item is not None:
            built.append(item)

    # 设置窗口（语言名用母语写法，故意不翻）
    import set as setmod
    add('设置 set.py', setmod.main, allow_cjk=('简体中文',))

    # 星历数据源窗口（延迟探测线程屏蔽）
    import tle_source_window as tsw
    tsw.DelayProbeWorker.start = lambda self: None
    add('星历数据源 tle_source_window.py', tsw.main)

    # 批量记录
    import batch_project as bp
    add('批量记录 batch_project.py', bp.main)

    # 插件设置
    import pack_set as ps
    add('插件设置 pack_set.py', ps.main)

    # 通联日志主窗口（不联网、不写盘；显式给存档路径以跳过原生「新建文件」对话框）
    import project as pj
    add('通联日志 project.py',
        lambda win: pj.main(win, filee=[], save_path=SMOKE_FHL))

    # 卫星过境窗口（自建 QMainWindow）
    import satellite_window as sw
    add('卫星过境 satellite_window.py', lambda w: sw.main(None), expect_new=True)

    # 通联预测窗口（自建 QMainWindow）
    import mutual_window as mw
    add('通联预测 mutual_window.py', lambda w: mw.main(None), expect_new=True)

    # 卫星地图窗口（自建 QMainWindow；轨迹线程屏蔽）
    import satellite_map_window as smw
    smw.TrackWorker.start = lambda self: None
    add('卫星地图 satellite_map_window.py',
        lambda w: smw.open_map(None, []), expect_new=True)

    total_left, total_clip, total_squash = [], [], []

    # 阶段 1：以英文构建（临时设置里 language=en）
    l, c, s = scan_all(built, '英文界面', 'en')
    total_left += l
    total_clip += c
    total_squash += s

    # 阶段 2/3：不重建窗口，直接切语言，验证「原地重译、不丢数据、不裁切」
    switch_language_via_ui('zh')
    l, c, s = scan_all(built, '英文→中文（即时刷新）', 'zh')
    total_left += l
    total_clip += c
    total_squash += s

    switch_language_via_ui('en')
    l, c, s = scan_all(built, '中文→英文（即时刷新）', 'en')
    total_left += l
    total_clip += c
    total_squash += s

    log('\n========== 汇总 ==========')
    log('引擎单元检查: %s' % ('通过' if ok else '失败'))
    log('构建窗口数: %d' % len(built))
    log('漏翻/未还原: %d 处（去重）' % len(set(total_left)))
    log('横向被裁切: %d 处（去重）' % len(set(total_clip)))
    log('竖向被压扁: %d 处（去重）' % len(set(total_squash)))
    return 0


if __name__ == '__main__':
    code = 1
    try:
        code = main()
    except Exception:
        log('!! 主流程异常：')
        for line in traceback.format_exc().strip().splitlines()[-12:]:
            log('   ' + line)
    finally:
        restore()
        try:
            _OUT.close()
        except Exception:
            pass
        shutil.rmtree(TMP, ignore_errors=True)
    os._exit(code)
