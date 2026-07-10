#!/usr/bin/env python3
"""商品の追加・削除・一覧を行う CLI。

config.json を直接編集してもよいが、このツールを使うと安全に操作できる。

例:
    # 一覧
    python manage.py list

    # 追加（最低限は id と url。価格抽出は自動 → 失敗したら --selector を指定）
    python manage.py add --id sony-wh1000 \\
        --name "Sony WH-1000XM5" \\
        --url "https://example.com/item/123" \\
        --currency USD --target 350

    # CSS セレクタを指定して追加（自動抽出が外れる場合）
    python manage.py add --id foo --url https://... --selector ".price"

    # 追加前に価格が取れるかテスト
    python manage.py add --id foo --url https://... --test

    # 一時停止 / 再開 / 削除
    python manage.py disable --id foo
    python manage.py enable  --id foo
    python manage.py remove  --id foo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"


def load() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save(config: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def find(config: dict, product_id: str) -> dict | None:
    for product in config.get("products", []):
        if product["id"] == product_id:
            return product
    return None


def cmd_list(config: dict, _args) -> int:
    products = config.get("products", [])
    if not products:
        print("登録された商品はありません。")
        return 0
    print(f"{'ID':<18} {'状態':<6} {'通貨':<5} {'目標':<10} 名前")
    print("-" * 70)
    for p in products:
        state = "有効" if p.get("enabled", True) else "停止"
        target = p.get("target_price")
        print(
            f"{p['id']:<18} {state:<6} {str(p.get('currency') or '-'):<5} "
            f"{str(target) if target is not None else '-':<10} {p.get('name') or ''}"
        )
    return 0


def cmd_add(config: dict, args) -> int:
    if find(config, args.id):
        print(f"✖ id '{args.id}' は既に存在します。別の id を使うか remove してください。")
        return 1

    extract = {
        "css_selector": args.selector,
        "regex": args.regex,
        "use_json_ld": True,
        "use_meta": True,
    }

    if args.test:
        print(f"価格抽出をテスト中: {args.url}")
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from scraper import fetch_price

            result = fetch_price(
                args.url,
                extract,
                user_agent=config.get("settings", {}).get(
                    "user_agent", "price-monitor/1.0"
                ),
                timeout=20,
            )
            print(f"  ✔ 抽出成功: {result.value:,.2f}  (方式: {result.method})")
        except Exception as exc:
            print(f"  ✖ 抽出失敗: {exc}")
            print("  → --selector か --regex を指定して再度お試しください。")
            return 2

    product = {
        "id": args.id,
        "name": args.name or args.id,
        "url": args.url,
        "currency": args.currency,
        "enabled": True,
        "extract": extract,
        "target_price": args.target,
    }
    config.setdefault("products", []).append(product)
    save(config)
    print(f"✔ 追加しました: {args.id}")
    return 0


def cmd_remove(config: dict, args) -> int:
    before = len(config.get("products", []))
    config["products"] = [p for p in config.get("products", []) if p["id"] != args.id]
    if len(config["products"]) == before:
        print(f"✖ id '{args.id}' が見つかりません。")
        return 1
    save(config)
    print(f"✔ 削除しました: {args.id}（履歴ファイル data/history/{args.id}.json は残ります）")
    return 0


def _set_enabled(config: dict, product_id: str, enabled: bool) -> int:
    product = find(config, product_id)
    if not product:
        print(f"✖ id '{product_id}' が見つかりません。")
        return 1
    product["enabled"] = enabled
    save(config)
    print(f"✔ {product_id} を{'有効化' if enabled else '停止'}しました。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="商品監視リストの管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="登録商品の一覧")

    p_add = sub.add_parser("add", help="商品を追加")
    p_add.add_argument("--id", required=True)
    p_add.add_argument("--url", required=True)
    p_add.add_argument("--name")
    p_add.add_argument("--currency", default=None)
    p_add.add_argument("--selector", default=None, help="価格の CSS セレクタ")
    p_add.add_argument("--regex", default=None, help="価格抽出の正規表現")
    p_add.add_argument("--target", type=float, default=None, help="目標価格（以下で通知）")
    p_add.add_argument("--test", action="store_true", help="追加前に抽出をテスト")

    p_rm = sub.add_parser("remove", help="商品を削除")
    p_rm.add_argument("--id", required=True)

    p_en = sub.add_parser("enable", help="商品を有効化")
    p_en.add_argument("--id", required=True)

    p_dis = sub.add_parser("disable", help="商品を一時停止")
    p_dis.add_argument("--id", required=True)

    args = parser.parse_args(argv)
    config = load()

    return {
        "list": cmd_list,
        "add": cmd_add,
        "remove": cmd_remove,
        "enable": lambda c, a: _set_enabled(c, a.id, True),
        "disable": lambda c, a: _set_enabled(c, a.id, False),
    }[args.cmd](config, args)


if __name__ == "__main__":
    sys.exit(main())
