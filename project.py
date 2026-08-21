from PySide6.QtWidgets import *
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt  # 新增导入 Qt
from dialog_defaults import desktop_dir
from functools import partial
import time as time_
import sys
import os
import re
import subprocess
import webbrowser
import urllib.parse
import fhl_rw
import copy
import call_upper

# 复制/粘贴使用的字段顺序（与表格列对应，英文键名作为剪贴板表头，便于跨窗口/跨软件解析）
COPY_FIELDS = ['date', 'time', 'm_call', 'o_call', 'freq', 'freq_rx', 'mode',
               'prop_mode', 'sat_name', 'm_rst', 'o_rst', 'm_qth', 'o_qth',
               'm_dig', 'o_dig', 'm_ant', 'o_ant', 'm_pow', 'o_pow', 'notes']
# 字段 -> 中文表头（粘贴时兼容中文表头）
FIELD_LABELS = {
    'date': '日期', 'time': '时间', 'm_call': '己方呼号', 'o_call': '对方呼号',
    'freq': '频率', 'freq_rx': '接收频率', 'mode': '调制模式', 'prop_mode': '传播方式',
    'sat_name': '卫星名称', 'm_rst': '己方接收信号', 'o_rst': '对方接收信号',
    'm_qth': '己方QTH', 'o_qth': '对方QTH', 'm_dig': '己方设备', 'o_dig': '对方设备',
    'm_ant': '己方天线', 'o_ant': '对方天线', 'm_pow': '己方功率', 'o_pow': '对方功率',
    'notes': '备注'
}

file = None
key = None
_open_windows = []  # 保持由本模块打开的卫星批量记录窗口引用，防止被回收

def _ensure_log_keys(entry):
    # 确保单条记录包含新加的字段
    for k in ['freq_rx', 'prop_mode', 'sat_name']:
        if k not in entry:
            entry[k] = ''


def _upgrade_file_records(file_list):
    if not file_list:
        return
    for e in file_list:
        _ensure_log_keys(e)

def main(window, filee='', save_path='',key_ = None,quick_poject=False):
    global file,key
    key = key_
    if isinstance(filee, list):
        file = filee
        _upgrade_file_records(file)
        # 打开项目时自动校验所有呼号（己方 m_call 与对方 o_call），统一转为大写
        for _rec in file:
            if 'm_call' in _rec:
                _rec['m_call'] = _rec['m_call'].upper()
            if 'o_call' in _rec:
                _rec['o_call'] = _rec['o_call'].upper()
    else:
        file = []
    table = None
    undo_stack = []   # 撤销栈：保存 file 的完整深拷贝快照
    redo_stack = []   # 重做栈

    # ---------- 撤销 / 重做 / 复制 / 粘贴 ----------
    def snapshot_before():
        # 在修改 file 之前调用，记录当前完整状态到撤销栈（深拷贝，避免后续修改污染快照）
        undo_stack.append(copy.deepcopy(file))
        if len(undo_stack) > 300:
            undo_stack.pop(0)
        redo_stack.clear()

    def undo():
        global file
        if not undo_stack:
            QMessageBox.information(window, "撤销", "没有可撤销的操作。")
            return
        redo_stack.append(copy.deepcopy(file))
        file = undo_stack.pop()
        table_update()

    def redo():
        global file
        if not redo_stack:
            QMessageBox.information(window, "重做", "没有可重做的操作。")
            return
        undo_stack.append(copy.deepcopy(file))
        file = redo_stack.pop()
        table_update()

    def get_selected_row_indexes():
        # 优先返回“选择”列勾选的行；若都没有勾选，则回退到表格当前选中的行
        result = []
        if table is None:
            return result
        for row in range(table.rowCount()):
            cell_w = table.cellWidget(row, 0)
            if cell_w is not None:
                cb = cell_w.findChild(QCheckBox)
                if cb is not None and cb.isChecked():
                    result.append(row)
        if result:
            return result
        for idx in table.selectionModel().selectedRows():
            result.append(idx.row())
        return result

    def copy_records_to_clipboard(records):
        if not records:
            return False
        lines = ['\t'.join(COPY_FIELDS)]
        for rec in records:
            lines.append('\t'.join(str(rec.get(k, '')) for k in COPY_FIELDS))
        QApplication.clipboard().setText('\n'.join(lines))
        return True

    def copy_from_main():
        rows = get_selected_row_indexes()
        if not rows:
            QMessageBox.information(window, "复制", "请先勾选或选中要复制的行。")
            return
        records = [file[r] for r in rows]
        if copy_records_to_clipboard(records):
            QMessageBox.information(window, "复制", f"已复制 {len(records)} 条日志到剪贴板。")

    def paste_to_main():
        text = QApplication.clipboard().text()
        if not text or not text.strip():
            QMessageBox.information(window, "粘贴", "剪贴板为空或不是文本。")
            return
        lines = [ln for ln in text.replace('\r\n', '\n').split('\n') if ln != '']
        if not lines:
            return
        header = [h.strip() for h in lines[0].split('\t')]
        label_to_field = {v: k for k, v in FIELD_LABELS.items()}
        field_index = {}
        for i, h in enumerate(header):
            if h in COPY_FIELDS:
                field_index[h] = i
            elif h in label_to_field:
                field_index[label_to_field[h]] = i
        if not field_index:
            QMessageBox.warning(window, "粘贴", "剪贴板内容无法识别为日志数据。")
            return
        new_records = []
        for ln in lines[1:]:
            cells = ln.split('\t')
            rec = {k: '' for k in COPY_FIELDS}
            for fld, idx in field_index.items():
                if idx < len(cells):
                    rec[fld] = cells[idx]
            new_records.append(rec)
        if not new_records:
            return
        snapshot_before()
        file.extend(new_records)
        table_update()
        QMessageBox.information(window, "粘贴", f"已粘贴 {len(new_records)} 条日志。")


    def table_context_menu(pos):
        menu = QMenu(window)
        a1 = QAction('全选', window); a1.triggered.connect(lambda: set_all_rows_checked(True)); menu.addAction(a1)
        a2 = QAction('反选', window); a2.triggered.connect(invert_rows_checked); menu.addAction(a2)
        a3 = QAction('取消选择', window); a3.triggered.connect(lambda: set_all_rows_checked(False)); menu.addAction(a3)
        menu.addSeparator()
        a4 = QAction('复制', window); a4.triggered.connect(copy_from_main); menu.addAction(a4)
        a5 = QAction('粘贴', window); a5.triggered.connect(paste_to_main); menu.addAction(a5)
        menu.addSeparator()
        a6 = QAction('撤销', window); a6.triggered.connect(undo); menu.addAction(a6)
        a7 = QAction('重做', window); a7.triggered.connect(redo); menu.addAction(a7)
        menu.exec(table.viewport().mapToGlobal(pos))

    def table_update(delete=True):
        nonlocal table
        if delete:
            layout.removeWidget(table)
            table.deleteLater()
            table = None
            list_time(message=False)
            save(message=False)
            

        file_length = len(file)
        # 创建表格部件，增加到15列（含“选择”复选框与“通联录音”列）
        table = QTableWidget(file_length, 14)
        table.setHorizontalHeaderLabels(["选择","日期","时间","己方呼号","对方呼号","频率","调制模式","传播模式","卫星名称", "己方接收信号", "对方接收信号", "己方QTH", "对方QTH","更多"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # 右键上下文菜单（含 选择/复制/粘贴/撤销/重做）
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(table_context_menu)
        print(file_length)
        # 统一使用默认列宽，不设置任何固定宽度
        
        # 添加一些示例数据
        for i in range(file_length):
            checkbox = QCheckBox()
            checkbox.setChecked(False)
            checkbox.setFixedSize(25, 20)
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.addWidget(checkbox)
            table.setCellWidget(i, 0, checkbox_widget)

            date = QTableWidgetItem(file[i]['date'])
            table.setItem(i, 1, date)
            time = QTableWidgetItem(file[i]['time'])
            table.setItem(i, 2, time)
            m_call = QTableWidgetItem(file[i]['m_call'])
            table.setItem(i, 3, m_call)
            o_call = QTableWidgetItem(file[i]['o_call'])
            table.setItem(i, 4, o_call)
            freq = QTableWidgetItem(file[i]['freq'])
            table.setItem(i, 5, freq)
            mode = QTableWidgetItem(file[i]['mode'])
            table.setItem(i, 6, mode)
            prop_mode = QTableWidgetItem(file[i].get('prop_mode', ''))
            table.setItem(i, 7, prop_mode)
            sat_name = QTableWidgetItem(file[i].get('sat_name', ''))
            table.setItem(i, 8, sat_name)
            m_rst = QTableWidgetItem(file[i]['m_rst'])
            table.setItem(i, 9, m_rst)
            o_rst = QTableWidgetItem(file[i]['o_rst'])
            table.setItem(i, 10, o_rst)
            m_qth = QTableWidgetItem(file[i]['m_qth'])
            table.setItem(i, 11, m_qth)
            o_qth = QTableWidgetItem(file[i]['o_qth'])
            table.setItem(i, 12, o_qth)
            other_button = QPushButton("更多")
            other_button.setFixedHeight(26)
            table.setCellWidget(i, 13, other_button)
            other_button.clicked.connect(partial(project_others, i))

        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.setColumnWidth(0, 45)
        table.setColumnWidth(1, 80)
        table.setColumnWidth(2, 70)
        table.setColumnWidth(3, 90)
        table.setColumnWidth(4, 90)
        table.setColumnWidth(5, 70)
        table.setColumnWidth(6, 80)
        table.setColumnWidth(7, 90)
        table.setColumnWidth(8, 90)
        table.setColumnWidth(9, 80)
        table.setColumnWidth(10, 80)
        table.setColumnWidth(11, 120)
        table.setColumnWidth(12, 120)
        table.setColumnWidth(13, 80)
        #table.verticalHeader().setDefaultSectionSize(24)
        layout.addWidget(table)

        table.scrollToBottom()  # 自动跳到底部

    def new(preset=None):
            with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
                xml_dict = eval(f.read())
            global project_others_window,file
            index = len(file)
            date = time_.strftime("%Y-%m-%d", time_.localtime())
            time = time_.strftime("%H:%M", time_.localtime())
            file_app = {
                'date': date,
                'time': time,
                'm_call': xml_dict.get('m_call', '').upper(),
                'o_call': '',
                'freq': '',
                'freq_rx': '',
                'mode': '',
                'prop_mode': '',
                'sat_name': '',
                'm_rst': '59',
                'o_rst': '59',
                'm_qth': xml_dict.get('m_qth', ''),
                'o_qth': '',
                "m_dig": xml_dict.get('m_dig', ''),
                'o_dig': '',
                'm_ant': '',
                'o_ant': '',
                'm_pow': '',
                'o_pow': '',
                'notes': ''
            }
            if preset:
                for k in ('date', 'time', 'm_call', 'o_call', 'freq', 'freq_rx',
                          'mode', 'prop_mode', 'sat_name'):
                    v = preset.get(k)
                    if v not in (None, ''):
                        file_app[k] = v
            
            project_others_window = QMainWindow()
            project_others_window.resize(410, 680)
            project_others_window.setWindowTitle('新建日志')
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
            rows = len(translation_dict)
            table_others = QTableWidget(rows, 2)
            table_others.setColumnWidth(0, 100)  # 设置第1列宽度为100
            table_others.setColumnWidth(1, 250)
            table_others.setHorizontalHeaderLabels(["项目", "内容"])

            row = 0
            for i in translation_dict.keys():
                item = QTableWidgetItem(translation_dict[i])
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 禁止编辑
                table_others.setItem(row, 0, item)
                item2 = QTableWidgetItem(file_app[i])  # 第2列可以编辑
                table_others.setItem(row, 1, item2)
                row += 1
            # 己方呼号(行2)与对方呼号(行3)单元格编辑时实时转大写
            _call_del = call_upper.UpperCallDelegate()
            table_others.setItemDelegateForRow(2, _call_del)
            table_others.setItemDelegateForRow(3, _call_del)
            table_others._upper_call_delegate = _call_del  # 保持引用，防止被回收
            central_widget = QWidget()
            project_others_window.setCentralWidget(central_widget)
            layout_others = QVBoxLayout(central_widget)
            layout_others.addWidget(table_others)

            def save_changes():
                # 获取表格数据并更新到 file 结构
                keys_list = list(translation_dict.keys())
                for row in range(len(keys_list)):
                    key = keys_list[row]

                    if key == 'date':
                        if not re.search(r'^\d{4}-\d{2}-\d{2}$', table_others.item(row, 1).text()):
                                QMessageBox.warning(project_others_window, "格式错误", f"日期格式错误，应为YYYY-MM-DD")
                                return
                    elif key == 'time':
                        if not re.search(r'^\d{2}:\d{2}(:\d{2})?$', table_others.item(row, 1).text()):
                            QMessageBox.warning(project_others_window, "格式错误", f"时间格式错误，应为HH:MM或HH:MM:SS")
                            return
                    elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                        if table_others.item(row, 1).text() == '':
                            QMessageBox.warning(project_others_window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                            return

                    item = table_others.item(row, 1)  # 第二列是可编辑的内容
                    if item!=None:
                        file_app[key] = item.text()
                project_others_window.close()

                snapshot_before()
                file.append(file_app)

                table_update()
            save_button = QPushButton("新建日志")
            save_button.clicked.connect(save_changes)
            layout_others.addWidget(save_button)
            
            project_others_window.show()

    def project_others(index):
        global project_others_window,file
        project_others_window = QMainWindow()
        project_others_window.resize(410, 690)
        project_others_window.setWindowTitle('更多信息')
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
        rows = len(translation_dict)
        table_others = QTableWidget(rows, 2)
        table_others.setColumnWidth(0, 100)  # 设置第1列宽度为100
        table_others.setColumnWidth(1, 250)
        table_others.setHorizontalHeaderLabels(["项目", "内容"])

        row = 0
        for i in translation_dict.keys():
            item = QTableWidgetItem(translation_dict[i])
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 禁止编辑
            table_others.setItem(row, 0, item)
            item2 = QTableWidgetItem(file[index][i])  # 第2列可以编辑
            table_others.setItem(row, 1, item2)
            row += 1
        # 己方呼号(行2)与对方呼号(行3)单元格编辑时实时转大写
        _call_del = call_upper.UpperCallDelegate()
        table_others.setItemDelegateForRow(2, _call_del)
        table_others.setItemDelegateForRow(3, _call_del)
        table_others._upper_call_delegate = _call_del  # 保持引用，防止被回收
        central_widget = QWidget()
        project_others_window.setCentralWidget(central_widget)
        layout_others = QVBoxLayout(central_widget)
        layout_others.addWidget(table_others)
        def save_changes():
            # 获取表格数据并更新到 file 结构
            keys_list = list(translation_dict.keys())
            # 先校验所有字段，校验不通过则不记录撤销点
            for row in range(len(keys_list)):
                key = keys_list[row]
                cell = table_others.item(row, 1)
                if cell is None:
                    continue  # 通联录音行使用 cell widget，跳过
                text = cell.text()
                if key == 'date':
                    if not re.search(r'^\d{4}-\d{2}-\d{2}$', text):
                        QMessageBox.warning(project_others_window, "格式错误", f"日期格式错误，应为YYYY-MM-DD")
                        return
                elif key == 'time':
                    if not re.search(r'^\d{2}:\d{2}$', text):
                        QMessageBox.warning(project_others_window, "格式错误", f"时间格式错误，应为HH:MM")
                        return
                elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                    if text == '':
                        QMessageBox.warning(project_others_window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                        return
            # 校验通过，记录撤销点后再写入
            snapshot_before()
            for row in range(len(keys_list)):
                key = keys_list[row]
                item = table_others.item(row, 1)  # 第二列是可编辑的内容
                if item!=None:
                    file[index][key] = item.text()
            project_others_window.close()
            table_update()
        def del_log(index):
            if QMessageBox.question(window, "删除日志", "确定要删除此日志吗？") == QMessageBox.Yes:
                snapshot_before()
                file.pop(index)
                project_others_window.close()
                table_update()

        qrz_button = QPushButton("查看对方QRZ主页")
        def open_qrz():
            call = file[index].get('o_call','').strip()
            if call == '':
                QMessageBox.warning(project_others_window, 'QRZ', '对方呼号为空，无法打开 QRZ。')
                return
            url = f"https://www.qrz.com/db/{urllib.parse.quote_plus(call)}"
            webbrowser.open(url)
        qrz_button.clicked.connect(open_qrz)

        del_button = QPushButton("删除日志")
        del_button.clicked.connect(lambda:del_log(index))

        button_row_layout = QHBoxLayout()
        button_row_layout.setSpacing(10)
        button_row_layout.addWidget(qrz_button)
        button_row_layout.addWidget(del_button)

        layout_others.addLayout(button_row_layout)

        save_button = QPushButton("保存更改")
        save_button.clicked.connect(save_changes)
        layout_others.addWidget(save_button)
        
        
        project_others_window.show()

    def save(message=True):
        with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
            xml_dict = eval(f.read())

        aouto_save_b = xml_dict['aouto_save']

        if (not(message) and aouto_save_b) or message:
            global key
            fhl_rw.write_fhl_file(save_path,file,key)
            if message:
                QMessageBox.information(window, "保存成功", "保存成功！")

    def osave():
        import json
        save_path, _ = QFileDialog.getSaveFileName(
            window,  # 父窗口，可以是None或者您的主窗口
            "另存为文件",  # 对话框标题
            desktop_dir(),  # 初始目录：桌面，默认文件名为空
            "F HamLog项目 (*.fhl)"  # 文件过滤器，只显示.fos文件
        )
        if save_path == '':
            return
        global key
        fhl_rw.write_fhl_file(save_path,file,key)
        QMessageBox.information(window, "另存成功", "另存成功！")

    def esave():
        import json
        global key
        fhl_rw.write_fhl_file(save_path,file,key)
        QMessageBox.information(window, "保存成功", "保存成功！")
        sys.exit()

    def input_HAM_tolls_():
        global file
        old_file = file.copy()  # 使用copy()确保是深拷贝
        import input_HAM_tolls
        snapshot_before()
        file = input_HAM_tolls.main(file)
        table_update()
        if file == old_file:  # 如果没有导入任何内容，则不保存
            return

    def import_from_ADI():
        global file
        old_file = file.copy()
        import input_adi
        try:
            snapshot_before()
            file = input_adi.main(file)
        except Exception as e:
            QMessageBox.warning(window, "导入失败", f"导入 ADI 失败：{e}")
            return
        if file == old_file:  # 如果没有导入任何内容，则不保存
            return
        table_update()

    def input_fhl():
        global file
        old_file = file.copy()  # 使用copy()确保是深拷贝
        import input_fhl
        snapshot_before()
        file = input_fhl.main(file)
        table_update()
        if file == old_file:  # 如果没有导入任何内容，则不保存
            return

    def output_adi(file):
        import output_adi

        output_adi.main(file)

    def output_excel(file):
        import output_excel
        output_excel.main(file)

    def get_selected_records():
        if table is None:
            QMessageBox.warning(window, "导出失败", "当前未加载日志表。")
            return None
        selected_records = []
        for row in range(table.rowCount()):
            # 优先检查嵌入的 QCheckBox 控件
            cell_w = table.cellWidget(row, 0)
            if cell_w is not None:
                cb = cell_w.findChild(QCheckBox)
                if cb is not None and cb.isChecked():
                    selected_records.append(file[row])
                continue

            # 退回到 QTableWidgetItem（如果存在的话）
            checkbox_item = table.item(row, 0)
            if checkbox_item is not None and checkbox_item.checkState() == Qt.Checked:
                selected_records.append(file[row])

        if not selected_records:
            QMessageBox.warning(window, "导出失败", "请先勾选要导出的日志行。")
            return None
        return selected_records

    def _get_main_checkbox(orig_index):
        # 获取主页面表格指定行第0列内嵌的复选框控件
        if table is None:
            return None
        if orig_index < 0 or orig_index >= table.rowCount():
            return None
        cell_w = table.cellWidget(orig_index, 0)
        if cell_w is not None:
            return cell_w.findChild(QCheckBox)
        return None

    def set_main_checkbox(orig_index, checked):
        # 将搜索结果的勾选状态同步到主页面对应行的复选框
        cb = _get_main_checkbox(orig_index)
        if cb is not None:
            cb.setChecked(bool(checked))

    def output_selected_fhl():
        selected_records = get_selected_records()
        if not selected_records:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            window,
            "导出选中日志为FHL文件",
            desktop_dir(),
            "F HamLog项目 (*.fhl)"
        )
        if not save_path:
            return
        global key
        fhl_rw.write_fhl_file(save_path,selected_records,key)

            
        QMessageBox.information(window, "导出成功", f"已导出 {len(selected_records)} 条记录到：\n{save_path}")

    def output_selected_adi():
        selected_records = get_selected_records()
        if not selected_records:
            return
        import output_adi
        output_adi.main(selected_records)

    def output_selected_excel():
        selected_records = get_selected_records()
        if not selected_records:
            return
        import output_excel
        output_excel.main(selected_records)

    if save_path == '':
        save_path, _ = QFileDialog.getSaveFileName(
            window,  # 父窗口，可以是None或者您的主窗口
            "新建文件",  # 对话框标题
            desktop_dir(),  # 初始目录：桌面，默认文件名为空
            "F HamLog项目 (*.fhl)"  # 文件过滤器，只显示.fos文件
        )
        if save_path == '':
            return
    print(save_path)
    window.resize(1350, 700)
    if quick_poject:
        window.setWindowTitle(f'F HamLog 2 - 通联日志')
    else:
        window.setWindowTitle(f'F HamLog 2 - {os.path.basename(save_path)}')
    # window.showMaximized()
    # 创建菜单栏
    menu_bar = window.menuBar()

    # 创建"文件"菜单
    file_menu = menu_bar.addMenu('文件')

    save_action = QAction('保存', window)
    save_action.setShortcut('Ctrl+S')
    save_action.triggered.connect(lambda: save())
    file_menu.addAction(save_action)

    osave_action = QAction('另存为', window)
    osave_action.setShortcut('Ctrl+Shift+S')
    osave_action.triggered.connect(lambda: osave())
    file_menu.addAction(osave_action)

    file_menu.addSeparator()

    def aes_open_():
        global key
        QMessageBox.information(window,'加密项目','F HamLog 将使用AES加密项目，\n请牢记你的密钥！若密钥丢失则无法恢复日志数据。')
        key = fhl_rw.get_user_key_dialog()
        list_time(message=False)
        save(message=False)
        QMessageBox.information(window,'加密项目','加密成功！\n请重新打开此项目。')
        window.close()
    def aes_close_():
        global key
        input_key = fhl_rw.get_user_key_dialog()
        if input_key == key:
            key = None
            list_time(message=False)
            save(message=False)
            QMessageBox.information(window,'解密项目','解密成功！\n请重新打开此项目。')
            window.close()
        else:
            QMessageBox.warning(window,'解密项目','密钥错误！')

    if key == None:
        aes_open = QAction('加密此项目', window)
        aes_open.setShortcut('Ctrl+Alt+E')
        aes_open.triggered.connect(aes_open_)
        file_menu.addAction(aes_open)
    else:
        aes_close = QAction('不再加密此项目', window)
        aes_close.setShortcut('Ctrl+Alt+E')
        aes_close.triggered.connect(aes_close_)
        file_menu.addAction(aes_close)

    file_menu.addSeparator()

    def open_main_page():
        # 打开主页面：启动 main.py 启动器窗口（与程序入口一致）
        import subprocess, sys, os
        main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'main.py')
        try:
            subprocess.Popen([sys.executable, main_py])
        except Exception as e:
            QMessageBox.warning(window, '打开主页面失败', str(e))

    open_main_action = QAction('打开主页面', window)
    open_main_action.setShortcut('Ctrl+Shift+M')
    open_main_action.triggered.connect(open_main_page)
    file_menu.addAction(open_main_action)

    file_menu.addSeparator()

    sexit_action = QAction('保存并退出', window)
    sexit_action.triggered.connect(lambda: esave())
    file_menu.addAction(sexit_action)

    zexit_action = QAction('退出', window)
    zexit_action.triggered.connect(lambda: sys.exit())
    file_menu.addAction(zexit_action)

    def delete_selected_logs():
        '''删除主表格中选中的日志：优先删除“选择”列已勾选的行；
        若未勾选任何行，则回退删除当前高亮选中的行。删除前二次确认，
        并记入撤销点（Ctrl+Z 可恢复），删除后自动重建表格并落盘。'''
        if table is None:
            QMessageBox.warning(window, "删除失败", "当前未加载日志表。")
            return
        # 1) 优先收集“选择”列（第0列）中已勾选的行
        checked_rows = []
        for row in range(table.rowCount()):
            cell_w = table.cellWidget(row, 0)
            cb = cell_w.findChild(QCheckBox) if cell_w is not None else None
            if cb is None:
                item = table.item(row, 0)
                if item is not None and item.checkState() == Qt.Checked:
                    checked_rows.append(row)
                continue
            if cb.isChecked():
                checked_rows.append(row)
        # 2) 若未勾选任何行，回退到当前高亮选中的行
        if not checked_rows:
            rows = set()
            for rng in table.selectedRanges():
                for r in range(rng.topRow(), rng.bottomRow() + 1):
                    rows.add(r)
            checked_rows = sorted(rows)
        if not checked_rows:
            QMessageBox.warning(window, "删除失败",
                "没有可删除的日志：请先在“选择”列勾选要删除的行，或直接选中（高亮）这些行。")
            return
        # 二次确认（破坏性操作）
        count = len(checked_rows)
        reply = QMessageBox.question(
            window, "确认删除",
            f"确定要删除选中的 {count} 条日志吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        # 记撤销点，随后按行号从大到小删除，避免索引错位
        snapshot_before()
        for row in sorted(checked_rows, reverse=True):
            del file[row]
        table_update()

    # 创建"编辑"菜单（撤销/重做/复制/粘贴/删除选中）
    edit_menu = menu_bar.addMenu('编辑')

    undo_action = QAction('撤销', window)
    undo_action.setShortcut('Ctrl+Z')
    undo_action.triggered.connect(undo)
    edit_menu.addAction(undo_action)

    redo_action = QAction('重做', window)
    redo_action.setShortcut('Ctrl+Y')
    redo_action.triggered.connect(redo)
    edit_menu.addAction(redo_action)

    edit_menu.addSeparator()

    copy_action = QAction('复制', window)
    copy_action.setShortcut('Ctrl+C')
    copy_action.triggered.connect(copy_from_main)
    edit_menu.addAction(copy_action)

    paste_action = QAction('粘贴', window)
    paste_action.setShortcut('Ctrl+V')
    paste_action.triggered.connect(paste_to_main)
    edit_menu.addAction(paste_action)

    edit_menu.addSeparator()

    delete_selected_action = QAction('删除选中的日志', window)
    delete_selected_action.setShortcut('Ctrl+D')
    delete_selected_action.triggered.connect(delete_selected_logs)
    edit_menu.addAction(delete_selected_action)

    def set_all_rows_checked(checked):
        # 遍历主表格“选择”列（第0列）的复选框，统一设置勾选状态
        if table is None:
            return
        for row in range(table.rowCount()):
            cell_w = table.cellWidget(row, 0)
            if cell_w is not None:
                cb = cell_w.findChild(QCheckBox)
                if cb is not None:
                    cb.setChecked(checked)

    def invert_rows_checked():
        # 反转每一行的勾选状态
        if table is None:
            return
        for row in range(table.rowCount()):
            cell_w = table.cellWidget(row, 0)
            if cell_w is not None:
                cb = cell_w.findChild(QCheckBox)
                if cb is not None:
                    cb.setChecked(not cb.isChecked())

    select_menu = menu_bar.addMenu('选择')

    select_all_action = QAction('全选', window)
    select_all_action.setShortcut('Ctrl+A')
    select_all_action.triggered.connect(lambda: set_all_rows_checked(True))
    select_menu.addAction(select_all_action)

    invert_action = QAction('反选', window)
    invert_action.setShortcut('Ctrl+I')
    invert_action.triggered.connect(invert_rows_checked)
    select_menu.addAction(invert_action)

    deselect_action = QAction('取消选择', window)
    deselect_action.setShortcut('Ctrl+Shift+A')
    deselect_action.triggered.connect(lambda: set_all_rows_checked(False))
    select_menu.addAction(deselect_action)


    import_menu = menu_bar.addMenu('导入/导出')

    import_from_ADI_action = QAction('从ADI导入日志', window)
    import_from_ADI_action.triggered.connect(lambda: import_from_ADI())
    import_menu.addAction(import_from_ADI_action)

    input_fhl_action = QAction('从 F HamLog 导入日志', window)
    input_fhl_action.triggered.connect(lambda: input_fhl())
    import_menu.addAction(input_fhl_action)

    input_HAM_tolls_action = QAction('从 旧版 HAM个人工具 导入日志', window)
    input_HAM_tolls_action.triggered.connect(lambda: input_HAM_tolls_())
    import_menu.addAction(input_HAM_tolls_action)

    import_menu.addSeparator()

    export_adi_action = QAction('导出ADI文件', window)
    export_adi_action.triggered.connect(lambda: output_adi(file))
    import_menu.addAction(export_adi_action)

    export_excel_action = QAction('导出为表格', window)
    export_excel_action.triggered.connect(lambda: output_excel(file))
    import_menu.addAction(export_excel_action)

    import_menu.addSeparator()
    export_selected_menu = import_menu.addMenu('导出选中的日志')

    export_selected_adi_action = QAction('导出选中的日志为ADI', window)
    export_selected_adi_action.triggered.connect(output_selected_adi)
    export_selected_menu.addAction(export_selected_adi_action)

    export_selected_excel_action = QAction('导出选中的日志为表格', window)
    export_selected_excel_action.triggered.connect(output_selected_excel)
    export_selected_menu.addAction(export_selected_excel_action)

    export_selected_fhl_action = QAction('导出选中的日志为 F HamLog 项目文件', window)
    export_selected_fhl_action.triggered.connect(output_selected_fhl)
    export_selected_menu.addAction(export_selected_fhl_action)

    # ---------- 选择菜单：全选 / 反选 / 取消选择 ----------
    

    def list_time(message=True):
        with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
            xml_dict = eval(f.read())
        
        aouto_list_b = xml_dict['aouto_list']
        if (not(message) and aouto_list_b) or message:
            try:
                file.sort(key=lambda x: (x.get('date', ''), x.get('time', '')))
                
                if message:
                    table_update()
                    QMessageBox.information(window, "排序完成", "按时间排序完成。")
            except Exception as e:
                QMessageBox.warning(window, "排序失败", str(e))

    def research_call(file_param=None):
        global research_window
        # 弹出高级搜索对话：选择字段 + 关键词 + 匹配方式
        dlg = QDialog(window)
        dlg.resize(320, 180)
        dlg.setWindowTitle('搜索')
        dlg_layout = QVBoxLayout(dlg)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel('字段：'))
        combo = QComboBox()
        choices = [
            ('o_call', '对方呼号'),
            ('m_call', '己方呼号'),
            ('date', '日期'),
            ('time', '时间'),
            ('freq', '频率'),
            ('mode', '调制模式'),
            ('m_dig', '己方设备'),
            ('o_dig', '对方设备'),
            ('m_qth', '己方QTH'),
            ('o_qth', '对方QTH'),
            ('m_ant', '己方天线'),
            ('o_ant', '对方天线'),
            ('m_pow', '己方功率'),
            ('o_pow', '对方功率'),
            ('notes', '备注')
        ]
        for k, v in choices:
            combo.addItem(v, k)
        h1.addWidget(combo)
        dlg_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel('关键词：'))
        edit = QLineEdit()
        # 选中的字段为己方/对方呼号时，关键词输入实时转大写
        call_upper.connect_callsign_upper(edit, lambda: combo.currentData())
        h2.addWidget(edit)
        dlg_layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel('匹配方式：'))
        match_combo = QComboBox()
        match_combo.addItems(['包含', '完全匹配'])
        h3.addWidget(match_combo)
        dlg_layout.addLayout(h3)

        h_scope = QHBoxLayout()
        h_scope.addWidget(QLabel('范围：'))
        scope_combo = QComboBox()
        scope_combo.addItems(['全部通联记录', '仅选中的行'])
        h_scope.addWidget(scope_combo)
        dlg_layout.addLayout(h_scope)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        field = combo.currentData()
        q = edit.text().strip().casefold()
        if q == '':
            QMessageBox.information(window, '搜索', '请输入关键词。')
            return
        exact = (match_combo.currentText() == '完全匹配')
        scope = scope_combo.currentText()

        def record_text(record, name):
            value = record.get(name, '')
            return '' if value is None else str(value)

        matches = []
        for i, rec in enumerate(file):
            val = record_text(rec, field).casefold()
            if (exact and val == q) or (not exact and q in val):
                matches.append((i, rec))

        # 范围：仅选中的行 → 仅保留主页面勾选（或当前选中）的记录
        if scope == '仅选中的行':
            selected = set(get_selected_row_indexes())
            matches = [(i, rec) for i, rec in matches if i in selected]

        if not matches:
            QMessageBox.information(window, "搜索结果", "未找到任何匹配记录。")
            return

        research_window = QMainWindow()
        research_window.resize(1300, 600)
        research_window.setWindowTitle(f"搜索结果：{edit.text().strip()}")
        central = QWidget()
        research_window.setCentralWidget(central)
        lay = QVBoxLayout(central)

        search_checkboxes = []  # [(checkbox, orig_index), ...]

        # 选择逻辑：与 project.py 主窗口一致（全选 / 反选 / 取消选择）
        def _search_select_all():
            for cb, _ in search_checkboxes:
                cb.setChecked(True)

        def _search_select_none():
            for cb, _ in search_checkboxes:
                cb.setChecked(False)

        def _search_invert():
            for cb, _ in search_checkboxes:
                cb.setChecked(not cb.isChecked())

        # 仅针对当前搜索结果（matches）的统计与导出
        def _search_records():
            return [rec for _, rec in matches]

        # 搜索结果统计的范围解析：全部通联记录 / 全部搜索结果 / 仅选中的行（搜索窗口勾选的行）
        def _stat_scope_resolver(scope):
            if scope == '全部通联记录':
                return file
            if scope == '仅选中的行':
                return [file[orig_index] for cb, orig_index in search_checkboxes if cb.isChecked()]
            return [rec for _, rec in matches]  # 全部搜索结果

        def _export_search_fhl():
            recs = _search_records()
            if not recs:
                QMessageBox.warning(research_window, "导出失败", "没有可导出的搜索结果。")
                return
            save_path, _ = QFileDialog.getSaveFileName(
                research_window, "导出搜索结果为FHL文件", desktop_dir(), "F HamLog项目 (*.fhl)")
            if not save_path:
                return
            fhl_rw.write_fhl_file(save_path, recs, key)
            QMessageBox.information(research_window, "导出成功", f"已导出 {len(recs)} 条记录到：\n{save_path}")

        def _export_search_adi():
            recs = _search_records()
            if not recs:
                return
            import output_adi
            output_adi.main(recs)

        def _export_search_excel():
            recs = _search_records()
            if not recs:
                return
            import output_excel
            output_excel.main(recs)

        # 菜单栏“选择”：快捷键与主窗口一致（Ctrl+A 全选 / Ctrl+I 反选 / Ctrl+D 取消选择）
        _mb = research_window.menuBar()
        _sel_menu = _mb.addMenu('选择')
        _sel_all = QAction('全选', research_window)
        _sel_all.setShortcut('Ctrl+A')
        _sel_all.triggered.connect(_search_select_all)
        _sel_menu.addAction(_sel_all)
        _sel_inv = QAction('反选', research_window)
        _sel_inv.setShortcut('Ctrl+I')
        _sel_inv.triggered.connect(_search_invert)
        _sel_menu.addAction(_sel_inv)
        _sel_none = QAction('取消选择', research_window)
        _sel_none.setShortcut('Ctrl+Shift+A')
        _sel_none.triggered.connect(_search_select_none)
        _sel_menu.addAction(_sel_none)

        # 功能：统计图（仅统计当前搜索结果），与主窗口“功能”菜单一致
        _func_menu = _mb.addMenu('功能')
        _stat_act = QAction('统计图', research_window)
        _stat_act.setShortcut('Ctrl+Shift+P')
        _stat_act.triggered.connect(lambda: show_statistics(
            parent=research_window,
            scope_labels=['全部通联记录', '全部搜索结果', '仅选中的行'],
            scope_resolver=_stat_scope_resolver,
            default_scope='全部搜索结果'))
        _func_menu.addAction(_stat_act)

        # 导入/导出：与主窗口“导入/导出”菜单完全一致
        # 导入项复用主窗口函数（导入进主项目）；导出项仅限当前搜索结果
        _imp_menu = _mb.addMenu('导入/导出')
        _imp_adi = QAction('从ADI导入日志', research_window)
        _imp_adi.triggered.connect(lambda: import_from_ADI())
        _imp_menu.addAction(_imp_adi)
        _imp_fhl = QAction('从 F HamLog 导入日志', research_window)
        _imp_fhl.triggered.connect(lambda: input_fhl())
        _imp_menu.addAction(_imp_fhl)
        _imp_ham = QAction('从 旧版 HAM个人工具 导入日志', research_window)
        _imp_ham.triggered.connect(lambda: input_HAM_tolls_())
        _imp_menu.addAction(_imp_ham)
        _imp_menu.addSeparator()
        _exp_adi = QAction('导出ADI文件', research_window)
        _exp_adi.triggered.connect(_export_search_adi)
        _imp_menu.addAction(_exp_adi)
        _exp_xls = QAction('导出为表格', research_window)
        _exp_xls.triggered.connect(_export_search_excel)
        _imp_menu.addAction(_exp_xls)
        _imp_menu.addSeparator()
        _exp_sel_menu = _imp_menu.addMenu('导出选中的日志')
        _exp_sel_adi = QAction('导出选中的日志为ADI', research_window)
        _exp_sel_adi.triggered.connect(_export_search_adi)
        _exp_sel_menu.addAction(_exp_sel_adi)
        _exp_sel_xls = QAction('导出选中的日志为表格', research_window)
        _exp_sel_xls.triggered.connect(_export_search_excel)
        _exp_sel_menu.addAction(_exp_sel_xls)
        _exp_sel_fhl = QAction('导出选中的日志为 F HamLog 项目文件', research_window)
        _exp_sel_fhl.triggered.connect(_export_search_fhl)
        _exp_sel_menu.addAction(_exp_sel_fhl)

        # 顶部提示栏（已取消 全选 / 全不选 按钮）
        top_row = QHBoxLayout()
        hint = QLabel('勾选下方记录，选择结果会自动同步到主页面的选择框（Ctrl+A 全选 / Ctrl+I 反选 / Ctrl+D 取消选择）')
        hint.setStyleSheet('color: gray;')
        top_row.addWidget(hint)
        top_row.addStretch(1)
        lay.addLayout(top_row)

        # 新增"选择"列（列0），其余列整体右移一列
        table_r = QTableWidget(len(matches), 14)
        table_r.setHorizontalHeaderLabels(["选择","日期","时间","己方呼号","对方呼号","频率","调制模式","传播模式","卫星名称", "己方接收信号", "对方接收信号", "己方QTH", "对方QTH","更多"])
        table_r.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row, (orig_index, rec) in enumerate(matches):
            # 选择复选框：初始状态与主页面当前勾选保持一致
            checkbox = QCheckBox()
            main_cb = _get_main_checkbox(orig_index)
            checkbox.setChecked(main_cb.isChecked() if main_cb is not None else False)
            checkbox.setFixedSize(25, 20)
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.addWidget(checkbox)
            table_r.setCellWidget(row, 0, checkbox_widget)
            # 勾选变化时实时同步到主页面对应行
            checkbox.toggled.connect(partial(set_main_checkbox, orig_index))
            search_checkboxes.append((checkbox, orig_index))

            table_r.setItem(row, 1, QTableWidgetItem(record_text(rec, 'date')))
            table_r.setItem(row, 2, QTableWidgetItem(record_text(rec, 'time')))
            table_r.setItem(row, 3, QTableWidgetItem(record_text(rec, 'm_call')))
            table_r.setItem(row, 4, QTableWidgetItem(record_text(rec, 'o_call')))
            table_r.setItem(row, 5, QTableWidgetItem(record_text(rec, 'freq')))
            table_r.setItem(row, 6, QTableWidgetItem(record_text(rec, 'mode')))
            table_r.setItem(row, 7, QTableWidgetItem(record_text(rec, 'prop_mode')))
            table_r.setItem(row, 8, QTableWidgetItem(record_text(rec, 'sat_name')))
            table_r.setItem(row, 9, QTableWidgetItem(record_text(rec, 'm_rst')))
            table_r.setItem(row, 10, QTableWidgetItem(record_text(rec, 'o_rst')))
            table_r.setItem(row, 11, QTableWidgetItem(record_text(rec, 'm_qth')))
            table_r.setItem(row, 12, QTableWidgetItem(record_text(rec, 'o_qth')))
            more_btn = QPushButton("更多")
            more_btn.setFixedHeight(26)
            more_btn.clicked.connect(partial(project_others, orig_index))
            table_r.setCellWidget(row, 13, more_btn)

        table_r.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table_r.setColumnWidth(0, 45)
        table_r.setColumnWidth(1, 80)
        table_r.setColumnWidth(2, 70)
        table_r.setColumnWidth(3, 90)
        table_r.setColumnWidth(4, 90)
        table_r.setColumnWidth(5, 70)
        table_r.setColumnWidth(6, 80)
        table_r.setColumnWidth(7, 90)
        table_r.setColumnWidth(8, 90)
        table_r.setColumnWidth(9, 80)
        table_r.setColumnWidth(10, 80)
        table_r.setColumnWidth(11, 120)
        table_r.setColumnWidth(12, 120)
        table_r.setColumnWidth(13, 80)
        lay.addWidget(table_r)
        table_r.scrollToBottom()

        # 搜索结果表格右键菜单：复制选中行 / 全选 / 反选 / 取消选择（复制的记录可粘贴到主窗口或 Excel）
        def _search_context_menu(pos):
            menu = QMenu(window)
            act_copy = QAction('复制选中行', window)
            def do_copy():
                recs = []
                for cb, orig_index in search_checkboxes:
                    if cb.isChecked():
                        recs.append(file[orig_index])
                if not recs:
                    for idx in table_r.selectionModel().selectedRows():
                        recs.append(file[matches[idx.row()][0]])
                if not recs:
                    QMessageBox.information(window, "复制", "请先勾选要复制的行。")
                    return
                if copy_records_to_clipboard(recs):
                    QMessageBox.information(window, "复制", f"已复制 {len(recs)} 条日志到剪贴板。")
            act_copy.triggered.connect(do_copy)
            menu.addAction(act_copy)
            menu.addSeparator()
            act_all = QAction('全选', window); act_all.triggered.connect(_search_select_all); menu.addAction(act_all)
            act_inv = QAction('反选', window); act_inv.triggered.connect(_search_invert); menu.addAction(act_inv)
            act_none = QAction('取消选择', window); act_none.triggered.connect(_search_select_none); menu.addAction(act_none)
            menu.exec(table_r.viewport().mapToGlobal(pos))

        table_r.setContextMenuPolicy(Qt.CustomContextMenu)
        table_r.customContextMenuRequested.connect(_search_context_menu)

        research_window.show()

    def find_replace():
        # 按字段查找替换：选择字段 + 查找文本 + 替换文本 + 匹配方式 + 范围，批量替换
        dlg = QDialog(window)
        dlg.setWindowTitle('查找替换')
        dlg.resize(300, 200)
        dlg_layout = QVBoxLayout(dlg)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel('字段：'))
        combo = QComboBox()
        choices = [
            ('o_call', '对方呼号'),
            ('m_call', '己方呼号'),
            ('date', '日期'),
            ('time', '时间'),
            ('freq', '频率'),
            ('mode', '调制模式'),
            ('prop_mode', '传播方式'),
            ('sat_name', '卫星名称'),
            ('m_dig', '己方设备'),
            ('o_dig', '对方设备'),
            ('m_qth', '己方QTH'),
            ('o_qth', '对方QTH'),
            ('m_ant', '己方天线'),
            ('o_ant', '对方天线'),
            ('m_pow', '己方功率'),
            ('o_pow', '对方功率'),
            ('notes', '备注')
        ]
        for k, v in choices:
            combo.addItem(v, k)
        h1.addWidget(combo)
        dlg_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel('查找：'))
        find_edit = QLineEdit()
        # 选中的字段为己方/对方呼号时，查找与替换输入实时转大写
        call_upper.connect_callsign_upper(find_edit, lambda: combo.currentData())
        h2.addWidget(find_edit)
        dlg_layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel('替换为：'))
        replace_edit = QLineEdit()
        call_upper.connect_callsign_upper(replace_edit, lambda: combo.currentData())
        h3.addWidget(replace_edit)
        dlg_layout.addLayout(h3)

        h4 = QHBoxLayout()
        h4.addWidget(QLabel('匹配方式：'))
        match_combo = QComboBox()
        match_combo.addItems(['包含', '完全匹配'])
        h4.addWidget(match_combo)
        dlg_layout.addLayout(h4)

        h5 = QHBoxLayout()
        h5.addWidget(QLabel('范围：'))
        scope_combo = QComboBox()
        scope_combo.addItems(['全部通联记录', '仅选中的行'])
        h5.addWidget(scope_combo)
        dlg_layout.addLayout(h5)

        def compute_matches():
            # 返回 (匹配行索引列表, 预计替换处数)；匹配不区分大小写，与“搜索”一致
            field = combo.currentData()
            q = find_edit.text()
            exact = (match_combo.currentText() == '完全匹配')
            scope = scope_combo.currentText()
            if q == '':
                return [], 0
            qlow = q.lower()
            matches = []
            for i, rec in enumerate(file):
                val = str(rec.get(field, ''))
                if (exact and val.lower() == qlow) or (not exact and qlow in val.lower()):
                    matches.append(i)
            if scope == '仅选中的行':
                selected = set(get_selected_row_indexes())
                matches = [i for i in matches if i in selected]
            change_count = 0
            for i in matches:
                val = str(file[i].get(field, ''))
                change_count += 1 if exact else len(re.findall(re.escape(q), val, re.IGNORECASE))
            return matches, change_count

        btns = QDialogButtonBox()
        replace_btn = QPushButton('替换')
        replace_btn.setDefault(True)
        replace_btn.clicked.connect(dlg.accept)
        btns.addButton(replace_btn, QDialogButtonBox.AcceptRole)
        cancel_btn = QPushButton('取消')
        cancel_btn.clicked.connect(dlg.reject)
        btns.addButton(cancel_btn, QDialogButtonBox.RejectRole)
        dlg_layout.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        field = combo.currentData()
        q = find_edit.text()
        rep = replace_edit.text()
        exact = (match_combo.currentText() == '完全匹配')
        scope = scope_combo.currentText()

        if q == '':
            QMessageBox.information(window, '查找替换', '请输入查找内容。')
            return

        matches, change_count = compute_matches()
        if not matches:
            QMessageBox.information(window, '查找替换', '没有找到匹配的记录。')
            return

        snapshot_before()
        affected = 0
        total = 0
        for i in matches:
            val = str(file[i].get(field, ''))
            if exact:
                if val.lower() == q.lower():
                    file[i][field] = rep
                    affected += 1
                    total += 1
            else:
                if q.lower() in val.lower():
                    file[i][field] = re.sub(re.escape(q), rep, val, flags=re.IGNORECASE)
                    affected += 1
                    total += len(re.findall(re.escape(q), val, re.IGNORECASE))
        table_update()
        QMessageBox.information(window, '查找替换',
                                f'替换完成：影响 {affected} 条记录，共 {total} 处替换。')

    def show_statistics(records=None, parent=None, scope_labels=None, scope_resolver=None, default_scope=None):
        global file
        owner = parent if parent is not None else window
        dlg = QDialog(owner)
        dlg.setWindowTitle('统计图')  # 窗口标题
        dlg.resize(320,100)
        dlg_layout = QVBoxLayout(dlg)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel('字段：'))
        combo_stat = QComboBox()
        stat_choices = [
            ('o_call', '对方呼号'),  # 添加对方呼号统计
            ('mode', '调制模式'),
            ('freq', '频率'),
            ('prop_mode', '传播方式'),
            ('sat_name', '卫星名称'),
            ('m_qth', '己方QTH'),
            ('o_qth', '对方QTH'),
            ('m_dig', '己方设备'),
            ('o_dig', '对方设备'),
            ('notes', '备注')
        ]
        for k, v in stat_choices:
            combo_stat.addItem(v, k)
        h1.addWidget(combo_stat)
        dlg_layout.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel('图表类型：'))
        chart_combo = QComboBox()
        chart_combo.addItems(['条形图', '扇形图'])
        h2.addWidget(chart_combo)
        dlg_layout.addLayout(h2)

        # 范围：自定义（如搜索结果按 全部搜索结果/仅选中的行）或默认（主窗口 全部通联记录/仅选中的行）
        if scope_labels is not None:
            label_list = scope_labels
        elif records is None:
            label_list = ['全部通联记录', '仅选中的行']
        else:
            label_list = None
        if label_list is not None:
            h_scope = QHBoxLayout()
            h_scope.addWidget(QLabel('范围：'))
            scope_combo = QComboBox()
            scope_combo.addItems(label_list)
            if default_scope is not None:
                scope_combo.setCurrentText(default_scope)
            h_scope.addWidget(scope_combo)
            dlg_layout.addLayout(h_scope)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        field = combo_stat.currentData()
        chart_type = chart_combo.currentText()

        # 数据来源
        if scope_labels is not None:
            data = scope_resolver(scope_combo.currentText())
        elif records is not None:
            data = records
        else:
            scope = scope_combo.currentText()
            if scope == '仅选中的行':
                selected = set(get_selected_row_indexes())
                data = [file[i] for i in selected]
            else:
                data = file

        # 统计各项出现次数
        counts = {}
        for rec in data:
            val = str(rec.get(field, '')).strip()
            if val == '':
                val = '<空>'
            counts[val] = counts.get(val, 0) + 1

        if not counts:
            QMessageBox.information(owner, '统计', '没有可统计的数据。')
            return

        # 绘图
        try:
            import matplotlib.pyplot as plt
            import matplotlib
            # 设置中文字体
            matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
            matplotlib.rcParams['axes.unicode_minus'] = False  # 正常显示负号
        except Exception:
            QMessageBox.warning(owner, '缺少依赖', '未安装 matplotlib，请运行: pip install matplotlib')
            return

        labels = list(counts.keys())
        values = list(counts.values())

        plt.figure(figsize=(8, 6))
        if chart_type == '条形图':
            plt.bar(labels, values)
            plt.xticks(rotation=45, ha='right')
            plt.ylabel('次数')
        else:
            plt.pie(values, labels=labels, autopct='%1.1f%%')

        # 使用自定义标题或默认标题
        display_map = {k: v for k, v in stat_choices}
        plt.title(f"{display_map.get(field, field)} 统计")
        plt.tight_layout()
        plt.show()

    tool_menu = menu_bar.addMenu('功能')

    list_action = QAction('按时间排序', window)
    list_action.setShortcut('Ctrl+L')
    list_action.triggered.connect(lambda: list_time())
    tool_menu.addAction(list_action)

    tool_menu.addSeparator()

    stats_action = QAction('统计图', window)
    stats_action.setShortcut('Ctrl+Shift+P')
    stats_action.triggered.connect(lambda: show_statistics())
    tool_menu.addAction(stats_action)

    research_call_action = QAction('搜索', window)
    research_call_action.setShortcut('Ctrl+R')
    research_call_action.triggered.connect(lambda: research_call(file))
    tool_menu.addAction(research_call_action)

    find_replace_action = QAction('查找替换', window)
    find_replace_action.setShortcut('Ctrl+H')
    find_replace_action.triggered.connect(lambda: find_replace())
    tool_menu.addAction(find_replace_action)


    # ---------- 记录功能菜单 ----------
    sat_menu = menu_bar.addMenu('记录')

    def append_to_project(records):
        """复用卫星过境窗口“记录”按钮的保存逻辑：把记录（一条或多条）直接追加到
        当前打开的项目文件并落盘（不再弹出保存方式选择）。"""
        snapshot_before()
        for rec in records:
            file.append(rec)
        table_update()
        # 直接落盘到当前项目文件（不依赖自动保存开关，也不弹“保存成功”）
        global key
        fhl_rw.write_fhl_file(save_path, file, key)

    def quick_log(preset):
        """由卫星过境窗口“记录”按钮回调：打开批量记录窗口并预填卫星信息。"""
        import batch_project
        bw = QMainWindow()
        bw.setWindowTitle('批量记录 - ' + str(preset.get('sat_name', '')))
        batch_project.main(bw, preset=preset, on_saved=append_to_project)
        _open_windows.append(bw)

    def open_batch_record():
        """菜单“批量记录”：直接打开批量记录窗口（不预填卫星信息），
        保存逻辑与卫星过境预测中的“记录”按钮完全一致。"""
        import batch_project
        bw = QMainWindow()
        bw.setWindowTitle('批量记录')
        batch_project.main(bw, preset=None, on_saved=append_to_project)
        _open_windows.append(bw)

    def open_satellite_window():
        import satellite_window
        satellite_window.main(window, quick_log_callback=quick_log,
                              title='卫星通联记录')

    sat_predict_action = QAction('卫星通联记录', window)
    sat_predict_action.setShortcut('Ctrl+W')
    sat_predict_action.triggered.connect(open_satellite_window)
    sat_menu.addAction(sat_predict_action)

    sat_menu.addSeparator()

    batch_action = QAction('批量记录', window)
    batch_action.setShortcut('Ctrl+B')
    batch_action.triggered.connect(open_batch_record)
    sat_menu.addAction(batch_action)
    # 通联预测入口统一收归「卫星通联记录」窗口内的「通联预测」按钮，
    # 不再在菜单单独列出。


    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)

    button_new = QPushButton("新建日志（Ctrl+N）", window)
    button_new.setShortcut('Ctrl+N')
    button_new.clicked.connect(lambda: new())
    layout.addWidget(button_new)

    # 暴露给外部（如主页“卫星过境”记录按钮）调用，实现快速记录
    window._new_qso = new          # 弹出预填的“新建日志”窗口
    window._quick_add = quick_log  # 直接把预填记录追加到当前项目（不弹窗）

    pack_menu = menu_bar.addMenu('插件')
    with open('file/pack_list.txt', 'r', encoding='utf-8') as f:
        pack_list = eval(f.read())
    # 在菜单栏上显示插件状态（若无插件则显示“未安装插件”）
    plugin_label = QLabel()
    plugin_label.setStyleSheet("color: gray; padding: 4px;")
    plugin_label.setAlignment(Qt.AlignCenter)
    plugin_action = QWidgetAction(window)
    plugin_action.setDefaultWidget(plugin_label)
    pack_menu.addAction(plugin_action)
    if len(pack_list) == 0:
        plugin_label.setText("未安装插件，请前往 设置 安装插件")
    else:
            plugin_action.setVisible(False)
    
    def run_pack(pack_name):
        """返回一个 QAction，触发时执行插件文件夹下的 main.py 或 run.py（使用 runpy）。"""
        action = QAction(pack_name, window)

        def handler():
            global file,key
            if key != None:
                QMessageBox.information(window,'加密项目','F HamLog 会将项目解密后提供给插件，\n请确保插件来自可信的开发者。')
            import json
            with open(f'file/pypack/{pack_name}/input.fhl','w',encoding='utf-8') as f:
                json.dump(file, f, ensure_ascii=False, indent=2)
            subprocess.run(['python', f'file/pypack/{pack_name}/main.py'])
            try:
                with open(f'file/pypack/{pack_name}/output.fhl','r',encoding='utf-8') as f:
                    snapshot_before()
                    file = json.load(f)
            except FileNotFoundError:
                QMessageBox.warning(window, "插件错误", f"插件 {pack_name} 未正确生成输出文件！")
            table_update()
            os.remove(f'file/pypack/{pack_name}/input.fhl')
            os.remove(f'file/pypack/{pack_name}/output.fhl')

        action.triggered.connect(handler)
        return action

    for pack in pack_list:
        pack_menu.addAction(run_pack(pack))

    table_update(delete=False)
    table_update()

    window.show()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    main(win)
    app.exec()