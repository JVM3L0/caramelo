import httpx


def build_http_client(user_agent: str, proxy: str | None = None) -> httpx.AsyncClient:
    """Shared client for store integrations. Proxy is off unless configured."""
    return httpx.AsyncClient(
        proxy=proxy,
        headers={"User-Agent": user_agent, "Accept-Language": "pt-BR,pt;q=0.9"},
        timeout=httpx.Timeout(20.0),
        follow_redirects=True,
    )
