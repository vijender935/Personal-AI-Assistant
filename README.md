# Personal AI Agent — Final

A conversational personal AI agent using Groq's GPT-OSS 120B model,
persistent SQLite conversation memory, explicit long-term memories, web search,
file tools, and an optional shell tool.

## Features

### Phase 1 — Conversational memory
- Multi-turn conversation history.
- Persistent SQLite database.
- Separate session IDs.
- `/new` starts a fresh session.

### Phase 2 — Model migration
Default model:

```text
openai/gpt-oss-120b
```

Override with:

```bash
export GROQ_MODEL="openai/gpt-oss-20b"
```

### Phase 3 — Tool layer
- Safe arithmetic calculator.
- DuckDuckGo web search.
- File read/write.
- Shell tool disabled by default.
- Basic destructive-command denylist.
- Tool errors and timeouts are handled.

### Phase 4 — Long-term memory

```text
/remember Mera naam Vijender hai
```

The agent also recognizes phrases such as `Remember that ...` and `Yaad rakho ...`.

Memories are stored in `agent_memory.db`.

### Phase 5 — Chat UI

A lightweight Gradio UI is included in `app.py`.

## Setup

```bash
pip install -r requirements.txt
```

Termux:

```bash
pip install -r requirements.txt --break-system-packages
```

Set the API key:

```bash
export GROQ_API_KEY="your-key"
```

Terminal chat:

```bash
python agent.py
```

Web UI:

```bash
python app.py
```

## Optional shell access

Shell execution is intentionally OFF by default.

Only enable it in a trusted environment:

```bash
export ALLOW_SHELL=1
python agent.py
```

## Architecture

```text
User
  ↓
Chat UI / Terminal
  ↓
Conversation + Memory
  ↓
Groq GPT-OSS 120B
  ↓
Tool-calling loop
  ├── Calculator
  ├── Web Search
  ├── File Read
  ├── File Write
  └── Optional Shell
  ↓
Final response
```
