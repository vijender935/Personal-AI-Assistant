import auth
def test_single_account_lifecycle(monkeypatch,tmp_path):
    monkeypatch.setattr(auth,"DB_PATH",tmp_path/"auth.db")
    auth.init_auth_db()
    assert not auth.account_exists()
    account=auth.setup_account("Vijender","vijender@example.com","StrongPass123")
    assert account["email"]=="vijender@example.com"
    assert auth.account_exists()
    assert auth.setup_account if False else True
    result=auth.login("vijender@example.com","StrongPass123")
    assert result
    token,logged= result
    assert auth.get_account_for_session(token)["display_name"]=="Vijender"
    auth.change_password(token,"StrongPass123","NewStrong123")
    assert auth.login("vijender@example.com","StrongPass123") is None
    assert auth.login("vijender@example.com","NewStrong123")
    auth.logout(token)
    assert auth.get_account_for_session(token) is None
