from PySide6.QtWidgets import *
from PySide6.QtGui import QAction
import sys
import os

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

        file_length = len(file)
        # 创建表格部件
        table = QTableWidget(file_length, 13)  # 5行3列
        table.setHorizontalHeaderLabels(["对方呼号", "己方信号报告", "对方信号报告", "己方QTH", "对方QTH","己方设备","对方设备","己方天线","对方天线","己方功率","对方功率" ,"编辑", "删除"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # 添加一些示例数据
        for i in range(file_length):
            name = QTableWidgetItem(file[i]['name'])
            table.setItem(i, 0, name)
            place = QTableWidgetItem(file[i]['place'])
            table.setItem(i, 1, place)
            data = QTableWidgetItem(f'{len(file[i]['data'])}项')
            table.setItem(i, 2, data)
            edit_button = QPushButton("编辑")
            table.setCellWidget(i, 3, edit_button)
            edit_button.clicked.connect(lambda: print('edit'))
            delete_button = QPushButton("删除")
            table.setCellWidget(i, 4, delete_button)
            delete_button.clicked.connect(lambda: print('delete'))

            # 将表格添加到布局中
        layout.addWidget(table)

    def new():
        global file, window_n
        #import new_log
        print('new')
        # file.append({'name': '新建项', 'place': '新建项', 'data': []})
        window_n = QMainWindow()
        #new_log.main(window_n)
        table_update()

    def save():
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(str(file))
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
    window.resize(1350, 700)
    window.setWindowTitle(f'F Order Statistics 1 - {os.path.basename(save_path)}')
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

    zexit_action = QAction('直接退出', window)
    zexit_action.triggered.connect(lambda: sys.exit())
    file_menu.addAction(zexit_action)

    central_widget = QWidget()
    window.setCentralWidget(central_widget)
    layout = QVBoxLayout(central_widget)

    button_new = QPushButton("新建项（Ctrl+N）", window)
    button_new.setShortcut('Ctrl+N')
    button_new.clicked.connect(lambda: new())
    layout.addWidget(button_new)

    table_update(delete=False)

    window.show()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = QMainWindow()
    main(win)
    app.exec()