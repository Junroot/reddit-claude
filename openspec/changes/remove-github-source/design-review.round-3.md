# design.md 적대적 리뷰

검증 통과 지적 1건.

### [높음] 이어받은 소스 칸을 기본값으로 정규화하면 배너·알림이 수집 성공/실패를 거꾸로 말한다

- **위치**: `design.md` D6의 "**재실행 경로.**" 문단 / `tasks.md` 1.4 / `specs/community-collection/spec.md:90, 118-122`
- **설계 주장**: "`load_status`의 `setdefault`는 소스 이름 수준까지만 적용되므로 이어받은 `reddit` 칸은 옛 필드(`requested`/`ok`/`failed`)를 그대로 지닌 채 새 성공 여부 필드가 빠진 상태로 배너와 알림에 들어간다. … `load_status`가 기본 스키마에 없는 필드를 버리고 빠진 필드를 기본값으로 채우게 한다. 이러면 `blank_status`가 스키마의 단일 출처라는 성질이 필드 수준에서도 성립한다." 스펙 델타는 이를 MUST로 못 박는다 — "스키마에 없는 필드는 버리고 빠진 필드는 기본값으로 채운다".
- **무엇이 깨지나**: 옛 소스 칸에서 **수집 성공/실패의 진실을 담고 있는 유일한 필드가 `ok`/`failed`** 인데, 설계는 그 둘을 "스키마에 없는 필드"로 버리라고 정하고, 그 자리를 채울 성공 여부 필드는 옛 기록에 없으므로 **항상 기본값**이 된다. 즉 정규화가 정보를 보존하는 것이 아니라 **정확한 값을 상수로 덮는다.** `tasks.md` 1.6이 `requested`/`ok`/`failed` 이름 자체를 없애도록 지시하므로, 새 성공 여부 필드가 옛 값을 우연히 물려받는 경로도 없다.

  구체 시나리오 (설계가 스스로 "배포 후 14일 동안 실재하는 경로"라고 선언한 그 경로다):
  1. 배포 전 실행 A는 정상이었다 — `sources.reddit = {requested:1, ok:1, failed:0, items:25, filtered:0}`, `sources.hn = {…, ok:1, items:19}`.
  2. 배포 후 운영자가 `from_run_id = A`로 재실행한다. 워크플로는 수집·묶기·순위·보강 단계를 건너뛰고 A의 `work` 디렉터리를 그대로 내려받아 요약과 페이지 조립만 수행한다(`.github/workflows/brief.yml:69-87, 132-151`).
  3. `publish.main()`이 `common.load_status`로 A의 `status.json`을 읽는다(`scripts/publish.py:297-302`). 새 규칙에 따라 `requested`/`ok`/`failed`가 버려지고 성공 여부 필드가 기본값으로 채워진다. `blank_status`의 나머지 칸이 모두 0/거짓으로 시작하므로 이 기본값은 사실상 "실패"다.
  4. 결과: `items`는 25/19로 살아 있어 `any_source_succeeded`(`scripts/common.py:176-186`)는 참이고 브리프는 정상 발행되는데, 같은 `status`를 읽는 `build_banner`는 "**Reddit 수집 실패**", "**Hacker News 수집 실패**"를 페이지에 찍고 `notify.source_lines`도 같은 문구를 Discord로 보낸다. 25건짜리 브리프를 실은 페이지가 "두 소스 모두 수집 실패"라고 자기 자신을 부정한다.

  기본값을 반대로("성공") 잡아도 대칭적으로 깨진다 — 실제로 HN이 실패했던 날의 실행을 이어받으면 "Hacker News 정상 — 0건"이 된다. 어느 기본값도 두 경우를 동시에 맞히지 못하므로 구현자가 국소적으로 고를 수 있는 사안이 아니고, 스펙이 "기본값으로 채운다"를 MUST로 고정했으므로 옛 `ok`/`failed`에서 성공 여부를 유도하는 선택지도 스펙 위반이 된다. `items > 0`으로 유도하는 것도 답이 아니다 — "성공했으나 0건"(HN 24시간 무결과, `openspec/specs/community-collection/spec.md:52-57`)이 성공 여부 필드가 존재하는 이유이기 때문이다.

  이 경로는 변경 전에는 옳게 표시됐다(옛 코드가 옛 필드를 읽었다). 즉 설계가 "해결했다"고 선언한 마이그레이션 처리가 바로 그 경로에 없던 오표시를 새로 만든다. 관측 가능성을 잃지 않는다는 Goal과, "문제가 있을 때만 표시하면 독자가 그 자리를 보지 않게 된다"는 배너 요구사항의 취지(`openspec/specs/brief-publication/spec.md:153-158`)가 함께 무너진다 — 상시 표시되는 자리가 거짓을 말하면 배너 자체를 신뢰할 수 없다.
- **검증 근거**:
  - `scripts/common.py:139-159` — `load_status`는 `blank_status`를 `base`로 삼아 `setdefault`만 하며, 소스 이름 수준까지만 순회한다(설계 주장대로다).
  - `scripts/common.py:104-115` — 옛 소스 칸은 `{requested, ok, failed, items, filtered}`이고, 성공/실패를 표현하는 필드는 `ok`/`failed`뿐이다.
  - `scripts/publish.py:196-210` — `build_banner`는 `requested`/`failed`/`items` 세 값으로 "정상 / 부분 실패 / 수집 실패"를 가른다. D6 이후에는 성공 여부 필드와 `items`로 "정상 / 수집 실패"를 가르게 된다.
  - `scripts/notify.py:25-38` — `source_lines`도 같은 필드를 읽어 네 갈래를 만든다.
  - `scripts/common.py:176-186` — `any_source_succeeded`는 `items > 0`만 보므로 발행 판정은 성공 여부 필드와 무관하게 통과한다(발행은 되고 표기만 거짓이 되는 조합의 근거).
  - `.github/workflows/brief.yml:69-87, 132-151` — 재실행 경로는 이전 실행의 work를 통째로 내려받고, 요약 입력·요약·페이지 조립은 조건 없이 실행된다. `.github/workflows/brief.yml:190-197` — 아티팩트 보관 14일.
  - `openspec/changes/remove-github-source/specs/community-collection/spec.md:90, 118-122` — "빠진 필드는 기본값으로 채운다"가 MUST와 시나리오 **THEN** 양쪽에 박혀 있다.
  - `openspec/changes/remove-github-source/tasks.md:10` (1.6) — `requested`/`ok`/`failed`를 없애고 성공 여부 하나만 남기도록 지시한다.

## 기각한 후보

- **재실행 경로에서 `items.json`에 남은 GitHub 항목이 크래시를 낸다** — 반증. 재실행 시 순위 계산 단계가 건너뛰어져 `rank.DIVERSITY[len(sources)]`(`scripts/rank.py:189-203`)에 3이 들어갈 경로가 없고, 표시 계층은 소스 이름으로 dict를 대괄호 인덱싱하지 않는다(`scripts/publish.py:162`의 `SOURCE_LABEL.get(..., "?")`, `scripts/llm_input.py:79/116/129`는 값을 그대로 통과). 남는 것은 라벨이 `?`로 찍히는 표시 차이뿐이고, 이는 "그 실행의 데이터를 그대로 재사용한다"는 재실행 경로의 정의상 그날 수집분이 나오는 것이라 판정을 막지 않는다.
- **HN의 24시간 창 제외 건수가 `filtered`에 안 남아 "소스마다 제외한 항목 수를 남긴다(MUST)"를 위반한다** — 반증. HN의 24시간 창은 Algolia 요청의 `numericFilters=created_at_i>=cutoff`로 서버 쪽에서 적용되고, 응답 순회에는 시간 기준으로 항목을 버리는 코드가 없다(`scripts/collect.py:186-215`). HN은 로컬에서 제외하는 항목이 없으므로 `filtered = 0`이 거짓이 아니다.
- **세 소스로 짜인 정렬 키 사다리 테스트를 두 소스로 재현할 수 없다** — 반증. `tests/test_rank.py:282-315`의 기대값은 등수 합에 배수를 곱한 값이고, D1이 두 소스 배수를 2.0으로 두므로 옛 `DIVERSITY[3] = 2.0`과 곱수가 같다. Reddit 등수는 피드 순서로 1·6을 동시에 만들 수 있어 `(1, 2, 6)` 조합도 Reddit 2건 + HN 1건으로 그대로 재현된다. 부동소수점 기대 문자열까지 보존된다.
- **델타가 main spec 요구사항의 시나리오를 누락했다** — 반증. 전수 대조 결과 community-collection "Reddit 글 수집"(main 5개 → 델타 7개), "수집 결과 기록"(요청 단위 시나리오를 D6 결정에 따라 의도적으로 대체), daily-automation "발행 여부 판정"(3개 → 4개), brief-publication 두 요구사항 모두 기존 시나리오를 잃지 않았다. 배너·Discord 요구사항에는 애초에 요청 단위 부분 실패 시나리오가 없어 D6로 사라지는 표시 갈래와 충돌하지 않는다.

판정: 조건부(치명·높음 1건 선해결) — 재실행 경로에서 이어받은 소스 칸을 기본값으로 정규화할 때 수집 성공/실패를 어떻게 정할지(옛 `ok`/`failed`에서 유도할지, 이어받은 기록임을 표기할지, 그 오표시를 명시적으로 수용할지)를 D6에서 결정해야 한다.
