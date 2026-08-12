## Why

GitHub Issues에서 오는 내용이 대부분 버그 리포트다. 이 브리프가 담으려는 것은 "그날 커뮤니티가 무엇에 반응했는가"인데, 이슈는 재현 절차와 로그와 환경 정보로 이루어진 결함 신고문이라 반응이 아니라 증상이다. 참여도 조건(댓글 + 리액션 ≥ 1)을 통과한 이슈조차 대체로 "나도 같은 증상"의 확인 댓글이 한둘 붙은 것이라, 논의라기보다 중복 신고에 가깝다.

규모까지 감안하면 손실보다 이득이 크다. 첫 시운전 실측에서 1차 LLM 입력 113건 중 GitHub이 69건으로 61%를 차지했다. 즉 입력의 과반을 버그 신고가 점유한 채, 그 신고들이 주제 묶기와 순위 계산을 통과해 브리프 상위 8칸을 두고 Reddit·Hacker News의 실제 논의와 경쟁해 왔다.

## What Changes

- **BREAKING** GitHub Issues를 수집 소스에서 완전히 제거한다. `anthropics/claude-code` 저장소 조회, 생성 시각 48시간 창, 참여도 조건, Pull Request 제외, 페이지네이션이 함께 사라진다. 소스는 Reddit과 Hacker News 둘이 된다.
- **BREAKING** `status.json`의 `sources.github` 칸을 제거한다. 발행 여부 판정과 페이지 배너와 Discord 알림이 모두 이 파일을 읽으므로 셋이 함께 바뀐다.
- **BREAKING** `status.json`의 소스 칸을 요청 단위 카운터(`requested`/`ok`/`failed`)에서 소스 단위 성공/실패로 줄인다. 남는 두 소스는 실행당 요청이 각 1회뿐이라 "한 소스 안에서 일부 요청만 실패"가 존재하지 않고, 요청 단위 기록을 유지하면 없는 다중 요청 경로가 있는 것처럼 읽힌다. 실제로 여러 요청을 보내는 `enrich` 절의 요청 단위 기록은 그대로 둔다.
- 소스 다양성 배수의 최대값을 유지한다. 소스가 셋일 때 최대 다양성에 2.0을 주던 것을, 소스가 둘이 된 뒤에도 최대 다양성(두 소스 모두 포함)에 2.0을 준다. 배수표는 `{1: 1.0, 2: 2.0}`이 된다.
- `status.json`의 `filtered` 필드를 Reddit 48시간 초과 제외 건수를 기록하는 용도로 되살린다. 지금 이 필드를 채우는 곳은 GitHub의 참여도 필터와 Pull Request 제외뿐이라, GitHub이 빠지면 전 소스에서 항상 0이 된다.
- 1차 LLM 프롬프트의 소스 목록과 교차 소스 묶기 예시를 Reddit × Hacker News로 바꾼다. 지금 예시가 Reddit 글과 GitHub 이슈의 짝이라 그대로 두면 존재하지 않는 소스를 가르치게 된다.

### 하지 않는 것

- Hacker News는 유지한다. 실측에서 Reddit + HN이 44건이었고 Reddit RSS가 약 25건이므로 HN은 약 19건 규모다. 교차 주제가 실제로 생기는 양이라 다양성 배수가 계속 작동한다.
- GitHub Discussions로 갈아 끼우지 않는다. 이번 변경은 제거로 한정한다.
- 상위 8 상한(`TOP_N`)과 Reddit 슬롯 예약 칸 수(3칸)는 바꾸지 않는다. 근거만 다시 쓴다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- `community-collection`: GitHub Issues 수집 요구사항을 제거한다. 정규화·기록 요구사항의 소스 수를 셋에서 둘로 줄이고, Reddit 수집에 48시간 초과 제외 건수 기록을 추가한다. "수집 결과 기록"은 요청 단위 계약을 소스 단위 성공/실패로 바꾼다.
- `topic-ranking`: 소스 다양성 배수표를 `{1: 1.0, 2: 2.0}`으로 바꾼다. 등수 산출 표와 주제 묶기 예시에서 GitHub을 뺀다. Reddit 슬롯 예약의 근거를 다시 쓴다.
- `daily-automation`: 발행 여부 판정의 "세 소스"를 "두 소스"로 바꾼다. 같은 전제를 시나리오 **WHEN**에 담고 있는 "스케줄 비활성화 방지"도 함께 바꾼다.
- `brief-publication`: 수집 상태 배너가 표시하는 소스를 둘로 줄인다. "Discord 알림"의 발행 실패 시나리오 전제도 "두 소스"로 바꾼다.

## Impact

### 코드

| 파일 | 변경 |
|---|---|
| `scripts/collect.py` | `collect_github` 및 `GITHUB_*` 상수 제거, `SOURCES` 축소, Reddit 제외 건수를 `filtered`에 기록, `_get`·`main()`의 소스 칸 기록을 소스 단위로 |
| `scripts/common.py` | `blank_status`의 `github` 칸 제거, 소스 칸 필드 축소, `filtered`·기록 단위 주석 재작성, `any_source_succeeded` 문구 |
| `scripts/rank.py` | `SIGNALS`에서 `github` 제거, `DIVERSITY` 배수표 교체, `RESERVED_REDDIT_RANKS` 근거 주석 |
| `scripts/publish.py` | `SOURCE_LABEL`, 상태 배너 행, 배너 소스 갈래를 정상/실패 둘로, "세 소스" 문구 |
| `scripts/notify.py` | `SOURCE_LABELS`, `source_lines`의 소스 갈래를 정상/실패 둘로 |
| `scripts/llm_input.py` | 본문 절단 근거 주석(GitHub 이슈 본문 언급) |
| `prompts/cluster.md` | 소스 목록, 교차 소스 묶기 예시 |
| `prompts/summarize.md` | 예시 문장의 소스 표기 |
| `.github/workflows/brief.yml` | 수집 단계의 `GITHUB_TOKEN` 환경 변수 |
| `README.md` | 소스 표, "세 소스" 문구, 시크릿 표의 용도 |
| `tests/test_collect.py` | GitHub 수집 테스트 제거 |
| `tests/test_rank.py` | `gh_` 픽스처 44곳을 Reddit·HN 조합으로 재구성. 새 배수 2.0에 맞춰 기대값 갱신 |
| `tests/test_publish.py` | 상태 배너 픽스처의 소스 수와 소스 칸 스키마 |

### 마이그레이션

`from_run_id` 재실행 경로는 이전 실행의 `status.json`을 그대로 내려받는다(`.github/workflows/brief.yml`의 수집 재사용 단계). `common.load_status`는 읽어 온 데이터에 없는 칸만 채우고 남는 칸은 지우지 않으므로, 예전 실행의 `sources.github`가 살아남아 `any_source_succeeded`의 판정에 들어갈 수 있다. 알려진 소스만 남기도록 정리하는 처리가 필요하다.

### 데이터

- 1차 LLM 입력이 실측 기준 113건에서 44건 규모로 줄어든다(61% 감소).
- 브리프 상위 8칸을 두고 경쟁하는 주제 수가 함께 줄어, 단일 항목 주제가 상위에 오를 확률이 높아진다.

### 시크릿

`GITHUB_TOKEN`은 계속 필요하다. 용도에서 이슈 조회가 빠지고 gh-pages 발행만 남는다.
