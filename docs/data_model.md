# 데이터 구조 설명서

**작성일**: 2026-08-28 · BigQuery 프로젝트 `bgg-user-analytics`의 raw/staging/mart 3계층 스키마 전체를 다룬다. 표의 모든 컬럼·행수는 `INFORMATION_SCHEMA` 실측 기준(추정치 아님).

## 왜 3계층인가

```
data/*.csv (원본, BGG API 그대로)
   ↓ scripts/load_bigquery.py
bgg_raw     — 원본을 그대로 옮김. 전부 STRING.
   ↓ sql/staging/preprocessing.sql (SAFE_CAST, NULLIF, CASE WHEN)
bgg_staging — 타입 캐스팅 + 결측 마커 정규화. 분석 가능한 상태.
   ↓ sql/marts/*.sql (GROUP BY, 윈도우 함수)
bgg_mart    — 퍼널·코호트·세그먼트 등 분석 결과. 노트북이 조회하는 곳.
```

세 층을 나눈 이유:

1. **raw를 전부 STRING으로 받는 이유** — `rank` 컬럼처럼 숫자 컬럼에 `"Not Ranked"` 같은 문자열이 섞여 있다. pandas/BigQuery의 자동 타입추론에 맡기면 이런 혼입 값 때문에 컬럼 전체가 조용히 잘못된 타입으로 잡힐 수 있어서, 원본은 일단 전부 STRING으로 받아두고 타입 변환은 SQL에서 명시적으로 한다(`src/loaders/bigquery_loader.py` 원칙).
2. **staging에서 정제만 하고 집계는 안 하는 이유** — 정제 규칙(예: `"N/A"` → NULL)은 이 데이터를 쓰는 모든 분석이 공통으로 필요로 한다. 정제와 집계를 한 파일에 섞으면, 나중에 새 분석을 추가할 때마다 정제 로직을 또 베껴 써야 한다.
3. **mart가 최종 소비 지점인 이유** — 노트북은 `bgg_raw`나 `bgg_staging`을 직접 조회하지 않고 최대한 `bgg_mart`(이미 계산 끝난 결과)를 조회한다. 정제·집계 로직이 SQL 한 곳에만 있어야 노트북을 몇 번 다시 만들어도 로직이 어긋나지 않는다.

---

## 1. `bgg_raw` — 원본 그대로 (전부 STRING)

| 테이블 | 행수 | 만든 스크립트 | 내용 |
|---|---:|---|---|
| `user_info` | 2,954 | `scripts/collect/user.py` | 1차 스크리닝 통과 유저의 기본 정보 |
| `user_info_v2` | 600 | `scripts/collect/verify_frame.py` | 신규 표집틀(frame_candidates.csv) 검증표본 |
| `item_info` | 53,169 | `scripts/collect/collection.py` | 유저 컬렉션에서 처음 발견된 게임의 기본정보 |
| `item_info_v2` | 47,310 | `scripts/collect/verify_frame.py` | 검증표본 600명이 소유한 게임의 기본정보 |
| `item_details` | 53,166 | `scripts/collect/thing.py` | thing API 기본정보 블록 |
| `item_stats` | 53,166 | `scripts/collect/thing.py` | thing API 통계 블록(복잡도·평점 등) |
| `item_link` | 888,528 | `scripts/collect/thing.py` | 카테고리/메커닉/디자이너/퍼블리셔 (long 포맷) |
| `item_rank` | 74,101 | `scripts/collect/thing.py` | 서브타입별 순위(전체순위 + 장르별순위) |
| `user_item` | 495,346 | `scripts/collect/collection.py` | 유저×게임 컬렉션(own=1) |
| `user_item_v2` | 264,738 | `scripts/collect/verify_frame.py` | 검증표본 600명의 컬렉션(own=1) |
| `user_wishlist` | 56,798 | `scripts/collect/wishlist.py` | 유저×게임 개인 위시리스트(wishlist=1) |
| `user_play` | 520,892 | `scripts/collect_phase4_plays.py` | plays 표본(1,065명) 실제 플레이 로그 |
| `plays_sample` | 1,065 | `scripts/collect_phase4_plays.py` | plays 표집 대상 명단(코호트 분모용) |

### 컬럼 의미

**`user_info` / `user_info_v2`** — user API 응답
| 컬럼 | 의미 |
|---|---|
| `user_id` | BGG 유저명 |
| `yearregistered` | 가입 연도(월/일 없음 — API 자체가 연도만 줌) |
| `lastlogin` | 마지막 로그인 일자 |
| `country`, `stateorprovince` | 국가/주(결측 다수, 유저가 선택적으로 입력) |
| `traderating` | 거래 평판 점수 |

**`item_info` / `item_info_v2`** — collection API 응답에 딸려온 게임 기본정보
| 컬럼 | 의미 |
|---|---|
| `objectid` | 게임 고유 ID |
| `name`, `yearpublished` | 게임명, 출시연도 |
| `minplayers`~`playingtime` | 인원·시간 |
| `numowned` | **BGG 전체** 소유자 수(우리 표본 아님) |
| `average`, `bayesaverage` | 평균평점 / 베이지안 평균평점(소량평가 게임 극단치 보정) |
| `rank` | BGG 전체 순위 — `"Not Ranked"` 문자열 섞여 있음 |

**`item_details`** — thing API 기본정보 블록
| 컬럼 | 의미 |
|---|---|
| `objectid`, `name`, `minage`, `description` | |
| `yearpublished` | **기본 의미는 상업적 출시연도**(99.98%가 이 의미). 단 상업적 출시 개념이 없는 극소수 고대 전통게임(세네트 -3500, 바둑 -2200 등 10건뿐)은 예외적으로 기원 연도(음수 포함)로 대체돼 있고, 발매예정작(134건, 2027년 이후)은 예고된 출시연도가 그대로 들어있어 여전히 "출시연도" 의미다. `0`은 순수 결측 마커(665건, 1.2%). `data_quality.md` §3에서 2024 데이터로도 같은 현상 확인됨 |
| `avg_weights` | thing API가 주는 복잡도 필드지만 실측상 값이 안 채워짐 — 분석은 아래 `item_stats.averageweight`를 쓴다 |

**`item_stats`** — thing API 통계 블록(분석 핵심 테이블)
| 컬럼 | 의미 |
|---|---|
| `usersrated` | 평가자 수 |
| `average`, `bayesaverage`, `stddev` | 평점 통계 |
| `owned`, `trading`, `wanting`, `wishing` | **BGG 전체** 집계(소유/거래희망/원함/위시 인원) — 개인 위시 아님 |
| `numweights` | 복잡도 채점자 수 |
| `averageweight` | 복잡도(1~5) — **`0`은 "아무도 채점 안 함"이라는 결측 마커**(TROUBLESHOOTING #10) |

**`item_link`** — 카테고리/메커닉/디자이너/퍼블리셔를 한 테이블에 다 담은 long 포맷
| 컬럼 | 의미 |
|---|---|
| `objectid` | 게임 ID |
| `link_type` | `boardgamecategory` / `boardgamemechanic` / `boardgamedesigner` / `boardgamepublisher` 등 |
| `ref_id`, `value` | 해당 항목의 ID와 이름 |

**`item_rank`** — subtype별 세부 순위(`item_info.rank`는 대표 1건뿐)
| 컬럼 | 의미 |
|---|---|
| `rank_type`, `friendlyname` | 예: `"Strategy Game Rank"` |
| `value` | 순위 — `"Not Ranked"` 가능 |

**`user_item` / `user_item_v2` / `user_wishlist`** — 유저×게임 컬렉션(컬럼 동일, 수집 조건만 다름: own=1 vs wishlist=1)
| 컬럼 | 의미 |
|---|---|
| `user_rating` | 유저가 매긴 평점 — **미평가는 `"N/A"` 문자열**(빈 문자열 아님, TROUBLESHOOTING #9) |
| `numplays` | 플레이 횟수 |
| `own`, `prevowned`, `fortrade`, `want`, `wanttoplay`, `wanttobuy`, `wishlist`, `preordered` | 상태 플래그, `"0"`/`"1"`/빈 문자열 |
| `wishlistpriority` | 위시 우선순위(1~5) |

**`user_play`** — plays API 실제 플레이 로그
| 컬럼 | 의미 |
|---|---|
| `play_id` | 플레이 기록 ID |
| `play_date` | 플레이 일자(`"0000-00-00"` 등 무효값 존재 — staging에서 NULL 처리) |
| `quantity`, `length`, `incomplete`, `location` | 플레이 횟수/소요시간/미완료여부/장소 |

**`plays_sample`** — 코호트 분모용 명단(플레이 0건 유저도 포함해야 분모가 안 왜곡됨)
| 컬럼 | 의미 |
|---|---|
| `user_id`, `yearregistered` | plays 표집 대상 1,065명 |

---

## 2. `bgg_staging` — 정제됨 (타입 캐스팅 + 결측 정규화)

정제 규칙 공통 원칙: `SAFE_CAST`(잘못된 값은 에러 대신 NULL), `NULLIF(컬럼, '마커')`로 결측 마커를 NULL로 변환.

| raw 테이블 | staging 테이블 | 핵심 정제 내용 |
|---|---|---|
| `user_info`(`_v2`) | `stg_user_info`(`_v2`) | `yearregistered`→INT64, `lastlogin`→DATE |
| `item_info` | `stg_item_info` | `rank`: `"Not Ranked"`→NULL 후 INT64 |
| `item_details` | `stg_item_details` | `yearpublished`는 `stg_item_info` 값으로 COALESCE(보험) |
| `item_stats` | `stg_item_stats` | 전부 SAFE_CAST. **`averageweight=0`은 여기선 안 걸러짐** — 유효한 float라 SAFE_CAST를 통과함. NULL 처리는 마트(`funnel.sql`)의 `CASE WHEN`에서 함 |
| `item_link` | `stg_item_link` + `item_category`/`item_mechanic`/`item_designer`/`item_publisher`(뷰) | `link_type`별로 4개 뷰로 쪼갬 |
| `item_rank` | `stg_item_rank` | `value`: `"Not Ranked"`→NULL 후 INT64(`rank_value`로 리네임) |
| `user_item`(`_v2`) | `stg_user_item`(`_v2`) | `user_rating`: `NULLIF(x,'N/A')`→FLOAT64. 상태플래그: `"1"`→BOOL |
| `user_wishlist` | `stg_user_wishlist` | `stg_user_item`과 동일 규칙 |
| `user_play` | `stg_user_play` | `play_date`→DATE(무효값 자동 NULL), `incomplete`→BOOL |
| `plays_sample` | `stg_plays_sample` | `yearregistered`→INT64 |

컬럼 구성은 raw와 거의 동일(이름 유지)하고 **타입만 정확해진다** — 위 표에 없는 세부 컬럼은 1절의 raw 설명과 같다.

---

## 3. `bgg_mart` — 분석 결과 (노트북이 조회하는 곳)

| 테이블/뷰 | 종류 | 무엇에 답하는가 | 근거 staging 테이블 |
|---|---|---|---|
| `funnel_user` | TABLE | user_info 3,000명 기준 1행 — 보유/플레이기록/반복플레이기록 여부 + Core User 세그먼트 플래그 | `stg_user_info` + `stg_user_item` |
| `funnel_user_summary` | VIEW | 퍼널 3단계별 인원·전환율(Core User 제외) | `funnel_user` |
| `funnel_user_core_segment` | VIEW | Core User 세그먼트 인원·비중(퍼널 전환율 아님) | `funnel_user` |
| `funnel_item` | TABLE | 유저×게임 1행 — 평가/플레이기록/반복플레이기록 여부 + 복잡도 구간 | `stg_user_item` + `stg_item_stats` |
| `funnel_item_by_complexity` | VIEW | 복잡도 구간별 소유→플레이기록 비율 | `funnel_item` |
| `cohort_size` | TABLE | 가입연도별 관측 대상 수(분모) | `stg_plays_sample` |
| `cohort_retention_long` | TABLE | 코호트연도×경과년수별 리텐션율 | `stg_user_play` + `stg_plays_sample` |
| `user_segment` | TABLE | 유저를 플레이량 3분위(소프트유저/미들유저/하드유저)로 분류 | `stg_user_item` |
| `segment_complexity_pref` | TABLE | 세그먼트별 평균 플레이 복잡도 | `user_segment` + `stg_item_stats` |
| `segment_category_pref` | TABLE | 세그먼트별 선호 카테고리 Top10 | `user_segment` + `item_category` |
| `trend_yearly` | TABLE | 출시연도별 게임 수·복잡도·평점 추이 | `stg_item_details` |
| `trend_cooperative_share` | TABLE | 연도별 협력게임 메커닉 비중 | `stg_item_details` + `item_mechanic` |

### 컬럼 의미

| 테이블 | 컬럼 | 의미 |
|---|---|---|
| `funnel_user` | `is_owner`/`has_play_record`/`has_repeat_play_record` | 퍼널 3단계 도달 여부(BOOL). "플레이"가 아니라 "플레이 기록"인 이유: `numplays`는 BGG에 남은 기록을 재는 값이라 "안 했다"와 "기록 안 했다"를 구분 못 한다(01.EDA 8-0 실측 검증) |
| `funnel_user` | `is_core_user` | **퍼널 단계가 아니다** — 플레이 기록이 있는 유저 중 `total_numplays` 상위 20%(분위수 컷오프, 데이터 갱신 시 값이 바뀜). `user_segment.segment`의 3등분(상위 33%) 하드유저와도 다른 컷오프 |
| `funnel_user` | `n_rated` | engagement 보조 컬럼(퍼널 단계 아님) — 평가 참여율 최상위 분위의 플레이 기록 비율이 오히려 41.4%로 최저였다(01.EDA 8-3) |
| `funnel_user_summary` | `stage`, `n`, `conversion_from_prev`, `conversion_from_stage1` | 퍼널 3단계만의 단계명, 인원, 직전대비·1단계대비 전환율(Core User는 여기 없음) |
| `funnel_user_core_segment` | `n_players`, `n_core_users`, `core_share_of_players` | Core User는 세그먼트이므로 퍼널 전환율 컬럼 없이 인원·비중만 |
| `funnel_item` | `is_rated`, `has_play_record`, `has_repeat_play_record`, `complexity_bucket` | 평가/플레이기록/반복플레이기록 여부, 5개 복잡도 구간(`averageweight=0`은 NULL 처리됨) |
| `cohort_retention_long` | `cohort_year`, `year_offset`, `retention_rate` | 가입연도, 가입 후 경과년수(0=가입한 해), 그 시점 활성비율 |
| `user_segment` | `total_numplays`, `segment` | 전체 플레이횟수 합, `1.소프트유저`/`2.미들유저`/`3.하드유저`(명칭은 2024 팀 프로젝트의 Soft_User/Hard_User 관례를 따름) |

---

## v2 테이블은 왜 따로 있는가

**09/08 정정**: `user_info`(본표본, 3,000명)와 `_v2`가 붙은 세 테이블(`user_info_v2`, `item_info_v2`, `user_item_v2`, 검증표본 600명)은 둘 다 **같은 신규 표집틀**(`frame_candidates.csv`, `frame.py`가 BGG `thing` API의 `ratingcomments`로 만듦)에서 뽑았다. 원래 쓰던 `user_list.csv`(2024년 팀 프로젝트 유래, 194,643명)는 가입연도 시간 절단 편향(2025·2026 가입자 0명)이 있다는 게 검증표본 600명(`scripts/collect/verify_frame.py`)으로 실측 확인돼 완전히 폐기됐다 — 본표본도 `user_list.csv`가 아니라 `frame_candidates.csv`에서 `scripts/collect/main_frame.py`로 뽑았다. `_v2`는 이 편향을 검증하려고 먼저 뽑은 600명이고, 본표본(3,000명)은 같은 표집틀에서 별도로 추출한 독립 표본이다 — `docs/sampling_design.md` 참고.
