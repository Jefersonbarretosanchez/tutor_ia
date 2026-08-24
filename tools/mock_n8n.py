"""Servidor mínimo para simular el webhook /clara de n8n durante pruebas locales."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        reply = f"(mock) Respuesta a: {body.get('message', '')[:50]}"
        data = {
            "agente": "Clara",
            "reply": reply,
            "momento_tipo": body.get("momento_tipo"),
            "tokens_used": 500,  # formato actual de /clara (compat shim)
        }
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 9000), Handler).serve_forever()
