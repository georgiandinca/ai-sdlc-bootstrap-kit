import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import io, json, unittest
import mcp_server as srv


class McpProtocolTests(unittest.TestCase):
    def test_initialize(self):
        r = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(r["result"]["protocolVersion"], srv.PROTOCOL_VERSION)
        self.assertIn("tools", r["result"]["capabilities"])
        self.assertIn("serverInfo", r["result"])

    def test_tools_list_has_three(self):
        r = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in r["result"]["tools"]}
        self.assertEqual(names, {"kg_query", "kg_federated_query", "kg_trace"})

    def test_notification_no_reply(self):
        self.assertIsNone(srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_unknown_method_errors(self):
        r = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "no/such"})
        self.assertEqual(r["error"]["code"], -32601)

    def test_serve_survives_bad_json_and_replies(self):
        stdin = io.StringIO("not json\n"
                            + json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/list"}) + "\n")
        stdout = io.StringIO()
        srv.serve(stdin=stdin, stdout=stdout)
        lines = [l for l in stdout.getvalue().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)  # bad line skipped, one valid reply
        self.assertEqual(json.loads(lines[0])["id"], 9)


if __name__ == "__main__":
    unittest.main()
