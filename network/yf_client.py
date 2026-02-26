"""
YFinance Client Wrapper — Proxy-aware, retry-enabled yf.download() / Ticker.history().

Semua panggilan ke yfinance melewati sini sehingga:
  - Proxy diinjeksikan ke session (curl_cffi jika tersedia, else requests)
  - Retry otomatis dengan backoff
  - Adaptive rate-limiter dipakai sebelum setiap request
  - Hasil error dilaporkan ke ProxyManager + RateLimiter
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Union

import pandas as pd
import yfinance as yf

from network.proxy_manager import ProxyManager, _build_proxies, _mask, get_proxy_manager
from network.rate_limiter import AdaptiveRateLimiter, get_rate_limiter
from network.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

# Matikan noise yfinance
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)


class YFClient:
    """
    Wrapper yfinance dengan proxy, retry, dan adaptive rate-limiting.

    Gunakan melalui singleton get_yf_client() untuk konsistensi.
    """

    def __init__(
        self,
        proxy_manager: Optional[ProxyManager] = None,
        retry_policy: Optional[RetryPolicy] = None,
        limiter: Optional[AdaptiveRateLimiter] = None,
        impersonate: str = "chrome110",
    ):
        self.proxy_manager = proxy_manager or get_proxy_manager()
        self.retry_policy = retry_policy or RetryPolicy()
        self.limiter = limiter or get_rate_limiter()
        self.impersonate = impersonate

    # ─── download() ───────────────────────────────────────────────────────────

    def download(
        self,
        tickers: Union[str, List[str]],
        interval: str = "1d",
        period: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        group_by: str = "ticker",
        threads: bool = True,
        auto_adjust: bool = False,
        progress: bool = False,
    ) -> pd.DataFrame:
        """
        yf.download() dengan proxy + retry.

        Apply rate limiter sebelum request.
        Retry hingga max_retry kali.
        """
        max_retry = self.retry_policy.max_retry

        for attempt in range(1, max_retry + 2):  # +1 untuk final attempt
            proxy = self.proxy_manager.get_proxy()
            self.limiter.wait_sync()

            try:
                kwargs = dict(
                    tickers=tickers,
                    interval=interval,
                    auto_adjust=auto_adjust,
                    progress=progress,
                )
                if period:
                    kwargs["period"] = period
                if start:
                    kwargs["start"] = start
                if end:
                    kwargs["end"] = end

                # Inject proxy via session
                session = _build_session(proxy, self.impersonate)
                if session is not None:
                    kwargs["session"] = session

                df = yf.download(**kwargs)
                self.proxy_manager.report_success(proxy)
                self.limiter.report_success()
                return df

            except Exception as e:
                is_429 = self.retry_policy.is_429(e)
                self.proxy_manager.report_failure(proxy, e)
                self.limiter.report_error(is_429=is_429)

                if attempt > max_retry or not self.retry_policy.should_retry(e):
                    logger.warning(
                        f"[yf_client] download failed after {attempt} "
                        f"attempt(s): {e}"
                    )
                    raise

                sleep = self.retry_policy.backoff_seconds(attempt, is_429=is_429)
                logger.debug(
                    f"[yf_client] Retry {attempt}/{max_retry} "
                    f"proxy={_mask(proxy)} sleep={sleep:.1f}s err={e}"
                )
                time.sleep(sleep)

        raise RuntimeError("[yf_client] download: max retries exceeded")

    # ─── history() ────────────────────────────────────────────────────────────

    def history(
        self,
        ticker: str,
        period: str = "1d",
        interval: str = "5m",
        auto_adjust: bool = True,
    ) -> Optional[pd.DataFrame]:
        """
        yf.Ticker.history() dengan proxy + retry.
        """
        max_retry = self.retry_policy.max_retry

        for attempt in range(1, max_retry + 2):
            proxy = self.proxy_manager.get_proxy()
            self.limiter.wait_sync()

            try:
                session = _build_session(proxy, self.impersonate)
                if session is not None:
                    stock = yf.Ticker(ticker, session=session)
                else:
                    stock = yf.Ticker(ticker)

                df = stock.history(
                    period=period,
                    interval=interval,
                    auto_adjust=auto_adjust,
                )

                self.proxy_manager.report_success(proxy)
                self.limiter.report_success()
                return df

            except Exception as e:
                is_429 = self.retry_policy.is_429(e)
                self.proxy_manager.report_failure(proxy, e)
                self.limiter.report_error(is_429=is_429)

                if attempt > max_retry or not self.retry_policy.should_retry(e):
                    logger.debug(
                        f"[yf_client] history {ticker} failed: {e}"
                    )
                    return None

                sleep = self.retry_policy.backoff_seconds(attempt, is_429=is_429)
                logger.debug(
                    f"[yf_client] Retry {attempt}/{max_retry} "
                    f"{ticker} sleep={sleep:.1f}s proxy={_mask(proxy)}"
                )
                time.sleep(sleep)

        return None


# ─── Session Builder ──────────────────────────────────────────────────────────

def _build_session(proxy: Optional[str], impersonate: str = "chrome110"):
    """
    Bangun curl_cffi session jika tersedia, fallback ke None.

    curl_cffi mendukung impersonation — menyamarkan fingerprint browser.
    Jika tidak terinstall, yfinance akan pakai session default-nya.
    """
    if not proxy:
        return None
    try:
        from curl_cffi import requests as curl_req  # type: ignore
        session = curl_req.Session(impersonate=impersonate)
        if proxy:
            session.proxies = _build_proxies(proxy)
        return session
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"[yf_client] curl_cffi session error: {e}")

    # Fallback: requests.Session biasa
    try:
        import requests as _req
        session = _req.Session()
        if proxy:
            session.proxies = _build_proxies(proxy)
        return session
    except Exception:
        return None


# ─── Singleton ────────────────────────────────────────────────────────────────

_client: Optional[YFClient] = None


def get_yf_client() -> YFClient:
    global _client
    if _client is None:
        try:
            from config import settings
            _client = YFClient(
                proxy_manager=get_proxy_manager(),
                retry_policy=RetryPolicy(max_retry=settings.PROXY_MAX_RETRY),
                limiter=get_rate_limiter(),
            )
        except Exception:
            _client = YFClient()
    return _client
