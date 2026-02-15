from PySide6.QtWidgets import QFileDialog, QMessageBox
import re
import os
import json
from datetime import datetime, timezone


def _read_my_call_from_config():
    """从m_xml.txt文件中读取我的呼号"""
    try:
        # 获取项目根目录路径
        project_root = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(project_root, 'file', 'm_xml.txt')
        
        # 检查文件是否存在
        if not os.path.exists(config_path):
            return ''
            
        # 读取文件内容
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            
        # 解析字典格式的内容
        if content.startswith('{') and content.endswith('}'):
            # 移除首尾的大括号并解析
            dict_content = content[1:-1]
            # 简单解析键值对
            pairs = dict_content.split(',')
            for pair in pairs:
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    key = key.strip().strip("'\"")
                    value = value.strip().strip("'\"")
                    if key == 'm_call':
                        return value
    except Exception:
        # 发生任何错误都返回空字符串
        pass
    
    return ''

def _parse_adi_text(text):
    # 简单解析 ADI/ADIF：匹配格式 <TAG:len>value
    entries = []
    # split by <eor> (end of record)
    parts = re.split(r'<eor>|<EOR>', text)
    tag_re = re.compile(r'<([^:>\s]+)(?::(\d+))?>([^<]*)', re.IGNORECASE)
    for part in parts:
        if not part.strip():
            continue
        rec = {}
        for m in tag_re.finditer(part):
            tag = m.group(1).upper()
            val = m.group(3).strip()
            rec[tag] = val
        if rec:
            entries.append(rec)
    return entries


def _map_record(rec):
    # 将 ADIF 字段映射到 project.py 使用的字段
    def fmt_date(d):
        if not d:
            return ''
        d = d.strip()
        if len(d) >= 8 and d.isdigit():
            return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
        return d

    def fmt_time(t):
        if not t:
            return ''
        t = t.strip()
        t = re.sub(r'[^0-9]', '', t)
        if len(t) >= 4:
            return f"{t[0:2]}:{t[2:4]}"
        return t

    def _adi_utc_to_local(date_str, time_str):
        # ADIF 常用格式: date YYYYMMDD, time HHMM 或 HHMMSS (通常为 UTC)
        if not date_str or not time_str:
            return None, None
        ds = date_str.strip()
        if '-' in ds:
            parts = ds.split('-')
            if len(parts) != 3:
                return None, None
            y, m, d = parts
        elif len(ds) >= 8 and ds.isdigit():
            y, m, d = ds[0:4], ds[4:6], ds[6:8]
        else:
            return None, None

        ts = time_str.strip()
        ts = re.sub(r'[^0-9]', '', ts)
        if len(ts) < 4:
            return None, None
        hh, mm = int(ts[0:2]), int(ts[2:4])

        try:
            utc_dt = datetime(int(y), int(m), int(d), hh, mm, tzinfo=timezone.utc)
        except Exception:
            return None, None

        local_tz = datetime.now().astimezone().tzinfo
        local_dt = utc_dt.astimezone(local_tz)
        return local_dt.strftime('%Y-%m-%d'), local_dt.strftime('%H:%M')

    # 尝试将 ADI 中的 UTC 时间转换为本地时间；失败则回退为简单格式化
    raw_date = rec.get('QSO_DATE', '') or rec.get('DATE', '')
    raw_time = rec.get('TIME_ON', '') or rec.get('TIME', '') or rec.get('TIME_OFF', '')
    local_date, local_time = _adi_utc_to_local(raw_date, raw_time)

    # 获取默认的我的呼号
    default_my_call = _read_my_call_from_config()
    
    # 获取记录中的呼号，如果没有则使用默认值
    my_call = rec.get('MY_CALL', rec.get('STATION_CALLSIGN', ''))
    if not my_call and default_my_call:
        my_call = default_my_call

    mapped = {
        'date': local_date if local_date else fmt_date(raw_date),
        'time': local_time if local_time else fmt_time(raw_time),
        'm_call': my_call,
        'o_call': rec.get('CALL', ''),
        'freq': rec.get('FREQ', rec.get('FREQ_MHz', '')),
        'freq_rx': rec.get('FREQ_RX', ''),
        'mode': rec.get('MODE', ''),
        'prop_mode': rec.get('PROP_MODE', ''),
        'sat_name': rec.get('SAT_NAME', ''),
        'm_rst': rec.get('RST_SENT', rec.get('RSTS', '')),
        'o_rst': rec.get('RST_RCVD', rec.get('RSTR', '')),
        'm_qth': rec.get('MY_GRIDSQUARE', rec.get('MY_QTH', '')),
        'o_qth': rec.get('GRIDSQUARE', rec.get('QTH', '')),
        'm_dig': rec.get('MY_EQSL', ''),
        'o_dig': rec.get('EQUIPMENT', rec.get('EQP', '')),
        'm_ant': rec.get('ANTENNA', ''),
        'o_ant': '',
        'm_pow': rec.get('TX_PWR', rec.get('POWER', '')),
        'o_pow': '',
        'notes': rec.get('COMMENT', rec.get('NOTES', '')),
    }
    # Ensure keys exist
    for k in ['date','time','m_call','o_call','freq','freq_rx','mode','prop_mode','sat_name','m_rst','o_rst','m_qth','o_qth','m_dig','o_dig','m_ant','o_ant','m_pow','o_pow','notes']:
        if k not in mapped:
            mapped[k] = ''
    return mapped


def main(file_list):
    # 弹出文件选择对话框以选择 .adi 文件
    path, _ = QFileDialog.getOpenFileName(None, '选择 ADI/ADIF 文件', '', 'ADI 文件 (*.adi);;All Files (*)')
    if not path:
        return file_list
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            txt = f.read()
    except Exception:
        try:
            with open(path, 'r', encoding='gbk', errors='ignore') as f:
                txt = f.read()
        except Exception:
            return file_list

    records = _parse_adi_text(txt)
    mapped = [_map_record(r) for r in records]
    # 将导入记录追加到现有 file_list，先做重复检测（按 呼号+日期+时间），提示一次选择覆盖或跳过
    out = list(file_list) if file_list is not None else []

    # 生成现有记录键集合
    existing_keys = set()
    for e in out:
        key = ((e.get('o_call') or '').strip().lower(), e.get('date', ''), e.get('time', ''))
        if key[0] and key[1] and key[2]:
            existing_keys.add(key)

    mapped_dup = []
    mapped_nondup = []
    dup_keys = set()
    for r in mapped:
        key = ((r.get('o_call') or '').strip().lower(), r.get('date', ''), r.get('time', ''))
        if key[0] and key[1] and key[2] and key in existing_keys:
            mapped_dup.append(r)
            dup_keys.add(key)
        else:
            mapped_nondup.append(r)

    if mapped_dup:
        msg = QMessageBox()
        msg.setWindowTitle("检测到重复记录")
        msg.setText(f"检测到 {len(mapped_dup)} 条导入记录与现有记录重复。请选择处理方式：")
        overwrite_btn = msg.addButton("全部覆盖", QMessageBox.AcceptRole)
        skip_btn = msg.addButton("全部跳过", QMessageBox.RejectRole)
        msg.exec()
        if msg.clickedButton() == overwrite_btn:
            # 删除现有重复项后添加所有导入记录（覆盖行为）
            out = [e for e in out if ((e.get('o_call') or '').strip().lower(), e.get('date', ''), e.get('time', '')) not in dup_keys]
            out.extend(mapped)
        else:
            # 跳过重复项，仅添加非重复记录
            out.extend(mapped_nondup)
    else:
        out.extend(mapped)

    return out
