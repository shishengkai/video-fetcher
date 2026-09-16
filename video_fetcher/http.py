from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session: requests.Session | None = None


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = build_session()
    return _session


def build_session() -> requests.Session:
    session = requests.Session()
    # 仅自动重试连接/读失败；HTTP 业务状态与体积校验交给 tenacity，避免双重放大。
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=0,
        backoff_factor=0.3,
        allowed_methods=frozenset({"GET", "POST", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
