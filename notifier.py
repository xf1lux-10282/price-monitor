"""価格変動の通知。ntfy.sh と Discord Webhook に対応。

設定は config.json の settings.ntfy / settings.discord、または環境変数:
  - NTFY_SERVER  (既定 https://ntfy.sh)
  - NTFY_TOPIC
  - DISCORD_WEBHOOK_URL
環境変数があれば config.json より優先する（Secrets 運用向け）。
"""

from __future__ import annotations

import os

import requests


def _resolve(settings: dict) -> tuple[dict, dict]:
    ntfy = dict(settings.get("ntfy", {}))
    discord = dict(settings.get("discord", {}))

    if os.environ.get("NTFY_TOPIC"):
        ntfy["topic"] = os.environ["NTFY_TOPIC"]
        ntfy["enabled"] = True
    if os.environ.get("NTFY_SERVER"):
        ntfy["server"] = os.environ["NTFY_SERVER"]
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        discord["webhook_url"] = os.environ["DISCORD_WEBHOOK_URL"]
        discord["enabled"] = True
    return ntfy, discord


def send_ntfy(ntfy: dict, *, title: str, message: str, url: str | None, priority: str) -> bool:
    topic = (ntfy.get("topic") or "").strip()
    if not ntfy.get("enabled") or not topic:
        return False
    server = (ntfy.get("server") or "https://ntfy.sh").rstrip("/")
    headers = {
        "Title": title.encode("utf-8"),
        "Priority": priority,
        "Tags": "moneybag",
    }
    if url:
        headers["Click"] = url
    try:
        resp = requests.post(
            f"{server}/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"  [ntfy] 送信失敗: {exc}")
        return False


def send_discord(discord: dict, *, title: str, message: str, url: str | None, color: int) -> bool:
    webhook = (discord.get("webhook_url") or "").strip()
    if not discord.get("enabled") or not webhook:
        return False
    embed = {"title": title, "description": message, "color": color}
    if url:
        embed["url"] = url
    payload = {"embeds": [embed]}
    try:
        resp = requests.post(webhook, json=payload, timeout=15)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"  [discord] 送信失敗: {exc}")
        return False


def _fx_note(currency: str, usdjpy, price_jpy) -> str:
    if usdjpy is None or price_jpy is None or currency == "JPY":
        return ""
    return f"\n参考: 1 USD = {usdjpy:.2f} 円 ≒ ¥{price_jpy:,}"


def notify_change(
    settings: dict, *, product: dict, old, new, currency: str, usdjpy=None, price_jpy=None
) -> None:
    """価格変動を全チャンネルに通知する。"""
    ntfy, discord = _resolve(settings)
    name = product.get("name") or product.get("id")
    url = product.get("url")
    fx_note = _fx_note(currency, usdjpy, price_jpy)

    if old is None:
        title = f"📈 価格の監視を開始: {name}"
        body = f"現在価格: {new:,.2f} {currency}{fx_note}"
        priority, color = "default", 0x3498DB
    else:
        diff = new - old
        arrow = "🔻 値下がり" if diff < 0 else "🔺 値上がり"
        pct = (diff / old * 100) if old else 0
        title = f"{arrow}: {name}"
        body = (
            f"{old:,.2f} → {new:,.2f} {currency}\n"
            f"差額: {diff:+,.2f} {currency} ({pct:+.1f}%)"
            f"{fx_note}"
        )
        priority = "high" if diff < 0 else "default"
        color = 0x2ECC71 if diff < 0 else 0xE74C3C

    sent_ntfy = send_ntfy(ntfy, title=title, message=body, url=url, priority=priority)
    sent_discord = send_discord(discord, title=title, message=body, url=url, color=color)
    channels = [c for c, ok in (("ntfy", sent_ntfy), ("discord", sent_discord)) if ok]
    if channels:
        print(f"  通知送信: {', '.join(channels)}")
    else:
        print("  通知先が未設定のためスキップ（NTFY_TOPIC / DISCORD_WEBHOOK_URL を設定してください）")


def notify_target_reached(settings: dict, *, product: dict, price: float, target: float, currency: str) -> None:
    ntfy, discord = _resolve(settings)
    name = product.get("name") or product.get("id")
    url = product.get("url")
    title = f"🎯 目標価格に到達: {name}"
    body = f"現在 {price:,.2f} {currency} ≤ 目標 {target:,.2f} {currency}"
    send_ntfy(ntfy, title=title, message=body, url=url, priority="max")
    send_discord(discord, title=title, message=body, url=url, color=0xF1C40F)
