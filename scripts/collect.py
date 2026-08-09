#!/usr/bin/env python3
"""[1] collect — 세 소스에서 하루치 논의를 모아 공통 스키마로 정규화한다.

산출물은 두 개다.

    work/items.json    정규화된 항목 목록
    work/status.json   요청 단위 실행 기록

공통 항목 스키마(3.1):

    {
      "item_id":       "rd_1a2b3c",        소스 접두사가 붙은 고유 ID
      "source":        "reddit"|"hn"|"github",
      "title":         "...",              원문 제목. 번역하지 않는다
      "url":           "https://...",      원문 URL
      "author":        "...",
      "published_at":  "2026-08-09T12:00:00Z" | null,   해석된 게시 시각
      "published_raw": "...",              소스가 준 원본 시각 문자열
      "body":          "...",              자르지 않은 본문
      "signals":       { ... }             소스별 원시 신호
    }

본문을 자르지 않는 것은 원문 보존 규정 때문이다. 길이 제한은 LLM 입력을
만드는 시점에만 적용한다(D11).

한 소스가 실패해도 나머지 소스의 수집을 계속한다. 실패는 소스 단위가 아니라
요청 단위로 센다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import common

SUBREDDIT = "ClaudeCode"
REDDIT_FEED = f"https://www.reddit.com/r/{SUBREDDIT}/top/.rss?t=day"
HN_QUERY = "Claude Code"
GITHUB_REPO = "anthropics/claude-code"

# Reddit에만 48시간을 주는 이유는 어제 저녁에 올라와 밤새 표를 모은 글을
# 지키기 위해서다. top?t=day가 그 글을 상위로 올렸다는 사실 자체가 커뮤니티의
# 판단이므로 시각으로 뒤집지 않는다. 48시간은 Reddit이 이따금 훨씬 오래된 글을
# 순위에 올려보내는 경우만 막는 안전장치다.
REDDIT_MAX_AGE_HOURS = 48
OTHER_MAX_AGE_HOURS = 24

ATOM = {"atom": "http://www.w3.org/2005/Atom"}

# 24시간 창을 서버 쪽에서 걸러도 페이지가 넘칠 수 있다. 폭주를 막는 상한이며,
# 여기에 걸리면 로그로 알린다.
GITHUB_MAX_PAGES = 10


def _get(entry: dict, url: str, headers: dict | None = None, timeout: int = 30) -> bytes:
    """요청 한 건을 보내고 그 결과를 status의 소스 칸에 센다."""
    entry["requested"] += 1
    try:
        raw = common.http_get(url, headers, timeout)
    except Exception:
        entry["failed"] += 1
        raise
    entry["ok"] += 1
    return raw


def _text(node, path: str) -> str:
    found = node.find(path, ATOM)
    return (found.text or "").strip() if found is not None else ""


# ── Reddit ──────────────────────────────────────────────────────────────────

def parse_reddit_feed(raw: bytes) -> list:
    """Atom 피드를 읽어 피드 나열 순서를 보존한 채 항목으로 바꾼다(3.2).

    RSS 응답에는 업보트 수도 댓글 수도 담기지 않는다. 그래서 이 단계에서 얻는
    인기 신호는 피드에 나열된 순서뿐이고, Reddit의 등수는 그 순서로만 정한다.
    """
    root = ET.fromstring(raw)
    parsed = []
    for position, node in enumerate(root.findall("atom:entry", ATOM), start=1):
        full_id = _text(node, "atom:id")           # t3_1a2b3c
        short_id = full_id.split("_", 1)[-1] if full_id else ""
        if not short_id:
            continue

        link = node.find("atom:link", ATOM)
        url = (link.get("href") if link is not None else "") or ""
        published_raw = _text(node, "atom:published") or _text(node, "atom:updated")

        parsed.append({
            "item_id": f"rd_{short_id}",
            "source": "reddit",
            "title": _text(node, "atom:title"),
            "url": url,
            "author": _text(node, "atom:author/atom:name"),
            "published_at": None,
            "published_raw": published_raw,
            "body": _text(node, "atom:content"),
            "signals": {"feed_position": position},
        })
        parsed[-1]["published_at"] = common.parse_iso(published_raw)
    return parsed


def filter_and_rank_reddit(parsed: list, now_dt: datetime) -> tuple:
    """48시간을 넘긴 글을 버리고 남은 글에 등수를 1부터 다시 부여한다(3.3).

    원래 피드 위치 번호를 등수로 쓰지 않는 것이 핵심이다. 위치 번호를 그대로
    두면 피드 1~3위가 모두 걸러진 날 Reddit의 최상위 글이 등수 4를 받아 1/4만
    기여하는데, 같은 날 HN과 GitHub은 수집된 집합 위에서 등수를 매기므로 항상
    1.0짜리 1위를 갖는다. "소스 간 비교는 등수로만 한다"는 등가화 전제가
    Reddit에만 불리하게 깨진다. 재압축하면 수집 결과가 0건인 날을 빼고 Reddit
    에도 항상 등수 1이 존재하고, 슬롯 예약도 매일 대상 글을 갖는다.

    돌려주는 값은 (남은 항목, 제외한 건수)이다.
    """
    kept, dropped = [], 0
    for item in parsed:
        published = item["published_at"]
        # 시각을 해석하지 못한 글은 버리지 않는다. 오래됐다고 판정할 근거가
        # 없는데 버리면 조용히 항목을 잃는다.
        if published is not None and common.hours_since(published, now_dt) > REDDIT_MAX_AGE_HOURS:
            dropped += 1
            continue
        item = dict(item, signals=dict(item["signals"], rank=len(kept) + 1))
        item["published_at"] = common.to_iso(published) if published else None
        kept.append(item)
    return kept, dropped


def collect_reddit(entry: dict, now_dt: datetime, out: list) -> None:
    """r/ClaudeCode의 top/.rss?t=day를 1회 요청한다(3.2)."""
    raw = _get(entry, REDDIT_FEED, headers={"User-Agent": common.BROWSER_UA})
    parsed = parse_reddit_feed(raw)
    kept, dropped = filter_and_rank_reddit(parsed, now_dt)
    out.extend(kept)
    print(f"[reddit] 피드 {len(parsed)}건 → 48시간 초과 {dropped}건 제외 → {len(kept)}건")


# ── Hacker News ─────────────────────────────────────────────────────────────

def collect_hn(entry: dict, now_dt: datetime, out: list) -> None:
    """Algolia 검색으로 24시간 이내 스토리를 모은다(3.4).

    24시간 안에 결과가 하나도 없는 것은 실패가 아니라 조용한 날이다.
    """
    cutoff = int(now_dt.timestamp()) - OTHER_MAX_AGE_HOURS * 3600
    url = (
        "https://hn.algolia.com/api/v1/search_by_date?"
        + urllib.parse.urlencode({
            "query": HN_QUERY,
            "tags": "story",
            "numericFilters": f"created_at_i>={cutoff}",
            "hitsPerPage": 100,
        })
    )
    data = json.loads(_get(entry, url).decode("utf-8", "replace"))

    for hit in data.get("hits") or []:
        object_id = str(hit.get("objectID") or "")
        if not object_id:
            continue
        published_raw = hit.get("created_at") or ""
        published = common.parse_iso(published_raw)
        # 브리프 독자가 눌러 가야 할 곳은 논의가 붙은 HN 스레드다. 링크 스토리의
        # 외부 기사 주소는 신호에 남겨 둔다.
        out.append({
            "item_id": f"hn_{object_id}",
            "source": "hn",
            "title": hit.get("title") or "",
            "url": f"https://news.ycombinator.com/item?id={object_id}",
            "author": hit.get("author") or "",
            "published_at": common.to_iso(published) if published else None,
            "published_raw": published_raw,
            "body": hit.get("story_text") or "",
            "signals": {
                "points": hit.get("points") or 0,
                "num_comments": hit.get("num_comments") or 0,
                "story_url": hit.get("url") or "",
            },
        })

    print(f"[hn] 24시간 이내 스토리 {len(out)}건")


# ── GitHub Issues ───────────────────────────────────────────────────────────

def collect_github(entry: dict, now_dt: datetime, out: list) -> None:
    """anthropics/claude-code의 이슈 중 24시간 안에 갱신된 것을 모은다(3.5).

    updated_at 기준이므로 사흘 전에 열린 이슈라도 오늘 댓글이 달렸으면 대상이
    된다. "지난 24시간의 논의"라는 정의에 이쪽이 맞다.
    """
    since = common.to_iso(now_dt - timedelta(hours=OTHER_MAX_AGE_HOURS))
    headers = {
        "User-Agent": common.BOT_UA,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    seen_pull_requests = 0
    for page in range(1, GITHUB_MAX_PAGES + 1):
        url = (
            f"https://api.github.com/repos/{GITHUB_REPO}/issues?"
            + urllib.parse.urlencode({
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": 100,
                "since": since,
                "page": page,
            })
        )
        rows = json.loads(_get(entry, url, headers).decode("utf-8", "replace"))
        if not isinstance(rows, list) or not rows:
            break

        for row in rows:
            # 이 엔드포인트는 Pull Request를 이슈로 섞어 반환한다(3.6).
            if "pull_request" in row:
                seen_pull_requests += 1
                continue

            number = row.get("number")
            if number is None:
                continue
            published_raw = row.get("created_at") or ""
            published = common.parse_iso(published_raw)
            out.append({
                "item_id": f"gh_{number}",
                "source": "github",
                "title": row.get("title") or "",
                "url": row.get("html_url") or "",
                "author": ((row.get("user") or {}).get("login")) or "",
                "published_at": common.to_iso(published) if published else None,
                "published_raw": published_raw,
                "body": row.get("body") or "",
                "signals": {
                    "number": number,
                    "reactions": ((row.get("reactions") or {}).get("total_count")) or 0,
                    "comments": row.get("comments") or 0,
                    "state": row.get("state") or "",
                    "labels": [
                        (lb.get("name") if isinstance(lb, dict) else str(lb))
                        for lb in (row.get("labels") or [])
                    ],
                    "updated_at": row.get("updated_at") or "",
                },
            })

        if len(rows) < 100:
            break
    else:
        print(f"[github] 경고: 페이지 상한 {GITHUB_MAX_PAGES}에 걸렸다. 일부 이슈가 빠졌을 수 있다")

    print(f"[github] 이슈 {len(out)}건 (Pull Request {seen_pull_requests}건 제외)")


# ── 실행 ────────────────────────────────────────────────────────────────────

SOURCES = (
    ("reddit", collect_reddit),
    ("hn", collect_hn),
    ("github", collect_github),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="세 소스에서 하루치 논의를 수집한다")
    parser.add_argument("--work", default="work", help="작업 디렉터리")
    args = parser.parse_args()

    now_dt = common.now()
    status = common.blank_status(common.to_iso(now_dt))
    items: list = []

    for name, collect in SOURCES:
        entry = status["sources"][name]
        got: list = []
        try:
            collect(entry, now_dt, got)
        except Exception as exc:
            # 한 소스가 죽어도 나머지 소스는 계속 수집한다(3.8). 이미 받아 둔
            # 항목은 버리지 않는다 — 실패는 요청 단위이지 소스 단위가 아니다.
            print(f"[{name}] 수집 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
            if entry["requested"] == 0:
                # 요청을 보내기도 전에 죽은 경우까지 실패로 남긴다.
                entry["requested"] = 1
                entry["failed"] = 1
        entry["items"] = len(got)
        items.extend(got)

    common.write_json(os.path.join(args.work, "items.json"), {
        "generated_at": status["generated_at"],
        "items": items,
    })
    status["cluster"]["items"] = len(items)
    common.save_status(args.work, status)

    print(f"\n총 {len(items)}건을 items.json에 썼다")
    for name, _ in SOURCES:
        s = status["sources"][name]
        print(f"  {name:7s} 요청 {s['requested']} 성공 {s['ok']} 실패 {s['failed']} 항목 {s['items']}")

    # 세 소스가 전부 실패해도 여기서 세우지 않는다. 발행 여부 판정은 [6] publish가
    # status.json을 보고 한 곳에서 내린다.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
