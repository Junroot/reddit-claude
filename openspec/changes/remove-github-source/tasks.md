## 1. 소스 목록의 단일 출처부터 바꾼다

소스 목록이 `common.blank_status` 한 곳에서 나오므로 여기가 기준점이다. 여기를 먼저 바꾸면 나머지 단계에서 남은 참조가 테스트 실패로 드러난다.

- [x] 1.1 `scripts/common.py`의 `blank_status`에서 `sources.github` 칸을 제거한다
- [x] 1.2 `blank_status`의 `filtered` 주석을 다시 쓴다. 지금은 "시간 창 안에 있으나 이슈가 아닌 GitHub Pull Request가 여기 잡힌다"고 적혀 있는데, Reddit의 48시간 초과 제외 건수를 세는 칸으로 의미가 바뀐다 (design.md D2)
- [x] 1.3 `load_status`가 기본 스키마에 없는 소스 칸을 제거하도록 한다. 재실행 경로가 이전 실행의 `status.json`을 이어받으므로, `sources.github`가 살아남으면 `any_source_succeeded`가 그 값을 세어 발행 판정이 잘못 통과한다 (design.md D4)
- [x] 1.4 `load_status`의 정리를 소스 칸 **안의 필드**까지 넓힌다. 지금 `setdefault`는 소스 이름 수준까지만 적용돼, 이어받은 `reddit` 칸이 옛 요청 카운터 필드를 지닌 채 새 성공 여부 필드 없이 배너·알림에 들어간다. 스키마에 없는 필드는 버리고 빠진 필드는 기본값으로 채운다 (design.md D6)
- [x] 1.5 `any_source_succeeded`의 docstring에서 "세 소스가 전부 실패한 날에만"을 두 소스 기준으로 고친다
- [x] 1.6 `blank_status`의 각 소스 칸에서 요청 단위 카운터(`requested`/`ok`/`failed`)를 없애고 수집 성공 여부 하나와 `items`·`filtered`만 남긴다. `enrich` 절의 `requested`/`ok`/`failed`는 그대로 둔다 (design.md D6)
- [x] 1.7 `blank_status` 위 주석의 "실패는 소스 단위가 아니라 요청 단위로 센다" 문단을 다시 쓴다. 두 소스가 실행당 1회만 요청하므로 소스 칸은 소스 단위로 세고, 요청 단위 기록은 여러 요청을 보내는 `enrich` 절에만 남는다는 판단이 코드에 남아야 한다 (design.md D6)

## 2. 수집 단계

- [x] 2.1 `scripts/collect.py`에서 `collect_github` 함수를 제거한다
- [x] 2.2 `GITHUB_REPO`, `GITHUB_MAX_AGE_HOURS`, `GITHUB_MAX_PAGES`, `GITHUB_MIN_ENGAGEMENT` 상수를 제거한다
- [x] 2.3 `SOURCES` 튜플에서 `("github", collect_github)` 항목을 제거한다
- [x] 2.4 모듈 docstring의 공통 항목 스키마 예시에서 `"github"`을 빼고, "세 소스"를 두 소스로 고친다
- [x] 2.5 시간 창 주석에서 GitHub 48시간 설명 블록을 제거한다. Reddit 48시간의 근거는 그대로 둔다 — GitHub과 폭을 맞춘다는 문장만 빠진다
- [x] 2.6 `filter_and_rank_reddit`가 돌려주는 제외 건수를 `entry["filtered"]`에 기록하도록 `collect_reddit`을 고친다 (design.md D2)
- [x] 2.7 `import os`가 GitHub 토큰 조회에만 쓰이는지 확인하고, 그렇다면 함께 정리한다
- [x] 2.8 `_get`이 소스 칸의 요청 카운터를 올리던 것을 없앤다. 소스 칸에는 수집 함수가 끝난 뒤 성공/실패만 기록한다 (design.md D6)
- [x] 2.9 `main()`의 except 분기를 새 스키마에 맞춘다. `requested == 0`인지 보고 채우던 조건이 사라지고, 요청을 보내기 전에 죽든 요청이 실패하든 그 소스는 수집 실패로 기록된다 (design.md D6)

## 3. 순위 계산

- [x] 3.1 `scripts/rank.py`의 `SIGNALS`에서 `"github"` 항목을 제거한다
- [x] 3.2 `DIVERSITY`를 `{1: 1.0, 2: 2.0}`으로 바꾼다. 표를 `{1: 1.0, 2: 1.5}`로 자르지 않는다 — 배수는 소스의 절대 개수가 아니라 다양성의 정도를 나타내므로 최대값 2.0이 "가능한 모든 소스에서 얘기됐다"는 자리를 지켜야 한다 (design.md D1)
- [x] 3.3 `DIVERSITY` 위에 배수 의미를 설명하는 주석을 단다. 소스가 줄어도 척도의 끝점을 낮추지 않는다는 판단이 코드에 남아야 다음 사람이 무심코 1.5로 되돌리지 않는다
- [x] 3.4 `RESERVED_REDDIT_RANKS`의 주석을 다시 쓴다. 근거가 "GitHub 이슈 무더기에 밀리는 것을 막는다"에서 "HN에서 큰 스토리가 여러 건 터진 날 Reddit 최상위 글이 밀리는 것을 막는다"로 바뀐다. 값 3은 유지한다 (design.md D3)
- [x] 3.5 `build_item_ranks`의 docstring에서 "Hacker News와 GitHub"을 Hacker News만 남기도록 고친다

## 4. 표시 계층

- [x] 4.1 `scripts/publish.py`의 `SOURCE_LABEL`에서 `"github"`을 제거한다
- [x] 4.2 상태 배너가 순회하는 소스 튜플에서 GitHub 행을 제거한다
- [x] 4.3 `publish.py`의 "세 소스" 문구 두 곳을 고친다 — 모듈 docstring의 자리표시자 설명과, 발행하지 않는 이유 문자열
- [x] 4.4 `scripts/notify.py`의 `SOURCE_LABELS`에서 GitHub 항목을 제거한다
- [x] 4.5 `publish.build_banner`의 소스 갈래를 "정상 / 수집 실패" 둘로 줄인다. 요청 건수를 인용하던 소스 부분 실패 갈래는 만들 수 있는 상태가 없어 사라진다. 댓글 보강 부분 실패 표시는 `enrich` 절을 읽으므로 그대로 둔다 (design.md D6)
- [x] 4.6 `notify.source_lines`의 네 갈래("수집을 시도하지 못함" / 정상 / 부분 실패 / 수집 실패)를 "정상 / 수집 실패" 둘로 줄인다 (design.md D6)
- [x] 4.7 `scripts/llm_input.py` 모듈 docstring에서 본문 절단 근거로 든 "GitHub 이슈 본문에는 로그와 스택 트레이스가 길게 붙는다"를 고친다. `CLUSTER_BODY_CHARS = 150`은 그대로 둔다 — 입력이 줄어도 손해가 없다

## 5. 프롬프트

- [x] 5.1 `prompts/cluster.md`의 소스 목록에서 GitHub Issues를 제거한다
- [x] 5.2 교차 소스 묶기 예시를 Reddit × Hacker News로 새로 쓴다. 소스만 갈아 끼우지 않는다 — GitHub 이슈 제목은 결함 신고문 형태지만 HN 스토리는 릴리스·기사 링크 형태라 그대로 옮기면 부자연스럽다 (design.md D5)
- [x] 5.3 `prompts/summarize.md`의 예시 문장 "Reddit과 GitHub 양쪽에서"를 고친다

## 6. 워크플로와 문서

- [x] 6.1 `.github/workflows/brief.yml`의 수집 단계에서 `GITHUB_TOKEN` 환경 변수를 제거한다. 발행 단계의 토큰은 그대로 둔다
- [x] 6.2 워크플로 상단 파이프라인 주석의 "세 소스 수집"을 고친다
- [x] 6.3 `README.md`의 소스 표에서 GitHub Issues 행을 제거한다
- [x] 6.4 README 도입부의 "세 곳에 흩어져 있다"와 파이프라인 표의 "세 소스 수집"을 고친다
- [x] 6.5 README에서 GitHub이 `created_at`을 쓰는 이유를 설명하는 문단(D14 참조)을 제거한다
- [x] 6.6 README 시크릿 표에서 `GITHUB_TOKEN`의 용도를 "gh-pages 발행"만 남기도록 고친다. 시크릿 자체는 계속 필요하다

## 7. 테스트

가장 큰 덩이다. 픽스처를 지우는 것이 아니라 **같은 등수 패턴을 두 소스로 재현**하는 것이 판정 기준이다 (design.md의 위험 항목).

- [x] 7.1 `tests/test_collect.py`에서 GitHub 수집 테스트를 제거한다 (`collect_github` 호출 4곳과 이슈 응답 픽스처)
- [x] 7.2 `tests/test_collect.py`에 Reddit 48시간 초과 제외 건수가 `filtered`에 기록되는지 확인하는 테스트를 추가한다 (2.6에 대응)
- [x] 7.3 `tests/test_rank.py`의 `gh_item` 헬퍼를 제거하고, 이를 쓰던 픽스처를 Reddit·HN 조합으로 옮긴다. 각 테스트가 검증하던 등수 조합을 그대로 재현한다
- [x] 7.4 세 소스 주제로 검증하던 정렬 키 사다리 테스트를 두 소스로 다시 구성한다. `(1, 2, 6)` 대 `(6, 2, 1)` 같은 등수 조합이 부동소수점 합산 순서 차이를 만드는 것이 이 테스트의 요지이므로, 항목 수와 등수 값이 보존돼야 한다
- [x] 7.5 다양성 배수 기대값을 2.0 기준으로 갱신한다. 두 소스 주제의 점수가 `합 × 1.5`에서 `합 × 2.0`으로 바뀐다
- [x] 7.6 `tests/test_publish.py`의 상태 배너 픽스처(`status(reddit, hn, github)`)를 두 소스로 줄이고, 소스 칸을 새 스키마(성공 여부 + `items` + `filtered`)로 바꾼다. 요청 건수를 인용하던 소스 부분 실패 기대 문구를 검증하던 케이스는 표현 가능한 상태가 아니므로 함께 정리한다 (design.md D6)
- [x] 7.7 이어받은 `status.json`에 `sources.github`가 남아 있어도 발행 판정이 그 값을 세지 않는지 확인하는 테스트를 추가한다 (1.3에 대응)
- [x] 7.8 `tests/test_collect.py`에서 소스 칸의 `requested`/`ok`/`failed`를 검증하던 단언을 새 스키마의 성공/실패 검증으로 바꾼다. 요청 실패한 날과 요청 전에 죽은 날이 모두 수집 실패로 기록되는지 확인한다 (2.8·2.9에 대응)
- [x] 7.9 옛 스키마의 소스 칸(요청 카운터가 남아 있고 성공 여부 필드가 없는 `sources.reddit`)을 이어받아도 `load_status`가 현재 스키마로 정규화하는지 확인하는 테스트를 추가한다 (1.4에 대응)
- [x] 7.10 `python3 -m unittest discover -s tests`가 전부 통과하는지 확인한다

## 8. 확인

- [x] 8.1 `python3 scripts/collect.py --work work`를 로컬에서 돌려 `items.json`에 `"source": "github"`인 항목이 없고 `status.json`에 `github` 칸이 없는지 확인한다
- [x] 8.2 `git grep -i github -- scripts prompts tests` 결과에 남은 것이 저장소 URL·Actions 관련 참조뿐인지 확인한다
- [x] 8.3 `openspec validate remove-github-source --strict`를 통과시킨다
- [x] 8.4 `git grep -n "세 소스\|세 곳" -- openspec/specs` 결과가 비어 있는지 확인한다. `openspec/specs/community-collection/spec.md`의 Purpose 문단은 요구사항이 아니라 델타로 덮이지 않으므로, sync/archive 시점에 두 소스 기준으로 직접 고친다 (design.md Migration Plan 1)

## 9. 발행 후 관찰

- [ ] 9.1 며칠간 `ranked.json`의 주제별 소스 수 분포를 보고 다양성 배수 2.0이 실제로 몇 번 발동하는지 확인한다. 거의 걸리지 않으면 design.md D1을 다시 판단한다
- [ ] 9.2 `status.json`의 `sources.reddit.filtered`에 며칠치가 쌓이면 Reddit 48시간 상한값 자체를 다시 판단한다 (design.md D2)
- [ ] 9.3 입력이 44건 규모로 줄어든 뒤 단일 항목 주제가 상위 8을 얼마나 채우는지 본다. `cluster.auto_topics`와 구별해서 봐야 한다 — 전자는 그날 논의가 적었다는 신호이고 후자는 1차 LLM이 항목을 흘렸다는 경고다
