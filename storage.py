"""価格履歴の永続化。商品ごとに data/history/<id>.json を持つ。

履歴フォーマット:
{
  "id": "...",
  "name": "...",
  "url": "...",
  "currency": "JPY",
  "points": [
    {"t": "2026-06-05T09:00:00Z", "price": 1234.0, "method": "json-ld:price"}
  ]
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
HISTORY_DIR = DATA_DIR / "history"


def _history_path(product_id: str) -> Path:
    return HISTORY_DIR / f"{product_id}.json"


def load_history(product_id: str) -> dict:
    path = _history_path(product_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"id": product_id, "points": []}


def last_price(history: dict) -> float | None:
    points = history.get("points") or []
    return points[-1]["price"] if points else None


def to_jpy(price: float, currency: str, usdjpy: float | None) -> float | None:
    """円換算価格を求める。USD は為替で換算、JPY はそのまま。"""
    if price is None:
        return None
    if currency == "JPY":
        return round(price)
    if currency == "USD" and usdjpy:
        return round(price * usdjpy)
    return None


def append_point(
    product: dict, price: float, method: str, currency: str, usdjpy: float | None = None
) -> dict:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history = load_history(product["id"])
    history["id"] = product["id"]
    history["name"] = product.get("name")
    history["url"] = product.get("url")
    history["currency"] = currency
    point = {
        "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "price": price,
        "method": method,
    }
    if usdjpy is not None:
        point["fx_usdjpy"] = round(usdjpy, 4)
    price_jpy = to_jpy(price, currency, usdjpy)
    if price_jpy is not None:
        point["price_jpy"] = price_jpy
    history.setdefault("points", []).append(point)
    _history_path(product["id"]).write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return history


# 1 トロイオンス = 31.1034768 グラム（地金の円/g換算に使う）
GRAMS_PER_TROY_OUNCE = 31.1034768


def usd_oz_to_jpy_g(usd_per_oz: float, usdjpy: float | None) -> int | None:
    """USD/トロイオンス → 円/グラム（日本での地金表示単位）。"""
    if usd_per_oz is None or not usdjpy:
        return None
    return round(usd_per_oz * usdjpy / GRAMS_PER_TROY_OUNCE)


def record_metals(metals: list, usdjpy: float | None) -> None:
    """地金（プラチナ・パラジウム）の推移を data/metals.json に記録する。

    各点: USD/oz（国際標準）と 円/g（日本の地金表示）を保存。
    metals は metals.MetalResult のリスト。
    """
    if not metals:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "metals.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    t = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for m in metals:
        entry = data.setdefault(m.key, {"label": m.label, "unit": "USD/oz", "points": []})
        entry["label"] = m.label
        point = {"t": t, "usd": round(m.usd, 2), "source": m.source}
        jpy_g = usd_oz_to_jpy_g(m.usd, usdjpy)
        if jpy_g is not None:
            point["jpy_g"] = jpy_g
        entry.setdefault("points", []).append(point)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record_fx(usdjpy: float, source: str) -> None:
    """USD/JPY の推移を独立した系列としても記録する（為替単体の振り返り用）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "fx_usdjpy.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"pair": "USD/JPY", "points": []}
    data.setdefault("points", []).append(
        {
            "t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "usdjpy": round(usdjpy, 4),
            "source": source,
        }
    )
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_index(products: list[dict]) -> None:
    """ダッシュボード用の一覧 index.json を書き出す。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    index = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "products": []}

    fx_path = DATA_DIR / "fx_usdjpy.json"
    if fx_path.exists():
        fx_points = json.loads(fx_path.read_text(encoding="utf-8")).get("points") or []
        index["fx_usdjpy"] = fx_points[-1]["usdjpy"] if fx_points else None
    else:
        index["fx_usdjpy"] = None

    for product in products:
        history = load_history(product["id"])
        points = history.get("points") or []
        latest = points[-1] if points else None
        first = points[0] if points else None
        index["products"].append(
            {
                "id": product["id"],
                "name": product.get("name"),
                "url": product.get("url"),
                "currency": history.get("currency") or product.get("currency"),
                "enabled": product.get("enabled", True),
                "target_price": product.get("target_price"),
                "latest_price": latest["price"] if latest else None,
                "latest_time": latest["t"] if latest else None,
                "latest_price_jpy": latest.get("price_jpy") if latest else None,
                "latest_fx": latest.get("fx_usdjpy") if latest else None,
                "first_price": first["price"] if first else None,
                "points": len(points),
            }
        )
    (DATA_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
