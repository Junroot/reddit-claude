#!/usr/bin/env python3
"""[6] publish — 본문을 무해화하고 자리표시자를 채워 페이지를 조립한다.

입력  work/brief.html (2차 LLM 출력), work/items.json, work/status.json
출력  work/site/index.html, work/site/.nojekyll, work/publish.json

우리가 통제하지 않는 문자열이 HTML 안으로 들어오는 경로는 둘이고, 서로 다른
관문이 각각을 닫는다.

    ① 2차 LLM 출력      → 허용 태그 화이트리스트 + 속성 전면 제거
    ② 자리표시자 치환   → HTML 이스케이프 + http/https 스킴 확인

①의 필터는 LLM 출력 경로의 유일한 관문이다. 2차 LLM 입력에는 누구나 쓸 수 있는
r/ClaudeCode 글과 댓글이 들어가므로, 태그 이름만 보고 속성을 그대로 두면 관문이
반쯤 열린 채로 남는다. 그래서 속성 화이트리스트를 두지 않고 전부 지운다. 본문
조각이 쓰는 태그 일곱 개 중 속성이 필요한 것은 하나도 없다.

②는 ①보다 뒤 단계라 필터가 이 문자열을 아예 보지 못한다. 항목 제목은 두 소스가
준 그대로이고 꺾쇠나 `&`가 들어 있는 것이 이상한 일이 아니므로, 무해화는 치환하는
쪽이 해야 한다.

어느 위반도 발행을 막지 않는다. 막지 말고 보정하고 관측 가능하게 한다 —
브리프 전체가 사라지는 것보다 링크 몇 개가 평문인 편이 낫다.
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import timedelta, timezone
from html.parser import HTMLParser

import common

# 본문 조각이 쓸 수 있는 태그. `a`는 여기 없다 — 화면에 나오는 링크는 전부
# 자리표시자 치환이 만들고, 그 결과는 이 필터 뒤 단계의 산출물이라 필터를
# 지나지 않는다. 그래서 `a`를 빼도 표시되는 링크는 줄지 않는다.
ALLOWED_TAGS = frozenset({"h2", "h3", "p", "ul", "li", "blockquote", "code"})

# 이 둘은 태그만 지우고 안쪽 글자를 남기면 코드가 본문에 그대로 흘러나온다.
# 내용까지 함께 버린다.
DROP_WITH_CONTENT = frozenset({"script", "style"})

PLACEHOLDER = re.compile(r"\[\[item:([^\]\s]+)\]\]")
RAW_LINK = re.compile(r"https?://", re.IGNORECASE)

KST = timezone(timedelta(hours=9))
SOURCE_LABEL = {"reddit": "Reddit", "hn": "HN"}
TITLE = "Claude Code 커뮤니티 브리프"


# ── 이스케이프 ──────────────────────────────────────────────────────────────

def escape_text(value: str) -> str:
    """텍스트 자리용. `&`를 먼저 치환해야 이중 이스케이프가 나지 않는다."""
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def escape_attr(value: str) -> str:
    """속성값 자리용. 텍스트 규칙에 따옴표 둘을 더 막는다."""
    return escape_text(value).replace('"', "&quot;").replace("'", "&#39;")


# ── ① 허용 태그 필터 ────────────────────────────────────────────────────────

class _TagFilter(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list = []
        self.open_tags: list = []
        self.filtered_tags = 0
        self.filtered_attrs = 0
        self._suppress_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.filtered_tags += 1
            self._suppress_depth += 1
            return
        if tag not in ALLOWED_TAGS:
            # 태그만 지우고 안쪽 글자는 남긴다. 링크로 쓰인 <a>의 글자가
            # 사라지면 문장에 구멍이 난다.
            self.filtered_tags += 1
            return
        self.filtered_attrs += len(attrs)
        self.parts.append(f"<{tag}>")
        self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT or tag not in ALLOWED_TAGS:
            self.filtered_tags += 1
            return
        self.filtered_attrs += len(attrs)
        self.parts.append(f"<{tag}></{tag}>")

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self._suppress_depth = max(0, self._suppress_depth - 1)
            return
        if tag not in ALLOWED_TAGS or tag not in self.open_tags:
            return
        # 닫히지 않은 채 남은 안쪽 태그를 함께 닫아 구조를 맞춘다.
        while self.open_tags:
            top = self.open_tags.pop()
            self.parts.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data):
        if self._suppress_depth:
            return
        # convert_charrefs가 실체 참조를 원래 문자로 되돌려 놓았으므로, 그대로
        # 내보내면 지운 태그가 되살아난다. 다시 이스케이프해서 내보낸다.
        self.parts.append(escape_text(data))

    def result(self) -> str:
        while self.open_tags:
            self.parts.append(f"</{self.open_tags.pop()}>")
        return "".join(self.parts)


def filter_html(raw: str) -> tuple:
    """허용 목록 밖 태그를 지우고 통과시키는 태그의 속성을 전부 지운다.

    돌려주는 값은 (본문, 제거한 태그 수, 제거한 속성 수)이다.
    """
    parser = _TagFilter()
    parser.feed(raw or "")
    parser.close()
    return parser.result(), parser.filtered_tags, parser.filtered_attrs


# ── ② 자리표시자 치환 ───────────────────────────────────────────────────────

def display_time(item: dict) -> str:
    parsed = common.parse_iso(item.get("published_at") or "")
    if parsed:
        return parsed.astimezone(KST).strftime("%m/%d %H:%M")
    return (item.get("published_raw") or "").strip() or "시각 불명"


def substitute_refs(body: str, items_by_id: dict) -> tuple:
    """`[[item:<항목 ID>]]`를 원문 링크·제목·게시 시각으로 바꾼다.

    기준 시각, 수집 상태, 항목별 원문 링크, 항목별 게시 시각 — 이 넷은 서술이
    아니라 사실 보고이므로 기계가 채워야 정확하다. LLM이 쓰는 것은 문장뿐이다.
    """
    counts = {"refs": 0, "unresolved_refs": 0, "unsafe_links": 0}

    def replace(match: re.Match) -> str:
        item_id = match.group(1)
        counts["refs"] += 1
        item = items_by_id.get(item_id)

        if item is None:
            # 없는 항목을 가리켰다. 발행을 세우지 않고 링크 없는 평문으로 남긴다.
            counts["unresolved_refs"] += 1
            return f'<span class="ref-plain">{escape_text(item_id)}</span>'

        label = escape_text(item.get("title") or item_id)
        meta = (f'<span class="ref">({escape_text(SOURCE_LABEL.get(item.get("source"), "?"))}'
                f' · {escape_text(display_time(item))})</span>')
        url = (item.get("url") or "").strip()

        # 이스케이프만으로는 `javascript:` 류 스킴을 막지 못하므로 별도 관문을 둔다.
        if not (url.startswith("http://") or url.startswith("https://")):
            counts["unsafe_links"] += 1
            return f'<span class="ref-plain">{label}</span> {meta}'

        return f'<a href="{escape_attr(url)}">{label}</a> {meta}'

    return PLACEHOLDER.sub(replace, body), counts


def count_raw_links(body: str) -> int:
    """자리표시자를 거치지 않고 본문에 남은 원시 링크 수(8.3b).

    치환보다 **앞에서** 센다. 치환이 만드는 `<a href="https://…">`까지 세면
    2차 LLM이 규약을 어겼는지 알 수 없게 된다. 제거하지는 않는다 — `a`가 허용
    목록에 없고 속성이 지워지므로 그것은 클릭되지 않는 평문으로만 남는다.
    """
    return len(RAW_LINK.findall(body))


# ── 수집 상태 배너 ──────────────────────────────────────────────────────────

def build_banner(status: dict) -> str:
    """소스별 수집 상태를 항상 표시한다(8.2).

    문제가 있을 때만 나타나는 표시는 독자가 그 자리를 보지 않게 만들고, 정작
    중요한 날 놓치게 한다.
    """
    lines: list = []
    attention = False

    # 소스 갈래는 둘뿐이다. 두 소스 모두 실행당 요청이 1회라 "일부 요청만 실패"가
    # 존재하지 않는다. 요청 단위 표시는 실제로 여러 요청을 보내는 댓글 보강에만 남는다.
    for key, label in (("reddit", "Reddit"), ("hn", "Hacker News")):
        entry = (status.get("sources") or {}).get(key) or {}
        got = entry.get("items", 0)
        if entry.get("collected"):
            lines.append(f"{label} 정상 — {got}건 수집")
        else:
            attention = True
            lines.append(f"<b>{label} 수집 실패</b>")

    enrich = status.get("enrich") or {}
    if enrich.get("requested", 0):
        if enrich.get("failed", 0):
            attention = True
            lines.append(f"<b>Reddit 댓글 보강 부분 실패</b> — 요청 {enrich['requested']}건 중 "
                         f"{enrich['ok']}건 성공")
        else:
            lines.append(f"Reddit 댓글 보강 정상 — {enrich['ok']}건")

    publish = status.get("publish") or {}
    for key, label in (("unresolved_refs", "원문을 찾지 못한 항목 참조"),
                       ("raw_links", "규약을 벗어난 원시 링크"),
                       ("unsafe_links", "링크로 만들지 못한 주소")):
        if publish.get(key, 0):
            attention = True
            lines.append(f"<b>{label} {publish[key]}건</b>")

    body = "".join(f"<li>{line}</li>" for line in lines)
    cls = "banner attention" if attention else "banner"
    return f'<div class="{cls}"><b>이번 회차 수집 상태</b><ul>{body}</ul></div>'


# ── 페이지 조립 ─────────────────────────────────────────────────────────────

def to_kst_display(iso: str) -> str:
    parsed = common.parse_iso(iso)
    if not parsed:
        return iso or "불명"
    return parsed.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")


def render_page(template: str, *, generated_at: str, built_at: str,
                banner: str, body: str, repo_url: str, repo_name: str) -> str:
    tokens = {
        "{{TITLE}}": escape_text(TITLE),
        "{{GENERATED_AT}}": escape_text(generated_at),
        "{{BUILT_AT}}": escape_text(built_at),
        "{{BANNER}}": banner,
        "{{BODY}}": body,
        "{{REPO_URL}}": escape_attr(repo_url),
        "{{REPO_NAME}}": escape_text(repo_name),
    }
    for token, value in tokens.items():
        template = template.replace(token, value)
    return template


def main() -> int:
    parser = argparse.ArgumentParser(description="브리프 페이지를 조립한다")
    parser.add_argument("--work", default="work", help="작업 디렉터리")
    parser.add_argument("--out", default=None, help="페이지를 쓸 디렉터리 (기본 <work>/site)")
    parser.add_argument("--template", default=None, help="템플릿 경로")
    args = parser.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    template_path = args.template or os.path.join(here, "..", "templates", "index.html")
    out_dir = args.out or os.path.join(args.work, "site")

    status = common.load_status(args.work)
    items_doc = common.read_json(os.path.join(args.work, "items.json"), {"items": []})
    items_by_id = {it["item_id"]: it for it in (items_doc.get("items") or [])}

    brief_path = os.path.join(args.work, "brief.html")
    raw_body = ""
    if os.path.exists(brief_path):
        with open(brief_path, encoding="utf-8") as f:
            raw_body = f.read()

    filtered, filtered_tags, filtered_attrs = filter_html(raw_body)
    raw_links = count_raw_links(filtered)
    body, counts = substitute_refs(filtered, items_by_id)

    status["publish"] = {
        "refs": counts["refs"],
        "unresolved_refs": counts["unresolved_refs"],
        "raw_links": raw_links,
        "unsafe_links": counts["unsafe_links"],
        "filtered_tags": filtered_tags,
        "filtered_attrs": filtered_attrs,
    }
    common.save_status(args.work, status)

    print(f"본문 자리표시자 {counts['refs']}건 (원문을 찾지 못한 것 {counts['unresolved_refs']}건)")
    print(f"원시 링크 {raw_links}건, 링크로 만들지 못한 주소 {counts['unsafe_links']}건")
    print(f"제거한 태그 {filtered_tags}개, 제거한 속성 {filtered_attrs}개")

    # 항목을 하나라도 얻은 소스가 있으면 발행한다. 두 소스가 전부 실패한 날에만
    # 발행하지 않는다(8.4).
    # 판정 결과도 파일로 남긴다. 단계 사이 값 전달을 파일로만 하는 규율을
    # 지켜야 재실행이 성립하고, 발행 여부의 근거가 로그에 흩어지지 않는다.
    should_publish = common.any_source_succeeded(status)
    reason = "" if should_publish else "두 소스에서 항목을 하나도 얻지 못했다"
    common.write_json(os.path.join(args.work, "publish.json"),
                      {"publish": should_publish, "reason": reason})

    if not should_publish:
        print(f"\n발행하지 않는다 — {reason}")
        print("기존 페이지를 건드리지 않는다")
        return 0

    if not body.strip():
        body = '<p class="empty">오늘은 실을 주제가 없다.</p>'

    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    repo = os.environ.get("GITHUB_REPOSITORY", "Junroot/reddit-claude")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    page = render_page(
        template,
        generated_at=to_kst_display(status.get("generated_at") or ""),
        built_at=to_kst_display(common.to_iso(common.now())),
        banner=build_banner(status),
        body=body,
        repo_url=f"{server}/{repo}",
        repo_name=repo,
    )

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    open(os.path.join(out_dir, ".nojekyll"), "w").close()

    print(f"\n{out_dir}/index.html 을 썼다 ({len(page)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
