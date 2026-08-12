#!/usr/bin/env python3
"""Discord 알림 — 성공한 날과 실패한 날 모두 알린다.

성공만 알리면 실패가 침묵과 구분되지 않는다. 이 프로젝트에서 그것은 치명적이다.
구독 인증 토큰은 만료되는데, 만료를 감지할 수단이 이 알림뿐이기 때문이다. 알림이
없으면 브리프는 조용히 멈추고, 고정 주소에는 어제 페이지가 계속 남는다.

`status.json`을 문구의 단일 출처로 쓴다. 페이지의 배너와 발행 여부 판정도 같은
파일을 읽으므로 셋이 서로 어긋날 수 없다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

import common

SOURCE_LABELS = (("reddit", "Reddit"), ("hn", "Hacker News"))


def source_lines(status: dict) -> list:
    """소스마다 한 줄. 갈래는 정상과 수집 실패 둘뿐이다.

    두 소스 모두 실행당 요청이 1회라 "일부 요청만 실패"를 만들 수 있는 경로가
    없다. 요청 건수를 인용하는 표시는 실제로 여러 요청을 보내는 댓글 보강에만
    남는다.
    """
    lines = []
    for key, label in SOURCE_LABELS:
        entry = (status.get("sources") or {}).get(key) or {}
        if entry.get("collected"):
            lines.append(f"· {label} — {entry.get('items', 0)}건")
        else:
            lines.append(f"· {label} — **수집 실패**")
    return lines


def build_message(status: dict, decision: dict, job_status: str, *,
                  brief_url: str, run_url: str, detail: str) -> str:
    enrich = status.get("enrich") or {}
    publish = status.get("publish") or {}
    failed_stage = job_status not in ("", "success")
    published = bool(decision.get("publish"))

    if failed_stage:
        head = "❌ **브리프 실행이 중단됐다**"
    elif not published:
        head = "⚠️ **오늘 브리프를 발행하지 않았다**"
    else:
        head = "📰 **오늘의 Claude Code 커뮤니티 브리프**"

    lines = [head, ""]

    if published and not failed_stage and brief_url:
        lines.append(brief_url)
        lines.append("")

    if not published and not failed_stage:
        lines.append(decision.get("reason") or "발행 조건을 만족하지 못했다")
        lines.append("고정 주소의 페이지는 건드리지 않았다. 지금 보이는 것은 어제 브리프다.")
        lines.append("")

    if failed_stage:
        lines.append(f"job 상태 `{job_status}`. 어느 단계에서 멈췄는지는 로그를 봐야 한다.")
        lines.append("")

    lines.append("**수집 상태**")
    lines.extend(source_lines(status))

    if enrich.get("requested", 0):
        lines.append(f"· Reddit 댓글 보강 — 요청 {enrich['requested']}건 중 {enrich['ok']}건 성공")

    cluster = status.get("cluster") or {}
    corrections = [
        (cluster.get("dropped_refs", 0), "없는 항목 참조 제거"),
        (cluster.get("auto_topics", 0), "단일 항목 주제 자동 편입"),
        (cluster.get("merged_topics", 0), "중복 주제 병합"),
    ]
    active = [f"{label} {count}건" for count, label in corrections if count]
    if active:
        lines.append("")
        lines.append("**주제 묶기 보정** — " + ", ".join(active))

    violations = [
        (publish.get("unresolved_refs", 0), "원문을 찾지 못한 참조"),
        (publish.get("raw_links", 0), "규약을 벗어난 원시 링크"),
        (publish.get("unsafe_links", 0), "링크로 만들지 못한 주소"),
        (publish.get("filtered_tags", 0), "제거한 태그"),
        (publish.get("filtered_attrs", 0), "제거한 속성"),
    ]
    active = [f"{label} {count}건" for count, label in violations if count]
    if active:
        lines.append("")
        lines.append("**본문 무해화** — " + ", ".join(active))

    if detail:
        lines.append("")
        lines.append(detail)

    if run_url:
        lines.append("")
        lines.append(f"실행 로그: {run_url}")

    return "\n".join(lines)


def send(webhook: str, content: str) -> None:
    # Discord 메시지 상한은 2000자다. 넘치면 잘라 보낸다 — 알림 자체가 실패해
    # 침묵으로 끝나는 것이 가장 나쁘다.
    if len(content) > 1900:
        content = content[:1880] + "\n…(생략)"
    request = urllib.request.Request(
        webhook,
        data=json.dumps({"content": content}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": common.BOT_UA},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        print(f"Discord 응답 {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="실행 결과를 Discord로 알린다")
    parser.add_argument("--work", default="work", help="작업 디렉터리")
    parser.add_argument("--job-status", default="success", help="워크플로 job 상태")
    parser.add_argument("--brief-url", default=os.environ.get("BRIEF_URL", ""))
    parser.add_argument("--run-url", default="")
    parser.add_argument("--detail", default="", help="덧붙일 한 줄")
    args = parser.parse_args()

    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not webhook:
        print("✗ DISCORD_WEBHOOK_URL 시크릿이 없다", file=sys.stderr)
        return 1

    status = common.load_status(args.work)
    decision = common.read_json(os.path.join(args.work, "publish.json"),
                                {"publish": False, "reason": "발행 단계에 이르지 못했다"})

    message = build_message(status, decision, args.job_status,
                            brief_url=args.brief_url, run_url=args.run_url, detail=args.detail)
    print(message)
    print("---")

    try:
        send(webhook, message)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        print(f"✗ Discord {exc.code}: {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"✗ Discord 전송 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
