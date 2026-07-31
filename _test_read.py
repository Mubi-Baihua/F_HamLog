import os, sys

# 模拟“从非项目目录启动”：把工作目录切到 C:\
os.chdir("C:\\")
sys.path.insert(0, r"D:\F-Dev\BIG\F_HamLog")
import satellite_pred as sp

print("CWD now:", os.getcwd())
print("SAT_RADIO_DICT_PATH =", sp.SAT_RADIO_DICT_PATH)
print("exists:", os.path.exists(sp.SAT_RADIO_DICT_PATH))
print("TQSL_DICT_PATH =", sp.TQSL_DICT_PATH)
print("tqsl exists:", os.path.exists(sp.TQSL_DICT_PATH))

d = sp.load_sat_radio_dict()
print("loaded entries:", len(d))
print("ISS:", d.get("ISS (ZARYA)"))
print("SO-50:", d.get("SO-50"))
print("AO-91:", d.get("AO-91"))
print("OK")
