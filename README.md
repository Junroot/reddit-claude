# reddit-claude

Claude Code를 둘러싼 논의가 Reddit, Hacker News, GitHub Issues 세 곳에 흩어져 있다.
흐름을 따라가려면 매일 세 곳을 각각 돌아야 하고, 같은 사건이 세 곳에서 다른 제목으로
다뤄지기 때문에 무엇이 그날의 진짜 화제였는지는 한참 읽어야 드러난다.

하루 한 번 자동으로 모아 주제별로 묶고 화제 순으로 정렬한 브리프를 한 페이지에 발행한다.

**브리프: https://junroot.github.io/reddit-claude/**

주소는 고정이고 매일 덮어쓴다. 과거 브리프는 남기지 않는다.

## 언제 도착하나

한국 시간 **05:40**에 시작해 **05:50~06:00경** 도착한다. 발행되면 Discord로 알린다.
실행이 실패한 날에도 알린다 — 성공만 알리면 실패가 침묵과 구분되지 않기 때문이다.

GitHub Actions 스케줄은 원래 수 분에서 수십 분까지 밀릴 수 있다. 지연 자체는 실패가 아니다.

## 무엇을 모으나

| 소스 | 대상 | 시간 창 |
|---|---|---|
| Reddit | r/ClaudeCode의 `top?t=day` | 게시 48시간 이내 |
| Hacker News | Algolia 검색어 `Claude Code` | 작성 24시간 이내 |
| GitHub Issues | `anthropics/claude-code` | **생성** 48시간 이내, 댓글+리액션 0건 제외 |

시간 창이 소스마다 다른 것은 의도한 것이다. 통일하면 각 소스에서 그날 가장 중요한 것을
버리게 된다. 대신 페이지에 기준 시각과 항목별 게시 시각을 표시해 독자가 판단하게 한다.

GitHub만 `created_at`을 쓰는 이유는 [design.md의 D14](openspec/changes/add-daily-community-brief/design.md)에
적혀 있다. 요약하면 `updated_at`은 라벨 변경만으로도 갱신되어 수백 일 된 이슈가 섞이고,
API가 주는 댓글·리액션 수가 누적값이라 등수까지 왜곡되기 때문이다.

## 어떻게 도나

```
 [1] collect     스크립트   세 소스 수집        → items.json, status.json
 [2] cluster     LLM 1차    주제 묶기           → topics.json
 [3] rank        스크립트   보정·점수·상위 8    → ranked.json
 [4] enrich      스크립트   상위 주제 댓글      → comments.json
 [5] summarize   LLM 2차    요약문 작성         → brief.html
 [6] publish     스크립트   페이지 조립         → gh-pages
```

**판단만 LLM이 하고 수집·순위 계산·대기·발행은 스크립트가 한다.** 순위가 매일 같은 규칙으로
나와야 하고, 왜 이 주제가 위에 있는지 설명할 수 있어야 하기 때문이다. 1차 LLM은 묶기만 하고
순위를 매기지 않으며, 2차 LLM은 확정된 순위 위에서 문장만 쓴다.

수집·순위 계산·발행 스크립트는 Python 3 표준 라이브러리만 쓴다. 이 경로에는 의존성 설치
단계가 없어 패키지 저장소 장애가 실패 원인에서 빠진다.

## 실행하기

```bash
# 전체 파이프라인 (Actions에서 수동 실행)
gh workflow run brief.yml

# 요약 단계부터 다시 (이전 실행의 산출물을 재사용한다)
gh workflow run brief.yml -f from_run_id=<이전 실행 ID>
```

두 번째 형태가 있는 이유는 비용 때문이다. `[4] enrich`가 Reddit에 최대 8분간 요청을 보내는데,
요약 문장이 마음에 안 든다는 이유로 다시 8분어치 요청을 보내는 것은 낭비이자 차단 위험이다.

스크립트를 따로 돌릴 수도 있다.

```bash
python3 scripts/collect.py --work work
python3 scripts/llm_input.py cluster --work work
# (여기서 LLM이 work/topics.json을 만든다)
python3 scripts/validate_topics.py --work work
python3 scripts/rank.py --work work
python3 scripts/enrich.py --work work --interval 60
python3 scripts/llm_input.py summarize --work work
# (여기서 LLM이 work/brief.html을 만든다)
python3 scripts/publish.py --work work
```

## 테스트

```bash
python3 -m unittest discover -s tests
```

의존성이 없으므로 설치할 것이 없다.

## 필요한 시크릿

| 이름 | 용도 |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | Actions에서 LLM 실행 (구독 인증) |
| `DISCORD_WEBHOOK_URL` | 발행 및 실패 알림 |
| `GITHUB_TOKEN` | 이슈 조회, gh-pages 발행 (Actions 기본 제공) |

### 토큰 갱신

`CLAUDE_CODE_OAUTH_TOKEN`은 **만료된다.** 만료되면 LLM 단계가 실패하고 브리프가 멈춘다.
감지 수단은 Discord 실패 알림뿐이다.

```bash
claude setup-token          # 로컬에서 실행. 토큰은 한 번만 표시된다
```

발급한 값을 저장소 시크릿 `CLAUDE_CODE_OAUTH_TOKEN`에 바로 교체한다.

토큰은 발급한 개인 계정에 묶이므로 그 계정의 구독 한도를 함께 쓴다. 같은 계정으로 Claude를
많이 쓴 날은 새벽 실행이 한도에 걸릴 수 있다.

## 설계 문서

무엇을 왜 그렇게 정했는지는 `openspec/changes/add-daily-community-brief/` 아래에 있다.

| 문서 | 내용 |
|---|---|
| `proposal.md` | 무엇을 만드는가 |
| `design.md` | 어떻게 만드는가. 결정 D1~D14와 감수한 위험 |
| `specs/` | 네 능력의 요구사항과 시나리오 |
| `tasks.md` | 구현 순서와 진행 상태 |
