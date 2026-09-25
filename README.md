# Personal AI Assistant

A local conversational personal AI assistant powered by Groq, with persistent SQLite memory, tool calling, web search, sandboxed file tools, and a lightweight Gradio UI.

## Phase 6 — Production foundation

The original prototype has now been hardened without changing its core purpose.

### Security improvements

- File reads/writes are restricted to AGENT_FILE_ROOT.
- Calculator no longer uses eval().
- Shell access remains disabled by default.
- Enabled shell commands use an allowlist.
- Shell commands run with shell=False.
- Shell execution has a configurable timeout.
- Runtime configuration is centralized in config.py.
- Runtime data is ignored by Git.
- Automated tests cover security-critical tools.

## Project structure

Personal-AI-Assistant/
- agent.py — agent loop, memory context, model calls
- tools.py — tools and SQLite memory
- config.py — environment-based configuration
- app.py — local Gradio UI
- tests/test_tools.py — security-focused tests
- requirements.txt
- .gitignore
- README.md

## Setup

Create an environment and install dependencies:

    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Termux:

    pip install -r requirements.txt --break-system-packages

Set the Groq key:

    export GROQ_API_KEY="your-key"

Terminal chat:

    python agent.py

Web UI:

    python app.py

Tests:

    pytest -q

## Configuration

Default model:

    openai/gpt-oss-120b

Useful environment variables:

    GROQ_MODEL
    MAX_ITERATIONS
    MAX_RETRIES
    MAX_HISTORY_MESSAGES
    MAX_FILE_CHARS
    AGENT_DATA_DIR
    AGENT_FILE_ROOT
    AGENT_DB
    ALLOW_SHELL
    ALLOWED_SHELL_COMMANDS
    SHELL_TIMEOUT

Default runtime data is stored under:

    data/
      agent_memory.db
      files/

The data directory is intentionally excluded from Git.

## File tools

The AI can read and write text files only inside AGENT_FILE_ROOT.

Example tool paths:

    notes/todo.txt
    projects/example.py

Attempts to escape the configured root using ../ or an external absolute path are rejected.

## Optional shell access

Shell execution is OFF by default.

To explicitly enable it:

    export ALLOW_SHELL=1

Then configure an allowlist if needed:

    export ALLOWED_SHELL_COMMANDS="python,python3,pip,git,pwd,ls,cat,echo"

Commands are executed without shell=True and from the configured file root.

Do not enable shell access in an untrusted environment.

## Memory commands

    /remember Mera naam Vijender hai
    /memories
    /new
    /exit

The assistant also recognizes explicit phrases such as Remember that ... and Yaad rakho ....

## Architecture

User
  |
  +--> Terminal / Gradio UI
          |
          +--> Agent Engine
                  |
                  +--> Conversation history
                  +--> Long-term memory
                  +--> Groq LLM
                  +--> Tool loop
                          +--> Calculator
                          +--> Web Search
                          +--> Sandboxed File Tools
                          +--> Optional Allowlisted Shell

## Phase 7

Next, the agent engine will be exposed through a proper FastAPI REST API so a future React/Next.js frontend can communicate with it cleanly.


## Phase 7 — FastAPI REST API

The agent engine is now exposed through a REST API. This separates the AI backend from the future web/mobile frontend.

### Run the API

Install dependencies:

    pip install -r requirements.txt

Start the development server:

    uvicorn api:app --reload

The API will be available at:

    http://127.0.0.1:8000

FastAPI interactive documentation:

    http://127.0.0.1:8000/docs

OpenAPI schema:

    http://127.0.0.1:8000/openapi.json

### API endpoints

#### Health

    GET /health

Returns service status, model name, and whether shell access is enabled.

#### Chat

    POST /api/v1/chat

Request:

    {
      "message": "Hello",
      "session_id": "default"
    }

Response:

    {
      "answer": "...",
      "session_id": "default",
      "model": "openai/gpt-oss-120b"
    }

The API keeps the session identifier and passes it to the existing SQLite conversation-memory layer.

#### Memories

Create a memory:

    POST /api/v1/memories

    {
      "fact": "Mera naam Vijender hai",
      "source": "api"
    }

List memories:

    GET /api/v1/memories

Search memories:

    GET /api/v1/memories/search?q=Vijender

### CORS

Allowed frontend origins are configured through CORS_ORIGINS.

Example:

    export CORS_ORIGINS="http://localhost:3000,http://localhost:5173"

This prepares the backend for a future React/Next.js frontend.

### API architecture

    React / Next.js / Mobile
              |
              | HTTP + JSON
              v
         FastAPI API
              |
              v
         Agent Engine
          /    |    \
       Memory LLM  Tools
              |
              v
        SQLite / external services

### Run tests

    pytest -q

Phase 7 adds API-level tests for health, service info, memory operations, and missing API-key handling.
