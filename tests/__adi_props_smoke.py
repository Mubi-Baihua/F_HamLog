# -*- coding: utf-8 -*-
"""打开 .adi / .fhl / .fhla 时，「项目属性」「自定义日志字段」「加密」三处的话术分流。

用户要求（原话）：
  1) 悬浮提示不带感叹号，**也不带句末句号**；
  2) 自定义字段保存后只提示「已保存字段更改」；
  3) 不管在哪个文件窗口，``.fhl`` 和 ``.fhla`` 都要分开说——准确说是**按真实格式分开**：
     ADI 文件别再被甩 .fhl 的「纯记录格式」那句话；
  4) ADI 的「项目属性」显示模式**和 .fhl 一样**（同样是「这个格式没有属性」的提示版式），
     只是话术换成 ADI 的；
  5) ADI 也要有「加密此项目」入口，点了明确提示不支持。

离屏运行；项目备份路径重定向到临时目录，不触碰 file/ 里的用户数据。
用法：python tests/__adi_props_smoke.py
"""
import os
import re
import shutil
import sys
import tempfile
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(PROJECT_DIR, 'src'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QAction                          # noqa: E402
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox  # noqa: E402

from f_hamlog import backup                                # noqa: E402
from f_hamlog import export_adi                            # noqa: E402
from f_hamlog import i18n                                  # noqa: E402
from f_hamlog import project as pj                         # noqa: E402
from f_hamlog import toast_tip                             # noqa: E402

TMP = tempfile.mkdtemp(prefix='adi_props_')
backup.PROJECT_BACKUP = os.path.join(TMP, 'backup.fhl')

app = QApplication(sys.argv)

PASS = []


def ok(name, cond, extra=''):
    PASS.append(bool(cond))
    print('[%s] %s%s' % ('PASS' if cond else 'FAIL', name, ('  <- ' + extra) if extra else ''),
          flush=True)


def pump(n=6):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


def recs(n=3):
    out = []
    for i in range(n):
        out.append({'date': '2026-03-%02d' % (i + 1), 'time': '08:0%d' % i,
                    'm_call': 'BG5ABC', 'o_call': 'BI8SQL%d' % i,
                    'freq': '14.074', 'mode': 'FT8', 'notes': ''})
    return out


def no_fhl(text):
    """正文里不含 .fhl（**允许** .fhla：建议里会提到「另存为 .fhla 项目」）。"""
    return re.search(r'\.fhl(?!a)', text or '') is None


def find_action(win, *texts):
    return next((a for a in win.findChildren(QAction) if a.text() in texts), None)


def popup_text(win, action):
    """触发菜单项，返回弹窗正文（QMessageBox 静态方法按 Qt 行为必须整体替换）。"""
    if action is None:
        return None
    captured = {}
    orig = QMessageBox.information
    QMessageBox.information = staticmethod(
        lambda parent, title, text, *a, **k: (captured.update(t=text), QMessageBox.Ok)[1])
    try:
        action.trigger()
        pump(3)
    finally:
        QMessageBox.information = orig
    return captured.get('t')


# ==========================================================================
# A. 提示文案即纯函数：三种格式各自说自己的话
# ==========================================================================
print('--- A format_reject_text ---', flush=True)
ADI = os.path.join(TMP, 'a.adi')
export_adi.write_adif_file(ADI, recs(3))
FHL = os.path.join(TMP, 'b.fhl')
pj.fhl_rw.write_fhl_file(FHL, recs(2))

t_adi_prop = pj.format_reject_text(ADI, '属性')
t_adi_cf = pj.format_reject_text(ADI, '自定义字段')
t_fhl_prop = pj.format_reject_text(FHL, '属性')
t_fhl_cf = pj.format_reject_text(FHL, '自定义字段')
t_new = pj.format_reject_text('', '属性')
t_new_cf = pj.format_reject_text('', '自定义字段')

ok('A1 ADI 属性：说 ADI，不提 .fhl',
   'ADI 是通用日志交换格式' in t_adi_prop and no_fhl(t_adi_prop), t_adi_prop.replace('\n', ' | '))
ok('A2 ADI 自定义字段：说 ADI，不提 .fhl',
   '不含自定义日志字段' in t_adi_cf and no_fhl(t_adi_cf), t_adi_cf.replace('\n', ' | '))
ok('A3 .fhl 属性：仍说「纯记录格式」，不提 ADI',
   '纯记录格式' in t_fhl_prop and 'ADI' not in t_fhl_prop, t_fhl_prop.replace('\n', ' | '))
ok('A4 .fhl 自定义字段：仍说「纯记录格式」，不提 ADI',
   '纯记录格式' in t_fhl_cf and 'ADI' not in t_fhl_cf, t_fhl_cf.replace('\n', ' | '))
ok('A5 未保存：让用户先保存，不提 .fhl / ADI',
   '当前项目还没有保存到磁盘' in t_new and no_fhl(t_new) and 'ADI' not in t_new,
   t_new.replace('\n', ' | '))
ok('A6 未保存 + 自定义字段：提到自定义日志字段',
   '自定义日志字段' in t_new_cf and no_fhl(t_new_cf), t_new_cf.replace('\n', ' | '))
ok('A7 三处都给出「另存为 .fhla」这条可执行的去处',
   all('.fhla' in t for t in (t_adi_prop, t_adi_cf, t_fhl_prop, t_fhl_cf)))
ok('A8 提示文案里没有感叹号', not any('！' in t or '!' in t
                                  for t in (t_adi_prop, t_adi_cf, t_fhl_prop, t_fhl_cf)))

# ==========================================================================
# B. 真实窗口：.adi 的「项目属性」= 和 .fhl 一样的提示版式 + ADI 话术
# ==========================================================================
print('--- B 打开 .adi ------------', flush=True)
data, key, meta = pj.read_project_file(ADI)
ok('B1 .adi 读出记录、无密钥、无属性块', len(data) == 3 and key is None and meta is None,
   '%d / %r / %r' % (len(data), key, meta))

win = QMainWindow()
pj.main(win, filee=data, save_path=ADI)
win.show()
pump()

text_prop = popup_text(win, find_action(win, '项目属性', 'Project properties'))
ok('B2 属性弹窗用的是 ADI 话术（不是 .fhl 那句）',
   'ADI 是通用日志交换格式' in text_prop and no_fhl(text_prop),
   (text_prop or '').replace('\n', ' | ')[:200])
ok('B3 显示模式与 .fhl 一致：不摆「记录条数 / 文件大小 / 修改时间」信息卡',
   not any(k in text_prop for k in ('记录条数', '文件大小', '修改时间')))
ok('B4 仍有「需要…时，可用『另存为』保存为 .fhla 项目」这条建议',
   '另存为' in text_prop and '.fhla' in text_prop)
ok('B5 结尾是句号，不是感叹号', '！' not in text_prop and '!' not in text_prop)

text_cf = popup_text(win, find_action(win, '自定义日志字段', 'Custom log fields'))
ok('B6 自定义日志字段：ADI 话术（截图里的 .fhl 提示已消失）',
   '不含自定义日志字段' in text_cf and no_fhl(text_cf),
   (text_cf or '').replace('\n', ' | ')[:200])

# 加密入口：有菜单，点了明确说不支持，且不会真的把 key 设上
aes = find_action(win, '加密此项目', 'Encrypt this project')
ok('B7 .adi 也有「加密此项目」入口', aes is not None)
text_aes = popup_text(win, aes)
ok('B8 点「加密此项目」→ 提示 ADI 不支持加密',
   '不支持加密' in text_aes and no_fhl(text_aes),
   (text_aes or '').replace('\n', ' | ')[:200])
ok('B9 点完没有真的加密（key 仍为空、文件仍可当文本读）',
   getattr(win, '_key', None) is None and pj.detect_encrypted(ADI) is False)

# 英文界面：同样按格式分开（同一窗口再点，文案在点击时按当前语言生成）
i18n.set_language('en')
pump(3)
text_prop_en = popup_text(win, find_action(win, '项目属性', 'Project properties'))
text_cf_en = popup_text(win, find_action(win, '自定义日志字段', 'Custom log fields'))
ok('B10 英文 ADI 属性文案已翻译',
   'ADI is a generic log interchange format' in text_prop_en, (text_prop_en or '')[:120])
ok('B11 英文里也没 .fhl / 感叹号',
   no_fhl(text_prop_en) and '!' not in text_prop_en and no_fhl(text_cf_en))
i18n.set_language('zh')
pump(2)

# ==========================================================================
# C. 回归：.fhl / .fhla 没被改坏
# ==========================================================================
print('--- C .fhl / .fhla 回归 ---', flush=True)
win2 = QMainWindow()
pj.main(win2, filee=recs(2), save_path=FHL)
win2.show()
pump()
text_fhl = popup_text(win2, find_action(win2, '项目属性', 'Project properties'))
ok('C1 .fhl 属性：仍是「不支持的格式 + 纯记录格式」',
   '不支持的格式' in text_fhl and '纯记录格式' in text_fhl,
   (text_fhl or '').replace('\n', ' | ')[:160])
ok('C2 .fhl 属性不提 ADI', 'ADI' not in text_fhl)
text_fhl_cf = popup_text(win2, find_action(win2, '自定义日志字段', 'Custom log fields'))
ok('C3 .fhl 自定义字段：仍是「纯记录格式，不含自定义日志字段」',
   '纯记录格式' in text_fhl_cf and '不含自定义日志字段' in text_fhl_cf,
   (text_fhl_cf or '').replace('\n', ' | ')[:160])

FHLA = os.path.join(TMP, 'c.fhla')
pj.write_fhla_file(FHLA, recs(2), meta=pj.normalize_meta({}), editor='BG5ABC')
_read, _key, _meta = pj.read_project_file(FHLA)
win3 = QMainWindow()
pj.main(win3, filee=_read, save_path=FHLA, key_=_key, fhla_meta=_meta)
win3.show()
pump()
text_fhla = popup_text(win3, find_action(win3, '项目属性', 'Project properties'))
ok('C4 .fhla 仍展示属性块（有属性行，不是提示）',
   '上一次编辑的人：BG5ABC' in text_fhla and '格式版本：' in text_fhla,
   (text_fhla or '').replace('\n', ' | ')[:200])
ok('C5 .fhla 不会被「没有属性」的提示顶掉',
   'ADI' not in text_fhla and '纯记录格式' not in text_fhla)

# ==========================================================================
# D. 悬浮提示：不带感叹号、不带句末句号；自定义字段只提示「已保存字段更改」
# ==========================================================================
print('--- D 悬浮提示 ---', flush=True)
ok('D1 「已保存成功！」→「已保存成功」', toast_tip.strip_bang('已保存成功！') == '已保存成功')
ok('D2 「已删除 3 条日志。」→ 无句末句号', toast_tip.strip_bang('已删除 3 条日志。') == '已删除 3 条日志')
ok('D3 英文「Saved!」→「Saved」', toast_tip.strip_bang('Saved!') == 'Saved')
ok('D4 句中/文件名里的点不误伤',
   toast_tip.strip_bang('已迁移为 main.fhla') == '已迁移为 main.fhla'
   and toast_tip.strip_bang('已保存到 t.adi') == '已保存到 t.adi')
ok('D5 幂等', toast_tip.strip_bang(toast_tip.strip_bang('已保存字段更改。')) == '已保存字段更改')

# 真实弹一个：label 上就是去掉句号后的文案
t = toast_tip.show_toast('已保存字段更改。', win)
pump(2)
ok('D6 实际显示的提示不带句末句号', t._label.text() == '已保存字段更改', t._label.text())
t.close()
pump(2)

# 源码里自定义字段保存后的提示只剩这一句（不再报条数）
src = open(os.path.join(PROJECT_DIR, 'src', 'f_hamlog', 'project.py'), encoding='utf-8').read()
ok('D7 自定义字段保存只提示「已保存字段更改」',
   "show_toast(i18n.tr('已保存字段更改')" in src
   and '个自定义字段。' not in src)
i18n.set_language('en')
ok('D8 词表里这句能翻', i18n.tr('已保存字段更改') == 'Field changes saved',
   i18n.tr('已保存字段更改'))
i18n.set_language('zh')

# ==========================================================================
# E. 备份文件：只有真有未保存内容时才存在；0 字节空壳一律不留
# ==========================================================================
print('--- E 备份文件 ---', flush=True)
stale = os.path.join(TMP, 'project_backup_deadbeef0000.fhl')
open(stale, 'w', encoding='utf-8').close()          # 造一个旧版本留下的 0 字节空壳
ok('E1 0 字节空壳被顺手清掉（list_project_backups）',
   stale not in backup.list_project_backups() and not os.path.exists(stale))

ghost = os.path.join(TMP, 'project_backup_ghost000000.fhl')
backup.clear_backup(ghost)
ok('E2 clear_backup 不会凭空建出备份文件', not os.path.exists(ghost))

backup.write_backup(ghost, recs(2))
ok('E3 真有未保存内容时才写备份', backup.is_backup_nonempty(ghost)
   and ghost in backup.list_project_backups())
backup.write_backup(ghost, [])
ok('E4 内容清空 → 文件被删除（不是留 0 字节）', not os.path.exists(ghost))

ok('E5 打开 / 操作过的窗口没留下任何备份文件', backup.list_project_backups() == [],
   str(backup.list_project_backups()))

# ==========================================================================
print('', flush=True)
print('通过 %d / %d' % (sum(PASS), len(PASS)), flush=True)
print('RESULT=%s' % ('ALL PASS' if all(PASS) else 'HAS FAIL'), flush=True)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(0 if all(PASS) else 1)
