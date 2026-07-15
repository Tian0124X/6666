"""知识工程质量报告、分块预设和金标集加载回归测试。"""

from langchain_core.documents import Document


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
