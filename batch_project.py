from PySide6.QtWidgets import *
from PySide6.QtCore import Qt  # 新增导入 Qt
from functools import partial
import time as time_
import sys
import re
import json
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

page_index = 0
fhl_list= []

def main(window):
    window.resize(410, 660)
    window.setWindowTitle('批量记录')
    
    with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
        xml_dict = eval(f.read())

    date = time_.strftime("%Y-%m-%d", time_.localtime())
    time = time_.strftime("%H:%M", time_.localtime())
    
    app_list = {
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
                
        item2 = QTableWidgetItem(app_list[i])  # 第2列可以编辑
        table_others.setItem(row, 1, item2)
        row += 1
    central_widget = QWidget()
    window.setCentralWidget(central_widget)

    def save_changes(app_list):
        global fhl_list,window_page,page_index,fhl_list

        keys_list = list(translation_dict.keys())
        for row in range(len(keys_list)):
            key = keys_list[row]

            if key == 'date':
                if not (re.search(r'^\d{4}-\d{2}-\d{2}$', table_others.item(row, 1).text()) or table_others.item(row, 1).text() == ''):
                        QMessageBox.warning(window, "格式错误", f"日期格式错误，应为YYYY-MM-DD")
                        return
            elif key == 'time':
                if not (re.search(r'^\d{2}:\d{2}$', table_others.item(row, 1).text()) or table_others.item(row, 1).text() == ''):
                    QMessageBox.warning(window, "格式错误", f"时间格式错误，应为HH:MM")
                    return

        for row in range(table_others.rowCount()):
            key = list(translation_dict.keys())[row]
            value = table_others.item(row, 1).text()
            app_list[key] = value

        
        print("填充的内容:", app_list)
        window.close()

        fhl_list= []

        page_index = 0

        show_page(app_list)

        
    def show_page(app_list):
        global fhl_list,window_page,page_index,fhl_list
        page_sum = len(fhl_list)

        if page_index+1 > page_sum:
            page_sum = page_index+1
            this_app_list = app_list
        else:
            this_app_list = fhl_list[page_index]

        window_page = QMainWindow() 
        window_page.resize(410, 660)
        window_page.setWindowTitle('批量记录')

        page_widget = QWidget()
        window_page.setCentralWidget(page_widget)

        layout_page = QVBoxLayout(page_widget)

        label_page = QLabel(f"第 {page_index + 1} 条  共 {page_sum} 条")
        label_page.setAlignment(Qt.AlignCenter)

        if app_list['date'] == '':
            this_app_list['date'] = time_.strftime("%Y-%m-%d", time_.localtime())
        if app_list['time'] == '':
            this_app_list['time'] = time_.strftime("%H:%M", time_.localtime())

        layout_page.addWidget(label_page)

        rows = len(translation_dict)
        table_others_page = QTableWidget(rows, 2)
        table_others_page.setColumnWidth(0, 100)  # 设置第1列宽度为100
        table_others_page.setColumnWidth(1, 250)
        table_others_page.setHorizontalHeaderLabels(["项目", "内容"])
        row = 0
        for i in translation_dict.keys():
            item = QTableWidgetItem(translation_dict[i])
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)  # 禁止编辑
            table_others_page.setItem(row, 0, item)
                        
            item2 = QTableWidgetItem(this_app_list[i])  # 第2列可以编辑
            table_others_page.setItem(row, 1, item2)
            row += 1

        layout_page.addWidget(table_others_page)

        def navigate_page(window,direction, app_list,table_others_page):
            global fhl_list,page_index

            app_dict_now = {}

            for row in range(table_others_page.rowCount()):
                key = list(translation_dict.keys())[row]
                value = table_others_page.item(row, 1).text()
                app_dict_now[key] = value
            
            keys_list = list(translation_dict.keys())
            for row in range(len(keys_list)):
                key = keys_list[row]

                if key == 'date':
                    if not re.search(r'^\d{4}-\d{2}-\d{2}$', table_others_page.item(row, 1).text()):
                            QMessageBox.warning(window, "格式错误", f"日期格式错误，应为YYYY-MM-DD")
                            return
                elif key == 'time':
                    if not re.search(r'^\d{2}:\d{2}$', table_others_page.item(row, 1).text()):
                        QMessageBox.warning(window, "格式错误", f"时间格式错误，应为HH:MM")
                        return
                elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                    if table_others_page.item(row, 1).text() == '':
                        QMessageBox.warning(window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                        return

            if page_index+1 > len(fhl_list):
                fhl_list.append(app_dict_now)
            else:
                fhl_list[page_index] = app_dict_now

            page_index += direction

            show_page(app_list)

        def save_page_changes(window,table_others_page):
            global fhl_list,page_index
            app_dict_now = {}

            for row in range(table_others_page.rowCount()):
                key = list(translation_dict.keys())[row]
                value = table_others_page.item(row, 1).text()
                app_dict_now[key] = value
            
            keys_list = list(translation_dict.keys())
            for row in range(len(keys_list)):
                key = keys_list[row]

                if key == 'date':
                    if not re.search(r'^\d{4}-\d{2}-\d{2}$', table_others_page.item(row, 1).text()):
                            QMessageBox.warning(window, "格式错误", f"日期格式错误，应为YYYY-MM-DD")
                            return
                elif key == 'time':
                    if not re.search(r'^\d{2}:\d{2}$', table_others_page.item(row, 1).text()):
                        QMessageBox.warning(window, "格式错误", f"时间格式错误，应为HH:MM")
                        return
                elif key == 'm_call' or key == 'o_call' or key == 'freq' or key == 'mode'or key == 'm_rst' or key == 'o_rst':
                    if table_others_page.item(row, 1).text() == '':
                        QMessageBox.warning(window, "格式错误", f"缺少 {translation_dict[key]} (必填)")
                        return

            if page_index+1 > len(fhl_list):
                fhl_list.append(app_dict_now)
            else:
                fhl_list[page_index] = app_dict_now

            if not fhl_list:
                QMessageBox.warning(window, "提示", "没有可保存的记录。")
                return

            def save_records_to_path(records, save_path,key = None):
                fhl_rw.write_fhl_file(save_path, records,key)

            def load_records_from_path(load_path):
                if not os.path.exists(load_path):
                    return []
                data,key = fhl_rw.read_fhl_file(load_path)
                return data,key

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
                records,key = load_records_from_path(project_path)
                records.extend(fhl_list)
                save_records_to_path(records, project_path,key)
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
                records,key = load_records_from_path(default_path)
                records.extend(fhl_list)
                save_records_to_path(records, default_path,key)
                QMessageBox.information(finish_dialog, '完成', f'已添加到 {len(fhl_list)} 条记录到默认通联日志')
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

        button_layout = QVBoxLayout()
        button_layout.setSpacing(10)
        button_layout.setContentsMargins(0, 0, 0, 0)

        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(10)
        nav_layout.setContentsMargins(0, 0, 0, 0)

        button_last = QPushButton('上一条')
        button_last.clicked.connect(lambda: navigate_page(window,-1, app_list,table_others_page))
        if page_index == 0:
            button_last.setEnabled(False)
        button_next = QPushButton('下一条')
        button_next.clicked.connect(lambda: navigate_page(window,1, app_list,table_others_page))
        button_save = QPushButton('完成')
        button_save.clicked.connect(lambda: save_page_changes(window,table_others_page))

        nav_layout.addWidget(button_last)
        nav_layout.addStretch(1)
        nav_layout.addWidget(button_next)
        nav_layout.addWidget(button_save)

        button_layout.addLayout(nav_layout)

        layout_page.addLayout(button_layout)

        window_page.show()


    label = QLabel("请输入批量记录的模板（日期与时间为空则自动填充）")
    label.setAlignment(Qt.AlignCenter)

    save_button = QPushButton("下一步")
    save_button.clicked.connect(lambda: save_changes(app_list))
    
    
    layout_others = QVBoxLayout(central_widget)
    layout_others.addWidget(label)
    layout_others.addWidget(table_others)
    layout_others.addWidget(save_button)

    window.show()
    

if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    main(win)
    app.exec()