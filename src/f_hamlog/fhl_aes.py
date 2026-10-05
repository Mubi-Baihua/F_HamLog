import os
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.exceptions import InvalidTag

# 自定义固定盐，写死在代码，不用额外存储
FIX_SALT = b"abc987654321XYZ_secret_salt_001"
NONCE_LENGTH = 12  # GCM标准nonce长度

def get_aes256_key(password: str) -> bytes:
    """任意字符串密码 + 固定盐 生成32字节AES256密钥"""
    combine_data = password.encode("utf-8") + FIX_SALT
    # sha256输出正好32字节，完美匹配AES-256密钥长度
    return hashlib.sha256(combine_data).digest()

def aes_gcm_encrypt(plain_text: str, password: str) -> bytes:
    key = get_aes256_key(password)
    nonce = os.urandom(NONCE_LENGTH)
    cipher = Cipher(algorithms.AES(key), modes.GCM(nonce))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plain_text.encode("utf-8")) + encryptor.finalize()
    # 打包格式：nonce(12) + tag(16) + 密文
    return nonce + encryptor.tag + ciphertext

def aes_gcm_decrypt(encrypted_package: bytes, password: str) -> str:
    key = get_aes256_key(password)
    # 拆分打包数据
    nonce = encrypted_package[:12]
    tag = encrypted_package[12:28]
    ciphertext = encrypted_package[28:]
    try:
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag))
        decryptor = cipher.decryptor()
        raw_bytes = decryptor.update(ciphertext) + decryptor.finalize()
        return raw_bytes.decode("utf-8")
    except InvalidTag:
        raise Exception("密码错误、密文被篡改、文件损坏")

# 测试代码
if __name__ == "__main__":
    my_pwd = "我只需要记住这一串密码就行123456！中文也支持"
    origin_text = "测试AES-256-GCM加密内容，任意长度字符串，中文数字符号均可"

    enc_data = aes_gcm_encrypt(origin_text, my_pwd)
    print(f"加密数据包总字节长度：{len(enc_data)}")

    dec_text = aes_gcm_decrypt(enc_data, my_pwd)
    print("解密结果：", dec_text)