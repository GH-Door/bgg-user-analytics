-- 퍼널: 소유 → 평가 → 플레이 → 헤비유저 (4단계).
-- "가입 → 소유" 전환율은 own=1로 고정 수집해서 애초에 측정 불가하다(PLAN.md §4-2,
-- 생존편향으로 문서화된 한계) — 그래서 4단계는 "가입" 없이 "소유"부터 시작한다.
--
-- 퍼널 SQL의 본질은 딱 두 단계다: (1) CASE WHEN/불리언 비교로 "이 행이 이 단계에
-- 도달했는가"를 표시 → (2) COUNTIF/COUNT(DISTINCT)로 그 표시를 숫자로 좁힌다.
-- 아래 두 마트가 이 패턴을 유저 축·아이템 축에 각각 적용한 것뿐이다.
--
-- 두 축이 필요한 이유: 유저 축(funnel_user)은 "누가 이탈하는가", 아이템 축
-- (funnel_item)은 "어떤 게임에서 이탈하는가"에 답한다. 특히 아이템 축에
-- 복잡도(averageweight)를 붙이면 "복잡도 높은 게임일수록 소유만 하고 안 하는
-- 비율이 높은가"(Q3 핵심 질문 3과 직결)까지 같은 쿼리로 나온다.
--
-- 실행: bq query --use_legacy_sql=false --project_id=$GCP_PROJECT_ID < sql/marts/funnel.sql

-- ============================================================
-- funnel_user — 유저 축: 유저 한 명당 한 행. 이 유저가 퍼널 어디까지 갔는가.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.funnel_user` AS
WITH user_stats AS (
  -- stg_user_item은 유저×게임(행 하나 = 소유한 게임 하나)이라 유저 단위로 먼저
  -- 접어야 한다. COUNTIF는 조건을 만족하는 행 수를 세는 COUNT의 사촌 — 여기선
  -- "이 유저가 평가한 게임이 하나라도 있는가"만 필요해서 0보다 큰지만 본다.
  SELECT
    user_id,
    COUNTIF(user_rating IS NOT NULL) AS n_rated,
    SUM(numplays) AS total_numplays
  FROM `bgg_staging.stg_user_item`
  GROUP BY user_id
),
heavy_cutoff AS (
  -- 헤비유저 = "플레이한 유저" 중 numplays 합계 상위 20%. 컷오프 숫자를 직접
  -- 계산해서 하드코딩하지 않는다 — PERCENTILE_CONT 대신 정수 인덱스로 쓸 수 있는
  -- APPROX_QUANTILES(x, 100)[OFFSET(80)]로 80번째 백분위수(=상위 20% 경계)를 구함.
  -- WHERE total_numplays > 0로 "플레이 안 한 유저"를 분모에서 미리 뺀다 —
  -- 안 그러면 절반 가까이가 0이라 분포 자체가 왜곡된다.
  SELECT APPROX_QUANTILES(total_numplays, 100)[OFFSET(80)] AS cutoff
  FROM user_stats
  WHERE total_numplays > 0
)
SELECT
  user_id,
  TRUE AS is_owner,                                      -- 1단계: 이 테이블에 있다 = own=1로 수집된 유저
  n_rated > 0 AS is_rater,                                -- 2단계
  total_numplays > 0 AS is_player,                        -- 3단계
  total_numplays >= (SELECT cutoff FROM heavy_cutoff) AS is_heavy_user  -- 4단계
FROM user_stats;

-- 단계별 인원수·직전 대비 전환율 요약(리포트에 바로 쓰는 표).
CREATE OR REPLACE VIEW `bgg_mart.funnel_user_summary` AS
WITH stage_counts AS (
  SELECT 1 AS stage_order, '1.소유' AS stage, COUNTIF(is_owner) AS n FROM `bgg_mart.funnel_user`
  UNION ALL
  SELECT 2, '2.평가', COUNTIF(is_rater) FROM `bgg_mart.funnel_user`
  UNION ALL
  SELECT 3, '3.플레이', COUNTIF(is_player) FROM `bgg_mart.funnel_user`
  UNION ALL
  SELECT 4, '4.헤비유저', COUNTIF(is_heavy_user) FROM `bgg_mart.funnel_user`
)
SELECT
  stage_order,
  stage,
  n,
  -- LAG로 "바로 이전 행의 n"을 끌어와 직전 대비 전환율을 구한다. 윈도우 함수를
  -- 안 쓰면 이 표를 4번 따로 짜서 손으로 나눠야 한다.
  SAFE_DIVIDE(n, LAG(n) OVER (ORDER BY stage_order)) AS conversion_from_prev,
  SAFE_DIVIDE(n, FIRST_VALUE(n) OVER (ORDER BY stage_order)) AS conversion_from_stage1
FROM stage_counts
ORDER BY stage_order;

-- ============================================================
-- funnel_item — 아이템 축: 유저×게임 한 쌍이 한 행(=stg_user_item과 동일 단위).
-- 복잡도(averageweight)를 붙여 "복잡도별 소유→플레이 전환율"을 바로 뽑는다.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.funnel_item` AS
SELECT
  ui.user_id,
  ui.objectid,
  ui.user_rating IS NOT NULL AS is_rated,
  ui.numplays > 0 AS is_played,
  s.averageweight,
  CASE
    -- averageweight=0은 "매우 가벼움"이 아니라 "아무도 복잡도를 채점 안 함"이다
    -- (item_info.rank의 "Not Ranked"와 같은 성격의 결측 마커 — 실측 확인:
    -- stg_item_stats에서 averageweight=0인 게임이 12,317개). 0을 그대로 두면
    -- 미채점 게임이 전부 "가벼움" 버킷으로 잘못 몰려 그 버킷의 전환율이 왜곡된다.
    WHEN s.averageweight IS NULL OR s.averageweight = 0 THEN NULL
    WHEN s.averageweight < 2.0 THEN '1.가벼움(<2.0)'
    WHEN s.averageweight < 2.5 THEN '2.라이트(2.0-2.5)'
    WHEN s.averageweight < 3.0 THEN '3.미들(2.5-3.0)'
    WHEN s.averageweight < 3.5 THEN '4.미들헤비(3.0-3.5)'
    ELSE '5.헤비(>=3.5)'
  END AS complexity_bucket
FROM `bgg_staging.stg_user_item` ui
LEFT JOIN `bgg_staging.stg_item_stats` s USING (objectid);

-- 복잡도 구간별 소유→플레이 전환율(Q3 핵심 근거표).
CREATE OR REPLACE VIEW `bgg_mart.funnel_item_by_complexity` AS
SELECT
  complexity_bucket,
  COUNT(*) AS n_owned,
  COUNTIF(is_played) AS n_played,
  SAFE_DIVIDE(COUNTIF(is_played), COUNT(*)) AS play_conversion_rate
FROM `bgg_mart.funnel_item`
WHERE complexity_bucket IS NOT NULL
GROUP BY complexity_bucket
ORDER BY complexity_bucket;
