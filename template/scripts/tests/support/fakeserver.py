#!/usr/bin/env python3
"""A local fake HTTP server for tests: canned answers, recorded requests, no network.

    with FakeServer({"/api/me": {"name": "dev1"}}) as srv:
        status, headers, body = open_url(srv.url_for("/api/me"),
                                         headers={"Authorization": "Bearer t"})
        srv.requests[0].header("authorization")          # "Bearer t"

It listens on 127.0.0.1 only, on a port the system picks, in a background thread.
`stop()` (or leaving the `with` block) shuts it down and frees the port.

A route key is a path without the query string (`"/api/me"`), or `(METHOD, path)`,
which wins over the bare path for that method. A route value is one of:

- a dict or list: served as JSON with status 200;
- a `Reply(status, body, headers)`: body is JSON-encoded unless it is str or bytes;
- a callable `f(request) -> Reply | dict | list | str | bytes`, for answers that depend
  on the request;
- `Seq(a, b, ...)`: each request gets the next answer, the last one repeating, e.g.
  `Seq(Reply(429, headers={"Retry-After": "0"}), Reply(200, {...}))`.

`guarded(expected_authorization, answer)` answers only when the request carries that
Authorization header, else `DENIED` (401). An unknown route answers 404, and a route
that raises answers 500 and keeps the exception in `errors`; both bodies are JSON
`{"error": ...}`. A request is recorded before its answer is sent, so a test that has
the answer can read it from `requests` without waiting. Absolute-URI request lines
(as sent to a proxy) are recorded too: `target` is the raw request target, `path` its
path part. `routes` may be changed while the server runs.

`open_url()` is a small client for tests that ignores proxy variables; `free_port()`
gives a port nothing listens on (for connection-refused tests). Stdlib only; Python 3.9+.

Adapted from Emil Dan's fork of this kit (MIT).
"""
from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

HOST = "127.0.0.1"
HANDLER_TIMEOUT = 10        # seconds a connection may sit idle before it is dropped


@dataclass
class Reply:
    status: int = 200
    body: Any = None
    headers: Dict[str, str] = field(default_factory=dict)


class Seq:
    """Answers served in turn; the last one repeats. Safe across handler threads."""

    def __init__(self, *answers):
        if not answers:
            raise ValueError("Seq needs at least one answer")
        self.answers = list(answers)
        self._i = 0
        self._lock = threading.Lock()

    def next(self):
        with self._lock:
            answer = self.answers[min(self._i, len(self.answers) - 1)]
            self._i += 1
        return answer


@dataclass
class Request:
    method: str
    target: str
    path: str
    query: Dict[str, List[str]]
    headers: Dict[str, str]
    body: bytes

    def header(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """A header's value by name, in any case."""
        low = name.lower()
        for key, value in self.headers.items():
            if key.lower() == low:
                return value
        return default

    def json(self):
        return json.loads(self.body.decode("utf-8"))


DENIED = Reply(401, {"error": "not authenticated"})


def guarded(expected_authorization: str, answer, denied: Reply = DENIED):
    """A route that gives `answer` only to a request whose Authorization header equals
    `expected_authorization`; any other request gets `denied`."""
    def route(req: Request):
        if req.header("Authorization") != expected_authorization:
            return denied
        return answer(req) if callable(answer) and not isinstance(answer, Reply) else answer
    return route


class FakeServer:
    def __init__(self, routes: Optional[dict] = None):
        self.routes: dict = dict(routes or {})
        self.host = HOST
        self._requests: List[Request] = []
        self._errors: List[BaseException] = []
        self._lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle --
    def __enter__(self) -> "FakeServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    def start(self) -> "FakeServer":
        if self._server is not None:
            raise RuntimeError("server already started")
        self._server = _Server((HOST, 0), _handler_for(self))
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={"poll_interval": 0.05},
                                        name="fakeserver", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop serving and free the port. Safe to call twice. Handler threads are
        daemons, so a client holding a connection open cannot hold this up."""
        server, self._server = self._server, None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(5)
            self._thread = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("server not started")
        return self._server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def url_for(self, path: str) -> str:
        return self.url + (path if path.startswith("/") else "/" + path)

    # -- what happened --
    @property
    def requests(self) -> List[Request]:
        """The requests so far, oldest first (a copy)."""
        with self._lock:
            return list(self._requests)

    @property
    def errors(self) -> List[BaseException]:
        """Exceptions raised by routes (each answered 500), oldest first (a copy)."""
        with self._lock:
            return list(self._errors)

    def clear(self) -> None:
        with self._lock:
            self._requests.clear()
            self._errors.clear()

    # -- routing --
    def _record(self, req: Request) -> None:
        with self._lock:
            self._requests.append(req)

    def answer(self, req: Request) -> Reply:
        """The Reply for `req` (also usable without a socket, e.g. to test routes)."""
        route = self.routes.get((req.method, req.path), self.routes.get(req.path))
        if route is None:
            return Reply(404, {"error": f"no route for {req.method} {req.path}"})
        try:
            if isinstance(route, Seq):
                route = route.next()
            if callable(route) and not isinstance(route, Reply):
                route = route(req)
        except Exception as exc:  # a broken route must not kill the handler thread
            with self._lock:
                self._errors.append(exc)
            return Reply(500, {"error": f"route failed: {type(exc).__name__}"})
        return route if isinstance(route, Reply) else Reply(200, route)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def handle_error(self, request, client_address):
        # A client that hung up or timed out is not a test failure; anything else is
        # printed by the default handler.
        import sys
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, socket.timeout)):
            return
        super().handle_error(request, client_address)


def _encode(body) -> bytes:
    if body is None:
        return b""
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        return body.encode("utf-8")
    return json.dumps(body).encode("utf-8")


def _handler_for(owner: FakeServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = HANDLER_TIMEOUT

        def log_message(self, *args):  # keep test output quiet
            pass

        def _serve(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            parts = urllib.parse.urlsplit(self.path)
            req = Request(self.command, self.path, parts.path or "/",
                          urllib.parse.parse_qs(parts.query, keep_blank_values=True),
                          dict(self.headers.items()), body)
            owner._record(req)
            reply = owner.answer(req)
            data = _encode(reply.body)
            self.send_response(reply.status)
            headers = {"Content-Type": "application/json"}
            headers.update(reply.headers)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _serve

    return Handler


def open_url(url: str, data: Optional[bytes] = None, headers: Optional[Dict[str, str]] = None,
             method: Optional[str] = None, timeout: float = 10
             ) -> Tuple[int, Dict[str, str], bytes]:
    """(status, headers, body) for one request, with proxy variables ignored. An HTTP
    error status is returned, not raised; a connection failure raises URLError."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, data=data, headers=dict(headers or {}), method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as err:
        with err:
            return err.code, dict(err.headers.items()), err.read()


def free_port() -> int:
    """A loopback port nothing listens on right now."""
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]
