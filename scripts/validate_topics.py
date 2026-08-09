#!/usr/bin/env python3
"""topics.json 형식 검증 — 여기서만 실행을 중단시킨다.

중단 대상은 셋뿐이다(4.4).

    1. 유효한 JSON인가
    2. 기대하는 구조인가
    3. 각 주제가 고유한 주제 ID를 갖는가

이 셋은 형식이 무너진 경우이고, 깨진 출력을 뒤 단계가 억지로 해석하면 실패
원인을 찾기 어려워진다. 반대로 1차 LLM 출력의 나머지 결함 넷 — 실재하지 않는
항목 ID 참조, 커버리지 누락, 항목 집합이 같은 중복 주제, 한 항목의 중복 배정 —
은 형식 붕괴가 아니라 판단의 결함이고 결정론적으로 복구할 수 있다. 그것들은
중단시키지 않고 rank 단계가 보정한 뒤 status.json에 건수를 남긴다.

85건 중 84건이 완벽히 묶인 날에 없는 ID 하나 때문에 브리프가 통째로 사라지면,
고정 주소에는 어제 브리프가 남아 독자가 그것을 오늘치로 읽는다. 발행을 거르는
쪽이 더 해롭다는 판정 규칙과 어긋난다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def validate(raw: str) -> dict:
    """검증을 통과하면 파싱된 객체를, 실패하면 ValueError를 돌려준다."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"유효한 JSON이 아니다: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("기대 구조가 아니다: 최상위가 객체여야 한다")
    topics = data.get("topics")
    if not isinstance(topics, list):
        raise ValueError("기대 구조가 아니다: topics가 배열이어야 한다")

    seen: set[str] = set()
    for i, topic in enumerate(topics):
        if not isinstance(topic, dict):
            raise ValueError(f"기대 구조가 아니다: topics[{i}]가 객체여야 한다")
        for field, kind, label in (
            ("topic_id", str, "문자열"),
            ("title", str, "문자열"),
            ("item_ids", list, "배열"),
        ):
            if not isinstance(topic.get(field), kind):
                raise ValueError(f"기대 구조가 아니다: topics[{i}].{field}가 {label}여야 한다")
        for j, item_id in enumerate(topic["item_ids"]):
            if not isinstance(item_id, str):
                raise ValueError(f"기대 구조가 아니다: topics[{i}].item_ids[{j}]가 문자열이어야 한다")

        # 중복 주제 병합(4.11)이 "주제 ID 사전순 첫 번째를 남긴다"는 규칙에
        # 기대므로, 주제 ID의 고유성은 형식 요건이다.
        topic_id = topic["topic_id"]
        if topic_id in seen:
            raise ValueError(f"주제 ID가 고유하지 않다: {topic_id!r}가 두 번 나온다")
        seen.add(topic_id)

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="topics.json 형식을 검증한다")
    parser.add_argument("--work", default="work", help="작업 디렉터리")
    args = parser.parse_args()

    path = os.path.join(args.work, "topics.json")
    if not os.path.exists(path):
        print(f"✗ {path} 이 없다. 주제 묶기 단계가 파일을 남기지 못했다", file=sys.stderr)
        return 1

    with open(path, encoding="utf-8") as f:
        raw = f.read()

    try:
        data = validate(raw)
    except ValueError as exc:
        print(f"✗ 형식 검증 실패 — {exc}", file=sys.stderr)
        return 1

    topics = data["topics"]
    referenced = {i for t in topics for i in t["item_ids"]}
    print(f"✓ 형식 검증 통과 — 주제 {len(topics)}건, 참조된 항목 {len(referenced)}건")
    print("  실재하지 않는 참조·커버리지 누락·중복 주제는 rank 단계가 보정한다")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
