#!/usr/bin/env python3
"""[3] rank — 보정하고, 점수를 매기고, 정렬하고, 상위 8을 고른다.

입력  work/topics.json (1차 LLM 원본 출력), work/items.json
출력  work/ranked.json

`topics.json`은 덮어쓰지 않는다. 재실행이 원본을 다시 읽을 수 있어야 하고,
"LLM이 쓴 파일"과 "스크립트가 순위를 확정한 파일"이 한 이름을 겸하면 형식
검증이 어느 쪽을 보는지 모호해진다.

수행 순서는 규약이다(5.0a).

    허깨비 참조 제거 → 커버리지 보정 → 중복 주제 병합
    → 등수 산출 → 점수 계산 → 정렬 → 슬롯 예약 → 상위 8 선택

앞의 보정이 뒤의 보정 입력을 바꾸기 때문이다. 허깨비 참조를 먼저 버려야 그
참조가 가리키려 했던 항목이 미커버 상태로 드러나 커버리지 보정이 받고, 참조
제거로 항목 구성이 같아진 두 주제가 그다음 병합 대상이 된다. 순서를 바꾸면
같은 입력에 다른 ranked.json이 나온다.
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from functools import cmp_to_key

import common

TOP_N = 8

# Reddit에만 머무는 화제를 건지는 구제 장치다. 지분 배분이 아니므로 한 글이
# 강제로 확보하는 자리는 최대 하나다.
RESERVED_REDDIT_RANKS = 3

# 두 점수의 상대 차이가 이 값 이내면 동점으로 본다. float64의 정밀도에서 유도한
# 값이고, 누적 반올림 오차보다 충분히 크며 서로 다른 등수 조합이 만드는 실제
# 점수 차이보다 압도적으로 작다.
SCORE_REL_TOL = 1e-9

DIVERSITY = {1: 1.0, 2: 1.5, 3: 2.0}

# 소스별로 등수를 매길 때 쓰는 신호. Reddit은 피드 순서가 곧 등수라 여기 없다.
SIGNALS = {
    "hn": ("points", "num_comments"),
    "github": ("reactions", "comments"),
}


# ── 등수 ────────────────────────────────────────────────────────────────────

def rank_values(values: dict, higher_is_better: bool) -> dict:
    """값을 등수로 바꾼다. 동점인 항목은 같은 등수를 받는다(5.2).

    등수는 "자기보다 엄격히 나은 항목 수 + 1"이다. 동점이 둘이면 1, 1, 3이 된다.
    """
    counts = Counter(values.values())
    better = 0
    rank_of = {}
    for value in sorted(counts, reverse=higher_is_better):
        rank_of[value] = better + 1
        better += counts[value]
    return {key: rank_of[value] for key, value in values.items()}


def build_item_ranks(items: list) -> dict:
    """소스 안에서의 등수를 항목마다 매긴다(5.1).

    Reddit은 수집 단계가 48시간 필터 뒤에 다시 부여한 등수를 그대로 쓴다.
    신호가 둘인 Hacker News와 GitHub은 신호마다 따로 등수를 매기고 평균을 낸 뒤
    다시 등수화한다. `points + num_comments × 2` 같은 식으로 합치면 계수 2가
    근거 없는 상수가 되는데, 이 방식에는 임의 상수가 들어가지 않고 신호의 단위가
    달라도 상관없다.
    """
    ranks: dict = {}

    reddit = [it for it in items if it["source"] == "reddit"]
    if reddit and all("rank" in (it.get("signals") or {}) for it in reddit):
        for it in reddit:
            ranks[it["item_id"]] = int(it["signals"]["rank"])
    else:
        # 수집 단계가 등수를 남기지 않은 입력(손으로 만든 고정 입력 등)에서는
        # 나열 순서를 등수로 본다.
        for position, it in enumerate(reddit, start=1):
            ranks[it["item_id"]] = position

    for source, signal_names in SIGNALS.items():
        group = [it for it in items if it["source"] == source]
        if not group:
            continue
        per_signal = [
            rank_values(
                {it["item_id"]: float((it.get("signals") or {}).get(name) or 0) for it in group},
                higher_is_better=True,
            )
            for name in signal_names
        ]
        averages = {
            it["item_id"]: sum(table[it["item_id"]] for table in per_signal) / len(per_signal)
            for it in group
        }
        ranks.update(rank_values(averages, higher_is_better=False))

    return ranks


# ── 보정 ────────────────────────────────────────────────────────────────────

def drop_ghost_refs(topics: list, known: set) -> tuple:
    """items.json에 없는 항목 ID 참조를 버린다(4.5b).

    긴 영숫자 ID를 한 글자 틀리게 옮겨 적는 것은 LLM의 대표적 실패 양식이다.
    그대로 순위 계산에 넘기면 등수 테이블에서 조회할 수 없어 실행이 죽거나
    그 주제의 점수·항목 수·최고 등수가 조용히 틀리게 계산된다.
    """
    kept_topics, dropped_refs, dropped_topics = [], [], []
    for topic in topics:
        alive = [i for i in topic["item_ids"] if i in known]
        dropped_refs.extend(i for i in topic["item_ids"] if i not in known)
        if not alive:
            # 참조가 전부 허깨비라 남는 항목이 없으면 주제 자체를 버린다.
            dropped_topics.append(topic["topic_id"])
            continue
        kept_topics.append(dict(topic, item_ids=alive))
    return kept_topics, dropped_refs, dropped_topics


def cover_missing(topics: list, items: list) -> tuple:
    """어느 주제에도 담기지 않은 항목을 단일 항목 주제로 편입한다(4.7).

    긴 목록에서 항목을 빠뜨리는 것도 LLM의 대표적 실패 양식인데, 하필 빠진
    것이 Reddit 1위 글이면 슬롯 예약이 매칭 대상을 못 찾아 그날 최대 화제가
    브리프에서 사라진다. 중단시키지 않고 보정하는 것은 누락이 형식 붕괴가
    아니라 판단 누락이고 복구가 가능하기 때문이다.
    """
    covered = {i for t in topics for i in t["item_ids"]}
    added = []
    for item in sorted(items, key=lambda it: it["item_id"]):
        if item["item_id"] in covered:
            continue
        added.append({
            "topic_id": f"auto:{item['item_id']}",
            "title": item.get("title") or item["item_id"],
            "item_ids": [item["item_id"]],
            "auto": True,
        })
    return topics + added, [t["topic_id"] for t in added]


def merge_identical(topics: list) -> tuple:
    """항목 집합이 정확히 같은 주제를 하나로 합친다(4.11).

    제목만 다르고 항목 집합은 같은 두 주제("2.1 릴리스", "2.1 업데이트 반응")를
    그대로 두면 정렬 키가 끝까지 동률이 되어 순서가 입력 나열 순서로 떨어지고,
    같은 내용이 브리프에 두 번 실린다. 부분적으로만 겹치는 주제는 여기 해당하지
    않는다 — 그쪽은 서로 다른 맥락이므로 함께 실리는 것을 허용한다.

    남기는 규칙은 주제 ID 사전순 첫 번째다. 나열 순서와 무관하므로 결정론적이다.
    """
    groups: dict = {}
    for topic in topics:
        groups.setdefault(frozenset(topic["item_ids"]), []).append(topic)

    kept, merged = [], []
    for group in groups.values():
        ordered = sorted(group, key=lambda t: t["topic_id"])
        kept.append(ordered[0])
        merged.extend(t["topic_id"] for t in ordered[1:])
    return kept, sorted(merged)


# ── 점수와 정렬 ─────────────────────────────────────────────────────────────

def score_topics(topics: list, ranks: dict, source_of: dict) -> list:
    """주제 점수 = ( Σ 묶인 항목의 1/등수 ) × 소스 다양성 배수 (5.3).

    합산 대상은 항목 ID로 중복 제거한 뒤 **사전순으로 정렬한** 리스트다. 부동
    소수점 덧셈은 결합법칙을 만족하지 않으므로, 순회 순서가 정해지지 않은 set을
    그대로 더하면 문자열 해시 랜덤화 때문에 같은 입력이 프로세스마다 다른 점수를
    낸다. 정렬한 리스트를 순서대로 더하면 같은 항목 집합은 언제나 비트 단위로
    같은 점수를 낸다.

    등수 r을 1/r로 바꾸는 것은 1위와 2위의 간격을 10위와 11위의 간격보다 크게
    벌리기 위해서다. 실제 투표 수 분포가 그렇다.
    """
    scored = []
    for topic in topics:
        item_ids = sorted(set(topic["item_ids"]))
        total = 0.0
        for item_id in item_ids:
            total += 1.0 / ranks[item_id]
        sources = sorted({source_of[i] for i in item_ids})
        scored.append({
            "topic_id": topic["topic_id"],
            "title": topic.get("title") or "",
            "item_ids": item_ids,
            "item_count": len(item_ids),
            "sources": sources,
            "best_rank": min(ranks[i] for i in item_ids),
            "score": total * DIVERSITY[len(sources)],
            "auto": bool(topic.get("auto")),
        })
    return scored


def scores_tie(a: float, b: float) -> bool:
    """상대 오차 허용 비교(5.4a). 정확 일치로 비교하지 않는다.

    항목 구성이 다른 두 주제가 수학적으로 같은 점수를 갖는 경우가 흔한데,
    합산 순서가 달라 double 값이 마지막 비트에서 갈린다. 등수 {1, 2, 6}을 가진
    두 주제는 3.3333333333333335와 3.333333333333333으로 갈리고, 정확 일치로
    비교하면 이 둘은 동점 사다리에 도달하지 못한 채 float 잡음으로 앞뒤가
    정해진다.
    """
    if a == b:
        return True
    scale = max(abs(a), abs(b))
    if scale == 0.0:
        return True
    return abs(a - b) / scale <= SCORE_REL_TOL


def sort_topics(scored: list) -> list:
    """주제 정렬 키를 적용한다(5.4).

        1. 주제 점수                       내림차순 (상대 오차 1e-9 이내는 동점)
        2. 주제에 묶인 항목 수             내림차순
        3. 주제 내 최고 등수               오름차순
        4. 주제 내 항목 ID 정렬 첫 값      사전순 오름차순
        5. 주제 내 전체 항목 ID 정렬 리스트 사전순 오름차순

    두 번에 나눠 정렬하는 데는 이유가 있다. 1번 키의 허용 오차 비교는 일반적으로
    추이적이지 않아서(a≈b, b≈c인데 a≉c인 경우가 원리상 가능하다), 이것을 그대로
    비교 함수로 넘기면 정렬 결과에 입력 나열 순서가 새어 들 수 있다. 먼저 2~5번
    키로 전순서 정렬을 해 두고 그다음 1번 키만으로 안정 정렬하면, 결과가 오직 앞
    정렬이 만든 표준 순서에만 의존한다. `topics.json`의 나열 순서가 최종 순위에
    전혀 영향을 주지 않아야 한다는 요건이 이렇게 지켜진다.
    """
    ordered = sorted(
        scored,
        key=lambda t: (-t["item_count"], t["best_rank"], t["item_ids"][0], t["item_ids"]),
    )

    def by_score(a: dict, b: dict) -> int:
        if scores_tie(a["score"], b["score"]):
            return 0
        return -1 if a["score"] > b["score"] else 1

    return sorted(ordered, key=cmp_to_key(by_score))


# ── 슬롯 예약과 상위 8 선택 ─────────────────────────────────────────────────

def reserve_slots(ordered: list, items: list, ranks: dict) -> list:
    """Reddit 등수 1~3위 글이 속한 주제의 자리를 확보한다(5.5, 5.5a).

    예약은 주제가 아니라 **글 단위**로 판정한다. 상위 3개 글 각각에 대해 그 글을
    포함한 주제 중 정렬 키 순서상 가장 앞선 하나만 예약 대상으로 삼는다. 한
    항목이 여러 주제에 배정될 수 있으므로, 주제 단위로 예약하면 글 하나가 8칸
    예산을 두 칸씩 잠식한다.
    """
    top_posts = [
        it for it in items
        if it["source"] == "reddit" and ranks.get(it["item_id"], 10 ** 9) <= RESERVED_REDDIT_RANKS
    ]
    top_posts.sort(key=lambda it: (ranks[it["item_id"]], it["item_id"]))

    reserved: list = []
    taken: set = set()
    for post in top_posts:
        for topic in ordered:
            if post["item_id"] in topic["item_ids"]:
                if topic["topic_id"] not in taken:
                    taken.add(topic["topic_id"])
                    reserved.append(topic)
                break
    return reserved


def select_top(ordered: list, reserved: list) -> list:
    """상위 8을 고른다(5.6).

    예약은 상위 8 **집합**에만 관여한다. 선택된 주제의 표시 순서는 언제나 정렬 키
    순서이고, 예약으로 구제된 주제도 자기 정렬 키 위치에 놓인다. 순서까지
    앞당기면 앞자리의 근거가 점수가 아니라 예약이 되어 순위를 설명할 수 없게 된다.

    항목이 겹친다는 이유로 주제를 제외하거나 후순위로 미루지 않는다. 한 글이 여러
    맥락에서 논의될 수 있고, 두 주제의 요약문은 각자의 맥락을 서술한다.
    """
    chosen: set = set()
    for topic in reserved[:TOP_N]:
        chosen.add(topic["topic_id"])
    for topic in ordered:
        if len(chosen) >= TOP_N:
            break
        chosen.add(topic["topic_id"])
    return [t for t in ordered if t["topic_id"] in chosen]


# ── 실행 ────────────────────────────────────────────────────────────────────

def run(topics_doc: dict, items_doc: dict) -> dict:
    """보정부터 상위 8 선택까지를 수행하고 ranked.json 내용을 돌려준다.

    파일을 건드리지 않으므로 테스트가 이 함수만 부르면 된다.
    """
    items = items_doc.get("items") or []
    known = {it["item_id"] for it in items}
    source_of = {it["item_id"]: it["source"] for it in items}

    topics, dropped_refs, dropped_topics = drop_ghost_refs(topics_doc.get("topics") or [], known)
    covered_by_llm = len({i for t in topics for i in t["item_ids"]})
    topics, auto_topics = cover_missing(topics, items)
    topics, merged_topics = merge_identical(topics)

    ranks = build_item_ranks(items)
    ordered = sort_topics(score_topics(topics, ranks, source_of))
    reserved = reserve_slots(ordered, items, ranks)
    top = select_top(ordered, reserved)

    reserved_ids = {t["topic_id"] for t in reserved}
    top_ids = {t["topic_id"] for t in top}
    for position, topic in enumerate(ordered, start=1):
        topic["position"] = position
        topic["reserved"] = topic["topic_id"] in reserved_ids
        topic["selected"] = topic["topic_id"] in top_ids

    return {
        "generated_at": items_doc.get("generated_at") or "",
        "topics": ordered,
        "top": [t["topic_id"] for t in top],
        "item_ranks": ranks,
        "corrections": {
            "dropped_refs": sorted(dropped_refs),
            "dropped_topics": sorted(dropped_topics),
            "auto_topics": auto_topics,
            "merged_topics": merged_topics,
        },
        "counts": {
            "items": len(items),
            "covered_by_llm": covered_by_llm,
            "dropped_refs": len(dropped_refs),
            "dropped_topics": len(dropped_topics),
            "auto_topics": len(auto_topics),
            "merged_topics": len(merged_topics),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="주제를 보정하고 순위를 확정한다")
    parser.add_argument("--work", default="work", help="작업 디렉터리")
    args = parser.parse_args()

    topics_doc = common.read_json(os.path.join(args.work, "topics.json"), {"topics": []})
    items_doc = common.read_json(os.path.join(args.work, "items.json"), {"items": []})

    ranked = run(topics_doc, items_doc)
    common.write_json(os.path.join(args.work, "ranked.json"), ranked)
    common.record_section(args.work, "cluster", ranked["counts"])

    counts = ranked["counts"]
    print(f"항목 {counts['items']}건 중 LLM이 {counts['covered_by_llm']}건을 덮었다")
    print(f"  허깨비 참조 제거 {counts['dropped_refs']}건 (그로 인해 버린 주제 {counts['dropped_topics']}건)")
    print(f"  단일 항목 주제 자동 편입 {counts['auto_topics']}건")
    print(f"  중복 주제 병합 {counts['merged_topics']}건")
    print(f"\n주제 {len(ranked['topics'])}건 중 상위 {len(ranked['top'])}건을 골랐다")
    for topic in ranked["topics"]:
        if not topic["selected"]:
            continue
        mark = " [예약]" if topic["reserved"] else ""
        print(f"  {topic['position']:3d}. {topic['score']:.4f}  "
              f"{'+'.join(topic['sources'])}  {topic['title'][:44]}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
