"""Loopback ingestion and observation service; no remote code or shell surface."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import store
from .broker import observe


class Handler(BaseHTTPRequestHandler):
    server_version = "Faultline/1"

    def reply(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            if self.path == "/health":
                with store.connect() as db:
                    db.execute("SELECT 1")
                return self.reply(200, {"service": "ingestion", "database": "reachable"})
            parts = self.path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "runs" and parts[2] == "observations":
                return self.reply(200, observe(store.run_id(parts[1])))
            self.reply(404, {"error": "unknown route"})
        except ValueError as exc:
            self.reply(400, {"error": str(exc)})
        except Exception:
            self.reply(503, {"error": "service unavailable"})

    def do_POST(self):
        try:
            # Prevent a browser page from driving the local service cross-origin.
            if self.headers.get("Origin") or self.headers.get_content_type() != "application/json":
                return self.reply(403, {"error": "only local JSON clients are supported"})
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024*1024:
                return self.reply(413, {"error": "body budget exceeded"})
            body = json.loads(self.rfile.read(size))
            if self.path == "/runs" and body == {}:
                return self.reply(201, {"run_id": store.create()})
            parts = self.path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "runs" and parts[2] == "events" and set(body) == {"events"}:
                store.ingest(parts[1], body["events"])
                return self.reply(202, {"received": len(body["events"])})
            self.reply(400, {"error": "unsupported request"})
        except (ValueError, TypeError):
            self.reply(400, {"error": "invalid request"})
        except Exception:
            self.reply(503, {"error": "service unavailable"})

    def log_message(self, *_args):
        pass


def serve(port=0):
    store.initialize()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(json.dumps({"port": server.server_port}), flush=True)
    server.serve_forever()
