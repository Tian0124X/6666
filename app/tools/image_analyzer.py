"""
图片分析工具 — 多模态支持（OCR文字提取 + 图片信息分析）

上传图片/截图 → 提取文字 → LLM分析 → 结构化回答
"""

import os
import base64
import logging
from typing import Optional
from PIL import Image, ExifTags
import io

logger = logging.getLogger(__name__)

UPLOAD_DIR = "data/uploads"


def ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_uploaded_image(data: bytes, filename: str) -> str:
    """保存上传图片，返回文件路径"""
    ensure_upload_dir()
    safe_name = os.path.basename(filename).replace(" ", "_")
    path = os.path.join(UPLOAD_DIR, safe_name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def get_image_info(path: str) -> dict:
    """提取图片基本信息 (尺寸/格式/EXIF)"""
    img = Image.open(path)
    info = {
        "format": img.format,
        "size": f"{img.width}x{img.height}",
        "mode": img.mode,
        "file_size_kb": round(os.path.getsize(path) / 1024, 1),
    }
    # EXIF
    try:
        exif_data = img._getexif()
        if exif_data:
            exif = {}
            for tag_id, value in exif_data.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                if isinstance(value, bytes):
                    value = value.decode(errors="ignore")[:200]
                exif[tag_name] = str(value)[:200]
            info["exif"] = exif
    except Exception:
        pass
    img.close()
    return info


def ocr_extract_text(path: str) -> str:
    """OCR 文字提取 (优先 pytesseract, 降级为占位描述)"""
    try:
        import pytesseract
        img = Image.open(path)
        # 预处理: 灰度化 + 放大
        if img.mode != "L":
            img = img.convert("L")
        text = pytesseract.image_to_string(img, lang="chi_sim+eng")
        img.close()
        return text.strip() if text.strip() else ""
    except ImportError:
        logger.info("pytesseract 未安装，跳过OCR")
        return ""
    except Exception as e:
        logger.warning(f"OCR失败: {e}")
        return ""


def analyze_image(path: str, question: str = "") -> str:
    """
    图片分析主入口。

    流程: 提取图片信息 → OCR文字 → 组合为LLM可理解的描述
    """
    info = get_image_info(path)
    ocr_text = ocr_extract_text(path)

    parts = [
        f"## 📷 图片信息",
        f"- 格式: {info.get('format', '未知')}",
        f"- 尺寸: {info.get('size', '未知')}",
        f"- 大小: {info.get('file_size_kb', 0)} KB",
    ]

    if ocr_text:
        parts.append(f"\n## 📝 OCR 提取文字\n```\n{ocr_text[:3000]}\n```")
    else:
        parts.append("\n> ⚠️ 未检测到文字内容。如需OCR识别请安装: pip install pytesseract")

    if question:
        parts.append(f"\n## ❓ 用户问题\n{question}")
        parts.append("\n请基于以上图片信息回答问题。如果图片包含图表/数据，请分析趋势和关键数字。")

    return "\n".join(parts)


def image_to_base64(path: str) -> str:
    """图片转 base64 (用于LLM视觉模型)"""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def is_image_file(filename: str) -> bool:
    """检查是否为支持的图片格式"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}
