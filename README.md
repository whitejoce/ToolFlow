# ToolFlow

[中文](./README_CN.md) | English

---

**Stop building workflows. Write a Python function. That's your tool.**

ToolFlow is a runtime-first MCP tool system for LLM applications. Forget DAGs and static pipelines — write plain Python functions and let ToolFlow handle dispatch, versioning, isolation, and execution at runtime.

No orchestration DSL. No full redeployment on every change. Tools compose dynamically, run in isolated sandboxes, and report back clean and stateless every time.

### Why ToolFlow?

- **No workflows required** — tools compose at runtime, not at design time
- **Python-native** — any Python function becomes a tool, zero boilerplate
- **Stateless & isolated** — each execution runs in an ephemeral sandbox; failures don't bleed over
- **Separated control & execution** — Django manages the control plane; FastMCP handles stateless execution
- **Built-in lifecycle management** — version, release, and monitor tools without restarting anything

### Architecture & Invocation Flow

#### 1. Architecture Flowchart

```mermaid
graph TD
  A[LLM / Client] -->|Tool Call| B[Django Gateway + Control Plane]
  B -->|Fetch Tool Code/Version| C["DB / Storage"]
  B -->|Dispatch Tasks| D{Queue/Dispatcher}
  D --> E[FastMCP Executor 1]
  D --> F[FastMCP Executor N]
  E -->|Ephemeral Load + Execute| G[Ephemeral Tool Runtime Sandbox]
  F -->|Ephemeral Load + Execute| H[Ephemeral Tool Runtime Sandbox]
  E -->|Report Status/Result| B
  F -->|Report Status/Result| B
```

### Project Structure

- `server/`: Django gateway and management APIs
- `runtime/`: executor, bridge service, and runtime config
- `frontend/`: React + Vite frontend
- `start_services.py`: one-command local orchestrator

### Quick Start

1) Set up Python environment

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2) Install frontend dependencies

```bash
cd frontend
npm install
```

3) Initialize database

```bash
cd ../server
python manage.py migrate
python preset_tools.py
```

4) Return to project root and start all services

```bash
cd ..
python start_services.py
```

Default frontend URL: `http://127.0.0.1:5173`

### Environment Variables

Copy `.env.example` to `.env` and configure as needed:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS`
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

### Notes

- Runtime config file: `runtime/config.json`
- MCP Bridge script: `runtime/mcp_bridge.py`

