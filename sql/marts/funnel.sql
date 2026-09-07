-- 퍼널: 보유 → 플레이 기록 존재 → 반복 플레이 기록 (3단계).
-- Core User는 퍼널 단계가 **아니다** — 플레이 기록이 있는 유저를 total_numplays
-- 상위 20%로 자른 세그먼트 플래그일 뿐이다(01.EDA 8-1 참고). 통과 실패가 일어나는
-- 관문이 아니라 분위수 컷오프이므로, funnel_user_summary의 전환율(LAG) 계산에는
-- 섞지 않고 별도 segment 컬럼으로 분리한다. 컷오프 값은 데이터가 갱신되면 함께 움직인다.
--
-- "보유 → 평가 → 플레이 → 코어유저" 옛 4단계 정의는 폐기했다. user_rating에는
-- 시점이 없어 시간 순서 단계로 쓸 수 없고(01.EDA 8-3: 평가 참여율 최상위 분위의
-- 플레이 기록 비율이 오히려 41.4%로 최저), "가입 → 소유" 전환율도 own=1로 고정
-- 수집해서 애초에 측정 불가하다(PLAN.md §4-2, 생존편향).
--
-- "플레이"가 아니라 "플레이 기록"이라 부르는 이유(01.EDA 8-0에서 실측 검증):
-- numplays는 유저가 BGG에 직접 남긴 값이라 "안 했다"와 "기록 안 했다"가 섞일 수
-- 있는데, user_play(개별 플레이 로그, 730명)와 교차한 결과 numplays>0인데 로그가
-- 없는 경우는 0건, numplays=0인데 로그가 있는 경우는 0.49%뿐이었다 — numplays는
-- 사실상 "BGG에 남은 플레이 기록"과 동의어다. 이 컬럼명(has_play_record 등)이
-- is_player가 아닌 이유가 여기 있다.
--
-- 퍼널 SQL의 본질은 딱 두 단계다: (1) CASE WHEN/불리언 비교로 "이 행이 이 단계에
-- 도달했는가"를 표시 → (2) COUNTIF/COUNT(DISTINCT)로 그 표시를 숫자로 좁힌다.
-- 아래 두 마트가 이 패턴을 유저 축·아이템 축에 각각 적용한 것뿐이다.
--
-- 두 축이 필요한 이유: 유저 축(funnel_user)은 "누가 관측상 감소 구간에 있는가",
-- 아이템 축(funnel_item)은 "어떤 게임에서 감소 구간이 발생하는가"에 답한다.
-- 특히 아이템 축에 복잡도(averageweight)를 붙이면 "복잡도 높은 게임일수록
-- 소유만 하고 플레이 기록이 없는 비율이 높은가"까지 같은 쿼리로 나온다.
--
-- dedup 필수: stg_user_item에는 (user_id, objectid) 중복 13,861쌍이 있다(같은
-- 게임을 다른 시점에 다시 기록한 행 — collection.py/thing.py 재수집 시 API가
-- 갱신된 스냅샷을 또 반환해서 생긴다, 실측: 01.EDA 4-1). 중복 행의 numplays는
-- 행 사이에서 100% 동일하지만(어떤 dedup 규칙을 써도 SUM(numplays)는 같다),
-- dedup 없이 그대로 두면 동일한 값이 중복 카운트돼 2,944명 중 678명의
-- numplays가 평균 110.9회 부풀려진다(최대 +5,678회). 갈리는 건 user_rating뿐
-- (867쌍 값 충돌, 3,222쌍 일부만 채워짐) — 최신 행만 남기면 rating 1,914건이
-- 사라지므로, 최신 행을 기준으로 하되 user_rating은 최신 non-null 값으로
-- 백필한다(01.EDA 4-1 확정 규칙).
--
-- 3,000명 분모: funnel_user는 stg_user_info를 기준 테이블로 LEFT JOIN해
-- 컬렉션이 0건인 56명도 "1단계 미도달"로 명시적으로 포함시킨다.
--
-- 실행: bq query --use_legacy_sql=false --project_id=$GCP_PROJECT_ID < sql/marts/funnel.sql

-- ============================================================
-- funnel_user — 유저 축: user_info 3,000명 기준 1행. 어느 단계까지 갔는가.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.funnel_user` AS
WITH latest_row AS (
  -- (user_id, objectid)당 최신 행(lastmodified 최댓값) 하나만 남긴다. GROUP BY로
  -- 먼저 접으면 dedup 전 상태로 SUM/COUNTIF가 실행되므로, 반드시 집계보다 앞서야 한다.
  SELECT user_id, objectid, user_rating, numplays, lastmodified
  FROM `bgg_staging.stg_user_item`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id, objectid ORDER BY lastmodified DESC) = 1
),
latest_rating AS (
  -- user_rating만 별도로 "최신 non-null 값"을 구해 latest_row의 NULL을 백필한다
  -- (최신 행 자체는 rating이 비어 있어도, 더 이전 행에 값이 있으면 그걸 쓴다).
  SELECT user_id, objectid, user_rating AS latest_nonnull_rating
  FROM `bgg_staging.stg_user_item`
  WHERE user_rating IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id, objectid ORDER BY lastmodified DESC) = 1
),
deduped_user_item AS (
  SELECT
    l.user_id, l.objectid, l.numplays,
    COALESCE(l.user_rating, r.latest_nonnull_rating) AS user_rating
  FROM latest_row l
  LEFT JOIN latest_rating r USING (user_id, objectid)
),
user_stats AS (
  -- deduped_user_item도 유저×게임(행 하나 = 소유한 게임 하나)이라 유저 단위로
  -- 다시 접어야 한다. COUNTIF는 조건을 만족하는 행 수를 세는 COUNT의 사촌 —
  -- 여기선 "이 유저가 평가한 게임이 하나라도 있는가"만 필요해서 0보다 큰지만 본다.
  SELECT
    user_id,
    COUNTIF(user_rating IS NOT NULL) AS n_rated,
    COUNT(*) AS n_owned,
    SUM(numplays) AS total_numplays,
    COUNTIF(numplays >= 2) AS n_repeat_games
  FROM deduped_user_item
  GROUP BY user_id
),
core_cutoff AS (
  -- Core User(세그먼트) = "플레이 기록이 있는 유저" 중 numplays 합계 상위 20%.
  -- 컷오프 숫자를 직접 계산해서 하드코딩하지 않는다 — PERCENTILE_CONT 대신 정수
  -- 인덱스로 쓸 수 있는 APPROX_QUANTILES(x, 100)[OFFSET(80)]로 80번째 백분위수
  -- (=상위 20% 경계)를 구함. WHERE total_numplays > 0로 "플레이 기록 없는 유저"를
  -- 분모에서 미리 뺀다 — 안 그러면 절반 가까이가 0이라 분포 자체가 왜곡된다.
  SELECT APPROX_QUANTILES(total_numplays, 100)[OFFSET(80)] AS cutoff
  FROM user_stats
  WHERE total_numplays > 0
)
SELECT
  info.user_id,
  s.user_id IS NOT NULL AS is_owner,                                   -- 1단계: 컬렉션 보유
  COALESCE(s.total_numplays, 0) > 0 AS has_play_record,                -- 2단계: 플레이 기록 존재
  COALESCE(s.n_repeat_games, 0) > 0 AS has_repeat_play_record,         -- 3단계: 반복 플레이 기록
  COALESCE(s.total_numplays, 0) >= (SELECT cutoff FROM core_cutoff)
    AND COALESCE(s.total_numplays, 0) > 0 AS is_core_user,             -- 세그먼트(퍼널 아님)
  s.n_rated,                                                            -- engagement 보조 컬럼(퍼널 단계 아님)
  s.n_owned,
  s.total_numplays
FROM `bgg_staging.stg_user_info` info
LEFT JOIN user_stats s USING (user_id);

-- 단계별 인원수·직전 대비 전환율 요약(리포트에 바로 쓰는 표). Core User는 stage가
-- 아니라 segment 행으로 따로 둬서 LAG 기반 전환율 계산에 섞이지 않게 한다.
CREATE OR REPLACE VIEW `bgg_mart.funnel_user_summary` AS
WITH stage_counts AS (
  SELECT 1 AS stage_order, '1.컬렉션 보유' AS stage, COUNTIF(is_owner) AS n FROM `bgg_mart.funnel_user`
  UNION ALL
  SELECT 2, '2.플레이 기록 존재', COUNTIF(has_play_record) FROM `bgg_mart.funnel_user`
  UNION ALL
  SELECT 3, '3.반복 플레이 기록', COUNTIF(has_repeat_play_record) FROM `bgg_mart.funnel_user`
)
SELECT
  stage_order,
  stage,
  n,
  -- LAG로 "바로 이전 행의 n"을 끌어와 직전 대비 전환율을 구한다. 윈도우 함수를
  -- 안 쓰면 이 표를 3번 따로 짜서 손으로 나눠야 한다.
  SAFE_DIVIDE(n, LAG(n) OVER (ORDER BY stage_order)) AS conversion_from_prev,
  SAFE_DIVIDE(n, FIRST_VALUE(n) OVER (ORDER BY stage_order)) AS conversion_from_stage1
FROM stage_counts
ORDER BY stage_order;

-- Core User는 퍼널 단계가 아니므로 별도 뷰로 분리 — "n_core / n_players"만 보여주고
-- 전체 대비/직전 대비 같은 퍼널 전환율 칼럼은 아예 두지 않는다(혼동 방지).
CREATE OR REPLACE VIEW `bgg_mart.funnel_user_core_segment` AS
SELECT
  COUNTIF(has_play_record) AS n_players,
  COUNTIF(is_core_user) AS n_core_users,
  SAFE_DIVIDE(COUNTIF(is_core_user), COUNTIF(has_play_record)) AS core_share_of_players
FROM `bgg_mart.funnel_user`;

-- ============================================================
-- funnel_item — 아이템 축: 유저×게임 한 쌍이 한 행(=stg_user_item과 동일 단위,
-- dedup 후 기준). 복잡도(averageweight)를 붙여 "복잡도별 소유→플레이 기록 비율"을
-- 바로 뽑는다.
-- ============================================================
CREATE OR REPLACE TABLE `bgg_mart.funnel_item` AS
WITH latest_row AS (
  SELECT user_id, objectid, user_rating, numplays, lastmodified
  FROM `bgg_staging.stg_user_item`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id, objectid ORDER BY lastmodified DESC) = 1
),
latest_rating AS (
  SELECT user_id, objectid, user_rating AS latest_nonnull_rating
  FROM `bgg_staging.stg_user_item`
  WHERE user_rating IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id, objectid ORDER BY lastmodified DESC) = 1
),
deduped_user_item AS (
  -- funnel_user와 같은 dedup+백필 — 여기서 안 하면 funnel_item_by_complexity의
  -- COUNT(*)/COUNTIF(has_play_record)가 중복 행만큼 그대로 부풀려진다.
  SELECT
    l.user_id, l.objectid, l.numplays,
    COALESCE(l.user_rating, r.latest_nonnull_rating) AS user_rating
  FROM latest_row l
  LEFT JOIN latest_rating r USING (user_id, objectid)
)
SELECT
  ui.user_id,
  ui.objectid,
  ui.user_rating IS NOT NULL AS is_rated,
  ui.numplays > 0 AS has_play_record,
  ui.numplays >= 2 AS has_repeat_play_record,
  s.averageweight,
  CASE
    -- averageweight=0은 "매우 가벼움"이 아니라 "아무도 복잡도를 채점 안 함"이다
    -- (item_info.rank의 "Not Ranked"와 같은 성격의 결측 마커 — 실측 확인:
    -- stg_item_stats에서 averageweight=0인 게임이 12,317개). 0을 그대로 두면
    -- 미채점 게임이 전부 "가벼움" 버킷으로 잘못 몰려 그 버킷의 비율이 왜곡된다.
    WHEN s.averageweight IS NULL OR s.averageweight = 0 THEN NULL
    WHEN s.averageweight < 2.0 THEN '1.가벼움(<2.0)'
    WHEN s.averageweight < 2.5 THEN '2.라이트(2.0-2.5)'
    WHEN s.averageweight < 3.0 THEN '3.미들(2.5-3.0)'
    WHEN s.averageweight < 3.5 THEN '4.미들헤비(3.0-3.5)'
    ELSE '5.헤비(>=3.5)'
  END AS complexity_bucket
FROM deduped_user_item ui
LEFT JOIN `bgg_staging.stg_item_stats` s USING (objectid);

-- 복잡도 구간별 소유→플레이 기록 비율(09 퍼널 후보 변수 근거표).
CREATE OR REPLACE VIEW `bgg_mart.funnel_item_by_complexity` AS
SELECT
  complexity_bucket,
  COUNT(*) AS n_owned,
  COUNTIF(has_play_record) AS n_with_play_record,
  SAFE_DIVIDE(COUNTIF(has_play_record), COUNT(*)) AS play_record_rate,
  COUNTIF(has_repeat_play_record) AS n_with_repeat_play_record,
  SAFE_DIVIDE(COUNTIF(has_repeat_play_record), COUNT(*)) AS repeat_play_record_rate
FROM `bgg_mart.funnel_item`
WHERE complexity_bucket IS NOT NULL
GROUP BY complexity_bucket
ORDER BY complexity_bucket;
