#!/usr/bin/env python3
"""rank 단계의 보정과 순위 계산 테스트 (4장 보정, 5장 순위).

여기서 지키려는 것은 하나다 — `topics.json`의 주제 나열 순서와 주제 내 항목
나열 순서가 최종 순위와 상위 8 선택에 전혀 영향을 주지 않는 것. 순서가 결과를
바꾸면 순위 결정을 사실상 LLM에 넘기는 것이 된다.

    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import textwrap
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import collect  # noqa: E402
import common  # noqa: E402
import rank  # noqa: E402

NOW = common.parse_iso("2026-08-10T00:00:00Z")


# ── 고정 입력 만들기 ────────────────────────────────────────────────────────

def reddit_item(item_id: str, rank_value: int, hours_ago: int = 5) -> dict:
    return {
        "item_id": item_id,
        "source": "reddit",
        "title": f"reddit {item_id}",
        "url": f"https://www.reddit.com/r/ClaudeCode/comments/{item_id}/",
        "author": "u/someone",
        "published_at": common.to_iso(NOW - timedelta(hours=hours_ago)),
        "published_raw": "",
        "body": "",
        "signals": {"feed_position": rank_value, "rank": rank_value},
    }


def hn_item(item_id: str, points: int, num_comments: int) -> dict:
    return {
        "item_id": item_id,
        "source": "hn",
        "title": f"hn {item_id}",
        "url": f"https://news.ycombinator.com/item?id={item_id}",
        "author": "someone",
        "published_at": common.to_iso(NOW - timedelta(hours=5)),
        "published_raw": "",
        "body": "",
        "signals": {"points": points, "num_comments": num_comments, "story_url": ""},
    }


def topic(topic_id: str, *item_ids: str, title: str = "") -> dict:
    return {"topic_id": topic_id, "title": title or topic_id, "item_ids": list(item_ids)}


def run(items: list, topics: list) -> dict:
    return rank.run({"topics": topics}, {"items": items, "generated_at": common.to_iso(NOW)})


def find(result: dict, topic_id: str) -> dict:
    for entry in result["topics"]:
        if entry["topic_id"] == topic_id:
            return entry
    raise AssertionError(f"주제 {topic_id!r}가 결과에 없다")


def shuffled(result_topics: list, seed: int) -> list:
    """주제 나열 순서와 주제 내 항목 나열 순서를 함께 섞는다."""
    rng = random.Random(seed)
    out = []
    for entry in result_topics:
        ids = list(entry["item_ids"])
        rng.shuffle(ids)
        out.append(dict(entry, item_ids=ids))
    rng.shuffle(out)
    return out


# ── 4.5d 허깨비 참조 보정 ───────────────────────────────────────────────────

class GhostReferenceTest(unittest.TestCase):
    """items.json에 없는 항목 ID 참조를 버리되 실행은 중단하지 않는다."""

    def setUp(self):
        self.items = [
            reddit_item("rd_01", 1),
            reddit_item("rd_02", 2),
            hn_item("hn_01", 100, 100),
        ]

    def test_없는_참조만_빠지고_나머지는_유지된다(self):
        result = run(self.items, [
            topic("t1", "rd_01", "rd_ghost", "hn_01"),
        ])
        self.assertEqual(find(result, "t1")["item_ids"], ["hn_01", "rd_01"])
        self.assertEqual(result["corrections"]["dropped_refs"], ["rd_ghost"])
        self.assertEqual(result["counts"]["dropped_refs"], 1)

    def test_참조가_전부_허깨비인_주제는_버려진다(self):
        result = run(self.items, [
            topic("t1", "rd_01", "rd_02", "hn_01"),
            topic("t2", "ghost_a", "ghost_b"),
        ])
        self.assertEqual(result["corrections"]["dropped_topics"], ["t2"])
        self.assertEqual(result["counts"]["dropped_topics"], 1)
        with self.assertRaises(AssertionError):
            find(result, "t2")

    def test_제거로_미커버가_된_항목을_커버리지_보정이_받는다(self):
        # rd_02를 가리키려다 한 글자를 틀린 참조. 참조가 사라지면 rd_02는 어느
        # 주제에도 담기지 않은 상태가 되고, 바로 다음 보정이 그것을 받는다.
        result = run(self.items, [
            topic("t1", "rd_01", "hn_01"),
            topic("t2", "rd_0X"),
        ])
        self.assertEqual(result["counts"]["dropped_refs"], 1)
        self.assertEqual(result["counts"]["dropped_topics"], 1)
        self.assertIn("auto:rd_02", result["corrections"]["auto_topics"])
        covered = {i for t in result["topics"] for i in t["item_ids"]}
        self.assertEqual(covered, {"rd_01", "rd_02", "hn_01"})


# ── 4.9 커버리지 보정 ───────────────────────────────────────────────────────

class CoverageTest(unittest.TestCase):
    """항목 85건 중 50건만 묶인 입력에서 보정이 모든 항목을 덮는다."""

    def setUp(self):
        self.items = (
            [reddit_item(f"rd_{n:02d}", n) for n in range(1, 26)]
            + [hn_item(f"hn_{n:02d}", 100 - n, 100 - n) for n in range(1, 61)]
        )
        self.assertEqual(len(self.items), 85)

    def test_35건이_자동_편입되어_전부_덮인다(self):
        clustered = [it["item_id"] for it in self.items[:50]]
        topics = [topic(f"t{i}", *clustered[i * 5:(i + 1) * 5]) for i in range(10)]

        result = run(self.items, topics)

        self.assertEqual(result["counts"]["items"], 85)
        self.assertEqual(result["counts"]["covered_by_llm"], 50)
        self.assertEqual(result["counts"]["auto_topics"], 35)

        covered = {i for t in result["topics"] for i in t["item_ids"]}
        self.assertEqual(covered, {it["item_id"] for it in self.items})

    def test_누락이_없는_날은_자동_편입이_0건이다(self):
        topics = [topic(f"t{i}", it["item_id"]) for i, it in enumerate(self.items)]
        result = run(self.items, topics)
        self.assertEqual(result["counts"]["auto_topics"], 0)
        self.assertEqual(result["corrections"]["auto_topics"], [])

    def test_자동_편입된_주제도_같은_점수_공식을_따른다(self):
        # rd_01(등수 1)만 빼고 전부 묶는다. 편입된 주제의 점수는 1/1 × 1.0이다.
        rest = [it["item_id"] for it in self.items if it["item_id"] != "rd_01"]
        result = run(self.items, [topic("t1", *rest)])
        auto = find(result, "auto:rd_01")
        self.assertEqual(auto["item_count"], 1)
        self.assertEqual(auto["sources"], ["reddit"])
        self.assertAlmostEqual(auto["score"], 1.0)


# ── 4.13 중복 주제 병합 ─────────────────────────────────────────────────────

class MergeTest(unittest.TestCase):
    """항목 집합이 정확히 같은 주제만 합친다."""

    def setUp(self):
        self.items = [
            reddit_item("rd_01", 1),
            reddit_item("rd_02", 2),
            hn_item("hn_01", 50, 50),
        ]

    def test_주제_ID_사전순_첫_번째가_남는다(self):
        result = run(self.items, [
            topic("zeta", "rd_01", "hn_01", title="2.1 업데이트 반응"),
            topic("alpha", "hn_01", "rd_01", title="2.1 릴리스"),
            topic("solo", "rd_02"),
        ])
        self.assertEqual(result["counts"]["merged_topics"], 1)
        self.assertEqual(result["corrections"]["merged_topics"], ["zeta"])
        find(result, "alpha")
        with self.assertRaises(AssertionError):
            find(result, "zeta")

    def test_나열_순서를_섞어도_남는_주제가_같다(self):
        base = [
            topic("zeta", "rd_01", "hn_01"),
            topic("alpha", "hn_01", "rd_01"),
            topic("solo", "rd_02"),
        ]
        expected = [t["topic_id"] for t in run(self.items, base)["topics"]]
        for seed in range(6):
            got = [t["topic_id"] for t in run(self.items, shuffled(base, seed))["topics"]]
            self.assertEqual(got, expected, f"seed={seed}")

    def test_일부만_겹치는_두_주제는_병합되지_않는다(self):
        result = run(self.items, [
            topic("a", "rd_01", "hn_01"),
            topic("b", "rd_01", "rd_02"),
        ])
        self.assertEqual(result["counts"]["merged_topics"], 0)
        find(result, "a")
        find(result, "b")


# ── 5.9 명세의 계산 예시 ────────────────────────────────────────────────────

class ScoreFormulaTest(unittest.TestCase):

    def test_Reddit_2위와_HN_4위가_묶이면_1점5다(self):
        items = [
            reddit_item("rd_01", 1),
            reddit_item("rd_02", 2),
            hn_item("hn_01", 40, 40),
            hn_item("hn_02", 30, 30),
            hn_item("hn_03", 20, 20),
            hn_item("hn_04", 10, 10),
        ]
        result = run(items, [topic("t1", "rd_02", "hn_04")])

        self.assertEqual(result["item_ranks"]["rd_02"], 2)
        self.assertEqual(result["item_ranks"]["hn_04"], 4)

        got = find(result, "t1")
        self.assertEqual(got["sources"], ["hn", "reddit"])
        # 0.5 + 0.25 = 0.75, 소스 2개이므로 배수 2.0 → 1.5
        self.assertAlmostEqual(got["score"], 1.5)

    def test_상위_등수의_간격이_하위보다_크다(self):
        items = [reddit_item(f"rd_{n:02d}", n) for n in range(1, 12)]
        result = run(items, [topic(f"t{n}", f"rd_{n:02d}") for n in range(1, 12)])
        by_rank = {find(result, f"t{n}")["score"]: n for n in range(1, 12)}
        scores = {n: s for s, n in by_rank.items()}
        self.assertAlmostEqual(scores[1] - scores[2], 0.5)
        self.assertGreater(scores[1] - scores[2], scores[10] - scores[11])

    def test_동점인_항목은_같은_등수를_받는다(self):
        items = [hn_item("hn_01", 100, 100), hn_item("hn_02", 50, 50), hn_item("hn_03", 50, 50)]
        result = run(items, [topic("t1", "hn_01")])
        self.assertEqual(result["item_ranks"]["hn_01"], 1)
        self.assertEqual(result["item_ranks"]["hn_02"], 2)
        self.assertEqual(result["item_ranks"]["hn_03"], 2)

    def test_한_주제_안의_같은_항목은_한_번만_센다(self):
        items = [reddit_item("rd_01", 1), reddit_item("rd_02", 2)]
        result = run(items, [topic("t1", "rd_01", "rd_01", "rd_02")])
        got = find(result, "t1")
        self.assertEqual(got["item_ids"], ["rd_01", "rd_02"])
        self.assertEqual(got["item_count"], 2)
        self.assertAlmostEqual(got["score"], 1.0 + 0.5)


# ── 5.7c 부동소수점 동점 ────────────────────────────────────────────────────

class FloatTieTest(unittest.TestCase):
    """등수 {1, 2, 6}을 갖는 두 주제는 합산 순서 때문에 double 값이 갈린다."""

    def setUp(self):
        # Hacker News 항목의 ID 사전순과 등수 순서를 일부러 어긋나게 둔다. 그래야
        # "float 값이 큰 쪽"과 "4번 키에서 이기는 쪽"이 서로 달라져서, 정확
        # 일치로 비교했을 때와 허용 오차로 비교했을 때의 결과가 갈린다.
        #
        # HN 등수는 points와 num_comments 기준 등수의 평균으로 정해지므로 두 신호를
        # 같은 값으로 두면 등수가 점수 내림차순 그대로 나온다. 90짜리 둘이 동점 2위를
        # 차지하므로 다음 값은 4위이고, 그 아래로 5위와 6위가 이어진다.
        self.items = (
            [reddit_item("rd_hi", 1), reddit_item("rd_lo", 6)]
            + [hn_item("hn_b1", 100, 100),                                  # 1위
               hn_item("hn_c2", 90, 90), hn_item("hn_d2", 90, 90),          # 공동 2위
               hn_item("hn_e4", 80, 80), hn_item("hn_f5", 70, 70),          # 4위, 5위
               hn_item("hn_a6", 60, 60)]                                    # 6위
        )
        # 합산은 항목 ID 사전순이다.
        #   t_big   : hn_b1(1) → hn_c2(2) → rd_lo(6)   즉 (1, 2, 6) 순
        #   t_small : hn_a6(6) → hn_d2(2) → rd_hi(1)   즉 (6, 2, 1) 순
        # 두 주제 모두 Reddit과 HN에 걸쳐 있어 배수 2.0을 똑같이 받는다.
        self.topics = [
            topic("t_big", "hn_b1", "hn_c2", "rd_lo"),
            topic("t_small", "hn_a6", "hn_d2", "rd_hi"),
        ]

    def test_두_점수가_비트_단위로는_다르다(self):
        result = run(self.items, self.topics)
        big, small = find(result, "t_big")["score"], find(result, "t_small")["score"]
        self.assertNotEqual(big, small, "이 테스트가 허용 오차 경로를 밟으려면 두 값이 달라야 한다")
        self.assertEqual(repr(big), "3.3333333333333335")
        self.assertEqual(repr(small), "3.333333333333333")

    def test_동점으로_판정되어_뒤_키로_갈린다(self):
        result = run(self.items, self.topics)
        big, small = find(result, "t_big")["score"], find(result, "t_small")["score"]

        self.assertGreater(big, small)
        self.assertTrue(rank.scores_tie(big, small))

        # 정확 일치로 비교했다면 값이 큰 t_big이 앞섰을 것이다. 허용 오차 비교가
        # 둘을 동점으로 만들면 항목 수(3=3)와 최고 등수(1=1)를 지나 4번 키로
        # 내려가고, hn_a6 < hn_b1 이므로 t_small이 앞선다. 두 비교 방식이 서로
        # 다른 답을 내는 입력이라야 이 검사가 의미를 갖는다.
        self.assertEqual([t["topic_id"] for t in result["topics"][:2]], ["t_small", "t_big"])

    def test_나열_순서를_섞어도_같다(self):
        expected = [t["topic_id"] for t in run(self.items, self.topics)["topics"]]
        for seed in range(8):
            got = [t["topic_id"] for t in run(self.items, shuffled(self.topics, seed))["topics"]]
            self.assertEqual(got, expected, f"seed={seed}")


# ── 5.8 구조적 동점 ─────────────────────────────────────────────────────────

class StructuralTieTest(unittest.TestCase):
    """서로 다른 소스의 같은 등수 단일 항목 주제는 정렬 키로 일관되게 갈린다."""

    def test_소스가_달라도_등수가_같으면_점수가_정확히_같다(self):
        items = [reddit_item("rd_01", 1), hn_item("hn_01", 100, 100)]
        topics = [topic("t_rd", "rd_01"), topic("t_hn", "hn_01")]
        result = run(items, topics)

        scores = [find(result, t)["score"] for t in ("t_rd", "t_hn")]
        self.assertEqual(len(set(scores)), 1, "두 점수가 비트 단위로 같아야 구조적 동점이다")

        # 항목 수와 최고 등수까지 같으므로 4번 키(항목 ID 사전순)가 가른다.
        self.assertEqual([t["topic_id"] for t in result["topics"]], ["t_hn", "t_rd"])

    def test_나열_순서를_섞어도_같다(self):
        items = [reddit_item("rd_01", 1), hn_item("hn_01", 100, 100)]
        topics = [topic("t_rd", "rd_01"), topic("t_hn", "hn_01")]
        for seed in range(8):
            got = [t["topic_id"] for t in run(items, shuffled(topics, seed))["topics"]]
            self.assertEqual(got, ["t_hn", "t_rd"], f"seed={seed}")

    def test_최고_등수가_점수와_항목_수_다음을_가른다(self):
        items = [
            reddit_item("rd_01", 1), reddit_item("rd_05", 5),
            hn_item("hn_01", 50, 50), hn_item("hn_02", 40, 40),
            hn_item("hn_03", 30, 30), hn_item("hn_04", 20, 20), hn_item("hn_05", 10, 10),
        ]
        # 두 주제 모두 항목 2건에 소스 1개다. 최고 등수는 2와 3이므로 2인 쪽이 앞선다.
        result = run(items, [topic("t_low", "hn_03", "hn_04"), topic("t_high", "hn_02", "hn_03")])
        a, b = find(result, "t_high"), find(result, "t_low")
        self.assertEqual(a["best_rank"], 2)
        self.assertEqual(b["best_rank"], 3)
        self.assertLess(a["position"], b["position"])


# ── 5.7 / 5.7a / 5.7e 결정론과 항목 겹침 ────────────────────────────────────

class DeterminismTest(unittest.TestCase):

    def build(self):
        # 옛 GitHub 항목 12건은 hn_09~hn_20으로 옮겼다. 주제마다 묶인 항목 수와
        # 소스 조합의 모양을 그대로 두어 같은 정렬 키 사다리를 밟게 한다.
        items = (
            [reddit_item(f"rd_{n:02d}", n) for n in range(1, 11)]
            + [hn_item(f"hn_{n:02d}", 100 - 3 * n, 90 - 2 * n) for n in range(1, 9)]
            + [hn_item(f"hn_{n + 8:02d}", 60 - 4 * n, 45 - n) for n in range(1, 13)]
        )
        topics = [
            topic("t01", "rd_01", "hn_09", "hn_01"),
            topic("t02", "rd_02", "hn_02"),
            topic("t03", "hn_10", "hn_11", "rd_03"),
            topic("t04", "hn_03"),
            topic("t05", "rd_04", "rd_05", "hn_12"),
            topic("t06", "hn_04", "hn_13"),
            topic("t07", "rd_06", "hn_05", "hn_14"),
            topic("t08", "hn_15", "hn_16"),
            topic("t09", "rd_07", "hn_06"),
            topic("t10", "hn_17", "rd_08"),
            topic("t11", "hn_07", "hn_18"),
            topic("t12", "rd_09", "rd_10", "hn_08", "hn_19", "hn_20"),
        ]
        return items, topics

    def test_같은_입력에_같은_순서(self):
        items, topics = self.build()
        first, second = run(items, topics), run(items, topics)
        self.assertEqual([t["topic_id"] for t in first["topics"]],
                         [t["topic_id"] for t in second["topics"]])
        self.assertEqual(first["top"], second["top"])

    def test_나열_순서를_섞어도_최종_순위와_상위_8이_같다(self):
        items, topics = self.build()
        base = run(items, topics)
        expected_order = [t["topic_id"] for t in base["topics"]]
        for seed in range(12):
            got = run(items, shuffled(topics, seed))
            self.assertEqual([t["topic_id"] for t in got["topics"]], expected_order, f"seed={seed}")
            self.assertEqual(got["top"], base["top"], f"seed={seed}")

    def test_상위는_최대_8개다(self):
        items, topics = self.build()
        self.assertEqual(len(run(items, topics)["top"]), 8)

    def test_후보가_상한에_못_미치면_있는_만큼만(self):
        items = [reddit_item("rd_01", 1), reddit_item("rd_02", 2), reddit_item("rd_03", 3)]
        result = run(items, [topic("t1", "rd_01"), topic("t2", "rd_02"), topic("t3", "rd_03")])
        self.assertEqual(len(result["top"]), 3)


class SharedItemTest(unittest.TestCase):
    """한 항목이 두 주제에 배정되는 것은 허용한다(5.7a, 5.7e)."""

    def build(self):
        # hn_01과 hn_03을 신호까지 같게 두어 둘 다 HN 등수 1을 받게 한다. 그래야
        # rd_01을 공유하는 두 주제가 같은 점수를 갖고, 겹침 때문에 어느 한쪽이
        # 깎이는지를 볼 수 있다.
        items = (
            [reddit_item(f"rd_{n:02d}", n) for n in range(1, 6)]
            + [hn_item("hn_01", 100, 100), hn_item("hn_02", 80, 80), hn_item("hn_03", 100, 100)]
        )
        # rd_01이 두 맥락에 함께 논의된 상황.
        topics = [
            topic("t_mcp", "rd_01", "hn_03"),
            topic("t_release", "rd_01", "hn_01"),
            topic("t_other", "rd_02", "hn_02"),
        ]
        return items, topics

    def test_두_주제_모두_자기_점수를_온전히_갖는다(self):
        items, topics = self.build()
        result = run(items, topics)
        # 겹친다는 이유로 어느 쪽의 점수도 깎지 않는다.
        for topic_id in ("t_mcp", "t_release"):
            got = find(result, topic_id)
            self.assertEqual(got["item_count"], 2)
            self.assertIn("rd_01", got["item_ids"])
            self.assertAlmostEqual(got["score"], (1.0 + 1.0) * 2.0)

    def test_겹침을_이유로_제외하거나_후순위로_밀지_않는다(self):
        items, topics = self.build()
        result = run(items, topics)
        self.assertIn("t_mcp", result["top"])
        self.assertIn("t_release", result["top"])
        # 점수 순으로도 둘이 나란히 맨 앞이다.
        self.assertEqual(set(result["top"][:2]), {"t_mcp", "t_release"})

    def test_예약이_자리를_하나만_쓴다(self):
        items, topics = self.build()
        result = run(items, topics)
        reserved = [t["topic_id"] for t in result["topics"] if t["reserved"]]
        # rd_01(등수 1)은 두 주제에 들어 있지만 예약 대상은 정렬 키 앞선 하나뿐이다.
        self.assertEqual(reserved.count("t_mcp") + reserved.count("t_release"), 1)

    def test_나열_순서를_섞어도_같다(self):
        items, topics = self.build()
        base = run(items, topics)
        for seed in range(10):
            got = run(items, shuffled(topics, seed))
            self.assertEqual([t["topic_id"] for t in got["topics"]],
                             [t["topic_id"] for t in base["topics"]], f"seed={seed}")
            self.assertEqual(got["top"], base["top"], f"seed={seed}")
            self.assertEqual([t["topic_id"] for t in got["topics"] if t["reserved"]],
                             [t["topic_id"] for t in base["topics"] if t["reserved"]], f"seed={seed}")


# ── 5.5 / 5.7b 슬롯 예약 ────────────────────────────────────────────────────

class ReservationTest(unittest.TestCase):

    def build_buried(self):
        """Reddit 1위 글이 속한 주제가 점수로는 상위 8에 못 드는 날.

        Reddit 1위 단일 항목 주제의 점수는 1/1 × 1.0 = 1.0으로 원래 꽤 높다.
        이것을 8위 밖으로 밀어내려면 그보다 높은 주제가 여덟 개 넘게 있어야 한다.
        Hacker News 항목의 신호를 전부 동점으로 두면 모두 등수 1을 받으므로, HN
        스토리 둘을 묶은 주제가 (1 + 1) × 1.0 = 2.0으로 열 개 만들어진다.

        HN에서 큰 스토리가 여러 건 터진 날이 예약이 필요한 날이라는 것이 이
        고정 입력이 재현하는 상황이다.
        """
        items = [reddit_item("rd_01", 1)]
        for n in range(1, 21):
            items.append(hn_item(f"hn_{n:02d}", 100, 100))
        topics = [topic("t_buried", "rd_01")]
        topics += [topic(f"t_{n:02d}", f"hn_{2 * n - 1:02d}", f"hn_{2 * n:02d}")
                   for n in range(1, 11)]
        return items, topics

    def test_묻힌_Reddit_1위_주제가_구제된다(self):
        items, topics = self.build_buried()
        result = run(items, topics)

        buried = find(result, "t_buried")
        self.assertTrue(buried["reserved"])
        self.assertTrue(buried["selected"])
        self.assertIn("t_buried", result["top"])
        # 점수로는 8위 밖이다. 예약이 없었다면 실리지 않았다.
        self.assertGreater(buried["position"], 8)

    def test_구제된_주제의_표시_위치는_정렬_키_순서_그대로다(self):
        items, topics = self.build_buried()
        result = run(items, topics)

        order = [t["topic_id"] for t in result["topics"] if t["selected"]]
        self.assertEqual(result["top"], order)
        # 예약으로 들어왔다고 앞자리로 당기지 않는다. 표시 순서상 맨 뒤다.
        self.assertEqual(result["top"][-1], "t_buried")
        positions = [find(result, t)["position"] for t in result["top"]]
        self.assertEqual(positions, sorted(positions))

    def test_이미_상위권이면_최종_목록을_바꾸지_않는다(self):
        items = [reddit_item(f"rd_{n:02d}", n) for n in range(1, 5)]
        topics = [topic(f"t{n}", f"rd_{n:02d}") for n in range(1, 5)]
        result = run(items, topics)
        self.assertEqual(result["top"], ["t1", "t2", "t3", "t4"])

    def test_예약이_차지하는_자리는_최대_3개다(self):
        items, topics = self.build_buried()
        items += [reddit_item("rd_02", 2), reddit_item("rd_03", 3), reddit_item("rd_04", 4)]
        topics += [topic("t_r2", "rd_02"), topic("t_r3", "rd_03"), topic("t_r4", "rd_04")]
        result = run(items, topics)

        reserved = [t["topic_id"] for t in result["topics"] if t["reserved"]]
        self.assertEqual(len(reserved), 3)
        self.assertEqual(set(reserved), {"t_buried", "t_r2", "t_r3"})
        # 등수 4위 글은 예약 대상이 아니다.
        self.assertFalse(find(result, "t_r4")["reserved"])
        self.assertEqual(len(result["top"]), 8)


# ── 5.10 피드 상위가 필터에 걸린 날 ─────────────────────────────────────────

FEED_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
{entries}
</feed>
"""

ENTRY_TEMPLATE = """  <entry>
    <id>t3_{short}</id>
    <title>{title}</title>
    <link href="https://www.reddit.com/r/ClaudeCode/comments/{short}/"/>
    <author><name>/u/tester</name></author>
    <published>{published}</published>
    <updated>{published}</updated>
    <content type="html">&lt;p&gt;본문 {short}&lt;/p&gt;</content>
  </entry>"""


def build_feed(ages_in_hours: list) -> bytes:
    entries = "\n".join(
        ENTRY_TEMPLATE.format(
            short=f"p{n:02d}",
            title=f"post {n}",
            published=common.to_iso(NOW - timedelta(hours=hours)),
        )
        for n, hours in enumerate(ages_in_hours, start=1)
    )
    return FEED_TEMPLATE.format(entries=entries).encode("utf-8")


class RedditWindowTest(unittest.TestCase):
    """피드 1~3위가 모두 48시간 필터로 걸린 날에도 등수 1이 존재한다."""

    def test_남은_글에_등수가_1부터_다시_부여된다(self):
        parsed = collect.parse_reddit_feed(build_feed([60, 55, 50, 5, 3]))
        self.assertEqual([p["signals"]["feed_position"] for p in parsed], [1, 2, 3, 4, 5])

        kept, dropped = collect.filter_and_rank_reddit(parsed, NOW)

        self.assertEqual(dropped, 3)
        self.assertEqual([k["item_id"] for k in kept], ["rd_p04", "rd_p05"])
        self.assertEqual([k["signals"]["rank"] for k in kept], [1, 2])
        # 원래 피드 위치 번호는 등수로 쓰지 않는다. 보존은 하되 4가 등수가 되면 안 된다.
        self.assertEqual(kept[0]["signals"]["feed_position"], 4)

    def test_24시간을_넘겼으나_48시간_이내인_글은_남는다(self):
        parsed = collect.parse_reddit_feed(build_feed([30]))
        kept, dropped = collect.filter_and_rank_reddit(parsed, NOW)
        self.assertEqual(dropped, 0)
        self.assertEqual(kept[0]["signals"]["rank"], 1)

    def test_필터_후_등수로_슬롯_예약이_작동한다(self):
        parsed = collect.parse_reddit_feed(build_feed([60, 55, 50, 5]))
        kept, _ = collect.filter_and_rank_reddit(parsed, NOW)

        items = list(kept)
        for n in range(1, 21):
            items.append(hn_item(f"hn_{n:02d}", 200, 200))
        topics = [topic("t_reddit", "rd_p04")]
        topics += [topic(f"t_{n:02d}", f"hn_{2 * n - 1:02d}", f"hn_{2 * n:02d}")
                   for n in range(1, 11)]

        result = run(items, topics)
        self.assertEqual(result["item_ranks"]["rd_p04"], 1)
        self.assertTrue(find(result, "t_reddit")["reserved"])
        self.assertIn("t_reddit", result["top"])


# ── 5.7d 합산 순서 고정 ─────────────────────────────────────────────────────

CHILD = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {scripts!r})
    import rank

    items, topics = [], []
    ids = []
    for n in range(1, 41):
        for source, signals in (("reddit", {{"rank": n}}),
                                ("hn", {{"points": 400 - n, "num_comments": 400 - n}})):
            item_id = "%s_%03d" % (source[:2], n)
            ids.append(item_id)
            items.append({{"item_id": item_id, "source": source, "title": item_id,
                          "signals": signals}})
    topics.append({{"topic_id": "t_all", "title": "t", "item_ids": ids}})

    result = rank.run({{"topics": topics}}, {{"items": items}})
    score = [t for t in result["topics"] if t["topic_id"] == "t_all"][0]["score"]
    print(repr(score))
""")


class SummationOrderTest(unittest.TestCase):
    """PYTHONHASHSEED를 달리한 별도 프로세스에서도 점수가 비트 단위로 같다."""

    def test_해시_시드가_달라도_점수가_같다(self):
        scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
        source = CHILD.format(scripts=os.path.abspath(scripts))

        outputs = []
        for seed in ("0", "1", "12345", "99991"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            done = subprocess.run(
                [sys.executable, "-c", source],
                capture_output=True, text=True, env=env, check=True,
            )
            outputs.append(done.stdout.strip())

        self.assertEqual(len(set(outputs)), 1,
                         f"해시 시드에 따라 점수가 달라졌다: {outputs}")


if __name__ == "__main__":
    unittest.main()
