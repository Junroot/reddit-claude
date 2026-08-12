#!/usr/bin/env python3
"""수집 단계에서 항목을 걸러내는 규칙과 실행 기록 테스트 (3.1~3.9).

거르는 규칙은 조용히 틀리기 쉽다. 요청은 성공하고 로그도 깨끗한데 항목만
사라지므로, 잘못 걸러도 "그날 논의가 적었다"와 구분되지 않는다. 그래서 제외
건수를 status.json에 남기는 것까지 함께 확인한다.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import collect  # noqa: E402
import common  # noqa: E402

NOW = common.parse_iso("2026-08-10T00:00:00Z")

FEED_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
{entries}
</feed>
"""

ENTRY_TEMPLATE = """  <entry>
    <id>t3_{short}</id>
    <title>post {short}</title>
    <link href="https://www.reddit.com/r/ClaudeCode/comments/{short}/"/>
    <author><name>/u/tester</name></author>
    <published>{published}</published>
    <content type="html">&lt;p&gt;본문&lt;/p&gt;</content>
  </entry>"""


def build_feed(ages_in_hours: list) -> bytes:
    entries = "\n".join(
        ENTRY_TEMPLATE.format(
            short=f"p{n:02d}",
            published=common.to_iso(NOW - timedelta(hours=hours)),
        )
        for n, hours in enumerate(ages_in_hours, start=1)
    )
    return FEED_TEMPLATE.format(entries=entries).encode("utf-8")


def run_collect_reddit(ages_in_hours: list) -> tuple:
    """collect_reddit을 HTTP 없이 돌리고 (항목, 소스 칸)을 돌려준다."""
    original = common.http_get
    common.http_get = lambda url, headers=None, timeout=30: build_feed(ages_in_hours)
    try:
        entry = common.blank_status("x")["sources"]["reddit"]
        out: list = []
        collect.collect_reddit(entry, NOW, out)
        return out, entry
    finally:
        common.http_get = original


# ── 3.3 Reddit 48시간 창 ────────────────────────────────────────────────────

class RedditFilterTest(unittest.TestCase):
    """48시간을 넘긴 글을 버리고, 버린 건수를 기록에 남긴다."""

    WINDOW = collect.REDDIT_MAX_AGE_HOURS

    def test_창을_넘긴_글은_제외된다(self):
        out, _ = run_collect_reddit([1, self.WINDOW - 1, self.WINDOW + 1, self.WINDOW * 10])
        self.assertEqual([i["item_id"] for i in out], ["rd_p01", "rd_p02"])

    def test_제외_건수가_filtered에_기록된다(self):
        out, entry = run_collect_reddit([1, 2, self.WINDOW + 1, self.WINDOW + 5, 3])
        self.assertEqual(entry["filtered"], 2)
        self.assertEqual(len(out), 3)

    def test_제외가_없는_날에도_0으로_기록된다(self):
        _, entry = run_collect_reddit([1, 2, 3])
        self.assertEqual(entry["filtered"], 0)

    def test_제외를_수집_실패로_세지_않는다(self):
        # collect_reddit은 성공 여부를 스스로 쓰지 않는다. 실패로 표시할 근거를
        # 남기지 않는 것이 여기서 확인할 내용이다.
        _, entry = run_collect_reddit([self.WINDOW + 1] * 4)
        self.assertEqual(entry["filtered"], 4)
        self.assertEqual(entry["items"], 0)


# ── 3.1 공통 항목 스키마 ────────────────────────────────────────────────────

class ItemSchemaTest(unittest.TestCase):
    """두 소스가 같은 구조로 변환된다(3.1, 3.9)."""

    FIELDS = ("item_id", "source", "title", "url", "author",
              "published_at", "published_raw", "body", "signals")

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

    def test_Hacker_News_항목이_공통_스키마를_갖는다(self):
        hits = ('{"hits": [{"objectID": "38210", "title": "Claude Code 2.1", '
                '"author": "someone", "created_at": "2026-08-09T20:00:00Z", '
                '"story_text": "본문", "points": 120, "num_comments": 44, '
                '"url": "https://example.com/a"}]}')

        original = common.http_get
        common.http_get = lambda url, headers=None, timeout=30: hits.encode("utf-8")
        try:
            out: list = []
            collect.collect_hn(common.blank_status("x")["sources"]["hn"], NOW, out)
        finally:
            common.http_get = original

        for field in self.FIELDS:
            self.assertIn(field, out[0])
        self.assertEqual(out[0]["item_id"], "hn_38210")
        self.assertEqual(out[0]["source"], "hn")
        self.assertEqual(out[0]["signals"]["points"], 120)


# ── 3.8 수집 결과 기록 ──────────────────────────────────────────────────────

class SourceRecordTest(unittest.TestCase):
    """소스 칸은 소스 단위로 성공/실패를 남긴다.

    두 소스 모두 실행당 요청이 1회뿐이라 "일부 요청만 실패"가 존재하지 않는다.
    요청을 보내기 전에 죽든 요청이 실패하든 결과는 하나 — 그 소스는 수집 실패다.
    """

    def run_main(self, sources: tuple) -> dict:
        original = collect.SOURCES
        collect.SOURCES = sources
        try:
            with tempfile.TemporaryDirectory() as work:
                sys.argv = ["collect.py", "--work", work]
                collect.main()
                return common.read_json(common.status_path(work))
        finally:
            collect.SOURCES = original

    def test_성공한_소스는_정상으로_기록된다(self):
        def ok(entry, now_dt, out):
            out.append({"item_id": "rd_1", "source": "reddit"})

        status = self.run_main((("reddit", ok), ("hn", ok)))
        for name in ("reddit", "hn"):
            self.assertTrue(status["sources"][name]["collected"], name)
            self.assertEqual(status["sources"][name]["items"], 1)

    def test_요청이_실패한_소스는_수집_실패로_기록된다(self):
        def ok(entry, now_dt, out):
            out.append({"item_id": "rd_1", "source": "reddit"})

        def request_failed(entry, now_dt, out):
            raise OSError("HTTP 503")

        status = self.run_main((("reddit", ok), ("hn", request_failed)))
        self.assertTrue(status["sources"]["reddit"]["collected"])
        self.assertFalse(status["sources"]["hn"]["collected"])
        self.assertEqual(status["sources"]["hn"]["items"], 0)

    def test_요청을_보내기_전에_죽어도_수집_실패로_기록된다(self):
        def died_early(entry, now_dt, out):
            raise ValueError("설정을 읽지 못했다")

        status = self.run_main((("reddit", died_early), ("hn", died_early)))
        for name in ("reddit", "hn"):
            self.assertFalse(status["sources"][name]["collected"], name)
        # 기록이 비어 있는 채로 남지 않는다.
        self.assertIn("filtered", status["sources"]["reddit"])

    def test_성공했으나_0건인_날과_실패한_날이_구별된다(self):
        def quiet(entry, now_dt, out):
            return

        def failed(entry, now_dt, out):
            raise OSError("HTTP 503")

        status = self.run_main((("reddit", failed), ("hn", quiet)))
        self.assertEqual(status["sources"]["hn"]["items"], 0)
        self.assertEqual(status["sources"]["reddit"]["items"], 0)
        self.assertTrue(status["sources"]["hn"]["collected"])
        self.assertFalse(status["sources"]["reddit"]["collected"])

    def test_소스_칸에_요청_건수를_남기지_않는다(self):
        def ok(entry, now_dt, out):
            return

        status = self.run_main((("reddit", ok), ("hn", ok)))
        self.assertEqual(set(status["sources"]["reddit"]), {"collected", "items", "filtered"})


if __name__ == "__main__":
    unittest.main()
