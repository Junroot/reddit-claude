## MODIFIED Requirements

### Requirement: 수집 상태 배너

시스템은 소스별 수집 상태를 페이지에 항상 표시해야 한다(SHALL). 문제가 있을 때만 표시해서는 안 된다(MUST NOT).

문제가 있을 때만 나타나는 표시는 독자가 그 자리를 보지 않게 만들고, 정작 중요한 날 놓치게 한다.

배너가 표시하는 소스는 현재 수집 대상인 Reddit과 Hacker News 둘로 한정한다(MUST). 더 이상 수집하지 않는 소스의 행을 표시해서는 안 된다(MUST NOT).

#### Scenario: 모든 소스 성공

- **WHEN** 두 소스의 수집이 모두 성공한다
- **THEN** 페이지에 두 소스가 모두 정상 수집되었다는 표시가 나타난다

#### Scenario: 일부 소스 실패

- **WHEN** Reddit 수집이 실패하고 Hacker News가 성공한다
- **THEN** 페이지에 Reddit 수집이 실패했음이 명시된다
- **AND** 브리프 본문은 Hacker News의 내용으로 발행된다

#### Scenario: 댓글 보강 부분 실패

- **WHEN** Reddit 댓글 요청 6건 중 2건이 실패한다
- **THEN** 페이지에 댓글 보강이 부분적으로 실패했음이 표시된다

#### Scenario: 자리표시자 규약 위반이 있는 날

- **WHEN** `status.json`의 `publish.unresolved_refs` 또는 `publish.raw_links`가 0이 아니다
- **THEN** 배너에 각각의 건수가 표시된다

#### Scenario: 링크로 만들지 못한 항목이 있는 날

- **WHEN** `status.json`의 `publish.unsafe_links`가 0이 아니다
- **THEN** 배너에 그 건수가 표시된다

### Requirement: Discord 알림

시스템은 실행 결과를 Discord 웹훅으로 알려야 한다(SHALL). 성공한 날과 실패한 날 모두 알린다(MUST). 알림 문구는 한국어로 쓴다.

성공만 알리면 실패가 침묵과 구분되지 않아, 브리프가 멈춘 사실을 알아챌 수 없다.

#### Scenario: 발행 성공 알림

- **WHEN** 브리프 발행이 성공한다
- **THEN** Discord 알림에 브리프 링크와 소스별 수집 상태가 포함된다

#### Scenario: 부분 실패 알림

- **WHEN** 일부 소스가 실패했으나 발행에는 성공한다
- **THEN** Discord 알림에 실패한 소스가 명시된다

#### Scenario: 발행 실패 알림

- **WHEN** 두 소스가 모두 실패해 발행하지 않는다
- **THEN** Discord 알림에 발행하지 않았다는 사실과 그 이유가 포함된다

#### Scenario: 단계 실패 알림

- **WHEN** 요약 단계나 발행 단계에서 오류가 발생해 실행이 중단된다
- **THEN** Discord로 실패가 알려진다
- **AND** 실행이 조용히 종료되지 않는다
