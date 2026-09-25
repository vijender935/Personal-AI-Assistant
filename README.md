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


## Phase 8 — Semantic Memory + RAG

Phase 8 upgrades keyword-only memory to local semantic retrieval and adds a lightweight document RAG layer.

### Semantic memory

Explicitly saved memories are embedded with:

    sentence-transformers/all-MiniLM-L6-v2

Embeddings are stored in SQLite. New messages retrieve semantically similar memories using cosine similarity rather than only matching words.

### Local RAG

Text documents can be chunked, embedded, stored in SQLite, and retrieved by semantic similarity.

Index a text document directly:

    POST /api/v1/rag/documents

Example body:

    {
      "source": "notes/knowledge.txt",
      "content": "Your knowledge-base text..."
    }

Index a file inside AGENT_FILE_ROOT:

    POST /api/v1/rag/files?path=notes/knowledge.txt

Search the knowledge base:

    GET /api/v1/rag/search?q=your%20question

When relevant RAG chunks exist, the agent adds them to the model context before generating its answer.

### Phase 8 architecture

    User message
         |
         v
       Agent
      /  |  \
     /   |   \
 History Memory RAG
   |      |     |
 SQLite  SQLite SQLite
          \     /
           \   /
        Relevant context
              |
              v
           Groq LLM

### Install

Phase 8 adds:

    sentence-transformers
    numpy

Run:

    pip install -r requirements.txt
    pytest -q

The embedding model is loaded lazily. The first semantic-memory or RAG operation may download the model and take longer than later requests.

The first implementation intentionally uses SQLite instead of requiring a separate vector database, keeping the local RAG stack simple and free for personal-scale datasets.


## Phase 9 — Agentic Tools + MCP

Phase 9 adds a standard Model Context Protocol (MCP) server around the assistant's tool layer.

### MCP server

File:

    mcp_server.py

The MCP server exposes:

    calculate
    search_web
    read_text_file
    write_text_file
    execute_command
    add_knowledge
    add_knowledge_file
    search_knowledge

This makes the assistant's capabilities consumable by MCP-compatible hosts and agents instead of being hard-wired to one UI.

### Run MCP locally

Install dependencies:

    pip install -r requirements.txt

For stdio:

    python mcp_server.py

For Streamable HTTP:

    mcp run mcp_server.py --transport streamable-http

### Phase 9 architecture

    Chat / Future UI
             |
             v
        Agent Engine
          /       \
         /         \
    Groq LLM    MCP Tool Layer
                    |
          +---------+---------+
          |         |         |
        Web/File  Shell      RAG
                  optional

The MCP server is separated from the model provider, so the same tools can later be consumed by another model, agent, IDE, MCP host, or custom frontend.

### Security

Phase 6 security controls remain active:

- File operations stay inside AGENT_FILE_ROOT.
- Shell remains disabled by default.
- Shell commands remain allowlisted.
- Shell uses shell=False and a timeout.
- RAG file indexing uses the same file sandbox.

The MCP layer does not bypass these controls.


## Phase 10 — Professional Frontend

A dedicated React/Vite frontend has been added under `frontend/`.

### UI features

- ChatGPT-style conversational layout
- Responsive sidebar
- New chat
- Conversation list
- Chat search UI
- Model indicator
- Message composer
- Enter-to-send / Shift+Enter
- Loading indicator
- Suggested prompts
- Settings modal
- Profile entry point
- Mobile-responsive layout
- Direct connection to the Phase 7 FastAPI chat endpoint

### Run the frontend

From the repository root:

    cd frontend
    npm install
    npm run dev

The Vite development server normally runs on:

    http://localhost:5173

Make sure the FastAPI backend is also running:

    uvicorn api:app --reload

The frontend calls:

    POST http://127.0.0.1:8000/api/v1/chat

For a deployed backend, change the API base URL in `frontend/src/main.jsx`.

### Frontend architecture

    React/Vite
        |
        | HTTP + JSON
        v
    FastAPI
        |
        v
    Agent Engine
      / | \
     RAG Memory Tools
        |
        v
      Groq LLM

Phase 10 is intentionally frontend-first. Authentication, persistent user accounts, file uploads, streaming responses, and richer profile/settings are expanded in the following phases.


## Phase 12 — Files + Multimodal Foundation

Phase 12 adds an authenticated file-upload layer and frontend attachment control.

### File API

    POST /api/v1/files/upload
    GET  /api/v1/files/{path}

Uploads are restricted to 10 MB and stored inside the configured file sandbox. Path traversal is rejected.

Supported local file handling includes text/JSON/XML preview and binary-file metadata/base64 access.

### Frontend

The chat composer now includes an attachment button. Selected files are uploaded through the authenticated FastAPI endpoint and the uploaded filename is added to the current composer context.

This phase establishes the file pipeline. Rich vision-model prompting, PDF extraction, OCR, document previews, and image-aware chat are the next multimodal refinements.


## Phase 13 — MCP Ecosystem

Phase 13 adds an external MCP server registry layer.

Configure external servers through the MCP_SERVERS environment variable as JSON.

Example:

    export MCP_SERVERS='{"local":{"transport":"stdio","command":"python","args":["server.py"]},"remote":{"transport":"streamable-http","url":"https://example.com/mcp"}}'

The backend exposes the authenticated registry view at:

    GET /api/v1/mcp/servers

The frontend includes an MCP Servers entry that displays configured servers.

The registry is intentionally configuration-only in this phase. It does not blindly execute arbitrary remote commands. This keeps external MCP connectivity opt-in while establishing the architecture for a future MCP client/tool discovery layer.
