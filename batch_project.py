from PySide6.QtWidgets import *
from PySide6.QtCore import Qt
import call_upper
import time as time_
import sys
import re
import os
import fhl_rw

translation_dict = {
                'date': '日期',
                'time': '时间',
                'm_call': '己方呼号',
                'o_call': '对方呼号',
                'freq': '频率',
                'freq_rx': '接收频率',
                'prop_mode': '传播方式',
                'sat_name': '卫星名称',
                'mode': '调制模式',
                'm_rst': '己方接收信号','o_rst': '对方接收信号',
                'm_qth': '己方QTH','o_qth': '对方QTH',
                "m_dig": '己方设备','o_dig': '对方设备',
                'm_ant': '己方天线','o_ant': '对方天线',
                'm_pow': '己方功率','o_pow': '对方功率',
                'notes': '备注'
            }

# 行顺序（即字段键顺序）
KEYS = list(translation_dict.keys())
# 每条日志必须满足的必填字段
REQUIRED_KEYS = ('m_call', 'o_call', 'freq', 'mode', 'm_rst', 'o_rst')

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
TIME_RE = re.compile(r'^\d{2}:\d{2}$')


class FrozenTableWidget(QTableWidget):
    """第一列（模板列）冻结在左侧，类似 Excel 的冻结窗格。"""

    def __init__(self, rows, cols, parent=None):
        super().__init__(rows, cols, parent)
        # 冻结层：用 QTableView 共享主表 model，仅显示第 0 列
        self._frozen = QTableView(self)
        self._frozen.setModel(self.model())
        self._frozen.verticalHeader().hide()
        self._frozen.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self._frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._frozen.setFocusPolicy(Qt.NoFocus)
        self._frozen.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._frozen.setStyleSheet("QTableView{ border:none; background-color:#f3f3f3; }")
        self.viewport().stackUnder(self._frozen)
        self._frozen.raise_()
        self._frozen.show()
        # 第 0 列宽度跟随主表
        self.horizontalHeader().sectionResized.connect(
            lambda i, _, w: self._frozen.setColumnWidth(0, w) if i == 0 else None)
        self.sync_frozen_columns()
        # 垂直滚动同步（双向，带防抖）
        self._syncing = False
        self.verticalScrollBar().valueChanged.connect(self._sync_from_main)
        self._frozen.verticalScrollBar().valueChanged.connect(self._sync_from_frozen)

    def sync_frozen_columns(self):
        """冻结层只显示第 0 列，并同步其宽度（横向表头标签由共享 model 提供）。"""
        for c in range(self.columnCount()):
            self._frozen.setColumnHidden(c, c != 0)
        self._frozen.setColumnWidth(0, self.columnWidth(0))

    def updateFrozenGeometry(self):
        hh = self.horizontalHeader().height()
        vhw = self.verticalHeader().width()
        # 冻结层从窗口顶部(y=0)开始，高度覆盖「表头+视口」，
        # 使其横向表头与各行都与主表精确对齐（类似 Excel 冻结首列）。
        self._frozen.setGeometry(vhw, 0, self.columnWidth(0), hh + self.viewport().height())
        self.sync_frozen_columns()

    def set_frozen(self, on):
        self._frozen.setVisible(on)
        if on:
            self.updateFrozenGeometry()
            # 重新显示后需置顶，否则会落到主表视口后面导致"失效"
            self._frozen.raise_()

    def _sync_from_main(self, val):
        if self._syncing:
            return
        self._syncing = True
        self._frozen.verticalScrollBar().setValue(val)
        self._syncing = False

    def _sync_from_frozen(self, val):
        if self._syncing:
            return
        self._syncing = True
        self.verticalScrollBar().setValue(val)
        self._syncing = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateFrozenGeometry()

    def showEvent(self, event):
        super().showEvent(event)
        self.updateFrozenGeometry()


def main(window, preset=None, on_saved=None):
    window.resize(1000, 750)
    window.setWindowTitle('批量记录')

    with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
        xml_dict = eval(f.read())

    date = time_.strftime("%Y-%m-%d", time_.localtime())
    time = time_.strftime("%H:%M", time_.localtime())

    app_list = {
                'date': date,
                'time': time,
                'm_call': xml_dict['m_call'].upper(),
                'o_call': '',
                'freq': '',
                'freq_rx': '',
                'mode': '',
                'prop_mode': '',
                'sat_name': '',
                'm_rst': '59',
                'o_rst': '59',
                'm_qth': xml_dict['m_qth'],
                'o_qth': '',
                "m_dig": xml_dict['m_dig'],
                'o_dig': '',
                'm_ant': '',
                'o_ant': '',
                'm_pow': '',
                'o_pow': '',
                'notes': ''
            }

    # 若由卫星窗口等外部调用并传入预填数据，则用其覆盖对应字段
    # （其余字段如 m_call/o_call/m_qth 仍取自设置，保持默认）
    if preset:
        for k in ('date', 'time', 'freq', 'freq_rx', 'mode', 'prop_mode', 'sat_name',
                  'm_qth', 'o_qth', 'o_call', 'notes'):
            v = preset.get(k)
            if v not in (None, ''):
                app_list[k] = v

    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)

    label = QLabel('第一列为模板（默认值），后续每列为一条日志；日期/时间为空时自动填充当前时间。')
    label.setAlignment(Qt.AlignCenter)
    layout.addWidget(label)

    # 选项区：冻结模板列开关（默认开启，类似 Excel 冻结首列）
    opt_row = QHBoxLayout()
    opt_row.setSpacing(10)
    cb_freeze = QCheckBox('固定模板列')
    cb_freeze.setChecked(True)
    opt_row.addWidget(cb_freeze)
    opt_row.addStretch(1)
    layout.addLayout(opt_row)

    # 表格：行=字段，列0=模板，初始无日志列（默认不要日志）
    table = FrozenTableWidget(len(KEYS), 1)
    table.setVerticalHeaderLabels(list(translation_dict.values()))
    # 行高与 project.py 主表一致：使用 Qt 默认行高，不设自定义值

    # 冻结模板列开关（默认开启）；在 table 创建后再连接
    cb_freeze.toggled.connect(table.set_frozen)

    def refresh_headers():
        headers = ['模板'] + [f'第{i}条' for i in range(1, table.columnCount())]
        table.setHorizontalHeaderLabels(headers)

    # 初始填充：仅模板列（默认值）
    for r in range(len(KEYS)):
        table.setItem(r, 0, QTableWidgetItem(app_list[KEYS[r]]))
    refresh_headers()
    # 默认选中最后一列（初始即模板列）
    table.setCurrentCell(0, table.columnCount() - 1)

    # 列宽
    table.setColumnWidth(0, 150)

    # 己方呼号(行2)与对方呼号(行3)单元格编辑时实时转大写
    _call_del = call_upper.UpperCallDelegate()
    table.setItemDelegateForRow(2, _call_del)
    table.setItemDelegateForRow(3, _call_del)
    table._upper_call_delegate = _call_del  # 保持引用，防止被回收
    # 冻结层同样挂委托（共享 model，模板列在此编辑）
    table._frozen.setItemDelegateForRow(2, _call_del)
    table._frozen.setItemDelegateForRow(3, _call_del)
    table._frozen._upper_call_delegate = _call_del

    layout.addWidget(table)

    def add_log_column():
        """在末尾新增一条日志列，内容复制当前模板列的值，并跳转到该列。"""
        c = table.columnCount()
        table.insertColumn(c)
        for r in range(table.rowCount()):
            v = table.item(r, 0).text() if table.item(r, 0) is not None else ''
            table.setItem(r, c, QTableWidgetItem(v))
        table.setColumnWidth(c, 120)
        refresh_headers()
        table.updateFrozenGeometry()
        # 默认回到最后一列（新增加的日志列）
        table.setCurrentCell(0, c)

    def delete_current_column():
        """删除当前选中的日志列（模板列不可删）。"""
        c = table.currentColumn()
        if c < 1:
            QMessageBox.warning(window, '提示', '请先选中要删除的日志列（模板列不可删除）。')
            return
        col_label = (table.horizontalHeaderItem(c).text()
                     if table.horizontalHeaderItem(c) is not None else f'第{c}条')
        reply = QMessageBox.question(window, '确认删除',
                                    f'确定要删除「{col_label}」吗？该列内容将丢失。',
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        table.removeColumn(c)
        refresh_headers()
        table.updateFrozenGeometry()

    def collect_and_validate():
        """从日志列（列>=1）收集记录，返回 (records, error_msg)。"""
        records = []
        for c in range(1, table.columnCount()):
            col_label = (table.horizontalHeaderItem(c).text()
                         if table.horizontalHeaderItem(c) is not None else f'第{c}条')
            rec = {}
            empty = True
            for r in range(table.rowCount()):
                v = table.item(r, c).text() if table.item(r, c) is not None else ''
                rec[KEYS[r]] = v
                if v != '':
                    empty = False
            if empty:
                continue  # 整列空白视为未填写，跳过
            # 日期/时间为空则自动填充当前时间
            if rec['date'] == '':
                rec['date'] = time_.strftime("%Y-%m-%d", time_.localtime())
            if rec['time'] == '':
                rec['time'] = time_.strftime("%H:%M", time_.localtime())
            # 校验
            if rec['date'] != '' and not DATE_RE.search(rec['date']):
                return None, f'{col_label} 日期格式错误，应为YYYY-MM-DD'
            if rec['time'] != '' and not TIME_RE.search(rec['time']):
                return None, f'{col_label} 时间格式错误，应为HH:MM'
            for k in REQUIRED_KEYS:
                if rec[k] == '':
                    return None, f'{col_label} 缺少 {translation_dict[k]} (必填)'
            records.append(rec)
        return records, ''

    def save_all():
        records, err = collect_and_validate()
        if err:
            QMessageBox.warning(window, '格式错误', err)
            return
        if not records:
            QMessageBox.warning(window, '提示', '没有可保存的记录（日志列均为空）。')
            return

        fhl_list = records  # 供下方保存逻辑使用（与旧逻辑保持一致）

        # 若由卫星窗口（项目界面）传入 on_saved，则直接追加到项目文件，不弹保存方式选择
        if on_saved is not None:
            try:
                on_saved(fhl_list)
                QMessageBox.information(window, '完成',
                                        f'已添加 {len(fhl_list)} 条记录到当前项目。')
            except Exception as e:
                QMessageBox.warning(window, '保存失败',
                                    f'添加到项目失败：\n{e}')
            window.close()
            return

        if not fhl_list:
            QMessageBox.warning(window, "提示", "没有可保存的记录。")
            return

        def save_records_to_path(records, save_path, key=None):
            fhl_rw.write_fhl_file(save_path, records, key)

        def load_records_from_path(load_path):
            if not os.path.exists(load_path):
                return [], None
            data, key = fhl_rw.read_fhl_file(load_path)
            return data, key

        finish_dialog = QDialog(window)
        finish_dialog.setWindowTitle('批量记录完成')
        finish_dialog.resize(520, 120)
        finish_dialog.setFixedSize(520, 120)
        finish_dialog.setModal(True)

        finish_layout = QVBoxLayout(finish_dialog)
        finish_layout.setSpacing(12)

        title_label = QLabel('请选择保存方式：')
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet('font-size: 12pt; font-weight: bold;')
        finish_layout.addWidget(title_label)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.setContentsMargins(0, 0, 0, 0)

        def add_to_project():
            project_path, _ = QFileDialog.getOpenFileName(
                finish_dialog,
                '添加到 F HamLog项目',
                '',
                'F HamLog项目 (*.fhl)'
            )
            if project_path == '':
                return
            records, key = load_records_from_path(project_path)
            records.extend(fhl_list)
            save_records_to_path(records, project_path, key)
            QMessageBox.information(finish_dialog, '完成', f'已添加 {len(fhl_list)} 条记录到项目。')
            finish_dialog.accept()

        def save_as_project():
            save_path, _ = QFileDialog.getSaveFileName(
                finish_dialog,
                '另存为 F HamLog项目',
                '',
                'F HamLog项目 (*.fhl)'
            )
            if save_path == '':
                return
            save_records_to_path(fhl_list, save_path)
            QMessageBox.information(finish_dialog, '完成', f'已另存为项目文件：{save_path}')
            finish_dialog.accept()

        def add_to_default_log():
            default_path = os.path.join('file', 'main.fhl')
            records, key = load_records_from_path(default_path)
            records.extend(fhl_list)
            save_records_to_path(records, default_path, key)
            QMessageBox.information(finish_dialog, '完成', f'已添加 {len(fhl_list)} 条记录到默认通联日志')
            finish_dialog.accept()

        btn_project = QPushButton('添加到 F HamLog 项目')
        btn_project.setMinimumHeight(36)
        btn_project.clicked.connect(add_to_project)
        action_row.addWidget(btn_project)

        btn_save_as = QPushButton('另存为 F HamLog 项目')
        btn_save_as.setMinimumHeight(36)
        btn_save_as.clicked.connect(save_as_project)
        action_row.addWidget(btn_save_as)

        btn_default = QPushButton('添加到默认通联日志')
        btn_default.setMinimumHeight(36)
        btn_default.clicked.connect(add_to_default_log)
        action_row.addWidget(btn_default)

        finish_layout.addLayout(action_row)

        cancel_button = QPushButton('取消')
        cancel_button.clicked.connect(finish_dialog.reject)
        finish_layout.addWidget(cancel_button, alignment=Qt.AlignRight)

        finish_dialog.exec()

    # 按钮区
    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    button_add = QPushButton('添加日志列')
    button_add.setMinimumHeight(34)
    button_add.clicked.connect(add_log_column)

    button_del = QPushButton('删除当前列')
    button_del.setMinimumHeight(34)
    button_del.clicked.connect(delete_current_column)

    button_save = QPushButton('完成')
    button_save.setMinimumHeight(34)
    button_save.clicked.connect(save_all)

    btn_row.addWidget(button_add)
    btn_row.addWidget(button_del)
    btn_row.addStretch(1)
    btn_row.addWidget(button_save)

    layout.addLayout(btn_row)

    window.show()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    main(win)
    app.exec()
