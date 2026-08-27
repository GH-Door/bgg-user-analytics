-- 세그먼트: 유저를 numplays 합계 기준 라이트/미들/헤비 3분위로 나누고,
-- 세그먼트별 선호 복잡도·카테고리를 비교한다.
--
-- NTILE(3)이 이 파일의 핵심 — "3분위로 나눠라"를 SQL이 직접 계산해서,
-- 컷오프 값을 코드 어디에도 하드코딩하지 않는다(피드백③에서 지적된
-- "컷오프 수치를 나중에 확정" 문제를 애초에 없앤다 — 데이터가 바뀌어도
-- NTILE이 알아서 다시 3등분한다).
--
-- 실행: bq query --use_legacy_sql=false --project_id=$GCP_PROJECT_ID < sql/marts/segmentation.sql

-- ============================================================
-- user_segment — 유저 한 명당 한 행. numplays 합계 기준 3분위 라벨.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.user_segment` AS
WITH user_totals AS (
  SELECT user_id, SUM(numplays) AS total_numplays
  FROM `bgg_staging.stg_user_item`
  GROUP BY user_id
  HAVING SUM(numplays) > 0  -- 세그먼트는 "플레이한 유저"만 대상. 플레이 0인
                            -- 유저까지 3등분에 끼면 라이트 구간이 전부
                            -- "안 하는 사람"으로 채워져 세그먼트 자체가 무의미해진다.
)
SELECT
  user_id,
  total_numplays,
  -- NTILE(3) OVER (ORDER BY x)는 정렬 순서대로 그룹을 1,2,3으로 나눈다.
  -- numplays가 적을수록 먼저 정렬되므로 1=라이트, 3=헤비가 되도록
  -- ORDER BY total_numplays(오름차순, 기본값)를 그대로 쓴다.
  CASE NTILE(3) OVER (ORDER BY total_numplays)
    WHEN 1 THEN '1.라이트'
    WHEN 2 THEN '2.미들'
    WHEN 3 THEN '3.헤비'
  END AS segment
FROM user_totals;

-- ============================================================
-- segment_complexity_pref — 세그먼트별 "실제로 플레이한 게임"의 평균 복잡도.
-- 소유만 하고 안 한 게임은 취향 신호가 아니므로 numplays > 0인 행만 쓴다
-- (funnel_item에서 이미 검증한 is_played와 같은 조건).
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.segment_complexity_pref` AS
SELECT
  seg.segment,
  COUNT(*) AS n_played_games,
  ROUND(AVG(NULLIF(s.averageweight, 0)), 3) AS avg_complexity_played,
  ROUND(APPROX_QUANTILES(NULLIF(s.averageweight, 0), 2)[OFFSET(1)], 3) AS median_complexity_played
FROM `bgg_mart.user_segment` seg
JOIN `bgg_staging.stg_user_item` ui USING (user_id)
LEFT JOIN `bgg_staging.stg_item_stats` s USING (objectid)
WHERE ui.numplays > 0
GROUP BY seg.segment
ORDER BY seg.segment;

-- ============================================================
-- segment_category_pref — 세그먼트별 카테고리 선호 Top 10(플레이한 게임 기준).
-- 한 게임이 카테고리 여러 개를 가질 수 있어(item_link가 long 포맷) 유저×게임×
-- 카테고리로 행이 늘어난다 — "선호 비중"이 목적이라 이건 의도된 동작이다.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.segment_category_pref` AS
WITH played_categories AS (
  SELECT seg.segment, c.category
  FROM `bgg_mart.user_segment` seg
  JOIN `bgg_staging.stg_user_item` ui USING (user_id)
  JOIN `bgg_staging.item_category` c USING (objectid)
  WHERE ui.numplays > 0
),
ranked AS (
  SELECT
    segment,
    category,
    COUNT(*) AS n,
    -- 세그먼트 안에서 카테고리별 순위. RANK()는 동점이면 같은 순위를 주고
    -- 다음 순위를 건너뛴다(1,1,3,...) — ROW_NUMBER()와 다르다.
    RANK() OVER (PARTITION BY segment ORDER BY COUNT(*) DESC) AS rnk
  FROM played_categories
  GROUP BY segment, category
)
SELECT segment, category, n, rnk
FROM ranked
WHERE rnk <= 10
ORDER BY segment, rnk;
