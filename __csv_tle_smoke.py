# -*- coding: utf-8 -*-
"""离屏冒烟：iter_tle_records 支持 Celestrak OMM CSV（重建 TLE 两行）。

对照基准：celestrak 同一元素集的官方 TLE（2026-09-27 抓取），
重建结果应与官方 TLE **逐场一致**。
"""
import os
import sys

import satellite_pred as sp

CSV_TEXT = (
    'OBJECT_NAME,OBJECT_ID,EPOCH,MEAN_MOTION,ECCENTRICITY,INCLINATION,'
    'RA_OF_ASC_NODE,ARG_OF_PERICENTER,MEAN_ANOMALY,EPHEMERIS_TYPE,'
    'CLASSIFICATION_TYPE,NORAD_CAT_ID,ELEMENT_SET_NO,REV_AT_EPOCH,BSTAR,'
    'MEAN_MOTION_DOT,MEAN_MOTION_DDOT\n'
    'OSCAR 7 (AO-7),1974-089B,2026-09-26T21:32:56.406912,12.53699809,'
    '.00119606,101.9915,284.2068,298.0104,181.2598,0,U,7530,999,37326,'
    '.10061247E-3,-.3E-6,0\n'
    'PHASE 3B (AO-10),1983-058B,2026-09-20T01:00:59.780448,2.05869937,'
    '.598033,25.9788,204.0605,141.6651,281.5604,0,U,14129,999,29744,0,'
    '-.6E-6,0\n'
)

# 官方 TLE（celestrak gp.php?GROUP=amateur&FORMAT=tle，同一批根数）
REAL = {
    '7530': ('1 07530U 74089B   26269.89787508 -.00000030  00000+0  10061-3 0  9994',
             '2 07530 101.9915 284.2068 0011960 298.0104 181.2598 12.53699809373261'),
    '14129': ('1 14129U 83058B   26263.04235857 -.00000060  00000+0  00000+0 0  9999',
              '2 14129  25.9788 204.0605 5980330 141.6651 281.5604  2.05869937297448'),
}

# ---- ① CSV 解析：条数 / 编号 / 名称 ----
recs = list(sp.iter_tle_records(CSV_TEXT))
assert len(recs) == 2, 'CSV 应解析出 2 条，实际 %d：%r' % (len(recs), recs)
by_norad = {r[0]: r for r in recs}
assert set(by_norad) == {'7530', '14129'}, by_norad.keys()
assert by_norad['7530'][1] == 'OSCAR 7 (AO-7)', by_norad['7530'][1]
assert by_norad['14129'][1] == 'PHASE 3B (AO-10)', by_norad['14129'][1]

# ---- ② 重建 TLE 与官方逐场对照 ----
for norad, name, l1, l2 in recs:
    r1, r2 = REAL[norad]
    assert len(l1) == 69 and len(l2) == 69, (len(l1), len(l2), l1, l2)
    # 校验和自洽
    assert sp._tle_checksum(l1[:68]) == l1[68], 'line1 校验和错误：%r' % l1
    assert sp._tle_checksum(l2[:68]) == l2[68], 'line2 校验和错误：%r' % l2
    # 行 1：编号/国际代号/历元/一阶导/二阶导/BSTAR（确定的场必须完全一致）
    assert l1[2:8] == r1[2:8], '编号/类别：%r vs %r' % (l1[2:8], r1[2:8])
    assert l1[9:17] == r1[9:17], '国际代号：%r vs %r' % (l1[9:17], r1[9:17])
    assert l1[18:32] == r1[18:32], '历元：%r vs %r' % (l1[18:32], r1[18:32])
    assert l1[33:43] == r1[33:43], '一阶导：%r vs %r' % (l1[33:43], r1[33:43])
    assert l1[44:52] == r1[44:52], '二阶导：%r vs %r' % (l1[44:52], r1[44:52])
    assert l1[53:61] == r1[53:61], 'BSTAR：%r vs %r' % (l1[53:61], r1[53:61])
    assert l1[62:68] == r1[62:68], '历元类型/星历编组：%r vs %r' % (l1[62:68], r1[62:68])
    # 行 2：全部场
    assert l2[2:7] == r2[2:7], '行2编号：%r vs %r' % (l2[2:7], r2[2:7])
    assert l2[8:16] == r2[8:16], '倾角：%r vs %r' % (l2[8:16], r2[8:16])
    assert l2[17:25] == r2[17:25], '升交点：%r vs %r' % (l2[17:25], r2[17:25])
    assert l2[26:33] == r2[26:33], '偏心率：%r vs %r' % (l2[26:33], r2[26:33])
    assert l2[34:42] == r2[34:42], '近地点幅角：%r vs %r' % (l2[34:42], r2[34:42])
    assert l2[43:51] == r2[43:51], '平近点角：%r vs %r' % (l2[43:51], r2[43:51])
    assert l2[52:63] == r2[52:63], '平均运动：%r vs %r' % (l2[52:63], r2[52:63])
    assert l2[63:68] == r2[63:68], '圈数：%r vs %r' % (l2[63:68], r2[63:68])

# ---- ③ 项目自带 twoline2rv 能解析重建的行 ----
sats = sp.parse_tle_text(CSV_TEXT)
assert len(sats) == 2, 'parse_tle_text 应解析出 2 颗，实际 %d' % len(sats)
names = [n for n, _ in sats]
assert 'OSCAR 7 (AO-7)' in names and 'PHASE 3B (AO-10)' in names, names

# ---- ④ 回归：3LE / 2LE 排版不受影响 ----
r1, r2 = REAL['7530']
recs3 = list(sp.iter_tle_records('OSCAR 7 (AO-7)\n%s\n%s\n' % (r1, r2)))
assert len(recs3) == 1 and recs3[0][0] == '7530', recs3
recs2 = list(sp.iter_tle_records('%s\n%s\n' % (r1, r2)))
assert len(recs2) == 1 and recs2[0][1] == '07530', recs2
# 名称行碰巧含逗号不会被误判成 CSV 表头
recs_c = list(sp.iter_tle_records('AO-7, TEST SAT\n%s\n%s\n' % (r1, r2)))
assert len(recs_c) == 1 and recs_c[0][0] == '7530', recs_c

# ---- ⑤ merge：CSV 与 TLE 混合，按编号去重、靠前优先 ----
merged = sp.merge_tle_texts(CSV_TEXT, 'OSCAR 7 (AO-7)\n%s\n%s\n' % (r1, r2))
m_recs = list(sp.iter_tle_records(merged))
assert len(m_recs) == 2, '合并后应只有 2 颗（7530 去重），实际 %d' % len(m_recs)

# ---- ⑥ BOM 兼容 ----
recs_bom = list(sp.iter_tle_records('\ufeff' + CSV_TEXT))
assert len(recs_bom) == 2, 'BOM 开头的 CSV 应正常解析'

# ---- ⑦ 内置默认源：5 个地址全部合法 ----
assert len(sp.DEFAULT_TLE_SOURCES) == 5, sp.DEFAULT_TLE_SOURCES
assert all(sp.is_valid_tle_source(u) for u in sp.DEFAULT_TLE_SOURCES)

print('OK: CSV(OMM) 重建 TLE 与官方逐场一致；3LE/2LE/合并/BOM 回归全过')
