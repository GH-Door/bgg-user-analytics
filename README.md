# BGG 유저 행동 패턴 및 게임 선호도 분석

> 멋쟁이사자처럼 로켓단 25기 인턴십 개인 프로젝트 (자유 주제, 하루 3시간, 08/13~09/09)
> 목표: DS/DA/AI Engineer가 섞인 기존 포트폴리오에서 **DA 역량**(지표 정의 · SQL · 데이터 한계 인지 · 인사이트의 의사결정 번역)을 명확히 보여주는 산출물을 만든다.

---

## 0. ⚠️ 시작 전 필수 — BGG API 토큰

**BGG XML API는 2025년 10월경부터 등록 후 발급받는 토큰(Bearer) 없이는 모든 요청이 401 Unauthorized로 막힌다.** 직접 확인한 결과 `xmlapi2`, 구버전 `xmlapi`, `api.geekdo.com` 전부 차단되어 있다. 기존 팀 프로젝트(2024년 7월 수집)는 이 정책 이전이라 무인증으로 가능했던 것뿐이다.

**공식 문서(2025-07-02판, `boardgamegeek.com/using_the_xml_api`)에 승인까지 "a week or more" 걸릴 수 있다고 명시되어 있다.** 즉 1주차(08/13~08/19) 안에 승인이 안 날 수도 있다는 뜻 — 폴백을 "혹시 몰라 준비"가 아니라 **기본 진행 경로**로 취급한다.

→ **오늘 바로 토큰 신청**(비상업용 애플리케이션 등록). 발급 방법은 이 문서 맨 아래 [API 토큰 발급 방법](#api-토큰-발급-방법) 참고. **신청 직후부터 승인 여부와 무관하게 2024년 폴백 데이터로 파이프라인·SQL·분석 로직을 먼저 완성**하고, 토큰이 나오는 대로 최신 데이터로 교체 수집한다 — [수집 설계 결정 로그 §1](#1-api-인증-정책-변경-대응) 참고.

---

## 1. 프로젝트 개요

**질문**: 보드게임 유저는 가입 이후 어떻게 성장하고, 어느 지점에서 이탈하며, 성장 단계에 따라 어떤 게임을 선호하게 되는가?

BoardGameGeek(BGG)은 세계 최대 보드게임 커뮤니티로, 유저별 소유 현황·평점·플레이 횟수 등 행동 데이터를 API로 공개한다. 이 데이터를 BigQuery에 적재하고 SQL 기반으로 분석해, 게임 플랫폼/퍼블리셔가 유저 세그먼트별로 어떤 액션을 취해야 하는지 도출한다.

**답하려는 질문 3가지**
1. 유저는 어느 단계(가입→소유→평가→플레이→헤비유저)에서 가장 많이 이탈하는가?
2. 가입 연도가 다른 유저 코호트는 리텐션 양상이 다른가?
3. 위시리스트만 쌓이고 실제로는 플레이되지 않는 게임의 공통 특성은 무엇인가?

---

## 2. 분석 질문 → 지표 → 액션 매핑표

| 분석 질문 | 핵심 지표 | 산출 위치 | 의사결정 액션 |
|---|---|---|---|
| 어디서 이탈이 큰가? | 단계별 전환율/이탈률 (Engagement Funnel) | `sql/marts/funnel.sql` | 이탈 최대 구간 직전에 온보딩 개입 |
| 코호트별 리텐션 차이 | 가입월 코호트 × N개월차 잔존율 | `sql/marts/cohort_retention.sql` | 리텐션 낮은 가입 시기의 온보딩 플로우 재설계 |
| 헤비유저는 뭘 좋아하나 | 세그먼트별 평균 `averageweight`, 선호 카테고리 | `sql/marts/segmentation.sql` | 세그먼트별 추천 규칙/마케팅 문구 차별화 |
| 시장 트렌드 변화 | 출시연도별 카테고리 비중, 평균 복잡도 추이 | `sql/marts/trend.sql` | 신작 기획 방향 제안 |
| 위시만 쌓이는 게임 특징 | Play-to-Wish Ratio vs 복잡도/플레이타임 상관 | `sql/marts/hypothesis.sql` | 난이도 완화판/입문 가이드 제작 제안 |

---

## 3. 데이터 수집 설계

| 데이터셋 | 엔드포인트 | 주요 피처 | 비고 |
|---|---|---|---|
| `user_info` | `GET /user?name={id}` | `yearregistered, lastlogin, country, stateorprovince, traderating` | |
| `user_item` | `GET /collection?username={id}&own=1&stats=1` | `objectid, user_rating, numplays, comment` | `own=1` 유지 → §2 결정 로그 참고 |
| `item_info` | 위 collection 응답에 동봉 | `numowned, average, bayesaverage, rank, min/maxplayers, playingtime` | 추가 호출 없이 얻음 |
| `item_details` | `GET /thing?id=...&stats=1` (배치) | `minage, description, avg_weights` | id 콤마 구분 배치 호출 |
| `item_stats` **(신규)** | 위 thing 응답 `statistics/ratings` | `wishing, wanting, trading, owned, numcomments, numweights, averageweight` | 기획서의 numwishing 포함, 같은 호출로 공짜로 확보 |
| `item_link` **(신규, 정규화)** | 위 thing 응답 `link` 태그 | `(objectid, link_type, ref_id, value)` long 포맷 | category/mechanic/family/designer/publisher 전부 여기로. 튜플 문자열 저장 안 함 |
| `item_rank` **(신규, 정규화)** | 위 thing 응답 `ranks/rank` | `(objectid, rank_type, friendlyname, value, bayesaverage)` | subtype별 순위를 행으로 분리 |
| `user_play` **(신규)** | `GET /plays?username={id}&page={n}` | `objectid, play_date, quantity, length, incomplete` | 샘플 유저 한정, §3 결정 로그 참고 |

**공통 수집 규칙**
- 모든 요청에 `Authorization: Bearer {BGG_API_TOKEN}` 헤더
- 요청 간 최소 간격 강제 (기본 5초, §0 토큰 발급 후 공식 rate limit로 교체)
- `202 Accepted` = 큐잉 중 → 지수 백오프 재시도 (성공으로 취급하지 않음)
- `429` = `Retry-After` 헤더 존중
- `401` = 즉시 중단 (토큰 문제는 재시도 무의미)
- 완료한 `user_id`를 체크포인트 파일에 append → 중단 후 재실행 시 자동 재개

---

## 4. 수집 설계 결정 로그

프로젝트 진행 중 내린 판단과 그 근거를 남긴다. **결과물보다 이 판단 과정이 DA 역량을 더 잘 보여준다고 판단해 별도 섹션으로 뺐다.**

### 1) API 인증 정책 변경 대응
착수 시점(2026-08-16)에 BGG XML API 전 엔드포인트를 직접 호출해보니 전부 401이었다. 원인을 조사한 결과 BGG가 2025년 10월경부터 등록+토큰 인증을 의무화했음을 확인했다([공식 안내](https://boardgamegeek.com/using_the_xml_api), [정책 공지 스레드](https://boardgamegeek.com/thread/3492262/registration-and-authorization-coming-to-the-xml-a)). 기존 팀 프로젝트(2024-07 수집)는 이 이전이라 무인증으로 동작했던 것.

08/16 계정 가입 후 애플리케이션 등록을 진행하며 공식 문서 원문을 직접 확인한 결과, 승인까지 **"a week or more"** 가 걸릴 수 있다고 명시되어 있음을 확인했다(등록은 `https://boardgamegeek.com/applications`에서 진행, Non-commercial 라이선스로 신청). 1주차 전체(08/13~08/19)를 승인 대기로 날릴 수 있는 리스크.
- **대응**: 토큰 신청은 08/16 즉시 진행. 승인 대기를 "리스크 발생 시 폴백"이 아니라 **기본 진행 순서**로 격상 — BigQuery 셋업, 2024년 기존 데이터 적재, `sql/staging`·`sql/marts` 쿼리, 지표 정의서까지를 **토큰 없이 2024년 데이터로 먼저 완성**한다. 토큰이 나오는 시점에 맞춰 최신 데이터로 재수집·교체 적재만 하면 되도록 파이프라인을 데이터 소스에 독립적으로 설계.

### 2) `own=1` 유지와 퍼널 재정의
기존 코드와 동일하게 `own=1`을 유지하기로 했다(요청 수는 동일하고 응답 크기만 달라지는 옵션이라 `own=0`으로도 바꿀 수 있었으나, 수집 범위를 좁게 유지하는 쪽을 택함). 이 경우 **소유 게임이 없는 유저는 애초에 응답에 아이템이 없으므로, "가입→소유" 전환율은 이 데이터로 측정할 수 없다** — 수집 시점에 이미 필터링되어 있기 때문(생존 편향).
- **대응**: 퍼널을 "소유 유저 → 평가자 → 플레이어 → 헤비유저" **4단계**로 재정의(기획서의 5단계에서 1단계 제거). `collection_collector.py`에서는 `own`을 함수 인자로 노출해두어, 추후 "가입→소유" 전환율이 꼭 필요해지면 재수집 없이 파라미터만 바꿔 재수집할 수 있게 함.

### 3) plays API 추가와 샘플 설계
기획서의 코호트 분석은 "클릭스트림이 없어 `lastlogin` 기반 Proxy로 근사한다"는 한계를 스스로 인정하고 있었다. BGG `plays` API는 유저가 기록한 개별 플레이의 **실제 날짜**를 제공하므로, 이를 확보하면 Proxy가 아닌 **진짜 월별 코호트 리텐션**을 계산할 수 있다.
- **비용**: 유저 1명당 페이지네이션 호출이 필요해 전수 수집은 비현실적(요청 간격 5초 × 유저 수).
- **대응**: 가입연도별 층화추출로 샘플 유저(예: 2,000~5,000명)만 수집. 표본 크기와 층화 비율은 실제 `user_info` 수집 후 가입연도 분포를 보고 확정 — 표본 설계 근거를 `docs/`에 별도 기록 예정.
- 기존 Proxy 코호트(`lastlogin` 기반)는 **버리지 않고 병행 산출**해 "Proxy vs 실측"을 비교하는 것 자체를 분석 콘텐츠로 삼는다.

### 4) 기존 수집 코드의 결함과 수정
기존 팀 프로젝트(`크롤링 코드(주석확인해주세욥).ipynb`)를 검토해 다음 결함을 찾았고, 새 코드(`collectors/`)에서 전부 수정했다.

| # | 결함 | 문제 | 수정 |
|---|---|---|---|
| 1 | `own=1` 필터 | 퍼널 2단계 생존 편향 | 위 §2 |
| 2 | 정상 경로에 `sleep` 없음 | 429가 나야만 대기, rate limit 미준수 | `bgg_client.py`에서 모든 요청 전 최소 간격 강제 |
| 3 | 루프 안에서 전체 DataFrame `concat`+`drop_duplicates` | O(n²), 197만 행 규모에서 치명적 | 행을 CSV에 append만, 정규화는 BigQuery SQL에서 |
| 4 | 유저마다 전체 DF `to_csv` 재작성 | O(n²) I/O | 위와 동일 |
| 5 | 광범위한 `except: continue` | 실패 원인 유실 | 예외를 명시적 타입(`BGGAuthError`/`BGGRequestError`)으로 구분, 값을 삼키지 않음 |
| 6 | 수동 `iloc` 인덱스로 재개 | 중단 시 사람이 CSV 열어 인덱스 확인 필요 | 완료 `user_id` 체크포인트 파일로 자동 재개 |
| 7 | 중복 키를 `name`으로 판정 | 동명이품 유실 | `objectid`로 판정 |
| 8 | `BeautifulSoup(..., "lxml")` | XML에 HTML 파서 | `xml.etree.ElementTree`(표준 라이브러리) |
| 9 | `202 Accepted`를 성공으로 취급 | collection API 큐잉 중 응답을 데이터로 오인 | 202는 재시도 대상으로 처리, 최종 200만 파싱 |
| 10 | 인증 헤더 없음 | 2026년 현재 전부 401 | `Authorization: Bearer` 헤더 추가 |

---

## 5. 데이터 모델 (BigQuery)

**3계층**: `bgg_raw`(수집 원본, CSV 그대로) → `bgg_staging`(타입 캐스팅·정규화·결측 처리) → `bgg_mart`(분석 목적 집계 테이블: 퍼널/코호트/세그먼트/트렌드)

raw 테이블은 §3의 8개 테이블 그대로. staging에서 다음을 처리한다.
- `item_info.rank`의 `"Not Ranked"` → NULL 캐스팅
- `item_details.avg_weights` 등 숫자 컬럼 STRING → FLOAT64 캐스팅
- `user_info.yearregistered`(연도) ↔ `user_play.play_date`(날짜) 단위 통일 — 코호트 계산의 전제
- `item_link`를 `link_type`별 뷰(`item_category`, `item_mechanic`, `item_designer`, `item_publisher`)로 분리

파티셔닝: `user_play`는 `play_date` 기준 DATE 파티션(코호트 쿼리가 항상 날짜 범위로 필터링하므로). 클러스터링: `user_item`, `item_link`는 `objectid`로 클러스터링(조인 키).

> 상세 컬럼별 타입/제약은 `docs/data_dictionary.md`에 정리 예정 (2주차 작업, TODO 참고)

---

## 6. BigQuery 적재 전략

- 데이터셋 3개: `bgg_raw`, `bgg_staging`, `bgg_mart` (프로젝트당 무료 한도 내 운영)
- `loaders/bigquery_loader.py` — CSV → raw 테이블. 스키마를 명시적으로 지정(자동추론에 맡기지 않음 — `rank` 컬럼처럼 혼입 문자열이 있는 컬럼이 있어서). `WRITE_TRUNCATE`로 멱등 적재.
- staging/mart는 Python이 아니라 **BigQuery SQL**로 생성 (`sql/staging/*.sql`, `sql/marts/*.sql`) — DA 포트폴리오에서 SQL 비중을 의도적으로 높임.
- 비용 관리: 쿼리 전 `dry_run`으로 스캔 바이트 확인 습관화. 월 1TB 무료 한도 내.

---

## 7. 데이터 품질 체크리스트

수집 직후, staging 이전에 다음을 SQL로 검증하고 결과를 `docs/data_quality.md`에 기록한다.

- [ ] **유일성**: `user_info.user_id`, `item_info.objectid` 중복 없음
- [ ] **참조 무결성**: `user_item.objectid`가 `item_info.objectid`에 전부 존재
- [ ] **값 범위**: `user_rating` 1~10, `averageweight` 1~5, `yearpublished` 1900~2026
- [ ] **결측률**: 컬럼별 NULL 비율 집계 — 특히 `rank`(Not Ranked 다수 예상), `comment`(대부분 결측 예상)
- [ ] **own=1 필터 확인**: `user_item`에 `numowned=0`인 유저가 없는지(있으면 파라미터 실수)

---

## 8. 지표 정의서 (요약 — 상세는 `docs/metrics.md`)

### Engagement Funnel (4단계, §4-2 참고)
| 단계 | 판정 조건 |
|---|---|
| 1. 소유 유저 | `user_item`에 해당 `user_id` 행이 1개 이상 존재 |
| 2. 평가자 | `user_rating IS NOT NULL` 행이 1개 이상 |
| 3. 플레이어 | `numplays >= 1` **또는** `user_play`에 실제 로그 존재(있으면 로그 우선) |
| 4. 헤비유저 | 유저별 `numplays` 총합이 전체 유저 상위 20% |

### 코호트
- **실측 코호트(신규)**: `yearregistered` 월 × `user_play.play_date` 월 조합으로 N개월차 잔존율 계산
- **Proxy 코호트(기존, 병행 유지)**: `lastlogin 연도 - yearregistered 연도` = 잔존 기간(년) — 마지막 로그인 1개뿐이라는 한계 명시

### 세그먼트 (라이트/미드/헤비)
`numplays` 총합 기준 3분위 — 컷오프 수치는 실제 데이터 수집 후 분포 확인하여 확정(임의 고정값 지양, `docs/metrics.md`에 산출 근거 기록).

---

## 9. 분석 설계

1. **Engagement Funnel** — 단계별 전환율/이탈률, 이탈 최대 구간의 특징(첫 게임 복잡도 등) 탐색
2. **코호트 리텐션** — 실측 vs Proxy 비교, 2018년 vs 2022년 가입 코호트 3년차 잔존율 비교
3. **세그먼트별 선호도** — 라이트/미드/헤비 유저의 카테고리·복잡도 선호 차이
4. **시장 트렌드** — 출시연도별 카테고리 비중, 복잡도/평점 추이
5. **가설 검증**

| 가설 | H0 | 검정 | 유의수준 |
|---|---|---|---|
| Play-to-Wish Ratio 낮을수록 복잡도·플레이시간 높다 | 상관 없음 | 상관분석 + Mann-Whitney U | α=0.05 |
| 헤비유저는 복잡도 높은 게임을 선호한다 | 세그먼트 간 복잡도 분포 동일 | Mann-Whitney U | α=0.05 |
| 2015년 이후 협력 게임 출시 비율 증가 | 비율 동일 | 비율 검정(z-test) | α=0.05 |

---

## 10. 알려진 한계와 편향

- **`own=1` 생존 편향**: §4-2에서 명시한 대로 "가입→소유" 전환율 측정 불가. 퍼널을 4단계로 재정의해 대응.
- **Proxy 코호트의 한계**: `lastlogin`은 마지막 로그인 1개뿐이라 중간 활동 이력을 알 수 없음. plays API 실측 코호트로 보완하되, 샘플 한정이라 전체 대표성은 제한적.
- **`numplays` 자기보고 편향**: 유저가 직접 기록하므로 실제 플레이보다 과소/과대 집계될 수 있음.
- **샘플 대표성**: `user_lst` 자체가 BGG 전체 유저가 아닌 특정 방식으로 수집된 후보 목록 — 모집단 대표성은 검증되지 않음.
- **폴백 시 시점 한계**: 토큰 승인이 지연되어 2024년 데이터로 진행할 경우, "현재" 트렌드가 아닌 2024년 시점 스냅샷임을 리포트에 명시.

---

## 11. 인사이트 → 액션 (템플릿)

```
Problem: [퍼널 이탈 분석에서 발견한 현상]
    ↓
Cause: [원인 가설]
    ↓
Solution: [구체적 액션 제안]
```

예시: 신규 유저 상당수가 소유 직후 평가/플레이로 이어지지 않음 → 초기 접한 게임의 복잡도가 성향과 안 맞음 → 세그먼트별 성장 로드맵 추천 규칙 제안, 위시만 쌓이는 고난도 게임에는 입문 가이드 제작 제안.

---

## 12. 실행 방법

```bash
# 1. 가상환경
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. 환경변수
cp .env.example .env
# .env에 BGG_API_TOKEN, GCP_PROJECT_ID 채우기

# 3. GCP 인증 (gcloud CLI 미설치 시 먼저 설치: https://cloud.google.com/sdk/docs/install)
gcloud auth application-default login
gcloud config set project $GCP_PROJECT_ID

# 4. 수집 (예시 — 실제 실행 스크립트는 2주차에 collectors/ 완성 후 추가)
python3 -c "
from collectors.bgg_client import BGGClient
from collectors.user_collector import collect_users
import os
client = BGGClient(token=os.environ['BGG_API_TOKEN'])
collect_users(client, ['Thorben2302'], Path('data/user_info.csv'))
"

# 5. 셀프 체크 (네트워크 불필요)
python3 collectors/test_bgg_client.py

# 6. BigQuery 적재
python3 -c "from loaders.bigquery_loader import ensure_dataset, load_csv_to_raw; ..."
```

---

## 13. TODO — 주차별 체크리스트

### 1주차 (08/13~08/19): 수집 환경 구축
- [x] **BGG API 토큰 신청** — 08/16 `boardgamegeek.com/applications`에서 Non-commercial로 등록 완료, 승인 대기 중 (공식 문서상 "a week or more" 소요 가능 → 1주차 안에 안 나올 수 있음, 대기가 기본 시나리오)
- [ ] Google Cloud 프로젝트 생성 + `bgg_raw`/`bgg_staging`/`bgg_mart` 데이터셋 세팅 — DoD: `bq ls`로 3개 데이터셋 확인
- [ ] 기존 2024 데이터 BigQuery 적재 — DoD: raw 8개 테이블에 행 수 있음 확인
- [ ] 지표 정의서 초안 작성(`docs/metrics.md`) — DoD: 퍼널 4단계 판정 조건 SQL 의사코드까지
- [ ] 데이터 품질 체크리스트(§7) 전 항목 SQL 실행 (2024 데이터 기준) — DoD: 결과 `docs/data_quality.md`에 기록
- [ ] plays API 샘플 유저 선정 기준 설계 (가입연도 층화) — DoD: 표본 설계 근거 `docs/`에 기록 (실제 수집은 토큰 발급 후)
- [ ] `/applications` 페이지에서 승인 여부 매일 확인
- [ ] **토큰 발급되면 즉시**: `/applications` → Usage로 실제 rate limit 확인 → `bgg_client.py`의 `MIN_INTERVAL_SEC` 갱신
- [ ] **토큰 발급되면 즉시**: `user_lst` 기준 재수집 착수 (own=1 유지, thing 배치 수집 포함), plays 샘플 수집 실행

### 2주차 (08/20~08/26): 전처리 + EDA + 퍼널/세그먼트
- [ ] `sql/staging/` 전처리 쿼리 (타입 캐스팅, `item_link` → 카테고리/메커닉 뷰 분리)
- [ ] EDA (`analysis/eda.ipynb`)
- [ ] `sql/marts/funnel.sql` — DoD: 4단계 전환율 테이블 + 이탈 최대 구간 식별
- [ ] `sql/marts/segmentation.sql` — DoD: 세그먼트 컷오프 근거와 함께 `docs/metrics.md`에 기록
- [ ] 세그먼트별 게임 선호도 비교

### 3주차 (08/27~09/02): 코호트 + 가설 검증 + 트렌드
- [ ] `sql/marts/cohort_retention.sql` — 실측(plays) + Proxy(lastlogin) 병행 산출
- [ ] 실측 vs Proxy 코호트 비교 분석
- [ ] `sql/marts/trend.sql`
- [ ] 가설 3종 통계 검증(`analysis/hypothesis.ipynb`) — DoD: 각 가설의 검정 통계량·p-value·해석 기록
- [ ] Play-to-Wish Ratio 분석
- [ ] 인사이트 → 액션 문서 작성

### 4주차 (09/03~09/09): 대시보드 + 문서화
- [ ] Looker Studio 대시보드 (퍼널, 코호트 히트맵, 트렌드)
- [ ] `docs/data_dictionary.md`, `docs/metrics.md`, `docs/data_quality.md` 완성
- [ ] GitHub 정리, 포트폴리오 슬라이드
- [ ] 최종 발표 (09/09)

**일정 리스크**: 실제 착수는 08/16(계획 대비 3일 지연). 08/16 토큰 신청 완료, 공식 문서상 승인까지 "a week or more" 가능 — 즉 2주차 초반까지도 토큰이 없을 수 있다. 이 리스크는 이미 기본 시나리오로 흡수했다(§4-1): 1~2주차는 2024년 폴백 데이터로 파이프라인·SQL·지표 정의를 완성하고, 토큰이 나오면 재수집·교체 적재만 추가한다. 발표일(09/09)은 고정이므로, 그래도 지연되면 plays API 샘플 규모를 줄이거나 최신 재수집 자체를 스킵하고 "2024년 스냅샷 + 한계 명시"로 마무리한다.

---

## 14. 기술 스택

| 구분 | 기술 |
|---|---|
| 데이터 수집 | Python (`requests`, 표준 `xml.etree.ElementTree`), BGG XML API v2 |
| 데이터 처리 | pandas, numpy |
| 클라우드 DB | Google BigQuery |
| SQL 분석 | BigQuery SQL |
| 통계 분석 | scipy (Mann-Whitney U, 비율 검정) |
| 시각화 | Matplotlib, Seaborn |
| 대시보드 | Looker Studio (BigQuery 네이티브 연동) |

---

## API 토큰 발급 방법

공식 문서(`boardgamegeek.com/using_the_xml_api`, 2025-07-02판) 기준.

1. https://boardgamegeek.com/applications 접속 (BGG 계정 로그인 상태) → **"Create Application"** 클릭
2. 라이선스 유형은 **Non-commercial** 선택 — 광고·결제·수익화가 없는 개인 학습/포트폴리오 프로젝트이므로 비상업용에 해당. 설명란에 용도(개인 학습용 데이터 분석, read-only 수집)를 간단히 기재
3. 제출 후 대기 — **공식 문서에 승인까지 "a week or more" 소요될 수 있다고 명시되어 있음.** 1주차 안에 안 나올 수 있으므로, 대기 중에도 2024년 폴백 데이터로 파이프라인을 먼저 진행할 것 (§4-1)
4. 승인되면 같은 페이지(`/applications`)에서 애플리케이션 이름 옆 **"Tokens"** 클릭 → 토큰 생성
5. 발급된 토큰을 `.env`의 `BGG_API_TOKEN`에 저장
6. 요청 헤더는 정확히 `Authorization: Bearer {TOKEN}` — **Bearer 뒤 콜론 없이 공백 하나**, 요청 도메인은 반드시 `boardgamegeek.com`(`www.` 없이). 이미 `collectors/bgg_client.py`에 이 형식대로 구현됨
7. `/applications` 페이지의 **"Usage"** 링크로 현재 사용량을 모니터링할 수 있음 — 공식 문서가 정확한 rate limit 수치를 아직 공개하지 않고 "요청을 최소화하라"고만 명시하므로, 이 페이지로 실측하며 `bgg_client.py`의 `MIN_INTERVAL_SEC`(현재 5초 가정)를 조정
8. `thing` 배치 호출 시 id 최대 개수(현재 20개로 가정)도 승인 후 실제 호출로 확인해 필요시 조정
9. 요청은 **가능한 서버 사이드로**, 결과는 캐싱해서 재사용 — 공식 문서가 명시적으로 권장. 이 프로젝트는 이미 CSV로 캐싱하는 구조라 해당 원칙을 따르고 있음

## 참고
- BGG XML API v2 개요: https://boardgamegeek.com/wiki/page/BGG_XML_API2
- API 인증 정책: https://boardgamegeek.com/using_the_xml_api
- Google BigQuery 무료 한도: 월 1TB 쿼리 / 신규 가입 시 $300 크레딧
