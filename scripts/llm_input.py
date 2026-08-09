#!/usr/bin/env python3
"""두 LLM 호출에 넣을 입력 파일을 만든다.

    llm_input.py cluster     items.json                    → cluster_input.json
    llm_input.py summarize   ranked.json + comments.json   → summary_input.json

`items.json`을 통째로 넣으면 컨텍스트가 커진다. 특히 GitHub 이슈 본문에는 로그와
스택 트레이스가 길게 붙는다. 그래서 여기서만 본문 길이를 자른다 — `items.json`
자체는 원문을 그대로 보존한다.

요약 입력에는 **원문 URL과 게시 시각을 넣지 않는다.** 2차 LLM은 항목을 가리킬
때 `[[item:<항목 ID>]]` 자리표시자만 쓰고, 링크와 시각은 발행 스크립트가
`items.json`에서 읽어 채운다. 애초에 주지 않으면 옮겨 적다 틀릴 일도 없다.
"""

from __future__ import annotations

import argparse
import os
import re
from html.parser import HTMLParser

import common

# 주제를 묶는 데는 제목과 도입부면 충분하다. 실제 수집량을 보고 조정한다.
CLUSTER_BODY_CHARS = 300

# 2차에는 상위 8개 주제에 속한 항목만 들어가므로 더 긴 본문을 넣어도 여유가 있다.
SUMMARY_BODY_CHARS = 2000
SUMMARY_COMMENTS_PER_ITEM = 12
SUMMARY_COMMENT_CHARS = 500


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list = []

    def handle_data(self, data):
        self.parts.append(data)


def to_text(raw: str) -> str:
    """Reddit 본문은 HTML로 온다. 태그를 걷어내고 공백을 정리한다."""
    if not raw:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
        text = "".join(parser.parts)
    except Exception:
        text = raw
    return re.sub(r"\s+", " ", text).strip()


def clip(text: str, limit: int) -> str:
    text = to_text(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


# ── 1차: 주제 묶기 입력 ─────────────────────────────────────────────────────

def build_cluster_input(items_doc: dict, body_chars: int) -> dict:
    items = items_doc.get("items") or []
    return {
        "generated_at": items_doc.get("generated_at") or "",
        "count": len(items),
        "items": [
            {
                "item_id": it["item_id"],
                "source": it["source"],
                "title": it.get("title") or "",
                "excerpt": clip(it.get("body") or "", body_chars),
            }
            for it in items
        ],
    }


# ── 2차: 요약 입력 ──────────────────────────────────────────────────────────

def build_summary_input(ranked: dict, items_doc: dict, comments_doc: dict) -> dict:
    """상위 8 주제를 받은 순서 그대로 담는다. 순위를 다시 계산하지 않는다."""
    by_id = {it["item_id"]: it for it in (items_doc.get("items") or [])}
    comments_by_item = comments_doc.get("by_item") or {}
    topics_by_id = {t["topic_id"]: t for t in (ranked.get("topics") or [])}

    topics = []
    for position, topic_id in enumerate(ranked.get("top") or [], start=1):
        topic = topics_by_id.get(topic_id)
        if not topic:
            continue
        entries = []
        for item_id in topic["item_ids"]:
            item = by_id.get(item_id)
            if not item:
                continue
            entries.append({
                "item_id": item_id,
                "source": item["source"],
                "title": item.get("title") or "",
                "author": item.get("author") or "",
                "body": clip(item.get("body") or "", SUMMARY_BODY_CHARS),
                "comments": [
                    clip(c, SUMMARY_COMMENT_CHARS)
                    for c in (comments_by_item.get(item_id) or [])[:SUMMARY_COMMENTS_PER_ITEM]
                ],
            })
        topics.append({
            "position": position,
            "topic_id": topic_id,
            "title": topic.get("title") or "",
            "sources": topic.get("sources") or [],
            "items": entries,
        })

    return {"generated_at": ranked.get("generated_at") or "", "topics": topics}


# ── 실행 ────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 입력 파일을 만든다")
    parser.add_argument("stage", choices=("cluster", "summarize"))
    parser.add_argument("--work", default="work", help="작업 디렉터리")
    parser.add_argument("--body-chars", type=int, default=CLUSTER_BODY_CHARS,
                        help="주제 묶기 입력에서 항목 본문을 자를 길이")
    args = parser.parse_args()

    if args.stage == "cluster":
        items_doc = common.read_json(os.path.join(args.work, "items.json"), {"items": []})
        built = build_cluster_input(items_doc, args.body_chars)
        out = os.path.join(args.work, "cluster_input.json")
        common.write_json(out, built)
        size = os.path.getsize(out)
        print(f"항목 {built['count']}건, 본문 {args.body_chars}자로 잘라 {out}에 썼다 "
              f"({size / 1024:.0f} KB)")
        return 0

    ranked = common.read_json(os.path.join(args.work, "ranked.json"), {"topics": [], "top": []})
    items_doc = common.read_json(os.path.join(args.work, "items.json"), {"items": []})
    comments_doc = common.read_json(os.path.join(args.work, "comments.json"), {"by_item": {}})
    built = build_summary_input(ranked, items_doc, comments_doc)
    out = os.path.join(args.work, "summary_input.json")
    common.write_json(out, built)
    total_comments = sum(len(e["comments"]) for t in built["topics"] for e in t["items"])
    print(f"주제 {len(built['topics'])}건, 댓글 {total_comments}건을 {out}에 썼다 "
          f"({os.path.getsize(out) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
