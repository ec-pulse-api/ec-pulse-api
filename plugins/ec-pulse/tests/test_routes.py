import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("ec_pulse_server_routes", SERVER)
server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(server)


class RouteMappingTests(unittest.TestCase):
    def assert_call(self, name, args, expected_method, expected_path, expected_body=None, expected_query=None):
        with patch.object(server, "_api_request", return_value={"ok": True}) as mocked:
            result = server._call_tool(name, args)
        self.assertEqual(result, {"ok": True})
        mocked.assert_called_once()
        method, path = mocked.call_args.args[:2]
        kwargs = mocked.call_args.kwargs
        self.assertEqual(method, expected_method)
        self.assertEqual(path, expected_path)
        if expected_body is not None:
            self.assertEqual(kwargs.get("body"), expected_body)
        if expected_query is not None:
            self.assertEqual(kwargs.get("query"), expected_query)

    def test_product_search_mapping(self):
        self.assert_call("ec_product_search", {"query": "収納ボックス", "marketplaces": ["amazon"], "limit": 3}, "POST", "/v1/products/search", {"query": "収納ボックス", "marketplaces": ["amazon"], "limit": 3})

    def test_product_get_mapping(self):
        self.assert_call("ec_product_get", {"url": "https://example.com/p/1"}, "GET", "/v1/products", expected_query={"url": "https://example.com/p/1"})

    def test_product_compare_mapping(self):
        self.assert_call("ec_product_compare", {"urls": ["https://example.com/a", "https://example.com/b"]}, "POST", "/v1/products/compare", {"urls": ["https://example.com/a", "https://example.com/b"]})

    def test_research_mapping(self):
        self.assert_call("ec_research_ingest", {"urls": ["https://example.com/reviews"], "max_comments_per_url": 25}, "POST", "/v1/research/ingest", {"urls": ["https://example.com/reviews"], "max_comments_per_url": 25})

    def test_consumer_insights_mapping(self):
        self.assert_call("ec_consumer_insights", {"comments": ["too expensive"], "source": "example"}, "POST", "/v1/consumer-insights/analyze", {"comments": ["too expensive"], "source": "example"})

    def test_monitor_create_mapping(self):
        self.assert_call("ec_monitor_create", {"url": "https://example.com/p", "interval_minutes": 60, "webhook_url": "https://hooks.example.com/ec"}, "POST", "/v1/monitors", {"url": "https://example.com/p", "interval_minutes": 60, "webhook_url": "https://hooks.example.com/ec"})

    def test_monitor_list_mapping(self):
        self.assert_call("ec_monitor_list", {}, "GET", "/v1/monitors")

    def test_monitor_history_mapping_and_encoding(self):
        self.assert_call("ec_monitor_history", {"monitor_id": "123e4567-e89b-12d3-a456-426614174000", "limit": 10}, "GET", "/v1/monitors/123e4567-e89b-12d3-a456-426614174000/history", expected_query={"limit": 10})

    def test_monitor_opportunity_mapping(self):
        self.assert_call("ec_monitor_opportunity", {"monitor_id": "123e4567-e89b-12d3-a456-426614174001", "limit": 20}, "GET", "/v1/monitors/123e4567-e89b-12d3-a456-426614174001/opportunity", expected_query={"limit": 20})

    def test_account_mapping(self):
        self.assert_call("ec_account", {}, "GET", "/v1/account")


if __name__ == "__main__":
    unittest.main()
