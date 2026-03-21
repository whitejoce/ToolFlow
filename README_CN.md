# ToolFlow

中文 | [English](./README.md)

---

## 中文说明

### 项目简介

ToolFlow 是一个基于瞬态执行模型（Ephemeral Execution Model）的 LLM Tool 动态调度与全栈管理平台，包含：

- Django 网关与控制面后端
- MCP Bridge（STDIO/SSE）
- 无状态 FastMCP 执行器与运行时配置
- React 管理前端

### 核心设计原则

1. **最小命名空间原则**：每次调用创建独立上下文，绝对隔离，避免全局状态污染。
2. **无状态执行原则**：MCP 执行节点不维护长期状态，天然支持多节点横向扩展。
3. **控制面与执行面分离**：Django 负责管理工具资产与调度状态；FastMCP 专注无状态的代码执行。
4. **失败可回收原则**：执行失败不影响系统整体稳定性，销毁上下文即完成回滚。
5. **按需即时加载**：放弃传统热更新，在独立的沙箱中即时编译执行最新代码。

### 系统架构流转

1. **请求接入**：LLM / 客户端发起调用请求至 Django 控制面。
2. **资产读取与派发**：控制面获取活跃版本的工具代码，并将任务派发给连接的 FastMCP 执行器。
3. **瞬态执行**：执行器在短生命周期的安全沙箱中动态载入代码，执行并进行签名校验。
4. **结果回传与销毁**：任务完成或失败后，沙箱即刻销毁，结果异步回传至控制面并最终返回给用户。

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


