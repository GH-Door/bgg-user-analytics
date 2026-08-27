-- 코호트 리텐션 — 실측(user_play 기반), Proxy(lastlogin) 폐기.
--
-- 중요한 제약 2가지, 반드시 리포트에 명시할 것:
--   1. BGG user API는 가입 "연도"만 준다(월/일 없음, 실측 확인 —
--      fixtures/user_fagentu007.xml에 <yearregistered value="2014"/>뿐).
--      그래서 원래 계획한 "월별 코호트"는 애초에 불가능하고, 여기는
--      "가입연도 코호트 × 연 단위 경과(year_offset)"로 리텐션을 본다.
--   2. 이 마트의 모집단은 전체 2,954명이 아니라 plays 표집 913명뿐이다
--      (docs/sampling_design.md의 코호트별 층화 표본). 분모를 stg_user_info
--      전체가 아니라 stg_plays_sample로 잡는 이유가 이거다.
--
-- SQL은 여기까지만 한다 — "코호트연도 × 경과년수 → 활성유저수"라는 **긴
-- 포맷(long format)**의 집계표를 만드는 게 SQL의 일(GROUP BY 2개, 어렵지 않음).
-- 이 표를 "가로 축=경과년수, 세로 축=코호트연도"인 리텐션 매트릭스로 펼치고
-- %로 정규화해서 히트맵으로 그리는 건 pandas.pivot_table()이 훨씬 자연스럽다
-- (jupyter/cohort_retention.ipynb에서 이어서 — SQL 긴 포맷을 굳이 SQL 안에서
-- PIVOT하면 경과년수 개수만큼 컬럼을 손으로 나열해야 해서 오히려 더 복잡해진다).
--
-- 실행: bq query --use_legacy_sql=false --project_id=$GCP_PROJECT_ID < sql/marts/cohort.sql

-- ============================================================
-- cohort_size — 가입연도별 관측 대상 수(분모). stg_user_play가 아니라
-- stg_plays_sample에서 센다 — 플레이 기록이 0건인 유저도 "관측했지만 활동
-- 없음"으로 분모엔 들어가야 하기 때문(빠지면 리텐션이 실제보다 높게 나온다).
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.cohort_size` AS
SELECT
  yearregistered AS cohort_year,
  COUNT(*) AS cohort_size
FROM `bgg_staging.stg_plays_sample`
WHERE yearregistered IS NOT NULL
GROUP BY cohort_year;

-- ============================================================
-- cohort_retention_long — (코호트연도, 경과년수)별 활성 유저 수 + 리텐션율.
-- year_offset=0은 "가입한 바로 그 해에도 플레이 기록이 있다"는 뜻.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.cohort_retention_long` AS
WITH play_years AS (
  -- 유저 하나가 한 해에 플레이를 여러 번 기록했어도 "그 해에 활성이었다"는
  -- 사실은 한 번만 세면 되므로 DISTINCT.
  SELECT DISTINCT
    user_id,
    EXTRACT(YEAR FROM play_date) AS play_year
  FROM `bgg_staging.stg_user_play`
  WHERE play_date IS NOT NULL
),
active AS (
  SELECT
    s.yearregistered AS cohort_year,
    py.play_year,
    py.play_year - s.yearregistered AS year_offset,
    COUNT(DISTINCT py.user_id) AS n_active_users
  FROM play_years py
  JOIN `bgg_staging.stg_plays_sample` s USING (user_id)
  WHERE py.play_year >= s.yearregistered  -- 가입 이전 플레이는 논리적으로 불가능
                                            -- (있다면 yearregistered 자체가 부정확한
                                            -- 이상치 — 있는지 검증 쿼리는 아래 참고)
  GROUP BY cohort_year, play_year, year_offset
)
SELECT
  a.cohort_year,
  a.year_offset,
  a.n_active_users,
  cs.cohort_size,
  SAFE_DIVIDE(a.n_active_users, cs.cohort_size) AS retention_rate
FROM active a
JOIN `bgg_mart.cohort_size` cs USING (cohort_year)
ORDER BY cohort_year, year_offset;

-- 검증용: 가입 이전 플레이 기록(있으면 안 됨) — 0행이어야 정상.
-- SELECT s.user_id, s.yearregistered, EXTRACT(YEAR FROM p.play_date) AS play_year
-- FROM `bgg_staging.stg_user_play` p
-- JOIN `bgg_staging.stg_plays_sample` s USING (user_id)
-- WHERE EXTRACT(YEAR FROM p.play_date) < s.yearregistered;
