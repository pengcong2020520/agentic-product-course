"""抓取 App Store（中国区）公开评论，汇成原始数据集。

数据来源是 Apple 公开的评论 RSS（每个应用、每种排序最多 10 页 × 50 条）。
只保存评论本身，不保存评论者昵称；结果写入 data/raw/（不进仓库）。

用法：python pipeline/crawl/appstore_reviews.py [--apps pipeline/crawl/apps.json] [--out data/raw/appstore_reviews.jsonl]
"""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FEED = "https://itunes.apple.com/cn/rss/customerreviews/page={page}/id={app_id}/sortby={sort}/json"
SORTS = ("mostrecent", "mosthelpful")
MAX_PAGES = 10
DELAY_SECONDS = 1.5
UA = "agentic-product-course/0.1 (course research)"


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries - 1:
                print(f"  放弃 {url}: {exc}")
                return None
            time.sleep(DELAY_SECONDS * (attempt + 2))


def crawl_app(app):
    seen = {}
    for sort in SORTS:
        for page in range(1, MAX_PAGES + 1):
            data = fetch(FEED.format(page=page, app_id=app["id"], sort=sort))
            entries = (data or {}).get("feed", {}).get("entry", [])
            if isinstance(entries, dict):
                entries = [entries]
            entries = [e for e in entries if "im:rating" in e]
            if not entries:
                break
            for e in entries:
                rid = e["id"]["label"]
                seen[rid] = {
                    "id": "as-" + hashlib.sha1(f"{app['id']}:{rid}".encode()).hexdigest()[:12],
                    "source": "appstore-cn",
                    "app": app["name"],
                    "app_id": app["id"],
                    "rating": int(e["im:rating"]["label"]),
                    "title": e["title"]["label"],
                    "content": e["content"]["label"],
                    "version": e.get("im:version", {}).get("label"),
                    "date": e["updated"]["label"],
                }
            time.sleep(DELAY_SECONDS)
    return list(seen.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apps", default="pipeline/crawl/apps.json")
    ap.add_argument("--out", default="data/raw/appstore_reviews.jsonl")
    args = ap.parse_args()
    apps = json.loads(Path(args.apps).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with out.open("w", encoding="utf-8") as f:
        for app in apps:
            rows = crawl_app(app)
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            total += len(rows)
            print(f"{app['name']}: {len(rows)} 条")
    meta = {"crawled_at": datetime.now(timezone.utc).isoformat(), "total": total, "apps": apps}
    out.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"共 {total} 条 → {out}")


if __name__ == "__main__":
    main()
