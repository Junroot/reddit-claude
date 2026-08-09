#!/usr/bin/env python3
"""[4] enrich — 상위 주제에 속한 Reddit 글의 댓글을 모은다.

입력  work/ranked.json, work/items.json
출력  work/comments.json

이 댓글은 **순위에 영향을 주지 않는다.** 순위는 앞 단계에서 이미 확정됐고,
여기서 모으는 것은 요약문을 쓸 재료일 뿐이다. 그래서 몇 건이 빠져도 브리프는
성립하고, 이 단계가 통째로 실패해도 발행을 막지 않는다.

요청은 비싸다. 실측에서 댓글 RSS는 재시도로 두들기면 90회 중 15회만 성공했고,
성공 간격이 약 55초로 일정했다. 분당 1회 수준의 한도가 걸려 있다는 뜻이므로
재시도는 한도를 앞당겨 소진시킬 뿐이다. 첫 요청은 즉시 보내고 이후 60초 간격으로
최대 8건을 보내며, 실패한 글은 건너뛴다.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import xml.etree.ElementTree as ET

import common

MAX_REQUESTS = 8
DEFAULT_INTERVAL_SECONDS = 60
ATOM = {"atom": "http://www.w3.org/2005/Atom"}


def pick_targets(ranked: dict, items: list) -> list:
    """상위 8 주제에서 댓글을 받아 올 Reddit 글을 고른다(6.1, 6.1a).

    한 주제에 Reddit 글이 여럿 묶여도 등수가 가장 높은 1건만 고른다. 그리고
    중복 방지는 주제 단위가 아니라 **글 URL 단위**로 한다. 주제 단위로만 막으면
    한 글이 여러 주제에 배정된 날 같은 URL로 두 번 요청이 나가, 하루 9건이라는
    상한이 실측 없이 샌다. 같은 글이 여러 주제에 묶이는 것은 허용된 정상
    경로이므로, 한 번 받은 댓글을 그 주제 모두의 재료로 재사용한다.
    """
    by_id = {it["item_id"]: it for it in items}
    ranks = ranked.get("item_ranks") or {}
    topics_by_id = {t["topic_id"]: t for t in (ranked.get("topics") or [])}

    targets: list = []
    seen_urls: set = set()
    for topic_id in ranked.get("top") or []:
        topic = topics_by_id.get(topic_id)
        if not topic:
            continue
        candidates = [
            by_id[i] for i in topic["item_ids"]
            if i in by_id and by_id[i]["source"] == "reddit"
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda it: (ranks.get(it["item_id"], 10 ** 9), it["item_id"]))
        url = best.get("url") or best["item_id"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        targets.append(best)
        if len(targets) >= MAX_REQUESTS:
            break
    return targets


def parse_comments(raw: bytes) -> list:
    """댓글 Atom 피드에서 본문 문자열만 뽑는다."""
    root = ET.fromstring(raw)
    out = []
    for node in root.findall("atom:entry", ATOM):
        content = node.find("atom:content", ATOM)
        text = (content.text or "").strip() if content is not None else ""
        if text:
            out.append(text)
    return out


def comment_feed_url(item: dict) -> str:
    short_id = item["item_id"].split("_", 1)[-1]
    return f"https://www.reddit.com/comments/{short_id}/.rss?limit=100"


def main() -> int:
    parser = argparse.ArgumentParser(description="상위 주제의 Reddit 댓글을 모은다")
    parser.add_argument("--work", default="work", help="작업 디렉터리")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SECONDS,
                        help="요청 사이 간격(초). 첫 요청에는 적용하지 않는다")
    args = parser.parse_args()

    ranked = common.read_json(os.path.join(args.work, "ranked.json"), {"topics": [], "top": []})
    items_doc = common.read_json(os.path.join(args.work, "items.json"), {"items": []})
    targets = pick_targets(ranked, items_doc.get("items") or [])

    by_item: dict = {}
    requested = ok = failed = 0

    if not targets:
        # 상위 주제에 Reddit 글이 없으면 요청을 보내지 않고 넘어간다(6.4).
        print("상위 주제에 Reddit 글이 없다. 댓글 요청을 보내지 않는다")
    else:
        print(f"댓글 수집 대상 {len(targets)}건, 간격 {args.interval:g}초, 재시도 없음")

    started = time.time()
    for index, item in enumerate(targets):
        if index and args.interval > 0:
            time.sleep(args.interval)
        url = comment_feed_url(item)
        requested += 1
        elapsed = time.time() - started
        try:
            raw = common.http_get(url, headers={"User-Agent": common.BROWSER_UA})
            comments = parse_comments(raw)
        except Exception as exc:
            # 실패한 글은 재시도하지 않고 건너뛴다.
            failed += 1
            print(f"  [{elapsed:5.0f}s] ✗ {item['item_id']}  {type(exc).__name__}")
            continue
        ok += 1
        by_item[item["item_id"]] = comments
        print(f"  [{elapsed:5.0f}s] ✓ {item['item_id']}  댓글 {len(comments)}건")

    common.write_json(os.path.join(args.work, "comments.json"), {
        "requested": requested,
        "ok": ok,
        "failed": failed,
        "by_item": by_item,
    })
    common.record_section(args.work, "enrich",
                          {"requested": requested, "ok": ok, "failed": failed})

    print(f"\n요청 {requested}건 중 {ok}건 성공, {failed}건 실패")
    if failed and not ok:
        # 전부 실패해도 발행은 막지 않는다. 요약 재료가 얇아질 뿐이다.
        print("모두 실패했지만 요약 단계를 정상 진행한다", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
