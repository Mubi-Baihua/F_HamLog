import json
from PySide6.QtWidgets import *
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


def _ensure_log_keys(entry):
    """确保单条记录包含项目所需字段。"""
    defaults = {
        'date': '',
        'time': '',
        'm_call': '',
        'o_call': '',
        'freq': '',
        'freq_rx': '',
        'mode': '',
        'prop_mode': '',
        'sat_name': '',
        'm_rst': '',
        'o_rst': '',
        'm_qth': '',
        'o_qth': '',
        'm_dig': '',
        'o_dig': '',
        'm_ant': '',
        'o_ant': '',
        'm_pow': '',
        'o_pow': '',
        'notes': ''
    }
    if not isinstance(entry, dict):
        return defaults.copy()

    normalized = defaults.copy()
    for key, value in entry.items():
        if key is not None:
            normalized[key] = value
    for key in defaults:
        if normalized.get(key) is None:
            normalized[key] = defaults[key]
    return normalized


def _normalize_records(records):
    if not isinstance(records, list):
        return []

    normalized = []
    for item in records:
        if isinstance(item, dict):
            normalized.append(_ensure_log_keys(item))
    return normalized


def _dup_key(record):
    return (
        (record.get('o_call') or '').strip().lower(),
        record.get('date', ''),
        record.get('time', '')
    )


def main(file_list):
    print("导入F_HamLog项目")

    file_path, _ = QFileDialog.getOpenFileName(
        None,
        "选择 F HamLog 项目文件",
        "",
        "F HamLog项目 (*.fhl);;All Files (*)"
    )
    if not file_path:
        return list(file_list or [])

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                data = eval(f.read())
        except Exception:
            QMessageBox.warning(None, "导入失败", "无法读取所选的 F HamLog 项目文件。")
            return list(file_list or [])

    records = _normalize_records(data if isinstance(data, list) else [])
    if not records:
        QMessageBox.information(None, "导入完成", "所选文件中没有可导入的日志记录。")
        return list(file_list or [])

    out = list(file_list or [])

    existing_keys = set()
    for entry in out:
        key = _dup_key(entry)
        if key[0] and key[1] and key[2]:
            existing_keys.add(key)

    mapped_dup = []
    mapped_nondup = []
    dup_keys = set()
    for record in records:
        key = _dup_key(record)
        if key[0] and key[1] and key[2] and key in existing_keys:
            mapped_dup.append(record)
            dup_keys.add(key)
        else:
            mapped_nondup.append(record)

    if mapped_dup:
        msg = QMessageBox()
        msg.setWindowTitle("检测到重复记录")
        msg.setText(f"检测到 {len(mapped_dup)} 条导入记录与现有记录重复。请选择处理方式：")
        overwrite_btn = msg.addButton("全部覆盖", QMessageBox.AcceptRole)
        skip_btn = msg.addButton("全部跳过", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == overwrite_btn:
            out = [entry for entry in out if _dup_key(entry) not in dup_keys]
            out.extend(records)
        else:
            out.extend(mapped_nondup)
    else:
        out.extend(records)

    return out


if __name__ == '__main__':
    app = QApplication()
    print(main([]))
