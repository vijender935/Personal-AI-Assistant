import tools
def test_calculator_is_safe():
 assert tools.calculator("2 + 3 * 4")=="14";assert tools.calculator("2 ** 3")=="8";assert "unsupported" in tools.calculator("__import__('os')").lower()
def test_file_access_is_sandboxed(tmp_path,monkeypatch):
 root=tmp_path/"files";root.mkdir();monkeypatch.setattr(tools,"FILE_ROOT",root)
 assert "Written" in tools.write_file("hello.txt","world");assert tools.read_file("hello.txt")=="world"
 (tmp_path/"outside.txt").write_text("secret");assert "outside the allowed" in tools.read_file("../outside.txt")
def test_shell_disabled(monkeypatch):monkeypatch.setattr(tools,"ALLOW_SHELL",False);assert "disabled" in tools.run_shell("echo hello").lower()
def test_shell_allowlist(tmp_path,monkeypatch):
 monkeypatch.setattr(tools,"ALLOW_SHELL",True);monkeypatch.setattr(tools,"FILE_ROOT",tmp_path);monkeypatch.setattr(tools,"ALLOWED_SHELL_COMMANDS",{"echo"})
 result=tools.run_shell("echo hello");assert "exit_code=0" in result and "hello" in result
def test_chat_helpers(tmp_path,monkeypatch):
 tools.init_db();tools.save_turn("s1","hello","world");tools.set_chat_title("s1","My chat")
 assert tools.get_chat_title("s1")=="My chat";assert tools.remove_last_assistant("s1") is True;assert tools.load_history("s1")[-1]["role"]=="user"
 tools.save_turn("s1","hello","again");assert tools.remove_last_turn("s1") is True;tools.delete_chat("s1");assert tools.load_history("s1")==[]
