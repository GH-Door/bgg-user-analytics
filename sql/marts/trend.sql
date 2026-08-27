-- 시장 트렌드: 출시연도별 게임 수·복잡도·평점 추이 + 협력 게임 비중(가설 3의 근거표).
--
-- yearpublished 범위는 실측으로 -3500~2030까지 나온다(고대 게임 Go/Senet,
-- 발표만 된 미출시 게임). 트렌드에 넣으면 그래프가 의미 없어지므로 최근
-- 수십 년으로 스코프를 좁힌다 — 다만 이 스코프는 값이 "틀려서" 빼는 게 아니라
-- "그래프를 읽을 수 있게" 빼는 선택이라, docs/data_quality.md §3(1900 하한을
-- 안 두기로 한 결정)과 모순되지 않는다. 그건 품질 체크 기준이고 이건 분석
-- 스코프 기준 — 다른 목적이라 다른 결정을 내려도 된다.
--
-- 실행: bq query --use_legacy_sql=false --project_id=$GCP_PROJECT_ID < sql/marts/trend.sql

-- ============================================================
-- trend_yearly — 연도별 출시 게임 수·평균 복잡도·평균 평점 + 3년 이동평균.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.trend_yearly` AS
WITH yearly AS (
  SELECT
    d.yearpublished,
    COUNT(*) AS n_games,
    -- averageweight=0은 funnel.sql과 같은 이유로 미채점 취급(NULLIF로 집계에서 제외).
    AVG(NULLIF(s.averageweight, 0)) AS avg_complexity,
    AVG(NULLIF(s.average, 0)) AS avg_rating
  FROM `bgg_staging.stg_item_details` d
  LEFT JOIN `bgg_staging.stg_item_stats` s USING (objectid)
  WHERE d.yearpublished BETWEEN 1970 AND 2026  -- 위 스코프 설명 참고
  GROUP BY d.yearpublished
)
SELECT
  yearpublished,
  n_games,
  ROUND(avg_complexity, 3) AS avg_complexity,
  ROUND(avg_rating, 3) AS avg_rating,
  -- 이동평균: "직전 2년 + 이번 해" 3개 값의 평균. ROWS BETWEEN은 물리적 행 개수
  -- 기준이라, 정렬(ORDER BY yearpublished)이 이미 연 단위 1행씩이라는 전제가
  -- 깨지면(예: 결측 연도가 빠져 있으면) 완벽한 "3개년" 평균이 아닐 수 있다 —
  -- 이 데이터는 1970~2026 전 연도가 다 존재해서 문제 없음(WHERE로 미리 확인).
  ROUND(AVG(n_games) OVER (
    ORDER BY yearpublished ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
  ), 1) AS n_games_3yr_avg
FROM yearly
ORDER BY yearpublished;

-- ============================================================
-- trend_cooperative_share — 가설 3(2015년 이후 협력 게임 출시 비율 증가)의
-- 근거표. 연도별 "협력 게임" 메커닉을 가진 게임의 비율.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.trend_cooperative_share` AS
WITH per_year AS (
  SELECT
    d.yearpublished,
    d.objectid,
    -- LOGICAL_OR: 이 게임의 여러 메커닉 행(item_link는 long 포맷) 중 하나라도
    -- "Cooperative Game"이면 TRUE. GROUP BY 없이 그냥 EXISTS 서브쿼리로도
    -- 되지만, item_mechanic 뷰가 이미 있어서 LEFT JOIN + LOGICAL_OR이 더 짧다.
    LOGICAL_OR(m.mechanic = 'Cooperative Game') AS is_cooperative
  FROM `bgg_staging.stg_item_details` d
  LEFT JOIN `bgg_staging.item_mechanic` m USING (objectid)
  WHERE d.yearpublished BETWEEN 1970 AND 2026
  GROUP BY d.yearpublished, d.objectid
)
SELECT
  yearpublished,
  COUNT(*) AS n_games,
  COUNTIF(is_cooperative) AS n_cooperative,
  SAFE_DIVIDE(COUNTIF(is_cooperative), COUNT(*)) AS cooperative_share
FROM per_year
GROUP BY yearpublished
ORDER BY yearpublished;
