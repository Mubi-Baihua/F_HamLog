import argparse
import json
import random
from datetime import date, timedelta

CALL_PREFIXES = [
    "BG", "BI", "BD", "BH", "BU", "BA", "BM", "BN", "BP"
]
CALL_SUFFIXES = [
    "SQL", "SVJ", "K5", "UP", "AAB", "XYZ", "ABC", "BBS", "CQC"
]
MODES = ["FM", "USB", "LSB", "CW", "AM"]
PROP_MODES = ["SAT", "IONO", "TROPO", "E", "LINEAR", "SSB"]
SAT_NAMES = ["SO-50", "ARISS", "AO-91", "FO-29", "XW-2A", "CAS-4A", "ISS"]
QTHS = ["昆明", "成都", "上海", "广州", "北京", "深圳", "杭州", "重庆", "西安"]
DIGS = ["UV-K5", "IC-705", "IC-9700", "FT-3D", "FT-817", "TM-8", "DM-1801"]
ANTS = ["原装", "高增益", "双频", "定向", "宽频"]
POWS = ["H", "M", "L"]
NOTES = ["测试记录", "常规通联", "卫星通信", "DX通信", "contest", "CQ CQ"]


def random_callsign():
    prefix = random.choice(CALL_PREFIXES)
    number = str(random.randint(1, 9))
    suffix = random.choice(CALL_SUFFIXES)
    return prefix + number + suffix


def random_date(days_back=365):
    today = date.today()
    delta = timedelta(days=random.randint(0, days_back))
    return (today - delta).isoformat()


def random_time():
    hour = random.randint(0, 23)
    minute = random.randint(0, 59)
    return f"{hour:02d}:{minute:02d}"


def random_frequency():
    band = random.choice([144.0, 430.0, 146.0, 438.7, 14.2, 7.1])
    step = random.choice([0.1, 0.05, 0.025, 0.001])
    return f"{band + random.uniform(-0.5, 0.5):.3f}" if step < 0.01 else f"{band + random.uniform(-0.2, 0.2):.1f}"


def make_record(index):
    mode = random.choice(MODES)
    prop_mode = random.choice(PROP_MODES)
    sat_name = random.choice(SAT_NAMES) if prop_mode == "SAT" else ""
    return {
        "date": random_date(365),
        "time": random_time(),
        "m_call": "BI8SQL",
        "o_call": random_callsign(),
        "freq": random_frequency(),
        "freq_rx": random_frequency(),
        "mode": mode,
        "prop_mode": prop_mode,
        "sat_name": sat_name,
        "m_rst": "59",
        "o_rst": "59",
        "m_qth": random.choice(QTHS),
        "o_qth": random.choice(QTHS),
        "m_dig": random.choice(DIGS),
        "o_dig": random.choice(DIGS),
        "m_ant": random.choice(ANTS),
        "o_ant": random.choice(ANTS),
        "m_pow": random.choice(POWS),
        "o_pow": random.choice(POWS),
        "notes": f"生成日志 {index + 1}"
    }


def generate_records(count):
    return [make_record(i) for i in range(count)]


def main():
    parser = argparse.ArgumentParser(description="生成 n 条 FHL 日志记录")
    parser.add_argument("-n", "--count", type=int, default=10, help="生成记录条数，默认 10")
    parser.add_argument("-o", "--output", default="output.fhl", help="输出文件路径，默认 output.fhl")
    args = parser.parse_args()

    count = max(0, args.count)
    records = generate_records(count)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"已生成 {count} 条 FHL 日志记录到 {args.output}")


if __name__ == "__main__":
    main()

#python test.py -n 100 -o sample.fhl