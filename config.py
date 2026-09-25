"""Centralized configuration for the Personal AI Assistant."""
from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("AGENT_DATA_DIR", BASE_DIR / "data")).expanduser().resolve()
FILE_ROOT = Path(os.getenv("AGENT_FILE_ROOT", DATA_DIR / "files")).expanduser().resolve()
DB_PATH = Path(os.getenv("AGENT_DB", DATA_DIR / "agent_memory.db")).expanduser().resolve()

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
MAX_ITERATIONS = max(1, int(os.getenv("MAX_ITERATIONS", "8")))
MAX_RETRIES = max(0, int(os.getenv("MAX_RETRIES", "2")))
MAX_HISTORY_MESSAGES = max(1, int(os.getenv("MAX_HISTORY_MESSAGES", "30")))
MAX_FILE_CHARS = max(1000, int(os.getenv("MAX_FILE_CHARS", "10000")))
SHELL_TIMEOUT = max(1, int(os.getenv("SHELL_TIMEOUT", "30")))
ALLOW_SHELL = os.getenv("ALLOW_SHELL", "0") == "1"
ALLOWED_SHELL_COMMANDS = {
    item.strip().split()[0]
    for item in os.getenv("ALLOWED_SHELL_COMMANDS", "python,python3,pip,git,pwd,ls,cat,echo").split(",")
    if item.strip()
}

def ensure_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FILE_ROOT.mkdir(parents=True, exist_ok=True)
