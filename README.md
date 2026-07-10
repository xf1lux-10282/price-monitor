# 📈 価格モニター (price-monitor)

> 🔖 **作業を再開する人へ**: 続きから始める場合は、まず [RESUME.md](RESUME.md) を読んでください。
> 現在のステータス・未完了の作業・次の候補タスクをまとめてあります。

海外サイトを含む任意の商品ページの価格を **GitHub Actions で定期的にウォッチ**し、

- 価格を履歴ファイル（JSON）に記録
- 変動があれば **ntfy / Discord にプッシュ通知**（スマホ・PCのアプリに届く）
- **PWAダッシュボード**で価格推移グラフを表示（ホーム画面に追加してアプリのように使える）

を自動で行うツールです。商品は設定ファイルまたは CLI で **追加・削除**できます。

---

## 仕組み

```
GitHub Actions（cron: 1日6回）
   ├─ monitor.py: config.json の各商品URLをスクレイピング
   ├─ USD/JPY 為替を取得し、為替と円換算価格も記録 💴
   ├─ data/history/<id>.json に価格を追記
   ├─ 価格が変わったら ntfy / Discord に通知 📱
   ├─ data/index.json を更新
   └─ docs/（ダッシュボード）+ data/ を GitHub Pages に公開 📊
```

あわせて毎回 **USD/JPY 為替レート**を取得・記録し、USD建て商品は**円換算価格**も
保存します（注文タイミングの判断や、円コストでの振り返りに利用）。為替は記録のみで、
通知は「商品価格が変わった時」だけ出ます（為替は毎日動くため通知はしません）。

価格の抽出は次の優先順で判定します（最初に取れたものを採用）:
1. **サイズ指定**（`extract.variant`）… 変動商品（サイズ違い）で「25ml」など特定サイズの価格を
   WooCommerce の `form.variations_form` から確実に取得。**サイズが複数ある商品はこれを推奨**。
2. **メイン価格**（`extract.main_price`）… 関連商品カルーセル等を除外し、メイン商品の価格を取得。
3. ユーザー指定の **CSSセレクタ**（`extract.css_selector`）
4. ユーザー指定の **正規表現**（`extract.regex`）
5. **JSON-LD**（schema.org の `offers.price`）← 多くのECサイト（WooCommerce/Shopify等）に有効
6. **meta タグ**（`product:price:amount` 等）

> このリポジトリで監視中の Bostick & Sullivan は、サイズ違いの変動商品かつ JSON-LD 非搭載で、
> 関連商品カルーセルに同じ価格クラスが現れる作りのため、**①サイズ指定方式**を使っている
> （`config.json` の各商品 `extract.variant` に追跡サイズを指定）。経緯は変更履歴 #9/#11 を参照。

---

## セットアップ

### 1. 通知先を用意する（どちらか片方でOK、両方も可）

**ntfy（最も手軽・通知専用アプリ）**
1. スマホに [ntfy](https://ntfy.sh/) アプリ（iOS/Android）を入れる。PCはWebでもOK
2. 推測されにくいトピック名を決める（例 `price-7f3a9c-watch`）
3. アプリでそのトピックを購読

**Discord**
1. サーバー設定 → 連携サービス → ウェブフック → 新しいウェブフック → URLをコピー
2. Discordアプリ（スマホ/PC）で通知を受け取れます

### 2. GitHub Secrets に登録

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で登録:

| Secret 名 | 値 | 必須 |
|---|---|---|
| `NTFY_TOPIC` | 決めたトピック名 | ntfyを使うなら |
| `NTFY_SERVER` | `https://ntfy.sh`（自前サーバーなら変更） | 任意 |
| `DISCORD_WEBHOOK_URL` | Webhook URL | Discordを使うなら |

> Secrets は config.json より優先されます。URLやトピックをコードに残さず運用できます。

### 3. GitHub Pages を有効化（ダッシュボード用）

**Settings → Pages → Build and deployment → Source = GitHub Actions** を選択。

### 4. ワークフローを動かす

- 自動巡回（cron）は **デフォルトブランチ（master）のワークフローだけ**が対象です。
  `.github/workflows/price-monitor.yml` を master にマージすると定期実行が始まります。
- すぐ試すには **Actions タブ → 価格モニター → Run workflow**（手動実行）。

---

## 商品の追加・削除

`config.json` を直接編集してもよいですが、CLI が安全で簡単です。

```bash
cd price-monitor
pip install -r requirements.txt

# 一覧
python manage.py list

# 追加（最低限 id と url。価格抽出は自動。--test で事前確認）
python manage.py add --id sony-xm5 --name "Sony WH-1000XM5" \
    --url "https://example.com/item/123" --currency USD --target 350 --test

# 自動抽出が外れる場合は CSS セレクタを指定
python manage.py add --id foo --url "https://..." --selector ".product-price"

# 一時停止 / 再開 / 削除
python manage.py disable --id foo
python manage.py enable  --id foo
python manage.py remove  --id foo
```

| オプション | 意味 |
|---|---|
| `--id` | 一意なID（履歴ファイル名になる。英数字推奨） |
| `--url` | 商品ページのURL |
| `--name` | 表示名 |
| `--currency` | 通貨表記（`USD`/`JPY`/`GBP` 等。表示用） |
| `--target` | 目標価格。**この値以下になると追加通知** |
| `--selector` | 価格のCSSセレクタ（自動抽出が外れる時） |
| `--regex` | 価格抽出の正規表現（上級者向け） |
| `--test` | 追加前に実際に価格が取れるか確認 |

変更を `git push` すれば、次回の実行から反映されます。

---

## ローカルでの実行・確認

```bash
cd price-monitor
pip install -r requirements.txt

# 通知を飛ばしたい場合は環境変数で（未設定ならスキップされる）
export NTFY_TOPIC="price-7f3a9c-watch"
# export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

python monitor.py            # 全商品をチェック
python monitor.py --only foo # 特定商品だけ

# ダッシュボードをローカルで確認
python -m http.server 8000 --directory . # → http://localhost:8000/docs/
```

> 注: ダッシュボードは `data/` を `docs/` からの相対パスで読みます。ローカルでは
> リポジトリ直下で `http.server` を立てると `docs/` と `data/` の両方が見えます。

---

## ファイル構成

```
price-monitor/
├── config.json            # 監視対象・通知設定（ここを編集 or manage.py で操作）
├── monitor.py             # メイン: 取得→記録→通知
├── scraper.py             # 価格抽出ロジック（JSON-LD/meta/CSS/regex）
├── fx.py                  # USD/JPY 為替レート取得（多重フォールバック）
├── notifier.py            # ntfy / Discord 通知
├── storage.py             # 価格履歴の保存と index.json 生成
├── manage.py              # 商品の追加・削除・一覧 CLI
├── requirements.txt
├── data/
│   ├── index.json         # ダッシュボード用サマリ（自動生成）
│   ├── fx_usdjpy.json     # USD/JPY 為替の推移（自動生成）
│   └── history/<id>.json  # 商品ごとの価格履歴＋円換算（自動生成）
├── docs/                  # GitHub Pages で公開するPWAダッシュボード
│   ├── index.html
│   ├── manifest.json
│   ├── sw.js
│   └── icon-192.png / icon-512.png
└── tests/                 # ネットワーク不要のスクレイパーテスト
```

ワークフロー定義はリポジトリ直下の `.github/workflows/price-monitor.yml` です。

---

## 注意・既知の制約

- **頻度**: cron は既定で1日6回（日本時間 6:17/9:17/12:17/15:17/18:17/21:17）。短くしすぎると
  相手サイトに負荷をかけるので、常識的な間隔を推奨します。`price-monitor.yml` の `cron` で調整。
- **スケジュールの遅延**: GitHub Actions の定期実行はベストエフォートで、混雑時は遅延・スキップ
  されることがあります（毎時 :00 は特に混みやすいため :17 にずらしてあります）。
- **ボット対策**: Cloudflare等の強い対策があるサイトはHTMLが取得できないことがあります。
  その場合はサイト公式のAPIや、対象サイトの利用規約の範囲での利用を検討してください。
- **為替**: 毎回 USD/JPY を取得し、USD建て商品は円換算も記録します（表示・振り返り用。
  注文の最終判断は実レートをご確認ください）。
- robots.txt と各サイトの利用規約を尊重してください。

---

## トラブルシューティング

### GitHub Actions の定期実行(schedule)が動かない場合

GitHub Actions の schedule イベントは、以下の制約により意図通りに動作しないことがあります：

**既知の制約:**
- schedule は**デフォルトブランチ（通常 main または master）のワークフローファイルだけ**を対象とします
  - 他のブランチに `.github/workflows/price-monitor.yml` があっても無視されます
- リポジトリが**非公開（private）**の場合、無料プランでは schedule は動作しません
- 初回の schedule 実行には**最大1時間程度の遅延**があることがあります
- GitHub Actions の schedule は**ベストエフォート**で、混雑時は遅延・スキップされることがあります
  - 毎時 `:00` は最も混雑しやすい時刻です（このワークフローは `:17` にずらしてあります）

**対処法:**
1. リポジトリを**公開（public）**にする（Settings → General → Danger Zone → Change visibility）
2. ワークフローファイルが**デフォルトブランチ**にマージされていることを確認
3. 初回実行は手動で「Actions → 価格モニター → Run workflow」を実行して待つ
4. 数日待っても schedule が動かない場合は、外部トリガーの利用を検討：

**外部トリガーで確実に定期実行する方法:**

GitHub Actions の schedule が不安定な場合、以下の外部サービスから repository_dispatch イベントをトリガーして定期実行を確保できます：

1. **GitHub Workflow を repository_dispatch に対応させる**（既に対応済み）
   - `price-monitor.yml` は `repository_dispatch` イベントで起動できるようになっています

2. **外部トリガーサービスを選ぶ**

   **オプションA: GitHub Actions の別リポジトリから呼ぶ**（無料・最も確実）
   ```yaml
   # 別の public リポジトリの .github/workflows/trigger.yml
   name: Trigger Price Monitor
   on:
     schedule:
       - cron: '17 21,0,3,6,9,12 * * *'
   jobs:
     trigger:
       runs-on: ubuntu-latest
       steps:
         - uses: peter-evans/repository-dispatch@v3
           with:
             token: ${{ secrets.PAT_TOKEN }}
             repository: xf1lux-10282/price-monitor
             event-type: check-prices
   ```
   - Personal Access Token (PAT) を作成し、別リポジトリの Secrets に登録する必要があります

   **オプションB: cron-job.org（無料・簡単）**
   1. https://cron-job.org でアカウント作成
   2. 新規ジョブ作成で以下を設定：
      - URL: `https://api.github.com/repos/xf1lux-10282/price-monitor/dispatches`
      - HTTP Method: `POST`
      - Headers:
        ```
        Accept: application/vnd.github.v3+json
        Authorization: Bearer YOUR_GITHUB_TOKEN
        ```
      - Body:
        ```json
        {"event_type": "check-prices"}
        ```
      - Schedule: `17 */3 * * *`（3時間ごと、17分に実行）

   **オプションC: EasyCron（無料枠あり）**
   - https://www.easycron.com で同様の設定

3. **GitHub Personal Access Token (PAT) を作成**
   1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token
   2. Scopes: `repo`（full control）にチェック
   3. 生成されたトークンを外部サービスに登録

4. **動作確認**
   - 外部サービスのジョブを手動実行してテスト
   - GitHub Actions タブで `repository_dispatch` イベントの実行が表示されることを確認

> 💡 外部トリガーを使うことで、GitHub Actions の schedule の制約を回避し、確実に定期実行できます。

---

## 変更履歴（開発記録）

詳細な経緯・意思決定は `obsidian/DailyNotes/2026/06/2026-06-06.md` を参照。

| PR | 日付 | 内容 |
|---|---|---|
| #1 | 2026-06-06 | 初版。価格の定期ウォッチ一式（自動抽出・複数商品CLI・ntfy/Discord通知・PWAダッシュボード・GitHub Actions） |
| — | 2026-06-06 | 監視サイトが JSON-LD 非搭載のため、CSSセレクタ `.usg_product_field_3` を指定して抽出に対応 |
| — | 2026-06-06 | チェック時刻を日本時間 6/9/12/15/18/21時に設定 |
| — | 2026-06-06 | USD/JPY 為替の取得・記録と円換算（通知・グラフにも反映） |
| #2 | 2026-06-06 | ダッシュボードのグラフ改善（日付軸・期間切替 1ヶ月/3ヶ月/1年/全期間・左右スクロール） |
| #3 | 2026-06-06 | 定期実行の信頼性向上のため cron を `:00` → `:17` にずらす |
| #4 | 2026-06-06 | PWAキャッシュ修正（HTML/データを network-first 化・キャッシュ v2）。更新が確実に反映されるように |
| #5 | 2026-06-06 | 開発履歴・RESUME の整備 |
| — | 2026-06-06 | **第3セッション**: 本番初回実行（ntfy/Discord Secrets設定・GitHub Pages有効化）、期間切替ボタンの動作修正（Chart.jsズームプラグインとの競合を `chart.resetZoom()` + `chart.zoomScale()` で解消）、アプリケーション資料整備 |
| #7 | 2026-06-06 | **定期実行を外部トリガーで確実化**。GitHub の schedule が全枠スキップされる問題に対し、外部cron（cron-job.org）から workflow_dispatch API を叩く方式を導入（手順: `EXTERNAL_TRIGGER.md`）。GitHub cron は予備として残置 |
| #9 | 2026-06-06 | **価格誤取得の修正(1)**。`.usg_product_field_3` が関連商品カルーセルの別商品を拾っていた問題に対し、カルーセルを除外してメイン価格を取る `_from_main_price` を追加 |
| #11 | 2026-06-06 | **価格誤取得の修正(2・最終)**。変動商品で最小サイズの最安値を拾う問題を解消。`form.variations_form` から**指定サイズ(`extract.variant`)の価格**を取得する `_from_variation` を追加。正しい価格を実機検証（Na2 10ml=$170.30 / Pt#3 25ml=$375.00 / Pd#3 25ml=$200.77）。旧履歴はリセット |
| #13 | 2026-06-07 | **断続ブロック対策**。高頻度アクセスでサイトが時々商品データ無しのページを返し取得失敗→失敗通知が多発。対策として①取得を指数バックオフで最大3回リトライ ②商品間に小休止 ③1件でも取れれば成功扱い（全件失敗時のみ異常終了）。あわせて巡回頻度を3時間おきに（cron-job.org側設定） |
| #14 | 2026-06-07 | **参考指標を追加**。プラチナ/パラジウムの地金スポット価格(Yahoo→stooqフォールバックでUSD/ozを取得)とUSD/JPYをダッシュボードに「参考指標」セクションとして追加（購入商品ではなく相場の参考）。`metals.py` 追加 |
| #16 | 2026-06-07 | 参考指標の金属表示を **円/g のみ**に変更（日本の地金表示単位に統一。データには USD/oz も保持）。SWキャッシュ v4 |

> 本番稼働中。定期実行は外部トリガー（cron-job.org・3時間おき）。価格は商品ごとに指定サイズを正確に取得（実機検証済み）。断続的なサイトブロックにはリトライで耐性。
