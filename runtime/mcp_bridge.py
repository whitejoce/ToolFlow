import argparse
from contextlib import asynccontextmanager
import json
import os
import sys

import uvicorn
from fastmcp.server import create_proxy
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Mount, Route
from starlette.responses import JSONResponse, RedirectResponse


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_defaults():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as exc:
        print(f"Warning: Failed to load config.json: {exc}, using defaults.", file=sys.stderr)
        return "http://127.0.0.1:8000/mcp/", 8001

    mcp_conf = config.get("mcp", {})
    django_port = mcp_conf.get("django_port", 8000)
    bridge_port = mcp_conf.get("bridge_http_port", mcp_conf.get("bridge_sse_port", 8001))
    return f"http://127.0.0.1:{django_port}/mcp/", bridge_port


DEFAULT_DJANGO_MCP_URL, DEFAULT_BRIDGE_PORT = load_defaults()


def build_proxy(django_url: str):
    return create_proxy(django_url, name="ToolFlow MCP Bridge")


def build_http_app(django_url: str) -> Starlette:
    proxy = build_proxy(django_url)
    mcp_app = proxy.http_app(transport="streamable-http", path="/", stateless_http=True)
    sse_app = proxy.http_app(transport="sse", path="/")

    async def index(_request):
        return RedirectResponse("/mcp")

    async def health(_request):
        return JSONResponse(
            {
                "status": "ok",
                "upstream": django_url,
                "endpoints": {
                    "streamable_http": "/mcp",
                    "sse": "/sse",
                },
            }
        )

    @asynccontextmanager
    async def lifespan(_app):
        # FastMCP transport apps initialize their session managers in lifespan.
        async with mcp_app.lifespan(mcp_app), sse_app.lifespan(sse_app):
            yield

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/", index, methods=["GET"]),
            Route("/health", health, methods=["GET"]),
            Mount("/mcp", app=mcp_app),
            Mount("/sse", app=sse_app),
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    return app


def run_stdio(django_url: str):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    proxy = build_proxy(django_url)
    proxy.run(transport="stdio", show_banner=False)


def run_http(django_url: str, host: str, port: int):
    app = build_http_app(django_url)
    print(f"ToolFlow MCP Bridge running on http://{host}:{port}", file=sys.stderr)
    print(f"  Streamable HTTP: http://{host}:{port}/mcp", file=sys.stderr)
    print(f"  SSE:             http://{host}:{port}/sse", file=sys.stderr)
    print(f"  Upstream:        {django_url}", file=sys.stderr)
    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> int:
    parser = argparse.ArgumentParser(description="ToolFlow MCP Bridge (FastMCP proxy)")
    parser.add_argument("--django-url", default=DEFAULT_DJANGO_MCP_URL, help="Backing Django MCP endpoint")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=DEFAULT_BRIDGE_PORT, help="HTTP bind port")
    parser.add_argument("--stdio", action="store_true", help="Run stdio bridge explicitly")
    parser.add_argument(
        "--http",
        nargs="?",
        const=DEFAULT_BRIDGE_PORT,
        type=int,
        help="Run HTTP bridge on the specified port",
        metavar="PORT",
    )
    parser.add_argument(
        "--sse",
        nargs="?",
        const=DEFAULT_BRIDGE_PORT,
        type=int,
        help="Backward-compatible alias for --http; serves both /sse and /mcp",
        metavar="PORT",
    )
    args = parser.parse_args()

    http_port = None if args.stdio else (args.http if args.http is not None else args.sse)
    if http_port is not None:
        run_http(args.django_url, args.host, http_port)
    else:
        run_stdio(args.django_url)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
