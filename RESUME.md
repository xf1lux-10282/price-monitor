# 🔖 プライスモニター 引き継ぎメモ（続きから再開するための入口）

> **「プライスモニターの続きをお願い」と言われたら、まずこのファイルを読んでください。**
> このリポジトリは毎回クローンし直す使い捨て環境で動くため、再開に必要な情報は
> すべてここ（とコミット履歴）に集約しています。

最終更新: 2026-06-07（第4セッション） / 作業ブランチ: `claude/product-price-monitoring-rmZQy`

---

## 1. これは何か

海外サイトの商品価格を **GitHub Actions で定期ウォッチ**し、変動を **ntfy / Discord** に
通知、価格と **USD/JPY 為替** を記録して **PWAダッシュボード** でグラフ表示するツール。
全体像・使い方は [README.md](README.md) を参照。

---

## 2. 現在のステータス（2026-06-06 第3セッション終了時点）

**🟢 本番稼働中。** 定期実行は外部トリガーで確実化、価格取得バグも修正・検証済み。

- ✅ PR #1〜#11 を master へマージ・Pages デプロイ済み
  - #1 本体 / #2 グラフ改善 / #3 cron:17 / #4 PWAキャッシュ修正
  - #7 外部トリガー手順 / #9 関連商品の誤取得修正 / #11 サイズ指定取得（最終）
- ✅ **定期実行を外部トリガーで確実化**（GitHubのcronは初日全スキップ＝既知のベストエフォート問題）
  - cron-job.org → GitHub workflow_dispatch API を叩いて起動。**設定済み・204成功・実行確認済み**。
  - 手順: [EXTERNAL_TRIGGER.md](EXTERNAL_TRIGGER.md)。トークンは Fine-grained（Actions:RW / 対象リポのみ / 期限2026-09-27、2026-06-29 再生成）。値は cron-job.org のヘッダーにのみ保持（リポジトリには置かない）。
  - GitHub の cron（`17 21,0,3,6,9,12 * * *`）は予備として残置。
- ✅ **価格取得バグを修正（重要）**。正しい価格を実機検証済み:
  | id | 商品 | 追跡サイズ | 価格 | 取得方式 |
  |---|---|---|---|---|
  | `bs-na2-platinum-20` | Sodium Platinum (Na2) 20% | 10ml | **$170.30** | `variation:10ml` |
  | `bs-platinum-3-25` | Platinum Solution #3 | 25ml | **$375.00** | `variation:25ml` |
  | `bs-palladium-3-25` | Palladium Solution #3 | 25ml | **$200.77** | `variation:25ml` |
  - 為替も記録中（例: 1$≈160.19）。**出典は Yahoo Finance に統一**（地金と同じ。旧 open.er-api.com から変更、PR #24）。
    Yahoo はほぼリアルタイム。落ちた時のみ er-api/frankfurter にフォールバック。円換算(price_jpy)・金属の円/gにも反映。
- ✅ ダッシュボードのグラフ改善（日付軸・**ネイティブ横スクロール**・期間 全体/1年/3ヶ月/1ヶ月/1週間/3日）公開済み
  - スクロール方式: 全データを横長キャンバスに描画し、選んだ期間が1画面に収まるよう幅を調整、
    はみ出す分を `.chart-box` の横スクロールで見る（PR #20〜#22）。SWキャッシュは現在 v8。
  - ※当面（〜2026-06中旬）はデータ蓄積待ち。蓄積後に各期間のスクロールが活きる。
- ✅ PWA は network-first＋キャッシュ v2（シェル更新時は CACHE 版を上げる）

### 🐞 第3セッションで直したバグ（経緯：再発時の参考に）
対象サイト（bostick-sullivan.com＝WooCommerce + UpSolution"US"テーマ）特有の罠だった。
1. **当初** `css:.usg_product_field_3` は、商品ページ下部の**関連商品カルーセル(owl-carousel)**の
   カードにのみ付くクラスで、メインではなく**別商品の価格**を拾っていた（並びが変わり値がブレた）。
2. **中間修正**（`_from_main_price`：カルーセル除外でメイン価格を取得）は、変動商品の
   **最小サイズ＝最安値(from価格)**を拾うため、25ml商品が10ml価格になった。
3. **最終修正**（`_from_variation`）：`form.variations_form` の `data-product_variations` JSON から
   **指定サイズ(`extract.variant`)の `display_price`** を取得。これが正解。
   - サイズ別価格（参考・2026-06-06時点）:
     Pt#3 = 10ml$170.30/15ml$255.45/**25ml$375.00**/50ml$851.50/100ml$1703
     Pd#3 = 10ml$87.29/15ml$130.94/**25ml$200.77**/100ml$803.07/250ml$2007.67/500ml$4364.50
   - 旧履歴は全リセット済み（不正値が混在していたため）。

### 🆕 第4セッションの追加・修正（2026-06-07, PR #13〜#16）
- ✅ **断続ブロック対策**（PR #13, #15）：高頻度アクセスで対象サイトが時々「商品データ無しの
  ページ」を返し取得失敗→失敗メール多発、だった。対策：①取得を指数バックオフで最大3回リトライ
  （`scraper.fetch_price`）②商品間に小休止 ③**商品取得の失敗ではジョブを失敗させない（exit 0）**。
  為替・地金・index は常に保存。コード/設定の本当の異常だけ例外でジョブ失敗。
- ✅ **巡回頻度を3時間おきに**（cron-job.org 側 `0 */3 * * *` ＝ JST 0,3,6,…,21時／1日8回）。
  過剰アクセス＝ブロックの根本対策。GitHub cron（予備）はそのまま。
- ✅ **参考指標を追加**（PR #14, #16, #18）：購入商品とは別に、相場の参考として
  プラチナ/パラジウム/**銀**の地金スポット価格と USD/JPY をダッシュボードに表示。
  - `metals.py`：地金 USD/oz を取得（Yahoo `PL=F`/`PA=F`/`SI=F` → stooq フォールバック。**Yahooで取得実績あり**）。
  - 保存：`data/metals.json`（USD/oz と 円/g 両方を保持。円/g = USD/oz × USD/JPY ÷ 31.1034768）。
  - 表示：**金属は「円/g のみ」**（ユーザー指定。USD/ozはデータには残すが非表示）。USD/JPYは単独グラフ。
  - 実機値（2026-06-07）：プラチナ ¥9,085/g、パラジウム ¥6,312/g、銀 ¥347/g。
  - SWキャッシュは v5。金属の追加は `metals.py` の `_METALS` と `docs/index.html` のキー配列に1行ずつ足すだけ。

### ⏳ 残り（任意）
- 値動き発生時に ntfy/Discord 通知が実際に届くか（Secrets設定済みなら次の変動時に確認）。
- **追跡サイズを変えたい場合**は `config.json` の該当商品 `extract.variant` を変更するだけ
  （例: Pd#3 を 25ml→100ml）。表記ゆれ（`25ml`/`25 mL`）は正規化で吸収する。
- 参考指標で「USDも見たい」場合、`data/metals.json` に USD/oz が入っているので
  `docs/index.html` の `drawMetalChart`/`refMetalCard` に USD 系列を足すだけ。

> 💡 開発サンドボックスは外部サイト/為替API/CDN へ到達できない（許可リスト制）。
> 実取得の確認は GitHub Actions ランナー側で行うこと（ローカルの monitor.py 実行で
> 失敗しても、それは環境制約であってコードの問題ではない場合がある）。

---

## 3. 「続き」でやり得ること（バックログ / 着手候補）

優先度は状況次第。ユーザーの指示を優先しつつ、以下から選ぶ。

### A. 初回実行の結果対応（最優先候補）
- ユーザーが Run workflow を回した後、**価格抽出に失敗した商品があれば修正**する。
  - 失敗時の直し方: 対象ページのHTMLを見て価格のCSSセレクタを特定し、
    `python manage.py add` ではなく `config.json` の該当 `extract.css_selector` を設定、
    または一度 remove して `manage.py add --id ... --url ... --selector "..." --test`。
  - 為替取得が失敗していないかもログで確認（`fx.py` のフォールバックが効くか）。
- 監視: `gh run watch` または GitHub Actions 拡張、もしくは私（Claude）が
  `subscribe_pr_activity` 相当でCI/実行を見張る。

### B. 機能追加の候補
- [ ] **目標価格アラート**を使いたくなったら `config.json` の `target_price` を設定
      （現状は全商品 null。仕組みは実装済み）。
- [ ] **変化幅のしきい値**（例: ±1%未満は通知しない）オプション。
- [ ] **在庫状況**（在庫切れ/再入荷）の監視・通知（JSON-LD の `availability` を利用）。
- [ ] ダッシュボードに**全商品の比較ビュー**や**為替単体グラフ**（`data/fx_usdjpy.json` 利用）。
- [ ] 通知に**商品サムネイル画像**を添付（Discord embed）。
- [ ] **週次/月次サマリ**（「今週変動した商品」一覧）を Issue や通知で。
- [ ] 監視商品の追加（ユーザーが新URLを提示したら `manage.py add`）。

### C. 運用・品質
- [ ] スクレイパーのテストを増やす（Shopify型・楽天/Amazon型のフィクスチャ）。
- [ ] 取得失敗が続いた商品を自動で通知 or 一時停止する仕組み。

---

## 4. 再開時の実務メモ

- **作業ブランチ**: `claude/product-price-monitoring-rmZQy`（既に master へマージ済みだが、
  追加変更もこのブランチで行い、必要に応じてPRを作る運用）。
- **ローカル確認コマンド**:
  ```bash
  cd price-monitor
  pip install -r requirements.txt
  python tests/test_scraper.py     # ロジックテスト（ネット不要）
  python manage.py list            # 監視商品一覧
  python monitor.py                # 手動チェック（※外部到達できる環境でのみ実価格取得）
  ```
- **サンドボックスの制約**: 外部サイト/為替API/CDN へ到達できないことがある（許可リスト制）。
  実取得の確認は GitHub Actions ランナー側で行う。
- **デイリーノート**: 作業したら `obsidian/DailyNotes/YYYY/MM/YYYY-MM-DD.md` に
  会話要約を残す（`.claude/rules.md` のルール）。直近の詳細は
  [2026-06-06.md](../obsidian/DailyNotes/2026/06/2026-06-06.md)。

---

## 5. 主要ファイルの地図

| ファイル | 役割 |
|---|---|
| `config.json` | 監視対象・通知設定（ここを編集 or `manage.py`） |
| `monitor.py` | メイン: 取得→為替→記録→通知 |
| `scraper.py` | 価格抽出。優先順: `variation`(サイズ指定) → `main_price`(カルーセル除外) → css → regex → JSON-LD → meta |
| `fx.py` | USD/JPY 為替取得（多重フォールバック） |
| `metals.py` | 参考指標: プラチナ/パラジウム地金 USD/oz 取得（Yahoo→stooq） |
| `notifier.py` | ntfy / Discord 通知 |
| `storage.py` | 履歴・円換算・index.json 生成 |
| `manage.py` | 商品の追加/削除/一覧 CLI |
| `docs/` | PWAダッシュボード（GitHub Pages公開対象） |
| `data/` | 価格履歴・為替・index（Actionsが自動生成・コミット） |
| `../.github/workflows/price-monitor.yml` | 定期実行ワークフロー |
