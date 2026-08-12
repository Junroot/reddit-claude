# design.md 적대적 리뷰

검증 통과한 `[치명]`·`[높음]` 지적 없음.

D1·D2·D3·D4·D5·D6의 코드 주장을 실제 파일로 전수 확인했고, 델타 스펙과 `tasks.md`를 main spec과 대조했다. 진입을 막는 결함을 세우지 못했다. 아래는 실제로 의심하고 파고들었으나 코드·문서로 **반증된** 후보들이다.

## 기각한 후보

### D6의 "소스 부분 실패 갈래는 만들 수 있는 상태가 없다"가 거짓인가

`publish.build_banner`의 두 번째 갈래 조건은 요청 건수가 여럿일 것을 요구하지 않는다 — `not(failed == 0 and requested > 0) and got > 0`이면 걸린다(`scripts/publish.py:201-206`). 그러므로 단일 요청 소스에서도 "요청은 실패했는데 항목은 있다"가 성립하면 D6의 단정이 깨진다고 의심했다.

반증됐다. `_get`이 실패하면 그대로 re-raise 해 수집 함수를 끝내는데(`scripts/collect.py:83-92`), `collect_reddit`은 파싱을 마친 뒤 `out.extend(kept)`를 한 번만 호출하고(`scripts/collect.py:161-167`) `collect_hn`은 `_get`이 첫 문장이라(`scripts/collect.py:187`) 두 경우 모두 `failed > 0`이면 `got == 0`이다. `requested == 0 and got > 0`도 두 수집 함수가 반드시 `_get`을 부르므로 성립하지 않는다. 즉 현재 코드에서 그 갈래는 실제로 도달 불가능하며, D6의 단정은 참이다.

파생 의심 — 새 스키마에서 "수집 실패로 기록됐는데 `items > 0`"이 `collect_hn`의 순회 도중 예외로 새로 생길 수 있는가도 봤다. `common.parse_iso`가 해석 실패에 예외 대신 `None`을 돌려주므로(`scripts/common.py:36-50`) 그 경로의 유일한 트리거는 Algolia가 `hits`에 dict가 아닌 원소를 섞어 보내는 경우뿐이고, 그때의 표시("수집 실패" + 일부 항목 발행)는 현재 코드의 표시("정상 — N건")보다 덜 틀리다. 진입을 막는 결함이 아니다.

### D4의 정규화가 재실행 경로에서 실제로 불리지 않는가

`collect.main()`은 `blank_status`로 새 기록을 만들고 `save_status`만 부른다 — `load_status`를 호출하지 않는다(`scripts/collect.py:333-363`). D4의 수정을 `load_status`에 넣으면 정작 발행 판정 시점에 적용되지 않는 것 아닌가를 의심했다.

반증됐다. 재실행 경로에서는 수집 단계 자체가 건너뛰어지고(`.github/workflows/brief.yml:69-87`), 항상 실행되는 발행 단계의 `publish.main()`이 `common.load_status`로 읽은 뒤 그 결과로 `any_source_succeeded`를 판정한다(`scripts/publish.py:269, 297-302`). `notify.main()`도 `load_status`를 쓴다(`scripts/notify.py:139`). `load_status` 호출처는 이 둘과 `common.record_section` 셋뿐이므로, 정규화 지점으로 `load_status`를 고른 것은 정확하다.

### 델타가 main spec의 시나리오를 조용히 떨어뜨렸는가

MODIFIED는 요구사항을 통째로 대체하므로 시나리오 하나가 빠지면 그대로 삭제된다. 네 델타 파일의 헤딩을 main과 전수 대조했다.

반증됐다. `topic-ranking` 델타의 네 요구사항, `community-collection` 델타의 세 MODIFIED 요구사항, `daily-automation`·`brief-publication` 델타의 각 두 요구사항 모두 main의 기존 시나리오를 하나도 빠뜨리지 않고 포함하며, 추가된 것만 있다("교차 주제가 단독 최상위 주제를 앞선다", "교차 주제에 밀린 Reddit 최상위 글 구제", Reddit `filtered` 기록 2개, 이어받은 기록 관련 2개, 제거된 소스 판정 1개).

### 델타가 덮지 못하는 GitHub 참조가 main spec에 남는가

`openspec/specs/` 전체를 `github|세 소스|세 곳|1.5`로 전수 grep 했다.

반증됐다. 잔여 언급은 (1) `community-collection`의 Purpose 문단 — design.md Migration Plan 1과 `tasks.md` 8.4가 sync/archive 시점 수작업으로 명시적으로 처리하고 있고, (2) `brief-publication`·`daily-automation`의 GitHub Actions·GitHub Pages 인프라 언급 — 이번 변경과 무관하다. 나머지는 전부 REMOVED/MODIFIED 델타 안에 들어 있다.

### 부동소수점 동점 테스트를 두 소스로 재현할 수 없는가

`tests/test_rank.py:282-315`의 `FloatTieTest`는 세 소스 주제 둘로 `repr` 마지막 비트 차이를 검증하고, 기대값에 `DIVERSITY[3] = 2.0`이 곱해져 있다. 소스가 둘이 되면 이 케이스를 재현할 수 없어 `tasks.md` 7.4가 성립하지 않는다고 의심했다.

반증됐다. D1이 `DIVERSITY[2]`를 2.0으로 두므로 배수가 옛 `DIVERSITY[3]`과 같고, 합산 순서는 소스 수가 아니라 항목 ID 사전순으로 정해진다(`scripts/rank.py:189-203`, `topic-ranking`의 "합산 순서가 고정됨"). `hn_` 두 건과 `rd_` 한 건으로 등수 1·2·6과 ID 정렬 순서를 그대로 재현하면 기대 `repr` 문자열이 바뀌지 않는다. 등수 2의 중복은 HN 동점 처리가 이미 허용한다.

### change를 쪼개야 하는가

D6의 `status.json` 소스 칸 스키마 변경은 GitHub 제거의 부수 효과가 아니라 별개의 기록 스키마 변경이라 분할 후보로 봤다.

반증됐다. D6의 근거는 "GitHub이 빠지면 다중 요청 경로가 사라진다"는 사실 자체이므로 GitHub 제거와 분리하면 전제가 성립하지 않는다. 미루면 참이 아닌 계약("요청 단위로 기록한다")이 main spec에 archive 된다는 design.md의 논거도 성립한다. 단일 응집 의도다.

판정: 진입 가능 — D1~D6의 코드 주장이 실제 코드와 일치하고, 델타 스펙이 main spec 요구사항·시나리오를 빠짐없이 덮으며, 재실행 경로의 부작용(제거된 소스 칸, 옛 스키마 필드, 이어받은 기록의 오표시)이 각각 결정·수용된 리스크·기각한 대안으로 명시적으로 다뤄져 있다.
