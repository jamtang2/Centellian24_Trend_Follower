# Centellian24_US_Monitor

센텔리안24(동국제약)의 미국 시장 인기도(수요 측 선행지표)를 매주 자동 수집하고 누적 시각화하는 정적 대시보드.

풀 배경/스펙은 [`PRD/Centellian24_US_Monitor_PRD_rev.md`](PRD/Centellian24_US_Monitor_PRD_rev.md) 참고 (아키텍처 변경 이력은 원본 [`Centellian24_US_Monitor_PRD.md`](PRD/Centellian24_US_Monitor_PRD.md) 대비 rev 문서 1장/7장 참고).

## 아키텍처: 로컬 실행 + GitHub Pages 배포 (2단 구조)

시범 운영 중 GitHub Actions 러너(데이터센터 IP)가 아마존(503)·Google Trends(429)에서 반복적으로 차단당하는 현상이 확인되어, **데이터 수집은 사용자 로컬 PC에서, 정적 사이트 배포는 GitHub Pages에서** 각각 처리하도록 구조를 변경했습니다.

- `.github/workflows/weekly_update.yml.disabled` — 더 이상 실행되지 않는 옛 GitHub Actions 수집 워크플로우(히스토리 보존용, 비활성화 처리됨).
- GitHub Pages는 `docs/` 폴더로의 push를 감지해 기존 자동 배포 기능만 그대로 사용합니다(별도 워크플로우 불필요).
- 로컬 PC에서 `python -m scripts.run_weekly`를 실행하면 전체 수집 → history 누적 → 대시보드 재생성 → git commit/push까지 한 번에 처리됩니다 (`scripts/git_push.py`).

## 폴더 구조

```
scripts/                  수집 스크립트 (Amazon, Google Trends, Gemini grounding, Qoo10, 감성분석, 주간 실행/요약, git push, headless 브라우저 fetch 공용 모듈)
data/                     주간 스냅샷(YYYY-MM-DD.json) + 누적 history.json + run_log.json(실행 이력)
docs/                     GitHub Pages로 배포되는 정적 대시보드 (index.html)
.github/workflows/        weekly_update.yml.disabled (비활성화된 옛 GitHub Actions 워크플로우)
run_weekly.bat            Windows 작업 스케줄러가 호출하는 배치 파일
setup_scheduler.ps1        작업 스케줄러 등록 스크립트 (관리자 권한 PowerShell에서 1회 실행)
logs/                     run_weekly.bat 실행 로그 (run_YYYY-MM-DD.log)
```

## 로컬 실행 방법

```bash
pip install -r requirements.txt
playwright install chromium   # 최초 1회: 헤드리스 Chromium 바이너리 설치 (Amazon/Qoo10 스크래핑용)
cp .env.example .env   # GEMINI_API_KEY 값 채워넣기
python -m scripts.run_weekly
```

`playwright install chromium`은 브라우저 바이너리를 로컬에 내려받는 별도 단계로, `pip install`만으로는 설치되지 않습니다 — 최초 1회 또는 Playwright 버전이 바뀔 때마다 실행하면 됩니다.

수동 실행 시 마지막 단계에서 `data/`, `docs/` 변경사항이 있으면 자동으로 git add/commit/push까지 수행됩니다. git push에 필요한 인증(SSH 키 또는 `gh auth login` 토큰)이 로컬에 미리 설정되어 있어야 합니다.

### 아마존/Qoo10이 requests만으로 차단되는 문제 (헤드리스 브라우저로 전환)

`scripts/collect_amazon.py`, `scripts/collect_qoo10.py`는 일반 `requests` 호출이 아니라 **헤드리스 Chromium(Playwright)** 으로 페이지를 열어 렌더링이 끝난 HTML을 가져옵니다 (`scripts/browser_fetch.py`). 브라우저 헤더를 그대로 흉내 낸 `requests` 호출로도 아마존은 503으로 완전 차단되고, Qoo10 재팬은 HTTP 200으로 위장한 봇 차단 페이지를 돌려주는 현상이 실측으로 확인되어, 실제 TLS/JS 지문을 가진 브라우저로 전환했습니다. 파싱 로직(BeautifulSoup 셀렉터, JSON-LD 파싱)은 기존 그대로 재사용되며, 가져오는 방식만 바뀌었습니다.

개별 수집 스크립트는 단독으로도 실행 가능합니다:

```bash
python -m scripts.collect_amazon
python -m scripts.collect_trends
python -m scripts.collect_grounding
python -m scripts.collect_qoo10
python -m scripts.analyze_sentiment
```

## 매주 자동 실행 등록 (Windows 작업 스케줄러)

매주 일요일 06:17 KST에 `scripts/run_weekly.py`를 자동 실행하도록 등록하려면, 관리자 권한 PowerShell에서 한 번만 실행하세요:

```powershell
.\setup_scheduler.ps1
```

- 등록되는 작업은 `run_weekly.bat`을 호출하며, 표준출력/에러를 `logs/run_YYYY-MM-DD.log`에 저장합니다.
- "PC가 꺼져있어 예정된 시간을 놓친 경우, 켜지면 최대한 빨리 실행" 옵션이 포함되어 있습니다.
- 등록 확인: `schtasks /query /tn "Centellian24_US_Monitor_Weekly" /v /fo list`
- **주의**: 이 자동화는 트리거 시점에 로컬 PC가 켜져 있고 인터넷에 연결되어 있어야 동작합니다. PC가 꺼져 있으면 그 주는 실행되지 않습니다 (아래 "실행 누락 대응" 참고). git push에 필요한 인증(SSH 키 또는 `gh auth` 토큰)이 스케줄러 실행 컨텍스트(사용자가 로그인하지 않은 상태 포함)에서도 유효한지 사전에 확인하세요.

## 실행 누락 대응 (이번 주 실행을 놓쳤을 때)

`scripts/run_weekly.py`는 성공/실패 여부와 무관하게 실행 결과를 `data/run_log.json`에 기록합니다. `scripts/check_missed_run.py`를 실행하면 이번 주(일요일 기준) 실행 기록이 있는지 확인해 누락 시 알려줍니다:

```bash
python -m scripts.check_missed_run
```

로그인 시 자동으로 확인하고 싶다면 `check_missed_run.bat`을 Windows 시작프로그램에 등록하세요:

1. `Win+R` → `shell:startup` 입력 후 엔터 (시작프로그램 폴더가 열립니다).
2. 이 폴더 안에 `check_missed_run.bat`의 바로가기(shortcut)를 생성합니다 (`check_missed_run.bat` 우클릭 → 바로 가기 만들기 → 생성된 바로가기를 `shell:startup` 폴더로 이동).
3. 다음 로그인부터 로그인 시마다 자동으로 이번 주 실행 여부를 확인하고, 누락 시 콘솔 메시지 + (plyer 설치 시) 데스크톱 알림 팝업을 띄웁니다.

**수동으로 놓친 주차 따라잡는 절차:**

1. `python -m scripts.run_weekly` 를 수동으로 실행합니다 (인터넷 연결 확인).
2. 실행 로그에서 각 채널 수집 성공/실패 여부를 확인합니다.
3. `git status`, `git log -1` 로 커밋/푸시가 정상적으로 이루어졌는지 확인합니다 (푸시 실패 시 `git push`를 직접 실행).
4. GitHub Pages 대시보드(`docs/`)가 최신 데이터로 갱신되었는지 배포 후 브라우저에서 확인합니다.

## 진행 상태

PRD의 마일스톤(M1~M10)을 순서대로 구현했습니다. 로컬 스케줄러 기반 자동화(M7~M7-2), 실행 누락 대응(M9), Qoo10 재팬 스크래핑 + 아마존 리뷰 감성분석(M10)까지 반영된 상태입니다.
