# -*- coding: utf-8 -*-
"""冒烟：卫星数据一律以「卫星编号」为键（选择卫星 / 两个 dict / 启动静默迁移）。

覆盖：
  1. 编号 ⇄ 名称解析：长名、短名（括号内）、全角、前导 0、Alpha-5/纯数字直通；
  2. normalize_sat_keys：混合「名称 + 编号」列表折成去重编号列表；
  3. SatelliteSelectDialog：传编号表时 get_selected() 返回编号、按编号回填勾选；
     不传编号表时行为与旧版一致（键 = 名称）；
  4. DictEditorDialog：文件里存编号 → 界面显示卫星名；界面填名称 → 保存为编号；
     解析不出的名称按原文保存（不丢数据）；
  5. lookup_transponder / tqsl_sat_name / has_tqsl_mapping：编号键优先，旧名称键仍兼容；
  6. migrate_legacy_sat_data：把 m_xml.txt 的 sat_sats / sat_radio_dict.txt /
     tqsl_dict.txt 由名称升级为编号，解析不出的原样跳过，重复执行幂等。

全部在临时目录里用「假星历」跑，绝不触碰真实数据文件。
"""
import os
import sys
import shutil
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
os.chdir(PROJECT_DIR)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from f_hamlog import satellite_pred as sp
from f_hamlog import satellite_window as sw

FAILS = []
OKS = [0]


def check(cond, msg):
    if cond:
        OKS[0] += 1
    else:
        FAILS.append(msg)
        print('  [FAIL] ' + msg)


def show(msg):
    print('  [ ok ] ' + msg)


# ---------------------------------------------------------------------------
# 假星历：3 颗星，含「长名 + 括号内短名」结构
# ---------------------------------------------------------------------------
FAKE_TLE = """\
ASRTU-1 (RS64S/BJ2CR)
1 61781U 24199AY  26268.59897373  .00000123  00000-0  10000-3 0  9999
2 61781  97.2827 136.3685 0012345  90.0000 270.0000 15.20000000    10
SAUDISAT-1C (SO-50)
1 27607U 02058C   26268.50000000  .00000123  00000-0  10000-3 0  9999
2 27607  64.5550 200.0000 0050000 270.0000  90.0000 14.70000000    10
ISS (ZARYA)
1 25544U 98067A   26268.50000000  .00000123  00000-0  10000-3 0  9999
2 25544  51.6400 100.0000 0005000  90.0000 270.0000 15.50000000    10
"""

TMP = tempfile.mkdtemp(prefix='fhl_satnum_')
FAKE_TLE_PATH = os.path.join(TMP, 'amateur.tle')
with open(FAKE_TLE_PATH, 'w', encoding='utf-8') as f:
    f.write(FAKE_TLE)

# 把星历指向假文件（含 satellite_window 里供补全用的那份常量）
_orig = {
    'TLE_CACHE': sp.TLE_CACHE,
    'SETTINGS_PATH': sp.SETTINGS_PATH,
    'SAT_RADIO_DICT_PATH': sp.SAT_RADIO_DICT_PATH,
    'TQSL_DICT_PATH': sp.TQSL_DICT_PATH,
    'sw_TLE_CACHE': sw.TLE_CACHE,
}
sp.TLE_CACHE = FAKE_TLE_PATH
sw.TLE_CACHE = FAKE_TLE_PATH
sp._sat_index_cache['key'] = None       # 丢掉真实星历的缓存索引


def reset_index():
    sp._sat_index_cache['key'] = None


print('1) 编号 ⇄ 名称解析')

check(sp.sat_number_of('ASRTU-1 (RS64S/BJ2CR)') == '61781', '长名 → 编号')
check(sp.sat_number_of('so-50') == '27607', '括号内短名（小写）→ 编号')
check(sp.sat_number_of('ASRTU-1 (AO-123)') == '', '查不到的名称 → 空串（不冒充编号）')
check(sp.sat_number_of('061781') == '61781', '前导 0 的编号等价')
check(sp.sat_number_of('６１７８１') == '61781', '全角编号等价')
check(sp.sat_number_of('ＡＳＲＴＵ－１') == '61781', '全角名称等价')
check(sp.sat_display_name('61781') == 'ASRTU-1 (RS64S/BJ2CR)', '编号 → 当前星历里的名称')
check(sp.sat_display_name('061781') == 'ASRTU-1 (RS64S/BJ2CR)', '前导 0 的编号同样能显示名称')
check(sp.sat_display_name('99999') == '99999', '星历里没有的编号 → 原样显示，不空白')
check(sp.sat_name_aliases('ISS (ZARYA)')[:3] == ['ISSZARYA', 'ZARYA', 'ISS'],
      '别名：全名 / 括号内短名 / 去括号部分')
show('编号 ⇄ 名称解析 9 项')

print('2) normalize_sat_keys')
check(sp.normalize_sat_keys(['ASRTU-1 (RS64S/BJ2CR)', '61781', 'SO-50']) == ['61781', '27607'],
      '混合名称+编号 → 去重编号（保持首次出现顺序）')
check(sp.normalize_sat_keys([]) == [], '空列表安全')
check(sp.normalize_sat_keys([None, '', '  ']) == [], '空值被丢弃')
check(sp.normalize_sat_keys(['AO-123-OLD']) == ['AO-123-OLD'], '解析不出的原样保留')
show('normalize_sat_keys 4 项')

print('3) SatelliteSelectDialog：键 = 编号')
names = [n for n, _s in sp.parse_tle_text(FAKE_TLE)]
check(names == ['ASRTU-1 (RS64S/BJ2CR)', 'SAUDISAT-1C (SO-50)', 'ISS (ZARYA)'], '假星历解析出 3 颗')
satnums = {n: sp.norad_key(str(getattr(s, 'satnum', '')))
           for n, s in sp.parse_tle_text(FAKE_TLE)}

dlg = sw.SatelliteSelectDialog(None, names, {'27607'}, satnums)
check(dlg.get_selected() == {'27607'}, '按编号回填勾选 + get_selected 返回编号')
check(dlg.items['SAUDISAT-1C (SO-50)'].checkState().name == 'Checked', '编号对应的行被勾选')
check(dlg.items['ISS (ZARYA)'].checkState().name == 'Unchecked', '未选中的行保持未勾选')

# 搜索仍按名称 / 编号（名称搜索不因键改成编号而失效）
dlg.search_edit.setText('asrtu')
app.processEvents()
check([dlg._row_names[r] for r in range(dlg.list_widget.count())
       if not dlg.list_widget.isRowHidden(r)] == ['ASRTU-1 (RS64S/BJ2CR)'],
      '按名称搜索照常可用')

# 不传编号表 → 键退回名称（旧调用零改动）
dlg2 = sw.SatelliteSelectDialog(None, ['DUMMY-1', 'DUMMY-2'], {'DUMMY-2'})
check(dlg2.get_selected() == {'DUMMY-2'}, '不传编号表时 get_selected 仍返回名称（向后兼容）')
show('SatelliteSelectDialog 6 项')

print('4) DictEditorDialog：显示名称、保存编号')


class _FakeBox(object):
    """顶掉模态提示框，避免 offscreen 下卡死。"""
    information = staticmethod(lambda *a, **k: None)
    warning = staticmethod(lambda *a, **k: None)


_orig_box = sw.QMessageBox
sw.QMessageBox = _FakeBox

radio_path = os.path.join(TMP, 'sat_radio_dict.txt')
with open(radio_path, 'w', encoding='utf-8') as f:
    f.write('# 卫星转发器表\n'
            '# 格式：卫星名=下行频率,上行频率,模式\n'
            '61781=435.4,145.85,FM\n'
            'SO-50=436.795,145.85,FM\n'
            'AO-123-OLD=100.0,200.0,FM\n')

dedlg = sw.DictEditorDialog(None, '编辑卫星转发器', radio_path,
                            ['卫星名', '下行频率', '上行频率', '模式'],
                            value_delimiter=',')
shown = [(dedlg.table.item(i, 0).text() if dedlg.table.item(i, 0) else '')
         for i in range(dedlg.table.rowCount())]
check(shown == ['ASRTU-1 (RS64S/BJ2CR)', 'SAUDISAT-1C (SO-50)', 'AO-123-OLD'],
      '打开时把编号显示成当前星历的卫星名（含短名 → 长名），查不到的保持原样')

# 界面里改成一个名称（模拟用户输入），再保存 → 应写成编号
dedlg.table.setItem(2, 0, sw.QTableWidgetItem('ISS (ZARYA)'))
check(len(dedlg.findChildren(sw.QPushButton)) > 0, '对话框可用')

import PySide6.QtWidgets as _qtw
buttons = {b.text(): b for b in dedlg.findChildren(_qtw.QPushButton)}
check('使用记事本编辑' not in buttons, '已移除「使用记事本编辑」按钮')
buttons['保存'].click()
app.processEvents()

saved = sp._read_text(radio_path)
data_lines = [ln for ln in saved.splitlines() if ln and not ln.startswith('#')]
check(data_lines[0] == '61781=435.4,145.85,FM', '保存后键为编号（原编号保持）')
check(data_lines[1] == '27607=436.795,145.85,FM', '短名 SO-50 → 编号 27607')
check(data_lines[2] == '25544=100.0,200.0,FM', '界面填的名称 → 编号 25544')
check(saved.splitlines()[0].startswith('#'), '注释行原样保留')
check(len(data_lines) == 3, '未解析成功的条目不会被丢弃（本用例 3 条全部解析成功）')

# 未解析的名称：原样保存
with open(radio_path, 'w', encoding='utf-8') as f:
    f.write('AO-123-OLD=100.0,200.0,FM\n')
dedlg2 = sw.DictEditorDialog(None, 'e', radio_path,
                             ['卫星名', '下行频率', '上行频率', '模式'])
buttons2 = {b.text(): b for b in dedlg2.findChildren(_qtw.QPushButton)}
buttons2['保存'].click()
app.processEvents()
check('AO-123-OLD' in sp._read_text(radio_path), '解析不出的名称按原文保存（不丢数据）')

# 窗口宽度：提示行文本不得把对话框顶宽（QLabel 默认不换行 → 文案越长最小宽度越大）
w_tqsl_path = os.path.join(TMP, 'tqsl_width.txt')
with open(w_tqsl_path, 'w', encoding='utf-8') as f:
    f.write('27607=ISS\n')
w_radio = sw.DictEditorDialog(None, 'w1', radio_path,
                              ['卫星名', '下行频率', '上行频率', '模式'])
w_tqsl = sw.DictEditorDialog(None, 'w2', w_tqsl_path, ['卫星名', 'TQSL认可名'], None)
for tag, d in (('转发器', w_radio), ('TQSL', w_tqsl)):
    d.show()
    app.processEvents()
    check(d.width() == 640 and d.height() == 480,
          '%s 对话框保持 640x480（实际 %dx%d）' % (tag, d.width(), d.height()))
    check(d.minimumSizeHint().width() < 640,
          '%s 对话框最小宽度 < 640（实际 %d）' % (tag, d.minimumSizeHint().width()))
_hint = w_radio.findChild(sw.QLabel)
check(_hint.wordWrap() is True, '提示行已开启自动换行（不再顶宽对话框）')
check(_hint.minimumSizeHint().width() < 640,
      '提示行最小宽度 < 640（实际 %d）' % _hint.minimumSizeHint().width())

sw.QMessageBox = _orig_box
show('DictEditorDialog 9 项 + 宽度 6 项')

print('5) 查表：编号键优先，名称键兼容')
bands_num = {'61781': {'downlink': '435.4', 'uplink': '145.85', 'mode': 'FM'}}
bands_old = {'ASRTU-1 (AO-123)': {'downlink': '1', 'uplink': '2', 'mode': 'FM'}}
check(sp.lookup_transponder(bands_num, 'ASRTU-1 (RS64S/BJ2CR)', '61781')['mode'] == 'FM',
      '转发器表以编号为键：按编号命中')
check(sp.lookup_transponder(bands_num, 'ASRTU-1 (RS64S/BJ2CR)')['mode'] == 'FM',
      '不传编号时按名称现查编号再命中')
check(sp.lookup_transponder(bands_old, 'ASRTU-1 (AO-123)')['mode'] == 'FM',
      '旧格式（键为名称）仍能命中')
check(sp.lookup_transponder({'0061781': {'mode': 'FM'}}, 'x', '61781')['mode'] == 'FM',
      '表里写成前导 0 的编号也命中')
check(sp.lookup_transponder(bands_num, 'x', '99999') is None, '编号对不上时返回 None')

tqsl_path = os.path.join(TMP, 'tqsl_dict.txt')
with open(tqsl_path, 'w', encoding='utf-8') as f:
    f.write('61781=AO-123\n')
check(sp.tqsl_sat_name('ASRTU-1 (RS64S/BJ2CR)', tqsl_path, '61781') == 'AO-123',
      'tqsl_sat_name 按编号命中')
check(sp.tqsl_sat_name('ASRTU-1 (RS64S/BJ2CR)', tqsl_path) == 'AO-123',
      'tqsl_sat_name 不传编号时按名称现查')
check(sp.tqsl_sat_name('ISS (ZARYA)', tqsl_path) == 'ISS (ZARYA)', '无映射时返回原名')
check(sp.has_tqsl_mapping('ASRTU-1 (RS64S/BJ2CR)', tqsl_path) is True, 'has_tqsl_mapping 命中')
check(sp.has_tqsl_mapping('ISS (ZARYA)', tqsl_path) is False, 'has_tqsl_mapping 未命中')
show('查表 10 项')

print('6) migrate_legacy_sat_data：静默升级')
sp.SETTINGS_PATH = os.path.join(TMP, 'm_xml.txt')
sp.SAT_RADIO_DICT_PATH = os.path.join(TMP, 'mig_radio.txt')
sp.TQSL_DICT_PATH = os.path.join(TMP, 'mig_tqsl.txt')

with open(sp.SETTINGS_PATH, 'w', encoding='utf-8') as f:
    f.write(str({'m_call': 'BI8SQL', 'sat_el': 20,
                 'sat_sats': ['ASRTU-1 (RS64S/BJ2CR)', 'SO-50', 'AO-123-OLD', '61781'],
                 'sat_mu_sats': ['ISS (ZARYA)']}))
with open(sp.SAT_RADIO_DICT_PATH, 'w', encoding='utf-8') as f:
    f.write('# 头注释\n\nSO-50=436.795,145.85,FM\nAO-123-OLD=1,2,FM\n')
with open(sp.TQSL_DICT_PATH, 'w', encoding='utf-8') as f:
    f.write('# TQSL\nSO-50=SO-50\n')

report = sp.migrate_legacy_sat_data()
check(report['settings'] == 2, '设置文件：sat_sats 与 sat_mu_sats 各改写一次')
check(report['radio'] == 1, '转发器表改写 1 条（解析不出的那条跳过）')
check(report['tqsl'] == 1, 'TQSL 表改写 1 条')

settings = eval(sp._read_text(sp.SETTINGS_PATH))
check(settings['sat_sats'] == ['27607', '61781', 'AO-123-OLD'],
      'sat_sats 已变成编号；解析不出的名称原样保留（不丢数据、不重复）')
check(settings['sat_mu_sats'] == ['25544'], 'sat_mu_sats 升级为编号')
check(settings['m_call'] == 'BI8SQL' and settings['sat_el'] == 20, '其它设置项不受影响')

radio_txt = sp._read_text(sp.SAT_RADIO_DICT_PATH)
check('27607=436.795,145.85,FM' in radio_txt, '转发器表键已升级为编号')
check('AO-123-OLD=1,2,FM' in radio_txt, '转发器表里解析不出的条目原样跳过')
check(radio_txt.splitlines()[0] == '# 头注释', '转发器表注释保留')
check('27607=SO-50' in sp._read_text(sp.TQSL_DICT_PATH), 'TQSL 表键已升级为编号')

# 幂等：再跑一次不应有任何改动
report2 = sp.migrate_legacy_sat_data()
check(report2 == {'settings': 0, 'radio': 0, 'tqsl': 0}, '重复执行幂等（0 改动）')

# 同一颗卫星写了多行（短名 + 长名）→ 换成编号后会变成重复键，应合并
dup_path = os.path.join(TMP, 'dedup.txt')
with open(dup_path, 'w', encoding='utf-8') as f:
    f.write('SO-50=1,2,FM\nSAUDISAT-1C (SO-50)=3,4,FM\n')
sp.SAT_RADIO_DICT_PATH = dup_path
sp.migrate_legacy_sat_data()
dup_txt = [ln for ln in sp._read_text(dup_path).splitlines() if ln.strip()]
check(dup_txt == ['27607=3,4,FM'],
      '同一颗星的多行合并为一行，且后者覆盖前者（与读取语义一致）：%r' % (dup_txt,))

# 注释里的字段说明同步更正（键已是编号、只有注释是旧口径）
hdr_path = os.path.join(TMP, 'hdr.txt')
with open(hdr_path, 'w', encoding='utf-8') as f:
    f.write('# 格式：卫星名=下行频率,上行频率,模式\n27607=1,2,FM\n')
sp.SAT_RADIO_DICT_PATH = hdr_path
r_hdr = sp.migrate_legacy_sat_data()
check(r_hdr['radio'] == 0, '键已是编号时不重复计数')
check('格式：卫星编号(NORAD ID)=' in sp._read_text(hdr_path),
      '注释里的「格式：卫星名=」更正为编号口径')
check(sp.migrate_legacy_sat_data()['radio'] == 0, '注释更正同样幂等')

# 没有星历时静默返回，不改任何文件
reset_index()
_bak = sp.TLE_CACHE
sp.TLE_CACHE = os.path.join(TMP, 'not_exist.tle')
report3 = sp.migrate_legacy_sat_data()
check(report3 == {'settings': 0, 'radio': 0, 'tqsl': 0}, '无星历时静默返回，不抛异常')
sp.TLE_CACHE = _bak
reset_index()
show('迁移 18 项')

# ---------------------------------------------------------------------------
print('6b) 迁移失败自动跳过（坏文件不崩）')
bad_dir = os.path.join(TMP, 'bad')
os.makedirs(bad_dir, exist_ok=True)
sp.SETTINGS_PATH = os.path.join(bad_dir, 'm_xml_missing.txt')   # 不存在
sp.SAT_RADIO_DICT_PATH = os.path.join(bad_dir, 'a_missing.txt')  # 不存在
sp.TQSL_DICT_PATH = bad_dir                                      # 是个目录 → 读取失败
try:
    r = sp.migrate_legacy_sat_data()
    check(r == {'settings': 0, 'radio': 0, 'tqsl': 0}, '文件缺失/不可读时静默跳过')
except Exception as e:
    check(False, '迁移不应抛异常：%r' % (e,))
show('迁移容错 1 项')

# ---------------------------------------------------------------------------
for k, v in _orig.items():
    if k == 'sw_TLE_CACHE':
        sw.TLE_CACHE = v
    else:
        setattr(sp, k, v)
reset_index()
shutil.rmtree(TMP, ignore_errors=True)

print('---')
print('通过 %d 项，失败 %d 项' % (OKS[0], len(FAILS)))
print('RESULT:', 'ALL_OK' if not FAILS else 'FAIL')
sys.exit(1 if FAILS else 0)
