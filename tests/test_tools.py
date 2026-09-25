import tools

def test_calculator_is_safe():
    assert tools.calculator("2 + 3 * 4") == "14"
    assert tools.calculator("2 ** 3") == "8"
    assert "unsupported" in tools.calculator("__import__('os')").lower()

def test_file_access_is_sandboxed(tmp_path, monkeypatch):
    root = tmp_path / "files"
    root.mkdir()
    monkeypatch.setattr(tools, "FILE_ROOT", root)
    assert "Written" in tools.write_file("hello.txt", "world")
    assert tools.read_file("hello.txt") == "world"
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    assert "outside the allowed file root" in tools.read_file("../outside.txt")

def test_shell_disabled(monkeypatch):
    monkeypatch.setattr(tools, "ALLOW_SHELL", False)
    assert "disabled" in tools.run_shell("echo hello").lower()

def test_shell_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ALLOW_SHELL", True)
    monkeypatch.setattr(tools, "FILE_ROOT", tmp_path)
    monkeypatch.setattr(tools, "ALLOWED_SHELL_COMMANDS", {"echo"})
    result = tools.run_shell("echo hello")
    assert "exit_code=0" in result
    assert "hello" in result

def test_chat_metadata_and_regeneration_helpers(tmp_path, monkeypatch):
    db = tmp_path / "assistant.db"
    monkeypatch.setattr(tools, "DB_PATH", db)
    tools.init_db()
    tools.save_turn("s1", "hello", "world", user_id=7)
    tools.set_chat_title("s1", "My chat", user_id=7)
    assert tools.get_chat_title("s1", user_id=7) == "My chat"
    assert tools.get_chat_title("s1", user_id=8) is None
    assert tools.remove_last_assistant("s1", user_id=7) is True
    assert tools.load_history("s1", user_id=7)[-1]["role"] == "user"
    tools.save_turn("s1", "hello", "again", user_id=7)
    assert tools.remove_last_turn("s1", user_id=7) is True
    assert tools.load_history("s1", user_id=7) == [{"role": "user", "content": "hello"}]
    tools.delete_chat("s1", user_id=7)
    assert tools.load_history("s1", user_id=7) == []
