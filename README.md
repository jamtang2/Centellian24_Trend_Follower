# Centellian24_US_Monitor

센텔리안24(동국제약)의 미국 시장 인기도(수요 측 선행지표)를 매주 자동 수집하고 누적 시각화하는 정적 대시보드.

풀 배경/스펙은 [`PRD/Centellian24_US_Monitor_PRD.md`](PRD/Centellian24_US_Monitor_PRD.md) 참고.

## 폴더 구조

```
scripts/            수집 스크립트 (Amazon, Google Trends, Gemini grounding, 주간 실행/요약)
data/               주간 스냅샷(YYYY-MM-DD.json) + 누적 history.json
docs/               GitHub Pages로 배포되는 정적 대시보드 (index.html)
.github/workflows/  GitHub Actions 워크플로우 (주간 자동 실행)
```

## 로컬 실행 방법 (초안)

```bash
pip install -r requirements.txt
cp .env.example .env   # GEMINI_API_KEY 값 채워넣기
python -m scripts.run_weekly
```

개별 수집 스크립트는 단독으로도 실행 가능합니다 (구현 완료 후):

```bash
python -m scripts.collect_amazon
python -m scripts.collect_trends
python -m scripts.collect_grounding
```

## 진행 상태

PRD의 마일스톤(M1~M8)을 순서대로 구현 중입니다. 현재 리포지토리 구조만 잡힌 상태이며, 수집 로직은 아직 구현되지 않았습니다.
