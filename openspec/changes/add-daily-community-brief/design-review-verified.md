# 검증 사실 캐시

이 루프 실행 중 실제 코드를 열어 확인한 관찰 사실. 코드는 루프 중 불변이므로
같은 루프의 후속 에이전트는 이 관찰을 직접 확인한 것과 동등하게 신뢰해도 된다.
사실만 담는다 — 심각도·지적·권고·평가 금지.

- `저장소 전체 파일 목록(find, .git 제외)` — 구현 코드는 없다. 존재하는 실행 파일은 `.github/workflows/spike-reddit-{oauth,rss,pace}.yml` 셋뿐이고, `scripts/`·`prompts/`·`index.html`·발행 워크플로는 아직 없다 (라운드 1)
- `.github/workflows/spike-reddit-pace.yml:29-83` — 고정 간격 요청 측정 스파이크. 기본 `interval=60`, `count=12`, 재시도 없음. 대상 URL은 `https://www.reddit.com/comments/{short}/.rss?limit=100`, 목록 URL은 `https://www.reddit.com/r/ClaudeCode/top/.rss?t=day&limit=100`. 요청 헤더에 Chrome 브라우저 User-Agent 문자열을 넣는다 (라운드 1)
- `.github/workflows/spike-reddit-pace.yml:5-7` — 주석에 "앞선 측정에서 90회 요청 중 15회 성공(약 55초당 1건)", "재시도 횟수가 1→6→실패 패턴" 이라고 적혀 있다. 실측 로그 자체는 저장소에 없다 (라운드 1)
- `.github/workflows/spike-reddit-rss.yml:57-66` — 피드 파싱을 정규식(`re.findall(r"<entry>(.*?)</entry>")`)으로 하고 `<id>t3_\w+</id>`, `<title>`, `<published>` 만 추출한다. 업보트·댓글 수 필드는 추출하지 않는다 (라운드 1)
- `.github/workflows/spike-reddit-rss.yml:72-86` — `top/.rss?t=day&limit=100` 을 `ClaudeCode`, `ClaudeAI` 두 서브레딧에 대해 각각 최대 12회 재시도(백오프 9초)로 요청한다 (라운드 1)
- `.github/workflows/spike-reddit-oauth.yml:26-47` — 비인증 `.json` 엔드포인트와 `api/v1/access_token` 더미 자격증명 응답 코드를 찍는 단계. 403이면 `exit 1` 로 실패시킨다. 2단계는 `REDDIT_CLIENT_ID` 시크릿이 있을 때만 실행된다 (라운드 1)
- `openspec/changes/add-daily-community-brief/tasks.md:92` — 7.4는 "출력에서 허용 목록 밖의 HTML 태그를 제거하는 필터를 구현한다" 뿐이며, 속성(attribute) 처리나 `href` 스킴 검사를 지시하는 문장은 없다 (라운드 1)
- `openspec/changes/add-daily-community-brief/tasks.md:104` — 8.3e의 URL 스킴 확인 대상은 "`href`에 넣을 URL", 즉 `items.json` 유래 URL이다 (라운드 1)
- `design.md·tasks.md·specs/*/spec.md 전체 grep("스킴", "속성", "허용 태그|허용 목록")` — 스킴 확인을 지시하는 문장은 `design.md:235`, `specs/brief-publication/spec.md:78,119`, `tasks.md:104(8.3e)`, `tasks.md:105(8.3f)` 뿐이고 모두 `items.json` 유래 URL이 대상이다. 속성값 이스케이프를 지시하는 문장(`design.md:234`, `spec.md:74`, `tasks.md:103`)도 모두 치환 시점의 제3자 문자열이 대상이다. 2차 LLM이 직접 쓴 태그의 속성이나 `href` 를 검사·제거하라는 문장은 네 문서 어디에도 없다 (라운드 1)
- `.github/workflows/spike-reddit-pace.yml:34-73` — 인라인 `python3` 힙독으로 실행하며 import 는 `urllib.request, urllib.error, time, re, os` 뿐이다. 워크플로에 pip install 단계가 없다 (라운드 2)
- `저장소 루트 ls -la` — 최상위에 `README.md`, `.github/`, `openspec/`, `.claude/` 만 있다. `scripts/`, `prompts/`, `index.html`, `.nojekyll`, 발행 워크플로는 여전히 없다 (라운드 2)
- `git remote -v` — origin 은 `https://github.com/Junroot/reddit-claude.git` 하나다 (라운드 2)
