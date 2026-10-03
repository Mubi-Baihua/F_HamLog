# -*- coding: utf-8 -*-
"""把「语言支持」的接入改动按精确字面量替换套用到各源文件。

只做机械替换；每处替换都要求原文**唯一命中**（count 校验），
任何一处没找到/命中多次都会报出来，方便人工复核。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IMPORT_TAIL = "from dialog_defaults import desktop_dir"
SP_THEME = "import satellite_pred as sp\nimport theme"

R = []   # (file, old, new, expected_count)


def add(f, old, new, n=1, expected=None):
    R.append((f, old, new, n if expected is None else expected))


# ----------------------------------------------------------------------
# 1) 各文件引入 i18n
# ----------------------------------------------------------------------
for f in ('project.py', 'batch_project.py', 'pack_set.py', 'export_adi.py',
          'input_fhl.py', 'input_adi.py', 'input_HAM_tolls.py', 'output_adi.py'):
    add(f, IMPORT_TAIL, IMPORT_TAIL + "\nimport i18n")

for f in ('satellite_window.py', 'mutual_window.py', 'satellite_map_window.py',
          'tle_source_window.py'):
    add(f, SP_THEME, SP_THEME + "\nimport i18n")

add('output_excel.py',
    "    from dialog_defaults import desktop_dir",
    "    from dialog_defaults import desktop_dir\n    import i18n")

# ----------------------------------------------------------------------
# 2) 文件对话框的标题 / 过滤器（原生对话框不走 Qt 控件树，必须调用处翻译）
# ----------------------------------------------------------------------
add('batch_project.py',
    "                '添加到 F HamLog项目',\n"
    "                desktop_dir(),\n"
    "                'F HamLog项目 (*.fhl)'",
    "                i18n.tr('添加到 F HamLog项目'),\n"
    "                desktop_dir(),\n"
    "                i18n.tr('F HamLog项目 (*.fhl)')")
add('batch_project.py',
    "                '另存为 F HamLog项目',\n"
    "                desktop_dir(),\n"
    "                'F HamLog项目 (*.fhl)'",
    "                i18n.tr('另存为 F HamLog项目'),\n"
    "                desktop_dir(),\n"
    "                i18n.tr('F HamLog项目 (*.fhl)')")
add('export_adi.py',
    "parent, '导出 ADIF (TQSL/LoTW)', desktop_dir(),\n"
    "        'ADIF 文件 (*.adi);;All Files (*)')",
    "parent, i18n.tr('导出 ADIF (TQSL/LoTW)'), desktop_dir(),\n"
    "        i18n.tr('ADIF 文件 (*.adi);;All Files (*)'))")
add('input_fhl.py',
    '"选择 F HamLog 项目文件",\n'
    '        desktop_dir(),\n'
    '        "F HamLog项目 (*.fhl);;All Files (*)"',
    'i18n.tr("选择 F HamLog 项目文件"),\n'
    '        desktop_dir(),\n'
    '        i18n.tr("F HamLog项目 (*.fhl);;All Files (*)")')
add('output_adi.py',
    'None, "导出 ADIF 文件 (TQSL/LoTW)", desktop_dir(),\n'
    '        "ADIF 文件 (*.adi);;All Files (*)")',
    'None, i18n.tr("导出 ADIF 文件 (TQSL/LoTW)"), desktop_dir(),\n'
    '        i18n.tr("ADIF 文件 (*.adi);;All Files (*)"))')
add('output_excel.py',
    '"导出为Excel文件",\n'
    '        desktop_dir(),\n'
    '        "Excel文件 (*.xlsx);;所有文件 (*)"',
    'i18n.tr("导出为Excel文件"),\n'
    '        desktop_dir(),\n'
    '        i18n.tr("Excel文件 (*.xlsx);;所有文件 (*)")')
add('input_adi.py',
    "'选择 ADI/ADIF 文件', desktop_dir(), 'ADI 文件 (*.adi);;All Files (*)')",
    "i18n.tr('选择 ADI/ADIF 文件'), desktop_dir(), "
    "i18n.tr('ADI 文件 (*.adi);;All Files (*)')")
add('input_HAM_tolls.py',
    '"选择Excel文件", desktop_dir(), "Excel文件 (*.xlsx *.xls)")',
    'i18n.tr("选择Excel文件"), desktop_dir(), i18n.tr("Excel文件 (*.xlsx *.xls)")')
add('pack_set.py',
    "'选择插件包', desktop_dir(), 'F HamLog插件包 (*.fhlpypack *.txt);;All Files (*)')",
    "i18n.tr('选择插件包'), desktop_dir(), "
    "i18n.tr('F HamLog插件包 (*.fhlpypack *.txt);;All Files (*)')")
add('project.py', '            "保存恢复的文件",', '            i18n.tr("保存恢复的文件"),')
add('project.py', '            "另存为文件",  # 对话框标题', '            i18n.tr("另存为文件"),  # 对话框标题')
add('project.py', '            "导出选中日志为FHL文件",', '            i18n.tr("导出选中日志为FHL文件"),')
add('project.py', '            "新建文件",  # 对话框标题', '            i18n.tr("新建文件"),  # 对话框标题')
add('project.py',
    'research_window, "导出搜索结果为FHL文件", desktop_dir(), "F HamLog项目 (*.fhl)")',
    'research_window, i18n.tr("导出搜索结果为FHL文件"), desktop_dir(), '
    'i18n.tr("F HamLog项目 (*.fhl)"))')
add('satellite_window.py',
    "            win, '导入卫星星历数据', desktop_dir(),\n"
    "            '星历文件 (*.tle *.txt *.csv);;TLE 文件 (*.tle);;'\n"
    "            'CSV 文件 (*.csv);;文本文件 (*.txt)')",
    "            win, i18n.tr('导入卫星星历数据'), desktop_dir(),\n"
    "            i18n.tr('星历文件 (*.tle *.txt *.csv);;TLE 文件 (*.tle);;'\n"
    "                    'CSV 文件 (*.csv);;文本文件 (*.txt)'))")

# ----------------------------------------------------------------------
# 3) 动态文案：自绘 / 状态栏 / 标题 等自动翻译覆盖不到的地方
# ----------------------------------------------------------------------
# project.py：自绘「更多 / 定位」按钮文字
add('project.py', "        btn_opt.text = self._text",
    "        btn_opt.text = i18n.tr(self._text)")
# project.py：窗口标题（未保存 * 前缀 + 多人日志标题）
add('project.py',
    "        title = _title_base() if base is None else base\n"
    "        window.setWindowTitle(('*' if dirty else '') + title)",
    "        title = _title_base() if base is None else base\n"
    "        window.setWindowTitle(('*' if dirty else '') + i18n.tr(title))")
# project.py：多人日志管理窗口的动态状态
add('project.py', "                status.setText('状态：未连接')",
    "                status.setText(i18n.tr('状态：未连接'))")
add('project.py', "                btn_open.setText('开放多人日志')",
    "                btn_open.setText(i18n.tr('开放多人日志'))")
add('project.py', "                status.setText(f'状态：服务端 {rc.host}:{rc.port}')",
    "                status.setText(i18n.tr(f'状态：服务端 {rc.host}:{rc.port}'))")
add('project.py', "                btn_open.setText('关闭多人日志')",
    "                btn_open.setText(i18n.tr('关闭多人日志'))")
add('project.py', "                lbl_pw.setText(rc.password or '（无）')",
    "                lbl_pw.setText(rc.password or i18n.tr('（无）'))")
add('project.py', "            btn.setText('已复制')",
    "            btn.setText(i18n.tr('已复制'))")
add('project.py', "            QTimer.singleShot(800, lambda: btn.setText('复制'))",
    "            QTimer.singleShot(800, lambda: btn.setText(i18n.tr('复制')))")
add('project.py', '        plugin_label.setText("未安装插件，请前往 设置 安装插件")',
    '        plugin_label.setText(i18n.tr("未安装插件，请前往 设置 安装插件"))')

# satellite_window.py：状态文字统一走 _status_set（先全量替换，再插辅助函数）
add('satellite_window.py', "status.setText(", "_status_set(",
    expected=13)
add('satellite_window.py', "        worker.progress.connect(status.setText)",
    "        worker.progress.connect(_status_set)")
add('satellite_window.py',
    "    status = QLabel('准备中…')\n"
    "    # 次要提示文字：深色模式下写死的 gray 会看不清，改为随主题取色\n"
    "    status.setStyleSheet(theme.hint_css())\n"
    "    layout.addWidget(status)",
    "    status = QLabel('准备中…')\n"
    "    # 次要提示文字：深色模式下写死的 gray 会看不清，改为随主题取色\n"
    "    status.setStyleSheet(theme.hint_css())\n"
    "    layout.addWidget(status)\n"
    "\n"
    "    def _status_set(text):\n"
    "        \"\"\"设置状态文字：动态文案按当前语言翻译后再显示。\"\"\"\n"
    "        status.setText(i18n.tr(text))")
add('satellite_window.py', "progress_bar.setFormat('下载星历 %p%')",
    "progress_bar.setFormat(i18n.tr('下载星历 %p%'))", expected=2)
add('satellite_window.py', "        self.count_label.setText(text)",
    "        self.count_label.setText(i18n.tr(text))")

# mutual_window.py：同上
add('mutual_window.py', "status.setText(", "_status_set(", expected=15)
add('mutual_window.py',
    "    status = QLabel('准备中…')\n"
    "    # 次要提示文字：深色模式下写死的 gray 会看不清，改为随主题取色\n"
    "    status.setStyleSheet(theme.hint_css())\n"
    "    layout.addWidget(status)",
    "    status = QLabel('准备中…')\n"
    "    # 次要提示文字：深色模式下写死的 gray 会看不清，改为随主题取色\n"
    "    status.setStyleSheet(theme.hint_css())\n"
    "    layout.addWidget(status)\n"
    "\n"
    "    def _status_set(text):\n"
    "        \"\"\"设置状态文字：动态文案按当前语言翻译后再显示。\"\"\"\n"
    "        status.setText(i18n.tr(text))")
add('mutual_window.py', "                _status_set(status.text() + '（可尝试降低最低仰角或延长预测时长）')",
    "                _status_set(status.text() + i18n.tr('（可尝试降低最低仰角或延长预测时长）'))")

# tle_source_window.py：状态栏 / 行提示 / 脏标记
add('tle_source_window.py',
    "    def _set_status(text, warn=False):\n"
    '        """统一设置状态文字与颜色（记住状态，便于主题切换时重刷）。"""\n'
    "        _status['text'], _status['warn'] = text, warn",
    "    def _set_status(text, warn=False):\n"
    '        """统一设置状态文字与颜色（记住状态，便于主题切换时重刷）。"""\n'
    "        text = i18n.tr(text)\n"
    "        _status['text'], _status['warn'] = text, warn")
add('tle_source_window.py',
    "    def _set_item_delay(item, text):\n"
    "        _guarded(lambda: item.setData(_ROLE_DELAY, text))",
    "    def _set_item_delay(item, text):\n"
    "        text = i18n.tr(text)\n"
    "        _guarded(lambda: item.setData(_ROLE_DELAY, text))")
add('tle_source_window.py',
    "        _set_status('%s（未保存，点「保存」写入文件）' % note)",
    "        _set_status(i18n.tr('%s（未保存，点「保存」写入文件）' % note))")
add('tle_source_window.py',
    "        _set_status('未修改：%s' % why, True)",
    "        _set_status(i18n.tr('未修改：%s' % why), True)")

# satellite_map_window.py：信息栏（逐段翻译后拼接）
add('satellite_map_window.py',
    "        parts.append('轨迹 %s → %s (%.0f h)' % (\n"
    "            now.strftime('%H:%M'), end.strftime('%H:%M'), self._track_hours))",
    "        parts.append(i18n.tr('轨迹 %s → %s (%.0f h)' % (\n"
    "            now.strftime('%H:%M'), end.strftime('%H:%M'), self._track_hours)))")
add('satellite_map_window.py',
    "            parts.append('显示 %d/%d 颗（还有 %d 颗未显示，可调大「最多显示的卫星」）'\n"
    "                         % (shown, total, hidden))",
    "            parts.append(i18n.tr('显示 %d/%d 颗（还有 %d 颗未显示，可调大「最多显示的卫星」）'\n"
    "                                 % (shown, total, hidden)))")
add('satellite_map_window.py',
    "            parts.append('显示 %d/%d 颗' % (shown, total))",
    "            parts.append(i18n.tr('显示 %d/%d 颗' % (shown, total)))")
add('satellite_map_window.py',
    "            s = '%s: 纬 %.2f° 经 %.2f° 高 %.0f km' % (\n"
    "                cur_entry['name'].strip(), lat, lon, alt)",
    "            s = i18n.tr('%s: 纬 %.2f° 经 %.2f° 高 %.0f km' % (\n"
    "                cur_entry['name'].strip(), lat, lon, alt))")
add('satellite_map_window.py',
    "                s += '，本台仰角 %.1f°（%s）' % (\n"
    "                    elev_a, '可见' if elev_a >= self._min_elev else '不可见')",
    "                s += i18n.tr('，本台仰角 %.1f°（%s）' % (\n"
    "                    elev_a, i18n.tr('可见') if elev_a >= self._min_elev\n"
    "                    else i18n.tr('不可见')))")
add('satellite_map_window.py',
    "                s += '，对方仰角 %.1f°（%s）' % (\n"
    "                    elev_b, '可见' if elev_b >= self._min_elev_b else '不可见')",
    "                s += i18n.tr('，对方仰角 %.1f°（%s）' % (\n"
    "                    elev_b, i18n.tr('可见') if elev_b >= self._min_elev_b\n"
    "                    else i18n.tr('不可见')))")
add('satellite_map_window.py',
    "            parts.append('未选择卫星（请在来源窗口刷新星历或选择卫星）')",
    "            parts.append(i18n.tr('未选择卫星（请在来源窗口刷新星历或选择卫星）'))")

# batch_project.py：列头（新增日志列时会重建）/ 时钟标签
add('batch_project.py',
    "        headers = ['模板'] + [f'第{i}条' for i in range(1, table.columnCount())]",
    "        headers = [i18n.tr('模板')] + [i18n.tr(f'第{i}条')\n"
    "                                      for i in range(1, table.columnCount())]")
add('batch_project.py',
    "        clock_label.setText('UTC %s   |   本地 %s (%s)'\n"
    "                            % (now_utc.strftime(fmt), now_local.strftime(fmt), tz_disp))",
    "        clock_label.setText(i18n.tr('UTC %s   |   本地 %s (%s)'\n"
    "                                    % (now_utc.strftime(fmt),\n"
    "                                       now_local.strftime(fmt), tz_disp)))")

# ----------------------------------------------------------------------
# 4) 各独立入口安装语言支持
# ----------------------------------------------------------------------
add('project.py',
    "if __name__ == '__main__':\n"
    "    app = QApplication(sys.argv)\n"
    "    win = QMainWindow()",
    "if __name__ == '__main__':\n"
    "    app = QApplication(sys.argv)\n"
    "    i18n.install(app)\n"
    "    win = QMainWindow()")
add('batch_project.py',
    "if __name__ == '__main__':\n"
    "    app = QApplication(sys.argv)\n"
    "    win = QMainWindow()",
    "if __name__ == '__main__':\n"
    "    app = QApplication(sys.argv)\n"
    "    i18n.install(app)\n"
    "    win = QMainWindow()")
add('satellite_window.py',
    "    from PySide6.QtWidgets import QApplication\n"
    "    app = QApplication([])\n"
    "    main(None)",
    "    from PySide6.QtWidgets import QApplication\n"
    "    app = QApplication([])\n"
    "    i18n.install(app)\n"
    "    main(None)")
add('mutual_window.py',
    "    from PySide6.QtWidgets import QApplication\n"
    "    app = QApplication([])\n"
    "    main(None)\n"
    "    app.exec()",
    "    from PySide6.QtWidgets import QApplication\n"
    "    app = QApplication([])\n"
    "    i18n.install(app)\n"
    "    main(None)\n"
    "    app.exec()")
add('satellite_map_window.py',
    "    from PySide6.QtWidgets import QApplication\n"
    "    app = QApplication([])\n"
    "    sats = sp.load_amateur_satellites()",
    "    from PySide6.QtWidgets import QApplication\n"
    "    app = QApplication([])\n"
    "    i18n.install(app)\n"
    "    sats = sp.load_amateur_satellites()")
add('tle_source_window.py',
    "if __name__ == '__main__':\n"
    "    app = QApplication()\n"
    "    main(QMainWindow())",
    "if __name__ == '__main__':\n"
    "    app = QApplication()\n"
    "    i18n.install(app)\n"
    "    main(QMainWindow())")
add('pack_set.py',
    "if __name__ == '__main__':\n"
    "    app = QApplication()\n"
    "    window=QMainWindow()",
    "if __name__ == '__main__':\n"
    "    app = QApplication()\n"
    "    i18n.install(app)\n"
    "    window=QMainWindow()")


def main():
    failed = []
    for f, old, new, want in R:
        path = os.path.join(ROOT, f)
        if not os.path.exists(path):
            failed.append((f, 'FILE-MISSING', old[:50]))
            continue
        src = io.open(path, 'r', encoding='utf-8').read()
        got = src.count(old)
        if got != want:
            failed.append((f, 'count=%d want=%d' % (got, want), old[:60]))
            continue
        src = src.replace(old, new)
        io.open(path, 'w', encoding='utf-8', newline='').write(src)
        print('OK  %-24s %s' % (f, old.replace('\n', ' | ')[:64]))
    print()
    if failed:
        print('!! 未套用 %d 处：' % len(failed))
        for f, why, snip in failed:
            print('   %-24s %-14s %s' % (f, why, snip.replace('\n', ' | ')))
        return 1
    print('全部套用完成。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
