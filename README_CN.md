# ToolFlow

中文 | [English](./README.md)

---

**别再搭工作流了。写个函数，就是一个工具。**

ToolFlow 是一个运行时优先的 MCP 工具系统，专为 LLM 应用设计。你只需编写普通的 Python 函数，ToolFlow 负责版本管理、调度分发、隔离执行与运行时动态组合。

没有 DAG，没有 Pipeline，不需要重启服务。工具按需加载、执行、销毁，在隔离沙箱中运行，调用时动态组合，无需提前编排。

底层基于 Django（控制面）+ FastMCP（无状态执行层）构建。

### 核心特性

- 🐍 **Python 原生** — 写一个函数，注册一个工具，零样板代码。
- ⚡ **运行时动态组合** — 工具在调用时组合，而非部署时静态绑定。
- 🔒 **瞬态隔离执行** — 每次调用独立沙箱，无共享状态，无副作用。
- 🧱 **控制面与执行面分离** — Django 管理工具资产，FastMCP 专注无状态执行。
- 🔄 **内置生命周期管理** — 独立的版本控制、发布与监控。

### 目录结构

- `server/`：Django 网关与后台管理 API
- `runtime/`：执行器、桥接服务与运行配置
- `frontend/`：React + Vite 前端
- `start_services.py`：本地一键启动脚本

### 快速启动

1) 配置 Python 环境

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2) 安装前端依赖

```bash
cd frontend
npm install
```

3) 初始化数据库

```bash
cd ..\server
python manage.py migrate
python preset_tools.py
```

4) 返回项目根目录并启动全部服务

```bash
cd ..
python start_services.py
```

前端默认地址：`http://127.0.0.1:5173`

### 环境变量

请将根目录 `.env.example` 复制为 `.env`，并按需配置：

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CORS_ALLOWED_ORIGINS`
- `OPENAI_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`

### 说明

- 运行时配置文件位于 `runtime/config.json`
- MCP Bridge 脚本位于 `runtime/mcp_bridge.py`


