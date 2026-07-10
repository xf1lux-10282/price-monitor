#!/usr/bin/env python3
"""価格監視のメインスクリプト。

config.json の有効な商品を順番にスクレイピングし、価格を履歴に追記する。
前回から価格が変わっていれば ntfy / Discord に通知する。
目標価格 (target_price) が設定され、それを下回ったら追加で通知する。

使い方:
    python monitor.py                 # config.json の全商品をチェック
    python monitor.py --only <id>     # 特定の商品だけチェック
    python monitor.py --config x.json # 別の設定ファイルを使う
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import fx as fx_module
import metals as metals_module
import notifier
import storage
from scraper import fetch_price

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_product(product: dict, settings: dict, usdjpy: float | None) -> bool:
    name = product.get("name") or product["id"]
    print(f"▶ {name}")
    try:
        result = fetch_price(
            product["url"],
            product.get("extract", {}),
            user_agent=settings.get("user_agent", "price-monitor/1.0"),
            timeout=int(settings.get("request_timeout_sec", 20)),
        )
    except Exception as exc:
        print(f"  ✖ 取得失敗: {exc}")
        return False

    currency = result.currency or product.get("currency") or "?"
    history = storage.load_history(product["id"])
    previous = storage.last_price(history)

    price_jpy = storage.to_jpy(result.value, currency, usdjpy)
    jpy_note = f"  ≒ ¥{price_jpy:,}" if price_jpy is not None else ""
    print(f"  価格: {result.value:,.2f} {currency}{jpy_note}  (抽出: {result.method})")

    storage.append_point(product, result.value, result.method, currency, usdjpy)

    changed = previous is None or result.value != previous
    if changed:
        notifier.notify_change(
            settings,
            product=product,
            old=previous,
            new=result.value,
            currency=currency,
            usdjpy=usdjpy,
            price_jpy=price_jpy,
        )
    else:
        print("  変化なし")

    target = product.get("target_price")
    if target is not None and result.value <= float(target):
        notifier.notify_target_reached(
            settings, product=product, price=result.value, target=float(target), currency=currency
        )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="商品価格モニター")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="設定ファイルのパス")
    parser.add_argument("--only", help="指定 id の商品だけチェック")
    args = parser.parse_args(argv)

    config = load_config(Path(args.config))
    settings = config.get("settings", {})
    products = [p for p in config.get("products", []) if p.get("enabled", True)]
    if args.only:
        products = [p for p in products if p["id"] == args.only]

    if not products:
        print("チェック対象の商品がありません。config.json を確認してください。")
        return 1

    # 為替は1回の実行につき1度だけ取得し、全商品で共有する
    fx = fx_module.get_usdjpy(timeout=int(settings.get("request_timeout_sec", 20)))
    usdjpy = fx.usdjpy if fx else None
    if fx:
        print(f"== 為替: 1 USD = {fx.usdjpy:.4f} JPY ({fx.source}) ==")
        storage.record_fx(fx.usdjpy, fx.source)

    # 参考指標: 地金（プラチナ・パラジウム）のスポット価格も記録する（購入商品ではない）
    metal_results = metals_module.get_metals(timeout=int(settings.get("request_timeout_sec", 20)))
    for m in metal_results:
        jpy_g = storage.usd_oz_to_jpy_g(m.usd, usdjpy)
        note = f" ≒ ¥{jpy_g:,}/g" if jpy_g is not None else ""
        print(f"== 地金 {m.label}: ${m.usd:,.2f}/oz{note} ({m.source}) ==")
    storage.record_metals(metal_results, usdjpy)

    print(f"== {len(products)} 件の商品をチェックします ==")
    ok = 0
    for i, product in enumerate(products):
        if i > 0:
            time.sleep(1.5)  # 連続アクセスでブロックされにくくする小休止
        if check_product(product, settings, usdjpy):
            ok += 1

    # ダッシュボード用インデックスは全商品分を出力（無効商品も履歴は残す）
    storage.write_index(config.get("products", []))

    failed = len(products) - ok
    print(f"\n完了: {ok}/{len(products)} 件成功" + (f"（{failed}件は今回取得できず）" if failed else ""))
    # サイトの一時ブロックは日常的に起きるため、商品取得の失敗ではジョブを失敗させない
    # （失敗通知の乱発を防ぐ／為替・地金・index は保存して次回再取得する）。
    # コードや設定の本当の異常は check_product 外で例外送出され、別途ジョブが失敗する。
    if ok == 0:
        print("⚠ 今回は全商品で取得できませんでした（サイトの一時ブロックの可能性）。"
              "為替・地金は記録済み。次回再取得します。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
