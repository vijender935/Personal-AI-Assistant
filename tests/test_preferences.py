def test_preferences_round_trip(monkeypatch, tmp_path):
    import preferences
    monkeypatch.setattr(preferences, "DB_PATH", str(tmp_path / "prefs.sqlite3"))
    monkeypatch.setattr(preferences, "ensure_directories", lambda: None)

    assert preferences.get_preferences(7)["appearance"] == "System"
    saved = preferences.update_preferences(
        7,
        {"appearance": "Dark", "haptics": False, "language": "Hindi", "custom_instructions": "Be concise."},
    )
    assert saved["appearance"] == "Dark"
    assert saved["haptics"] is False
    assert saved["language"] == "Hindi"
    assert saved["custom_instructions"] == "Be concise."

    loaded = preferences.get_preferences(7)
    assert loaded == saved
