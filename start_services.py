import json
import os
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
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
    # Prefer explicit command on Windows; fallback to PATH lookup for cross-platform.
    if os.name == "nt" and shutil.which("npm.cmd"):
        return "npm.cmd"
    if shutil.which("npm"):
        return "npm"
    return None


def stream_output(name: str, pipe) -> None:
    for line in iter(pipe.readline, ""):
        text = line.rstrip()
        if text:
            # Hide noisy Django development access logs from gateway output.
            if name == "gateway" and DJANGO_ACCESS_LOG_RE.match(text):
                continue
            print(f"[{name}] {text}")
    pipe.close()


def start_process(name: str, cmd: list[str], cwd: Path) -> subprocess.Popen:
    child_env = os.environ.copy()
    # Force UTF-8 in child python processes to avoid Windows GBK emoji encoding errors.
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    child_env.setdefault("PYTHONUTF8", "1")
    child_env.setdefault("PYTHONUNBUFFERED", "1")

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    t = threading.Thread(target=stream_output, args=(name, proc.stdout), daemon=True)
    t.start()
    return proc


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
    # Ensure launcher output is UTF-8 when supported.
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

    services: list[tuple[str, list[str], Path]] = [
        (
            "gateway",
            [sys.executable, "-u", "manage.py", "runserver", str(django_port)],
            ROOT_DIR / "server",
        ),
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

    for name, cmd, cwd in services:
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
