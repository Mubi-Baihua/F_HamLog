from PySide6.QtWidgets import QFileDialog
from datetime import datetime, timezone
from PySide6.QtWidgets import QApplication


def _to_utc_datetime(date_str, time_str):
    if not date_str or not time_str:
        return None
    # 支持 YYYY-MM-DD 或 YYYYMMDD
    ds = date_str.strip()
    if '-' in ds:
        parts = ds.split('-')
        if len(parts) != 3:
            return None
        y, m, d = parts
    elif len(ds) >= 8 and ds.isdigit():
        y, m, d = ds[0:4], ds[4:6], ds[6:8]
    else:
        return None

    ts = time_str.strip()
    ts = ts.replace(':', '')
    if len(ts) < 4 or not ts[:4].isdigit():
        return None
    hh, mm = int(ts[0:2]), int(ts[2:4])

    try:
        naive = datetime(int(y), int(m), int(d), hh, mm)
    except Exception:
        return None

    local_tz = datetime.now().astimezone().tzinfo
    local_dt = naive.replace(tzinfo=local_tz)
    return local_dt.astimezone(timezone.utc)


def main(file):
    file_path, _ = QFileDialog.getSaveFileName(None, "导出ADIF文件", "", "ADIF 文件 (*.adi);;All Files (*)")
    if not file_path:
        return False

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            # 标准化 ADIF 头部，使用大写 TAG
            f.write("ADIF export from F HamLog\n")
            f.write("<ADIF_VER:5>3.1.0\n")
            f.write("<PROGRAMID:8>F HAMLOG\n")
            f.write("<EOH>\n\n")

            for qso in file:
                # 输出字段均使用大写 TAG 和 <TAG:len>value 格式
                if qso.get('o_call'):
                    val = str(qso['o_call']).strip()
                    f.write(f"<CALL:{len(val)}>{val}\n")

                # 日期/时间 -> 转为 UTC 写入 QSO_DATE / TIME_ON
                utc = _to_utc_datetime(qso.get('date', ''), qso.get('time', ''))
                if utc is not None:
                    f.write(f"<QSO_DATE:8>{utc.strftime('%Y%m%d')}\n")
                    f.write(f"<TIME_ON:4>{utc.strftime('%H%M')}\n")

                if qso.get('freq'):
                    val = str(qso['freq']).strip()
                    f.write(f"<FREQ:{len(val)}>{val}\n")

                if qso.get('mode'):
                    val = str(qso['mode']).strip()
                    f.write(f"<MODE:{len(val)}>{val}\n")

                if qso.get('m_rst'):
                    val = str(qso['m_rst']).strip()
                    f.write(f"<RST_SENT:{len(val)}>{val}\n")

                if qso.get('o_rst'):
                    val = str(qso['o_rst']).strip()
                    f.write(f"<RST_RCVD:{len(val)}>{val}\n")

                if qso.get('m_call'):
                    val = str(qso['m_call']).strip()
                    f.write(f"<MY_CALL:{len(val)}>{val}\n")

                if qso.get('o_qth'):
                    val = str(qso['o_qth']).strip()
                    f.write(f"<QTH:{len(val)}>{val}\n")

                if qso.get('m_qth'):
                    val = str(qso['m_qth']).strip()
                    f.write(f"<MY_QTH:{len(val)}>{val}\n")

                if qso.get('notes'):
                    val = str(qso['notes']).strip()
                    f.write(f"<COMMENT:{len(val)}>{val}\n")

                f.write("<EOR>\n\n")

        return True
    except Exception as e:
        print(f"导出 ADIF 时出错: {e}")
        return False


if __name__ == '__main__':
    test_data = [
        {
            'o_call': 'BI8SQL',
            'date': '2023-12-01',
            'time': '14:30',
            'freq': '14.250',
            'mode': 'USB',
            'm_rst': '59',
            'o_rst': '59',
            'm_call': 'BG8XXX',
            'o_qth': 'Shanghai',
            'm_qth': 'Beijing',
            'notes': 'Nice QSO'
        }
    ]
    app = QApplication([])
    print(main(test_data))