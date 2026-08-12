# design.md 적대적 리뷰

검증 통과 지적 1건.

### [높음] GitHub이 빠지면 "요청 단위 기록" 요구사항의 유일한 실증 시나리오가 성립 불가능해진다

- **위치**: `design.md` Migration Plan 1 (델타 범위 판단) / `openspec/changes/remove-github-source/specs/community-collection/spec.md:94-97` (MODIFIED "수집 결과 기록"의 `#### Scenario: 부분 실패 기록`) / `openspec/specs/community-collection/spec.md:132-142`
- **설계 주장**: design.md Migration Plan 1은 델타 범위를 정하는 기준으로 "시나리오의 **WHEN**이 … 소스가 둘인 세계에서는 영영 성립하지 않는 전제가 된다"를 세우고, 그 기준을 `daily-automation`의 "스케줄 비활성화 방지"와 `brief-publication`의 "Discord 알림" 두 곳에만 적용해 "GitHub이 직접 등장하는 요구사항에 그치지 않는다"고 범위를 닫았다. 그 결과 확정된 델타는 `community-collection`의 "수집 결과 기록"을 소스 이름만 바꿔 유지하며, 요구사항 본문의 "수집 결과를 요청 단위로 기록해야 한다(SHALL). 소스 단위로만 기록해서는 안 된다(MUST NOT)"와 그 근거 "요청 단위로 기록해야 한 소스 안에서 일부 요청만 실패한 상황을 표현할 수 있다"를 그대로 둔 채, 실증 시나리오의 **WHEN**을 "GitHub 이슈를 3회 요청해 2회 성공하고 1회 실패한다"에서 "Hacker News 검색을 3회 요청해 2회 성공하고 1회 실패한다"로 갈아 끼웠다.
- **무엇이 깨지나**: 이 변경 후 남는 두 소스는 **어느 쪽도 한 실행에서 요청을 2회 이상 보내지 않는다.** `collect_reddit`은 피드 URL 하나로 `_get`을 1회 호출하고(`scripts/collect.py:161-167`), `collect_hn`은 `hitsPerPage=100`짜리 Algolia 호출 하나로 `_get`을 1회 호출한다(`scripts/collect.py:172-215`, 페이지네이션·재시도 루프 없음). `_get`은 호출당 `requested`를 1 올리고 실패 시 `failed`를 1 올린 뒤 그대로 re-raise 하므로(`scripts/collect.py:83-92`), 예외는 그 소스의 수집 함수를 통째로 끝낸다. `main()`의 except 분기도 `requested == 0`일 때만 1로 채운다(`scripts/collect.py:343-356`). 즉 소스 칸의 값은 항상 `requested ∈ {0, 1}`, `failed ∈ {0, 1}`이다. 페이지네이션으로 한 소스가 여러 요청을 보내던 유일한 경로는 제거 대상인 `collect_github`뿐이었다.

  따라서 확정하려는 델타 시나리오 "HN을 3회 요청해 2회 성공하고 1회 실패"는 **구현이 만들 수 없는 상태**다. 구체적으로:

  | | GitHub 있던 세계 | 이 변경 후 |
  |---|---|---|
  | 한 소스 안 부분 실패 | GitHub 페이지네이션에서 발생 | 발생 경로 없음 |
  | "요청 단위 기록" MUST NOT의 실질 | 소스 단위 기록으로는 표현 못 하는 상태가 존재 | 소스 단위 기록과 구별 불가 |
  | 실증 시나리오 | 재현 가능 | **재현 불가** |

  결과는 두 가지다. (1) 구현자가 이 시나리오를 검증하려 하면 존재하지 않는 다중 요청 경로를 찾게 된다 — 이 저장소 스펙이 "수행할 수단이 없는 검사를 명세하면 구현자가 없는 장치를 찾게 된다"며 명시적으로 금지한 형태다(`openspec/specs/topic-ranking/spec.md` "순위는 결정론적으로 계산한다"). (2) tasks.md에 이 시나리오에 대응하는 작업이 없으므로(7절 어디에도 없다) 실제로는 아무도 건드리지 않은 채 archive 되어, main spec이 "HN은 여러 번 요청될 수 있다"는 거짓 사실을 영구 기록으로 남긴다. 다음 사람이 `status.json` 스키마의 `requested`/`ok`/`failed` 세 칸을 보고 다중 요청 소스가 있다고 읽는다.

  이건 구현 시점에 국소적으로 못 정한다. 갈림길은 "요청 단위 기록이라는 계약을 앞으로 올 소스를 위한 불변식으로 유지하고 실증 시나리오를 실현 가능한 것으로 다시 쓸 것인가(예: 단일 요청 실패가 `requested 1 / failed 1`로 기록되는 시나리오), 아니면 요구사항 본문의 근거 문장 자체를 두 소스 세계에 맞게 다시 쓸 것인가"이고, 어느 쪽을 고르냐에 따라 `community-collection` 델타의 요구사항 본문과 시나리오 구성이 달라진다. 스펙의 요구사항 자체는 설계가 확정하는 계약이다.
- **검증 근거**:
  - `scripts/collect.py:83-92` — `_get`은 호출 한 건마다 `requested += 1`, 성공 시 `ok += 1`, 예외 시 `failed += 1` 후 re-raise
  - `scripts/collect.py:161-167` — `collect_reddit`의 `_get` 호출 1회, 반복문 없음
  - `scripts/collect.py:172-215` — `collect_hn`의 `_get` 호출 1회, `hitsPerPage=100`, 페이지네이션 루프 없음
  - `scripts/collect.py:343-356` — `main()` except 분기는 `requested == 0`일 때만 `requested = 1, failed = 1`
  - `openspec/changes/remove-github-source/specs/community-collection/spec.md:94-97` — 델타의 "부분 실패 기록" **WHEN** = "Hacker News 검색을 3회 요청해 2회 성공하고 1회 실패한다"
  - `openspec/specs/community-collection/spec.md:132-142` — main spec의 같은 요구사항 본문·근거·GitHub 3회 요청 시나리오
  - `design.md` Migration Plan 1 — "영영 성립하지 않는 전제" 기준을 세우고 `daily-automation`·`brief-publication` 두 곳에만 적용
  - `tasks.md` 7절 전체 — 이 시나리오에 대응하는 작업 없음

## 기각한 후보

검토했으나 반증된 의심들이다.

- **MODIFIED 요구사항이 main spec의 기존 시나리오를 소리 없이 지운다.** OpenSpec의 MODIFIED는 요구사항 블록 전체를 대체하므로 델타에 빠진 시나리오는 삭제된다. 7개 MODIFIED 요구사항을 main spec과 전수 대조한 결과 누락은 없었다 — `Reddit 글 수집`(main 5개 → 델타 7개), `공통 항목 스키마 정규화`(2 → 2), `수집 결과 기록`(2 → 3), `주제 묶기`(3 → 3), `소스 내 등수 산출`(5 → 5), `주제 점수 계산`(5 → 5), `Reddit 상위권 슬롯 예약`(5 → 6), `발행 여부 판정`(3 → 4), `스케줄 비활성화 방지`(2 → 2), `수집 상태 배너`(5 → 5), `Discord 알림`(4 → 4). 모두 원본 시나리오를 보존하거나 소스 이름만 바꿔 유지한다.
- **`daily-automation`의 "재실행 경로"와 `topic-ranking`의 "주제 정렬 키"가 델타에서 빠졌다.** 두 요구사항 전문을 열어 확인한 결과 GitHub·"세 소스"·배수 수치에 의존하는 문장이 하나도 없다(`openspec/specs/daily-automation/spec.md:192-214`, `openspec/specs/topic-ranking/spec.md:120-184`). MODIFIED 대상이 아닌 것이 맞다.
- **등수 1·2·6 부동소수점 동점 시나리오를 두 소스로 재현할 수 없다.** 세 항목이 세 소스에서 와야 하는 것이 아니라 배수만 같으면 되고, 스펙 시나리오도 "소스 다양성 배수도 같아"로만 서술한다(`openspec/specs/topic-ranking/spec.md:120-184`). 옛 3소스 배수와 새 2소스 배수가 똑같이 2.0이고 2.0 곱셈은 float64에서 정확하므로, Reddit 2건(등수 1·2) + HN 1건(등수 6)으로 `3.3333333333333335`/`3.333333333333333` 값이 비트 단위로 그대로 재현된다. `scores_tie`의 docstring 예시(`scripts/rank.py:206-217`)도 그대로 유효하다.
- **입력이 줄어 `enrich`의 `MAX_REQUESTS = 8` 상한에 새로 걸린다.** `pick_targets`는 `ranked["top"]`의 주제마다 Reddit 글을 최대 1건만 고르고 URL 단위로 중복을 막는다(`scripts/enrich.py:32-64`). `TOP_N = 8`이므로 후보가 8을 넘을 수 없어 상한은 원래부터 결속력이 없다. Non-Goals가 값을 그대로 둔 판단이 성립한다.
- **재실행 경로에서 옛 `items.json`의 GitHub 항목이 `SOURCE_LABEL` 조회에서 죽거나 `DIVERSITY[3]`에서 KeyError를 낸다.** `publish.py:162`는 `SOURCE_LABEL.get(item.get("source"), "?")`로 기본값을 주므로 예외가 없고, 순위 계산 단계는 재실행 경로에서 건너뛰므로(`.github/workflows/brief.yml`의 `if: inputs.from_run_id == ''`) `score_topics`가 옛 items를 보는 경로가 없다. 정상 실행의 `items.json`에는 소스가 둘뿐이라 `DIVERSITY[len(sources)]`의 키는 1 또는 2뿐이다. 옛 산출물을 그대로 재사용하는 것은 "재실행 경로" 요구사항이 규정한 의도된 동작이고, D4는 그중 발행 **판정**이 뒤집히는 경우만 막겠다고 Goals에서 범위를 명시했다.

판정: 조건부(치명·높음 1건 선해결) — `community-collection` 델타의 "수집 결과 기록"에서, 두 소스 모두 실행당 요청이 1회뿐이라 재현 불가능해진 "부분 실패 기록" 시나리오와 그것이 떠받치던 "요청 단위 기록" 근거 문장을 어떻게 처리할지 설계가 정해야 한다.
