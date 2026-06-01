import json
import os
import sys
import time
from typing import Any, Callable

import requests


class TestFailure(Exception):
    pass


class SecurityTestRunner:
    def __init__(self) -> None:
        self.workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.runtime_config_path = os.path.join(self.workspace_root, "runtime", "config.json")
        self.run_id = str(int(time.time() * 1000))
        self.session = requests.Session()

        django_port = 8000
        try:
            with open(self.runtime_config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                django_port = int(cfg.get("mcp", {}).get("django_port", 8000))
        except Exception:
            django_port = 8000

        self.base_url = f"http://127.0.0.1:{django_port}"
        self.mcp_url = f"{self.base_url}/mcp/"
        self.admin_tools_url = f"{self.base_url}/api/admin/tools"
        self.admin_execs_url = f"{self.base_url}/api/admin/executions"
        self.default_timeout = 30

    def _assert(self, condition: bool, message: str) -> None:
        if not condition:
            raise TestFailure(message)

    def _request_json(self, method: str, url: str, expected_status: int | None = None, **kwargs: Any) -> dict:
        try:
            resp = self.session.request(method=method, url=url, timeout=20, **kwargs)
        except requests.RequestException as e:
            raise TestFailure(f"HTTP request failed: {method} {url} -> {e}") from e

        try:
            data = resp.json()
        except ValueError as e:
            raise TestFailure(f"Non-JSON response: {method} {url} -> {resp.text[:300]}") from e

        if expected_status is not None:
            if resp.status_code != expected_status:
                raise TestFailure(
                    f"Unexpected status code: {method} {url} -> {resp.status_code}, expected {expected_status}, body={data}"
                )
        elif resp.status_code >= 400:
            raise TestFailure(f"HTTP error: {method} {url} -> {resp.status_code}, body={data}")

        return data

    def _mcp_request(self, method: str, params: dict | None = None) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        return self._request_json("POST", self.mcp_url, json=payload)

    def _mcp_initialize(self) -> None:
        self._mcp_request("initialize")
        self._mcp_request("notifications/initialized")

    def _unique_tool_id(self, prefix: str) -> str:
        return f"{prefix}_{self.run_id}"

    def _create_tool(self, tool_id: str, description: str) -> None:
        payload = {
            "id": tool_id,
            "name": tool_id,
            "description": description,
            "operator": "security_test",
        }
        self._request_json("POST", self.admin_tools_url, expected_status=201, json=payload)

    def _create_version(self, tool_id: str, code: str, entry_point: str = "run", schema: dict | None = None) -> int:
        if schema is None:
            schema = {"type": "object", "properties": {}}
        payload = {
            "code": code,
            "entry_point": entry_point,
            "schema": schema,
            "status": "draft",
            "message": "security test version",
        }
        data = self._request_json(
            "POST",
            f"{self.admin_tools_url}/{tool_id}/versions",
            expected_status=201,
            json=payload,
        )
        return int(data["version"])

    def _release_version(self, tool_id: str, version: int, environment: str = "prod") -> None:
        payload = {"environment": environment, "version": version}
        self._request_json(
            "POST",
            f"{self.admin_tools_url}/{tool_id}/release",
            expected_status=200,
            json=payload,
        )

    def _run_test(self, tool_id: str, arguments: dict, version: int | None = None) -> str:
        payload: dict[str, Any] = {"arguments": arguments}
        if version is not None:
            payload["version"] = version
        data = self._request_json(
            "POST",
            f"{self.admin_tools_url}/{tool_id}/run-test",
            expected_status=201,
            json=payload,
        )
        return str(data["execution_id"])

    def _poll_execution(self, execution_id: str, timeout_sec: int = 30) -> dict:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            data = self._request_json("GET", f"{self.admin_execs_url}/{execution_id}")
            status = data.get("status")
            if status in ["success", "error"]:
                return data
            time.sleep(0.5)
        raise TestFailure(f"Execution polling timeout: {execution_id}")

    def _mcp_call(self, tool_name: str, arguments: dict) -> dict:
        res = self._mcp_request("tools/call", {"name": tool_name, "arguments": arguments})
        if "error" in res:
            raise TestFailure(f"MCP tools/call returned JSON-RPC error: {res['error']}")
        if "result" not in res:
            raise TestFailure(f"Invalid MCP tools/call response: {res}")
        return res["result"]

    def _extract_content_text(self, mcp_result: dict) -> str:
        texts = []
        for item in mcp_result.get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(str(item.get("text", "")))
        return "\n".join(texts)

    def _extract_first_payload(self, mcp_result: dict) -> Any:
        content = mcp_result.get("content", [])
        if not content:
            return None
        first_text = str(content[0].get("text", ""))
        try:
            return json.loads(first_text)
        except Exception:
            return first_text

    # TC-S1
    def test_lifecycle(self) -> None:
        tool_id = self._unique_tool_id("tc_s1")
        self._create_tool(tool_id, "TC-S1 lifecycle")

        code = """def run(args):
    value = int(args.get('value', 0))
    return {'value': value, 'doubled': value * 2}
"""
        version = self._create_version(
            tool_id,
            code,
            entry_point="run",
            schema={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
            },
        )
        self._release_version(tool_id, version, "prod")

        call_result = self._mcp_call(tool_id, {"value": 7})
        self._assert(call_result.get("isError") is False, "TC-S1 tools/call should be success")
        payload = self._extract_first_payload(call_result)
        self._assert(isinstance(payload, dict), f"TC-S1 payload should be dict, got: {payload}")
        self._assert(payload.get("doubled") == 14, f"TC-S1 doubled mismatch: {payload}")

        execution_id = self._run_test(tool_id, {"value": 5}, version=version)
        detail = self._poll_execution(execution_id, timeout_sec=self.default_timeout)
        self._assert(detail.get("status") == "success", f"TC-S1 run-test should be success: {detail}")
        self._assert(detail.get("output", {}).get("doubled") == 10, f"TC-S1 output mismatch: {detail}")

    # TC-S2
    def test_multi_version_isolation(self) -> None:
        tool_id = self._unique_tool_id("tc_s2")
        self._create_tool(tool_id, "TC-S2 multi-version")

        code_v1 = """def run(args):
    return {'version': 'v1', 'value': 1}
"""
        code_v2 = """def run(args):
    return {'version': 'v2', 'value': 2}
"""

        v1 = self._create_version(tool_id, code_v1)
        v2 = self._create_version(tool_id, code_v2)

        self._release_version(tool_id, v1, "prod")
        r1 = self._mcp_call(tool_id, {})
        p1 = self._extract_first_payload(r1)
        self._assert(p1.get("version") == "v1", f"TC-S2 v1 call mismatch: {p1}")

        self._release_version(tool_id, v2, "prod")
        r2 = self._mcp_call(tool_id, {})
        p2 = self._extract_first_payload(r2)
        self._assert(p2.get("version") == "v2", f"TC-S2 v2 call mismatch: {p2}")

        self._release_version(tool_id, v1, "prod")
        r3 = self._mcp_call(tool_id, {})
        p3 = self._extract_first_payload(r3)
        self._assert(p3.get("version") == "v1", f"TC-S2 rollback-to-v1 mismatch: {p3}")

    # TC-S3
    def test_illegal_file_read(self) -> None:
        tool_id = self._unique_tool_id("tc_s3")
        self._create_tool(tool_id, "TC-S3 illegal read")

        code = """def run(args):
    with open('requirements.txt', 'r', encoding='utf-8') as f:
        return f.read()
"""
        version = self._create_version(tool_id, code)
        self._release_version(tool_id, version, "prod")

        result = self._mcp_call(tool_id, {})
        self._assert(result.get("isError") is True, f"TC-S3 should fail: {result}")
        text = self._extract_content_text(result)
        self._assert(
            any(k in text for k in ["TypeError", "NoneType", "open", "Security Sandbox Denied"]),
            f"TC-S3 error text not as expected: {text}",
        )

    # TC-S4
    def test_illegal_file_write(self) -> None:
        tool_id = self._unique_tool_id("tc_s4")
        self._create_tool(tool_id, "TC-S4 illegal write")

        filename = f"hack_{self.run_id}.txt"
        code = f"""def run(args):
    with open('{filename}', 'w', encoding='utf-8') as f:
        f.write('malicious content')
    return 'ok'
"""
        version = self._create_version(tool_id, code)
        self._release_version(tool_id, version, "prod")

        result = self._mcp_call(tool_id, {})
        self._assert(result.get("isError") is True, f"TC-S4 should fail: {result}")

        root_path = os.path.join(self.workspace_root, filename)
        runtime_path = os.path.join(self.workspace_root, "runtime", filename)
        self._assert(not os.path.exists(root_path), f"TC-S4 unexpected file created: {root_path}")
        self._assert(not os.path.exists(runtime_path), f"TC-S4 unexpected file created: {runtime_path}")

    # TC-S5
    def test_restricted_module_import(self) -> None:
        tool_id = self._unique_tool_id("tc_s5")
        self._create_tool(tool_id, "TC-S5 restricted import")

        restricted_cases = [
            ("os", "return os.listdir('.')"),
            ("socket", "return socket.gethostname()"),
        ]

        for module_name, body in restricted_cases:
            code = f"""def run(args):
    import {module_name}
    {body}
"""
            version = self._create_version(tool_id, code)
            self._release_version(tool_id, version, "prod")

            result = self._mcp_call(tool_id, {})
            self._assert(result.get("isError") is True, f"TC-S5 should fail for {module_name}: {result}")
            text = self._extract_content_text(result)
            self._assert(
                ("Security Sandbox Denied" in text) and (module_name in text),
                f"TC-S5 error text not as expected for {module_name}: {text}",
            )

    # TC-S6
    def test_command_execution_block(self) -> None:
        tool_id = self._unique_tool_id("tc_s6")
        self._create_tool(tool_id, "TC-S6 command execution block")

        code = """def run(args):
    import subprocess
    return subprocess.getoutput('echo hello')
"""
        version = self._create_version(tool_id, code)
        self._release_version(tool_id, version, "prod")

        result = self._mcp_call(tool_id, {})
        self._assert(result.get("isError") is True, f"TC-S6 should fail: {result}")
        text = self._extract_content_text(result)
        self._assert(
            ("Security Sandbox Denied" in text) or ("subprocess" in text),
            f"TC-S6 error text not as expected: {text}",
        )

    # TC-S7
    def test_global_state_isolation(self) -> None:
        tool_id = self._unique_tool_id("tc_s7")
        self._create_tool(tool_id, "TC-S7 global state")

        code_v1 = """counter = 0

def run(args):
    global counter
    counter += 1
    return {'counter': counter, 'version': 'a'}
"""
        code_v2 = """def run(args):
    return {'version': 'b'}
"""

        v1 = self._create_version(tool_id, code_v1)
        v2 = self._create_version(tool_id, code_v2)

        self._release_version(tool_id, v1, "prod")
        r1 = self._extract_first_payload(self._mcp_call(tool_id, {}))
        r2 = self._extract_first_payload(self._mcp_call(tool_id, {}))
        self._assert(r1.get("counter") == 1, f"TC-S7 first counter mismatch: {r1}")
        self._assert(r2.get("counter") == 1, f"TC-S7 second counter mismatch: {r2}")

        self._release_version(tool_id, v2, "prod")
        r3 = self._extract_first_payload(self._mcp_call(tool_id, {}))
        self._assert(r3.get("version") == "b", f"TC-S7 v2 result mismatch: {r3}")

    # TC-S8
    def test_exception_recovery(self) -> None:
        tool_id = self._unique_tool_id("tc_s8")
        self._create_tool(tool_id, "TC-S8 exception recovery")

        bad_code = """def run(args):
    raise RuntimeError('boom')
"""
        good_code = """def run(args):
    return {'ok': True, 'message': 'recovered'}
"""

        bad_v = self._create_version(tool_id, bad_code)
        good_v = self._create_version(tool_id, good_code)

        self._release_version(tool_id, bad_v, "prod")
        bad_result = self._mcp_call(tool_id, {})
        self._assert(bad_result.get("isError") is True, f"TC-S8 bad run should fail: {bad_result}")

        self._release_version(tool_id, good_v, "prod")
        good_result = self._mcp_call(tool_id, {})
        self._assert(good_result.get("isError") is False, f"TC-S8 recovery run should pass: {good_result}")
        payload = self._extract_first_payload(good_result)
        self._assert(payload.get("ok") is True, f"TC-S8 recovery payload mismatch: {payload}")

    # TC-A1
    def test_allowed_module_import_success(self) -> None:
        tool_id = self._unique_tool_id("tc_a1")
        self._create_tool(tool_id, "TC-A1 allowed module import")

        code = """def run(args):
    import math
    import json
    import re
    import random
    import time
    from collections import Counter
    import requests

    text = str(args.get('text', 'Hello hello world'))
    numbers = args.get('numbers', [1, 2, 3, 4])

    words = re.findall(r'[a-z]+', text.lower())
    counter = Counter(words)

    random.seed(7)
    req = requests.Request('GET', 'https://example.com/api', params={'q': 'toolflow'})
    prepared = req.prepare()

    return {
        'ok': True,
        'sqrt_9': math.sqrt(9),
        'word_top': counter.most_common(1),
        'sum': sum(numbers),
        'json_preview': json.dumps({'count': len(words)}, ensure_ascii=False),
        'randint': random.randint(1, 10),
        'year': int(time.strftime('%Y')),
        'final_url': prepared.url,
    }
"""
        version = self._create_version(tool_id, code)
        self._release_version(tool_id, version, "prod")

        result = self._mcp_call(tool_id, {"text": "Hello hello world", "numbers": [2, 3, 5]})
        self._assert(result.get("isError") is False, f"TC-A1 should pass: {result}")
        payload = self._extract_first_payload(result)
        self._assert(isinstance(payload, dict), f"TC-A1 payload should be dict: {payload}")
        self._assert(payload.get("ok") is True, f"TC-A1 ok mismatch: {payload}")
        self._assert(float(payload.get("sqrt_9", 0)) == 3.0, f"TC-A1 sqrt mismatch: {payload}")
        self._assert(int(payload.get("sum", -1)) == 10, f"TC-A1 sum mismatch: {payload}")
        self._assert(str(payload.get("final_url", "")).startswith("https://example.com/api"), f"TC-A1 url mismatch: {payload}")

    def run_all(self) -> int:
        print("=== Security Automation Test Runner ===")
        print(f"Target MCP URL: {self.mcp_url}")
        print(f"Target Admin URL: {self.admin_tools_url}")

        self._mcp_initialize()

        cases: list[tuple[str, Callable[[], None]]] = [
            ("TC-S1", self.test_lifecycle),
            ("TC-S2", self.test_multi_version_isolation),
            ("TC-S3", self.test_illegal_file_read),
            ("TC-S4", self.test_illegal_file_write),
            ("TC-S5", self.test_restricted_module_import),
            ("TC-S6", self.test_command_execution_block),
            ("TC-S7", self.test_global_state_isolation),
            ("TC-S8", self.test_exception_recovery),
            ("TC-A1", self.test_allowed_module_import_success),
        ]

        results: list[tuple[str, str, str]] = []
        for case_id, fn in cases:
            start = time.time()
            try:
                fn()
                elapsed_ms = int((time.time() - start) * 1000)
                results.append((case_id, "PASS", f"{elapsed_ms} ms"))
                print(f"[PASS] {case_id} ({elapsed_ms} ms)")
            except Exception as e:
                elapsed_ms = int((time.time() - start) * 1000)
                results.append((case_id, "FAIL", f"{elapsed_ms} ms | {e}"))
                print(f"[FAIL] {case_id} ({elapsed_ms} ms) -> {e}")

        print("\n=== Summary ===")
        for case_id, status, detail in results:
            print(f"{case_id:6s} | {status:4s} | {detail}")

        failed = [r for r in results if r[1] == "FAIL"]
        print(f"\nTotal: {len(results)}, Passed: {len(results) - len(failed)}, Failed: {len(failed)}")
        return 1 if failed else 0


if __name__ == "__main__":
    runner = SecurityTestRunner()
    sys.exit(runner.run_all())
