from PySide6.QtWidgets import *
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt  # 新增导入 Qt
from functools import partial
import time as time_
import sys
import os
import re
import subprocess
import webbrowser
import urllib.parse

file = None


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


def main(window, filee='', save_path='',quick_poject=False):
    global file
    if isinstance(filee, list):
        file = filee
        _upgrade_file_records(file)
    else:
        file = []
    table = None

    def table_update(delete=True):
        nonlocal table
        if delete:
            layout.removeWidget(table)
            table.deleteLater()
            table = None
            list_time(message=False)
            save(message=False)
            

        file_length = len(file)
        # 创建表格部件，增加到14列以容纳“选择”复选框
        table = QTableWidget(file_length, 14)
        table.setHorizontalHeaderLabels(["选择","日期","时间","己方呼号","对方呼号","频率","调制模式","传播模式","卫星名称", "己方接收信号", "对方接收信号", "己方QTH", "对方QTH","更多"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
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

    def new():
            with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
                xml_dict = eval(f.read())
            global project_others_window,file
            index = len(file)
            date = time_.strftime("%Y-%m-%d", time_.localtime())
            time = time_.strftime("%H:%M", time_.localtime())
            file_app = {
                'date': date,
                'time': time,
                'm_call': xml_dict['m_call'],
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
            
            project_others_window = QMainWindow()
            project_others_window.resize(400, 650)
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
                        if not re.search(r'^\d{2}:\d{2}$', table_others.item(row, 1).text()):
                            QMessageBox.warning(project_others_window, "格式错误", f"时间格式错误，应为HH:MM")
                            return
                    elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                        if table_others.item(row, 1).text() == '':
                            QMessageBox.warning(project_others_window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                            return

                    item = table_others.item(row, 1)  # 第二列是可编辑的内容
                    if item!=None:
                        file_app[key] = item.text()
                project_others_window.close()

                file.append(file_app)

                table_update()
            save_button = QPushButton("新建日志")
            save_button.clicked.connect(save_changes)
            layout_others.addWidget(save_button)
            
            project_others_window.show()

    def project_others(index):
        global project_others_window,file
        project_others_window = QMainWindow()
        project_others_window.resize(400, 670)
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
                    if not re.search(r'^\d{2}:\d{2}$', table_others.item(row, 1).text()):
                        QMessageBox.warning(project_others_window, "格式错误", f"时间格式错误，应为HH:MM")
                        return
                elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                    if table_others.item(row, 1).text() == '':
                        QMessageBox.warning(project_others_window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                        return

                item = table_others.item(row, 1)  # 第二列是可编辑的内容
                if item!=None:
                    file[index][key] = item.text()
            project_others_window.close()
            table_update()
        def del_log(index):
            if QMessageBox.question(window, "删除日志", "确定要删除此日志吗？") == QMessageBox.Yes:
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
        layout_others.addWidget(qrz_button)
        save_button = QPushButton("保存更改")
        save_button.clicked.connect(save_changes)
        layout_others.addWidget(save_button)

        del_button = QPushButton("删除日志")
        del_button.clicked.connect(lambda:del_log(index))
        layout_others.addWidget(del_button)
        
        
        project_others_window.show()

    def save(message=True):
        with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
            xml_dict = eval(f.read())

        aouto_save_b = xml_dict['aouto_save']

        if (not(message) and aouto_save_b) or message:
            import json
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(file, f, ensure_ascii=False, indent=2)
                if message:
                    QMessageBox.information(window, "保存成功", "保存成功！")

    def osave():
        import json
        save_path, _ = QFileDialog.getSaveFileName(
            window,  # 父窗口，可以是None或者您的主窗口
            "另存为文件",  # 对话框标题
            "",  # 初始目录，空字符串表示使用系统默认
            "F HamLog项目 (*.fhl)"  # 文件过滤器，只显示.fos文件
        )
        if save_path == '':
            return
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(file, f, ensure_ascii=False, indent=2)
            QMessageBox.information(window, "另存成功", "另存成功！")

    def esave():
        import json
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(file, f, ensure_ascii=False, indent=2)
            QMessageBox.information(window, "保存成功", "保存成功！")
        sys.exit()

    def input_HAM_tolls_():
        global file
        old_file = file.copy()  # 使用copy()确保是深拷贝
        import input_HAM_tolls
        file = input_HAM_tolls.main(file)
        table_update()
        if file == old_file:  # 如果没有导入任何内容，则不保存
            return
        if QMessageBox.question(window, "导入日志", "应用导入吗？") == QMessageBox.No:
            file = old_file
            table_update()  # 确保界面更新
    
    def import_from_ADI():
        global file
        old_file = file.copy()
        import input_adi
        try:
            file = input_adi.main(file)
        except Exception as e:
            QMessageBox.warning(window, "导入失败", f"导入 ADI 失败：{e}")
            return
        if file == old_file:  # 如果没有导入任何内容，则不保存
            return
        table_update()
        if QMessageBox.question(window, "导入日志", "应用导入吗？") == QMessageBox.No:
            file = old_file
            table_update()
    
    def input_fhl():
        global file
        old_file = file.copy()  # 使用copy()确保是深拷贝
        import input_fhl
        file = input_fhl.main(file)
        table_update()
        if file == old_file:  # 如果没有导入任何内容，则不保存
            return
        if QMessageBox.question(window, "导入日志", "应用导入吗？") == QMessageBox.No:
            file = old_file
            table_update()
    
    def output_adi(file):
        import output_adi

        if output_adi.main(file):
            QMessageBox.information(window, "导出成功", "导出成功！")

    def output_excel(file):
        import output_excel
        if output_excel.main(file):
            QMessageBox.information(window, "导出成功", "导出成功！")

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

    def output_selected_fhl():
        selected_records = get_selected_records()
        if not selected_records:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            window,
            "导出选中日志为FHL文件",
            "",
            "F HamLog项目 (*.fhl)"
        )
        if not save_path:
            return
        import json
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(selected_records, f, ensure_ascii=False, indent=2)
        QMessageBox.information(window, "导出成功", "导出成功！")

    def output_selected_adi():
        selected_records = get_selected_records()
        if not selected_records:
            return
        import output_adi
        if output_adi.main(selected_records):
            QMessageBox.information(window, "导出成功", "导出成功！")

    def output_selected_excel():
        selected_records = get_selected_records()
        if not selected_records:
            return
        import output_excel
        if output_excel.main(selected_records):
            QMessageBox.information(window, "导出成功", "导出成功！")

    if save_path == '':
        save_path, _ = QFileDialog.getSaveFileName(
            window,  # 父窗口，可以是None或者您的主窗口
            "新建文件",  # 对话框标题
            "",  # 初始目录，空字符串表示使用系统默认
            "F HamLog项目 (*.fhl)"  # 文件过滤器，只显示.fos文件
        )
        if save_path == '':
            return
    print(save_path)
    window.resize(1400, 700)
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

    sexit_action = QAction('保存并退出', window)
    sexit_action.triggered.connect(lambda: esave())
    file_menu.addAction(sexit_action)

    zexit_action = QAction('退出', window)
    zexit_action.triggered.connect(lambda: sys.exit())
    file_menu.addAction(zexit_action)

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
        h2.addWidget(edit)
        dlg_layout.addLayout(h2)

        h3 = QHBoxLayout()
        h3.addWidget(QLabel('匹配方式：'))
        match_combo = QComboBox()
        match_combo.addItems(['包含', '完全匹配'])
        h3.addWidget(match_combo)
        dlg_layout.addLayout(h3)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        field = combo.currentData()
        q = edit.text().strip().lower()
        if q == '':
            QMessageBox.information(window, '搜索', '请输入关键词。')
            return
        exact = (match_combo.currentText() == '完全匹配')

        matches = []
        for i, rec in enumerate(file):
            val = str(rec.get(field, '')).lower()
            if (exact and val == q) or (not exact and q in val):
                matches.append((i, rec))

        if not matches:
            QMessageBox.information(window, "搜索结果", "未找到任何匹配记录。")
            return

        research_window = QMainWindow()
        research_window.resize(1400, 500)
        research_window.setWindowTitle(f"搜索结果：{edit.text().strip()}")
        central = QWidget()
        research_window.setCentralWidget(central)
        lay = QVBoxLayout(central)
        table_r = QTableWidget(len(matches), 13)
        table_r.setHorizontalHeaderLabels(["日期","时间","己方呼号","对方呼号","频率","调制模式","传播模式","卫星名称", "己方接收信号", "对方接收信号", "己方QTH", "对方QTH","更多"])
        table_r.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for row, (orig_index, rec) in enumerate(matches):
            table_r.setItem(row, 0, QTableWidgetItem(rec.get('date', '')))
            table_r.setItem(row, 1, QTableWidgetItem(rec.get('time', '')))
            table_r.setItem(row, 2, QTableWidgetItem(rec.get('m_call', '')))
            table_r.setItem(row, 3, QTableWidgetItem(rec.get('o_call', '')))
            table_r.setItem(row, 4, QTableWidgetItem(rec.get('freq', '')))
            table_r.setItem(row, 5, QTableWidgetItem(rec.get('mode', '')))
            table_r.setItem(row, 6, QTableWidgetItem(rec.get('prop_mode', '')))
            table_r.setItem(row, 7, QTableWidgetItem(rec.get('sat_name', '')))
            table_r.setItem(row, 8, QTableWidgetItem(rec.get('m_rst', '')))
            table_r.setItem(row, 9, QTableWidgetItem(rec.get('o_rst', '')))
            table_r.setItem(row, 10, QTableWidgetItem(rec.get('m_qth', '')))
            table_r.setItem(row, 11, QTableWidgetItem(rec.get('o_qth', '')))
            more_btn = QPushButton("更多")
            more_btn.clicked.connect(partial(project_others, orig_index))
            table_r.setCellWidget(row, 12, more_btn)

        table_r.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table_r.setColumnWidth(0, 80)
        table_r.setColumnWidth(1, 70)
        table_r.setColumnWidth(2, 90)
        table_r.setColumnWidth(3, 90)
        table_r.setColumnWidth(4, 70)
        table_r.setColumnWidth(5, 80)
        table_r.setColumnWidth(6, 90)
        table_r.setColumnWidth(7, 90)
        table_r.setColumnWidth(8, 80)
        table_r.setColumnWidth(9, 80)
        table_r.setColumnWidth(10, 120)
        table_r.setColumnWidth(11, 120)
        table_r.setColumnWidth(12, 80)

        lay.addWidget(table_r)
        table_r.scrollToBottom()
        research_window.show()

    def show_statistics():
        global file
        dlg = QDialog(window)
        dlg.setWindowTitle('统计图表')  # 窗口标题
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

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btns)

        if dlg.exec() != QDialog.Accepted:
            return

        field = combo_stat.currentData()
        chart_type = chart_combo.currentText()

        # 统计各项出现次数
        counts = {}
        for rec in file:
            val = str(rec.get(field, '')).strip()
            if val == '':
                val = '<空>'
            counts[val] = counts.get(val, 0) + 1

        if not counts:
            QMessageBox.information(window, '统计', '没有可统计的数据。')
            return

        # 绘图
        try:
            import matplotlib.pyplot as plt
            import matplotlib
            # 设置中文字体
            matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
            matplotlib.rcParams['axes.unicode_minus'] = False  # 正常显示负号
        except Exception:
            QMessageBox.warning(window, '缺少依赖', '未安装 matplotlib，请运行: pip install matplotlib')
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

    stats_action = QAction('统计图表', window)
    stats_action.setShortcut('Ctrl+Shift+P')
    stats_action.triggered.connect(lambda: show_statistics())
    tool_menu.addAction(stats_action)

    tool_menu.addSeparator()

    research_call_action = QAction('搜索', window)
    research_call_action.setShortcut('Ctrl+R')
    research_call_action.triggered.connect(lambda: research_call(file))
    tool_menu.addAction(research_call_action)

    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)

    button_new = QPushButton("新建日志（Ctrl+N）", window)
    button_new.setShortcut('Ctrl+N')
    button_new.clicked.connect(lambda: new())
    layout.addWidget(button_new)

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
            global file
            import json
            with open(f'file/pypack/{pack_name}/input.fhl','w',encoding='utf-8') as f:
                json.dump(file, f, ensure_ascii=False, indent=2)
            subprocess.run(['python', f'file/pypack/{pack_name}/main.py'])
            try:
                with open(f'file/pypack/{pack_name}/output.fhl','r',encoding='utf-8') as f:
                    file = json.load(f)
            except FileNotFoundError:
                QMessageBox.warning(window, "插件错误", f"插件 {pack_name} 未正确生成输出文件！")
            table_update()

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