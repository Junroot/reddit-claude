#!/usr/bin/env python3
"""수집 단계에서 항목을 걸러내는 규칙 테스트 (3.6, 3.6a).

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
          pull_request: bool = False) -> dict:
    row = {
        "number": number,
        "title": f"issue {number}",
        "html_url": f"https://github.com/anthropics/claude-code/issues/{number}",
        "user": {"login": "someone"},
        "created_at": common.to_iso(NOW - timedelta(hours=5)),
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


class GithubFilterTest(unittest.TestCase):
    """GitHub 응답을 가짜로 돌려주고 걸러지는 항목을 확인한다."""

    def collect_with(self, rows: list) -> tuple:
        """collect_github을 HTTP 없이 돌린다."""
        pages = [rows, []]
        calls = {"n": 0}

        def fake_get(url, headers=None, timeout=30):
            page = pages[calls["n"]] if calls["n"] < len(pages) else []
            calls["n"] += 1
            return json.dumps(page).encode("utf-8")

        original = common.http_get
        common.http_get = fake_get
        try:
            entry = common.blank_status("x")["sources"]["github"]
            out: list = []
            collect.collect_github(entry, NOW, out)
            return out, entry
        finally:
            common.http_get = original

    def test_Pull_Request는_제외된다(self):
        out, _ = self.collect_with([
            issue(1, comments=3),
            issue(2, comments=3, pull_request=True),
        ])
        self.assertEqual([i["item_id"] for i in out], ["gh_1"])

    def test_댓글도_리액션도_0이면_제외된다(self):
        out, entry = self.collect_with([
            issue(1, comments=0, reactions=0),
            issue(2, comments=1, reactions=0),
            issue(3, comments=0, reactions=1),
            issue(4, comments=5, reactions=9),
        ])
        self.assertEqual([i["item_id"] for i in out], ["gh_2", "gh_3", "gh_4"])
        self.assertEqual(entry["filtered"], 1)

    def test_제외를_요청_실패로_세지_않는다(self):
        _, entry = self.collect_with([issue(n, comments=0, reactions=0) for n in range(1, 6)])
        self.assertEqual(entry["failed"], 0)
        self.assertEqual(entry["ok"], entry["requested"])
        self.assertEqual(entry["filtered"], 5)

    def test_신호가_그대로_보존된다(self):
        out, _ = self.collect_with([issue(7, comments=4, reactions=11)])
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
