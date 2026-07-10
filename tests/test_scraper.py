"""scraper の価格抽出ロジックのテスト（ネットワーク不要）。

実行: python tests/test_scraper.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup  # noqa: E402

import scraper  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _check(name, cond):
    print(f"  {'✔' if cond else '✖'} {name}")
    assert cond, name


def test_to_float():
    print("test_to_float")
    _check("£51.77", scraper._to_float("£51.77") == 51.77)
    _check("$78.50", scraper._to_float("$78.50") == 78.50)
    _check("1,234.56 円", scraper._to_float("1,234.56円") == 1234.56)
    _check("12,99 € (EU)", scraper._to_float("12,99 €") == 12.99)
    _check("1.234,56 (EU)", scraper._to_float("1.234,56") == 1234.56)
    _check("空文字 -> None", scraper._to_float("") is None)
    _check("数値なし -> None", scraper._to_float("お問い合わせ") is None)


def test_json_ld():
    print("test_json_ld (WooCommerce fixture)")
    html = (FIXTURES / "woocommerce_sample.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    result = scraper._from_json_ld(soup)
    _check("JSON-LD から 78.5 を抽出", result is not None and result.value == 78.5)


def test_css():
    print("test_css")
    html = (FIXTURES / "woocommerce_sample.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    result = scraper._from_css(soup, "p.price .woocommerce-Price-amount")
    _check("CSS セレクタから 78.5", result is not None and result.value == 78.5)


def test_main_price_excludes_carousel():
    print("test_main_price（関連商品カルーセルを除外してメイン価格を取る）")
    # 実サイト(B&S)の構造を模した HTML:
    #  - メイン商品は section.product 内、変動価格 $170.30–$1,703.00（最小=$170.30）
    #  - 下部の owl-carousel には別商品(Na2 5%=$42.58 など)が並ぶ
    html = """
    <html><body>
      <section class="l-section wpb_row product">
        <div class="vc_column-inner"><div class="wpb_column">
          <p class="w-post-elm product_field price us_custom_b6615905">
            <span class="woocommerce-Price-amount amount">$170.30</span>
            &ndash;
            <span class="woocommerce-Price-amount amount">$1,703.00</span>
          </p>
        </div></div>
      </section>
      <div class="w-grid-list owl-carousel">
        <article class="w-grid-item post-715 product">
          <p class="w-post-elm product_field price usg_product_field_3">
            <span class="woocommerce-Price-amount amount">$42.58</span>
          </p>
        </article>
        <article class="w-grid-item post-667 product">
          <p class="w-post-elm product_field price usg_product_field_3">
            <span class="woocommerce-Price-amount amount">$87.29</span>
          </p>
        </article>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = scraper._from_main_price(soup)
    _check("メイン価格 $170.30 を取得", result is not None and result.value == 170.30)
    _check("カルーセルの $42.58 を拾わない", result.value != 42.58)


def test_variation_picks_requested_size():
    print("test_variation（指定サイズ 25ml の価格を取る）")
    # WooCommerce 変動商品の data-product_variations を模した HTML。
    variations = [
        {"attributes": {"attribute_size": "10ml"}, "display_price": 170.30},
        {"attributes": {"attribute_size": "25ml"}, "display_price": 375.00},
        {"attributes": {"attribute_size": "100ml"}, "display_price": 1703.00},
    ]
    import json as _json

    html = (
        '<form class="variations_form cart" '
        f"data-product_variations='{_json.dumps(variations)}'></form>"
    )
    soup = BeautifulSoup(html, "html.parser")
    r25 = scraper._from_variation(soup, "25ml")
    _check("25ml -> $375.00", r25 is not None and r25.value == 375.00)
    r10 = scraper._from_variation(soup, "10 mL")  # 表記ゆれも一致する
    _check("'10 mL' 表記ゆれ -> $170.30", r10 is not None and r10.value == 170.30)
    _check("存在しないサイズ -> None", scraper._from_variation(soup, "7ml") is None)


def test_strategy_order():
    print("test_strategy_order（自動抽出: 設定なしで取れる）")
    html = (FIXTURES / "woocommerce_sample.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    # fetch_price はネットワークを使うので、内部戦略のみ検証
    result = scraper._from_json_ld(soup) or scraper._from_meta(soup)
    _check("設定ゼロでも JSON-LD で抽出できる", result is not None and result.value == 78.5)


def test_metals_parsing():
    print("test_metals（Yahoo JSON / stooq CSV のパース・円/g換算）")
    import metals as metals_mod
    import storage

    # Yahoo chart API 形式のレスポンスをスタブ
    class _Resp:
        def __init__(self, payload=None, text=None):
            self._p, self.text = payload, text
        def raise_for_status(self):
            pass
        def json(self):
            return self._p

    yahoo_payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 1234.5}}], "error": None}}
    orig = metals_mod.requests.get
    metals_mod.requests.get = lambda *a, **k: _Resp(payload=yahoo_payload)
    try:
        v = metals_mod._from_yahoo("PL=F", 5)
        _check("Yahoo から 1234.5 を抽出", v == 1234.5)
    finally:
        metals_mod.requests.get = orig

    # stooq CSV 形式
    csv = "Symbol,Date,Time,Open,High,Low,Close,Volume\nXPTUSD,2026-06-07,21:00:00,1230,1240,1228,1236.7,0"
    metals_mod.requests.get = lambda *a, **k: _Resp(text=csv)
    try:
        v = metals_mod._from_stooq("xptusd", 5)
        _check("stooq Close=1236.7 を抽出", v == 1236.7)
    finally:
        metals_mod.requests.get = orig

    # USD/oz → 円/g 換算（例: $1000/oz, 150円 → 1000*150/31.1034768 ≒ 4823円/g）
    g = storage.usd_oz_to_jpy_g(1000.0, 150.0)
    _check("円/g 換算 ≒ 4823", g == round(1000.0 * 150.0 / 31.1034768))
    _check("為替なしは None", storage.usd_oz_to_jpy_g(1000.0, None) is None)


def test_fx_yahoo():
    print("test_fx（Yahoo USDJPY=X のパース）")
    import fx as fx_mod

    class _Resp:
        def __init__(self, payload): self._p = payload
        def raise_for_status(self): pass
        def json(self): return self._p

    payload = {"chart": {"result": [{"meta": {"regularMarketPrice": 160.145}}], "error": None}}
    orig = fx_mod.requests.get
    fx_mod.requests.get = lambda *a, **k: _Resp(payload)
    try:
        r = fx_mod._from_yahoo(5)
        _check("Yahoo から 160.145 / source=Yahoo Finance",
               r is not None and r.usdjpy == 160.145 and r.source == "Yahoo Finance")
    finally:
        fx_mod.requests.get = orig


if __name__ == "__main__":
    test_to_float()
    test_json_ld()
    test_css()
    test_main_price_excludes_carousel()
    test_variation_picks_requested_size()
    test_metals_parsing()
    test_fx_yahoo()
    test_strategy_order()
    print("\nすべてのテストに合格しました ✅")
