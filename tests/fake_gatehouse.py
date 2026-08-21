"""Gatehouse falso: implementa POST /api/raspberry/access como o AccessController."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

ALLOWED = {"0012345678"}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if "tag_code" not in body:
            self.send_response(422); self.end_headers()
            self.wfile.write(b'{"message":"validation"}'); return
        ok = body["tag_code"] in ALLOWED
        resp = {"decision": "allowed" if ok else "denied", "open": ok}
        if not ok:
            resp["reason"] = "tag_nao_cadastrada"
        raw = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

HTTPServer(("127.0.0.1", 8899), H).serve_forever()
