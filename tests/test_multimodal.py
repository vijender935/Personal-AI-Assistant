import pytest
import multimodal

def test_user_paths_are_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(multimodal, "FILE_ROOT", tmp_path / "files")
    path = multimodal.save_upload("note.txt", b"hello", user_id=1)
    assert path == "note.txt"
    assert multimodal.read_upload(path, user_id=1)["text"] == "hello"
    with pytest.raises(FileNotFoundError):
        multimodal.read_upload(path, user_id=2)

def test_path_traversal_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(multimodal, "FILE_ROOT", tmp_path / "files")
    with pytest.raises(PermissionError):
        multimodal._safe_path("../secret.txt", user_id=1)

def test_filename_is_sanitized(monkeypatch, tmp_path):
    monkeypatch.setattr(multimodal, "FILE_ROOT", tmp_path / "files")
    path = multimodal.save_upload("/tmp/evil.txt", b"x", user_id=1)
    assert path == "evil.txt"
    assert (tmp_path / "files" / "user_1" / "evil.txt").read_bytes() == b"x"
