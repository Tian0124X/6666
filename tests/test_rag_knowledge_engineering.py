"""知识工程质量报告、分块预设和金标集加载回归测试。"""

from langchain_core.documents import Document
import pytest


@pytest.mark.asyncio
async def test_indexing_persists_version_metadata_on_every_chunk(monkeypatch, tmp_path):
    """质量报告中的文件版本必须随切片写入，供重启后的文档列表读取。"""
    from app.api import rag

    source = tmp_path / "员工手册.txt"
    source.write_text("制度正文", encoding="utf-8")
    chunks = [Document(page_content="制度正文", metadata={"source": str(source), "filename": source.name, "chunk_index": 0})]
    captured: dict[str, object] = {}
    monkeypatch.setattr(rag.UniversalDocumentLoader, "load", lambda _path: chunks)
    monkeypatch.setattr(rag, "split_documents", lambda _documents: chunks)
    monkeypatch.setattr(rag, "build_index_quality_report", lambda *_args: {"file_sha256": "a" * 64})
    monkeypatch.setattr(rag, "delete_by_source", lambda _source: 0)
    monkeypatch.setattr(rag, "add_documents", lambda indexed: captured.setdefault("chunks", indexed) and len(indexed))
    rag._index_status.clear()

    await rag._index_file(source, source.name, "2025-07-01")

    indexed = captured["chunks"]
    assert isinstance(indexed, list)
    assert indexed[0].metadata["file_sha256"] == "a" * 64
    assert indexed[0].metadata["indexed_at"]
    assert indexed[0].metadata["document_date"] == "2025-07-01"
    assert rag._index_status[source.name]["quality"]["indexed_at"]
    assert rag._index_status[source.name]["quality"]["document_date_source"] == "manual_upload"


def test_default_splitter_applies_document_type_preset(monkeypatch):
    """默认分块必须按文档类型选择预设，而不是全部走通用配置。"""
    from app.rag import splitter

    selected_types: list[str] = []
    original = splitter.create_splitter_for_document

    def capture(document, file_type=None):
        selected_types.append(document.metadata["file_type"])
        return original(document, file_type)

    monkeypatch.setattr(splitter, "create_splitter_for_document", capture)
    documents = [
        Document(page_content="制度内容。" * 200, metadata={"file_type": "pdf"}),
        Document(page_content="表格内容。" * 200, metadata={"file_type": "excel"}),
    ]

    chunks = splitter.split_documents(documents)

    assert chunks
    assert selected_types == ["pdf", "excel"]
    assert splitter.get_preset_for_type("excel")["chunk_size"] == 400
    assert splitter.get_preset_for_type("pdf_mineru")["chunk_size"] == 1200


def test_explicit_chunk_parameters_keep_backward_compatible_override(monkeypatch):
    """调用方显式指定大小时，应继续使用统一自定义参数。"""
    from app.rag import splitter

    def unexpected(*_args, **_kwargs):
        raise AssertionError("显式参数不应调用文档预设")

    monkeypatch.setattr(splitter, "create_splitter_for_document", unexpected)
    chunks = splitter.split_documents(
        [Document(page_content="测试内容。" * 100, metadata={"file_type": "pdf"})],
        chunk_size=120,
        chunk_overlap=20,
    )

    assert len(chunks) > 1


def test_index_quality_report_contains_version_and_parse_metrics(tmp_path):
    """上传质量报告必须包含版本、解析和切片统计。"""
    from app.rag.quality import build_index_quality_report

    file_path = tmp_path / "员工手册.txt"
    file_path.write_text("第一条制度", encoding="utf-8")
    documents = [Document(
        page_content="第一条制度",
        metadata={"file_type": "txt", "parser": "text"},
    )]
    chunks = [Document(page_content="第一条制度", metadata={"chunk_index": 0})]

    report = build_index_quality_report(file_path, documents, chunks)

    assert len(report["file_sha256"]) == 64
    assert report["source_characters"] == len("第一条制度")
    assert report["chunks"] == 1
    assert report["empty_chunks"] == 0
    assert report["parsers"] == ["text"]


def test_load_golden_dataset_validates_jsonl(tmp_path):
    """金标集应以项目实际文件名作为检索评测的输入。"""
    from app.eval.golden_dataset import load_golden_dataset

    dataset = tmp_path / "golden.jsonl"
    dataset.write_text(
        '{"id":"q1","question":"年假有几天？","relevant_docs":["员工手册.pdf"]}\n',
        encoding="utf-8",
    )

    samples = load_golden_dataset(dataset)

    assert samples[0]["id"] == "q1"
    assert samples[0]["expected_refusal"] is False


def test_pdf_fallback_enriches_page_when_numeric_facts_are_missing(monkeypatch):
    """MinerU 漏表格数字时，自动模式应保留其文本并补入 PyPDF 回退内容。"""
    from app.rag.loader import UniversalDocumentLoader

    mineru = [Document(page_content="年假表格标题，连续工作满12个月。", metadata={"page": 2, "parser": "mineru"})]
    fallback = [Document(page_content="已满1年 5天；已满10年 10天；已满20年 15天。", metadata={"page": 2, "parser": "pypdf"})]
    monkeypatch.setattr(UniversalDocumentLoader, "_load_pdf_pypdf2", lambda _path: fallback)

    result = UniversalDocumentLoader._enrich_mineru_with_pypdf("policy.pdf", mineru)

    assert "15天" in result[0].page_content
    assert result[0].metadata["parser"] == "mineru+pypdf_fallback"
