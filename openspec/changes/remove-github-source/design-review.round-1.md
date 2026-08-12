# design.md 적대적 리뷰 — remove-github-source

검증 통과 지적 1건. 나머지 의심은 전부 코드·문서를 열어 반증했거나 임계선 아래로 폐기했다.

### [높음] 스펙 델타가 "세 소스"를 말하는 요구사항 두 개를 빠뜨려, 이 change가 확정하는 스펙이 소스 개수에서 자기모순에 빠진다

- **위치**: `design.md:26` (Goals "GitHub Issues를 수집·순위·기록·발행 전 경로에서 제거한다"), `design.md:107` (Migration Plan 1 "스펙 델타를 적용해 요구사항을 확정한다"), `specs/daily-automation/spec.md`(델타, MODIFIED 1건), `specs/brief-publication/spec.md`(델타, MODIFIED 1건)
- **설계 주장**: 설계는 발행 판정과 표시 계층에서 GitHub이 사라지는 경로를 D4·D5와 Migration Plan 5로 다루고, 스펙 델타가 그 요구사항을 확정한다고 전제한다. `proposal.md:31-32`도 `daily-automation`은 "발행 여부 판정의 '세 소스'를 '두 소스'로 바꾼다", `brief-publication`은 "수집 상태 배너가 표시하는 소스를 둘로 줄인다"만 바꾸면 되는 것으로 범위를 잡았다.
- **무엇이 깨지나**: 두 capability의 main spec에는 발행 여부와 직접 얽힌 "세 소스" 서술이 **델타가 건드리지 않는 다른 요구사항 안에** 하나씩 더 있다. 이 change가 archive/sync되면 같은 파일 안에서 요구사항끼리 어긋난 스펙이 남는다.

  | 파일 | 요구사항 | 델타 후 남는 문장 | 델타가 새로 확정하는 문장 |
  |---|---|---|---|
  | `daily-automation/spec.md` | 스케줄 비활성화 방지 → `Scenario: 발행하지 않는 날` | "**WHEN** 세 소스가 모두 실패해 발행하지 않는다" (254행) | "두 소스가 모두 실패한 경우에만 발행하지 않는다(MUST)" (델타 5행) |
  | `brief-publication/spec.md` | Discord 알림 → `Scenario: 발행 실패 알림` | "**WHEN** 세 소스가 모두 실패해 발행하지 않는다" (218행) | "배너가 표시하는 소스는 … Reddit과 Hacker News 둘로 한정한다(MUST)" (델타 9행) |

  두 문장 모두 "발행하지 않는 날"의 **선행 조건**을 서술하므로, 소스가 둘인 세계에서는 영영 성립하지 않는 WHEN이 된다. 즉 stale prose가 아니라 도달 불가능한 시나리오 전제가 스펙에 남는다. `daily-automation`은 한 파일 안에서 "발행 여부 판정"은 두 소스로, "스케줄 비활성화 방지"는 세 소스로 같은 사건을 규정하게 된다.

  이 잔재는 구현 단계에서 걸러지지 않는다. `tasks.md:67`의 확인 명령이 `git grep -i github -- scripts prompts tests`로 **`openspec/` 밖만** 훑고, `tasks.md:68`의 `openspec validate --strict`는 델타 헤딩이 main spec 헤딩과 일치하는지만 보므로(네 델타의 헤딩은 전부 일치함) 통과한다. 구현자가 apply 단계에서 스스로 고칠 수도 없다 — 고치려면 델타에 MODIFIED 요구사항을 새로 **저술**해야 하고, 그건 스펙 범위 결정이라 설계 시점의 몫이다.

  같은 성격의 잔재가 `community-collection/spec.md:3` Purpose "세 소스에서 하루치 논의를 수집해 …"에도 있다. 이쪽은 요구사항이 아니라 Purpose 문단이라 델타 문법으로 표현할 수 없으므로, 설계가 "sync 시 Purpose도 손본다"를 명시하지 않으면 그대로 남는다.

- **검증 근거**:
  - `openspec/specs/daily-automation/spec.md:241-256` — "스케줄 비활성화 방지" 요구사항, `#### Scenario: 발행하지 않는 날`의 254행이 "**WHEN** 세 소스가 모두 실패해 발행하지 않는다". 이 change의 `specs/daily-automation/spec.md` 델타는 MODIFIED가 "발행 여부 판정" **하나뿐**이다.
  - `openspec/specs/brief-publication/spec.md:200-228` — "Discord 알림" 요구사항, `#### Scenario: 발행 실패 알림`의 218행이 "**WHEN** 세 소스가 모두 실패해 발행하지 않는다". 이 change의 `specs/brief-publication/spec.md` 델타는 MODIFIED가 "수집 상태 배너" **하나뿐**이다.
  - `openspec/specs/community-collection/spec.md:3` — Purpose "세 소스에서 하루치 논의를 수집해 공통 스키마로 정규화한다."
  - `openspec/specs/` 전체 `grep -rn -i "github|세 소스|세 곳"` — 위 세 곳을 제외한 나머지 언급은 전부 네 델타가 MODIFIED/REMOVED로 덮는 요구사항 안에 있다(`topic-ranking` 15·40·104행은 각각 "주제 묶기"·"소스 내 등수 산출"·"주제 점수 계산" 안, `community-collection` 64·118-145행은 "GitHub Issues 수집"·"공통 항목 스키마 정규화"·"수집 결과 기록" 안). 즉 누락은 정확히 이 세 곳이다.
  - `tasks.md:67-68` — 확인 단계의 grep 범위가 `scripts prompts tests`이고, 스펙 잔재를 잡는 작업 항목이 없다.

## 기각한 후보

아래는 의심했으나 코드·문서로 **반증된** 것들이다.

- **`DIVERSITY`를 `{1: 1.0, 2: 2.0}`으로 바꾸면 `score_topics`가 KeyError로 죽는 경로가 남는가** — `scripts/rank.py:201`은 `DIVERSITY[len(sources)]`를 직접 조회하므로 소스가 3개인 주제가 들어오면 죽는다. 그러나 `source_of`는 `items.json`에서만 만들어지고(`rank.py:310`), `items.json`은 `collect.py:main()`이 매 실행 통째로 덮어쓴다(`collect.py:358-361`). GitHub 항목이 남은 옛 `items.json`이 존재할 수 있는 유일한 경로는 워크플로의 `from_run_id` 재실행인데, 그 경로에서는 순위 계산 단계가 `if: inputs.from_run_id == ''`로 건너뛰어진다(`.github/workflows/brief.yml:122-125`). 도달 불가.
- **`SIGNALS`에서 `github`을 빼면 `ranks[item_id]` 조회가 실패하는가** — 위와 같은 이유로 GitHub 항목이 `rank.run()`에 들어오는 경로가 없다.
- **`FloatTieTest`의 `(1, 2, 6)` 대 `(6, 2, 1)` 사다리를 두 소스로 재현할 수 없는가** — `tests/test_rank.py:282-315`의 기대값 `3.3333333333333335` / `3.333333333333333`은 이미 배수 2.0이 곱해진 값이다(합 1.666… × 2.0). 새 표에서도 두 소스 주제의 배수가 2.0이고 2.0은 이진수에서 정확하므로 합산 순서가 만든 마지막 비트 차이가 그대로 보존된다. `hn_`·`rd_` 접두사만으로도 "ID 사전순과 등수 순서를 어긋나게 두는" 배치가 가능하다(예: `hn_a`(1)·`hn_b`(2)·`rd_lo`(6) 대 `hn_c`(6)·`hn_d`(2)·`rd_hi`(1)). 재현 가능.
- **D2가 `filtered`를 채우는 곳으로 "GitHub 참여도 필터와 Pull Request 제외"를 든 것이 맞는가** — 틀렸다. `collect.py:319`는 `entry["filtered"] = seen_unengaged` 한 줄뿐이고 `seen_pull_requests`는 320-321행 `print`에만 쓰인다(현재 `common.py:107-109`의 주석이 이미 틀려 있고 설계가 그 주석을 사실로 옮겨 적었다). 다만 PR 제외가 세어졌든 아니든 "GitHub이 빠지면 `filtered`가 전 소스에서 항상 0이 된다"는 D2의 전제와 결론은 그대로 성립하므로, 어떤 결정도 뒤집지 못한다.
- **D4의 "발행 판정이 잘못 통과한다"가 재실행 경로에서 실제로 해로운가** — 그 상황(Reddit·HN 실패 + 옛 GitHub 항목 수 잔존)에 도달하려면 `from_run_id` 재실행이어야 하는데, 그 경로에서는 `items.json`·`ranked.json`도 함께 이어받으므로 요약 대상 GitHub 항목이 실제로 존재한다. 즉 빈 페이지로 어제치를 덮는 상황은 아니다. D4 서술의 "어제 페이지를 오늘 브리프로 덮어쓰는"도 방향이 뒤집힌 문장이다(`publish.py:179-181`과 `specs/brief-publication` 원문은 *발행을 거를 때* 어제 페이지가 남는 것을 문제로 본다). 그러나 델타 `daily-automation`이 "판정은 현재 수집 대상 소스의 항목 수만 근거로 해야 한다(MUST)"를 명시적으로 결정했고, 그 결정 자체는 `common.load_status`(`common.py:139-159`)가 미지 칸을 통과시킨다는 사실 위에서 정합적이다. 근거 문장의 흠결이 결정을 무너뜨리지 못하므로 지적으로 세우지 않는다.
- **재실행 경로에서 옛 `items.json`의 GitHub 항목이 페이지에 "?"로 찍히는가** — 찍힌다(`publish.py:162`의 `SOURCE_LABEL.get(item.get("source"), "?")`). 그러나 이 fallback은 이미 코드에 설계된 미지 소스 처리이고, 배포 직후 pre-change 실행을 수동 재실행하는 14일 아티팩트 창 안에서만 나타나며 하루 뒤 자연 소멸한다. 진입을 막을 결함이 아니다.
- **D4의 "소스 목록이 단일 출처가 된다"가 사실인가** — 소스 목록은 `common.blank_status`(`common.py:110-114`) 외에 `collect.SOURCES`(326-330), `rank.SIGNALS`(45-48), `publish.SOURCE_LABEL`(49)·`build_banner` 튜플(197), `notify.SOURCE_LABELS`(23)에 각각 따로 있고 `tasks.md`도 이들을 개별 작업으로 나열한다. 다만 D4가 말하는 "같은 문제"는 `load_status`가 옛 기록의 미지 소스 칸을 통과시키는 문제로 좁게 읽히고, 그 문제는 `blank_status` 대조로 실제로 재발하지 않는다. 과장된 표현일 뿐 결정은 성립한다.
- **`MAX_REQUESTS = 8`이 실재하는 상수인가** — 실재한다(`scripts/enrich.py:27`). Non-Goals의 상수 인용 세 개(`TOP_N`=`rank.py:31`, `RESERVED_REDDIT_RANKS`=`rank.py:35`, `MAX_REQUESTS`=`enrich.py:27`)가 모두 현재 코드와 일치한다.
- **change 분할이 필요한가** — 필요 없다. 수집·순위·기록·발행·프롬프트·문서·테스트로 파일이 넓게 퍼져 있으나 의도는 "소스 하나를 뺀다" 하나이고, D1(배수표)·D2(`filtered` 재정의)·D4(미지 소스 칸 제거)는 그 제거가 강제하는 종속 결정이라 따로 떼면 중간 상태에서 스펙이 깨진다. 단일 응집 의도로 본다.

판정: 조건부(치명·높음 1건 선해결) — `daily-automation`의 "스케줄 비활성화 방지"와 `brief-publication`의 "Discord 알림" 시나리오에 남는 "세 소스" 전제를 델타 범위에 넣고(그리고 `community-collection` Purpose의 "세 소스"를 sync 시 어떻게 처리할지 정하고) 다시 진입 판정을 받는다.
