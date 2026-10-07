"""Finnhub price targets, independent of all internal valuation inputs."""
from dataclasses import asdict, dataclass
import json
import os
import re
import threading
import time
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from market_reference import positive

ENDPOINT = 'https://finnhub.io/api/v1/stock/price-target'

@dataclass
class MarketReferenceResult:
    ticker: str
    target_mean: float | None = None
    target_high: float | None = None
    target_low: float | None = None
    analyst_count: int | None = None
    last_updated: str | None = None
    source: str = 'Finnhub'
    source_status: str = 'NO_DATA'
    error: str | None = None

class MarketReferenceProvider(Protocol):
    def get_price_target(self, ticker: str) -> dict: ...


def configured_api_key():
    key = os.environ.get('FINNHUB_API_KEY', '').strip()
    if not key:
        try:
            import streamlit as st
            key = str(st.secrets.get('FINNHUB_API_KEY', '')).strip()
        except Exception:
            key = ''
    return key if key and key not in {'...', 'YOUR_FINNHUB_API_KEY'} else None


def _fetch(ticker, key):
    request = Request(ENDPOINT + '?' + urlencode({'symbol': ticker}),
                      headers={'X-Finnhub-Token': key, 'Accept': 'application/json'})
    with urlopen(request, timeout=10) as response:
        return json.load(response)


class FinnhubMarketReferenceProvider:
    """Process-wide singleton below survives reruns. Cache stores only public data.

    Serial requests are spaced by 1.1s. Successful/no-data responses last 12h;
    transient failures last 60s. A 429 pauses uncached calls for 60s or Retry-After.
    """
    def __init__(self, *, key_loader=configured_api_key, fetch=_fetch,
                 clock=time.monotonic, sleep=time.sleep, ttl=12*3600, interval=1.1):
        self._key_loader, self._fetch = key_loader, fetch
        self._clock, self._sleep = clock, sleep
        self._ttl, self._interval = ttl, interval
        self._cache = {}
        self._lock = threading.Lock()
        self._next_request = self._blocked_until = 0

    def get_price_target(self, ticker):
        ticker = str(ticker or '').strip().upper()
        result = MarketReferenceResult(ticker)
        def fail(status, error):
            result.source_status, result.error = status, error
            return asdict(result)
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-:]{0,24}', ticker):
            return fail('INVALID_SYMBOL', '股票代码无效')
        key = self._key_loader()
        if not key:
            return fail('NOT_CONFIGURED', '未配置市场参考')
        with self._lock:
            now = self._clock()
            cached = self._cache.get(ticker)
            if cached and cached[0] > now:
                return dict(cached[1])
            if now < self._blocked_until:
                return fail('RATE_LIMIT', '市场参考请求限流，请稍后重试')
            if now < self._next_request:
                self._sleep(self._next_request - now)
            self._next_request = self._clock() + self._interval
            try:
                payload = self._fetch(ticker, key)
                if not isinstance(payload, dict):
                    data = fail('NETWORK_ERROR', '市场参考响应格式无效')
                elif payload.get('error'):
                    # Never propagate response text: it may contain credentials.
                    data = fail('PROVIDER_ERROR', '市场参考服务返回错误')
                elif payload.get('symbol') and str(payload['symbol']).upper() != ticker:
                    data = fail('INVALID_SYMBOL', '市场参考股票代码不匹配')
                else:
                    result.target_mean = positive(payload.get('targetMean'))
                    result.target_high = positive(payload.get('targetHigh'))
                    result.target_low = positive(payload.get('targetLow'))
                    count = positive(payload.get('numberAnalysts'))
                    result.analyst_count = int(count) if count and count.is_integer() else None
                    updated = payload.get('lastUpdated')
                    result.last_updated = updated if isinstance(updated, str) else None
                    result.source_status = 'OK' if result.target_mean else 'NO_DATA'
                    data = asdict(result)
            except HTTPError as exc:
                status = {429:'RATE_LIMIT', 400:'INVALID_SYMBOL', 404:'INVALID_SYMBOL',
                          401:'AUTH_ERROR', 403:'ACCESS_DENIED'}.get(exc.code, 'NETWORK_ERROR')
                if status == 'RATE_LIMIT':
                    try:
                        cooldown = min(3600, max(60, float(exc.headers.get('Retry-After', 60))))
                    except (ValueError, TypeError, AttributeError):
                        cooldown = 60
                    self._blocked_until = self._clock() + cooldown
                data = fail(status, {'AUTH_ERROR':'市场参考密钥无效', 'ACCESS_DENIED':'市场参考接口权限不足'}.get(status, '市场参考请求失败'))
            except (URLError, TimeoutError, OSError, ValueError):
                data = fail('NETWORK_ERROR', '市场参考网络或响应异常')
            expiry = self._ttl if data['source_status'] in {'OK', 'NO_DATA', 'INVALID_SYMBOL'} else 60
            self._cache[ticker] = (self._clock() + expiry, dict(data))
            return data


_default_provider = FinnhubMarketReferenceProvider()

def get_market_reference_provider():
    return _default_provider


STATUS_LABELS = {'NOT_CONFIGURED':'未配置市场参考', 'NO_DATA':'暂无分析师目标',
                 'RATE_LIMIT':'市场参考限流', 'NETWORK_ERROR':'市场参考网络异常',
                 'INVALID_SYMBOL':'股票代码无效', 'AUTH_ERROR':'市场参考密钥无效',
                 'ACCESS_DENIED':'市场参考权限不足', 'PROVIDER_ERROR':'市场参考服务异常',
                 'HISTORICAL_UNAVAILABLE':'历史市场参考不可用'}

def format_consensus_target(reference):
    target = positive((reference or {}).get('analyst_consensus_target'))
    if target:
        return f'${target:,.0f}'
    return STATUS_LABELS.get((reference or {}).get('source_status'), '暂无市场参考')
