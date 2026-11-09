"""One tiny configurable microservice used for every ShopLite service.

NAME     service name
REQUIRE  dependency rule, e.g. "auth,db|cache" = auth AND (db OR cache)

A background thread checks dependencies every second and caches the result,
so /health answers instantly and failures propagate cleanly up the chain.
"""
import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAME = os.environ.get("NAME", "svc")
GROUPS = [[d.strip() for d in g.split("|") if d.strip()]
          for g in os.environ.get("REQUIRE", "").split(",") if g.strip()]
state = {"healthy": not GROUPS, "deps": {}}


def dep_up(host: str) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:8000/health", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def checker():
    while True:
        deps = {d: dep_up(d) for g in GROUPS for d in g}
        state["deps"] = deps
        state["healthy"] = all(any(deps[d] for d in g) for g in GROUPS)
        time.sleep(1)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        ok = state["healthy"]
        body = json.dumps({"service": NAME, "healthy": ok, "deps": state["deps"]}).encode()
        self.send_response(200 if ok or self.path != "/health" else 503)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=checker, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
