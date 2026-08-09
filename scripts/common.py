#!/usr/bin/env python3
"""파이프라인의 여러 단계가 함께 쓰는 최소한의 도구.

Python 3 표준 라이브러리만 쓴다(D3). 러너에 python3가 기본 설치돼 있으므로
수집·순위 계산·발행 경로에는 의존성 설치 단계가 아예 없고, 이 경로의 실행
실패 원인에서 패키지 저장소 장애와 버전 충돌이 빠진다.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

# Reddit은 요청 헤더에 따라 응답이 달라지는 것이 스파이크에서 확인됐다.
# 브라우저 UA로 보내야 200이 온다. 다른 소스에는 이 값을 쓰지 않는다.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BOT_UA = "reddit-claude-brief/1.0 (+https://github.com/Junroot/reddit-claude)"


# ── 시각 ────────────────────────────────────────────────────────────────────

def now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """UTC ISO8601 문자열로 바꾼다. 파일에 남는 시각 표기는 전부 이 형식이다."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str | None) -> datetime | None:
    """ISO8601 문자열을 UTC datetime으로 바꾼다. 해석할 수 없으면 None.

    게시 시각은 제3자가 준 값이라 형식이 어긋날 수 있다. 예외를 던져 수집
    전체를 세우는 대신 None을 돌려주고, 부르는 쪽이 그 항목을 어떻게 다룰지
    정하게 한다.
    """
    if not text:
        return None
    text = text.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def hours_since(dt: datetime, reference: datetime) -> float:
    return (reference - dt).total_seconds() / 3600.0


# ── HTTP ────────────────────────────────────────────────────────────────────

def http_get(url: str, headers: dict | None = None, timeout: int = 30) -> bytes:
    """GET 한 번. 200이 아니면 예외를 던진다. 재시도하지 않는다.

    재시도를 넣지 않는 것은 Reddit 때문이다. 실측에서 재시도로 두들기면 90회
    중 15회만 성공했고, 한도를 앞당겨 소진시킬 뿐이었다(D9).
    """
    req = urllib.request.Request(url, headers=headers or {"User-Agent": BOT_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_get_json(url: str, headers: dict | None = None, timeout: int = 30):
    return json.loads(http_get(url, headers, timeout).decode("utf-8", "replace"))


# ── 파일 ────────────────────────────────────────────────────────────────────

def read_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ── status.json ─────────────────────────────────────────────────────────────
#
# 실행 기록의 단일 출처다(D13). 발행 여부 판정과 페이지의 수집 상태 배너,
# Discord 알림 문구가 모두 이 한 파일을 읽으므로 서로 어긋날 수 없다.
# 실패는 소스 단위가 아니라 요청 단위로 센다. 소스 단위로만 세면 한 소스
# 안에서 일부 요청만 실패한 상황을 표현할 수 없다.

STATUS_NAME = "status.json"


def blank_status(generated_at: str) -> dict:
    return {
        "generated_at": generated_at,
        # `filtered`는 요청은 성공했지만 수집 조건에 걸려 버린 항목 수다. 지금은
        # 시간 창 안에 있으나 이슈가 아닌 GitHub Pull Request가 여기 잡힌다. 실패와
        # 구분해서 세야 "그날 논의가 적었다"와 "우리가 걸러냈다"를 가려낼 수 있다.
        "sources": {
            "reddit": {"requested": 0, "ok": 0, "failed": 0, "items": 0, "filtered": 0},
            "hn": {"requested": 0, "ok": 0, "failed": 0, "items": 0, "filtered": 0},
            "github": {"requested": 0, "ok": 0, "failed": 0, "items": 0, "filtered": 0},
        },
        "enrich": {"requested": 0, "ok": 0, "failed": 0},
        "cluster": {
            "items": 0,
            "covered_by_llm": 0,
            "dropped_refs": 0,
            "dropped_topics": 0,
            "auto_topics": 0,
            "merged_topics": 0,
        },
        "publish": {
            "refs": 0,
            "unresolved_refs": 0,
            "raw_links": 0,
            "unsafe_links": 0,
            "filtered_tags": 0,
            "filtered_attrs": 0,
        },
    }


def status_path(work: str) -> str:
    return os.path.join(work, STATUS_NAME)


def load_status(work: str) -> dict:
    """status.json을 읽는다. 없으면 빈 기록을 만든다.

    뒤 단계가 앞 단계의 기록 위에 자기 몫을 얹는 구조라, 없을 때 예외를 던지는
    대신 빈 기록으로 시작해 그 단계만이라도 관측 가능하게 둔다.
    """
    data = read_json(status_path(work))
    if not isinstance(data, dict):
        return blank_status(to_iso(now()))
    # 오래된 실행의 기록을 이어받을 때 빠진 칸을 채운다.
    base = blank_status(data.get("generated_at") or to_iso(now()))
    for section, defaults in base.items():
        if not isinstance(defaults, dict):
            continue
        got = data.get(section)
        if not isinstance(got, dict):
            data[section] = defaults
            continue
        for key, value in defaults.items():
            got.setdefault(key, value)
    return data


def save_status(work: str, status: dict) -> None:
    write_json(status_path(work), status)


def record_section(work: str, section: str, values: dict) -> dict:
    """status.json의 한 절을 갱신해 저장하고, 갱신된 전체를 돌려준다."""
    status = load_status(work)
    status.setdefault(section, {}).update(values)
    save_status(work, status)
    return status


# ── 발행 여부 ───────────────────────────────────────────────────────────────

def any_source_succeeded(status: dict) -> bool:
    """항목을 하나라도 얻은 소스가 있는가.

    발행을 거르는 쪽이 더 위험하다. 고정 주소 한 페이지를 덮어쓰는 구조라
    발행하지 않으면 어제 페이지가 그 자리에 남고 독자는 그것을 오늘 브리프로
    읽는다. 그래서 세 소스가 전부 실패한 날에만 발행하지 않는다.
    """
    return any(
        (s or {}).get("items", 0) > 0
        for s in (status.get("sources") or {}).values()
    )
