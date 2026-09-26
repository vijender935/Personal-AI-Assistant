import pytest,multimodal
def test_single_user_paths(monkeypatch,tmp_path):
 monkeypatch.setattr(multimodal,"FILE_ROOT",tmp_path/"files")
 path=multimodal.save_upload("note.txt",b"hello");assert path=="note.txt";assert multimodal.read_upload(path)["text"]=="hello"
def test_path_traversal_rejected(monkeypatch,tmp_path):
 monkeypatch.setattr(multimodal,"FILE_ROOT",tmp_path/"files")
 with pytest.raises(PermissionError):multimodal._safe_path("../secret.txt")
def test_filename_sanitized(monkeypatch,tmp_path):
 monkeypatch.setattr(multimodal,"FILE_ROOT",tmp_path/"files")
 assert multimodal.save_upload("/tmp/evil.txt",b"x")=="evil.txt"
 assert (tmp_path/"files"/"evil.txt").read_bytes()==b"x"
