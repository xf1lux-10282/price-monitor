"""価格抽出ロジック。

任意の商品ページからできるだけ設定なしで価格を取り出せるよう、
複数の戦略を順番に試す:

  1. JSON-LD (schema.org Product/Offer の price) ... 多くのECサイトに有効
  2. meta タグ (og:price:amount, product:price:amount, itemprop=price)
  3. ユーザー指定の CSS セレクタ
  4. ユーザー指定の正規表現

最初に数値が取れた戦略を採用する。通貨記号やカンマは取り除いて
float に正規化する。
"""

from __future__ import annotations

import json
import re
import time
import random
from dataclasses import dataclass
from html import unescape as _html_unescape

import requests
from bs4 import BeautifulSoup


@dataclass
class PriceResult:
    value: float
    raw: str
    method: str
    currency: str | None = None


_PRICE_RE = re.compile(r"(\d[\d.,]*\d|\d)")


def _to_float(text: str) -> float | None:
    """'£51.77' や '1,234.56円' のような文字列から数値を取り出す。"""
    if text is None:
        return None
    match = _PRICE_RE.search(str(text))
    if not match:
        return None
    num = match.group(1)
    # 桁区切りと小数点の判定: 最後の '.' か ',' を小数点とみなす
    if "," in num and "." in num:
        # 両方ある場合、後ろに来る方を小数点とする
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif num.count(",") == 1 and len(num.split(",")[-1]) == 2:
        # "12,99" のような欧州式小数
        num = num.replace(",", ".")
    else:
        num = num.replace(",", "")
    try:
        return float(num)
    except ValueError:
        return None


def _walk_json_ld(node) -> list[tuple[float, str]]:
    """JSON-LD ツリーを再帰的に辿り offers.price を集める。"""
    found: list[tuple[float, str]] = []
    if isinstance(node, dict):
        for key in ("price", "lowPrice", "highPrice"):
            if key in node:
                val = _to_float(node[key])
                if val is not None:
                    found.append((val, f"json-ld:{key}"))
        for value in node.values():
            found.extend(_walk_json_ld(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_json_ld(item))
    return found


def _from_json_ld(soup: BeautifulSoup) -> PriceResult | None:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not tag.string:
            continue
        try:
            data = json.loads(tag.string)
        except (json.JSONDecodeError, TypeError):
            continue
        hits = _walk_json_ld(data)
        # price を最優先
        hits.sort(key=lambda h: 0 if h[1].endswith("price") else 1)
        if hits:
            value, method = hits[0]
            return PriceResult(value=value, raw=str(value), method=method)
    return None


_META_KEYS = [
    ("property", "product:price:amount"),
    ("property", "og:price:amount"),
    ("itemprop", "price"),
    ("name", "twitter:data1"),
]


def _from_meta(soup: BeautifulSoup) -> PriceResult | None:
    for attr, key in _META_KEYS:
        tag = soup.find("meta", attrs={attr: key})
        if tag and tag.get("content"):
            value = _to_float(tag["content"])
            if value is not None:
                return PriceResult(value=value, raw=tag["content"], method=f"meta:{key}")
    # itemprop=price は span などにも付く
    tag = soup.find(attrs={"itemprop": "price"})
    if tag:
        raw = tag.get("content") or tag.get_text(strip=True)
        value = _to_float(raw)
        if value is not None:
            return PriceResult(value=value, raw=raw, method="itemprop:price")
    return None


# メイン商品ではない「関連商品 / おすすめ / カルーセル」を判定するためのクラス断片。
# これらの内側にある価格は別商品のものなので除外する。
_EXCLUDE_ANCESTOR_CLASSES = frozenset(
    {
        "owl-carousel",
        "w-grid-list",
        "w-grid-item",
        "related",
        "up-sells",
        "upsells",
        "cross-sells",
        "crosssells",
        "products",  # WooCommerce 標準の関連商品グリッド <ul class="products">
    }
)


def _in_excluded_section(el) -> bool:
    """要素が関連商品/カルーセル等のセクション内にあれば True。"""
    node = el.parent
    while node is not None and getattr(node, "name", None):
        classes = node.get("class") or []
        if any(c in _EXCLUDE_ANCESTOR_CLASSES for c in classes):
            return True
        node = node.parent
    return False


def _normalize_size(text) -> str:
    """サイズ表記を比較用に正規化する（'25ml' / '25 ml' / '25 mL' を同一視）。"""
    return re.sub(r"\s+", "", str(text)).lower()


def _from_variation(soup: BeautifulSoup, variant: str) -> PriceResult | None:
    """WooCommerce 変動商品から、指定サイズ(variant)の価格を取る。

    変動商品は <form class="variations_form" data-product_variations="[...]">
    に各バリアント(サイズ)の属性と display_price が JSON で埋め込まれている。
    商品名どおりのサイズ（例: 25ml）を確実に取得するために使う。
    """
    if not variant:
        return None
    target = _normalize_size(variant)
    for form in soup.select("form.variations_form"):
        raw = form.get("data-product_variations")
        if not raw or raw == "false":
            continue
        try:
            variations = json.loads(_html_unescape(raw))
        except (json.JSONDecodeError, TypeError):
            continue
        for v in variations:
            attrs = v.get("attributes", {}) or {}
            if any(_normalize_size(val) == target for val in attrs.values()):
                price = v.get("display_price", v.get("display_regular_price"))
                value = _to_float(str(price))
                if value is not None:
                    return PriceResult(value=value, raw=str(price), method=f"variation:{variant}")
    return None


def _from_main_price(soup: BeautifulSoup) -> PriceResult | None:
    """メイン商品の価格を取る（関連商品カルーセルを除外）。

    WooCommerce 系ページで、メイン価格は <p class="price"> 等に入る一方、
    「おすすめ/関連商品」のカードにも同じ価格クラスが付くことがある。
    カルーセル/グリッド内の要素を除外し、最初に残ったメイン価格ブロックを採用する。
    変動商品（サイズ違い）の "$170.30–$1,703.00" は最小値（=最小サイズ）を取る。
    セール中は ins（現在価格）を優先する。
    """
    blocks = soup.select("p.price, .summary .price, .entry-summary .price")
    main = next((b for b in blocks if not _in_excluded_section(b)), None)
    if main is None:
        return None
    amount = main.select_one("ins .woocommerce-Price-amount, ins .amount") or main.select_one(
        ".woocommerce-Price-amount, .amount"
    )
    if amount is None:
        return None
    raw = amount.get("content") or amount.get_text(strip=True)
    value = _to_float(raw)
    if value is None:
        return None
    return PriceResult(value=value, raw=raw, method="main-price")


def _from_css(soup: BeautifulSoup, selector: str) -> PriceResult | None:
    if not selector:
        return None
    el = soup.select_one(selector)
    if not el:
        return None
    raw = el.get("content") or el.get_text(strip=True)
    value = _to_float(raw)
    if value is None:
        return None
    return PriceResult(value=value, raw=raw, method=f"css:{selector}")


def _from_regex(html: str, pattern: str) -> PriceResult | None:
    if not pattern:
        return None
    match = re.search(pattern, html)
    if not match:
        return None
    raw = match.group(1) if match.groups() else match.group(0)
    value = _to_float(raw)
    if value is None:
        return None
    return PriceResult(value=value, raw=raw, method="regex")


def _extract_from_html(html: str, extract: dict) -> PriceResult | None:
    """取得済み HTML から価格を抽出する（戦略を順に試し、最初の成功を返す）。"""
    soup = BeautifulSoup(html, "html.parser")
    extract = extract or {}
    strategies = []
    # サイズ指定（変動商品で「25ml」など特定サイズの価格を確実に取る）を最優先。
    if extract.get("variant"):
        strategies.append(lambda: _from_variation(soup, extract["variant"]))
    # メイン価格抽出（関連商品カルーセルを除外）。variant が取れない時のフォールバック。
    if extract.get("main_price"):
        strategies.append(lambda: _from_main_price(soup))
    # ユーザー指定があればそれを優先する
    if extract.get("css_selector"):
        strategies.append(lambda: _from_css(soup, extract["css_selector"]))
    if extract.get("regex"):
        strategies.append(lambda: _from_regex(html, extract["regex"]))
    if extract.get("use_json_ld", True):
        strategies.append(lambda: _from_json_ld(soup))
    if extract.get("use_meta", True):
        strategies.append(lambda: _from_meta(soup))

    for strategy in strategies:
        try:
            result = strategy()
        except Exception:
            result = None
        if result is not None:
            return result
    return None


def fetch_price(
    url: str, extract: dict, *, user_agent: str, timeout: int, retries: int = 3
) -> PriceResult:
    """1商品の価格を取得する。失敗時は例外を投げる。

    対象サイトがボット対策で時々「商品データの無いページ」を返す（断続ブロック）ため、
    取得失敗・通信エラー時は指数バックオフ＋ジッターで数回リトライする。
    """
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            result = _extract_from_html(resp.text, extract)
            if result is not None:
                return result
            last_error = ValueError("価格を抽出できませんでした（ページに商品データが無い可能性）。")
        except requests.RequestException as exc:
            last_error = exc
        # 最終試行でなければ待ってリトライ（1.5s, 3s, 6s ... ＋ジッター）
        if attempt < retries - 1:
            time.sleep(1.5 * (2 ** attempt) + random.uniform(0, 1.0))

    raise ValueError(
        f"価格を抽出できませんでした（{retries}回試行）。サイトの一時的なブロックの可能性。"
        f" 直近のエラー: {last_error}"
    )
