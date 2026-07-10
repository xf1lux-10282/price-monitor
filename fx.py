"""為替レート(USD/JPY)の取得。

無料・APIキー不要のソースを順に試すフォールバック方式。
GitHub Actions のランナーから到達できればよい（開発サンドボックスは
許可リスト制のため到達できないことがあるが、本番では問題ない）。

ソース（出典は地金と同じ Yahoo Finance に統一。落ちた時のみ従来APIへ）:
  1. Yahoo Finance (https://query1.finance.yahoo.com/v8/finance/chart/USDJPY=X) ※ほぼリアルタイム
  2. open.er-api.com (https://open.er-api.com/v6/latest/USD)  ※1日1回更新・フォールバック
  3. frankfurter.app  (https://api.frankfurter.app/latest?from=USD&to=JPY) ※ECB営業日・フォールバック
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass
class FxResult:
    usdjpy: float
    source: str


def _from_yahoo(timeout: int) -> FxResult | None:
    r = requests.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/USDJPY=X",
        params={"range": "1d", "interval": "1d"},
        headers={"User-Agent": _UA},
        timeout=timeout,
    )
    r.raise_for_status()
    result = (r.json().get("chart") or {}).get("result") or []
    if not result:
        return None
    price = (result[0].get("meta") or {}).get("regularMarketPrice")
    if price:
        return FxResult(usdjpy=float(price), source="Yahoo Finance")
    return None


def _from_er_api(timeout: int) -> FxResult | None:
    r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=timeout)
    r.raise_for_status()
    data = r.json()
    rate = (data.get("rates") or {}).get("JPY")
    if rate:
        return FxResult(usdjpy=float(rate), source="open.er-api.com")
    return None


def _from_frankfurter(timeout: int) -> FxResult | None:
    r = requests.get(
        "https://api.frankfurter.app/latest", params={"from": "USD", "to": "JPY"}, timeout=timeout
    )
    r.raise_for_status()
    data = r.json()
    rate = (data.get("rates") or {}).get("JPY")
    if rate:
        return FxResult(usdjpy=float(rate), source="frankfurter.app")
    return None


def get_usdjpy(timeout: int = 15) -> FxResult | None:
    """USD/JPY を取得。Yahoo Finance 優先、失敗時のみ従来APIへ。全滅なら None。"""
    for fetch in (_from_yahoo, _from_er_api, _from_frankfurter):
        try:
            result = fetch(timeout)
        except Exception as exc:
            print(f"  [fx] {fetch.__name__} 失敗: {exc}")
            result = None
        if result is not None:
            return result
    print("  [fx] 為替レートを取得できませんでした（価格のみ記録します）")
    return None
