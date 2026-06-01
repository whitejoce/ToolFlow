import requests
import json
import time
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        django_port = config.get("mcp", {}).get("django_port", 8000)
        MCP_URL = f"http://127.0.0.1:{django_port}/mcp/"
except Exception:
    MCP_URL = "http://127.0.0.1:8000/mcp/"

def mcp_request(method, params=None):
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": method
    }
    if params is not None:
        payload["params"] = params
        
    print(f"\n--- Request: {method} ---")
    print(json.dumps(payload, indent=2))
    
    try:
        resp = requests.post(MCP_URL, json=payload, timeout=20)
        res_json = resp.json()
        print("--- Response ---")
        print(json.dumps(res_json, indent=2))
        return res_json
    except Exception as e:
        print("Request failed:", e)
        return None

if __name__ == "__main__":
    # 1. Initialize
    mcp_request("initialize")
    mcp_request("notifications/initialized")
    
    # 2. List tools
    mcp_request("tools/list")
    
    # 3. Call tools
    mcp_request("tools/call", {
        "name": "double",
        "arguments": {"value": [10, 20, 30]}
    })
    
    mcp_request("tools/call", {
        "name": "echo",
        "arguments": {"message": "Hello from MCP JSON-RPC"}
    })
