# -*- coding: utf-8 -*-
"""
mutual_window.py —— 双站「通联预测」界面（PySide6）

回答的问题：我（台站 A）和对方（台站 B）在未来一段时间里，
能通过哪些业余卫星互相通联？每次能联多久？

判据：同一时刻卫星对 A 站的仰角 ≥ A 站最低仰角，且对 B 站的仰角
≥ B 站最低仰角（即两站的可见窗口存在交集）。核心解算由
satellite_pred.predict_mutual_passes 完成（底层 skyfield / SGP4）。

入口：
  - 「卫星过境预测」窗口工具栏的「通联预测」按钮（主要入口）；
  - 由 satellite_window.main(..., quick_log_callback=...) 调用，
    记录回调与卫星过境窗口共用，保持预填数据一致。
每行「记录」按钮通过 quick_log_callback(preset) 快速建立日志，
预填卫星名 / 传播模式 / 收发频率 / 时间。
"""

import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QSpinBox,
    QLineEdit, QMessageBox, QFrame, QGroupBox, QAbstractItemView,
    QHeaderView, QDialog,
)
from PySide6.QtCore import QThread, Signal

import satellite_pred as sp
from satellite_window import (
    SatelliteSelectDialog, TleFetchWorker, LOCAL_TZ,
    _load_settings, _save_settings, _duration_str, _utc_to_local_str,
)

# 防止窗口在 main() 返回后被 Python 回收
_open_windows = []


class StationBox(QGroupBox):
    """单个台站的位置 + 最低仰角输入区（支持梅登黑格网格互转）。"""

    dataChanged = Signal()  # 坐标/网格/最低仰角变更时发出，供外部自动重算

    def __init__(self, title, lat, lon, alt, min_el, hint=''):
        super().__init__(title)
        grid = QGridLayout(self)
        grid.setContentsMargins(10, 6, 10, 8)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)

        self.lat_edit = QLineEdit(f'{lat:.5f}')
        self.lon_edit = QLineEdit(f'{lon:.5f}')
        self.alt_edit = QLineEdit(f'{alt:.1f}')
        for ed in (self.lat_edit, self.lon_edit, self.alt_edit):
            ed.setMaximumWidth(96)

        grid.addWidget(QLabel('纬度(°):'), 0, 0)
        grid.addWidget(self.lat_edit, 0, 1)
        grid.addWidget(QLabel('经度(°):'), 0, 2)
        grid.addWidget(self.lon_edit, 0, 3)
        grid.addWidget(QLabel('海拔(m):'), 0, 4)
        grid.addWidget(self.alt_edit, 0, 5)

        self.grid_edit = QLineEdit()
        self.grid_edit.setPlaceholderText('梅登黑格网格，如 PM84')
        self.grid_edit.setMaximumWidth(120)
        try:
            self.grid_edit.setText(sp.latlon_to_maidenhead(lat, lon))
        except Exception:
            pass
        self.el_spin = QSpinBox()
        self.el_spin.setRange(0, 90)
        self.el_spin.setValue(int(min_el))
        self.el_spin.setSuffix(' °')
        self.el_spin.setToolTip('本站的最低可用仰角：低于该仰角认为天线被遮挡 / 信号不可用，不计入可通联时间。')

        grid.addWidget(QLabel('网格:'), 1, 0)
        grid.addWidget(self.grid_edit, 1, 1)
        grid.addWidget(QLabel('最低仰角:'), 1, 4)
        grid.addWidget(self.el_spin, 1, 5)

        if hint:
            lbl = QLabel(hint)
            lbl.setStyleSheet('color: gray;')
            grid.addWidget(lbl, 2, 0, 1, 6)

        # 任意输入变更（坐标/网格编辑完成）都向外发信号，用于自动重算
        self.lat_edit.editingFinished.connect(self._coord_to_grid)
        self.lon_edit.editingFinished.connect(self._coord_to_grid)
        self.alt_edit.editingFinished.connect(self.dataChanged.emit)
        self.grid_edit.editingFinished.connect(self._grid_to_coord)

    # ---- 网格 / 坐标互转 ----
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
        self.dataChanged.emit()

    def _coord_to_grid(self):
        vals = self.get_values()
        if vals is None:
            QMessageBox.warning(self, '输入错误', '请先填写有效的经纬度数字。')
            return
        try:
            self.grid_edit.setText(sp.latlon_to_maidenhead(vals[0], vals[1]))
        except Exception as e:
            QMessageBox.warning(self, '转换失败', str(e))
            return
        self.dataChanged.emit()

    # ---- 取值 ----
    def get_values(self):
        """返回 (lat, lon, alt)；输入非法返回 None。"""
        try:
            return (float(self.lat_edit.text()),
                    float(self.lon_edit.text()),
                    float(self.alt_edit.text()))
        except ValueError:
            return None

    def min_elev(self):
        return self.el_spin.value()

    def grid_text(self):
        """当前网格文本；为空时按经纬度实时推算。"""
        t = self.grid_edit.text().strip()
        if t:
            return t
        vals = self.get_values()
        if vals is None:
            return ''
        try:
            return sp.latlon_to_maidenhead(vals[0], vals[1])
        except Exception:
            return ''


class MutualWorker(QThread):
    """后台计算两站的可通联窗口。"""
    progress = Signal(int)
    done = Signal(list)

    def __init__(self, sats, obs_a, obs_b, start_utc, hours, el_a, el_b):
        super().__init__()
        self.sats = sats
        self.obs_a = obs_a
        self.obs_b = obs_b
        self.start_utc = start_utc
        self.hours = hours
        self.el_a = el_a
        self.el_b = el_b

    def run(self):
        rows = []
        bands = sp.load_sat_radio_dict()
        total = max(len(self.sats), 1)
        for idx, (name, sat) in enumerate(self.sats):
            if self.isInterruptionRequested():
                return
            try:
                wins = sp.predict_mutual_passes(
                    sat, self.obs_a, self.obs_b, self.start_utc,
                    duration_hours=self.hours,
                    min_elev_a=self.el_a, min_elev_b=self.el_b)
            except Exception:
                wins = []
            for w in wins:
                rows.append(self._build_row(w, sp.lookup_transponder(bands, w['name'])))
            self.progress.emit(int((idx + 1) / total * 100))
        rows.sort(key=lambda r: r['start_jd'])
        self.done.emit(rows)

    def _build_row(self, w, band):
        name = w['name']
        local_start = w['start'].astimezone(LOCAL_TZ)
        preset = {
            'sat_name': sp.tqsl_sat_name(name),
            'prop_mode': 'SAT',
            'date': local_start.strftime('%Y-%m-%d'),
            'time': local_start.strftime('%H:%M'),
        }
        if band:
            # 记录时：freq=上行频率(本端发射)，freq_rx=下行频率(本端接收)
            preset['mode'] = band.get('mode', 'FM')
            preset['freq'] = band.get('uplink', '')
            preset['freq_rx'] = band.get('downlink', '')
        return {
            'name': name,
            'start_str': _utc_to_local_str(w['start'], LOCAL_TZ),
            'end_str': _utc_to_local_str(w['end'], LOCAL_TZ),
            'best_str': _utc_to_local_str(w['best_time'], LOCAL_TZ),
            'duration': w['duration_sec'],
            'a_max_elev': w['a_max_elev'],
            'b_max_elev': w['b_max_elev'],
            'a_az': (w['a_az_start'], w['a_az_end']),
            'b_az': (w['b_az_start'], w['b_az_end']),
            'best_min_elev': w['best_min_elev'],
            'clipped': w['clipped_start'] or w['clipped_end'],
            'start_jd': w['start_jd'],
            'preset': preset,
        }


def main(parent_window, quick_log_callback=None, on_selection_change=None):
    settings = _load_settings()

    # 台站 A 默认取「本站」位置（观测站设置 / 设置页写入的 m_lat/m_lon/m_alt）
    a_lat = float(settings.get('m_lat', 0.0) or 0.0)
    a_lon = float(settings.get('m_lon', 0.0) or 0.0)
    a_alt = float(settings.get('m_alt', 0.0) or 0.0)
    # 台站 A 的最低仰角与「卫星过境预测」窗口共用 sat_el，始终保持一致
    a_el = int(settings.get('sat_el', 10) or 10)

    # 台站 B 默认取上次填写的对方台站位置（设置里记住）；首次或清空后为空
    b_lat = float(settings.get('sat_b_lat', 0.0) or 0.0)
    b_lon = float(settings.get('sat_b_lon', 0.0) or 0.0)
    b_alt = float(settings.get('sat_b_alt', 0.0) or 0.0)
    b_el = int(settings.get('sat_mu_el_b', settings.get('sat_el', 10)) or 10)

    # 默认预测时长与「卫星过境预测」窗口保持一致（共用 sat_dur 设置）
    mu_dur = int(sp.clamp_predict_hours(settings.get('sat_dur', 24) or 24))
    # 自选卫星列表共用 sat_sats；兼容旧版 sat_mu_sats
    mu_sats_raw = settings.get('sat_sats', None)
    if mu_sats_raw is None:
        mu_sats_raw = settings.get('sat_mu_sats', None)

    win = QMainWindow()
    win.resize(1000, 660)
    win.setWindowTitle('通联预测')
    win._map_window = None  # 卫星地图窗口引用（由“地图”按钮打开）
    central = QWidget()
    win.setCentralWidget(central)
    layout = QVBoxLayout(central)

    # ---------- 台站位置 ----------
    sta_row = QHBoxLayout()
    box_a = StationBox('台站 A（本站）', a_lat, a_lon, a_alt, a_el,
                       hint='默认取“观测站设置”里的本站位置，可临时修改。')
    box_b = StationBox('台站 B（对方）', b_lat, b_lon, b_alt, b_el,
                       hint='填写对方 QTH：可直接填经纬度或梅登黑格网格，编辑完成后自动同步。')
    sta_row.addWidget(box_a)
    sta_row.addWidget(box_b)
    layout.addLayout(sta_row)

    # ---------- 预测参数 ----------
    par_grp = QGroupBox('预测参数')
    par = QHBoxLayout(par_grp)
    start_edit = QLineEdit()
    start_edit.setText(datetime.datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M'))
    start_edit.setPlaceholderText('YYYY-MM-DD HH:MM')
    start_edit.setMinimumWidth(150)
    start_edit.setToolTip('预测起始时刻（系统本地时间），默认当前时间，支持 YYYY-MM-DD HH:MM 或带秒。')

    dur_spin = QSpinBox()
    dur_spin.setRange(sp.MIN_PREDICT_HOURS, sp.MAX_PREDICT_HOURS)
    dur_spin.setValue(mu_dur)
    dur_spin.setToolTip('预测时间跨度，最长 %d 小时（10 天）。'
                        % sp.MAX_PREDICT_HOURS)

    sel_btn = QPushButton('选择卫星…')

    refresh_btn = QPushButton('刷新TLE')

    par.addWidget(QLabel('开始时间:'))
    par.addWidget(start_edit)
    par.addSpacing(10)
    par.addWidget(QLabel('预测时长(小时):'))
    par.addWidget(dur_spin)
    par.addSpacing(10)
    par.addWidget(sel_btn)
    par.addStretch(1)
    par.addWidget(refresh_btn)
    map_btn = QPushButton('卫星地图')
    map_btn.setToolTip(
        '打开全球卫星地图：显示所有已选卫星（与上方“范围/自选卫星”实时同步）'
        '自当前时刻起的地面轨迹与实时位置，以及本台站与对方台站。\n'
        '在结果表中点选一行，该卫星会在地图上聚焦高亮。')
    par.addWidget(map_btn)
    layout.addWidget(par_grp)

    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFrameShadow(QFrame.Sunken)
    layout.addWidget(sep)

    status = QLabel('准备中…')
    status.setStyleSheet('color: gray;')
    layout.addWidget(status)

    # ---------- 结果表 ----------
    headers = ['卫星', '可通联开始(本地)', '可通联结束(本地)', '可通联时长',
               'A最大仰角', 'B最大仰角', '最佳时刻(本地)', '记录']
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    for col, wdt in enumerate((180, 135, 135, 95, 85, 85, 135, 70)):
        table.setColumnWidth(col, wdt)
    layout.addWidget(table)

    sats = []
    last_rows = []
    selected_names = (set(mu_sats_raw)
                      if isinstance(mu_sats_raw, list) and mu_sats_raw
                      else None)

    # ---------- 逻辑 ----------
    def _persist():
        s = _load_settings()
        vb = box_b.get_values()
        if vb is not None:
            s['sat_b_lat'], s['sat_b_lon'], s['sat_b_alt'] = vb
        # 台站 A 的最低仰角同步写回 sat_el（与「卫星过境预测」共享，始终保持一致）
        s['sat_el'] = box_a.min_elev()
        s['sat_mu_el_b'] = box_b.min_elev()
        # 预测时长与「卫星过境预测」共用 sat_dur，保证两者默认一致
        s['sat_dur'] = int(sp.clamp_predict_hours(dur_spin.value()))
        s['sat_filter'] = '自选卫星'
        s['sat_sats'] = sorted(selected_names) if selected_names is not None else None
        _save_settings(s)

    def _parse_start():
        txt = start_edit.text().strip()
        for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
            try:
                return datetime.datetime.strptime(txt, fmt), None
            except ValueError:
                continue
        return None, ('格式应为 YYYY-MM-DD HH:MM（例如 2026-08-02 17:45），当前输入：'
                      + (txt or '（空）'))

    def active_sats_list():
        """返回当前自选卫星列表，预测与地图共用同一份。"""
        if selected_names is None:
            return []
        return [(n, s) for (n, s) in sats if n in selected_names]

    def _push_sats_to_map():
        """把当前「已选卫星」与台站 A / B 最低仰角同步给已打开的地图窗口。"""
        mw = getattr(win, '_map_window', None)
        if mw is None:
            return
        mw.set_sats(active_sats_list())
        mw.set_min_elev(box_a.min_elev())
        mw.set_min_elev_b(box_b.min_elev())

    def populate(rows):
        last_rows[:] = rows
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            name_item = QTableWidgetItem(r['name'])
            name_item.setToolTip(
                'A 站方位 %.0f°→%.0f°\nB 站方位 %.0f°→%.0f°\n'
                '最佳时刻两站仰角较低者：%.1f°'
                % (r['a_az'][0], r['a_az'][1], r['b_az'][0], r['b_az'][1],
                   r['best_min_elev']))
            table.setItem(i, 0, name_item)
            start_txt = r['start_str'] + ('（截断）' if r['clipped'] else '')
            table.setItem(i, 1, QTableWidgetItem(start_txt))
            table.setItem(i, 2, QTableWidgetItem(r['end_str']))
            table.setItem(i, 3, QTableWidgetItem(_duration_str(r['duration'])))
            table.setItem(i, 4, QTableWidgetItem(f"{r['a_max_elev']:.1f}°"))
            table.setItem(i, 5, QTableWidgetItem(f"{r['b_max_elev']:.1f}°"))
            table.setItem(i, 6, QTableWidgetItem(r['best_str']))
            btn = QPushButton('记录')
            btn.setToolTip('打开批量记录窗口并预填该卫星的卫星名/传播模式/收发频率等信息')
            btn.clicked.connect(lambda _checked=False, i=i: log_row(i))
            table.setCellWidget(i, 7, btn)
        table.scrollToTop()

    def run_prediction():
        """按当前两站位置/最低仰角/时长重新计算可通联窗口。

        任何数据变化（坐标、网格、最低仰角、时长、范围、开始时间）都会自动调用
        本函数；无有效 TLE、坐标缺失或非法时仅在状态栏提示，不弹窗（避免自动
        重算时频繁打断用户）。"""
        nonlocal selected_names
        _persist()  # 先把当前设置落盘（含可能刚改动的台站/仰角/时长）
        if not sats:
            status.setText('没有可用的卫星数据，请先“刷新TLE”。')
            return
        va = box_a.get_values()
        vb = box_b.get_values()
        if va is None or vb is None:
            status.setText('两个台站的经纬度/海拔必须都是有效数字。')
            return
        if va[0] == 0.0 and va[1] == 0.0:
            status.setText('台站 A（本站）尚未设置位置，请在“卫星过境预测 → 观测站设置”中填写并保存。')
            return
        if vb[0] == 0.0 and vb[1] == 0.0:
            status.setText('台站 B（对方）尚未设置位置，请填写对方 QTH 或网格后自动开始预测。')
            return

        start_local, err = _parse_start()
        if err:
            status.setText('开始时间无效：' + err)
            table.setRowCount(0)
            return
        start = start_local.replace(tzinfo=LOCAL_TZ).astimezone(datetime.timezone.utc)

        hours = sp.clamp_predict_hours(dur_spin.value())
        if dur_spin.value() != int(hours):
            dur_spin.blockSignals(True)
            dur_spin.setValue(int(hours))
            dur_spin.blockSignals(False)

        active_sats = active_sats_list()
        if not selected_names:
            status.setText('尚未选择卫星，请点击“选择卫星…”勾选。')
            table.setRowCount(0)
            _push_sats_to_map()
            return

        old = getattr(win, '_worker', None)
        if old is not None and old.isRunning():
            old.requestInterruption()
            old.wait(3000)

        dist = sp.great_circle_km(va[0], va[1], vb[0], vb[1])
        status.setText('正在计算两地可通联窗口（%d 颗卫星，跨度 %d 小时%s）…'
                       % (len(active_sats), int(hours),
                          '，可能较慢' if hours > 72 else ''))
        worker = MutualWorker(active_sats, va, vb, start, hours,
                              box_a.min_elev(), box_b.min_elev())
        win._worker = worker

        def on_progress(v):
            status.setText('正在计算两地可通联窗口… %d%%' % v)

        def on_done(rows):
            if getattr(win, '_worker', None) is worker:
                win._worker = None
            populate(rows)
            total = sum(r['duration'] for r in rows)
            status.setText(
                'A 纬%.3f° 经%.3f°（≥%d°） ｜ B 纬%.3f° 经%.3f°（≥%d°） ｜ 地面距离 %.0f km'
                ' ｜ 卫星 %d 颗 ｜ 可通联窗口 %d 个 ｜ 累计 %s'
                % (va[0], va[1], box_a.min_elev(), vb[0], vb[1], box_b.min_elev(),
                   dist, len(active_sats), len(rows), _duration_str(total)))
            if not rows:
                status.setText(status.text() + '（可尝试降低最低仰角或延长预测时长）')

        worker.progress.connect(on_progress)
        worker.done.connect(on_done)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        # 台站 A / B 位置、已选卫星、最低仰角变化，实时同步到已打开的地图窗口
        mw = getattr(win, '_map_window', None)
        if mw is not None:
            mw.set_stations(home=va, station_b=vb)
            mw.set_min_elev_b(box_b.min_elev())
            _push_sats_to_map()

    def refresh_tle(force=False, then_predict=True):
        nonlocal sats
        status.setText('正在获取业余卫星 TLE…')
        refresh_btn.setEnabled(False)
        old = getattr(win, '_tle_worker', None)
        if old is not None and old.isRunning():
            old.requestInterruption()
            old.wait(3000)
        worker = TleFetchWorker(force)
        win._tle_worker = worker

        def on_fetched(s):
            nonlocal sats, selected_names
            if getattr(win, '_tle_worker', None) is worker:
                win._tle_worker = None
            sats = s
            if selected_names is None:
                open_select()
                if selected_names is None:
                    selected_names = set()
            refresh_btn.setEnabled(True)
            status.setText('已载入 TLE，共 %d 颗卫星。' % len(sats))
            # 若地图窗口已打开，同步最新的「已选卫星」列表（名称/轨道根数）
            _push_sats_to_map()
            if then_predict:
                va, vb = box_a.get_values(), box_b.get_values()
                if (va and vb and not (va[0] == 0.0 and va[1] == 0.0)
                        and not (vb[0] == 0.0 and vb[1] == 0.0)):
                    run_prediction()
                else:
                    status.setText('已载入 TLE，共 %d 颗卫星。请填写两个台站的位置（坐标或网格）后自动开始预测。'
                                   % len(sats))

        def on_warning(w):
            status.setText(w)

        def on_error(e):
            if getattr(win, '_tle_worker', None) is worker:
                win._tle_worker = None
            refresh_btn.setEnabled(True)
            table.setRowCount(0)
            QMessageBox.warning(win, 'TLE 获取失败', e)

        worker.fetched.connect(on_fetched)
        worker.warning.connect(on_warning)
        worker.error.connect(on_error)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def open_select():
        nonlocal selected_names
        if not sats:
            QMessageBox.information(win, '暂无卫星', '请先刷新 TLE。')
            return
        dlg = SatelliteSelectDialog(win, [n for (n, s) in sats], selected_names)
        if dlg.exec() == QDialog.Accepted:
            selected_names = dlg.get_selected()
            _persist()
            run_prediction()  # 选择卫星后自动重新预测
            _push_sats_to_map()   # 自选卫星变化 → 地图同步显示新的一批卫星
            # 把选择实时同步回卫星过境预测窗口（若该窗口仍打开）
            if on_selection_change is not None:
                on_selection_change('自选卫星', selected_names)

    def apply_remote_selection(filter_mode, sel):
        """由「卫星过境预测」窗口反向同步：更新范围/自选卫星并重新预测。

        刻意不调用 on_selection_change 回弹，避免两个窗口互相触发形成循环。"""
        nonlocal selected_names
        selected_names = sel
        if sats:
            run_prediction()
        _push_sats_to_map()

    def open_map():
        """打开卫星地图窗口：显示「所有已选卫星」的地面轨迹 / 实时位置，以及
        台站 A（本台）、台站 B（对方）位置。

        - 卫星范围与本窗口的「范围 / 自选卫星」实时同步；
        - 在表格里点选某颗卫星，该星在地图上聚焦高亮；
        - 地图的「轨迹时长」会记住上次的设置，并与卫星过境预测打开的地图共用。"""
        import satellite_map_window

        name = None
        rows = table.selectedIndexes()
        if rows:
            name = table.item(rows[0].row(), 0).text()
        if not name and last_rows:
            name = last_rows[0]['name']
        va = box_a.get_values()
        vb = box_b.get_values()
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
            """地图内调整最低仰角后，回写到本窗口两个台站并重新预测 / 落盘。"""
            box_a.el_spin.blockSignals(True)
            box_a.el_spin.setValue(int(round(a)))
            box_a.el_spin.blockSignals(False)
            box_b.el_spin.blockSignals(True)
            box_b.el_spin.setValue(int(round(b)))
            box_b.el_spin.blockSignals(False)
            _persist()
            run_prediction()

        mw = satellite_map_window.open_map(
            win, active_sats_list(),
            home=va if va else None,
            station_b=vb if vb else None,
            selected_name=name, source=win, min_elev=box_a.min_elev(),
            min_elev_b=box_b.min_elev(), on_min_elev_change=on_el_change)
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

    def log_row(row_index):
        if row_index < 0 or row_index >= len(last_rows):
            QMessageBox.information(win, '记录', '请先在表格里选中一行。')
            return
        r = last_rows[row_index]
        preset = r.get('preset')
        if preset and not sp.has_tqsl_mapping(r['name']):
            QMessageBox.warning(
                win, 'TQSL 映射提醒',
                f'卫星「{r["name"]}」未找到 TQSL / LoTW 名称映射，\n'
                f'记录将以原始名称「{preset.get("sat_name", r["name"])}」保存，'
                f'可能不会被 LoTW / TQSL 正确识别。\n'
                f'可在「卫星过境预测」窗口的「编辑TQSL映射」中使用记事本补充。')
        if quick_log_callback is not None:
            quick_log_callback(preset)
        else:
            QMessageBox.information(win, '记录', '未设置记录回调，无法自动添加到项目。')

    def _on_start_text(_txt):
        _, err = _parse_start()
        if err and sats:
            status.setText('开始时间格式无效：' + err)

    refresh_btn.clicked.connect(lambda: refresh_tle(force=True))
    sel_btn.clicked.connect(open_select)
    map_btn.clicked.connect(open_map)
    # 行选择变化：仅同步已打开的地图（不开图）；点记录按钮导致行选中也不会误开地图
    table.itemSelectionChanged.connect(_sync_map_if_open)
    # 点击「非记录列」单元格：打开/聚焦地图；第 7 列是「记录」按钮，点它只记录、不开地图
    table.cellClicked.connect(lambda r, c: _focus_or_open_map() if c != 7 else None)
    # 任何数据变化都自动重新预测（不再有“开始预测”按钮）
    dur_spin.valueChanged.connect(lambda: run_prediction() if sats else None)
    box_a.el_spin.valueChanged.connect(lambda: run_prediction() if sats else None)
    box_b.el_spin.valueChanged.connect(lambda: run_prediction() if sats else None)
    box_a.dataChanged.connect(lambda: run_prediction() if sats else None)
    box_b.dataChanged.connect(lambda: run_prediction() if sats else None)
    start_edit.editingFinished.connect(lambda: run_prediction() if sats else None)
    start_edit.textChanged.connect(_on_start_text)

    def _on_close(event):
        _persist()
        for attr in ('_worker', '_tle_worker'):
            w = getattr(win, attr, None)
            if w is not None and w.isRunning():
                w.requestInterruption()
                if not w.wait(3000):
                    w.terminate()
                    w.wait()
            setattr(win, attr, None)
        QMainWindow.closeEvent(win, event)
    win.closeEvent = _on_close

    win.show()
    # 暴露反向同步接口，供「卫星过境预测」窗口在改选卫星时调用
    win.apply_remote_selection = apply_remote_selection
    if a_lat == 0.0 and a_lon == 0.0:
        QMessageBox.information(
            win, '未设置本站位置',
            '台站 A（本站）尚未设置位置。\n'
            '可在「卫星过境预测 → 观测站设置」中填写并保存，也可在本窗口临时填写。')
    refresh_tle(force=False)
    _open_windows.append(win)


if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    main(None)
    app.exec()
