from PySide6.QtWidgets import *
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt  # 新增导入 Qt
from functools import partial
import time as time_
import sys
import os
import re

file = None


def main(window, filee='', save_path=''):
    global file
    file = filee
    if file != '':
        file = eval(file)
    else:
        file = []
    table = None

    


    def table_update(delete=True):
        global window, table
        if delete:
            layout.removeWidget(table)
            table.deleteLater()
            table = None
            save(masage=False)
            

        file_length = len(file)
        # 创建表格部件
        table = QTableWidget(file_length, 11) 
        table.setHorizontalHeaderLabels(["日期","时间","己方呼号","对方呼号","频率","调制模式", "己方信号报告", "对方信号报告", "己方QTH", "对方QTH","更多"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        print(file_length)
        # 添加一些示例数据
        for i in range(file_length):
            date = QTableWidgetItem(file[i]['date'])
            table.setItem(i, 0, date)
            time = QTableWidgetItem(file[i]['time'])
            table.setItem(i, 1, time)
            m_call = QTableWidgetItem(file[i]['m_call'])
            table.setItem(i, 2, m_call)
            o_call = QTableWidgetItem(file[i]['o_call'])
            table.setItem(i, 3, o_call)
            freq = QTableWidgetItem(file[i]['freq'])
            table.setItem(i, 4, freq)
            mode = QTableWidgetItem(file[i]['mode'])
            table.setItem(i, 5, mode)
            m_rst = QTableWidgetItem(file[i]['m_rst'])
            table.setItem(i, 6, m_rst)
            o_rst = QTableWidgetItem(file[i]['o_rst'])
            table.setItem(i, 7, o_rst)
            m_qth = QTableWidgetItem(file[i]['m_qth'])
            table.setItem(i, 8, m_qth)
            o_qth = QTableWidgetItem(file[i]['o_qth'])
            table.setItem(i, 9, o_qth)
            other_button = QPushButton("更多")
            table.setCellWidget(i, 10, other_button)
            other_button.clicked.connect(partial(project_others, i))

            # 将表格添加到布局中
        layout.addWidget(table)

        table.scrollToBottom()  # 自动跳到底部

    def new():
        with open('file/m_xml.txt', 'r', encoding='utf-8') as f:
            xml_dict = eval(f.read())
        global project_others_window,file
        index = len(file)
        date = time_.strftime("%Y-%m-%d", time_.localtime())
        time = time_.strftime("%H:%M", time_.localtime())
        file.append({
            'date': date,
            'time': time,
            'm_call': xml_dict['m_call'],
            'o_call': '',
            'freq': '',
            'mode': '',
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
        })
        
        project_others_window = QMainWindow()
        project_others_window.resize(400, 600)
        project_others_window.setWindowTitle('新建日志')
        table_others = QTableWidget(17, 2)
        table_others.setColumnWidth(0, 100)  # 设置第1列宽度为100
        table_others.setColumnWidth(1, 250)
        
        table_others.setHorizontalHeaderLabels(["项目", "内容"])
        translation_dict = {
            'date': '日期',
            'time': '时间',
            'm_call': '己方呼号',
            'o_call': '对方呼号',
            'freq': '频率',
            'mode': '调制模式',
            'm_rst': '己方信号报告','o_rst': '对方信号报告',
            'm_qth': '己方QTH','o_qth': '对方QTH',
            "m_dig": '己方设备','o_dig': '对方设备',
            'm_ant': '己方天线','o_ant': '对方天线',
            'm_pow': '己方功率','o_pow': '对方功率',
            'notes': '备注'
        }
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
        save_button = QPushButton("新建日志")
        save_button.clicked.connect(save_changes)
        layout_others.addWidget(save_button)
        
        project_others_window.show()

    def project_others(index):
        global project_others_window,file
        project_others_window = QMainWindow()
        project_others_window.resize(400, 650)
        project_others_window.setWindowTitle('更多信息')
        table_others = QTableWidget(17, 2)
        table_others.setColumnWidth(0, 100)  # 设置第1列宽度为100
        table_others.setColumnWidth(1, 250)
        
        table_others.setHorizontalHeaderLabels(["项目", "内容"])
        translation_dict = {
            'date': '日期',
            'time': '时间',
            'm_call': '己方呼号',
            'o_call': '对方呼号',
            'freq': '频率',
            'mode': '调制模式',
            'm_rst': '己方信号报告','o_rst': '对方信号报告',
            'm_qth': '己方QTH','o_qth': '对方QTH',
            "m_dig": '己方设备','o_dig': '对方设备',
            'm_ant': '己方天线','o_ant': '对方天线',
            'm_pow': '己方功率','o_pow': '对方功率',
            'notes': '备注'
        }
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
        save_button = QPushButton("保存更改")
        save_button.clicked.connect(save_changes)
        layout_others.addWidget(save_button)

        del_button = QPushButton("删除日志")
        del_button.clicked.connect(lambda:del_log(index))
        layout_others.addWidget(del_button)
        
        project_others_window.show()

    def save(masage=True):
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(str(file))
            if masage:
                QMessageBox.information(window, "保存成功", "保存成功！")

    def osave():
        save_path, _ = QFileDialog.getSaveFileName(
            window,  # 父窗口，可以是None或者您的主窗口
            "另存为文件",  # 对话框标题
            "",  # 初始目录，空字符串表示使用系统默认
            "F HamLog项目 (*.fhl)"  # 文件过滤器，只显示.fos文件
        )
        if save_path == '':
            return
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(str(file))
            QMessageBox.information(window, "另存成功", "另存成功！")

    def esave():
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(str(file))
            QMessageBox.information(window, "保存成功", "保存成功！")
        sys.exit()

    def import_from_HAM_tolls_():
        global file
        old_file = file.copy()  # 使用copy()确保是深拷贝
        import import_from_HAM_tolls
        file = import_from_HAM_tolls.main(file)
        table_update()
        if QMessageBox.question(window, "导入日志", "应用导入吗？") == QMessageBox.No:
            file = old_file
            table_update()  # 确保界面更新
    
    def output_adi(file):
        import output_adi
        output_adi.main(file)
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
    window.resize(1200, 700)
    window.setWindowTitle(f'F HamLog 1 - {os.path.basename(save_path)}')
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

    import_from_HAM_tolls_action = QAction('从 HAM个人工具 导入日志', window)
    import_from_HAM_tolls_action.triggered.connect(lambda: import_from_HAM_tolls_())
    file_menu.addAction(import_from_HAM_tolls_action)

    export_adi_action = QAction('导出ADI文件', window)
    export_adi_action.triggered.connect(lambda: output_adi(file))
    file_menu.addAction(export_adi_action)



    file_menu.addSeparator()

    sexit_action = QAction('保存并退出', window)
    sexit_action.triggered.connect(lambda: esave())
    file_menu.addAction(sexit_action)

    zexit_action = QAction('退出', window)
    zexit_action.triggered.connect(lambda: sys.exit())
    file_menu.addAction(zexit_action)

    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)

    button_new = QPushButton("新建日志（Ctrl+N）", window)
    button_new.setShortcut('Ctrl+N')
    button_new.clicked.connect(lambda: new())
    layout.addWidget(button_new)

    table_update(delete=False)
    table_update()

    window.show()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    main(win)
    app.exec()