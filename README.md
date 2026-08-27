<div align="center">

<h1>🎲 BGG User Analytics</h1>

<p>
  <strong>BoardGameGeek(BGG) 유저 행동 패턴 및 게임 선호도 분석</strong><br>
  Pipeline: BGG XML API 수집 → BigQuery 적재 → SQL 기반 퍼널/코호트/가설 검증 → Looker Studio 대시보드
</p>

<p>
  <img src="https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square">
  <img src="https://img.shields.io/badge/Python%203.11%2B-3776AB?style=flat-square&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/BigQuery-4285F4?style=flat-square&logo=googlebigquery&logoColor=white">
  <img src="https://img.shields.io/badge/pandas-150458?style=flat-square&logo=pandas&logoColor=white">
  <img src="https://img.shields.io/badge/SciPy-8CAAE6?style=flat-square&logo=scipy&logoColor=white">
  <img src="https://img.shields.io/badge/Looker%20Studio-4285F4?style=flat-square&logo=looker&logoColor=white">
</p>

</div>

## Overview

BoardGameGeek(BGG)은 세계 최대 보드게임 커뮤니티로, 유저별 소유 현황·평점·플레이 횟수 등 행동 데이터를 API로 공개한다. 이 데이터를 BGG XML API로 직접 수집해 BigQuery에 적재하고, SQL 기반으로 유저 성장 패턴과 게임 선호도 변화를 분석한다.


| 항목 | 내용 |
|:-----|:-----|
| **📅 Date** | 2026.08.13 ~ 2026.09.09 (진행 중) |
| **👥 Type** | 개인 프로젝트 |
| **🎯 Goal** | BGG 유저 행동/선호도 분석 |
| **🔧 Tech Stack** | Python, BigQuery, BigQuery SQL, pandas, scipy, Looker Studio |
| **📊 Dataset** | BGG XML API v2 직접 수집 (user / collection / thing / plays) |

---

## 🎯 분석 질문

1. 유저는 어느 단계(소유→평가→플레이→헤비유저)에서 가장 많이 이탈하는가?
2. 가입 연도가 다른 유저 코호트는 리텐션 양상이 다른가?
3. 위시리스트만 쌓이고 실제로는 플레이되지 않는 게임의 공통 특성은 무엇인가?

질문별 지표·산출 위치·의사결정 액션 매핑은 상세 설계 문서(비공개, 프로젝트 완료 후 공개 예정)에 정리되어 있다.

---

## 📁 Project Structure

```
bgg/
├── README.md                 # 이 문서
├── scripts/                   # 실행 진입점 — "무엇을 수집/적재할지"
│   ├── collect/                #   4단계 수집 드라이버(API별 1:1 대응)
│   │   ├── user.py             #     1단계: user API 스크리닝(표본 추출)
│   │   ├── collection.py       #     2단계: collection API 본수집(own=1)
│   │   └── thing.py            #     3단계: thing API 아이템 상세(배치 20개)
│   ├── collect_phase4_plays.py #   4단계: plays API 표본 플레이로그(리네이밍 예정)
│   ├── _common.py              #   시작시각 영속화 + 로깅 설정 공용 유틸
│   └── load_fallback_2024.py   #   2024 데이터 → BQ 1회성 적재(재수집 완료 후 제거 예정)
├── src/
│   ├── config.py               # 경로 공용 상수(DATA_DIR/LOGS_DIR) + ensure_dirs()
│   ├── collectors/              # "어떻게 수집할지" — HTTP 호출·파싱·체크포인트
│   │   ├── bgg_client.py        #   인증/레이트리밋/재시도 공통 HTTP 계층
│   │   ├── checkpoint.py        #   체크포인트 파일 I/O + 진행률/ETA 로깅
│   │   ├── filters.py           #   수집 대상 국가/가입연도 필터(선택)
│   │   ├── user_collector.py / collection_collector.py / thing_collector.py / plays_collector.py
│   │   ├── fixtures/            #   파서 회귀 테스트용 실제 BGG 응답 샘플
│   │   ├── test_bgg_client.py   #   HTTP 계층 셀프 체크
│   │   └── test_parsers.py      #   파싱 로직 회귀 테스트
│   └── loaders/
│       ├── bigquery_loader.py   #   CSV → BigQuery raw 적재
│       └── fallback_adapter.py  #   2024 스키마 → 신규 스키마 변환(재수집 완료 후 제거 예정)
├── sql/
│   ├── staging/                 # raw → 정제/정규화
│   │   ├── preprocessing.sql
│   │   └── data_quality_checks.sql
│   └── marts/                    # 퍼널 · 코호트 · 세그먼트 · 트렌드(예정)
├── jupyter/                      # EDA, 가설 검증 노트북(예정)
├── docs/                         # 지표 정의서, 표본 설계, 데이터 품질/비교 리포트
└── data/                         # 수집·적재 산출물(재현 가능한 것만, git 제외)
```

`scripts/`(무엇을 할지, 얇은 오케스트레이션)와 `src/collectors/`(어떻게 할지, 재사용 가능한 파싱/HTTP/체크포인트 로직)를 분리한 이유: `src/collectors/`의 파싱 함수는 `test_parsers.py`가 API 호출 없이 직접 단위 테스트하고, `src/loaders/`도 이 모듈들을 그대로 import해서 쓴다 — 로직이 스크립트 안에 갇혀 있으면 둘 다 불가능하다.

### 실행 순서 (4단계, 순서대로)

```bash
uv run python -m scripts.collect.user          # 1. 스크리닝(표본 추출 + user API)
uv run python -m scripts.collect.collection     # 2. 본수집(collection API, own=1)
uv run python -m scripts.collect.thing          # 3. 아이템 상세(thing API, 배치 20개)
uv run python -m scripts.collect_phase4_plays   # 4. 표본 플레이로그(plays API)
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

## 📄 상세 문서

수집 설계 결정 로그(BGG API 인증 정책 대응, 기존 코드 결함 수정 내역), 데이터 모델, 지표 정의서, 알려진 한계, 주차별 TODO는 별도 설계 문서(비공개, 프로젝트 완료 후 공개 예정)에 정리되어 있습니다. 실제 수집 과정에서 겪은 문제와 해결 과정은 `TROUBLESHOOTING.md`(마찬가지로 프로젝트 완료 후 공개)에 기록되어 있습니다.
