# 投稿アクティビティ ダッシュボード

`daily_stats.csv` と `trip_daily_stats.csv` から、単体で動くHTMLダッシュボードを作ります。

## ファイル

| ファイル | 役割 |
|---|---|
| `daily_stats.csv` / `trip_daily_stats.csv` | 入力データ(定期更新される) |
| `template.html` | 画面(HTML/CSS/JS)。データは埋め込み位置 `/*__DATA__*/null` に入る |
| `build.py` | CSV を検証・集計して HTML を生成する |
| `.github/workflows/pages.yml` | GitHub Pages へ自動公開する設定 |

## ローカルで確認する

```powershell
python build.py            # dashboard.html を生成
python build.py --help     # オプション一覧
```

生成された `dashboard.html` をブラウザで開くだけで見られます。

## 公開の仕組み

次のどれかが起きるたびに、GitHub Actions が `build.py` を実行して GitHub Pages を更新します。

- CSV / `build.py` / `template.html` が `main` ブランチに push された
- 6時間ごとの定期実行(毎日 0:20, 6:20, 12:20, 18:20 UTC = 日本時間 9:20, 15:20, 21:20, 3:20)
- Actions タブからの手動実行

CSV が壊れている(列不足・数値以外・日付の欠損など)場合はビルドが失敗し、公開中のページは前の版のまま残ります。

## 初回セットアップ(GitHub アカウントが無い場合)

1. https://github.com でアカウントを作成する(無料)。
2. 右上の「+」→「New repository」で新しいリポジトリを作る。
   - Repository name: 例 `dashboard`
   - **Public** を選ぶ(無料プランの GitHub Pages は Public が必要)
3. 作成後の画面で「uploading an existing file」を選び、この作業フォルダの中身を全部ドラッグ&ドロップする。
   - `.github` フォルダ(中に `workflows/pages.yml`)も含めること。フォルダごとドロップできない場合は、
     「Add file → Create new file」でファイル名欄に `.github/workflows/pages.yml` と入力し、内容を貼り付ける。
   - `dashboard.html` は不要(アップロードしなくてよい)。
   - 「Commit changes」を押す(ブランチは `main`)。
4. リポジトリの「Settings → Pages」を開き、「Build and deployment → Source」を **GitHub Actions** にする。
5. 「Actions」タブを開き、「Build and deploy dashboard」が緑になるのを待つ。動いていなければ
   左の一覧から選んで「Run workflow」を押す。
6. 完了すると `https://<ユーザー名>.github.io/<リポジトリ名>/` で公開される。

## CSV の更新

- リポジトリ上で `daily_stats.csv` / `trip_daily_stats.csv` を置き換えてコミットすれば、自動で反映されます。
- 別のワークフローや外部の仕組みから CSV をコミットする場合、`GITHUB_TOKEN` によるコミットでは
  この設定は起動しません(GitHub の仕様)。その場合も6時間ごとの定期実行で反映されます。
  すぐ反映したいときは、CSV を更新する側から `workflow_dispatch` でこのワークフローを呼んでください。

## 注意

- 公開ページには、**全トリップの文字列とランキングが含まれます**(誰でも閲覧・検索・保存できます)。
  伏せたい場合は `.github/workflows/pages.yml` のビルド行を
  `python build.py --no-trips --out _site/index.html` に変更してください。
- GitHub の無料プランでは、Public リポジトリなので CSV そのものも誰でも閲覧できます。
- Public リポジトリは、60日間なにも更新がないと定期実行が自動停止されます(CSV が更新されていれば問題ありません)。
- 最新日は集計途中の可能性があるため、その日を含む期間の日次グラフは低めに出ます。
  除外する場合はビルド行に `--exclude-today` を追加してください。
