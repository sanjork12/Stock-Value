"""Bounded Yahoo exception recovery policy and request-local rate-limit state."""
from dataclasses import dataclass, field
from copy import deepcopy
from datetime import datetime, timezone
import time
import socket
from yfinance.exceptions import YFRateLimitError, YFException
from yfinance import Ticker as YahooTicker
from requests.exceptions import Timeout as RequestsTimeout, ConnectionError as RequestsConnectionError, HTTPError as RequestsHTTPError
from curl_cffi.requests.exceptions import Timeout as CurlTimeout, ConnectionError as CurlConnectionError, HTTPError as CurlHTTPError

YAHOO_RATE_LIMIT_BATCH_COOLDOWN_SECONDS = 3
YAHOO_RATE_LIMIT_RECOVERY_COOLDOWN_SECONDS = 2

def classify_exception(exc):
    if isinstance(exc, YFRateLimitError): return 'TRANSIENT_RATE_LIMIT'
    if isinstance(exc, (TimeoutError, RequestsTimeout, CurlTimeout)): return 'TRANSIENT_TIMEOUT'
    if isinstance(exc, (ConnectionError, RequestsConnectionError, CurlConnectionError, socket.gaierror)): return 'TRANSIENT_NETWORK'
    if isinstance(exc, (TypeError, ValueError, AttributeError, LookupError, ArithmeticError, AssertionError, NameError)): return 'PROGRAMMING_ERROR'
    if isinstance(exc, (YFException, RequestsHTTPError, CurlHTTPError)): return 'NON_TRANSIENT_PROVIDER_ERROR'
    return 'UNKNOWN_EXCEPTION'

def transient(category):
    return category in ('TRANSIENT_RATE_LIMIT', 'TRANSIENT_TIMEOUT', 'TRANSIENT_NETWORK')

def utc_now(): return datetime.now(timezone.utc).isoformat()

def pin_owned_info_alias(ticker, payload):
    """Seal only this acquisition's real Yahoo instance against implicit info retries.

    History/fast-info helpers may read self.info internally. They may reuse the
    already observed canonical response but cannot start another get_info call.
    A recovery is always performed on a separately constructed, unpinned instance.
    """
    if isinstance(ticker,YahooTicker):
        canonical=deepcopy(payload) if isinstance(payload,dict) else {}
        ticker.get_info=lambda *args,**kwargs:deepcopy(canonical)

@dataclass
class BatchProviderRateLimitState:
    sleep_fn: object = time.sleep
    clock_fn: object = utc_now
    yahoo_rate_limit_observed: bool = False
    first_observed_ticker: object = None
    first_observed_at: object = None
    affected_tickers: list = field(default_factory=list)
    primary_rate_limit_count: int = 0
    recovery_rate_limit_count: int = 0
    recovery_attempts: int = 0
    recovery_successes: int = 0
    cooldown_events: int = 0
    total_cooldown_seconds: int = 0
    attempts_by_ticker: dict = field(default_factory=dict)

    def observe(self, ticker, recovery=False):
        if not self.yahoo_rate_limit_observed:
            self.first_observed_ticker=ticker;self.first_observed_at=self.clock_fn()
        self.yahoo_rate_limit_observed=True
        if ticker not in self.affected_tickers:self.affected_tickers.append(ticker)
        if recovery:self.recovery_rate_limit_count+=1
        else:self.primary_rate_limit_count+=1

    def cooldown(self, recovery=False):
        if not self.yahoo_rate_limit_observed:return False
        seconds=YAHOO_RATE_LIMIT_RECOVERY_COOLDOWN_SECONDS if recovery else YAHOO_RATE_LIMIT_BATCH_COOLDOWN_SECONDS
        self.sleep_fn(seconds)
        self.cooldown_events+=1;self.total_cooldown_seconds+=seconds
        return True

    def count_attempt(self, ticker, recovery=False):
        attempts=self.attempts_by_ticker.setdefault(ticker,{'primary':0,'recovery':0})
        key='recovery' if recovery else 'primary'
        if attempts[key]>=1 or sum(attempts.values())>=2:
            raise RuntimeError('Yahoo batch attempt budget exhausted')
        attempts[key]+=1

    def summary(self):
        return {'provider':'Yahoo','endpoint_family':'quoteSummary/get_info',
            'rate_limit_observed':self.yahoo_rate_limit_observed,
            'yahoo_rate_limit_observed':self.yahoo_rate_limit_observed,
            'first_observed_ticker':self.first_observed_ticker,'first_observed_at':self.first_observed_at,
            'affected_tickers':list(self.affected_tickers),
            'event_count':self.primary_rate_limit_count+self.recovery_rate_limit_count,
            'primary_rate_limit_count':self.primary_rate_limit_count,'recovery_rate_limit_count':self.recovery_rate_limit_count,
            'recovery_attempts':self.recovery_attempts,'recovery_successes':self.recovery_successes,
            'cooldown_applied':bool(self.cooldown_events),'cooldown_seconds':YAHOO_RATE_LIMIT_BATCH_COOLDOWN_SECONDS,
            'cooldown_events':self.cooldown_events,'total_cooldown_seconds':self.total_cooldown_seconds}
