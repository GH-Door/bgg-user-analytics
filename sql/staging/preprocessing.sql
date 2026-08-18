-- bgg_raw → bgg_staging 전처리.
-- docs/data_quality.md에서 나온 결과를 그대로 반영한다:
--   - 숫자 컬럼 CAST는 전부 안전 확인됨 (실패 0건) → SAFE_CAST로 캐스팅만 하면 됨
--   - item_info.rank의 "Not Ranked"는 NULL로 바꾼 뒤 캐스팅
--   - item_details.yearpublished는 폴백 기간 100% NULL → item_info.yearpublished로 COALESCE
--   - item_info ↔ item_details/item_link는 커버리지 56.3%뿐이라 전부 LEFT JOIN
--   - user_item.user_rating 결측(47.8%)은 "미평가"이지 0점이 아니므로 NULL 유지(0으로 채우지 않음)
--   - yearpublished 범위는 1900 하한을 두지 않는다 (전통 게임이 실제로 그보다 오래됨, data_quality.md §3 참고)
--
-- 순서 중요: stg_item_info가 stg_item_details보다 먼저 있어야 COALESCE에서 참조 가능.
-- 실행: bq query --use_legacy_sql=false < sql/staging/preprocessing.sql

-- ============================================================
-- stg_user_info
-- ============================================================
CREATE OR REPLACE TABLE `bgg-user-analytics.bgg_staging.stg_user_info` AS
SELECT
  user_id,
  SAFE_CAST(yearregistered AS INT64) AS yearregistered,
  SAFE_CAST(lastlogin AS DATE) AS lastlogin,
  country,        -- 이미 NULL(빈 값)로 들어있음, 결측 28.8%는 정상 특성
  stateorprovince,-- 결측 52.3%, 정상 특성
  SAFE_CAST(traderating AS INT64) AS traderating
FROM `bgg-user-analytics.bgg_raw.user_info`;

-- ============================================================
-- stg_item_info
-- ============================================================
CREATE OR REPLACE TABLE `bgg-user-analytics.bgg_staging.stg_item_info`
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
FROM `bgg-user-analytics.bgg_raw.item_info`;

-- ============================================================
-- stg_item_details — yearpublished는 item_info로 COALESCE
-- (2024 폴백 데이터는 item_details.yearpublished가 100% NULL이라 사실상 전부 item_info 값을 씀,
--  재수집 후엔 thing API가 직접 채운 값과 item_info 값이 대부분 일치할 것)
-- ============================================================
CREATE OR REPLACE TABLE `bgg-user-analytics.bgg_staging.stg_item_details`
CLUSTER BY objectid AS
SELECT
  d.objectid,
  d.name,
  COALESCE(SAFE_CAST(d.yearpublished AS INT64), i.yearpublished) AS yearpublished,
  SAFE_CAST(d.minage AS INT64) AS minage,
  d.description,
  SAFE_CAST(d.avg_weights AS FLOAT64) AS avg_weights
FROM `bgg-user-analytics.bgg_raw.item_details` d
LEFT JOIN `bgg-user-analytics.bgg_staging.stg_item_info` i USING (objectid);

-- ============================================================
-- stg_user_item — user_rating 결측은 NULL 유지("미평가" ≠ 0점).
-- status 플래그는 "0"/"1" 문자열(또는 빈값)을 BOOL로 변환.
-- NULLIF(...,'')로 빈 문자열을 먼저 NULL로 만들어야 SAFE_CAST가 결측을 결측으로 인식한다.
-- ============================================================
CREATE OR REPLACE TABLE `bgg-user-analytics.bgg_staging.stg_user_item`
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
FROM `bgg-user-analytics.bgg_raw.user_item`;

-- ============================================================
-- stg_item_link
-- ============================================================
CREATE OR REPLACE TABLE `bgg-user-analytics.bgg_staging.stg_item_link`
CLUSTER BY objectid AS
SELECT
  objectid,
  link_type,
  SAFE_CAST(ref_id AS INT64) AS ref_id,
  value
FROM `bgg-user-analytics.bgg_raw.item_link`;

-- ============================================================
-- link_type별 뷰 (PLAN.md §5에서 계획한 4개: category/mechanic/designer/publisher)
-- ============================================================
CREATE OR REPLACE VIEW `bgg-user-analytics.bgg_staging.item_category` AS
SELECT objectid, ref_id AS category_id, value AS category
FROM `bgg-user-analytics.bgg_staging.stg_item_link`
WHERE link_type = 'boardgamecategory';

CREATE OR REPLACE VIEW `bgg-user-analytics.bgg_staging.item_mechanic` AS
SELECT objectid, ref_id AS mechanic_id, value AS mechanic
FROM `bgg-user-analytics.bgg_staging.stg_item_link`
WHERE link_type = 'boardgamemechanic';

CREATE OR REPLACE VIEW `bgg-user-analytics.bgg_staging.item_designer` AS
SELECT objectid, ref_id AS designer_id, value AS designer
FROM `bgg-user-analytics.bgg_staging.stg_item_link`
WHERE link_type = 'boardgamedesigner';

CREATE OR REPLACE VIEW `bgg-user-analytics.bgg_staging.item_publisher` AS
SELECT objectid, ref_id AS publisher_id, value AS publisher
FROM `bgg-user-analytics.bgg_staging.stg_item_link`
WHERE link_type = 'boardgamepublisher';
