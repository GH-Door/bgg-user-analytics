-- bgg_raw → bgg_staging 전처리. 실제 재수집 데이터(2026-08) 기준.
--   - 숫자 컬럼 CAST는 안전 확인됨(2024 폴백 기준 §3) → SAFE_CAST로 캐스팅만 하면 됨,
--     data_quality_checks.sql 재실행으로 실수집 데이터도 재검증할 것
--   - item_info.rank의 "Not Ranked"는 NULL로 바꾼 뒤 캐스팅
--   - item_details.yearpublished는 thing API가 직접 채운 값 — 실수집 데이터는 결측 0%.
--     그래도 item_info와 COALESCE는 유지한다(신규 objectid가 thing 응답에서 개별 결측일
--     가능성은 여전히 있고, item_info.yearpublished는 collection API에서 이미 확보된 값이라
--     보험으로 두는 게 손해가 없음)
--   - item_info ↔ item_details/item_link는 위시 전용 게임(아무도 안 갖고 있어 thing 수집
--     대상에서 빠졌던 게임) 때문에 커버리지가 100%가 아닐 수 있다 — 전부 LEFT JOIN 유지
--   - user_item.user_rating 결측(47.8%, 2024 폴백 기준)은 "미평가"이지 0점이 아니므로
--     NULL 유지(0으로 채우지 않음). 실측 데이터의 결측 표기는 빈 문자열이 아니라 "N/A"
--     문자열이다(fixtures/collection_fagentu007.xml로 실측 확인, test_parsers.py 참고) —
--     NULLIF(user_rating, 'N/A')가 이미 이 케이스를 처리한다
--   - yearpublished 범위는 1900 하한을 두지 않는다 (전통 게임이 실제로 그보다 오래됨, data_quality.md §3 참고)
--
-- 순서 중요: stg_item_info가 stg_item_details보다 먼저 있어야 COALESCE에서 참조 가능.
-- 실행: bq query --use_legacy_sql=false --project_id=$GCP_PROJECT_ID < sql/staging/preprocessing.sql
-- (프로젝트 id를 SQL에 안 박아두고 .env의 GCP_PROJECT_ID로 넘긴다 — clone해서 다른
-- 프로젝트로 돌릴 때 이 파일을 안 고쳐도 되게)

-- ============================================================
-- stg_user_info
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_user_info` AS
SELECT
  user_id,
  SAFE_CAST(yearregistered AS INT64) AS yearregistered,
  SAFE_CAST(lastlogin AS DATE) AS lastlogin,
  country,        -- 이미 NULL(빈 값)로 들어있음, 결측 28.8%는 정상 특성
  stateorprovince,-- 결측 52.3%, 정상 특성
  SAFE_CAST(traderating AS INT64) AS traderating
FROM `bgg_raw.user_info`;

-- ============================================================
-- stg_item_info
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_item_info`
CLUSTER BY objectid AS
SELECT
  objectid,
  name,
  SAFE_CAST(yearpublished AS INT64) AS yearpublished,
  SAFE_CAST(minplayers AS INT64) AS minplayers,
  SAFE_CAST(maxplayers AS INT64) AS maxplayers,
  SAFE_CAST(minplaytime AS INT64) AS minplaytime,
  SAFE_CAST(maxplaytime AS INT64) AS maxplaytime,
  SAFE_CAST(playingtime AS INT64) AS playingtime,
  SAFE_CAST(numowned AS INT64) AS numowned,
  SAFE_CAST(average AS FLOAT64) AS average,
  SAFE_CAST(bayesaverage AS FLOAT64) AS bayesaverage,
  SAFE_CAST(stddev AS FLOAT64) AS stddev,
  SAFE_CAST(IF(rank = 'Not Ranked', NULL, rank) AS INT64) AS rank
FROM `bgg_raw.item_info`;

-- ============================================================
-- stg_item_details — yearpublished는 item_info로 COALESCE
-- (2024 폴백 데이터는 item_details.yearpublished가 100% NULL이라 사실상 전부 item_info 값을 씀,
--  재수집 후엔 thing API가 직접 채운 값과 item_info 값이 대부분 일치할 것)
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_item_details`
CLUSTER BY objectid AS
SELECT
  d.objectid,
  d.name,
  COALESCE(SAFE_CAST(d.yearpublished AS INT64), i.yearpublished) AS yearpublished,
  SAFE_CAST(d.minage AS INT64) AS minage,
  d.description,
  SAFE_CAST(d.avg_weights AS FLOAT64) AS avg_weights
FROM `bgg_raw.item_details` d
LEFT JOIN `bgg_staging.stg_item_info` i USING (objectid);

-- ============================================================
-- stg_user_item — user_rating 결측은 NULL 유지("미평가" ≠ 0점).
-- status 플래그는 "0"/"1" 문자열(또는 빈값)을 BOOL로 변환.
-- NULLIF(...,'')로 빈 문자열을 먼저 NULL로 만들어야 SAFE_CAST가 결측을 결측으로 인식한다.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_user_item`
CLUSTER BY objectid AS
SELECT
  user_id,
  objectid,
  SAFE_CAST(NULLIF(user_rating, 'N/A') AS FLOAT64) AS user_rating,
  SAFE_CAST(numplays AS INT64) AS numplays,
  comment,
  SAFE_CAST(NULLIF(own, '') AS INT64) = 1 AS own,
  SAFE_CAST(NULLIF(prevowned, '') AS INT64) = 1 AS prevowned,
  SAFE_CAST(NULLIF(fortrade, '') AS INT64) = 1 AS fortrade,
  SAFE_CAST(NULLIF(want, '') AS INT64) = 1 AS want,
  SAFE_CAST(NULLIF(wanttoplay, '') AS INT64) = 1 AS wanttoplay,
  SAFE_CAST(NULLIF(wanttobuy, '') AS INT64) = 1 AS wanttobuy,
  SAFE_CAST(NULLIF(wishlist, '') AS INT64) = 1 AS wishlist,
  SAFE_CAST(NULLIF(wishlistpriority, '') AS INT64) AS wishlistpriority,
  SAFE_CAST(NULLIF(preordered, '') AS INT64) = 1 AS preordered,
  SAFE_CAST(NULLIF(lastmodified, '') AS DATETIME) AS lastmodified
FROM `bgg_raw.user_item`;

-- ============================================================
-- stg_item_link
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_item_link`
CLUSTER BY objectid AS
SELECT
  objectid,
  link_type,
  SAFE_CAST(ref_id AS INT64) AS ref_id,
  value
FROM `bgg_raw.item_link`;

-- ============================================================
-- stg_item_stats — thing API stats(2024 폴백엔 없던 신규 확보 컬럼).
-- Play-to-Wish 가설(wishing/wanting)에 직접 쓰는 테이블.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_item_stats`
CLUSTER BY objectid AS
SELECT
  objectid,
  SAFE_CAST(usersrated AS INT64) AS usersrated,
  SAFE_CAST(average AS FLOAT64) AS average,
  SAFE_CAST(bayesaverage AS FLOAT64) AS bayesaverage,
  SAFE_CAST(stddev AS FLOAT64) AS stddev,
  SAFE_CAST(owned AS INT64) AS owned,
  SAFE_CAST(trading AS INT64) AS trading,
  SAFE_CAST(wanting AS INT64) AS wanting,
  SAFE_CAST(wishing AS INT64) AS wishing,
  SAFE_CAST(numcomments AS INT64) AS numcomments,
  SAFE_CAST(numweights AS INT64) AS numweights,
  SAFE_CAST(averageweight AS FLOAT64) AS averageweight
FROM `bgg_raw.item_stats`;

-- ============================================================
-- stg_item_rank — subtype별 전체 순위(long 포맷). item_info.rank는 대표 1건뿐이라
-- "Strategy Game Rank"/"Family Game Rank" 등 세부 순위는 여기서만 얻는다.
-- value가 item_info.rank와 마찬가지로 "Not Ranked" 문자열을 가질 수 있다.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_item_rank`
CLUSTER BY objectid AS
SELECT
  objectid,
  rank_type,
  friendlyname,
  SAFE_CAST(IF(value = 'Not Ranked', NULL, value) AS INT64) AS rank_value,
  SAFE_CAST(bayesaverage AS FLOAT64) AS bayesaverage
FROM `bgg_raw.item_rank`;

-- ============================================================
-- stg_user_play — 실측 코호트 리텐션의 근거 테이블(기획서엔 없던 신규 테이블,
-- lastlogin 기반 Proxy 코호트를 대체). 표본 913명 한정(plays 표집 설계는
-- docs/sampling_design.md, scripts/collect/plays.py 참고) — 전체 user_item과
-- 모집단이 다르므로 JOIN 시 이 점을 명시할 것.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_user_play`
CLUSTER BY objectid AS
SELECT
  SAFE_CAST(play_id AS INT64) AS play_id,
  user_id,
  objectid,
  SAFE_CAST(play_date AS DATE) AS play_date,  -- "0000-00-00" 등 무효값은 SAFE_CAST가 NULL로
  SAFE_CAST(quantity AS INT64) AS quantity,
  SAFE_CAST(length AS INT64) AS length,
  SAFE_CAST(NULLIF(incomplete, '') AS INT64) = 1 AS incomplete,
  location
FROM `bgg_raw.user_play`;

-- ============================================================
-- stg_user_wishlist — collection API를 wishlist=1로 재수집한 결과
-- (own=1 고정 수집이던 user_item에는 개인 위시가 298행뿐이라 별도 확보,
-- scripts/collect/wishlist.py 참고). 컬럼은 stg_user_item과 동일 — own은
-- 이 수집에서 항상 0에 가깝고(위시 항목 대부분 미소유), own=1이면서
-- wishlist=1인 298건(확장판 등 중복 소유 케이스)만 예외.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_user_wishlist`
CLUSTER BY objectid AS
SELECT
  user_id,
  objectid,
  SAFE_CAST(NULLIF(user_rating, 'N/A') AS FLOAT64) AS user_rating,
  SAFE_CAST(numplays AS INT64) AS numplays,
  comment,
  SAFE_CAST(NULLIF(own, '') AS INT64) = 1 AS own,
  SAFE_CAST(NULLIF(prevowned, '') AS INT64) = 1 AS prevowned,
  SAFE_CAST(NULLIF(fortrade, '') AS INT64) = 1 AS fortrade,
  SAFE_CAST(NULLIF(want, '') AS INT64) = 1 AS want,
  SAFE_CAST(NULLIF(wanttoplay, '') AS INT64) = 1 AS wanttoplay,
  SAFE_CAST(NULLIF(wanttobuy, '') AS INT64) = 1 AS wanttobuy,
  SAFE_CAST(NULLIF(wishlist, '') AS INT64) = 1 AS wishlist,
  SAFE_CAST(NULLIF(wishlistpriority, '') AS INT64) AS wishlistpriority,
  SAFE_CAST(NULLIF(preordered, '') AS INT64) = 1 AS preordered,
  SAFE_CAST(NULLIF(lastmodified, '') AS DATETIME) AS lastmodified
FROM `bgg_raw.user_wishlist`;

-- ============================================================
-- stg_plays_sample — plays 표집 명단(913명). 코호트 마트의 분모(가입연도별
-- 관측 대상 크기)를 구할 때 쓴다 — stg_user_play만 쓰면 플레이 기록 0건인
-- 유저가 빠져 분모가 작게 잡힌다.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_staging.stg_plays_sample` AS
SELECT
  user_id,
  SAFE_CAST(yearregistered AS INT64) AS yearregistered
FROM `bgg_raw.plays_sample`;

-- ============================================================
-- link_type별 뷰 (PLAN.md §5에서 계획한 4개: category/mechanic/designer/publisher)
-- ============================================================
CREATE OR REPLACE VIEW `bgg_staging.item_category` AS
SELECT objectid, ref_id AS category_id, value AS category
FROM `bgg_staging.stg_item_link`
WHERE link_type = 'boardgamecategory';

CREATE OR REPLACE VIEW `bgg_staging.item_mechanic` AS
SELECT objectid, ref_id AS mechanic_id, value AS mechanic
FROM `bgg_staging.stg_item_link`
WHERE link_type = 'boardgamemechanic';

CREATE OR REPLACE VIEW `bgg_staging.item_designer` AS
SELECT objectid, ref_id AS designer_id, value AS designer
FROM `bgg_staging.stg_item_link`
WHERE link_type = 'boardgamedesigner';

CREATE OR REPLACE VIEW `bgg_staging.item_publisher` AS
SELECT objectid, ref_id AS publisher_id, value AS publisher
FROM `bgg_staging.stg_item_link`
WHERE link_type = 'boardgamepublisher';
