"""导出 ADIF（供 TQSL / LoTW 签名使用）。

F_HamLog 内部记录字段名与 ADIF 标签不同，这里做映射转换：
内部字段：date, time, m_call, o_call, freq, freq_rx, mode, prop_mode,
          sat_name, m_rst, o_rst, m_qth, o_qth, m_dig, o_dig,
          m_ant, o_ant, m_pow, o_pow, notes

约定：
- 内部 date/time 为本地时间，导出为 ADIF 时转换为 UTC（QSO_DATE/TIME_ON），
  符合 LoTW/TQSL 的惯例。
- 使用标准 ADIF 标签：STATION_CALLSIGN、CALL、FREQ、FREQ_RX、BAND、BAND_RX、
  MODE、PROP_MODE、SAT_NAME、RST_SENT、RST_RCVD 等。
- BAND 命名用小写（2m/70cm...），与 ADIF 规范一致。
"""
import os
import re
from datetime import datetime, timezone
from PySide6.QtWidgets import QFileDialog, QMessageBox

# 频段范围（MHz）-> ADIF BAND 名称（小写，符合规范）
_BAND_RANGES = [
    (1.8, 2.0, '160m'), (3.5, 4.0, '80m'), (7.0, 7.3, '40m'),
    (10.1, 10.15, '30m'), (14.0, 14.35, '20m'), (18.068, 18.168, '17m'),
    (21.0, 21.45, '15m'), (24.89, 24.99, '12m'), (28.0, 29.7, '10m'),
    (50.0, 54.0, '6m'), (70.0, 71.0, '4m'), (144.0, 148.0, '2m'),
    (222.0, 225.0, '1.25m'), (420.0, 450.0, '70cm'), (902.0, 928.0, '33cm'),
    (1240.0, 1300.0, '23cm'), (2300.0, 2450.0, '13cm'), (3400.0, 3500.0, '9cm'),
    (5650.0, 5925.0, '5cm'), (10000.0, 10500.0, '3cm'), (24000.0, 24500.0, '1.2cm'),
    (47000.0, 47200.0, '6mm'), (75500.0, 81000.0, '4mm'),
    (119980.0, 120000.0, '2.5mm'), (142000.0, 149000.0, '2mm'),
    (241000.0, 250000.0, '1mm'),
]


def freq_to_band(mhz):
    """把频率(MHz 字符串/数字)转换为 ADIF BAND 名称，无法识别返回空串。"""
    try:
        f = float(str(mhz).strip())
    except (TypeError, ValueError):
        return ''
    for lo, hi, name in _BAND_RANGES:
        if lo <= f <= hi:
            return name
    return ''


def _looks_like_grid(s):
    if not s:
        return False
    s = s.strip().upper()
    # Maidenhead 形如 AA00 / AA00AA
    return bool(re.match(r'^[A-R]{2}\d{2}([A-X]{0,2})?$', s))


def _local_to_utc(date_str, time_str):
    """本地 date(Y-M-D)/time(H:M) -> (YYYYMMDD, HHMM) UTC；失败返回 (None, None)。"""
    ds = (date_str or '').strip()
    if '-' in ds and ds.count('-') == 2:
        y, m, d = ds.split('-')
    elif len(ds) >= 8 and ds.isdigit():
        y, m, d = ds[0:4], ds[4:6], ds[6:8]
    else:
        return None, None
    ts = (time_str or '').strip().replace(':', '')
    if len(ts) < 4 or not ts[:4].isdigit():
        return None, None
    hh, mm = int(ts[0:2]), int(ts[2:4])
    try:
        naive = datetime(int(y), int(m), int(d), hh, mm)
    except Exception:
        return None, None
    local_tz = datetime.now().astimezone().tzinfo
    utc = naive.replace(tzinfo=local_tz).astimezone(timezone.utc)
    return utc.strftime('%Y%m%d'), utc.strftime('%H%M')


def _field(tag, value):
    """生成 <TAG:len>value 片段；value 为空返回空串。"""
    if value is None:
        return ''
    value = str(value).strip()
    if value == '':
        return ''
    return f"<{tag}:{len(value)}>{value}"


def record_to_adif(rec):
    """把单条 F_HamLog 记录转换为一行 ADIF（含 <EOR>）。无对方呼号则返回空串。"""
    call = (rec.get('o_call') or '').strip()
    if not call:
        return ''  # TQSL 必需 CALL
    qso_date, time_on = _local_to_utc(rec.get('date', ''), rec.get('time', ''))
    if not qso_date:
        qso_date = (rec.get('date') or '').strip().replace('-', '')
    if not time_on:
        time_on = (rec.get('time') or '').strip().replace(':', '')
    parts = [
        _field('CALL', call),
        _field('QSO_DATE', qso_date),
        _field('TIME_ON', time_on),
        _field('STATION_CALLSIGN', rec.get('m_call')),
        _field('MODE', rec.get('mode')),
        _field('PROP_MODE', rec.get('prop_mode')),
        _field('SAT_NAME', rec.get('sat_name')),
    ]
    freq = (rec.get('freq') or '').strip()
    parts.append(_field('FREQ', freq))
    parts.append(_field('BAND', freq_to_band(freq)))
    freq_rx = (rec.get('freq_rx') or '').strip()
    if freq_rx:
        parts.append(_field('FREQ_RX', freq_rx))
        parts.append(_field('BAND_RX', freq_to_band(freq_rx)))
    parts.append(_field('RST_SENT', rec.get('m_rst')))
    parts.append(_field('RST_RCVD', rec.get('o_rst')))
    m_qth = (rec.get('m_qth') or '').strip()
    parts.append(_field('MY_GRIDSQUARE', m_qth if _looks_like_grid(m_qth) else ''))
    o_qth = (rec.get('o_qth') or '').strip()
    parts.append(_field('GRIDSQUARE', o_qth if _looks_like_grid(o_qth) else ''))
    parts.append(_field('TX_PWR', rec.get('m_pow')))
    parts.append(_field('COMMENT', rec.get('notes')))
    parts = [p for p in parts if p]
    if not parts:
        return ''
    return ' '.join(parts) + ' <EOR>'


def records_to_adif(records):
    """把记录列表转换为完整 ADIF 文本（含文件头）。"""
    lines = ['<ADIF_VER:5>3.1.0', '<PROGRAMID:8>F HAMLOG', '<EOH>']
    for rec in records:
        line = record_to_adif(rec)
        if line:
            lines.append(line)
    return '\n'.join(lines) + '\n'


def export_adif_dialog(records, parent=None, default_name='FHamLog_export'):
    """弹出保存对话框，将记录导出为 ADIF 文件（供 TQSL 签名）。"""
    if not records:
        QMessageBox.warning(parent, '提示', '没有可导出的记录。')
        return
    path, _ = QFileDialog.getSaveFileName(
        parent, '导出 ADIF (TQSL/LoTW)', default_name + '.adi',
        'ADIF 文件 (*.adi);;All Files (*)')
    if not path:
        return
    if not path.lower().endswith('.adi'):
        path += '.adi'
    text = records_to_adif(records)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)
        QMessageBox.information(
            parent, '完成',
            f'已导出 {len(records)} 条记录到：\n{path}\n\n'
            '可用 TQSL 打开该 ADIF 文件进行签名，再上传到 LoTW。')
    except Exception as e:
        QMessageBox.warning(parent, '导出失败', f'写入文件失败：\n{e}')
