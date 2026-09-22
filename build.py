"""CSV -> dashboard.html builder.

data/all_daily_stats.csv / data/all_trip_daily_stats.csv(無ければ直下の同名ファイル)を集計して
template.html に埋め込み、単体で開ける HTML を出力する。データを更新したら再実行するだけ。
入力の all_* は fetch_shitaraba_archive_stats.py の出力(過去ログ + 現行スレッドの合算)。
all_* が無い場合だけ、旧形式の daily_stats.csv / trip_daily_stats.csv(現行スレッドのみ)を使う。

あわせて、data/cache/anime_11224/recent_posts.jsonl (トリップ検索機能用、直近の投稿本文の
キャッシュ)から trip_posts.json を出力先と同じフォルダに書き出す。ページ側はトリップを
選んだときだけこのファイルを読み込む(常に埋め込むと初期表示が重くなるため)。
recent_posts.jsonl が無い場合はエラーにせず、0件として trip_posts.json を出力する。

    python build.py                       # dashboard.html を出力(最新日も含める)
    python build.py --out _site/index.html   # 出力先を指定(GitHub Pages 用)
    python build.py --exclude-today       # 当日(集計途中の可能性)を除外
    python build.py --no-trips            # トリップ文字列・投稿本文を出力に含めない(ランキングも非表示)

CSV が壊れている(列不足・数値以外・日付の欠損など)場合はエラー終了し、出力ファイルは更新しない。
"""
import argparse
import csv
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"  # 非公開リポジトリ(git submodule)。無ければ ROOT 直下の CSV を使う
PLACEHOLDER = "/*__DATA__*/null"
JST = dt.timezone(dt.timedelta(hours=9))  # 実行環境(GitHub Actions は UTC)によらず日本時間で判定する

DAILY_COLS = ["date", "post_count", "tripped_post_count", "unique_trip_count", "new_thread_count"]
TRIP_COLS = ["trip", "date", "post_count"]


def fail(msg):
    sys.exit(f"[error] {msg}")


def default_csv(*names):
    """names の先頭ほど優先。data/ → ROOT の順に探し、どれも無ければ先頭の名前(エラー表示用)を返す。"""
    for name in names:
        for base in (DATA_DIR, ROOT):
            if (base / name).exists():
                return base / name
    return ROOT / names[0]


def default_recent_posts():
    """トリップ検索用の直近投稿キャッシュ。data/ → ROOT の順に探す(無くてもエラーにしない)。"""
    rel = Path("cache") / "anime_11224" / "recent_posts.jsonl"
    for base in (DATA_DIR, ROOT):
        if (base / rel).exists():
            return base / rel
    return DATA_DIR / rel


def data_updated(path, fallback):
    """CSV が最後に更新された日時(JST)。CSV を置いている git リポジトリでの最終コミット日時を使う
    (GitHub Actions では checkout 時刻がファイルの更新時刻になってしまうため)。取れなければ fallback。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(path.parent), "log", "-1", "--format=%cI", "--", path.name],
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
        return dt.datetime.fromisoformat(out).astimezone(JST)
    except (OSError, subprocess.SubprocessError, ValueError):
        return fallback


def read_csv(path, cols):
    if not path.exists():
        fail(f"{path} が見つかりません。")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in cols if c not in (reader.fieldnames or [])]
        if missing:
            fail(f"{path.name} に必要な列がありません: {', '.join(missing)}")
        rows = list(reader)
    if not rows:
        fail(f"{path.name} にデータ行がありません。")
    return rows


def to_int(row, col, path, line):
    try:
        v = int(row[col])
    except (TypeError, ValueError):
        fail(f"{path.name} {line}行目: {col} が整数ではありません ({row[col]!r})")
    if v < 0:
        fail(f"{path.name} {line}行目: {col} が負の値です ({v})")
    return v


def to_date(s, path, line):
    try:
        return dt.date.fromisoformat(s).isoformat()
    except (TypeError, ValueError):
        fail(f"{path.name} {line}行目: 日付が YYYY-MM-DD 形式ではありません ({s!r})")


def build_trip_posts(path: Path):
    """recent_posts.jsonl(スレッド単位)から、トリップ別の投稿一覧(新しい順)を作る。
    ファイルが無い/読めない場合はエラーにせず、0件として扱う
    (機能導入直後や backfill 未実行の環境でもビルド自体は止めないため)。
    戻り値は (トリップ文字列 -> 投稿リスト の dict, 読み込んだスレッド数)。"""
    by_trip = {}
    threads = 0
    if not path.exists():
        return by_trip, threads
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            threads += 1
            tid = rec.get("thread_id")
            for p in rec.get("posts", ()):
                trip = p.get("trip")
                if not trip:
                    continue
                by_trip.setdefault(trip, []).append({
                    "date": p.get("date"), "time": p.get("time"),
                    "thread_id": tid, "no": p.get("no"), "body": p.get("body"),
                })
    for posts in by_trip.values():
        posts.sort(key=lambda p: (p["date"] or "", p["time"] or ""), reverse=True)
    return by_trip, threads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", type=Path, default=default_csv("all_daily_stats.csv", "daily_stats.csv"))
    ap.add_argument("--trips-csv", type=Path, default=default_csv("all_trip_daily_stats.csv", "trip_daily_stats.csv"))
    ap.add_argument("--recent-posts", type=Path, default=default_recent_posts(),
                     help="トリップ検索用の直近投稿キャッシュ(recent_posts.jsonl)")
    ap.add_argument("--template", type=Path, default=ROOT / "template.html")
    ap.add_argument("--out", type=Path, default=ROOT / "dashboard.html")
    ap.add_argument("--exclude-today", action="store_true", help="今日の日付(集計途中の可能性)を除外する")
    ap.add_argument("--no-trips", action="store_true",
                     help="トリップ文字列・投稿本文を出力に含めない(ランキングも投稿検索も非表示)")
    args = ap.parse_args()

    now = dt.datetime.now(JST)
    today = now.date().isoformat()

    raw = read_csv(args.daily, DAILY_COLS)
    daily = []
    for n, r in enumerate(raw, start=2):
        daily.append({
            "date": to_date(r["date"], args.daily, n),
            **{c: to_int(r, c, args.daily, n) for c in DAILY_COLS[1:]},
        })
    daily.sort(key=lambda r: r["date"])
    if len({r["date"] for r in daily}) != len(daily):
        fail(f"{args.daily.name} に重複した日付があります。")

    excluded = None
    partial = daily[-1]["date"] >= today
    if args.exclude_today and partial and len(daily) > 1:
        excluded = daily[-1]["date"]
        daily = daily[:-1]
        partial = False

    dates = [r["date"] for r in daily]
    index = {d: i for i, d in enumerate(dates)}

    # 欠損日チェック(連続した暦であることをフロントは前提にしている)
    d0, d1 = dt.date.fromisoformat(dates[0]), dt.date.fromisoformat(dates[-1])
    if (d1 - d0).days + 1 != len(dates):
        fail(f"{args.daily.name} に欠損日があります。連続した日付が必要です。")

    trip_ids = {}
    trip_days = [[] for _ in dates]  # 日ごとの [トリップ連番, 投稿数, ...]
    skipped = 0
    for n, r in enumerate(read_csv(args.trips_csv, TRIP_COLS), start=2):
        date = to_date(r["date"], args.trips_csv, n)
        cnt = to_int(r, "post_count", args.trips_csv, n)
        i = index.get(date)
        if i is None:
            skipped += 1  # 除外日、または daily に無い日
            continue
        tid = trip_ids.setdefault(r["trip"], len(trip_ids))
        trip_days[i].extend((tid, cnt))

    # 2ファイルの整合性チェック(警告のみ)
    warn = 0
    for i, r in enumerate(daily):
        pairs = trip_days[i]
        if len(pairs) // 2 != r["unique_trip_count"] or sum(pairs[1::2]) != r["tripped_post_count"]:
            warn += 1
    if warn:
        print(f"[warn] daily_stats と trip_daily_stats が一致しない日が {warn} 日あります", file=sys.stderr)
    if skipped and not excluded:
        print(f"[warn] daily_stats に無い日付のトリップ行を {skipped} 行スキップしました", file=sys.stderr)

    data = {
        "meta": {
            "generated": now.strftime("%Y-%m-%d %H:%M") + " JST",
            "updated": data_updated(args.daily, now).strftime("%Y-%m-%d %H:%M") + " JST",  # データの最終更新(右上に表示)
            "first": dates[0],
            "last": dates[-1],
            "excluded": excluded,
            "partial": partial,
            "trips": len(trip_ids),
        },
        "tripNames": None if args.no_trips else list(trip_ids),  # dict は挿入順 = 連番順
        "dates": dates,
        "posts": [r["post_count"] for r in daily],
        "tripped": [r["tripped_post_count"] for r in daily],
        "uniqueTrips": [r["unique_trip_count"] for r in daily],
        "threads": [r["new_thread_count"] for r in daily],
        "tripDays": trip_days,
    }

    html = args.template.read_text(encoding="utf-8")
    if PLACEHOLDER not in html:
        fail("template.html にデータ埋め込み位置がありません。")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html.replace(PLACEHOLDER, payload), encoding="utf-8")

    print(f"OK {args.out}: {dates[0]} - {dates[-1]} ({len(dates)}日, トリップ{len(trip_ids)}件, {args.out.stat().st_size/1024:.0f}KB)")
    print(f"   入力: {args.daily} / {args.trips_csv}")
    if excluded:
        print(f"   {excluded} は集計途中の可能性があるため除外しました")
    elif partial:
        print(f"   {dates[-1]} は集計途中の可能性があります (--exclude-today で除外)")
    if args.no_trips:
        print("   トリップ文字列は含めていません")

    trip_posts_path = args.out.parent / "trip_posts.json"
    if args.no_trips:
        if trip_posts_path.exists():
            trip_posts_path.unlink()
        print("   投稿本文(trip_posts.json)も出力しません(--no-trips)")
    else:
        by_trip, threads_read = build_trip_posts(args.recent_posts)
        trip_posts_payload = json.dumps(by_trip, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
        trip_posts_path.write_text(trip_posts_payload, encoding="utf-8")
        total_posts = sum(len(v) for v in by_trip.values())
        print(f"OK {trip_posts_path}: {len(by_trip)}トリップ, 投稿{total_posts}件, "
              f"{trip_posts_path.stat().st_size/1024:.0f}KB (元スレッド{threads_read}件)")
        if not args.recent_posts.exists():
            print(f"   [注意] {args.recent_posts} が見つからないため0件で出力しました。"
                  f"backfill-recent-posts、または update を実行すると作られます。")


if __name__ == "__main__":
    main()
