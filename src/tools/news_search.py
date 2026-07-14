from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional

import requests

from src.core import DataAccessLayer, load_config


class NewsSearchTool:
    def __init__(
        self,
        data_access: DataAccessLayer | None = None,
        api_key: Optional[str] = None,
        max_results: int = 8,
        timeout: int = 20,
        http_post: Callable = requests.post,
    ):
        config = load_config()
        self.data_access = data_access or DataAccessLayer()
        self.api_key = api_key or config.tavily_api_key
        self.max_results = max_results
        self.timeout = timeout
        self.http_post = http_post

    def search(self, code: str, name: str = "") -> List[Dict]:
        if not self.api_key:
            return []
        name_part = f" {name}" if name else ""
        query = f"{code}{name_part} 股票 最近7天 新闻 公告 减持 业绩 监管 诉讼 中标 回购"
        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "topic": "news",
            "time_range": "week",
            "max_results": self.max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_domains": [
                "eastmoney.com",
                "cninfo.com.cn",
                "sse.com.cn",
                "szse.cn",
                "cs.com.cn",
                "stcn.com",
                "jrj.com.cn",
                "10jqka.com.cn",
            ],
        }

        def loader():
            response = self.http_post("https://api.tavily.com/search", json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json().get("results", [])[: self.max_results]

        return self.data_access.fetch(
            "tavily",
            "search",
            re.sub(r"\W+", "_", query)[:120],
            3600,
            1.0,
            loader,
        )
