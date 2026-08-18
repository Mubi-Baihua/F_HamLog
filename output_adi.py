"""ADIF 导出（兼容 TQSL / LoTW）。

实际的字段映射与转换统一在 export_adi.py 中实现（含本地时间转 UTC、标准
BAND 命名、STATION_CALLSIGN 等）。这里保留原入口，供 project.py 的
“导出ADI文件” / “导出选中的日志为ADI” 菜单调用，直接复用 export_adi，
确保主日志与卫星批量记录的 ADIF 导出完全一致且 TQSL 合规。
"""
from PySide6.QtWidgets import QFileDialog, QMessageBox
from dialog_defaults import desktop_dir


def main(file):
    if not file:
        QMessageBox.warning(None, '提示', '当前没有可导出的日志。')
        return False
    path, _ = QFileDialog.getSaveFileName(
        None, "导出 ADIF 文件 (TQSL/LoTW)", desktop_dir(),
        "ADIF 文件 (*.adi);;All Files (*)")
    if not path:
        return False
    if not path.lower().endswith('.adi'):
        path += '.adi'
    import export_adi
    text = export_adi.records_to_adif(file)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        QMessageBox.information(None, "导出成功", f"已导出 {len(file)} 条记录到：\n{path}")
        return True
    except Exception as e:
        print(f"导出 ADIF 时出错: {e}")
        QMessageBox.warning(None, "导出失败", str(e))
        return False
