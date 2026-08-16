"""通联录音工具。

把音频以二进制形式（base64 编码的字符串）保存到日志的 ``record`` 字段，
并提供播放能力。

说明：
- ``.fhl`` 本质是 JSON，无法直接存放裸二进制，因此音频字节统一做 base64 编码后
  存入 ``record`` 字段（空字符串表示无录音）。加密模式下，base64 字符串会随整个
  JSON 一起被 AES-GCM 加密，无需特殊处理。
- 播放不依赖 ``QtMultimedia``（PySide6-Essentials 不含该模块），而是把音频字节
  写入临时文件后用系统默认播放器打开，跨平台可用。
"""

import base64
import os
import subprocess
import sys
import tempfile

# 常见音频格式的文件头特征 -> 临时文件扩展名
_AUDIO_SIGNATURES = (
    (b'RIFF', 0, b'WAVE', 8, '.wav'),   # WAV: "RIFF"...."WAVE"
    (b'ID3', 0, None, 0, '.mp3'),       # MP3: ID3 标签
    (b'OggS', 0, None, 0, '.ogg'),      # OGG
    (b'fLaC', 0, None, 0, '.flac'),     # FLAC
    (b'ftyp', 4, None, 0, '.m4a'),      # MP4 / M4A: 偏移 4 处的 "ftyp"
)


def detect_audio_ext(data: bytes) -> str:
    """根据文件头魔数猜测音频扩展名，无法识别时返回 '.bin'。"""
    if not data:
        return '.bin'
    for head, off, sub, sub_off, ext in _AUDIO_SIGNATURES:
        if data[off:off + len(head)] == head:
            if sub is None or data[sub_off:sub_off + len(sub)] == sub:
                return ext
    # MP3 帧同步：0xFF 后跟 0xE0~0xFB 的最高 3 位为 1
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return '.mp3'
    return '.bin'


def encode_record(data: bytes) -> str:
    """音频字节 -> base64 字符串（存入 record 字段）。"""
    return base64.b64encode(data).decode('ascii')


def decode_record(b64: str) -> bytes:
    """record 字段(base64) -> 音频字节。空值返回 b''。"""
    if not b64:
        return b''
    return base64.b64decode(b64)


def _temp_dir() -> str:
    """返回（并懒创建）本次会话专用的临时目录。"""
    if not hasattr(_temp_dir, '_dir'):
        _temp_dir._dir = tempfile.mkdtemp(prefix='fhamlog_rec_')
    return _temp_dir._dir


def play_audio_bytes(data: bytes):
    """把音频字节写到临时文件并用系统默认播放器打开。

    返回 (ok: bool, msg: str)。msg 在成功时为临时文件路径，失败时为错误说明。
    """
    if not data:
        return False, '没有可播放的录音。'
    ext = detect_audio_ext(data)
    try:
        fd, path = tempfile.mkstemp(
            suffix=ext, prefix='fhamlog_play_', dir=_temp_dir())
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
    except Exception as e:  # 写入失败
        return False, f'写入临时文件失败：{e}'

    try:
        if sys.platform.startswith('win'):
            os.startfile(path)  # Windows
        elif sys.platform == 'darwin':
            subprocess.run(['open', path], check=False)
        else:
            subprocess.run(['xdg-open', path], check=False)
        return True, path
    except Exception as e:  # 打开播放器失败
        return False, f'无法打开系统播放器：{e}'
