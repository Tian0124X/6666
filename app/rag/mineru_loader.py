"""
MinerU PDF 解析引擎封装模块 (v2.x)

对 opendatalab/MinerU 的可选集成.
通过独立 venv + subprocess 调用, 避免 MinerU 的依赖和主项目冲突.

要求: 项目根目录下有 .venv-mineru/ 独立虚拟环境, 内安装 mineru[pipeline].
"""

import os
import re
import json
import logging
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ============================================================
# 懒检测 .venv-mineru
# ============================================================

_MINERU_VENV_PYTHON: Optional[str] = None
_mineru_available: bool = False
_mineru_import_error: str = ""

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# 按优先级探测 mineru 可用的 Python
_candidates = [
    # 独立 venv (推荐)
    os.path.join(_project_root, ".venv-mineru", "Scripts", "python.exe"),
    # 当前 venv
    os.path.join(_project_root, ".venv", "Scripts", "python.exe"),
    # 系统 Python
    "python",
]

for _py in _candidates:
    if _py == "python":
        _found = shutil.which("python")
        if not _found:
            continue
        _py = _found

    if os.path.isfile(_py) or (_py != "python" and shutil.which(_py)):
        try:
            result = subprocess.run(
                [_py, "-c",
                 "import os; os.environ['LOGURU_LEVEL']='ERROR';"
                 "from mineru.cli.common import do_parse;"
                 "print('__MINERU_OK__')"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=15,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "LOGURU_LEVEL": "ERROR"},
            )
            if "__MINERU_OK__" in result.stdout:
                _MINERU_VENV_PYTHON = _py
                _mineru_available = True
                logger.info(f"MinerU v2 可用: {_py}")
                break
            else:
                _mineru_import_error = (result.stderr or result.stdout).strip()[-500:]
        except Exception as e:
            _mineru_import_error = str(e)
            continue

if not _mineru_available:
    _mineru_import_error = _mineru_import_error or "未找到可用的 mineru 安装"
    logger.info(f"MinerU 未安装, PDF 解析将使用 PyPDF2 回退: {_mineru_import_error}")


# ============================================================
# TextPostProcessor: MinerU 原始 Markdown 后处理
# ============================================================

class TextPostProcessor:
    """对 MinerU 输出的 Markdown 做轻量后处理, 提升后续分块和检索质量."""

    @staticmethod
    def clean_control_chars(text: str) -> str:
        return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    @classmethod
    def post_process(cls, text: str) -> str:
        text = cls.clean_control_chars(text)
        text = cls.normalize_whitespace(text)
        return text


# ============================================================
# MinerUPDFExtractor: 通过 subprocess 调用独立 venv 中的 MinerU
# ============================================================

class MinerUPDFExtractor:
    """
    MinerU PDF 解析引擎封装 (v2.x).

    调用方式:
        extractor = MinerUPDFExtractor()
        if extractor.is_available():
            pages = extractor.extract("path/to/doc.pdf")

    输出格式:
        [
            {
                "page_number": 1,
                "markdown": "## 标题\\n\\n正文内容...",
                "metadata": {"table_count": 2, "image_count": 1},
            },
            ...
        ]
    """

    _temp_dirs: List[str] = []

    @staticmethod
    def is_available() -> bool:
        return _mineru_available

    @staticmethod
    def get_import_error() -> str:
        return _mineru_import_error

    @staticmethod
    def get_python_path() -> Optional[str]:
        return _MINERU_VENV_PYTHON

    @staticmethod
    def get_version() -> str:
        """获取已安装的 mineru 版本号"""
        py = _MINERU_VENV_PYTHON
        if not py:
            return "N/A"
        try:
            result = subprocess.run(
                [py, "-c", "from mineru.version import __version__; print(__version__)"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=10,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            return result.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    @classmethod
    def _cleanup_temp_dirs(cls):
        for d in cls._temp_dirs:
            try:
                if os.path.exists(d):
                    shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass
        cls._temp_dirs.clear()

    @classmethod
    def _read_mineru_output(
        cls, output_dir: str, pdf_stem: str, parse_method: str = "auto"
    ) -> List[Dict[str, Any]]:
        """
        从 MinerU v2 的输出目录中读取解析结果.

        v2 pipeline backend 输出结构:
          output_dir/{pdf_stem}/{method}/
            {pdf_stem}.md
            {pdf_stem}_middle.json
            {pdf_stem}_content_list.json
            {pdf_stem}_content_list_v2.json
            images/

        兼容旧版 magic-pdf 输出结构.
        """
        # 尝试 {pdf_stem}/{method}/ 目录
        method_dir = os.path.join(output_dir, pdf_stem, parse_method)
        if not os.path.isdir(method_dir):
            method_dir = os.path.join(output_dir, pdf_stem)

        if not os.path.isdir(method_dir):
            logger.warning(f"MinerU 输出目录不存在: {method_dir}")
            return []

        md_file = os.path.join(method_dir, f"{pdf_stem}.md")
        middle_json = os.path.join(method_dir, f"{pdf_stem}_middle.json")
        content_json = os.path.join(method_dir, f"{pdf_stem}_content_list.json")
        content_json_v2 = os.path.join(method_dir, f"{pdf_stem}_content_list_v2.json")

        pages = []

        # 方案 A: 从 content_list / middle_json 读取按页结构化数据
        for json_path in (content_json_v2, content_json, middle_json):
            if not os.path.isfile(json_path):
                continue
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                items = data if isinstance(data, list) else data.get("pdf_info", [])
                if not items:
                    continue

                first = items[0] if isinstance(items[0], dict) else {}
                # content_list 是块级别 (有 page_idx 无 markdown)
                # middle_json 是页级别 (可能直接有 markdown)
                is_block_level = (
                    isinstance(first, dict)
                    and "page_idx" in first
                    and "markdown" not in first
                )

                if is_block_level:
                    # --- content_list 格式: 按 page_idx 分组聚合 ---
                    page_texts: Dict[int, List[str]] = {}
                    page_tables: Dict[int, int] = {}
                    page_images: Dict[int, int] = {}

                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        pi = item.get("page_idx", 0)
                        if isinstance(pi, (int, float)):
                            pi = int(pi)

                        text = item.get("text") or item.get("content", "")
                        if not isinstance(text, str) or not text.strip():
                            continue

                        if pi not in page_texts:
                            page_texts[pi] = []
                            page_tables[pi] = 0
                            page_images[pi] = 0

                        page_texts[pi].append(text)

                        btype = item.get("type", "")
                        if btype in ("table", "simple_table", "complex_table"):
                            page_tables[pi] += 1
                        elif btype in ("image", "chart"):
                            page_images[pi] += 1

                    for pi in sorted(page_texts.keys()):
                        combined = "\n\n".join(page_texts[pi])
                        pages.append({
                            "page_number": pi + 1,
                            "markdown": TextPostProcessor.post_process(combined),
                            "metadata": {
                                "table_count": page_tables.get(pi, 0),
                                "image_count": page_images.get(pi, 0),
                            },
                        })
                else:
                    # --- middle_json 格式 (旧版兼容): 每项是一页 ---
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        pn = item.get("page_idx", item.get("page_number", 0))
                        if isinstance(pn, (int, float)):
                            pn = int(pn) + 1

                        md = item.get("markdown") or item.get("content") or item.get("text", "")
                        if isinstance(md, str) and md.strip():
                            tb = item.get("tables", [])
                            im = item.get("images", item.get("img", []))
                            pages.append({
                                "page_number": int(pn),
                                "markdown": TextPostProcessor.post_process(md),
                                "metadata": {
                                    "table_count": len(tb) if isinstance(tb, list) else 0,
                                    "image_count": len(im) if isinstance(im, list) else 0,
                                },
                            })

                if pages:
                    logger.debug(f"从 {os.path.basename(json_path)} 读取到 {len(pages)} 页")
                    break
            except Exception as e:
                logger.debug(f"{os.path.basename(json_path)} 解析失败: {e}")

        # 方案 B: 从 .md 文件读取 (JSON 不可用时的回退)
        if not pages and os.path.isfile(md_file):
            try:
                with open(md_file, "r", encoding="utf-8") as f:
                    full_md = f.read()

                if full_md.strip():
                    parts = [full_md]
                    for sep in [
                        r'\n---\s*\n',
                        r'\n\* \* \*\s*\n',
                        r'\n## Page\s+\d+',
                        r'\n\{pagebreak\}',
                    ]:
                        if len(parts) == 1:
                            parts = re.split(sep, full_md)

                    for i, part in enumerate(parts, 1):
                        text = TextPostProcessor.post_process(part)
                        if text and len(text) > 20:
                            pages.append({
                                "page_number": i,
                                "markdown": text,
                                "metadata": {"table_count": 0, "image_count": 0},
                            })

                    if not pages:
                        text = TextPostProcessor.post_process(full_md)
                        if text:
                            pages.append({
                                "page_number": 1,
                                "markdown": text,
                                "metadata": {"table_count": 0, "image_count": 0},
                            })
            except Exception as e:
                logger.warning(f".md 文件读取失败: {e}")

        return pages

    @classmethod
    def _call_mineru_subprocess(
        cls,
        file_path: str,
        output_dir: str,
        parse_method: str,
        backend: str = "pipeline",
    ) -> bool:
        """通过 subprocess 调用独立 venv 中的 Python 执行 mineru.cli.common.do_parse."""
        py = cls.get_python_path()
        if not py:
            raise RuntimeError("MinerU Python 不可用")

        pdf_stem = Path(file_path).stem

        code = f'''
import sys, os, traceback
os.environ["LOGURU_LEVEL"] = "ERROR"
os.environ["TOKENIZERS_PARALLELISM"] = "false"

try:
    from mineru.cli.common import do_parse, read_fn
    from mineru.utils.enum_class import MakeMode

    pdf_path = r"{file_path}"
    pdf_stem = r"{pdf_stem}"
    output_dir = r"{output_dir}"
    parse_method = "{parse_method}"
    backend = "{backend}"

    pdf_bytes = read_fn(pdf_path)
    if not pdf_bytes:
        print("__MINERU_ERR__: read_fn returned empty bytes", file=sys.stderr)
        sys.exit(1)

    do_parse(
        output_dir=output_dir,
        pdf_file_names=[pdf_stem],
        pdf_bytes_list=[pdf_bytes],
        p_lang_list=["ch"],
        backend=backend,
        parse_method=parse_method,
        formula_enable=True,
        table_enable=True,
        f_draw_layout_bbox=False,
        f_draw_span_bbox=False,
        f_dump_md=True,
        f_dump_middle_json=True,
        f_dump_model_output=False,
        f_dump_orig_pdf=False,
        f_dump_content_list=True,
        f_make_md_mode=MakeMode.MM_MD,
        start_page_id=0,
        end_page_id=None,
    )
    print("__MINERU_OK__")
except Exception as e:
    print(f"__MINERU_ERR__: {{e}}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
'''

        result = subprocess.run(
            [py, "-c", code],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "LOGURU_LEVEL": "ERROR"},
        )

        if result.returncode == 0 and "__MINERU_OK__" in result.stdout:
            return True
        else:
            logger.error(
                f"MinerU subprocess 失败 (exit={result.returncode}):\n"
                f"STDERR: {result.stderr[:2000]}\n"
                f"STDOUT: {result.stdout[:500]}"
            )
            return False

    @classmethod
    def extract(
        cls,
        file_path: str,
        output_dir: Optional[str] = None,
        ocr: bool = False,
        backend: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        使用 MinerU 解析 PDF, 返回按页组织的 Markdown 内容.

        Args:
            file_path: PDF 文件绝对路径
            output_dir: 输出目录 (默认临时目录, 解析完自动清理)
            ocr: 是否强制 OCR 模式
            backend: MinerU backend (默认从 MINERU_BACKEND 环境变量读取, fallback "pipeline")

        Returns:
            每页一个 dict, 含 page_number / markdown / metadata
        """
        if not cls.is_available():
            raise RuntimeError(
                f"MinerU 未安装, 无法解析. 请先创建独立 venv 并安装 mineru:\n"
                f"  python -m venv .venv-mineru\n"
                f"  .venv-mineru/Scripts/pip install mineru[pipeline]\n"
                f"错误: {_mineru_import_error}"
            )

        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"PDF 文件不存在: {file_path}")

        if backend is None:
            backend = os.getenv("MINERU_BACKEND", "pipeline")

        own_tempdir = output_dir is None
        if own_tempdir:
            output_dir = tempfile.mkdtemp(prefix="mineru_")
            cls._temp_dirs.append(output_dir)

        pdf_stem = Path(file_path).stem
        parse_method = "ocr" if ocr else "auto"

        logger.info(
            f"MinerU 开始解析: {file_path} "
            f"(backend={backend}, method={parse_method})"
        )

        try:
            success = cls._call_mineru_subprocess(
                file_path, output_dir, parse_method, backend=backend
            )

            if not success:
                logger.warning("MinerU subprocess 调用失败, 尝试读取已有输出")

            pages = cls._read_mineru_output(output_dir, pdf_stem, parse_method)

            if pages:
                total_chars = sum(len(p.get("markdown", "")) for p in pages)
                logger.info(
                    f"MinerU 解析完成: {Path(file_path).name} "
                    f"-> {len(pages)} 页, 总 {total_chars} 字符"
                )
            else:
                logger.warning(f"MinerU 解析后无输出: {file_path}")

            return pages

        except Exception as e:
            logger.error(f"MinerU 解析失败: {file_path}: {e}", exc_info=True)
            return []

        finally:
            if own_tempdir and output_dir:
                cls._cleanup_temp_dirs()


# ============================================================
# 模块级别便利函数
# ============================================================

from typing import Literal  # noqa: E402

PDFEngine = Literal["auto", "mineru", "pypdf2"]


def resolve_pdf_engine(engine: str) -> str:
    """
    解析 pdf_engine 参数, 返回实际使用的引擎名称.

    - "auto" -> mineru (若可用) 否则 pypdf2
    - "mineru" -> mineru (不可用时抛出错误)
    - "pypdf2" -> pypdf2
    """
    if engine == "auto":
        return "mineru" if _mineru_available else "pypdf2"
    if engine == "mineru" and not _mineru_available:
        raise ImportError(
            f"MinerU 未安装, 无法使用 mineru 引擎."
            f"请先创建独立 venv 并安装 mineru:\n"
            f"  python -m venv .venv-mineru\n"
            f"  .venv-mineru/Scripts/pip install mineru[pipeline]\n"
            f"错误: {_mineru_import_error}"
        )
    return engine


def get_mineru_info() -> Dict[str, Any]:
    """返回当前 MinerU 集成状态信息"""
    return {
        "available": _mineru_available,
        "python_path": _MINERU_VENV_PYTHON,
        "version": MinerUPDFExtractor.get_version() if _mineru_available else None,
        "error": _mineru_import_error if not _mineru_available else None,
    }


__all__ = [
    "MinerUPDFExtractor",
    "resolve_pdf_engine",
    "get_mineru_info",
    "PDFEngine",
    "_mineru_available",
]
