"""
哈希计算模块 - C 负责实现

接口约定：
    compute_sha256(file_path) -> str  返回十六进制哈希字符串
    compute_md5(file_path) -> str     返回十六进制哈希字符串
"""

import hashlib


def compute_sha256(file_path: str) -> str:
    """计算文件的 SHA-256 哈希值。"""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


def compute_md5(file_path: str) -> str:
    """计算文件的 MD5 哈希值（辅助，SHA-256 为主）。"""
    md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)
    return md5.hexdigest()
