"""多模态（图片分析）+ 报告下载端点"""

import os
import logging

from fastapi import APIRouter, HTTPException, Query, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse

from app.config import settings
from app.tools.image_analyzer import save_uploaded_image, analyze_image, is_image_file
from app.models.user import UserInfo
from app.api.auth import require_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat/image", tags=["对话"])
async def analyze_chat_image(
    file: UploadFile = File(...),
    question: str = Form(default="请描述这张图片的内容"),
    user: UserInfo = Depends(require_user),
):
    """
    上传图片进行分析（截图提问、图表分析、OCR文字提取）

    支持: PNG, JPG, GIF, BMP, WebP, TIFF
    """
    if not file.filename or not is_image_file(file.filename):
        supported = ".png, .jpg, .jpeg, .gif, .bmp, .webp, .tiff"
        raise HTTPException(status_code=400, detail=f"不支持的图片格式，支持: {supported}")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片过大 (上限10MB)")

    path = save_uploaded_image(data, file.filename)
    analysis_text = analyze_image(path, question)

    if settings.is_llm_available and question:
        from app.rag.llm_factory import get_llm
        from langchain_core.messages import SystemMessage, HumanMessage
        try:
            llm = get_llm(temperature=0.3)
            response = llm.invoke([
                SystemMessage(content="你是多模态分析助手。根据图片的OCR文字和元数据，回答用户问题。如果是图表请分析趋势，如果是文档请提取关键信息。"),
                HumanMessage(content=analysis_text),
            ])
            answer = response.content
        except Exception as e:
            answer = analysis_text + f"\n\n⚠️ LLM分析失败: {e}"
    else:
        answer = analysis_text

    return {
        "status": "ok",
        "filename": file.filename,
        "image_path": path,
        "analysis": analysis_text,
        "answer": answer,
    }


@router.get("/chat/report/generate")
async def generate_and_download_report(
    file_path: str = Query(..., description="数据文件路径"),
    session_id: str = Query(default="default"),
    user: UserInfo = Depends(require_user),
):
    """
    生成 Word 数据分析报告并返回下载。
    使用方式: GET /api/chat/report/generate?file_path=data/documents/xxx.xlsx&session_id=xxx
    """
    import asyncio
    from app.tools.data_conversation import generate_data_report
    from app.tools.registry import validate_file_path

    try:
        safe_path = validate_file_path(file_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail=f"文件不存在: {safe_path}")

    try:
        report_path = await asyncio.to_thread(generate_data_report, safe_path)
    except Exception as e:
        logger.error(f"报告生成失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"报告生成失败: {e}")

    if not os.path.exists(report_path):
        raise HTTPException(status_code=500, detail="报告生成后文件不存在")

    filename = os.path.basename(report_path)
    return FileResponse(
        report_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
