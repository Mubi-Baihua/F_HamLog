import sys, os
sys.path.insert(0, r"D:\F-Dev\BIG\F_HamLog")
import satellite_pred as sp

# 1) 含 BOM 的 UTF-8 文件
with open(r"D:\F-Dev\BIG\F_HamLog\file\_bom.txt", "wb") as f:
    f.write(b"\xef\xbb\xbf")  # UTF-8 BOM
    f.write("TESTBOM=437.100,145.900,FM\n".encode("utf-8"))
print("BOM file ->", sp.load_sat_radio_dict(r"D:\F-Dev\BIG\F_HamLog\file\_bom.txt").get("TESTBOM"))

# 2) GBK 编码文件
with open(r"D:\F-Dev\BIG\F_HamLog\file\_gbk.txt", "wb") as f:
    f.write("测试星=437.100,145.900,FM\n".encode("gbk"))
print("GBK file ->", sp.load_sat_radio_dict(r"D:\F-Dev\BIG\F_HamLog\file\_gbk.txt").get("测试星"))

os.remove(r"D:\F-Dev\BIG\F_HamLog\file\_bom.txt")
os.remove(r"D:\F-Dev\BIG\F_HamLog\file\_gbk.txt")
print("OK")
