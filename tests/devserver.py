"""Stdlib stand-in for uvicorn, used only to UI-test in a sandbox without FastAPI."""
import sys, os, re, json, http.server, mimetypes
sys.path.insert(0, "/tmp/stub"); sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DCS_DB", "/tmp/ui.db")
from backend import main
from backend import engine
main._startup()
routes = []
for (m, p), f in main.app.routes.items():
    routes.append((m, re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", p) + "$"), f, p))
import inspect
class H(http.server.BaseHTTPRequestHandler):
    def log_message(s,*a): pass
    def handle_any(s, m):
        path = s.path.split("?")[0]; qs = dict(x.split("=",1) for x in s.path.split("?")[1].split("&")) if "?" in s.path else {}
        n = int(s.headers.get("Content-Length") or 0); body = json.loads(s.rfile.read(n) or b"{}") if n else {}
        if path.startswith("/api"):
            for mm, rx, f, p in routes:
                g = rx.match(path)
                if mm == m and g:
                    try:
                        sig = inspect.signature(f); kw = dict(g.groupdict())
                        for name, par in sig.parameters.items():
                            if name in kw: 
                                if par.annotation is int: kw[name]=int(kw[name])
                                continue
                            ann = par.annotation
                            if inspect.isclass(ann) and issubclass(ann, main.BaseModel): kw[name] = ann(**body)
                            elif name in qs: kw[name] = __import__("urllib.parse").parse.unquote(qs[name])
                        out = f(**kw)
                        data = out if isinstance(out, (dict, list)) else None
                        if data is None: s.send_response(200); s.send_header("Content-Type","text/html"); s.end_headers(); return
                        raw = json.dumps(data, default=str).encode(); s.send_response(200)
                    except engine.GameError as e:
                        raw = json.dumps({"detail": str(e)}).encode(); s.send_response(e.code)
                    s.send_header("Content-Type","application/json"); s.end_headers(); s.wfile.write(raw); return
            s.send_response(404); s.end_headers(); return
        fp = os.path.join(main.FRONTEND, "index.html" if path == "/" else path.lstrip("/"))
        if os.path.isfile(fp):
            s.send_response(200); s.send_header("Content-Type", mimetypes.guess_type(fp)[0] or "text/plain"); s.end_headers(); s.wfile.write(open(fp,"rb").read())
        else: s.send_response(404); s.end_headers()
    do_GET = lambda s: s.handle_any("GET"); do_POST = lambda s: s.handle_any("POST"); do_DELETE = lambda s: s.handle_any("DELETE")
http.server.ThreadingHTTPServer(("127.0.0.1", 8099), H).serve_forever()
