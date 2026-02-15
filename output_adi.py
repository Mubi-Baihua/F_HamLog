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

                # 写入发送频率
                if qso.get('freq'):
                    val = str(qso['freq']).strip()
                    f.write(f"<FREQ:{len(val)}>{val}\n")

                # 若存在接收频率，则写入接收频率及推断接收波段
                def _infer_band_from_mhz(freq_mhz):
                    try:
                        fmhz = float(str(freq_mhz).strip())
                    except Exception:
                        return ''
                    # 常见波段范围（简化）：2M, 70CM, 15M, 20M, 40M, 80M, 160M, 10M
                    if 144.0 <= fmhz < 148.0:
                        return '2M'
                    if 430.0 <= fmhz < 450.0:
                        return '70CM'
                    if 21.0 <= fmhz < 21.45:
                        return '15M'
                    if 14.0 <= fmhz < 14.35:
                        return '20M'
                    if 7.0 <= fmhz < 7.3:
                        return '40M'
                    if 3.5 <= fmhz < 4.0:
                        return '80M'
                    if 1.8 <= fmhz < 2.0:
                        return '160M'
                    if 28.0 <= fmhz < 29.7:
                        return '10M'
                    return ''

                if qso.get('freq_rx'):
                    val = str(qso['freq_rx']).strip()
                    band = _infer_band_from_mhz(val)
                    if band:
                        f.write(f"<BAND_RX:{len(band)}>{band}\n")
                    f.write(f"<FREQ_RX:{len(val)}>{val}\n")

                if qso.get('mode'):
                    val = str(qso['mode']).strip()
                    f.write(f"<MODE:{len(val)}>{val}\n")

                # 写入卫星/传播方式信息（若有）
                if qso.get('prop_mode'):
                    val = str(qso['prop_mode']).strip()
                    f.write(f"<PROP_MODE:{len(val)}>{val}\n")

                if qso.get('sat_name'):
                    val = str(qso['sat_name']).strip()
                    f.write(f"<SAT_NAME:{len(val)}>{val}\n")
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