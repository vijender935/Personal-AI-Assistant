def test_preferences_round_trip(monkeypatch,tmp_path):
 import preferences
 monkeypatch.setattr(preferences,"DB_PATH",str(tmp_path/"prefs.sqlite3"));monkeypatch.setattr(preferences,"ensure_directories",lambda:None)
 assert preferences.get_preferences()["appearance"]=="System"
 saved=preferences.update_preferences({"appearance":"Dark","haptics":False,"language":"Hindi","custom_instructions":"Be concise."})
 assert saved["appearance"]=="Dark" and saved["haptics"] is False and saved["language"]=="Hindi"
 assert preferences.get_preferences()==saved
