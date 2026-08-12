#!/usr/bin/env python3
"""발행 단계의 두 관문 테스트 (7.4 허용 태그 필터, 8.3 자리표시자 치환).

우리가 통제하지 않는 문자열이 HTML로 들어오는 경로는 둘이고, 여기서 확인하는
것은 각 경로의 관문이 실제로 닫혀 있는가다. 남는 위험이 "관문 구현 자체의
누락"이므로 알려진 공격 문자열을 고정 케이스로 박아 회귀를 막는다.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import html
import os
import sys
import tempfile
import unittest
from html.parser import HTMLParser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import publish  # noqa: E402


class _Reader(HTMLParser):
    """결과 HTML에서 태그 이름과 속성, 그리고 글자를 뽑는다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags: list = []
        self.attrs: list = []
        self.text: list = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(name for name, _ in attrs)

    handle_startendtag = handle_starttag

    def handle_data(self, data):
        self.text.append(data)


def read(markup: str) -> _Reader:
    reader = _Reader()
    reader.feed(markup)
    reader.close()
    return reader


def item(item_id: str, *, title: str, url: str, published_at: str | None = "2026-08-09T12:34:00Z",
         source: str = "reddit") -> dict:
    return {
        "item_id": item_id,
        "source": source,
        "title": title,
        "url": url,
        "author": "u/someone",
        "published_at": published_at,
        "published_raw": published_at or "",
        "body": "",
        "signals": {},
    }


# ── 7.4c 허용 태그 필터 ─────────────────────────────────────────────────────

class TagFilterTest(unittest.TestCase):

    def test_a_태그와_위험한_스킴이_함께_사라진다(self):
        body, tags, attrs = publish.filter_html(
            '<p>보기 <a href="javascript:alert(1)">여기</a></p>')
        self.assertEqual((tags, attrs), (1, 0))
        self.assertNotIn("a", read(body).tags)
        self.assertNotIn("javascript:", body)
        # 태그만 지우고 글자는 남긴다. 문장에 구멍이 나면 안 된다.
        self.assertIn("여기", body)

    def test_허용_태그의_이벤트_핸들러가_지워진다(self):
        body, tags, attrs = publish.filter_html('<p onclick="steal()">문장</p>')
        self.assertEqual((tags, attrs), (0, 1))
        self.assertEqual(read(body).tags, ["p"])
        self.assertEqual(read(body).attrs, [])
        self.assertNotIn("onclick", body)

    def test_허용_태그의_style도_지워진다(self):
        body, tags, attrs = publish.filter_html('<code style="color:red">npm run</code>')
        self.assertEqual((tags, attrs), (0, 1))
        self.assertEqual(read(body).tags, ["code"])
        self.assertEqual(read(body).attrs, [])
        self.assertIn("npm run", body)

    def test_script는_태그와_내용이_함께_사라진다(self):
        body, tags, attrs = publish.filter_html("<p>앞</p><script>alert(1)</script><p>뒤</p>")
        self.assertEqual((tags, attrs), (1, 0))
        self.assertNotIn("script", read(body).tags)
        self.assertNotIn("alert(1)", body)
        self.assertIn("앞", body)
        self.assertIn("뒤", body)

    def test_네_입력을_한꺼번에_넣어도_건수가_맞는다(self):
        body, tags, attrs = publish.filter_html(
            '<p onclick="steal()">문장 <a href="javascript:alert(1)">링크</a></p>'
            '<code style="color:red">cmd</code>'
            "<script>alert(1)</script>"
        )
        self.assertEqual(tags, 2, "허용 목록 밖 태그는 a와 script 둘이다")
        self.assertEqual(attrs, 2, "허용 태그에 달린 속성은 onclick과 style 둘이다")

        parsed = read(body)
        self.assertEqual(parsed.attrs, [], "결과에 속성이 하나도 남지 않아야 한다")
        self.assertNotIn("a", parsed.tags, "클릭 가능한 링크가 남으면 안 된다")
        self.assertNotIn("script", parsed.tags)
        for leaked in ("javascript:", "onclick", "style="):
            self.assertNotIn(leaked, body)

    def test_실체_참조로_감춘_태그가_되살아나지_않는다(self):
        # convert_charrefs가 &lt;script&gt;를 <script>로 되돌려 놓기 때문에,
        # 글자를 그대로 내보내면 지운 태그가 살아난다.
        body, _, _ = publish.filter_html("<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>")
        self.assertNotIn("script", read(body).tags)
        self.assertIn("&lt;script&gt;", body)

    def test_닫히지_않은_태그가_구조를_깨뜨리지_않는다(self):
        body, _, _ = publish.filter_html("<p>앞<blockquote><p>안쪽")
        self.assertTrue(body.endswith("</p></blockquote></p>"), body)

    def test_허용_태그는_그대로_통과한다(self):
        source = "<h2>제목</h2><ul><li>항목</li></ul><blockquote><p>인용</p></blockquote>"
        body, tags, attrs = publish.filter_html(source)
        self.assertEqual((tags, attrs), (0, 0))
        self.assertEqual(body, source)


# ── 8.3c 자리표시자 치환 ────────────────────────────────────────────────────

class SubstitutionTest(unittest.TestCase):

    def setUp(self):
        self.items = {
            "rd_1a2b3c": item("rd_1a2b3c", title="MCP server disconnects",
                              url="https://www.reddit.com/r/ClaudeCode/comments/1a2b3c/"),
        }

    def test_정상_치환(self):
        body, counts = publish.substitute_refs(
            "<p>보고가 이어졌다 [[item:rd_1a2b3c]].</p>", self.items)

        self.assertEqual(counts, {"refs": 1, "unresolved_refs": 0, "unsafe_links": 0})
        parsed = read(body)
        self.assertIn("a", parsed.tags)
        self.assertIn("MCP server disconnects", "".join(parsed.text))
        self.assertIn('href="https://www.reddit.com/r/ClaudeCode/comments/1a2b3c/"', body)
        # 게시 시각이 함께 표시된다. 12:34 UTC는 한국 시간 21:34이다.
        self.assertIn("08/09 21:34", body)
        self.assertNotIn("[[item:", body)

    def test_없는_항목_ID를_가리키면_평문으로_남고_건수가_남는다(self):
        body, counts = publish.substitute_refs(
            "<p>보고 [[item:rd_없는것]] 이어졌다.</p>", self.items)

        self.assertEqual(counts["refs"], 1)
        self.assertEqual(counts["unresolved_refs"], 1)
        self.assertNotIn("a", read(body).tags, "링크를 만들면 안 된다")
        self.assertNotIn("[[item:", body)

    def test_원시_링크는_세기만_하고_제거하지_않는다(self):
        filtered, _, _ = publish.filter_html(
            '<p>여기 https://example.com/a 와 http://example.com/b 를 봐라</p>')
        raw_links = publish.count_raw_links(filtered)
        body, counts = publish.substitute_refs(filtered, self.items)

        self.assertEqual(raw_links, 2)
        self.assertEqual(counts["refs"], 0)
        self.assertIn("https://example.com/a", body)
        # `a`가 허용 목록에 없으므로 클릭되지 않는 평문으로만 남는다.
        self.assertNotIn("a", read(body).tags)

    def test_치환이_만든_링크는_원시_링크로_세지_않는다(self):
        filtered, _, _ = publish.filter_html("<p>보고 [[item:rd_1a2b3c]]</p>")
        raw_links = publish.count_raw_links(filtered)
        body, _ = publish.substitute_refs(filtered, self.items)

        self.assertEqual(raw_links, 0, "치환보다 앞에서 세야 규약 위반을 가릴 수 있다")
        self.assertIn("https://", body)

    def test_같은_항목을_여러_번_가리켜도_모두_센다(self):
        _, counts = publish.substitute_refs(
            "<p>[[item:rd_1a2b3c]] 와 [[item:rd_1a2b3c]]</p>", self.items)
        self.assertEqual(counts["refs"], 2)


# ── 8.3f 이스케이프와 스킴 확인 ─────────────────────────────────────────────

class EscapingTest(unittest.TestCase):
    """제목은 두 소스가 준 그대로다. 꺾쇠나 `&`가 든 것이 이상한 일이 아니다."""

    def substitute(self, entry: dict) -> tuple:
        return publish.substitute_refs(f"<p>보고 [[item:{entry['item_id']}]]</p>",
                                       {entry["item_id"]: entry})

    def assert_renders_as(self, body: str, original: str) -> None:
        """브라우저가 렌더링한 글자가 원문과 같은지 본다."""
        self.assertIn(original, html.unescape("".join(read(body).text)))

    def test_꺾쇠가_든_제목(self):
        title = "Prompt leaks <system-reminder> into output"
        body, counts = self.substitute(item("hn_1", title=title,
                                            url="https://news.ycombinator.com/item?id=1"))
        self.assertEqual(counts["unsafe_links"], 0)
        self.assertNotIn("system-reminder", read(body).tags, "태그로 해석되면 안 된다")
        self.assertIn("&lt;system-reminder&gt;", body)
        self.assert_renders_as(body, title)

    def test_앰퍼샌드가_든_제목(self):
        title = "Q&A: tips & tricks"
        body, _ = self.substitute(item("hn_2", title=title,
                                       url="https://news.ycombinator.com/item?id=2"))
        self.assertIn("&amp;", body)
        self.assertNotIn("&amp;amp;", body, "이중 이스케이프가 나면 안 된다")
        self.assert_renders_as(body, title)

    def test_따옴표가_든_제목(self):
        title = 'He said "it\'s broken"'
        body, _ = self.substitute(item("hn_3", title=title,
                                       url="https://news.ycombinator.com/item?id=3"))
        self.assert_renders_as(body, title)
        # 제목은 텍스트 자리에 들어가므로 따옴표가 속성을 탈출하지 못한다.
        parsed = read(body)
        self.assertEqual(parsed.tags, ["p", "a", "span"])
        self.assertEqual(parsed.attrs, ["href", "class"])

    def test_스크립트_삽입_시도가_든_제목(self):
        title = "<img src=x onerror=alert(1)>"
        body, _ = self.substitute(item("rd_4", title=title,
                                       url="https://www.reddit.com/r/ClaudeCode/comments/4/"))
        parsed = read(body)
        self.assertNotIn("img", parsed.tags, "태그가 아니라 글자로 표시되어야 한다")
        self.assertNotIn("onerror", parsed.attrs)
        self.assert_renders_as(body, title)

    def test_http도_https도_아닌_URL은_링크로_만들지_않는다(self):
        body, counts = self.substitute(
            item("rd_5", title="위험한 링크", url="javascript:alert(1)"))
        self.assertEqual(counts["unsafe_links"], 1)
        self.assertEqual(counts["unresolved_refs"], 0)
        self.assertNotIn("a", read(body).tags)
        self.assertNotIn("javascript:", body)
        self.assertIn("위험한 링크", body)

    def test_따옴표가_든_URL은_속성을_탈출하지_못한다(self):
        body, counts = self.substitute(
            item("rd_6", title="제목", url='https://example.com/"><script>alert(1)</script>'))
        self.assertEqual(counts["unsafe_links"], 0)
        parsed = read(body)
        self.assertNotIn("script", parsed.tags)
        self.assertIn("&quot;", body)

    def test_게시_시각을_해석하지_못하면_원본_문자열을_이스케이프해_쓴다(self):
        entry = item("rd_7", title="제목", url="https://example.com/", published_at=None)
        entry["published_raw"] = "<b>어제</b>"
        body, _ = self.substitute(entry)
        self.assertNotIn("b", read(body).tags)
        self.assertIn("&lt;b&gt;", body)


# ── 8.4 발행 여부 판정 ──────────────────────────────────────────────────────

class PublishDecisionTest(unittest.TestCase):

    def status(self, reddit: int, hn: int, *, quiet: tuple = ()) -> dict:
        """소스 칸을 채운 기록을 만든다.

        기본은 "항목이 있으면 수집 성공, 없으면 수집 실패"다. `quiet`에 이름을
        넣으면 그 소스는 성공했으나 0건인 날이 된다 — 항목 수만으로는 표현할 수
        없어서 성공 여부 필드가 따로 있다.
        """
        import common
        built = common.blank_status("2026-08-10T00:00:00Z")
        for key, got in (("reddit", reddit), ("hn", hn)):
            built["sources"][key]["items"] = got
            built["sources"][key]["collected"] = bool(got) or key in quiet
        return built

    def test_한_소스만_성공해도_발행한다(self):
        import common
        self.assertTrue(common.any_source_succeeded(self.status(0, 19)))

    def test_두_소스가_모두_실패하면_발행하지_않는다(self):
        import common
        self.assertFalse(common.any_source_succeeded(self.status(0, 0)))

    def test_배너는_전부_성공한_날에도_표시된다(self):
        banner = publish.build_banner(self.status(25, 19))
        self.assertIn("이번 회차 수집 상태", banner)
        self.assertIn("Reddit 정상", banner)
        self.assertIn("Hacker News 정상", banner)
        self.assertNotIn("attention", banner)

    def test_실패한_소스가_배너에_명시된다(self):
        banner = publish.build_banner(self.status(0, 19))
        self.assertIn("Reddit 수집 실패", banner)
        self.assertIn("attention", banner)

    def test_성공했으나_0건인_소스는_실패로_표시되지_않는다(self):
        # HN은 24시간 안에 결과가 없는 날이 있다. 조용한 날과 실패한 날은 다르다.
        banner = publish.build_banner(self.status(25, 0, quiet=("hn",)))
        self.assertIn("Hacker News 정상 — 0건 수집", banner)
        self.assertNotIn("attention", banner)

    def test_제거된_소스는_배너에_나오지_않는다(self):
        built = self.status(25, 19)
        built["sources"]["github"] = {"collected": True, "items": 830, "filtered": 0}
        banner = publish.build_banner(built)
        self.assertNotIn("GitHub", banner)

    def test_규약_위반_건수가_배너에_노출된다(self):
        built = self.status(25, 19)
        built["publish"].update({"unresolved_refs": 2, "raw_links": 3, "unsafe_links": 1})
        banner = publish.build_banner(built)
        self.assertIn("원문을 찾지 못한 항목 참조 2건", banner)
        self.assertIn("규약을 벗어난 원시 링크 3건", banner)
        self.assertIn("링크로 만들지 못한 주소 1건", banner)

    def test_제거한_태그와_속성은_배너에_올리지_않는다(self):
        built = self.status(25, 19)
        built["publish"].update({"filtered_tags": 4, "filtered_attrs": 7})
        banner = publish.build_banner(built)
        # 독자가 아니라 우리가 볼 신호이므로 status.json에만 남긴다.
        self.assertNotIn("4", banner.split("<ul>")[1])
        self.assertNotIn("attention", banner)


# ── 8.4 / 3.8 이어받은 기록의 정규화 ────────────────────────────────────────

class InheritedStatusTest(unittest.TestCase):
    """재실행이 이전 실행의 status.json을 이어받는 경로를 지킨다.

    워크플로의 `from_run_id` 경로는 이전 실행의 산출물을 그대로 내려받아 그 위에
    이어 쓴다. 그래서 지금 스키마에 없는 소스 칸과 필드가 살아 들어올 수 있다.
    """

    def write(self, work: str, status: dict) -> None:
        import common
        common.write_json(common.status_path(work), status)

    def test_제거된_소스의_항목_수는_발행_판정에_쓰이지_않는다(self):
        import common
        with tempfile.TemporaryDirectory() as work:
            self.write(work, {
                "generated_at": "2026-08-10T00:00:00Z",
                "sources": {
                    "reddit": {"collected": False, "items": 0, "filtered": 0},
                    "hn": {"collected": False, "items": 0, "filtered": 0},
                    "github": {"collected": True, "items": 69, "filtered": 354},
                },
            })
            status = common.load_status(work)

            self.assertNotIn("github", status["sources"])
            # 두 소스가 모두 실패한 날이므로 발행하지 않는다. 옛 GitHub 항목 수가
            # 판정을 통과시키면 어제 페이지를 오늘 브리프로 덮어쓰게 된다.
            self.assertFalse(common.any_source_succeeded(status))

    def test_옛_스키마의_소스_칸이_현재_스키마로_정규화된다(self):
        import common
        with tempfile.TemporaryDirectory() as work:
            self.write(work, {
                "generated_at": "2026-08-10T00:00:00Z",
                "sources": {
                    "reddit": {"requested": 1, "ok": 1, "failed": 0, "items": 25, "filtered": 0},
                    "hn": {"requested": 1, "ok": 1, "failed": 0, "items": 19, "filtered": 0},
                },
            })
            status = common.load_status(work)

            entry = status["sources"]["reddit"]
            self.assertEqual(set(entry), {"collected", "items", "filtered"})
            # 옛 기록에 성공 여부 필드가 없으므로 기본값이 들어간다. 배너와 알림이
            # 한시적으로 수집 실패로 표시하는 것은 설계에서 수용한 대가다(D6).
            self.assertFalse(entry["collected"])
            self.assertEqual(entry["items"], 25)
            self.assertNotIn("requested", entry)
            # 항목 수는 보존되므로 발행 자체는 정상이다.
            self.assertTrue(common.any_source_succeeded(status))

    def test_빠진_절은_기본값으로_채워진다(self):
        import common
        with tempfile.TemporaryDirectory() as work:
            self.write(work, {"generated_at": "2026-08-10T00:00:00Z"})
            status = common.load_status(work)
            self.assertEqual(status["enrich"], {"requested": 0, "ok": 0, "failed": 0})
            self.assertEqual(set(status["sources"]), {"reddit", "hn"})


if __name__ == "__main__":
    unittest.main()
