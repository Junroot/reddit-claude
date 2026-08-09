#!/usr/bin/env python3
"""수집 단계에서 항목을 걸러내는 규칙 테스트 (3.5, 3.6).

거르는 규칙은 조용히 틀리기 쉽다. 요청은 성공하고 로그도 깨끗한데 항목만
사라지므로, 잘못 걸러도 "그날 논의가 적었다"와 구분되지 않는다.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import collect  # noqa: E402
import common  # noqa: E402

NOW = common.parse_iso("2026-08-10T00:00:00Z")


def issue(number: int, *, comments: int = 0, reactions: int = 0,
          created_hours_ago: float = 5, pull_request: bool = False) -> dict:
    row = {
        "number": number,
        "title": f"issue {number}",
        "html_url": f"https://github.com/anthropics/claude-code/issues/{number}",
        "user": {"login": "someone"},
        "created_at": common.to_iso(NOW - timedelta(hours=created_hours_ago)),
        "updated_at": common.to_iso(NOW - timedelta(hours=1)),
        "body": "본문",
        "comments": comments,
        "reactions": {"total_count": reactions},
        "state": "open",
        "labels": [{"name": "bug"}],
    }
    if pull_request:
        row["pull_request"] = {"url": "..."}
    return row


class GithubWindowTest(unittest.TestCase):
    """생성 시각으로 자르고, 창을 벗어나는 첫 항목에서 멈춘다."""

    def collect_with(self, *pages: list) -> tuple:
        """collect_github을 HTTP 없이 돌린다. 요청 횟수도 함께 돌려준다."""
        served = list(pages) + [[]]
        calls = {"n": 0}

        def fake_get(url, headers=None, timeout=30):
            page = served[calls["n"]] if calls["n"] < len(served) else []
            calls["n"] += 1
            return json.dumps(page).encode("utf-8")

        original = common.http_get
        common.http_get = fake_get
        try:
            entry = common.blank_status("x")["sources"]["github"]
            out: list = []
            collect.collect_github(entry, NOW, out)
            return out, entry, calls["n"]
        finally:
            common.http_get = original

    # 창의 폭은 바뀔 수 있으므로 상수를 기준으로 테스트한다.
    WINDOW = collect.GITHUB_MAX_AGE_HOURS

    def test_창을_넘겨_생성된_이슈는_제외된다(self):
        out, _, _ = self.collect_with([
            issue(1, comments=1, created_hours_ago=1),
            issue(2, comments=1, created_hours_ago=self.WINDOW - 1),
            issue(3, comments=1, created_hours_ago=self.WINDOW + 1),
            issue(4, comments=1, created_hours_ago=self.WINDOW * 10),
        ])
        self.assertEqual([i["item_id"] for i in out], ["gh_1", "gh_2"])

    def test_창을_벗어나면_다음_페이지를_요청하지_않는다(self):
        first = [issue(n, comments=1, created_hours_ago=1) for n in range(1, 100)]
        first.append(issue(999, comments=1, created_hours_ago=self.WINDOW + 1))
        _, _, calls = self.collect_with(first, [issue(1000, comments=1, created_hours_ago=1)])
        self.assertEqual(calls, 1, "생성 시각 내림차순이므로 한 번에 끝나야 한다")

    def test_한_페이지가_가득_차면_다음_페이지를_이어_받는다(self):
        full = [issue(n, comments=1, created_hours_ago=1) for n in range(1, 101)]
        out, _, calls = self.collect_with(full, [issue(200, comments=1, created_hours_ago=2)])
        self.assertEqual(len(out), 101)
        self.assertEqual(calls, 2)

    def test_Pull_Request는_제외된다(self):
        out, entry, _ = self.collect_with([
            issue(1, comments=3),
            issue(2, comments=3, pull_request=True),
        ])
        self.assertEqual([i["item_id"] for i in out], ["gh_1"])
        self.assertEqual(entry["failed"], 0)

    def test_반응이_하나도_없는_이슈는_제외된다(self):
        out, entry, _ = self.collect_with([
            issue(1, comments=0, reactions=0),
            issue(2, comments=1, reactions=0),
            issue(3, comments=0, reactions=1),
            issue(4, comments=5, reactions=9),
        ])
        self.assertEqual([i["item_id"] for i in out], ["gh_2", "gh_3", "gh_4"])
        self.assertEqual(entry["filtered"], 1)

    def test_제외를_요청_실패로_세지_않는다(self):
        _, entry, _ = self.collect_with([issue(n, comments=0, reactions=0) for n in range(1, 6)])
        self.assertEqual(entry["failed"], 0)
        self.assertEqual(entry["ok"], entry["requested"])
        self.assertEqual(entry["filtered"], 5)

    def test_시간_창을_벗어난_이슈는_참여도_판정을_거치지_않는다(self):
        # 창 밖에서 멈추므로 오래된 이슈는 filtered로 세지 않는다. 그래야 이 값이
        # "창 안에 열렸는데 아무도 반응하지 않은 이슈 수"라는 뜻을 유지한다.
        _, entry, _ = self.collect_with([
            issue(1, comments=1, created_hours_ago=2),
            issue(2, comments=0, created_hours_ago=self.WINDOW * 2),
        ])
        self.assertEqual(entry["filtered"], 0)

    def test_신호가_그대로_보존된다(self):
        out, _, _ = self.collect_with([issue(7, comments=4, reactions=11)])
        signals = out[0]["signals"]
        self.assertEqual(signals["comments"], 4)
        self.assertEqual(signals["reactions"], 11)
        self.assertEqual(signals["number"], 7)
        self.assertEqual(signals["labels"], ["bug"])


class ItemSchemaTest(unittest.TestCase):
    """세 소스가 같은 구조로 변환된다(3.1, 3.9)."""

    FIELDS = ("item_id", "source", "title", "url", "author",
              "published_at", "published_raw", "body", "signals")

    def test_GitHub_항목이_공통_스키마를_갖는다(self):
        rows = [issue(1, comments=2)]

        def fake_get(url, headers=None, timeout=30):
            return json.dumps(rows if "page=1" in url else []).encode("utf-8")

        original = common.http_get
        common.http_get = fake_get
        try:
            out: list = []
            collect.collect_github(common.blank_status("x")["sources"]["github"], NOW, out)
        finally:
            common.http_get = original

        for field in self.FIELDS:
            self.assertIn(field, out[0])
        self.assertEqual(out[0]["source"], "github")

    def test_Reddit_항목이_공통_스키마를_갖는다(self):
        feed = ("""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>t3_abc123</id>
            <title>제목</title>
            <link href="https://www.reddit.com/r/ClaudeCode/comments/abc123/"/>
            <author><name>/u/tester</name></author>
            <published>""" + common.to_iso(NOW - timedelta(hours=2)) + """</published>
            <content type="html">&lt;p&gt;본문&lt;/p&gt;</content>
          </entry>
        </feed>""").encode("utf-8")

        parsed = collect.parse_reddit_feed(feed)
        kept, _ = collect.filter_and_rank_reddit(parsed, NOW)

        for field in self.FIELDS:
            self.assertIn(field, kept[0])
        self.assertEqual(kept[0]["item_id"], "rd_abc123")
        self.assertEqual(kept[0]["signals"]["rank"], 1)
        # 본문은 자르지 않고 온전히 보존한다. 길이 제한은 LLM 입력 시점에만 건다.
        self.assertEqual(kept[0]["body"], "<p>본문</p>")


if __name__ == "__main__":
    unittest.main()
