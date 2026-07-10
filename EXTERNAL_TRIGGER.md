# 外部トリガーで定期実行を確実化する手順

GitHub Actions の `schedule`（cron）は**ベストエフォートで、スロットがまるごと
スキップされる**ことがある（実際この価格モニターでも初日は一度も発火しなかった）。
そこで、**外部の無料 cron サービスから GitHub の API を叩いてワークフローを起動**し、
定期実行を確実にする。

```
外部cronサービス（cron-job.org など）
   │  毎日 決まった時刻に HTTP POST
   ▼
GitHub API: workflow_dispatch エンドポイント
   ▼
「価格モニター」ワークフローが起動（手動実行と同じ扱い）
```

> ワークフロー側の変更は不要（既に `workflow_dispatch` 対応済み）。GitHub の cron も
> 残してあるので、稀に発火すれば二重に動くが、価格データが1点増えるだけで無害。

---

## ステップ1: GitHub の Fine-grained トークンを作成

最小権限（このリポジトリの Actions だけ）で作る。

1. GitHub → 右上アイコン → **Settings**
2. 左下 **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
3. **Generate new token**
   - **Token name**: `price-monitor-trigger`（任意）
   - **Expiration**: 任意（例: 1年。期限切れ時は作り直し）
   - **Resource owner**: `xf1lux-10282`
   - **Repository access**: **Only select repositories** → `xf1lux-10282/price-monitor` を選択
   - **Permissions** → **Repository permissions** → **Actions** を **Read and write** に設定
     （他は No access のままでよい）
4. **Generate token** → 表示された `github_pat_...` を**コピー**（一度しか表示されない）

> ⚠️ このトークンはパスワード同様。外部サービスにのみ貼り、他人に渡さない。
> 不要になったら同じ画面でいつでも **Revoke**（無効化）できる。

---

## ステップ2: cron-job.org でジョブを作成（無料）

1. <https://cron-job.org> に登録（無料）してログイン
2. **CREATE CRONJOB**
3. **Common（基本）**
   - **Title**: `price-monitor trigger`
   - **URL**:
     ```
     https://api.github.com/repos/xf1lux-10282/price-monitor/actions/workflows/price-monitor.yml/dispatches
     ```
4. **Schedule（実行時刻）**
   - タイムゾーンを **Asia/Tokyo** に設定
   - **1時間毎**（毎時0分など）に設定する（2026-07-10 本人決定＝旧15分毎から是正）
     ※外部トリガーなので「毎時ちょうど」でも混雑の影響を受けにくい
     ※cron-job.org の「Every hour」プリセット、または分=0・時=* で設定
5. **Advanced（詳細設定）** を開く
   - **Request method**: `POST`
   - **Headers**（ヘッダーを3つ追加）:
     | Key | Value |
     |---|---|
     | `Accept` | `application/vnd.github+json` |
     | `Authorization` | `Bearer github_pat_ここに貼る` |
     | `X-GitHub-Api-Version` | `2022-11-28` |
   - **Request body**:
     ```json
     {"ref":"master"}
     ```
   - **Treat as success / 成功判定**: HTTP ステータス **204** を成功とみなす
     （GitHub の dispatch は成功時に `204 No Content` を返す。cron-job.org は既定で
     2xx を成功扱いするので通常そのままでOK）
6. **CREATE** で保存

---

## ステップ3: 動作テスト

1. cron-job.org のジョブ画面で **「Run now / テスト実行」** を押す
   （または保存後の最初のスケジュールを待つ）
2. GitHub → リポジトリ → **Actions** → 「価格モニター」に、新しい実行が
   **event: workflow_dispatch** で出れば成功
3. 数十秒で完了し、`data/history/*.json` に新しい価格点が追記される

> うまくいかない時のチェック:
> - 401/403 → トークンの権限（Actions: Read and write）や期限切れを確認
> - 404 → URL のリポジトリ名・ワークフローファイル名（`price-monitor.yml`）を確認
> - Body が空 → `{"ref":"master"}` が送られているか確認

---

## 補足

- **GitHub の cron は残してある**（`.github/workflows/price-monitor.yml` の `schedule`）。
  外部トリガーが主、GitHub cron は予備。両方走っても無害（concurrency 設定で衝突回避）。
- 外部サービスは cron-job.org 以外でも可（Google Cloud Scheduler、Make/Zapier など。
  「指定時刻に、認証ヘッダー付きで HTTP POST できる」サービスなら何でもよい）。
- トークンを使わずに済ませたい場合は、GitHub cron の枠を増やして（例: 2〜3時間ごと）
  ドロップされても日に数回は通る確率を上げる、という妥協案もある。
