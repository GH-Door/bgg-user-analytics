<div align="center">

<img src="assets/logo.png" width="280" alt="BoardGameGeek logo">

<h1>🎲 BGG User Analytics</h1>

<p>
  <strong>BoardGameGeek(BGG) 유저 행동 데이터로 신규 유입 정체의 원인이 되는 이탈 지점을 규명한 분석 프로젝트</strong><br>
  Pipeline: BGG XML API 수집 → BigQuery 3계층 적재(raw/staging/mart) → SQL 마트 → 퍼널·세그먼트·가설 검증
</p>

<p>
  <img src="https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square">
  <img src="https://img.shields.io/badge/Python%203.11%2B-3776AB?style=flat-square&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/BigQuery-4285F4?style=flat-square&logo=googlebigquery&logoColor=white">
  <img src="https://img.shields.io/badge/pandas-150458?style=flat-square&logo=pandas&logoColor=white">
  <img src="https://img.shields.io/badge/SciPy-8CAAE6?style=flat-square&logo=scipy&logoColor=white">
  <img src="https://img.shields.io/badge/statsmodels-white?style=flat-square">
  <img src="https://img.shields.io/badge/scikit--learn-F7931E?style=flat-square&logo=scikitlearn&logoColor=white">
</p>

</div>

## Overview

보드게임 시장은 매출 규모로는 성장 중이지만 신규 유저 유입은 정체돼 있다. 업계는 원인을 "게임이 어려워서 초보자가 못 버틴다"와 "사놓고 안 하는 백로그 현상" 두 가지로 진단하지만, 실제 유저 행동 데이터로 검증된 적은 없다. 이 프로젝트는 BGG 유저 3,000명의 소유·평가·플레이 데이터를 직접 수집해 어디서 얼마나 이탈하는지, 그 이탈이 어떤 유저 특성과 함께 움직이는지, 시간이 지나도 그 구분이 유지되는지를 순서대로 검증한다.

**주요 성과:**
- 퍼널 최대 손실 구간을 **보유 → 첫 플레이 기록(-32.5%p, 956명)** 으로 특정
- 보유 게임 수 단독 세그먼트의 한계를 규명하고 **보유 게임 수 × 활용도 2×2**로 5개 세그먼트를 정의, 비지도 군집화와 교차 검증(일치도 **0.29**, 느슨하게 일치)
- 가설 3개 검정: H1 채택(상관 **-0.81**), H2 부분 채택, H3 채택(**85.5% → 47.0%**)
- **"위험군은 수집가형이 아니라 저관여형"** 이라는 통념 반전 발견(H2)
- 결측 마커로 위장한 `0` 값을 컬럼 5개에서 진단, `averageweight=0`(**31.6%**) 제외 시 복잡도-평점 상관 **0.28 → 0.41**로 정정

| 항목 | 내용 |
|:-----|:-----|
| **📅 Date** | 2026.08.13 ~ 2026.09.09 |
| **👥 Type** | 개인 프로젝트(멋쟁이사자처럼 로켓단 25기 인턴십) |
| **🎯 Goal** | 어디서 유저를 놓치는지 숫자로 짚고, 그 지점에 뭘 하면 좋을지 근거를 남긴다 |
| **🔧 Tech Stack** | Python, BigQuery(SQL), pandas, scipy, statsmodels(로지스틱 회귀), scikit-learn(K-means), Jupyter Notebook |
| **📊 Dataset** | [BGG XML API v2](https://boardgamegeek.com/wiki/page/BGG_XML_API2) 직접 수집(user / collection / thing / plays), 유저 3,000명 · 게임 85,442개 |

BigQuery를 선택한 이유는 채용 공고에서 자주 요구되는 클라우드 데이터 웨어하우스·SQL 역량을 직접 보여주고 싶었고, 100만 행 이상 규모의 데이터를 다루기에도 실제로 적합했기 때문이다.

전체 분석은 `jupyter/`의 [01.EDA](jupyter/01.EDA.ipynb) → [02.Funnel](jupyter/02.Funnel_Retention.ipynb) → [03.Segment](jupyter/03.Segment_Wishlist.ipynb) → [04.Trend](jupyter/04.Trend.ipynb) 순으로 읽는다.

---

## 📊 Results

**퍼널 3단계**: 보유 게임이 있는 2,944명을 대상으로 다음 단계 진행 여부를 실측

| 단계 | 인원 | 직전 대비 |
|---|---:|---:|
| 1. 보유 게임 있음 | 2,944명 | 전체의 98.1% |
| 2. 플레이 기록 있음 | 1,988명 | **-32.5%p (최대 손실)** |
| 3. 반복 플레이 기록 있음 | 1,850명 | -6.9%p |

<div align="center">
<img src="assets/funnel_stages.png" width="90%" alt="퍼널 3단계 및 Core User 세그먼트">
</div>

**보유 게임 수 × 활용도 2×2 세그먼트**: 보유 게임 수만으로는 "많이 갖고 많이 쓰는 유저"와 "많이 갖고 안 쓰는 유저"를 구분할 수 없다는 것이 [Funnel 분석](jupyter/02.Funnel_Retention.ipynb)에서 확인되어, 활용도(`play_game_ratio`) 축을 더해 5개 세그먼트로 분리

| 세그먼트 | 인원 | 특징 |
|---|---:|---|
| 미플레이 | 956명 | 플레이 기록 없음, 평가 참여율 중앙값 82% |
| 몰입형 | 455명 | 보유 게임 많음 · 활용도 높음 |
| 수집가형 | 539명 | 보유 게임 많음 · 활용도 낮음 |
| 집중형 | 539명 | 보유 게임 적음 · 활용도 높음 |
| 저관여형 | 455명 | 보유 게임 적음 · 활용도 낮음, 로그인 경과일 가장 김 |

<div align="center">
<img src="assets/segment_2x2.png" width="70%" alt="보유 게임 수 × 활용도 2x2 세그먼트 산점도">
</div>

---

## 🔬 Analysis

- **[01.EDA](jupyter/01.EDA.ipynb)**
    - 유저 플레이량 지니계수 0.78, 게임 소유량 지니계수 0.80으로 상위 10% 유저가 전체 플레이량의 59.3%를 차지하는 것으로 확인
        - 활동량이 소수에 극단적으로 쏠려 있어, 평균만으로는 유저를 설명하기 어렵다는 것을 시사
    - `user_item` 중복 13,861쌍을 dedup 규칙으로 정리(1,309,380 → 1,295,519행)
    - 평가 참여율은 최상위 분위의 플레이 비율이 오히려 41.4%로 최저인 비단조 패턴으로 확인
        - 퍼널 단계가 아닌 별도 engagement 축으로 분리
    - 게임 변수 14개 간 스피어만 상관을 전수 확인
        - 인기도 계열(평가자 수·소유자 수·위시 수)은 서로 0.82~0.92로 강하게 묶이고, 베이지안 평점과도 0.75~0.81로 연결되는 것으로 확인
        - 복잡도는 플레이타임(0.66)·권장연령(0.54)과는 강하게, 평점과는 0.41~0.54 수준으로 약하게 연결되는 것으로 확인
        - 이 구조는 이후 [02.Funnel](jupyter/02.Funnel_Retention.ipynb)에서 "인기도가 복잡도보다 강한 신호"로 나온 결과의 배경으로 연결

  <div align="center">
  <img src="assets/lorenz_curve.png" width="60%" alt="활동량·소유량 집중도 로렌츠 곡선">
  </div>
  <div align="center">
  <img src="assets/correlation_heatmap.png" width="80%" alt="게임 변수 간 상관관계 히트맵">
  </div>

- **[02.Funnel](jupyter/02.Funnel_Retention.ipynb)**
    - 퍼널 전환과 연관된 후보 변수를 효과 크기로 비교한 결과, 보유 게임 수(0.43, 중간~큰 효과) > 평가 참여율(0.29, 작음~중간) ≈ 로그인 경과일(0.28, 작음~중간) > 가입 경과연수(0.25, 작음~중간) 순으로 확인
    - 로지스틱 회귀로 네 변수를 동시에 통제해도 전부 유의, 다만 네 변수를 합친 모델의 설명력 자체는 크지 않음(약 12% 수준)
        - 보유 게임 수(log)의 오즈비 1.60으로 가장 크게 확인, 보유 게임이 늘수록 플레이 기록 확률도 함께 상승
        - 평가 참여율의 오즈비는 0.52로 확인 → 다른 조건이 같을 때 평가만 열심히 하는 유저일수록 오히려 플레이 기록 확률이 낮다는 것을 시사, [01.EDA](jupyter/01.EDA.ipynb)의 비단조 패턴과 같은 방향
        - 다만 단일 변수만으로 "누가 전환하는가"를 설명하기는 어렵다는 것을 시사
    - 게임 축에서는 인기도(연관도 0.22)가 복잡도(0.13)보다 강한 신호로 확인
        - 다만 둘 다 약한 수준의 연관이라, 인기도가 상대적으로 조금 더 뚜렷하다는 정도로 해석

  <div align="center">
  <img src="assets/odds_ratio.png" width="65%" alt="퍼널 전환 로지스틱 회귀 오즈비">
  </div>

- **[03.Segment](jupyter/03.Segment_Wishlist.ipynb)**
    - 보유 게임이 많을수록 "1회 이상 했다"는 이진 전환은 쉽지만, 소유 대비 실제 플레이 비율(`play_game_ratio`)은 오히려 낮은 것으로 확인(스피어만 -0.13)
    - 위시리스트 사용 비율은 몰입형·수집가형이 79%대로 가장 높고, 미플레이가 46%로 가장 낮은 것으로 확인
    - 위시 → 실제 소유·기록 전환율은 전 세그먼트 1% 안팎으로 낮게 확인
        - 몰입형이 상대적으로 높지만(다른 유형의 2~4배 수준) 절대 수준 자체는 낮음
        - 위시 우선순위(`wishlistpriority`)별로 나눠도 일관된 차이는 나타나지 않는 것으로 확인
        - 위시리스트에 담는 행위를 이후 소유·플레이의 예고 지표로 보기는 어렵다는 것을 시사

  <div align="center">
  <img src="assets/wishlist_conversion.png" width="90%" alt="세그먼트별 위시리스트 보유 비율과 전환율">
  </div>

- **[04.Trend](jupyter/04.Trend.ipynb)**
    - 스냅샷 기반 세그먼트가 시간이 지나도 유지되는지, 반복 플레이가 실제 지속 참여를 예측하는지 가설로 검증(상세 내용과 시각화는 아래 "가설 검증" 참고)

---

## 🧪 가설 검증

EDA·Funnel·Segment 세 노트북이 스냅샷 데이터만으로 남긴 미해결 질문 세 가지를, [04.Trend](jupyter/04.Trend.ipynb)에서 실제 플레이 로그(`plays_sample` 1,065명 중 실로그 730명)로 가설 검증.

| 가설 | 검정 결과 | 판정 |
|---|---|:---:|
| H1. 반복 플레이(스냅샷)가 실제 지속 참여를 예측하는가 | 반복 플레이 있음 647명은 활동 연수 중앙값 8년·2026년까지 활동, 없음 82명은 1년·마지막 활동 7년 전(상관 -0.81) | 채택 |
| H2. 세그먼트가 시간이 지나도 유지되는 구분인가 | 몰입형·수집가형·집중형은 최근성 중앙값 0년, 저관여형만 마지막 활동 4~5년 전. K-means 활동축과 실제 최근성 상관 0.49 | 부분 채택 |
| H3. 최근 가입 코호트일수록 실제 참여에 못 이르는가 | 실제 플레이 로그 보유율 ~2005년 85.5% → 2021년 이후 47.0%(코호트당 150~230명, 방향성 수준) | 채택(방향성) |

**H1. 반복 플레이가 실제 지속 참여를 예측하는가**
- 반복 플레이 기록이 있는 647명은 실제 활동 연수 중앙값 8년, 2026년까지 활동이 이어지는 것으로 확인
- 반복 플레이 기록이 없는 82명은 활동 연수 중앙값 1년, 마지막 활동은 7년 전에 멈춘 것으로 확인
- 두 집단 차이는 상관 -0.81(매우 큰 효과크기)로 확인
    - 스냅샷 지표 하나만으로도 실제 장기 지속성을 상당 부분 예측할 수 있다는 것을 시사

<div align="center">
<img src="assets/h1_repeat_play.png" width="55%" alt="반복 플레이 여부별 실제 활동 연수">
</div>

**H2. 세그먼트가 시간이 지나도 유지되는 구분인가**
- 몰입형·수집가형·집중형은 마지막 활동까지 경과 중앙값 0년, 활동 span 8~13년으로 확인
- 저관여형만 마지막 활동 4~5년 전, 활동 span 1년으로 확인
    - 시간축에서 뚜렷하게 갈라지는 집단은 저관여형뿐이라는 것을 시사
- 비지도 군집화(K-means)의 활동축과 실제 최근성 상관 0.49(중간 수준)로 교차 확인

<div align="center">
<img src="assets/h2_segment_span.png" width="90%" alt="세그먼트별 마지막 활동 경과와 활동 span">
</div>

- H2의 핵심은 반전: 위험 신호는 보유 게임이 많은데 안 쓰는 수집가형이 아니라, 적게 갖고도 몇 년째 안 돌아온 저관여형에서 확인
    - 보유 게임 수 하나로 세그먼트를 정의했다면 놓쳤을 결과

**H3. 최근 가입 코호트일수록 실제 참여에 못 이르는가**
- 실제 플레이 로그 보유율이 ~2005년 가입 코호트 85.5%에서 2021년 이후 코호트 47.0%로 하락하는 것으로 확인
- 코호트당 표본이 150~230명 수준이라 방향성 수준으로 해석

<div align="center">
<img src="assets/cohort_retention.png" width="65%" alt="가입연도 코호트별 실제 플레이 로그 보유율">
</div>

---

## 🧭 핵심 인사이트 → 액션

EDA부터 가설 검증까지의 결과를 프로젝트 목표(신규 유입 정체 대응)로 되돌려 정리.

- 가장 큰 손실은 게임을 산 뒤 처음 플레이 기록을 남기는 순간에서 발생(Funnel)
    - 이 첫 기록의 문턱은 고정돼 있지 않고, 최근 가입 유저일수록 못 넘는 비율이 더 높음(H3)
- 반복 플레이라는 스냅샷 지표 하나가 실제 장기 지속성과 강하게 연결(H1)
    - 스냅샷 기반 판단이 근거 없는 것은 아니었다는 것을 시사
- "많이 가진 유저"가 "잘 쓰는 유저"는 아님
    - 비율 지표·비지도 군집화·실제 시간축까지 세 가지 독립적인 근거가 같은 방향을 가리킴(H2)
- 진짜 위험 신호는 보유 게임이 많은데 안 쓰는 사람이 아니라, 적게 갖고도 몇 년째 안 돌아온 사람(H2 반전)
- 평가만 하고 기록은 안 하는 유저층이 실재하고, 위시리스트는 구매 예고가 아니라 관심 신호에 가까움(Segment)

위 인사이트를 근거로 도출한 제안 액션은 아래와 같다. 인과가 증명된 것이 아니라 관찰된 패턴에서 나온 가설이므로, 각 행에 실행 후 확인할 검증 방법을 함께 남긴다.

| 타깃 | 근거 | 제안 액션 | 검증 방법(제안) |
|---|---|---|---|
| 최근 가입 코호트(2021년 이후) | H3 | 온보딩에서 "첫 플레이 기록" 유도를 더 이른 시점에 배치 | 코호트별 실로그 보유율 추이 모니터링 |
| 보유 → 첫 기록 구간(전체 유저) | Funnel 최대 감소 구간(-32.5%p) | 소유 등록 직후 "플레이 기록 남기기" 넛지 | A/B 테스트로 기록 전환율 비교 |
| 저관여형(실제 재참여 단절) | H2 | 재활성화 캠페인 우선 타깃 | 캠페인 전후 재활동율 |
| 수집가형(백로그는 많지만 지속 활동) | H2 반전 발견 | "위험군"이 아닌 "백로그 관리 지원" 대상으로 재포지셔닝 | 추천 클릭률·후속 기록률 |
| 미플레이/평가만 하는 유저 | [Segment 분석](jupyter/03.Segment_Wishlist.ipynb) 2-0 | 평가 직후 "플레이 기록도 남겨보세요" 유도 | 기록 전환율 |
| 집중형(위시-실제 복잡도 갭 최대) | [Segment 분석](jupyter/03.Segment_Wishlist.ipynb) 4-1 | 위시리스트 기반 유사 난이도 신작 추천 | 추천 후 구매·기록 전환율 |

- 이 프로젝트는 기존 유저(이미 가입하고 보유 게임을 가진 사람)의 행동만 다룸
    - 신규 유입 자체를 늘리는 액션은 이 데이터로 증명할 수 없고, 위 제안은 기존 유저의 유지·활성화 패턴을 신규 유저 온보딩 설계에 참고할 수 있는 가설로 남김

---

## 📐 표본 설계와 재수집

- 원래 2024년 팀 프로젝트에서 물려받은 `user_list.csv`(194,643명)를 표집틀로 사용
    - 가입연도 분포를 확인하는 과정에서 2016~2021년에 표본이 집중되고 2025~2026년 신규 가입자가 구조적으로 0명인 시간 절단 편향을 발견
- `frame.py`로 BGG `thing` API의 `ratingcomments`를 이용한 독립 표집틀(`user_list.csv`와 무관)을 새로 구축
    - 검증표본 600명으로 두 표집틀의 가입연도 분포 차이를 실측 확인(`docs/sampling_design.md`) → 편향이 실제로 존재함을 확인
- 기존 명단을 부분 보정하지 않고, 새 표집틀로 3,000명(`main_frame.py`)을 전면 재수집
    - 표본 크기는 모비율 추정 공식(신뢰수준 95%, 허용오차 ±2%p)으로 산정한 목표 유효 표본 2,400명에 스크리닝 손실 버퍼를 더해 3,000명으로 결정
- 편향 검증 이전의 구버전 분석은 보존하지 않고 폐기, 이 프로젝트의 분석은 새 표집틀로 재수집한 데이터만 사용

---

## 🗄️ Data Pipeline

```
data/*.csv (원본, BGG API 그대로)
   ↓ scripts/load_bigquery.py
bgg_raw     : 원본을 그대로 옮김. 전부 STRING.
   ↓ sql/staging/preprocessing.sql (SAFE_CAST, NULLIF, CASE WHEN)
bgg_staging : 타입 캐스팅 + 결측 마커 정규화. 분석 가능한 상태.
   ↓ sql/marts/*.sql (GROUP BY, 윈도우 함수)
bgg_mart    : 퍼널·코호트·세그먼트 등 분석 결과. 노트북이 조회하는 곳.
```

- raw를 전부 STRING으로 받는 이유: `rank` 컬럼처럼 숫자 컬럼에 `"Not Ranked"` 같은 문자열이 섞여 있어, 자동 타입 추론에 맡기면 컬럼 전체가 조용히 잘못된 타입으로 잡힐 위험 존재
    - 타입 변환은 항상 SQL에서 명시적으로 수행

**데이터 규모** (BigQuery `INFORMATION_SCHEMA` 실측 기준)

| 테이블 | 행 수 | 내용 |
|---|---:|---|
| `user_info` | 3,000 | 유저 기본정보(user API) |
| `user_item` | 1,309,380 | 유저×게임 보유 게임(collection API, own=1) |
| `user_wishlist` | 160,565 | 유저×게임 개인 위시리스트(wishlist=1) |
| `user_play` | 1,272,008 | 실제 플레이 로그(plays API) |
| `item_details` / `item_stats` | 각 85,442 | 게임 상세정보 · 통계(thing API) |
| `item_link` | 1,240,967 | 카테고리·메커닉·디자이너·퍼블리셔(long 포맷) |

컬럼 단위 스키마와 각 컬럼의 의미는 [`docs/data_model.md`](docs/data_model.md)에 정리했다.

---

## 📁 Project Structure

```
bgg/
├── README.md                    # 이 문서
├── scripts/                      # 실행 진입점
│   ├── collect/                   #   수집 드라이버(API별 1:1 대응)
│   │   ├── frame.py                #     1. 신규 표집틀 구축(thing ratingcomments)
│   │   ├── verify_frame.py         #     2. 표집틀 검증(600명, 편향 실측)
│   │   ├── main_frame.py           #     3. 본수집(3,000명, user+collection)
│   │   ├── thing.py                #     4. 아이템 상세(배치 20개)
│   │   └── wishlist.py             #     5. 위시리스트 보강 수집(wishlist=1)
│   ├── collect_phase4_plays.py    #   6. 표본 플레이로그(plays API)
│   ├── load_bigquery.py           #   7. CSV → BigQuery raw 적재
│   ├── load_fallback_2024.py      #   2024 폴백 데이터 적재(보존용)
│   └── _common.py                 #   시작시각 영속화 + 로깅 설정 공용 유틸
├── src/
│   ├── config.py                  # 경로 공용 상수(DATA_DIR/LOGS_DIR)
│   ├── collectors/                 # "어떻게 수집할지"(HTTP 호출·파싱·체크포인트)
│   │   ├── bgg_client.py            #   인증/레이트리밋/재시도 공통 HTTP 계층
│   │   ├── checkpoint.py            #   체크포인트 파일 I/O + 진행률/ETA 로깅
│   │   ├── filters.py               #   수집 대상 국가/가입연도 필터(선택)
│   │   ├── frame_collector.py / user_collector.py / collection_collector.py / thing_collector.py / plays_collector.py
│   │   ├── fixtures/                #   파서 회귀 테스트용 실제 BGG 응답 샘플
│   │   ├── test_bgg_client.py       #   HTTP 계층 셀프 체크
│   │   └── test_parsers.py          #   파싱 로직 회귀 테스트
│   ├── loaders/
│   │   ├── bigquery_loader.py       #   CSV → BigQuery 적재 공용 유틸
│   │   └── fallback_adapter.py      #   2024 스키마 → 신규 스키마 변환(보존용)
│   ├── preprocess/
│   │   └── eda.py                   # 결측·이상치·정규성 요약 EDA 헬퍼
│   └── utils/
│       └── setup_font.py            # matplotlib 한글 폰트 설정
├── sql/
│   ├── staging/                   # raw → 정제/정규화
│   │   ├── preprocessing.sql
│   │   └── data_quality_checks.sql
│   └── marts/                      # 퍼널 · 코호트 · 세그먼트 · 트렌드
│       ├── funnel.sql / cohort.sql / segmentation.sql / trend.sql
├── jupyter/                        # 분석 4편(EDA → Funnel → Segment → Trend)
├── docs/                           # 데이터 모델, 품질 체크, 표본 설계, 데이터셋 비교
├── assets/                         # README용 차트·로고 이미지
└── data/                           # 수집·적재 산출물(재현 가능한 것만, git 제외)
```

- `scripts/`(무엇을 할지, 얇은 오케스트레이션)와 `src/collectors/`(어떻게 할지, 재사용 가능한 파싱/HTTP/체크포인트 로직) 분리
    - `src/collectors/`의 파싱 함수는 `test_parsers.py`가 API 호출 없이 직접 단위 테스트, `src/loaders/`도 이 모듈들을 그대로 import
    - 로직이 스크립트 안에 갇혀 있으면 두 재사용 모두 불가능

### 실행 순서 (7단계, 순서대로)

```bash
uv run python -m scripts.collect.frame          # 1. 신규 표집틀 구축
uv run python -m scripts.collect.verify_frame    # 2. 표집틀 검증(600명)
uv run python -m scripts.collect.main_frame      # 3. 본수집(3,000명)
uv run python -m scripts.collect.thing           # 4. 아이템 상세(배치 20개)
uv run python -m scripts.collect.wishlist        # 5. 위시리스트 보강 수집
uv run python -m scripts.collect_phase4_plays    # 6. 표본 플레이로그
uv run python -m scripts.load_bigquery           # 7. BigQuery raw 적재
```

각 단계는 체크포인트 기반이라 중단 후 재실행해도 이어서 진행된다. 국가/가입연도로 수집 대상을 제한하고 싶다면 저장소 루트의 `config.yaml`(`collect.countries`/`min_year`/`max_year`)을 채운다.

---

## 🚀 Quick Start

```bash
# 1. 의존성 설치 (uv가 .venv 생성 + Python 버전까지 알아서 관리)
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv 없는 경우
uv sync

# 2. 환경변수 (BGG API 토큰, GCP 프로젝트 ID)
cp .env.example .env

# 3. 셀프 체크 (네트워크 불필요, 저장소 루트에서 실행)
uv run python -m src.collectors.test_bgg_client
uv run python -m src.collectors.test_parsers
```

BGG API 토큰은 [BGG XML API 안내](https://boardgamegeek.com/using_the_xml_api)에서 등록 후 승인 시 발급된다. GCP는 `gcloud auth application-default login`으로 인증한다(서비스 계정 키를 쓰는 경우 `.env.example` 참고). 전체 실행 순서는 위 "실행 순서" 참고.

---

## 💡 Lesson and Learned

- 0으로 채워진 값을 결측으로 의심하지 않고 그대로 쓰면 통계가 조용히 왜곡되는 것으로 확인
    - `averageweight=0`을 걸러내지 않으면 "가벼운 게임" 비율이 21.5%p 차이 나고, 복잡도-평점 상관도 0.28로 과소평가됨
    - 값이 존재한다고 해서 전부 유효한 값은 아니라는 것을 시사
- 데이터가 수십만 행이면 아주 작은 차이도 p-value가 거의 항상 "유의미하다"는 판정을 내리기 쉬운 것으로 확인
    - 유의미하다는 것과 그 차이가 실제로 큰 차이라는 것은 다른 이야기라, 효과 크기 등으로 크기까지 따로 확인해야 한다는 것을 시사
- 표집틀 편향은 수집을 마친 뒤에야 알아채기 쉬움
    - 가입연도 분포를 초반에 확인해 시간 절단 편향을 스스로 발견
    - 부분 보정 대신 독립 검증표본으로 실측 확인 후 전면 재수집 → 이번 프로젝트에서 가장 큰 설계 교훈

---

## 🪞 회고

- 실제 로그인·세션 로그가 없어, 퍼널·코호트 분석을 소유·기록 여부로 근사할 수밖에 없었던 점이 아쉬움
    - BGG API가 제공하는 것은 "언제 소유했고 언제 기록을 남겼는지"까지이고, "언제 로그인해서 무엇을 봤는지"의 세션 로그는 제공하지 않음
    - 실제 세션 로그가 있었다면 퍼널·코호트를 더 정교한 시점 기준으로 다시 볼 수 있었을 것
- 이 프로젝트는 이미 가입한 기존 유저의 행동만 다뤄, 애초에 신규 유저가 왜 유입되지 않는지는 확인하지 못함
    - 유입 자체를 다루려면 비가입자 대상 데이터나 마케팅 채널 데이터처럼 이 프로젝트 범위 밖의 데이터가 필요

---

## 🙏 Acknowledgements

이 프로젝트는 [BoardGameGeek](https://boardgamegeek.com) XML API로 수집한 데이터를 사용했다. **Powered by BoardGameGeek.**
