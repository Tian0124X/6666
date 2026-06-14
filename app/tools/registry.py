"""工具安全沙箱 — 文件路径白名单校验"""

import os
import re
from typing import List

# 文件操作白名单目录
ALLOWED_DIRECTORIES = [
    os.path.abspath("data/documents"),
    os.path.abspath("data/uploads"),
    os.path.abspath("data/reports"),
]

# 禁止出现在文件路径中的危险模式
FORBIDDEN_PATTERNS = [
    r"\.\./",
    r"\.\.\\",
    r"/etc/",
    r"C:\\Windows",
    r"file://",
    r"\;",
    r"\|\|",
    r"&&",
]


def validate_file_path(file_path: str) -> str:
    """
    校验文件路径安全性。
    Returns: 规范化后的绝对路径
    Raises: ValueError 若路径不安全
    """
    # 检查禁止模式
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, file_path):
            raise ValueError(f"文件路径包含不安全模式: {pattern}")

    abs_path = os.path.abspath(file_path)

    # 检查白名单
    if not any(abs_path.startswith(d) for d in ALLOWED_DIRECTORIES):
        raise ValueError(
            f"文件路径不在允许的目录中。允许: {ALLOWED_DIRECTORIES}"
        )

    return abs_path


def ensure_directory(path: str):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)
