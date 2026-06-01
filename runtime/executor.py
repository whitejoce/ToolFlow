import json
import traceback
import io
import time
import requests
import threading
import builtins
import multiprocessing as mp
import queue as queue_mod
import keyword
from contextlib import redirect_stdout, redirect_stderr

with open("config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

django_port = CONFIG.get("mcp", {}).get("django_port")
if django_port:
    SERVER_URL = f"http://127.0.0.1:{django_port}"
else:
    SERVER_URL = CONFIG["server"]["url"]

ALLOWED_MODULES = set(CONFIG["sandbox"]["allowed_modules"])
EXECUTION_TIMEOUT = float(CONFIG.get("sandbox", {}).get("execution_timeout", 5))
STATUS_REPORT_INTERVAL = float(
    CONFIG.get("server", {}).get("status_report_interval", 5)
)
HTTP_TIMEOUT = max(10.0, STATUS_REPORT_INTERVAL + 5.0)
STREAM_RECONNECT_DELAY = 1.0


class ExecResult:
    def __init__(self, data, logs):
        self.data = data
        self.logs = logs


class SafeExecError(Exception):
    def __init__(self, cause, logs):
        super().__init__(f"Execution failed: {cause}")
        self.logs = logs


def get_safe_builtins():
    original_import = builtins.__import__

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        base_module = name.split(".")[0]
        if base_module not in ALLOWED_MODULES:
            raise ImportError(
                f"Security Sandbox Denied: Module {name} is not in the whitelist."
            )
        return original_import(name, globals, locals, fromlist, level)

    safe_dict = builtins.__dict__.copy()
    safe_dict["__import__"] = safe_import
    safe_dict["open"] = None
    return safe_dict


def _resolve_timeout_seconds(limits: dict = None) -> float:
    timeout = EXECUTION_TIMEOUT
    if isinstance(limits, dict):
        candidate = limits.get("execution_timeout", limits.get("timeout"))
        if candidate is not None:
            timeout = candidate

    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        timeout = EXECUTION_TIMEOUT

    return max(0.1, timeout)


def _is_auto_var_name(name: str) -> bool:
    return (
        isinstance(name, str)
        and name.isidentifier()
        and not keyword.iskeyword(name)
        and not (name.startswith("__") and name.endswith("__"))
    )


def _schema_properties(schema: dict = None) -> dict:
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties")
    return properties if isinstance(properties, dict) else {}


def _schema_field_value(args: dict, field_name: str, field_schema: dict):
    if field_name in args:
        return args[field_name]
    if isinstance(field_schema, dict) and "default" in field_schema:
        return field_schema["default"]
    return None


def _build_runtime_prelude(
    args: dict, context: dict = None, schema: dict = None
) -> str:
    arguments = args if isinstance(args, dict) else {}
    runtime_context = context if isinstance(context, dict) else {}
    lines = [
        "# ToolFlow runtime injected variables",
        f"__toolflow_arguments__ = {repr(arguments)}",
        f"__toolflow_context__ = {repr(runtime_context)}",
    ]

    for field_name, field_schema in _schema_properties(schema).items():
        if not _is_auto_var_name(field_name):
            continue
        value = _schema_field_value(arguments, field_name, field_schema)
        lines.append(f"{field_name} = {repr(value)}")

    return "\n".join(lines) + "\n\n"


def _run_user_code(
    code_str: str, entry: str, args: dict, context: dict = None, schema: dict = None
) -> ExecResult:
    namespace = {"__builtins__": get_safe_builtins()}
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    func_name = entry.split(":")[-1] if ":" in entry else entry
    runtime_code = _build_runtime_prelude(args, context, schema) + code_str

    with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
        try:
            exec(runtime_code, namespace)
            if func_name not in namespace:
                raise ValueError("Entry point not found.")
            func = namespace[func_name]
            result = func(args)
        except Exception as e:
            logs = (
                stdout_buf.getvalue()
                + stderr_buf.getvalue()
                + "\n"
                + traceback.format_exc()
            )
            raise SafeExecError(str(e), logs)

    logs = stdout_buf.getvalue() + stderr_buf.getvalue()
    return ExecResult(data=result, logs=logs)


def _subprocess_entry(
    result_queue, code_str: str, entry: str, args: dict, context: dict, schema: dict
):
    try:
        result = _run_user_code(code_str, entry, args, context, schema)
        result_queue.put({"ok": True, "data": result.data, "logs": result.logs})
    except SafeExecError as e:
        result_queue.put({"ok": False, "error": str(e), "logs": e.logs})
    except Exception as e:
        result_queue.put(
            {
                "ok": False,
                "error": f"Execution failed: {e}",
                "logs": traceback.format_exc(),
            }
        )


def run_ephemeral(
    code_str: str,
    entry: str,
    args: dict,
    context: dict = None,
    schema: dict = None,
    limits: dict = None,
) -> ExecResult:
    timeout_seconds = _resolve_timeout_seconds(limits)
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue(maxsize=1)
    proc = ctx.Process(
        target=_subprocess_entry,
        args=(result_queue, code_str, entry, args, context or {}, schema or {}),
    )
    proc.start()
    proc.join(timeout_seconds)

    if proc.is_alive():
        proc.terminate()
        proc.join(1)
        raise SafeExecError(
            f"Sandbox execution timed out after {timeout_seconds:.2f}s", ""
        )

    try:
        payload = result_queue.get_nowait()
    except queue_mod.Empty:
        exit_code = proc.exitcode
        raise SafeExecError(f"Execution subprocess crashed (exit_code={exit_code})", "")

    if payload.get("ok"):
        return ExecResult(data=payload.get("data"), logs=payload.get("logs", ""))

    raise SafeExecError(
        payload.get("error", "Unknown execution error"), payload.get("logs", "")
    )


class Task:
    def __init__(
        self, task_id, code, entry, args, context=None, schema=None, tool_id=None
    ):
        self.id = task_id
        self.code = code
        self.entry = entry
        self.args = args
        self.context = context or {}
        self.schema = schema or {}
        self.tool_id = tool_id


class WorkerStatus:
    def __init__(self):
        self._lock = threading.Lock()
        self.status = "idle"
        self.current_task = None

    def set_idle(self):
        with self._lock:
            self.status = "idle"
            self.current_task = None

    def set_running(self, task):
        with self._lock:
            self.status = "running"
            self.current_task = task

    def snapshot(self):
        with self._lock:
            return self.status, self.current_task


def report_executor_status(worker_id, worker_env, status="idle", current_task=None):
    body = {
        "executor_id": worker_id,
        "executor_env": worker_env,
        "status": status,
    }
    if current_task is not None:
        body["current_execution_id"] = current_task.id
        body["current_tool_id"] = current_task.tool_id

    try:
        resp = requests.post(
            f"{SERVER_URL}/api/executors/report", json=body, timeout=HTTP_TIMEOUT
        )
        if resp.status_code >= 400:
            print(
                f"[report_executor_status] Failed for {worker_id}: HTTP {resp.status_code} {resp.text}"
            )
    except Exception as e:
        print(f"[report_executor_status] Failed for {worker_id}: {e}")


def heartbeat_loop(worker_id, worker_env, worker_status):
    while True:
        status, current_task = worker_status.snapshot()
        report_executor_status(worker_id, worker_env, status, current_task)
        time.sleep(STATUS_REPORT_INTERVAL)


def report_task(task_id, worker_id, worker_env, payload):
    body = {
        "executor_id": worker_id,
        "executor_env": worker_env,
        **payload,
    }
    resp = requests.post(
        f"{SERVER_URL}/api/tasks/{task_id}/report", json=body, timeout=HTTP_TIMEOUT
    )
    if resp.status_code >= 400:
        print(
            f"[report_task] Failed to report {task_id}: HTTP {resp.status_code} {resp.text}"
        )


def iter_sse_events(resp):
    event_type = "message"
    data_lines = []

    for raw_line in resp.iter_lines(chunk_size=1, decode_unicode=True):
        if raw_line is None:
            continue

        line = raw_line.strip("\r")
        if line == "":
            if data_lines:
                yield event_type, "\n".join(data_lines)
            event_type = "message"
            data_lines = []
            continue

        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_type = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())


def try_pop_task(worker_id, worker_env):
    resp = requests.post(
        f"{SERVER_URL}/api/tasks/pop",
        json={"executor_id": worker_id, "executor_env": worker_env},
        timeout=HTTP_TIMEOUT,
    )
    if resp.status_code != 200:
        print(
            f"[try_pop_task] Failed for {worker_id}: HTTP {resp.status_code} {resp.text}"
        )
        return None

    data = resp.json()
    if not data or not data.get("task_id"):
        return None

    return Task(
        data["task_id"],
        data["code"],
        data["entry"],
        data["args"],
        context=data.get("context"),
        schema=data.get("schema"),
        tool_id=data.get("tool_id"),
    )


def execute_task(worker_id, worker_env, task, worker_status):
    print(f"[{task.id}] Working on {worker_id}...")
    worker_status.set_running(task)
    report_executor_status(worker_id, worker_env, "running", task)
    try:
        res = run_ephemeral(
            task.code,
            task.entry,
            task.args,
            context=task.context,
            schema=task.schema,
            limits={"execution_timeout": EXECUTION_TIMEOUT},
        )
        report_task(
            task.id,
            worker_id,
            worker_env,
            {"status": "DONE", "result": res.data, "logs": res.logs},
        )
    except SafeExecError as e:
        report_task(
            task.id,
            worker_id,
            worker_env,
            {"status": "FAILED", "error": str(e), "logs": e.logs},
        )
    finally:
        worker_status.set_idle()
        report_executor_status(worker_id, worker_env, "idle")


def run_worker(worker_id, worker_env="prod"):
    print(
        f"Starting Worker {worker_id} [{worker_env}], streaming task events from {SERVER_URL} ..."
    )
    worker_status = WorkerStatus()
    report_executor_status(worker_id, worker_env, "idle")
    heartbeat = threading.Thread(
        target=heartbeat_loop, args=(worker_id, worker_env, worker_status), daemon=True
    )
    heartbeat.start()

    while True:
        try:
            with requests.get(
                f"{SERVER_URL}/api/tasks/stream",
                params={"executor_id": worker_id, "executor_env": worker_env},
                stream=True,
                timeout=(HTTP_TIMEOUT, HTTP_TIMEOUT),
            ) as resp:
                if resp.status_code != 200:
                    print(
                        f"[task_stream] Failed for {worker_id}: HTTP {resp.status_code} {resp.text}"
                    )
                    time.sleep(STREAM_RECONNECT_DELAY)
                    continue

                for event_type, _data in iter_sse_events(resp):
                    if event_type != "task_available":
                        continue

                    while True:
                        task = try_pop_task(worker_id, worker_env)
                        if not task:
                            break
                        execute_task(worker_id, worker_env, task, worker_status)
        except Exception as e:
            print(f"[run_worker] {worker_id} loop error: {e}")
            time.sleep(STREAM_RECONNECT_DELAY)


def executor_main():
    worker_cfg = CONFIG.get("worker", {})
    pools = worker_cfg.get("pools")

    # Backward compatibility for old config format
    if not pools:
        pools = [
            {
                "env": worker_cfg.get("env", "prod"),
                "prefix": worker_cfg.get("prefix", "node-alpha"),
                "count": worker_cfg.get("count", 3),
            }
        ]

    threads = []
    for pool in pools:
        env = pool.get("env", "prod")
        prefix = pool.get("prefix", f"node-{env}")
        count = int(pool.get("count", 0))
        for i in range(count):
            worker_id = f"{prefix}-{i + 1}"
            t = threading.Thread(target=run_worker, args=(worker_id, env))
            t.daemon = True
            t.start()
            threads.append(t)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    executor_main()
