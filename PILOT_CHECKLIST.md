# 시범 운영(1~2주) 전 점검 체크리스트

M1~M7으로 구현된 파이프라인을 실제 스케줄로 돌리기 전에 확인할 항목. 로컬 테스트에서 관찰된 구체적인 실패 양상을 기준으로 작성했다.

## 0. 가장 중요한 선행 확인 — Amazon / Google Trends 외부 차단

로컬 테스트에서 `collect_amazon.py`는 매번 Amazon으로부터 `503 Service Unavailable`을, `collect_trends.py`는 매번 `429`(rate limit)를 받았다. 즉 지금 상태로 시범 운영을 시작하면 **아마존/Trends 데이터는 매주 계속 null일 가능성이 높다.**

- [ ] 시범 운영 첫 주 실행 후 `data/{week}.json`을 열어 `amazon[].asin`, `google_trends.US/JP` 값이 실제로 채워지는지 확인
- [ ] 계속 null이면: Amazon은 요청 헤더/딜레이 조정 또는 실행 환경(예: GitHub Actions runner IP 자체가 차단 대상인지) 재검토, Trends는 pytrends 대체 라이브러리 또는 재시도 간격 확대 검토
- [ ] 이 채널들이 당장 안 되더라도 Ulta/TikTok/Instagram(Gemini grounding)만으로도 파이프라인 자체는 정상 동작하므로, "완전 실패"와 "일부 채널 미수집"을 구분해서 판단할 것

## 1. Amazon 스크래핑 셀렉터가 실제 페이지 구조와 맞는지 확인

- [ ] 브라우저에서 추적 대상 제품의 실제 아마존 검색결과/상세 페이지를 열어 `collect_amazon.py`가 참조하는 셀렉터가 여전히 유효한지 확인: `div[data-component-type='s-search-result'][data-asin]`, `.a-price .a-offscreen`, `#acrPopover`/`span.a-icon-alt`, `#acrCustomerReviewText`, `#availability`, `"bought in past month"` 텍스트, `#in <카테고리>` 패턴
- [ ] 503이 아니라 정상 200 응답인데도 필드가 null이면 셀렉터 변경 가능성이 높음 → 실제 페이지 HTML 일부를 저장해 셀렉터 보정
- [ ] `scripts/config.py`의 `asin`을 `None`으로 둔 채 운영 중이면, 검색 결과 1위 제품이 매주 바뀌어 추적 대상이 흔들릴 수 있음 → 최초 몇 주 확인 후 올바른 ASIN을 config에 고정하는 것을 권장

## 2. Gemini grounding 응답이 스키마대로 파싱되는지 확인

- [ ] `python -m scripts.collect_grounding`를 여러 번 실행해 `confidence` 값 분포 확인 (`low` vs `failed`)
- [ ] 로컬 테스트에서 TikTok 응답이 JSON 파싱 실패(빈 응답, 배열 응답 등)로 `confidence: "failed"`가 되는 경우가 실제로 관찰됨 — 실패율이 계속 높으면 프롬프트에 "다른 설명 없이 순수 JSON 객체 하나만" 같은 제약을 더 명시적으로 강화
- [ ] `sources` 필드가 실제 URL인지(citation 인덱스 숫자가 아닌지) 확인 — 현재는 API의 `grounding_metadata`에서 직접 추출하도록 고쳐져 있으므로 정상이라면 `vertexaisearch.cloud.google.com/...` 형태여야 함

## 3. GitHub Actions 크론 시간이 실제 06:17 KST에 맞게 동작하는지 확인

- [ ] `.github/workflows/weekly_update.yml`의 `cron: "17 21 * * 6"`이 UTC 기준 토요일 21:17 = KST 기준 일요일 06:17로 계산된 것이 맞는지 재검증 (KST = UTC+9, 자정을 넘어가는 변환이므로 요일이 하루 당겨짐에 유의)
- [ ] 첫 자동 실행 후 GitHub Actions 실행 로그의 타임스탬프(UTC로 표시됨)를 확인해 의도한 시각과 맞는지 확인
- [ ] GitHub의 스케줄 트리거는 부하 상황에 따라 수 분~수십 분 지연될 수 있음을 감안 — 정각 일치보다는 "그 날 안에 실행되었는가"를 우선 확인
- [ ] `workflow_dispatch`로 수동 실행해 전체 파이프라인이 최초 1회 정상 완주하는지 먼저 확인 (스케줄만 믿고 기다리지 말 것)

## 4. GitHub Secrets(GEMINI_API_KEY) 설정 여부 확인

- [ ] 리포지토리 Settings → Secrets and variables → Actions에 `GEMINI_API_KEY`가 등록되어 있는지 확인
- [ ] 미설정 시 `collect_grounding.py`의 `_get_client()`가 `RuntimeError("GEMINI_API_KEY is not set")`을 던지도록 되어 있으므로, Actions 실행 로그에 이 문구가 보이면 시크릿 미설정이 원인임을 바로 알 수 있음
- [ ] 로컬 `.env`에 있는 키와 GitHub Secrets에 등록한 키가 동일한지(오타 없이 복사되었는지) 확인

## 5. `data/history.json`이 매주 정상적으로 append되는지, 중복 저장되지 않는지 확인

- [ ] `run_weekly.py`는 같은 `week` 값의 기존 항목을 제거한 뒤 새로 append하는 방식(upsert)으로 구현되어 있음 — 수동 재실행/재시도가 있어도 같은 주차가 중복 저장되지 않아야 함
- [ ] 확인 방법: `python -c "import json; h=json.load(open('data/history.json')); print(len(h), len(set(e['week'] for e in h)))"` 실행 후 두 숫자가 같은지 확인(다르면 중복 발생)
- [ ] `docs/data/history.json`(대시보드가 fetch하는 사본)과 `data/history.json`(원본)이 항상 동일한 내용인지 확인 — `run_weekly.py`가 매 실행마다 두 곳에 동시에 쓰도록 되어 있음

## 6. GitHub Pages 배포 후 대시보드가 정상 렌더링되는지 확인

- [ ] 리포지토리 Settings → Pages에서 소스가 `/docs` 폴더로 지정되어 있는지 확인
- [ ] 배포된 URL에서 `data/history.json`이 직접 열리는지 확인 (예: `https://<user>.github.io/<repo>/data/history.json`) — 404면 `docs/data/history.json`이 아직 커밋되지 않은 것
- [ ] 배포된 대시보드 페이지를 열어 브라우저 개발자 도구 콘솔에 에러가 없는지 확인
- [ ] 카드 5개, 차트 5개, AI 코멘트+출처 링크, 원자료 테이블, CSV 다운로드 버튼이 모두 정상 표시되는지 확인
- [ ] 모바일 화면 폭에서 가로 스크롤이 발생하지 않는지 확인
