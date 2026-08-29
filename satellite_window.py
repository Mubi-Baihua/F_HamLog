# -*- coding: utf-8 -*-
"""
satellite_window.py —— 业余卫星过境预测界面（PySide6）

由 project.py 的“记录”菜单调用。提供：
  - 业余卫星未来过境列表（升起/落下时间、最大仰角、方位、时长）
  - 刷新 TLE（从 Celestrak 下载并本地缓存）
  - 设置观测站位置（纬度/经度/海拔）
  - 每行“快速记录”按钮：打开预填好的新建日志
"""

import os
import datetime
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QSpinBox, QDialog, QLineEdit,
    QDialogButtonBox, QMessageBox, QFrame, QCheckBox, QApplication,
    QAbstractItemView, QHeaderView, QScrollArea, QGroupBox, QFileDialog,
    QSizePolicy, QListWidget, QListWidgetItem, QGridLayout, QProgressBar,
    QStyledItemDelegate, QCompleter,
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer

import satellite_pred as sp
from dialog_defaults import desktop_dir

SETTINGS_PATH = sp.app_path('file/m_xml.txt')
TLE_CACHE = sp.app_path('file/amateur.tle')

# 防止预测窗口（局部 QMainWindow）在 main() 返回后被 Python 回收
_open_windows = []


def _load_settings():
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            return eval(f.read())
    except Exception:
        return {}


def _save_settings(d):
    with open(SETTINGS_PATH, 'w', encoding='utf-8') as f:
        f.write(str(d))


# 本地时间统一使用「系统本地时区」显示/输入，避免按经度近似时区导致
# 与 Heavens-Above、手机卫星 APP 等其他应用显示不一致（例如经度被推算成
# 比真实时区快 1 小时）。物理轨道解算（SGP4）仍使用 observer 的真实经纬度，不受影响。
LOCAL_TZ = datetime.datetime.now().astimezone().tzinfo


def _utc_to_local_str(dt, tz=None):
    """把（带 UTC 时区的）datetime 转为本地时间字符串。tz 缺省用系统本地时区。"""
    if dt is None:
        return '--'
    local = dt.astimezone(tz) if tz is not None else dt.astimezone()
    return local.strftime('%m-%d %H:%M')


def _duration_str(sec):
    sec = int(sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f'{h}时{m}分'
    if m > 0:
        return f'{m}分{s}秒' if s else f'{m}分'
    return f'{s}秒'


def _load_local_tle_names():
    """读取本地星历中的卫星原名，供字典编辑器搜索补全。"""
    try:
        if not os.path.exists(TLE_CACHE):
            return []
        with open(TLE_CACHE, 'r', encoding='utf-8-sig') as f:
            return [name for name, _ in sp.parse_tle_text(f.read())]
    except Exception:
        return []


class SatelliteNameDelegate(QStyledItemDelegate):
    """让 TQSL / 转发器编辑器的卫星名可从本地星历中搜索。"""

    def __init__(self, names, parent=None):
        super().__init__(parent)
        self._names = names

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        completer = QCompleter(self._names, editor)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        editor.setCompleter(completer)
        return editor


class ObserverDialog(QDialog):
    """编辑观测站位置（纬度/经度/海拔），支持梅登黑格网格输入。"""

    def __init__(self, parent, lat=0.0, lon=0.0, alt=0.0):
        super().__init__(parent)
        self.setWindowTitle('观测站位置')
        self.resize(340, 175)
        lay = QVBoxLayout(self)
        #lay.addWidget(QLabel('设置你的 QTH 位置，用于计算卫星仰角与方位。\n可填经纬度或梅登黑格网格，编辑完成后自动同步。'))

        self.lat_edit = QLineEdit(f'{lat:.5f}')
        self.lon_edit = QLineEdit(f'{lon:.5f}')
        self.alt_edit = QLineEdit(f'{alt:.1f}')
        for lbl, ed in (('纬度(°) 北纬为正:', self.lat_edit),
                        ('经度(°) 东经为正:', self.lon_edit),
                        ('海拔(m):', self.alt_edit)):
            row = QHBoxLayout()
            row.addWidget(QLabel(lbl))
            row.addWidget(ed)
            lay.addLayout(row)

        # 梅登黑格网格
        grid_row = QHBoxLayout()
        self.grid_edit = QLineEdit()
        try:
            self.grid_edit.setPlaceholderText(
                '梅登黑格网格，如 %s' % sp.latlon_to_maidenhead(lat, lon))
            self.grid_edit.setText(sp.latlon_to_maidenhead(lat, lon))
        except Exception:
            self.grid_edit.setPlaceholderText('梅登黑格网格，如 PM84')
        grid_row.addWidget(QLabel('网格:'))
        grid_row.addWidget(self.grid_edit)
        lay.addLayout(grid_row)

        self.lat_edit.editingFinished.connect(self._coord_to_grid)
        self.lon_edit.editingFinished.connect(self._coord_to_grid)
        self.grid_edit.editingFinished.connect(self._grid_to_coord)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _grid_to_coord(self):
        text = self.grid_edit.text().strip()
        if not text:
            return
        try:
            glat, glon = sp.maidenhead_to_latlon(text)
        except ValueError as e:
            QMessageBox.warning(self, '网格无效', str(e))
            return
        self.grid_edit.setText(sp.latlon_to_maidenhead(glat, glon))
        self.lat_edit.setText(f'{glat:.5f}')
        self.lon_edit.setText(f'{glon:.5f}')

    def _coord_to_grid(self):
        try:
            self.grid_edit.setText(sp.latlon_to_maidenhead(
                float(self.lat_edit.text()), float(self.lon_edit.text())))
        except (TypeError, ValueError):
            return

    def get_values(self):
        try:
            lat = float(self.lat_edit.text())
            lon = float(self.lon_edit.text())
            alt = float(self.alt_edit.text())
        except ValueError:
            return None
        return lat, lon, alt


class SatelliteSelectDialog(QDialog):
    """从已加载卫星中勾选“自选”范围。"""

    def __init__(self, parent, names, selected):
        super().__init__(parent)
        self.setWindowTitle('选择卫星')
        self.resize(360, 480)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('勾选要参与过境预测的卫星（可搜索筛选）：'))

        top = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText('搜索卫星名…')
        top.addWidget(self.search_edit)
        top.addWidget(self._mk_btn('全选', self._select_all))
        top.addWidget(self._mk_btn('全不选', self._select_none))
        lay.addLayout(top)

        self.list_widget = QListWidget()
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setUpdatesEnabled(False)
        self.checks = {}
        self.items = {}
        init = selected if isinstance(selected, set) else None
        for n in names:
            item = QListWidgetItem(n, self.list_widget)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if init is None or n in init
                               else Qt.CheckState.Unchecked)
            self.items[n] = item
        self.list_widget.setUpdatesEnabled(True)
        lay.addWidget(self.list_widget)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        self._search = ''
        self.search_edit.textChanged.connect(self._filter)

    def _mk_btn(self, text, slot):
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    def _filter(self, text):
        self._search = text.strip().lower()
        self.list_widget.setUpdatesEnabled(False)
        for n, item in self.items.items():
            item.setHidden(bool(self._search) and self._search not in n.lower())
        self.list_widget.setUpdatesEnabled(True)

    def _visible_names(self):
        """当前搜索条件下可见的卫星名；无搜索时返回全部。"""
        if not self._search:
            return list(self.items.keys())
        return [n for n in self.items if self._search in n.lower()]

    def _select_all(self):
        for n in self._visible_names():
            self.items[n].setCheckState(Qt.CheckState.Checked)

    def _select_none(self):
        for n in self._visible_names():
            self.items[n].setCheckState(Qt.CheckState.Unchecked)

    def get_selected(self):
        return {n for n, item in self.items.items()
            if item.checkState() == Qt.CheckState.Checked}


class DictEditorDialog(QDialog):
    """通用「键值文本文件」编辑器，用于维护 sat_radio_dict.txt（卫星转发器）
    与 tqsl_dict.txt（TQSL/LoTW 名称映射）。

    列定义：
      - columns[0] 为键（key，如卫星名）；
      - 其余列为值字段，按 value_delimiter 拼接/拆分（None 表示单列值）。
    文件中的注释行（# 开头）与空行会被原样保留，仅在末尾重写数据行。
    """

    def __init__(self, parent, title, path, columns, value_delimiter=','):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 480)
        self._path = path
        self._columns = list(columns)
        self._delim = value_delimiter
        self._comments = []
        self._rows = []  # 每行: (key, [value, ...])

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            '每行一条记录。点击单元格可直接编辑；用“添加”新增，“删除选中”移除整行；'
            '完成后点“保存”写回文件。'))

        self.table = QTableWidget(0, len(self._columns))
        self.table.setHorizontalHeaderLabels(self._columns)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed |
            QAbstractItemView.AnyKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        tle_names = _load_local_tle_names()
        if tle_names:
            self.table.setItemDelegateForColumn(
                0, SatelliteNameDelegate(tle_names, self.table))
        lay.addWidget(self.table, 1)   # 拉伸因子 1：表格纵列填满窗口

        btn_row = QHBoxLayout()
        add_btn = QPushButton('添加')
        del_btn = QPushButton('删除选中')
        text_btn = QPushButton('使用记事本编辑')
        save_btn = QPushButton('保存')
        close_btn = QPushButton('关闭')
        add_btn.clicked.connect(self._add_row)
        del_btn.clicked.connect(self._del_row)
        text_btn.clicked.connect(self._open_text_editor)
        save_btn.clicked.connect(self._save)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addWidget(text_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._load()

    def _open_text_editor(self):
        if self._delim is not None:
            header = ('# 卫星转发器表\n# 格式：卫星名=下行频率,上行频率,模式\n'
                      '# 例如：SO-50=436.795,145.850,FM')
        else:
            header = ('# TQSL / LoTW 卫星名称映射表\n# 格式：卫星显示名=TQSL认可名\n'
                      '# 例如：ISS (ZARYA)=ISS')
        sp.open_text_config(self._path, header)

    # ---- 读取 ----
    def _load(self):
        self._comments = []
        self._rows = []
        if os.path.exists(self._path):
            try:
                text = sp._read_text(self._path)
            except Exception:
                text = ''
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith('#') or not stripped:
                    self._comments.append(line.rstrip('\n'))  # 保留原注释/空行
                    continue
                if '=' not in line:
                    continue
                key, rest = line.split('=', 1)
                key = key.strip()
                if not key:
                    continue
                rest = rest.strip()
                if self._delim is not None:
                    vals = [x.strip() for x in rest.split(self._delim)]
                else:
                    vals = [rest]
                nvals = len(self._columns) - 1
                if len(vals) < nvals:
                    vals += [''] * (nvals - len(vals))
                elif len(vals) > nvals:
                    # 值字段含分隔符（如模式 “SSB,CW”）时合并多余部分
                    vals = vals[:nvals - 1] + [self._delim.join(vals[nvals - 1:])]
                self._rows.append((key, vals))
        self._render()

    def _render(self):
        self.table.setRowCount(len(self._rows))
        for i, (key, vals) in enumerate(self._rows):
            self.table.setItem(i, 0, QTableWidgetItem(key))
            for j, v in enumerate(vals):
                self.table.setItem(i, j + 1, QTableWidgetItem(v))

    # ---- 编辑 ----
    def _add_row(self):
        self._rows.append(('', [''] * (len(self._columns) - 1)))
        self._render()
        self.table.scrollToBottom()
        # 选中新行首列并进入编辑，方便直接输入
        last = self.table.rowCount() - 1
        if last >= 0:
            self.table.selectRow(last)
            self.table.editItem(self.table.item(last, 0))

    def _del_row(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for r in rows:
            if 0 <= r < len(self._rows):
                del self._rows[r]
        self._render()

    def _collect(self):
        """从表格（含未保存的修改）读回当前数据。"""
        self._rows = []
        for i in range(self.table.rowCount()):
            key = (self.table.item(i, 0).text() if self.table.item(i, 0) else '').strip()
            if not key:
                continue
            vals = []
            for j in range(1, len(self._columns)):
                it = self.table.item(i, j)
                vals.append(it.text().strip() if it else '')
            self._rows.append((key, vals))

    # ---- 保存 ----
    def _save(self):
        self._collect()
        if not self._rows:
            QMessageBox.warning(self, '无可保存数据', '没有任何有效（键不为空）的记录。')
            return
        try:
            os.makedirs(os.path.dirname(self._path) or '.', exist_ok=True)
            with open(self._path, 'w', encoding='utf-8') as f:
                if self._comments:
                    f.write('\n'.join(self._comments).rstrip('\n') + '\n')
                else:
                    if self._delim is not None:
                        f.write('# 卫星转发器数据（格式：卫星名=下行频率,上行频率,模式）\n'
                                '# 下行频率=接收频率(freq_rx)，上行频率=发射频率(freq)\n'
                                '# 可由“卫星通联记录”窗口的“编辑转发器”维护\n')
                    else:
                        f.write('# TQSL / LoTW 卫星名称映射表（格式：卫星显示名=TQSL认可名）\n'
                                '# 可由“卫星通联记录”窗口的“编辑TQSL映射”维护\n')
                for key, vals in self._rows:
                    if self._delim is not None:
                        line = '%s=%s' % (key, self._delim.join(vals))
                    else:
                        line = '%s=%s' % (key, vals[0] if vals else '')
                    f.write(line + '\n')
            QMessageBox.information(self, '已保存', '已保存 %d 条记录。' % len(self._rows))
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, '保存失败', '写入文件出错：%s' % e)


class PredictWorker(QThread):
    progress = Signal(int)
    done = Signal(list)

    def __init__(self, sats, observer, start_utc, duration_hours, min_elev, step_sec):
        super().__init__()
        self.sats = sats
        self.observer = observer
        self.start_utc = start_utc
        self.duration_hours = duration_hours
        self.min_elev = min_elev
        self.step_sec = step_sec

    def run(self):
        rows = []
        bands = sp.load_sat_radio_dict()  # 卫星转发器数据（来自 sat_radio_dict.txt，回退内置 SATE_BANDS）
        total = len(self.sats)
        for idx, (name, sat) in enumerate(self.sats):
            if self.isInterruptionRequested():
                return  # 窗口关闭等场景，及时退出，避免线程被强制销毁
            try:
                passes = sp.predict_passes(
                    sat, self.observer, self.start_utc,
                    duration_hours=self.duration_hours,
                    min_elevation_deg=self.min_elev,
                    step_sec=self.step_sec)
            except Exception:
                passes = []
            for p in passes:
                band = sp.lookup_transponder(bands, p['name'])
                rows.append(self._build_row(p, band))
            self.progress.emit(int((idx + 1) / total * 100))
        rows.sort(key=lambda r: r['aos_jd'])
        self.done.emit(rows)

    def _build_row(self, p, band):
        name = p['name']
        obs_tz = LOCAL_TZ
        local_aos = p['aos'].astimezone(obs_tz)
        # 快速记录预填内容：卫星名用 TQSL/LoTW 认可的名称
        preset = {
            'sat_name': sp.tqsl_sat_name(name),
            'prop_mode': 'SAT',
            'date': local_aos.strftime('%Y-%m-%d'),
            'time': local_aos.strftime('%H:%M'),
        }
        if band:
            # FM 转发器（或线性转发器）的模式与收发频率
            # 记录时：freq=上行频率(本端发射)，freq_rx=下行频率(本端接收)
            preset['mode'] = band.get('mode', 'FM')
            preset['freq'] = band.get('uplink', '')
            preset['freq_rx'] = band.get('downlink', '')
        return {
            'name': name,
            'aos_str': _utc_to_local_str(p['aos'], obs_tz),
            'los_str': _utc_to_local_str(p['los'], obs_tz),
            'max_elev': p['max_elevation'],
            'aos_az': p['aos_azimuth'],
            'los_az': p['los_azimuth'],
            'duration': p['duration_sec'],
            'aos_jd': p['aos_jd'],
            'preset': preset,
        }


class TleFetchWorker(QThread):
    """后台下载/解析业余卫星 TLE，避免阻塞主线程（加速界面打开）。"""
    fetched = Signal(list)
    progress = Signal(str)
    progress_pct = Signal(int)
    warning = Signal(str)
    error = Signal(str)
    canceled = Signal()  # 用户主动取消下载（非错误）

    def __init__(self, force):
        super().__init__()
        self.force = force
        self.cancel_requested = False  # 由主线程置 True 触发取消

    def run(self):
        try:
            text = sp.fetch_amateur_tle(
                cache_path=TLE_CACHE, force=self.force, timeout=25,
                progress=self.progress.emit,
                progress_pct=self.progress_pct.emit,
                cancel=lambda: self.cancel_requested)
            sats = sp.parse_tle_text(text)
            self.fetched.emit(sats)
        except sp.TleFetchCanceled:
            # 用户取消：不发错误，仅通知界面已取消
            self.canceled.emit()
            return
        except Exception as e:
            if self.force:
                self.error.emit(f'无法获取全部活动卫星 TLE：\n{e}')
                return
            # 下载失败，回退到本地缓存
            try:
                text = sp.fetch_amateur_tle(cache_path=TLE_CACHE, force=False)
                sats = sp.parse_tle_text(text)
                self.warning.emit(f'下载失败，使用本地缓存（{len(sats)} 颗）：{e}')
                self.fetched.emit(sats)
            except Exception as e2:
                self.error.emit(f'无法下载 TLE 且没有本地缓存：\n{e2}')


def main(parent_window, quick_log_callback=None, title='卫星过境'):
    settings = _load_settings()
    lat = float(settings.get('m_lat', 0.0) or 0.0)
    lon = float(settings.get('m_lon', 0.0) or 0.0)
    alt = float(settings.get('m_alt', 0.0) or 0.0)
    observer_unset = (lat == 0.0 and lon == 0.0)

    # 上次保存的预测设置（时长/仰角/范围/自选卫星）
    # 时长统一钳制到 [1, 240] 小时：历史设置里若存有更大的值，这里自动收敛到 240
    sat_dur = int(sp.clamp_predict_hours(settings.get('sat_dur', 24) or 24))
    sat_el = int(settings.get('sat_el', 10) or 10)
    sat_sats_raw = settings.get('sat_sats', None)  # None=从未保存；[]=曾显式清空；list=已选卫星名

    win = QMainWindow()
    win.resize(940, 620)
    win.setWindowTitle(title)
    win._map_window = None  # 卫星地图窗口引用（由“地图”按钮打开）
    central = QWidget()
    win.setCentralWidget(central)
    layout = QVBoxLayout(central)

    # ---------- 工具栏（两行：上方“数据与设置”，下方“预测参数”） ----------
    # 第一行：数据 / 设置类操作
    top_grp = QGroupBox('数据与设置')
    top_vlay = QVBoxLayout(top_grp)
    tool_top = QHBoxLayout()
    top_vlay.addLayout(tool_top)
    refresh_btn = QPushButton('刷新TLE')
    obs_btn = QPushButton('观测站设置')
    edit_radio_btn = QPushButton('编辑转发器')
    edit_radio_btn.setToolTip('使用记事本编辑卫星转发器数据 sat_radio_dict.txt（下行/上行频率与模式）')
    edit_tqsl_btn = QPushButton('编辑TQSL映射')
    edit_tqsl_btn.setToolTip('使用记事本编辑 TQSL/LoTW 卫星名称映射 tqsl_dict.txt')
    import_tle_btn = QPushButton('导入星历数据')
    import_tle_btn.setToolTip('从 txt 或 tle 文件导入卫星星历数据（TLE 格式），追加到现有卫星列表中')
    # 双站通联预测：从本窗口直接打开，无需再回到主页或菜单
    mutual_btn = QPushButton('通联预测')
    mutual_btn.setToolTip('打开双站通联预测：输入对方台站位置与各自最低仰角，预测两地可通过哪些卫星互相通联')
    # 卫星地图：打开全球地图窗口，显示选中卫星的地面轨迹 / 当前位置 / 本台站
    map_btn = QPushButton('卫星地图')
    map_btn.setToolTip(
        '打开全球卫星地图：显示所有已选卫星（与下方“范围/自选卫星”实时同步）'
        '自当前时刻起的地面轨迹与实时位置，以及本台站。\n'
        '在结果表中点选一行，该卫星会在地图上聚焦高亮。')
    # 星历自动更新实时开关（等价于“设置”中的复选框）
    auto_cb = QCheckBox('卫星星历自动更新')
    _auto_on = bool(settings.get('sat_auto_update', False))
    _auto_hours = int(settings.get('sat_update_hours', 24) or 24)
    auto_cb.setChecked(_auto_on)
    auto_cb.setToolTip('开启后按“设置”中的间隔（当前每 %d 小时）自动刷新卫星星历(TLE)。也可在“设置”中修改。' % _auto_hours)
    tool_top.addWidget(refresh_btn)
    tool_top.addWidget(obs_btn)
    tool_top.addSpacing(12)
    tool_top.addWidget(edit_radio_btn)
    tool_top.addWidget(edit_tqsl_btn)
    tool_top.addWidget(import_tle_btn)
    tool_top.addSpacing(10)
    tool_top.addWidget(mutual_btn)
    tool_top.addWidget(map_btn)
    tool_top.addStretch(1)
    tool_top.addWidget(auto_cb)
    # 星历最近更新时间：取本地缓存文件 file/amateur.tle 的修改时间（手动刷新或后台
    # 自动更新写入后均会刷新）。放在「数据与设置」框内，窗口打开即显示，获取完成后再次刷新。
    tle_time_label = QLabel('星历更新时间：—')
    tle_time_label.setStyleSheet('color: gray;')
    top_vlay.addWidget(tle_time_label)
    layout.addWidget(top_grp)

    # 分隔线
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFrameShadow(QFrame.Sunken)
    layout.addWidget(sep)

    # 第二行：预测参数
    bot_grp = QGroupBox('预测参数')
    tool_bottom = QHBoxLayout(bot_grp)
    start_label = QLabel('开始时间:')
    start_edit = QLineEdit()
    start_edit.setText(datetime.datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M'))
    start_edit.setPlaceholderText('YYYY-MM-DD HH:MM（如 2026-07-27 17:45）')
    start_edit.setMinimumWidth(150)
    start_edit.setToolTip('预测起始时刻（系统本地时间），默认当前时间，支持 YYYY-MM-DD HH:MM 或带秒。')
    dur_label = QLabel('预测时长(小时):')
    dur_spin = QSpinBox()
    dur_spin.setRange(sp.MIN_PREDICT_HOURS, sp.MAX_PREDICT_HOURS)  # 最长 240 小时（10 天）
    dur_spin.setToolTip('预测时间跨度，最长 %d 小时（10 天）。' % sp.MAX_PREDICT_HOURS)
    dur_spin.setValue(sat_dur)  # 自动读取上次的值（已钳制到 240 以内）
    el_label = QLabel('最低仰角(°):')
    el_spin = QSpinBox()
    el_spin.setRange(0, 90)
    el_spin.setValue(sat_el)
    el_spin.setToolTip('本站（观测站）的最低可用仰角：低于该仰角认为天线被遮挡 / 信号不可用，不计入可见过境。')
    sel_btn = QPushButton('选择卫星…')
    tool_bottom.addWidget(start_label)
    tool_bottom.addWidget(start_edit)
    tool_bottom.addSpacing(12)
    tool_bottom.addWidget(dur_label)
    tool_bottom.addWidget(dur_spin)
    tool_bottom.addWidget(el_label)
    tool_bottom.addWidget(el_spin)
    tool_bottom.addSpacing(12)
    tool_bottom.addWidget(sel_btn)
    tool_bottom.addStretch(1)
    layout.addWidget(bot_grp)

    status = QLabel('准备中…')
    status.setStyleSheet('color: gray;')
    layout.addWidget(status)

    # 卫星星历下载进度条 + 取消按钮：仅在「刷新TLE」下载期间显示，平时隐藏
    prog_layout = QHBoxLayout()
    progress_bar = QProgressBar()
    progress_bar.setRange(0, 100)
    progress_bar.setTextVisible(True)
    progress_bar.setFormat('下载星历 %p%')
    progress_bar.setVisible(False)
    prog_layout.addWidget(progress_bar, 1)
    cancel_dl_btn = QPushButton('取消下载')
    cancel_dl_btn.setVisible(False)
    cancel_dl_btn.setToolTip('取消当前正在进行的星历下载')

    def cancel_download():
        # 置取消标志；后台线程在分块读时检测到后会抛出 TleFetchCanceled
        cur = getattr(win, '_tle_worker', None)
        if cur is not None and cur.isRunning():
            cur.cancel_requested = True
        cancel_dl_btn.setEnabled(False)
        cancel_dl_btn.setText('取消中…')

    cancel_dl_btn.clicked.connect(cancel_download)
    prog_layout.addWidget(cancel_dl_btn)
    layout.addLayout(prog_layout)

    # ---------- 表格 ----------
    table = QTableWidget(0, 8)
    table.setHorizontalHeaderLabels(
        ['卫星', '升起(本地)', '落下(本地)', '最大仰角', '方位(升起→落下)', '时长', '记录', ''])
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    table.setColumnWidth(0, 170)
    table.setColumnWidth(1, 120)
    table.setColumnWidth(2, 120)
    table.setColumnWidth(3, 80)
    table.setColumnWidth(4, 150)
    table.setColumnWidth(5, 90)
    table.setColumnWidth(6, 70)
    table.setColumnWidth(7, 0)
    layout.addWidget(table)

    sats = []
    last_rows = []  # 保存最近一次预测结果，供单行"记录"按钮读取预填数据
    # 默认「全不选」：没有任何已保存的选择时，初始为空集合；
    # 这样选择对话框里所有卫星都保持未勾选状态（符合需求：选择卫星默认全不选）。
    selected_names = (set(sat_sats_raw)
                      if isinstance(sat_sats_raw, list)
                      else set())
    # 窗口打开后首次获取 TLE 时：若尚未选择任何卫星（包括曾显式清空的情况），
    # 自动弹出选择框引导用户；用户关闭对话框后本窗口会话内不再自动弹窗，
    # 避免每次刷新都打扰。
    auto_prompt_pending = True

    def set_observer(lat_, lon_, alt_):
        nonlocal lat, lon, alt
        lat, lon, alt = lat_, lon_, alt_

    def _persist():
        """把当前的预测设置写入 file/m_xml.txt，便于下次启动恢复。"""
        s = _load_settings()
        s['sat_dur'] = int(sp.clamp_predict_hours(dur_spin.value()))
        s['sat_el'] = el_spin.value()
        s['sat_filter'] = '自选卫星'
        s['sat_sats'] = sorted(selected_names)
        _save_settings(s)

    def _parse_start():
        """解析“开始时间”文本框；返回 (datetime_local, error_msg)。"""
        txt = start_edit.text().strip()
        for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d %H:%M:%S.%f'):
            try:
                return datetime.datetime.strptime(txt, fmt), None
            except ValueError:
                continue
        return None, ('格式应为 YYYY-MM-DD HH:MM（例如 2026-07-27 17:45），'
                     '可带秒；当前输入：' + (txt or '（空）'))

    def active_sats_list():
        """返回当前自选卫星列表，预测与地图共用同一份。"""
        # selected_names 现在恒为 set（默认空集合 = 全不选），
        # 空集合时返回空列表，预测会提示“尚未选择卫星”。
        return [(n, s) for (n, s) in sats if n in selected_names]

    def _push_sats_to_map():
        """把当前「已选卫星」与最低仰角同步给已打开的地图窗口。"""
        mw = getattr(win, '_map_window', None)
        if mw is None:
            return
        mw.set_sats(active_sats_list())
        mw.set_min_elev(el_spin.value())

    def _show_tle_time():
        """在窗口中显示星历（TLE）最近更新时间——取自设置 file/m_xml.txt 的 sat_last_update（epoch 秒）。"""
        s = _load_settings()
        epoch = s.get('sat_last_update')
        if epoch:
            try:
                dt = datetime.datetime.fromtimestamp(float(epoch), LOCAL_TZ)
                tle_time_label.setText(
                    '星历更新时间：' + dt.strftime('%Y-%m-%d %H:%M:%S'))
                return
            except (ValueError, OSError, TypeError):
                pass
        tle_time_label.setText('星历更新时间：尚未获取')

    _show_tle_time()  # 窗口打开即显示（若本地已有缓存，则为其修改时间）

    # 后台自动更新会定期刷新本地星历缓存；用定时器让窗口中的更新时间保持最新
    _tle_time_timer = QTimer(win)
    _tle_time_timer.setInterval(60000)  # 每 60 秒刷新一次
    _tle_time_timer.timeout.connect(_show_tle_time)
    _tle_time_timer.start()

    def run_prediction():
        nonlocal sats, selected_names
        if not sats:
            status.setText('没有可用的卫星数据，请先“刷新TLE”。')
            return
        active_sats = active_sats_list()
        if not selected_names:
            status.setText('尚未选择卫星，请点击“选择卫星…”勾选要跟踪的卫星。')
            table.setRowCount(0)
            _push_sats_to_map()
            return
        observer = (lat, lon, alt)
        status.setText('正在计算过境（%d 颗卫星）…' % len(active_sats))
        refresh_btn.setEnabled(False)
        # 若上一次预测仍在跑，先中断它，避免重复线程与“destroyed while running”
        old = getattr(win, '_worker', None)
        if old is not None and old.isRunning():
            old.requestInterruption()
            old.wait(3000)
        # 开始时间取自文本框（系统本地时间），先校验格式，再按系统本地时区转 UTC 供 SGP4 使用
        start_local, err = _parse_start()
        if err:
            status.setText('开始时间无效：' + err)
            table.setRowCount(0)
            refresh_btn.setEnabled(True)
            return
        start = start_local.replace(tzinfo=LOCAL_TZ).astimezone(datetime.timezone.utc)
        # 时长兜底钳制：任何来源（手输/历史设置）超过 240 小时都按 240 小时算
        hours = sp.clamp_predict_hours(dur_spin.value())
        if dur_spin.value() != int(hours):
            dur_spin.blockSignals(True)
            dur_spin.setValue(int(hours))
            dur_spin.blockSignals(False)
        if hours > 72:
            status.setText('正在计算过境（%d 颗卫星，跨度 %d 小时，可能较慢）…'
                           % (len(active_sats), int(hours)))
        worker = PredictWorker(
            active_sats, observer, start,
            duration_hours=hours,
            min_elev=el_spin.value(),
            step_sec=60)
        win._worker = worker  # 防止被回收

        def on_progress(v):
            status.setText('正在计算过境… %d%%' % v)

        def on_done(rows):
            if getattr(win, '_worker', None) is worker:
                win._worker = None  # 线程即将被 deleteLater，避免关闭时访问已删除对象
            populate(rows)
            refresh_btn.setEnabled(True)
            obs_info = f'观测站: 纬{lat:.3f}° 经{lon:.3f}° 海拔{alt:.0f}m'
            sel_info = f' ｜ 已选 {len(selected_names)} 颗'
            status.setText(
                f'{obs_info}{sel_info} ｜ 卫星 {len(active_sats)} 颗 ｜ 可见过境 {len(rows)} 次')

        worker.finished.connect(worker.deleteLater)
        worker.progress.connect(on_progress)
        worker.done.connect(on_done)
        worker.start()

    def populate(rows):
        last_rows[:] = rows
        table.setRowCount(len(rows))
        sel_col = 7
        for i, r in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(r['name']))
            table.setItem(i, 1, QTableWidgetItem(r['aos_str']))
            table.setItem(i, 2, QTableWidgetItem(r['los_str']))
            table.setItem(i, 3, QTableWidgetItem(f"{r['max_elev']:.1f}°"))
            table.setItem(i, 4, QTableWidgetItem(
                f"{r['aos_az']:.0f}°→{r['los_az']:.0f}°"))
            table.setItem(i, 5, QTableWidgetItem(_duration_str(r['duration'])))
            rec_btn = QPushButton('记录')
            rec_btn.setToolTip('打开批量记录窗口并预填该卫星的卫星名/传播模式/收发频率等信息')
            rec_btn.clicked.connect(
                lambda _checked=False, i=i: log_row(i))
            table.setCellWidget(i, 6, rec_btn)
            # 第7列隐藏，仅占位（保持与其它记录窗口列风格一致）
            table.setItem(i, sel_col, QTableWidgetItem(''))
        table.scrollToTop()

    def refresh_tle(force=False):
        nonlocal sats
        status.setText('正在获取全部活动卫星 TLE…')
        # 显示下载进度条（默认确定进度；若服务器未返回大小则转忙碌动画）
        progress_bar.setVisible(True)
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setFormat('下载星历 %p%')
        cancel_dl_btn.setVisible(True)  # 下载期间显示「取消下载」
        refresh_btn.setEnabled(False)
        # 若上一次获取仍在跑，先中断
        old = getattr(win, '_tle_worker', None)
        if old is not None and old.isRunning():
            old.requestInterruption()
            old.wait(3000)
        worker = TleFetchWorker(force)
        win._tle_worker = worker

        def on_fetched(s):
            nonlocal sats, selected_names, auto_prompt_pending
            if getattr(win, '_tle_worker', None) is worker:
                win._tle_worker = None
            progress_bar.setVisible(False)
            cancel_dl_btn.setVisible(False)
            cancel_dl_btn.setEnabled(True)
            cancel_dl_btn.setText('取消下载')
            sats = s
            status.setText(f'已更新 TLE，共 {len(sats)} 颗卫星。')
            _show_tle_time()
            refresh_btn.setEnabled(True)
            # 窗口打开后首次获取 TLE：若尚未选择任何卫星，自动弹出选择框引导；
            # 用户关闭对话框后（auto_prompt_pending 置 False）本会话不再自动弹窗。
            if auto_prompt_pending:
                auto_prompt_pending = False
                if not selected_names:
                    open_select()
            if selected_names:
                run_prediction()
            # 若地图窗口已打开，同步最新的「已选卫星」列表（名称/轨道根数）
            _push_sats_to_map()

        def on_warning(w):
            progress_bar.setVisible(False)
            cancel_dl_btn.setVisible(False)
            cancel_dl_btn.setEnabled(True)
            cancel_dl_btn.setText('取消下载')
            status.setText(w)
            _show_tle_time()

        def on_error(e):
            if getattr(win, '_tle_worker', None) is worker:
                win._tle_worker = None
            progress_bar.setVisible(False)
            cancel_dl_btn.setVisible(False)
            cancel_dl_btn.setEnabled(True)
            cancel_dl_btn.setText('取消下载')
            refresh_btn.setEnabled(True)
            table.setRowCount(0)
            QMessageBox.warning(win, 'TLE 获取失败', e)

        def on_canceled():
            # 用户主动取消：清理状态，不弹错误框
            if getattr(win, '_tle_worker', None) is worker:
                win._tle_worker = None
            progress_bar.setVisible(False)
            cancel_dl_btn.setVisible(False)
            cancel_dl_btn.setEnabled(True)
            cancel_dl_btn.setText('取消下载')
            refresh_btn.setEnabled(True)
            status.setText('已取消星历下载。')

        def on_progress_pct(pct):
            # pct < 0：服务器未返回 Content-Length，进度条显示忙碌动画
            if pct < 0:
                progress_bar.setRange(0, 0)
                progress_bar.setFormat('下载星历…')
            else:
                progress_bar.setRange(0, 100)
                progress_bar.setValue(pct)

        worker.fetched.connect(on_fetched)
        worker.progress.connect(status.setText)
        worker.progress_pct.connect(on_progress_pct)
        worker.warning.connect(on_warning)
        worker.error.connect(on_error)
        worker.canceled.connect(on_canceled)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def edit_observer():
        dlg = ObserverDialog(win, lat, lon, alt)
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.get_values()
            if vals is None:
                QMessageBox.warning(win, '输入错误', '请输入有效的数字。')
                return
            lat_, lon_, alt_ = vals
            set_observer(lat_, lon_, alt_)
            s = _load_settings()
            s['m_lat'] = lat_
            s['m_lon'] = lon_
            s['m_alt'] = alt_
            _save_settings(s)
            run_prediction()
            # 本台站位置变化，同步到已打开的地图窗口
            mw = getattr(win, '_map_window', None)
            if mw is not None:
                mw.set_stations(home=(lat_, lon_, alt_))

    def _push_selection_to_mutual():
        """把本窗口当前的 范围/自选卫星 反向同步到所有已打开的「通联预测」窗口。"""
        try:
            import mutual_window
        except Exception:
            return
        for w in list(getattr(mutual_window, '_open_windows', [])):
            fn = getattr(w, 'apply_remote_selection', None)
            if callable(fn):
                fn('自选卫星', selected_names)

    def open_select():
        nonlocal selected_names
        if not sats:
            QMessageBox.information(win, '暂无卫星', '请先刷新 TLE。')
            return
        names = [n for (n, s) in sats]
        dlg = SatelliteSelectDialog(win, names, selected_names)
        if dlg.exec() == QDialog.Accepted:
            selected_names = dlg.get_selected()
            _persist()
            run_prediction()
            _push_selection_to_mutual()
            _push_sats_to_map()   # 自选卫星变化 → 地图同步显示新的一批卫星

    def import_tle():
        nonlocal selected_names
        """从用户选择的 txt 或 tle 文件导入卫星星历数据，追加到现有卫星列表。"""
        path, _ = QFileDialog.getOpenFileName(
            win, '导入卫星星历数据', desktop_dir(),
            '星历文件 (*.tle *.txt);;TLE 文件 (*.tle);;文本文件 (*.txt)')
        if not path:
            return
        try:
            text = sp._read_text(path)
        except Exception as e:
            QMessageBox.warning(win, '读取失败', '无法读取文件：%s' % e)
            return
        imported = sp.parse_tle_text(text)
        if not imported:
            QMessageBox.warning(win, '导入失败', '未从文件中解析到有效的 TLE 数据。')
            return
        existing_names = {n for n, _ in sats}
        new_sats = [(n, sat) for n, sat in imported if n not in existing_names]
        duplicate_count = len(imported) - len(new_sats)
        if not new_sats:
            QMessageBox.information(
                win, '导入完成',
                '文件中 %d 颗卫星均已存在，无需更新。' % len(imported))
            return
        sats.extend(new_sats)
        selected_names = set(n for n, _ in sats)
        _persist()
        QMessageBox.information(
            win, '导入完成',
            '已导入 %d 颗新卫星（跳过 %d 颗已存在），当前共 %d 颗。'
            % (len(new_sats), duplicate_count, len(sats)))
        run_prediction()
        _push_sats_to_map()

    def edit_radio_dict():
        dlg = DictEditorDialog(
            win, '编辑卫星转发器', sp.SAT_RADIO_DICT_PATH,
            ['卫星名', '下行频率', '上行频率', '模式'], value_delimiter=',')
        if dlg.exec() == QDialog.Accepted and sats:
            run_prediction()

    def edit_tqsl_dict():
        dlg = DictEditorDialog(
            win, '编辑 TQSL/LoTW 映射', sp.TQSL_DICT_PATH,
            ['卫星显示名', 'LoTW 认可名'], value_delimiter=None)
        if dlg.exec() == QDialog.Accepted and sats:
            run_prediction()

    def open_mutual():
        """从卫星过境预测窗口内打开双站通联预测（入口统一收归此处）。"""
        import mutual_window

        def on_sel_change(filter_mode, sel):
            """通联预测里改了自选卫星 / 范围，实时同步回本窗口。"""
            nonlocal selected_names
            selected_names = sel
            _persist()
            if sats:
                run_prediction()
            _push_sats_to_map()   # 通联预测改了自选卫星 → 地图同步

        mutual_window.main(
            win, quick_log_callback=quick_log_callback,
            on_selection_change=on_sel_change)

    def open_map():
        """打开卫星地图窗口：显示「所有已选卫星」的地面轨迹 / 实时位置 / 本台站。

        - 卫星范围与本窗口的「范围 / 自选卫星」实时同步；
        - 在表格里点选某颗卫星，该星在地图上聚焦高亮；
        - 地图的「轨迹时长」会记住上次的设置，并与通联预测打开的地图共用。"""
        import satellite_map_window

        name = None
        rows = table.selectedIndexes()
        if rows:
            name = table.item(rows[0].row(), 0).text()
        if not name and last_rows:
            name = last_rows[0]['name']
        # 已经开过就直接激活，避免堆出多个地图窗口
        mw = getattr(win, '_map_window', None)
        if mw is not None and mw.isVisible():
            _push_sats_to_map()
            if name:
                mw.set_satellite(name)
            mw.raise_()
            mw.activateWindow()
            return
        def on_el_change(a, b):
            """地图内调整最低仰角后，回写到本窗口并重新预测 / 落盘。"""
            el_spin.blockSignals(True)
            el_spin.setValue(int(round(a)))
            el_spin.blockSignals(False)
            _persist()
            if sats:
                run_prediction()

        mw = satellite_map_window.open_map(
            win, active_sats_list(), home=(lat, lon, alt),
            selected_name=name, source=win, min_elev=el_spin.value(),
            on_min_elev_change=on_el_change)
        win._map_window = mw

    def _sync_map_if_open():
        """地图已打开时，把选中的卫星名实时同步到地图（聚焦该卫星）。

        注意：此函数**不会**主动打开地图——打开动作只由「单击非记录列」
        （_focus_or_open_map）触发，避免点击「记录」按钮时因行选择变化而误开地图。
        """
        rows = table.selectedIndexes()
        if not rows:
            return
        mw = getattr(win, '_map_window', None)
        if mw is not None and mw.isVisible():
            mw.set_satellite(table.item(rows[0].row(), 0).text())

    def _focus_or_open_map():
        """单击「非记录列」单元格时调用：地图未打开则打开并聚焦该卫星，已打开则仅聚焦。

        覆盖「点击已选中的同一行」这种 itemSelectionChanged 不触发的情况——
        因为单击一定会触发 cellClicked。"""
        rows = table.selectedIndexes()
        if not rows:
            return
        mw = getattr(win, '_map_window', None)
        if mw is None or not mw.isVisible():
            open_map()          # open_map 会读取当前选中行作为初始聚焦卫星
            return
        mw.set_satellite(table.item(rows[0].row(), 0).text())

    def on_auto_toggled(checked):
        """实时开关星历自动更新（与“设置”中的复选框等价）。"""
        s = _load_settings()
        s['sat_auto_update'] = bool(checked)
        _save_settings(s)

    def log_row(row_index):
        """对指定行的卫星，直接把预填记录追加到当前项目（通过 quick_log_callback）。"""
        if row_index < 0 or row_index >= len(last_rows):
            QMessageBox.information(
                win, '记录',
                '请先在表格里点击选中一颗卫星所在的行。')
            return
        r = last_rows[row_index]
        preset = r.get('preset')
        # 提示：该卫星显示名未配置 TQSL/LoTW 映射，记录后名称可能不被 LoTW/TQSL 识别
        if preset and not sp.has_tqsl_mapping(r['name']):
            QMessageBox.warning(
                win, 'TQSL 映射提醒',
                f'卫星「{r["name"]}」未找到 TQSL / LoTW 名称映射，\n'
                f'记录将以原始名称「{preset.get("sat_name", r["name"])}」保存，'
                f'可能不会被 LoTW / TQSL 正确识别。\n'
                f'可点击工具栏「编辑TQSL映射」使用记事本补充该卫星的映射。')
        if quick_log_callback is not None:
            quick_log_callback(preset)
        else:
            QMessageBox.information(
                win, '记录',
                '未设置记录回调，无法自动添加到项目。')

    refresh_btn.clicked.connect(lambda: refresh_tle(force=True))
    obs_btn.clicked.connect(edit_observer)
    sel_btn.clicked.connect(open_select)
    import_tle_btn.clicked.connect(import_tle)
    edit_radio_btn.clicked.connect(edit_radio_dict)
    edit_tqsl_btn.clicked.connect(edit_tqsl_dict)
    mutual_btn.clicked.connect(open_mutual)
    map_btn.clicked.connect(open_map)
    # 行选择变化：仅同步已打开的地图（不开图）；点记录按钮导致行选中也不会误开地图
    table.itemSelectionChanged.connect(_sync_map_if_open)
    # 点击「非记录列」单元格：打开/聚焦地图；第 6 列是「记录」按钮，点它只记录、不开地图
    table.cellClicked.connect(lambda r, c: _focus_or_open_map() if c != 6 else None)
    auto_cb.toggled.connect(on_auto_toggled)
    dur_spin.valueChanged.connect(lambda: (run_prediction() if sats else None, _persist()))
    el_spin.valueChanged.connect(
        lambda: (run_prediction() if sats else None, _persist(), _push_sats_to_map()))
    def _on_start_text(_txt):
        _, err = _parse_start()
        if err and sats:
            status.setText('开始时间格式无效：' + err)
    start_edit.textChanged.connect(_on_start_text)
    start_edit.editingFinished.connect(lambda: run_prediction() if sats else None)

    # 关闭窗口时：先停止后台线程（避免 QThread destroyed while running），再保存设置
    def _on_close(event):
        _persist()
        for attr in ('_worker', '_tle_worker'):
            w = getattr(win, attr, None)
            if w is not None and w.isRunning():
                w.requestInterruption()
                if not w.wait(3000):
                    w.terminate()
                    w.wait()
            setattr(win, attr, None)  # 断开引用，避免后续访问已停止/已删除的线程
        QMainWindow.closeEvent(win, event)
    win.closeEvent = _on_close

    # ---------- 先显示界面，再后台获取 TLE（加速打开） ----------
    win.show()

    # 首次打开：若未设置观测站则引导
    if observer_unset:
        QMessageBox.information(
            win, '设置观测站',
            '尚未设置观测站位置。\n请在弹出的对话框中填写你的 QTH 经纬度与海拔，'
            '否则过境预测不准确。')
        dlg = ObserverDialog(win, 0.0, 0.0, 0.0)  # 默认 0,0
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.get_values()
            if vals:
                lat_, lon_, alt_ = vals
                set_observer(lat_, lon_, alt_)
                s = _load_settings()
                s['m_lat'] = lat_
                s['m_lon'] = lon_
                s['m_alt'] = alt_
                _save_settings(s)

    refresh_tle(force=False)  # 后台获取 TLE 并预测（界面已先显示）
    _open_windows.append(win)  # 保持引用，防止被回收


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    main(None)
