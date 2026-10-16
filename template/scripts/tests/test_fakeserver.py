#!/usr/bin/env python3
"""Tests for support/fakeserver.py: the local fake HTTP server tests use instead of a
real service. Every request here goes to 127.0.0.1; nothing leaves the machine."""
import http.client
import json
import os
import socket
import sys
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "support"))
import fakeserver as fs  # noqa: E402
from fakeserver import FakeServer, Reply, Seq  # noqa: E402


def get(url, **kw):
    return fs.open_url(url, **kw)


class TestRouting(unittest.TestCase):
    def setUp(self):
        self.srv = FakeServer().start()
        self.addCleanup(self.srv.stop)

    def test_dict_route_is_served_as_json(self):
        self.srv.routes["/api/me"] = {"name": "dev1"}
        status, headers, body = get(self.srv.url_for("/api/me"))
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body), {"name": "dev1"})

    def test_list_route_and_query_string_is_ignored_for_lookup(self):
        self.srv.routes["/items"] = [1, 2]
        status, _, body = get(self.srv.url_for("/items?page=2"))
        self.assertEqual((status, json.loads(body)), (200, [1, 2]))
        self.assertEqual(self.srv.requests[0].query, {"page": ["2"]})
        self.assertEqual(self.srv.requests[0].target, "/items?page=2")

    def test_unknown_path_is_404_json(self):
        status, _, body = get(self.srv.url_for("/nope"))
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "no route for GET /nope"})

    def test_reply_with_status_headers_and_text_or_bytes_body(self):
        self.srv.routes["/text"] = Reply(201, "plain", {"Content-Type": "text/plain"})
        self.srv.routes["/bytes"] = Reply(200, b"\x00\x01", {"Content-Type": "application/octet-stream"})
        self.srv.routes["/empty"] = Reply(204)
        status, headers, body = get(self.srv.url_for("/text"))
        self.assertEqual((status, headers["Content-Type"], body), (201, "text/plain", b"plain"))
        self.assertEqual(get(self.srv.url_for("/bytes"))[2], b"\x00\x01")
        status, _, body = get(self.srv.url_for("/empty"))
        self.assertEqual((status, body), (204, b""))

    def test_callable_route_sees_the_request(self):
        self.srv.routes["/echo"] = lambda req: {"q": req.query.get("q", [""])[0]}
        self.assertEqual(json.loads(get(self.srv.url_for("/echo?q=hi"))[2]), {"q": "hi"})

    def test_callable_may_return_a_reply(self):
        self.srv.routes["/gone"] = lambda req: Reply(410, {"error": "gone"})
        self.assertEqual(get(self.srv.url_for("/gone"))[0], 410)

    def test_seq_serves_in_turn_and_repeats_the_last(self):
        self.srv.routes["/retry"] = Seq(Reply(429, headers={"Retry-After": "0"}),
                                        Reply(200, {"ok": True}))
        statuses = [get(self.srv.url_for("/retry"))[0] for _ in range(3)]
        self.assertEqual(statuses, [429, 200, 200])

    def test_seq_may_hold_plain_bodies_and_callables(self):
        self.srv.routes["/s"] = Seq({"n": 1}, lambda req: {"n": 2})
        self.assertEqual([json.loads(get(self.srv.url_for("/s"))[2])["n"] for _ in range(3)],
                         [1, 2, 2])

    def test_method_specific_route_wins_over_path_route(self):
        self.srv.routes["/thing"] = {"via": "any"}
        self.srv.routes[("POST", "/thing")] = Reply(201, {"via": "post"})
        self.assertEqual(json.loads(get(self.srv.url_for("/thing"))[2]), {"via": "any"})
        status, _, body = get(self.srv.url_for("/thing"), data=b"{}", method="POST")
        self.assertEqual((status, json.loads(body)), (201, {"via": "post"}))

    def test_method_only_route_is_404_for_other_methods(self):
        self.srv.routes[("DELETE", "/thing")] = Reply(204)
        self.assertEqual(get(self.srv.url_for("/thing"))[0], 404)
        self.assertEqual(get(self.srv.url_for("/thing"), method="DELETE")[0], 204)

    def test_head_gets_headers_and_no_body(self):
        self.srv.routes["/h"] = {"a": 1}
        status, headers, body = get(self.srv.url_for("/h"), method="HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(headers["Content-Length"], str(len(json.dumps({"a": 1}))))

    def test_a_failing_route_answers_500_and_is_recorded(self):
        def boom(req):
            raise RuntimeError("route bug")
        self.srv.routes["/boom"] = boom
        status, _, body = get(self.srv.url_for("/boom"))
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body), {"error": "route failed: RuntimeError"})
        self.assertEqual(len(self.srv.errors), 1)
        self.assertIsInstance(self.srv.errors[0], RuntimeError)

    def test_a_body_that_cannot_be_encoded_answers_500_and_is_recorded(self):
        self.srv.routes["/call"] = lambda req: {"when": {1, 2}}
        self.srv.routes["/reply"] = Reply(200, {"when": {1, 2}})
        self.srv.routes["/seq"] = Seq(object())
        for path in ("/call", "/reply", "/seq"):
            with self.subTest(path=path):
                status, _, body = get(self.srv.url_for(path))
                self.assertEqual(status, 500)
                self.assertEqual(json.loads(body), {"error": "route failed: TypeError"})
        self.assertEqual([type(e) for e in self.srv.errors], [TypeError] * 3)

    def test_answers_resolve_through_nested_seqs_and_callables(self):
        self.srv.routes["/n"] = lambda req: Seq(lambda r: Reply(202, {"deep": True}))
        status, _, body = get(self.srv.url_for("/n"))
        self.assertEqual((status, json.loads(body)), (202, {"deep": True}))

    def test_a_route_that_never_settles_answers_500(self):
        def loop(req):
            return loop
        self.srv.routes["/loop"] = loop
        self.assertEqual(get(self.srv.url_for("/loop"))[0], 500)
        self.assertIsInstance(self.srv.errors[0], RecursionError)


class TestRecording(unittest.TestCase):
    def setUp(self):
        self.srv = FakeServer({"/x": {}}).start()
        self.addCleanup(self.srv.stop)

    def test_records_method_headers_and_body(self):
        get(self.srv.url_for("/x"), data=json.dumps({"k": "v"}).encode(), method="PUT",
            headers={"Authorization": "Bearer abc", "X-Trace": "1"})
        req = self.srv.requests[-1]
        self.assertEqual((req.method, req.path), ("PUT", "/x"))
        self.assertEqual(req.header("authorization"), "Bearer abc")   # any case
        self.assertEqual(req.headers["X-Trace"], "1")
        self.assertIsNone(req.header("missing"))
        self.assertEqual(req.json(), {"k": "v"})

    def test_request_is_recorded_before_the_reply_is_sent(self):
        # No sleep: once the client has the answer, the request is in the list.
        for i in range(20):
            get(self.srv.url_for(f"/x?i={i}"))
            self.assertEqual(len(self.srv.requests), i + 1)

    def test_requests_is_a_snapshot(self):
        snap = self.srv.requests
        get(self.srv.url_for("/x"))
        self.assertEqual(snap, [])
        self.assertEqual(len(self.srv.requests), 1)

    def test_concurrent_requests_are_all_recorded(self):
        threads = [threading.Thread(target=get, args=(self.srv.url_for(f"/x?n={n}"),))
                   for n in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        got = sorted(int(r.query["n"][0]) for r in self.srv.requests)
        self.assertEqual(got, list(range(16)))

    def test_clear_forgets_requests_and_errors(self):
        get(self.srv.url_for("/x"))
        self.srv.clear()
        self.assertEqual((self.srv.requests, self.srv.errors), ([], []))

    def test_absolute_uri_request_line_is_recorded_as_a_proxy_would_see_it(self):
        with socket.create_connection(("127.0.0.1", self.srv.port), timeout=5) as s:
            s.sendall(b"GET http://svc.example.test/x?a=1 HTTP/1.1\r\n"
                      b"Host: svc.example.test\r\nConnection: close\r\n\r\n")
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        self.assertTrue(data.startswith(b"HTTP/1.1 200"))
        req = self.srv.requests[-1]
        self.assertEqual(req.target, "http://svc.example.test/x?a=1")
        self.assertEqual((req.path, req.query), ("/x", {"a": ["1"]}))


class TestGuarded(unittest.TestCase):
    def test_answers_only_with_the_expected_authorization(self):
        with FakeServer({"/me": fs.guarded("Bearer good", {"ok": True})}) as srv:
            self.assertEqual(get(srv.url_for("/me"))[0], 401)
            self.assertEqual(get(srv.url_for("/me"), headers={"Authorization": "Bearer bad"})[0], 401)
            status, _, body = get(srv.url_for("/me"), headers={"Authorization": "Bearer good"})
            self.assertEqual((status, json.loads(body)), (200, {"ok": True}))
            self.assertEqual(json.loads(get(srv.url_for("/me"))[2]), {"error": "not authenticated"})

    def test_answer_may_be_a_callable_or_reply(self):
        routes = {"/a": fs.guarded("t", lambda req: {"p": req.path}),
                  "/b": fs.guarded("t", Reply(202, {"queued": 1}))}
        with FakeServer(routes) as srv:
            self.assertEqual(json.loads(get(srv.url_for("/a"), headers={"Authorization": "t"})[2]),
                             {"p": "/a"})
            self.assertEqual(get(srv.url_for("/b"), headers={"Authorization": "t"})[0], 202)

    def test_answer_may_be_a_seq(self):
        routes = {"/r": fs.guarded("t", Seq(Reply(429, headers={"Retry-After": "0"}), {"ok": 1}))}
        auth = {"Authorization": "t"}
        with FakeServer(routes) as srv:
            self.assertEqual(get(srv.url_for("/r"))[0], 401)       # a refusal uses no turn
            self.assertEqual([get(srv.url_for("/r"), headers=auth)[0] for _ in range(3)],
                             [429, 200, 200])
            self.assertEqual(srv.errors, [])


class TestLifecycle(unittest.TestCase):
    def test_binds_loopback_on_an_ephemeral_port(self):
        with FakeServer() as a, FakeServer() as b:
            self.assertEqual(a.host, "127.0.0.1")
            self.assertTrue(a.url.startswith("http://127.0.0.1:"))
            self.assertNotEqual(a.port, 0)
            self.assertNotEqual(a.port, b.port)

    def test_stop_releases_the_port_and_is_idempotent(self):
        srv = FakeServer({"/x": {}}).start()
        port = srv.port
        get(srv.url_for("/x"))
        srv.stop()
        srv.stop()
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=2).close()

    def test_stop_returns_while_a_client_holds_a_connection_open(self):
        srv = FakeServer({"/x": {}}).start()
        idle = socket.create_connection(("127.0.0.1", srv.port), timeout=5)
        self.addCleanup(idle.close)
        done = threading.Event()
        threading.Thread(target=lambda: (srv.stop(), done.set()), daemon=True).start()
        self.assertTrue(done.wait(10), "stop() hung on an idle client")

    def test_a_keep_alive_connection_gets_no_answer_after_stop(self):
        srv = FakeServer({"/x": {}}).start()
        conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/x")
        resp = conn.getresponse()
        resp.read()
        self.assertEqual(resp.status, 200)
        self.assertFalse(resp.will_close)            # the connection stays open
        srv.stop()
        with self.assertRaises((ConnectionError, http.client.HTTPException)):
            conn.request("GET", "/x")
            conn.getresponse()
        self.assertEqual(len(srv.requests), 1)

    def test_context_manager_stops_on_error(self):
        with self.assertRaises(ValueError):
            with FakeServer() as srv:
                port = srv.port
                raise ValueError
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=2).close()

    def test_start_twice_is_an_error(self):
        srv = FakeServer().start()
        self.addCleanup(srv.stop)
        with self.assertRaises(RuntimeError):
            srv.start()

    def test_url_before_start_is_an_error(self):
        with self.assertRaises(RuntimeError):
            FakeServer().url

    def test_free_port_is_not_listening(self):
        port = fs.free_port()
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=2).close()


class TestOpenUrl(unittest.TestCase):
    def test_ignores_proxy_variables(self):
        bogus = f"http://127.0.0.1:{fs.free_port()}"
        env = {"HTTP_PROXY": bogus, "http_proxy": bogus, "ALL_PROXY": bogus, "all_proxy": bogus,
               "NO_PROXY": "", "no_proxy": ""}
        with FakeServer({"/x": {"ok": 1}}) as srv, mock.patch.dict(os.environ, env):
            self.assertEqual(get(srv.url_for("/x"))[0], 200)

    def test_http_errors_are_returned_not_raised(self):
        with FakeServer({"/x": Reply(503, {"e": 1})}) as srv:
            status, _, body = get(srv.url_for("/x"))
        self.assertEqual((status, json.loads(body)), (503, {"e": 1}))

    def test_connection_refused_raises(self):
        with self.assertRaises(urllib.error.URLError):
            get(f"http://127.0.0.1:{fs.free_port()}/x", timeout=2)


if __name__ == "__main__":
    unittest.main()
