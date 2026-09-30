import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

SERVER = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("ec_pulse_server", SERVER)
server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(server)

class MCPProtocolTests(unittest.TestCase):
    def test_initialize(self):
        r=server._handle({"jsonrpc":"2.0","id":1,"method":"initialize","params":{}})
        self.assertEqual(r["result"]["serverInfo"]["name"],"ec-pulse")
    def test_tools_list(self):
        r=server._handle({"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
        self.assertEqual(len(r["result"]["tools"]),12)
        self.assertIn("ec_product_search",{x["name"] for x in r["result"]["tools"]})
    def test_notification_semantics(self):
        self.assertIsNone(server._handle({"jsonrpc":"2.0","method":"notifications/initialized","params":{}}))
        self.assertIsNone(server._handle({"jsonrpc":"2.0","method":"notifications/cancelled","params":{}}))
        self.assertIsNone(server._handle({"jsonrpc":"2.0","method":"initialize","params":{}}))
        self.assertIsNone(server._handle({"jsonrpc":"2.0","method":"tools/list","params":{}}))
        with patch.object(server, "_call_tool", return_value={"ok": True}):
            self.assertIsNone(server._handle({"jsonrpc":"2.0","method":"tools/call","params":{"name":"ec_account","arguments":{}}}))
        self.assertIsNone(server._handle({"jsonrpc":"2.0","method":"tools/call","params":None}))
        self.assertIsNone(server._handle({"jsonrpc":"2.0","method":"tools/call","params":{"name":"nope","arguments":{}}}))

    def test_ping(self):
        self.assertEqual(server._handle({"jsonrpc":"2.0","id":8,"method":"ping","params":{}}), {"jsonrpc":"2.0","id":8,"result":{}})
        self.assertIsNone(server._handle({"jsonrpc":"2.0","method":"ping","params":{}}))
    def test_unknown_method(self):
        r=server._handle({"jsonrpc":"2.0","id":3,"method":"nope","params":{}})
        self.assertEqual(r["error"]["code"],-32601)
    def test_unknown_tool(self):
        r=server._handle({"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"nope","arguments":{}}})
        self.assertEqual(r["error"]["code"],-32602)
    def test_invalid_request(self):
        r=server._handle({"jsonrpc":"1.0","id":5,"method":"initialize"})
        self.assertEqual(r["error"]["code"],-32600)
    def test_parse_error(self):
        with patch("sys.stdin",iter(["{broken\\n"])),patch("sys.stdout") as out:
            server.main()
            emitted=out.write.call_args.args[0]
        self.assertEqual(json.loads(emitted)["error"]["code"],-32700)

class ValidationTests(unittest.TestCase):
    def test_empty_query(self):
        with self.assertRaises(ValueError): server._validate_args("ec_product_search",{"query":""})
    def test_invalid_url(self):
        with self.assertRaises(ValueError): server._validate_url("not-a-url")
    def test_local_and_private_urls_rejected(self):
        for url in [
            "http://localhost:8080/x",
            "http://127.0.0.1:8080/x",
            "http://10.0.0.1/x",
            "http://172.16.0.1/x",
            "http://192.168.1.1/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/x",
            "http://[fc00::1]/x",
        ]:
            with self.assertRaises(ValueError, msg=url):
                server._validate_url(url)
    def test_compare_minimum(self):
        with self.assertRaises(ValueError): server._validate_args("ec_product_compare",{"urls":["https://example.com"]})
    def test_uuid_validation(self):
        for name in ("ec_monitor_history", "ec_monitor_opportunity", "ec_research_opportunity"):
            field = "run_id" if name == "ec_research_opportunity" else "monitor_id"
            with self.assertRaises(ValueError):
                server._validate_args(name, {field: "not-a-uuid"})
        valid = "12345678-1234-5678-1234-567812345678"
        self.assertEqual(server._validate_args("ec_monitor_history", {"monitor_id": valid}), {"monitor_id": valid})
        self.assertEqual(server._validate_args("ec_research_opportunity", {"run_id": valid}), {"run_id": valid})

    def test_research_runs_url_validation(self):
        with self.assertRaises(ValueError):
            server._validate_args("ec_research_runs", {"url": "http://127.0.0.1/private"})
        with self.assertRaises(ValueError):
            server._validate_args("ec_research_runs", {"url": "https://user:pass@example.com/research"})
        valid = "https://example.com/research"
        self.assertEqual(
            server._validate_args("ec_research_runs", {"url": valid, "limit": 7}),
            {"url": valid, "limit": 7},
        )

    def test_unknown_argument(self):
        with self.assertRaises(ValueError): server._validate_args("ec_account",{"api_key":"secret"})

class SecurityTests(unittest.TestCase):
    def test_key_missing(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(RuntimeError): server._api_key()
    def test_key_not_leaked(self):
        secret="TEST_SECRET_NOT_FOR_AUTH"
        with patch.dict(os.environ,{"EC_PULSE_API_KEY":secret},clear=True),patch.object(server,"_api_request",side_effect=RuntimeError("EC Pulse authentication failed (401)")):
            r=server._handle({"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"ec_account","arguments":{}}})
        self.assertNotIn(secret,r["result"]["content"][0]["text"])
    def test_no_retry(self):
        calls=[]
        def fail(*a,**k):
            calls.append(1)
            raise RuntimeError("EC Pulse rate limit exceeded (429)")
        with patch.object(server,"_api_request",side_effect=fail):
            server._handle({"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"ec_account","arguments":{}}})
        self.assertEqual(len(calls),1)
    def test_retry_after_is_reported_without_retry(self):
        from email.message import Message
        headers = Message()
        headers["Retry-After"] = "30"
        with patch.object(server, "_api_key", return_value="TEST_SECRET_NOT_FOR_AUTH"), patch.object(
            server, "urlopen", side_effect=HTTPError("https://ec-pulse-api.vercel.app/v1/account", 429, "Too Many Requests", headers, None)
        ):
            with self.assertRaisesRegex(RuntimeError, r"429.*Retry-After: 30"):
                server._api_request("GET", "/v1/account")

    def test_url_length_limit(self):
        with self.assertRaises(ValueError):
            server._validate_url("https://example.com/" + "a" * 2000)

    def test_schema_url_and_id_limits(self):
        by_name = {tool["name"]: tool for tool in server.TOOLS}
        monitor = by_name["ec_monitor_create"]["inputSchema"]["properties"]
        self.assertEqual(monitor["url"]["maxLength"], 2000)
        self.assertEqual(monitor["webhook_url"]["maxLength"], 2000)
        for name in ("ec_monitor_history", "ec_monitor_opportunity"):
            self.assertEqual(by_name[name]["inputSchema"]["properties"]["monitor_id"]["maxLength"], 200)

    def test_base_url_rejects_credentials(self):
        with patch.dict(os.environ, {"EC_PULSE_API_BASE_URL": "https://user:pass@example.com"}, clear=True):
            with self.assertRaises(RuntimeError):
                server._base_url()
        for base in ("https://example.com/api", "https://example.com/?x=1", "https://example.com/#x"):
            with patch.dict(os.environ, {"EC_PULSE_API_BASE_URL": base}, clear=True):
                with self.assertRaises(RuntimeError):
                    server._base_url()

    def test_signature(self):
        self.assertEqual(len(server._sign("secret","1700000000","POST","/v1/products/search",b"{}")),71)

if __name__=="__main__":
    unittest.main()
