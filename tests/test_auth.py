import auth
import pytest
from db import connect

@pytest.fixture(autouse=True)
def clean_auth_db():
    auth.init_auth_db()
    with connect() as con:
        con.execute("DELETE FROM auth_sessions")
        con.execute("DELETE FROM account")
    yield
    with connect() as con:
        con.execute("DELETE FROM auth_sessions")
        con.execute("DELETE FROM account")

def test_single_account_lifecycle():
    assert not auth.account_exists()
    account=auth.setup_account("Vijender","vijender@example.com","StrongPass123")
    assert account["email"]=="vijender@example.com"
    assert auth.account_exists()
    with pytest.raises(RuntimeError):
        auth.setup_account("Other","other@example.com","AnotherPass123")
    result=auth.login("vijender@example.com","StrongPass123")
    assert result
    token,logged=result
    assert auth.get_account_for_session(token)["display_name"]=="Vijender"
    auth.change_password(token,"StrongPass123","NewStrong123")
    assert auth.login("vijender@example.com","StrongPass123") is None
    assert auth.login("vijender@example.com","NewStrong123")
    auth.logout(token)
    assert auth.get_account_for_session(token) is None
