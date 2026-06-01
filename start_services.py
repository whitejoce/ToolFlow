import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent

DJANGO_ACCESS_LOG_RE = re.compile(
    r'^\[[^\]]+\]\s+"(?:GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+.*\s+HTTP/\d\.\d"\s+\d+\s+\d+$'
)


def load_ports() -> tuple[int, int]:
    config_path = ROOT_DIR / "runtime" / "config.json"
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        mcp = data.get("mcp", {})
        django_port = int(mcp.get("django_port", 8000))
        sse_port = int(mcp.get("bridge_sse_port", 8001))
        return django_port, sse_port
    except Exception:
        return 8000, 8001


def get_npm_command() -> str | None:
    if os.name == "nt" and shutil.which("npm.cmd"):
        return "npm.cmd"
    if shutil.which("npm"):
        return "npm"
    return None


def build_child_env() -> dict[str, str]:
    child_env = os.environ.copy()
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    child_env.setdefault("PYTHONUTF8", "1")
    child_env.setdefault("PYTHONUNBUFFERED", "1")
    return child_env


def stream_output(name: str, pipe) -> None:
    for line in iter(pipe.readline, ""):
        text = line.rstrip()
        if text:
            if name == "gateway" and DJANGO_ACCESS_LOG_RE.match(text):
                continue
            print(f"[{name}] {text}")
    pipe.close()


def start_process(name: str, cmd: list[str], cwd: Path) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=build_child_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    t = threading.Thread(target=stream_output, args=(name, proc.stdout), daemon=True)
    t.start()
    return proc


def run_gateway_migrations() -> int:
    print("[ToolFlow] Applying gateway migrations...")
    proc = subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=str(ROOT_DIR / "server"),
        env=build_child_env(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    for line in output.splitlines():
        if line.strip():
            print(f"[migrate] {line}")

    if proc.returncode != 0:
        print("[ToolFlow] Gateway migrations failed. Services were not started.")

    return proc.returncode


def wait_for_gateway(port: int, timeout_seconds: float = 30.0) -> bool:
    url = f"http://127.0.0.1:{port}/api/admin/config"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if 200 <= resp.status < 500:
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.3)
    return False


def stop_all(procs: list[tuple[str, subprocess.Popen]]) -> None:
    for _, proc in procs:
        if proc.poll() is None:
            proc.terminate()

    deadline = time.time() + 5
    for _, proc in procs:
        if proc.poll() is None:
            timeout = max(0, deadline - time.time())
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    django_port, sse_port = load_ports()
    django_url = f"http://127.0.0.1:{django_port}/mcp/"
    npm_cmd = get_npm_command()

    if not npm_cmd:
        print("[ToolFlow] npm was not found in PATH. Please install Node.js/npm first.")
        return 1

    print("=" * 72)
    print("ToolFlow Dev Orchestrator")
    print("Unified startup for gateway, bridge, executor")
    print("=" * 72)

    migrate_code = run_gateway_migrations()
    if migrate_code != 0:
        return migrate_code

    gateway_service = (
        "gateway",
        [sys.executable, "-u", "manage.py", "runserver", str(django_port)],
        ROOT_DIR / "server",
    )
    dependent_services: list[tuple[str, list[str], Path]] = [
        (
            "bridge",
            [
                sys.executable,
                "-u",
                "mcp_bridge.py",
                "--sse",
                str(sse_port),
                "--django-url",
                django_url,
            ],
            ROOT_DIR / "runtime",
        ),
        (
            "executor",
            [sys.executable, "-u", "executor.py"],
            ROOT_DIR / "runtime",
        )
    ]

    print("Services:")
    print(f"  - gateway : http://127.0.0.1:{django_port}")
    print(f"  - bridge  : http://127.0.0.1:{sse_port}/sse")
    print("  - executor: background worker")
    print("  - frontend     : npm run dev")
    print()

    procs: list[tuple[str, subprocess.Popen]] = []

    def handle_signal(_signum, _frame):
        print("\n[ToolFlow] Received stop signal. Stopping all services...")
        stop_all(procs)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    name, cmd, cwd = gateway_service
    print(f"[ToolFlow] Starting {name:<8} | cwd={cwd.name}")
    proc = start_process(name, cmd, cwd)
    procs.append((name, proc))

    print(f"[ToolFlow] Waiting for gateway on http://127.0.0.1:{django_port} ...")
    if not wait_for_gateway(django_port):
        print("[ToolFlow] Gateway did not become ready in time. Stopping services.")
        stop_all(procs)
        return 1

    for name, cmd, cwd in dependent_services:
        print(f"[ToolFlow] Starting {name:<8} | cwd={cwd.name}")
        proc = start_process(name, cmd, cwd)
        procs.append((name, proc))

    print("\n[ToolFlow] All services started in this terminal. Press Ctrl+C to stop all.\n")

    while True:
        for name, proc in procs:
            code = proc.poll()
            if code is not None:
                print(f"\n[ToolFlow] Service '{name}' exited with code {code}. Stopping remaining services...")
                stop_all(procs)
                return code
        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
