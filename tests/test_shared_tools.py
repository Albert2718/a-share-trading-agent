from __future__ import annotations

import unittest

import numpy as np

from src.tools.lstm import LSTMPredictor
from src.tools.news_search import NewsSearchTool
from src.tools.utils import normalize_a_share_code


class _DataAccess:
    def fetch(self, namespace, endpoint, key, ttl_seconds, min_interval, loader):
        return loader()


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"results": [{"title": "测试新闻", "content": "内容", "url": "https://example.com"}]}


class SharedToolTests(unittest.TestCase):
    def test_normalize_a_share_code(self):
        self.assertEqual(normalize_a_share_code("SH.600519"), "600519")
        self.assertEqual(normalize_a_share_code("1"), "000001")

    def test_news_search_uses_injected_transport(self):
        calls = []

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return _Response()

        tool = NewsSearchTool(
            data_access=_DataAccess(),
            api_key="test-key",
            http_post=post,
            max_results=3,
        )
        results = tool.search("600519", "贵州茅台")

        self.assertEqual(results[0]["title"], "测试新闻")
        self.assertEqual(calls[0][0], "https://api.tavily.com/search")
        self.assertNotIn("test-key", str(results))

    def test_lstm_predictor_loads_project_model(self):
        predictor = LSTMPredictor()
        closes = np.array(
            [10, 10.1, 10.05, 10.2, 10.3, 10.25, 10.4, 10.5, 10.45, 10.6, 10.7, 10.65, 10.8, 10.9],
            dtype=np.float32,
        )

        value = predictor.predict_return(closes)

        self.assertEqual(predictor.model_path.name, "lstm_model.pt")
        self.assertIsNotNone(value, predictor.last_error)


if __name__ == "__main__":
    unittest.main()
