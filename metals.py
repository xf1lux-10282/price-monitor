"""地金（プラチナ・パラジウム）のスポット価格(USD/oz)の取得。

参考指標用。為替(fx.py)と同じく無料・APIキー不要のソースをフォールバックで試す。
GitHub Actions のランナーから到達できればよい。

ソース:
  1. Yahoo Finance chart API（PL=F=プラチナ先物 / PA=F=パラジウム先物, COMEX）
     https://query1.finance.yahoo.com/v8/finance/chart/PL=F
  2. stooq（XPTUSD / XPDUSD のスポット, CSV）
     https://stooq.com/q/l/?s=xptusd&f=sd2t2ohlcv&h&e=csv

※先物/スポットの厳密な違いはあるが「参考」用途のため近似値として扱う。
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# (キー, 表示名, Yahooシンボル, stooqシンボル)
_METALS = [
    ("platinum", "プラチナ", "PL=F", "xptusd"),
    ("palladium", "パラジウム", "PA=F", "xpdusd"),
    ("silver", "銀", "SI=F", "xagusd"),
]


@dataclass
class MetalResult:
    key: str       # "platinum" / "palladium"
    label: str     # 表示名
    usd: float     # 1トロイオンスあたり USD
    source: str


def _from_yahoo(symbol: str, timeout: int) -> float | None:
    r = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"range": "1d", "interval": "1d"},
        headers={"User-Agent": _UA},
        timeout=timeout,
    )
    r.raise_for_status()
    result = (r.json().get("chart") or {}).get("result") or []
    if not result:
        return None
    meta = result[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    return float(price) if price else None


def _from_stooq(symbol: str, timeout: int) -> float | None:
    r = requests.get(
        "https://stooq.com/q/l/",
        params={"s": symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"},
        headers={"User-Agent": _UA},
        timeout=timeout,
    )
    r.raise_for_status()
    lines = r.text.strip().splitlines()
    if len(lines) < 2:
        return None
    # Symbol,Date,Time,Open,High,Low,Close,Volume → Close は index 6
    cols = lines[1].split(",")
    if len(cols) < 7:
        return None
    close = cols[6].strip()
    if close in ("", "N/D"):
        return None
    try:
        return float(close)
    except ValueError:
        return None


def get_metals(timeout: int = 15) -> list[MetalResult]:
    """プラチナ・パラジウムの USD/oz を取得。取得できたものだけ返す。"""
    results: list[MetalResult] = []
    for key, label, ysym, ssym in _METALS:
        usd: float | None = None
        source = ""
        for name, fn, arg in (("yahoo", _from_yahoo, ysym), ("stooq", _from_stooq, ssym)):
            try:
                usd = fn(arg, timeout)
            except Exception as exc:  # noqa: BLE001
                print(f"  [metals] {key} {name} 失敗: {exc}")
                usd = None
            if usd:
                source = name
                break
        if usd:
            results.append(MetalResult(key=key, label=label, usd=usd, source=source))
        else:
            print(f"  [metals] {key} の価格を取得できませんでした")
    return results
