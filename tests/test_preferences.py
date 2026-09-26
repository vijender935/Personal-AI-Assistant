import preferences
from db import connect

def _clean():
    preferences.init_preferences_db()
    with connect() as con:
        con.execute("DELETE FROM preferences")

def test_defaults(monkeypatch):
    _clean()
    assert preferences.get_preferences()["appearance"]=="System"

def test_update_round_trip(monkeypatch):
    _clean()
    result=preferences.update_preferences({"appearance":"Dark","haptics":False,"language":"Hindi"})
    assert result["appearance"]=="Dark"
    assert result["haptics"] is False
    assert preferences.get_preferences()["language"]=="Hindi"
