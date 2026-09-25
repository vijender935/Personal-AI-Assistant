from pathlib import Path

from document_parser import extract_text, is_supported_document


def test_txt_extraction(tmp_path):
    path=tmp_path/"notes.txt"
    path.write_text("hello\nworld",encoding="utf-8")
    assert "hello" in extract_text(path)


def test_csv_extraction(tmp_path):
    path=tmp_path/"data.csv"
    path.write_text("name,score\nVijender,10\n",encoding="utf-8")
    text=extract_text(path)
    assert "Vijender" in text
    assert "10" in text


def test_supported_documents():
    assert is_supported_document("report.pdf")
    assert is_supported_document("report.docx")
    assert is_supported_document("data.csv")
    assert not is_supported_document("image.png")
