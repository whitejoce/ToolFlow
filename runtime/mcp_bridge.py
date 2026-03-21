import sys
import json
import requests
import argparse
import threading
import queue
import uuid
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 读取同目录下的 config.json 以自动拉取端口配置
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
        mcp_conf = config.get("mcp", {})
        django_port = mcp_conf.get("django_port", 8000)
        DEFAULT_SSE_PORT = mcp_conf.get("bridge_sse_port", 8001)
        DJANGO_MCP_URL = f"http://127.0.0.1:{django_port}/mcp/"
except Exception as e:
    DJANGO_MCP_URL = "http://127.0.0.1:8000/mcp/"
    DEFAULT_SSE_PORT = 8001
    print(f"Warning: Failed to load config.json: {e}, using defaults.", file=sys.stderr)

def run_stdio():
    # 强制 stdout 输出时不带缓冲区，防止阻塞客户端读取
    sys.stdout.reconfigure(line_buffering=True)
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
                
            payload = json.loads(line)
            resp = requests.post(DJANGO_MCP_URL, json=payload, timeout=30)

            # JSON-RPC notification has no id; do not emit response on stdio/SSE stream.
            if payload.get("id") is None:
                continue

            if resp.status_code == 200:
                resp_j = resp.json()
                # Only forward valid JSON-RPC messages to avoid client parser errors.
                if isinstance(resp_j, dict) and resp_j.get("jsonrpc") == "2.0":
                    out_data = json.dumps(resp_j, ensure_ascii=False)
                    sys.stdout.write(out_data + "\n")
            else:
                err_resp = {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32000, "message": f"Transport Error: HTTP {resp.status_code}"}}
                sys.stdout.write(json.dumps(err_resp) + "\n")
        except json.JSONDecodeError:
            continue
        except Exception as e:
            print(f"Bridge Error: {str(e)}", file=sys.stderr)
            sys.stderr.flush()

class SSEHandler(BaseHTTPRequestHandler):
    sessions = {}

    def do_OPTIONS(self):
        # 处理 CORS 预检请求（如果在网页测试等情况）
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/sse':
            session_id = str(uuid.uuid4())
            q = queue.Queue()
            self.sessions[session_id] = q
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # 服务端第一步：推送 endpoint 事件告知客户端发消息去哪里
            endpoint_msg = f"event: endpoint\ndata: http://127.0.0.1:{self.server.server_address[1]}/message?session_id={session_id}\n\n"
            self.wfile.write(endpoint_msg.encode('utf-8'))
            self.wfile.flush()
            
            try:
                # 阻塞循环读取队列并推流
                while True:
                    msg = q.get()
                    if msg is None:
                        break
                    # MCP 标准：事件类型为 message，数据为 JSONRPC 返回值
                    sse_msg = f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
                    self.wfile.write(sse_msg.encode('utf-8'))
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                self.sessions.pop(session_id, None)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path.startswith('/message?session_id='):
            session_id = self.path.split('=')[1]
            if session_id not in self.sessions:
                self.send_response(400)
                self.end_headers()
                return
                
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            payload = json.loads(post_data)
            
            # MCP SSE 协议：立即返回 202 Accepted
            self.send_response(202)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # 新开线程去同步向 Django 请求（避免阻塞主 ThreadingHTTPServer 处理进程）
            def fetch_django():
                try:
                    resp = requests.post(DJANGO_MCP_URL, json=payload, timeout=30)
                    # JSON-RPC notification has no id; do not emit response on SSE stream.
                    if payload.get("id") is None:
                        return

                    if resp.status_code == 200:
                        resp_j = resp.json()
                        # Only forward valid JSON-RPC messages to avoid client parser errors.
                        if isinstance(resp_j, dict) and resp_j.get("jsonrpc") == "2.0":
                            self.sessions[session_id].put(resp_j)
                    else:
                        self.sessions[session_id].put({
                            "jsonrpc": "2.0",
                            "id": payload.get("id"),
                            "error": {"code": -32000, "message": f"Bridge Http Error {resp.status_code}"}
                        })
                except Exception as e:
                    self.sessions[session_id].put({
                        "jsonrpc": "2.0",
                        "id": payload.get("id"),
                        "error": {"code": -32000, "message": str(e)}
                    })
                    
            threading.Thread(target=fetch_django).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # 禁用默认的无意义请求输出，避免 stdout 污染
        pass


def run_sse(port):
    # 使用 ThreadingHTTPServer 支持并发长连接的建立
    server = ThreadingHTTPServer(('0.0.0.0', port), SSEHandler)
    print(f"\n MCP Bridge Server running!")
    server.serve_forever()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP Bridge (STDIO / SSE Gateway)")
    parser.add_argument("--sse", nargs='?', const=DEFAULT_SSE_PORT, type=int, help="Run as SSE server on specified port (defaults to config.json setting)", metavar="PORT")
    parser.add_argument("--django-url", type=str, default=DJANGO_MCP_URL, help="Backing Django MCP endpoint")
    args = parser.parse_args()
    
    global_django_url = args.django_url
    DJANGO_MCP_URL = global_django_url
    
    if args.sse is not None:
        run_sse(args.sse)
    else:
        run_stdio()
