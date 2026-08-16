<div align="center">

<h1>🎲 BGG User Analytics</h1>

<p>
  <strong>BoardGameGeek(BGG) 유저 행동 패턴 및 게임 선호도 분석</strong><br>
  Pipeline: BGG XML API 수집 → BigQuery 적재 → SQL 기반 퍼널/코호트/가설 검증 → Looker Studio 대시보드
</p>

<p>
  <img src="https://img.shields.io/badge/Status-In%20Progress-yellow?style=flat-square">
  <img src="https://img.shields.io/badge/Python%203.9%2B-3776AB?style=flat-square&logo=python&logoColor=white">
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

질문별 지표·산출 위치·의사결정 액션 매핑은 [PLAN.md §2](PLAN.md#2-분석-질문--지표--액션-매핑표) 참고.

---

## 📁 Project Structure

```
bgg/
├── README.md              # 이 문서
├── PLAN.md                # 상세 설계 · 수집 결정 로그 · 지표 정의 · 주차별 TODO
├── collectors/             # BGG XML API 수집 모듈
│   ├── bgg_client.py       # 인증/레이트리밋/재시도 공통 HTTP 계층
│   ├── user_collector.py
│   ├── collection_collector.py
│   ├── thing_collector.py
│   └── plays_collector.py  # 실제 플레이 로그 기반 코호트 (신규)
├── loaders/
│   └── bigquery_loader.py  # CSV → BigQuery raw 적재
├── sql/
│   ├── staging/            # raw → 정제/정규화
│   └── marts/               # 퍼널 · 코호트 · 세그먼트 · 트렌드
├── analysis/                # EDA, 가설 검증 노트북
├── docs/                    # 지표 정의서, 데이터 사전, 품질 리포트
├── dashboard/                # Looker Studio 연동 메모
└── data/                     # 로컬 캐시 + 체크포인트 (git 제외)
```

---

## 🚀 Quick Start

```bash
# 1. 가상환경 + 의존성
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. 환경변수 (BGG API 토큰, GCP 프로젝트 ID)
cp .env.example .env

# 3. 셀프 체크 (네트워크 불필요)
python3 collectors/test_bgg_client.py
```

BGG API 토큰 발급 방법, GCP 인증, 전체 실행 순서는 [PLAN.md §12](PLAN.md#12-실행-방법) 참고.

---

## 📄 상세 문서

수집 설계 결정 로그(BGG API 인증 정책 대응, 기존 코드 결함 수정 내역), 데이터 모델, 지표 정의서, 알려진 한계, 주차별 TODO는 **[PLAN.md](PLAN.md)** 에 정리되어 있습니다.
