# PRD: Centellian24_US_Monitor
### 센텔리안24(동국제약) 미국 시장 인기도 추적 대시보드

---

## 1. 배경 (Background)

- 동국제약의 화장품 수출액은 2024년 163억원 → 2025년 300억원 → 2026년 1,000억원 돌파 전망(LS증권 추정)이며, 특히 미국향 수출은 전년 대비 6~7배 성장이 기대되는 상황.
- 지난달(2026.06) 센텔리안24가 미국 뷰티 전문 유통 '얼타 뷰티(Ulta Beauty)' 1,400개 매장, '노드스트롬' 89개 매장에 입점 완료.
- 그러나 이는 **유통망 확장(공급 측 지표)** 일 뿐, 실제 미국 소비자들의 **수요/인기 반응(수요 측 지표)** 은 별도로 확인되지 않음.
- 회사 측 공식 실적(분기 IR, DART 공시)은 분기 단위로만 확인 가능해 반응 속도가 느림 → **주간 단위 선행지표(leading indicator)** 를 통해 미국 내 확산 추이를 조기에 포착하고자 함.
- 기존 구축 파이프라인(PRD → Claude Code → GitHub Actions → GitHub Pages, 예: Shortage_Bottleneck_Scanner, CAPEX_Dashboard)과 동일한 아키텍처를 재사용.

## 2. 목적 (Goal)

센텔리안24의 미국 시장 내 소비자 관심도·판매 확산 정도를 나타내는 직·간접 지표를 **매주 1회 자동 수집**하고, **시계열 누적 대시보드**로 시각화하여 동국제약 화장품 사업 모멘�텀을 정성/정량적으로 조기 판단할 수 있게 한다.

## 3. 추적 지표 (Tracking Metrics)

| # | 지표 분류 | 구체 항목 | 유형 | 수집 난이도 |
|---|---|---|---|---|
| 1 | 아마존(Amazon.com) | 대표 제품별 추정 월간 판매량, 카테고리 내 Best Seller Rank(BSR), 리뷰 수, 평균 별점 | 직접(판매 프록시) | 중 |
| 2 | Google Trends | "Centellian24", "Madeca Cream" 등 키워드의 미국 + 일본 지역 검색 관심도 지수(0~100) | 간접(수요) | 낮음 |
| 3 | Ulta Beauty | 자사몰 내 입점 제품 수, 상품별 리뷰 수·평점, 품절 여부 | 직접(유통/판매 프록시) | 중~높음 |
| 4 | TikTok 해시태그 | #Centellian24, #MadecaCream 등 해시태그 게시물 수, 누적 조회수 | 간접(바이럴리티) | 높음 |
| 5 | Instagram 해시태그 | 동일 해시태그 게시물 수, 대표 포스트 참여도(좋아요 등 확인 가능 범위 내) | 간접(바이럴리티) | 높음 |

> 참고: 아마존/Ulta는 "판매량 지표"가 아니라 "판매 순위·리뷰 증가 속도"를 프록시로 사용하는 것이며, TikTok/Instagram 해시태그 지표는 공식 API 접근이 제한적이므로 수집 방식에 한계가 있음을 3장 하단 리스크에 명시.

## 4. 수집 방식 및 기술적 제약

### 4.1 아마존 — 직접 스크래핑
- 공식 Product Advertising API는 승인 절차·매출 실적 요건이 있어 개인 프로젝트로는 접근 제한 → **검색 결과 페이지 + 상품 상세 페이지 스크래핑**으로 진행(SerpApi 등 유료 서비스 미사용).
- 최소 수집 필드: 상품명, ASIN, **추정 월간 판매량**(상품 상세 페이지의 "지난달 N+ 구매" 배지 등에서 파싱), 카테고리명, 카테고리 내 BSR 순위, 리뷰 수, 평균 별점, 가격, 품절 여부.
- 대표 추적 상품 3~5개 선정(마데카 크림 타임 리버스, 360도 샷 PDRN 리프팅 아이크림, 마데카 크림 액티브 리뉴 PDRN 등 주력 라인 기준).
- 페이지 구조 변경으로 스크래핑이 실패하는 경우, 해당 주차는 이전 값을 유지하고 실패 로그만 남김(4.4의 grounding 폴백 대상에서는 제외 — 아마존은 스크래핑 전용 채널로 고정).

### 4.2 Google Trends — 미국 + 일본
- `pytrends`(비공식 라이브러리) 사용, 국가 코드 **US, JP 둘 다 조회**, 지난 12개월 롤링 윈도우로 조회 후 최신 주차 값만 누적 저장.
- 키워드셋: "Centellian24", "Madeca Cream"(영문) + 필요 시 일본어 표기("センテリアン24" 등) 별도 트래킹 여부는 M2 단계에서 실데이터 확인 후 결정.
- 무료·안정적이나 비공식 API이므로 요청 빈도 제한(주 1회 실행이므로 문제 없음) 유의.

### 4.3~4.4 Ulta Beauty / TikTok / Instagram 해시태그 — Google Search grounding 전용
- 세 채널 모두 스크래핑을 시도하지 않고 **Gemini API + Google Search grounding**을 1차이자 유일한 수집 방식으로 사용.
- 질의 예시:
  - Ulta: "Ulta Beauty 웹사이트에서 Centellian24(센텔리안24) 제품의 현재 리뷰 수, 평균 별점, 입점 SKU 수, 품절 여부를 조사해줘"
  - TikTok: "TikTok에서 #Centellian24, #MadecaCream 해시태그의 게시물 수와 대표 영상 조회수를 조사해줘"
  - Instagram: "Instagram에서 #Centellian24 해시태그의 게시물 수를 조사해줘"
- 응답은 구조화된 JSON으로 반환하도록 프롬프트를 설계하고, 근거가 된 출처 URL을 함께 받아 저장.
- 이 방식으로 얻은 모든 수치는 **추정치(estimate)** 로 취급하며, 대시보드에 신뢰도 낮음 배지를 표기(아마존/Google Trends 대비 실측 정합성이 낮음을 명시).

### 4.5 AI API 활용 (Google Gemini)
- 본 프로젝트는 **Gemini 단독 사용**. 기존 Claude/GPT/Gemini 앙상블 방식과 달리, Google Search grounding 기능이 핵심 수집 채널(4.3~4.4)이자 유일한 AI 호출 지점.
- 역할:
  1. Ulta / TikTok / Instagram 지표의 1차이자 유일한 수집 수단(grounding 검색)
  2. 주간 수집 데이터 기반 정성적 요약 코멘트 생성("이번 주 아마존 추정 판매량 20,000개 유지, 아이크림 카테고리 1위 지속" 등)
  3. 출처 URL을 함께 반환하도록 프롬프트 설계(기존 프로젝트의 "출처 인용" 요구사항과 동일하게 적용)
- 모델: Gemini 최신 안정 버전(실행 시점 기준 확인 필요, grounding 기능 지원 모델 선택), API 키는 GitHub Actions Secrets에 저장.

## 5. 데이터 저장 및 누적 방식

- 매주 실행 결과를 `data/YYYY-MM-DD.json` 형태로 원본 스냅샷 저장 + `data/history.csv`(또는 `history.json`)에 누적 append.
- 스키마 예시:

```json
{
  "week": "2026-07-06",
  "amazon": [
    {"product": "마데카 크림 타임 리버스", "asin": "B0XXXXX", "est_monthly_sales": 20000, "category": "Face Moisturizers", "bsr": 45, "review_count": 4820, "rating": 4.6, "in_stock": true, "source": "scrape"},
    {"product": "360도 샷 PDRN 리프팅 아이크림", "asin": "B0YYYYY", "est_monthly_sales": 8500, "category": "Eye Treatment Creams", "bsr": 1, "review_count": 2100, "rating": 4.7, "in_stock": true, "source": "scrape"}
  ],
  "google_trends": {
    "US": {"Centellian24": 34, "Madeca Cream": 58},
    "JP": {"Centellian24": 21, "Madeca Cream": 40}
  },
  "ulta": {"review_count": 210, "rating": 4.5, "sku_count": 6, "in_stock": true, "source": "gemini_grounding", "confidence": "low"},
  "tiktok": {"hashtag": "#Centellian24", "post_count_est": 1200, "top_view_count_est": 850000, "source": "gemini_grounding", "confidence": "low"},
  "instagram": {"hashtag": "#Centellian24", "post_count_est": 3400, "source": "gemini_grounding", "confidence": "low"},
  "ai_summary": "이번 주 아마존 아이크림 카테고리 1위 유지, 추정 판매량 전주 대비 소폭 증가...",
  "sources": ["https://...", "https://..."]
}
```

- 누적 데이터를 기반으로 지표별 **주차별 추이 라인 차트** + **전주 대비 변화율(WoW)** 계산.

## 6. 대시보드 구성 (GitHub Pages)

기존 프로젝트(Shortage_Bottleneck_Scanner 등)와 톤앤매너 통일.

1. **상단 요약 카드**: 최신 주차 기준 5개 지표 스냅샷 + WoW 변화율(▲▼ 색상 표기)
2. **누적 추이 차트 (핵심 화면)**
   - 아마존 제품별 추정 월간 판매량 추이(막대/선 그래프)
   - 아마존 BSR 순위 추이(역순 스케일, 낮을수록 상단)
   - 아마존/Ulta 리뷰 수 누적 추이(선 그래프)
   - Google Trends 지수 추이 — **미국/일본 두 라인 비교**
   - TikTok/Instagram 게시물 수·조회수 추이(추정치 배지 표시)
3. **AI 주간 코멘트 섹션**: Gemini가 생성한 자연어 요약 + 참고 출처 링크
4. **원자료 테이블**: 주차별 raw 데이터 다운로드(CSV) 옵션
5. **신뢰도 표기**: 스크래핑 기반 실측(Amazon, Google Trends) vs Gemini grounding 기반 추정(Ulta, TikTok, Instagram) 구분 뱃지

## 7. 자동화 아키텍처

```
[GitHub Actions: 매주 일요일 06:17 KST 실행]
        │
        ├─ Step 1: Amazon 검색결과/상품 상세 페이지 스크래핑 (추정 판매량, BSR, 리뷰 수 등)
        ├─ Step 2: pytrends 호출 — Google Trends US + JP
        ├─ Step 3: Gemini grounding 호출 — Ulta Beauty 리뷰/입점 현황
        ├─ Step 4: Gemini grounding 호출 — TikTok 해시태그
        ├─ Step 5: Gemini grounding 호출 — Instagram 해시태그
        ├─ Step 6: 데이터 정합성 체크 + history 누적 저장
        ├─ Step 7: Gemini로 주간 코멘트 생성
        └─ Step 8: 정적 대시보드(index.html) 재생성 → GitHub Pages 배포
```

- 실행 시각은 사용자 지정에 따라 **매주 일요일 06:17 KST**로 고정(정각 경계를 피한 설정으로 기존 프로젝트 교훈과도 부합).
- 스크래핑(아마존) 실패 시 이전 주차 값 유지 + 로그 기록. Gemini grounding 호출(Ulta/TikTok/Instagram) 실패 시에도 동일하게 이전 값 유지.

## 8. 마일스톤 (기존 프로젝트 방식 준용)

| 단계 | 내용 |
|---|---|
| M1 | 리포지토리 생성, PRD 확정, 폴더 구조 설계 |
| M2 | Amazon 스크래핑(추정 판매량·BSR·리뷰) + Google Trends(US/JP) 수집 스크립트 구현 |
| M3 | Ulta / TikTok / Instagram 대상 Gemini Search grounding 프롬프트 및 파싱 로직 구현 |
| M4 | 3개 grounding 채널 신뢰도 플래그 처리 및 JSON 구조화 검증 |
| M5 | 데이터 누적 스키마 및 history 저장 로직 |
| M6 | GitHub Pages 대시보드(UI) 구현 — 차트, 요약 카드, AI 코멘트 |
| M7 | GitHub Actions 스케줄링 + Secrets(GEMINI_API_KEY) 설정 |
| M8 | 1~2주 시범 운영 후 데이터 품질 검증 및 임계값/알림 조정 |

## 9. 리스크 및 한계

- **법적/약관 리스크**: 아마존은 자동 스크래핑을 이용약관으로 제한하는 경우가 있어, 상업적 배포가 아닌 **개인 리서치 목적의 저빈도(주 1회) 조회**로 한정하고 과도한 요청은 피해야 함.
- **데이터 신뢰도**: Ulta/TikTok/Instagram 수치는 Gemini 검색 grounding 결과에 의존하는 추정치로, 실제 값과 오차가 클 수 있음 → 절대값보다는 **추세(방향성)** 참고용으로 활용 권장. 아마존 "추정 판매량"도 아마존이 공식 제공하는 정확한 수치가 아니라 페이지 내 구매 배지 기반 추정값임에 유의.
- **소스 변경 취약성**: 아마존 페이지 HTML 구조 변경 시 스크래핑 실패 가능 → 정기적인 셀렉터 점검 필요.
- **아마존 카테고리 특정 어려움**: 마데카 크림 등 제품이 여러 카테고리에 걸쳐 있을 경우 BSR 비교 기준이 흔들릴 수 있음 → 추적 제품/카테고리를 명확히 고정.
- **Gemini grounding 응답 변동성**: 동일 질의라도 검색 결과 구성에 따라 매주 응답 형식/수치가 요동칠 수 있으므로, 프롬프트에 출력 스키마를 엄격히 지정하고 파싱 실패 시 재시도 로직 필요.

## 10. 향후 확장 아이디어

- 일본 큐텐(Qoo10) 채널도 유사 구조로 추가해 미국·일본 동시 비교 대시보드로 확장.
- 아마존 리뷰 텍스트를 Gemini로 감성분석하여 "호감도 점수" 산출.
- 동사 주가/컨센서스(에프앤가이드) 데이터와 교차해 "SNS 확산도 vs 주가 반응" 상관관계 뷰 추가.
