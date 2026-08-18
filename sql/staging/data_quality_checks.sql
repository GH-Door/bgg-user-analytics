-- 데이터 품질 체크리스트 — bgg_raw 대상, staging 이전 검증.
-- 결과는 docs/data_quality.md에 기록한다. 2024 폴백 데이터 기준 실행분이며,
-- 재수집 후 실제 데이터로 교체되면 이 파일을 그대로 재실행해 재검증한다.
-- (own=1 체크와 어댑터 파싱 체크는 폴백 데이터 한정 항목 — 하단 주석 참고)

-- ============================================================
-- 1. 유일성
-- ============================================================

-- [1-1] user_info.user_id 중복 — 기대: 0행
SELECT user_id, COUNT(*) AS n
FROM `bgg-user-analytics.bgg_raw.user_info`
GROUP BY user_id
HAVING COUNT(*) > 1;

-- [1-2] item_info.objectid 중복 — 기대: 0행
SELECT objectid, COUNT(*) AS n
FROM `bgg-user-analytics.bgg_raw.item_info`
GROUP BY objectid
HAVING COUNT(*) > 1;

-- [1-3] user_item (user_id, objectid) 조합 중복 — 정보용(실패 판정 아님).
--       BGG는 한 유저가 같은 게임을 여러 카피 소유할 수 있어 중복이 있을 수 있다.
SELECT COUNT(*) AS duplicate_pairs
FROM (
  SELECT user_id, objectid
  FROM `bgg-user-analytics.bgg_raw.user_item`
  GROUP BY user_id, objectid
  HAVING COUNT(*) > 1
);

-- ============================================================
-- 2. 참조 무결성
-- ============================================================

-- [2-1] user_item.objectid ⊆ item_info.objectid — 기대: orphan 0행
SELECT COUNT(*) AS orphan_rows
FROM `bgg-user-analytics.bgg_raw.user_item` ui
LEFT JOIN `bgg-user-analytics.bgg_raw.item_info` ii USING (objectid)
WHERE ii.objectid IS NULL;

-- [2-2] item_link.objectid ⊆ item_info.objectid — 기대: orphan 0행
SELECT COUNT(*) AS orphan_rows
FROM `bgg-user-analytics.bgg_raw.item_link` il
LEFT JOIN `bgg-user-analytics.bgg_raw.item_info` ii USING (objectid)
WHERE ii.objectid IS NULL;

-- [2-3] item_details ↔ item_info 모집단 일치 확인 (양방향 차집합)
SELECT
  (SELECT COUNT(*) FROM `bgg-user-analytics.bgg_raw.item_details` d
     LEFT JOIN `bgg-user-analytics.bgg_raw.item_info` i USING (objectid)
     WHERE i.objectid IS NULL) AS in_details_not_info,
  (SELECT COUNT(*) FROM `bgg-user-analytics.bgg_raw.item_info` i
     LEFT JOIN `bgg-user-analytics.bgg_raw.item_details` d USING (objectid)
     WHERE d.objectid IS NULL) AS in_info_not_details;

-- ============================================================
-- 3. 값 범위
-- ============================================================

-- [3-1] user_rating 범위 이탈 (1~10 또는 N/A/빈값 외) — 상위 20건
SELECT user_rating, COUNT(*) AS n
FROM `bgg-user-analytics.bgg_raw.user_item`
WHERE user_rating NOT IN ('N/A', '')
  AND (SAFE_CAST(user_rating AS FLOAT64) IS NULL
       OR SAFE_CAST(user_rating AS FLOAT64) NOT BETWEEN 1 AND 10)
GROUP BY user_rating
ORDER BY n DESC
LIMIT 20;

-- [3-2] avg_weights 범위 이탈 (0~5 외)
SELECT avg_weights, COUNT(*) AS n
FROM `bgg-user-analytics.bgg_raw.item_details`
WHERE avg_weights != ''
  AND (SAFE_CAST(avg_weights AS FLOAT64) IS NULL
       OR SAFE_CAST(avg_weights AS FLOAT64) NOT BETWEEN 0 AND 5)
GROUP BY avg_weights
ORDER BY n DESC
LIMIT 20;

-- [3-3] yearpublished 이상값 (1900~2027 외)
SELECT yearpublished, COUNT(*) AS n
FROM `bgg-user-analytics.bgg_raw.item_info`
WHERE SAFE_CAST(yearpublished AS INT64) IS NULL
   OR SAFE_CAST(yearpublished AS INT64) NOT BETWEEN 1900 AND 2027
GROUP BY yearpublished
ORDER BY n DESC
LIMIT 20;

-- [3-4] 숫자 컬럼 CAST 실패 건수 — 기대: 전부 0
SELECT
  COUNTIF(numowned != '' AND SAFE_CAST(numowned AS INT64) IS NULL) AS numowned_cast_fail,
  COUNTIF(average != '' AND SAFE_CAST(average AS FLOAT64) IS NULL) AS average_cast_fail,
  COUNTIF(bayesaverage != '' AND SAFE_CAST(bayesaverage AS FLOAT64) IS NULL) AS bayesaverage_cast_fail,
  COUNTIF(stddev != '' AND SAFE_CAST(stddev AS FLOAT64) IS NULL) AS stddev_cast_fail,
  COUNTIF(rank != '' AND rank != 'Not Ranked' AND SAFE_CAST(rank AS INT64) IS NULL) AS rank_cast_fail
FROM `bgg-user-analytics.bgg_raw.item_info`;

-- ============================================================
-- 4. 결측률
-- ============================================================

-- [4-1] user_info 컬럼별 결측 비율
-- 주의: 원본 CSV의 빈 필드가 pandas에서 NaN → BigQuery 적재 시 실제 NULL이 된다.
-- 빈 문자열('')이 아니라 NULL로 들어가므로 반드시 IS NULL도 같이 확인해야 한다
-- (이 체크를 처음에 `= ''`로만 짰다가 결측이 전부 안 잡히는 걸 보고 고침).
SELECT
  ROUND(COUNTIF(yearregistered IS NULL OR yearregistered = '') / COUNT(*), 4) AS yearregistered_blank_rate,
  ROUND(COUNTIF(lastlogin IS NULL OR lastlogin = '') / COUNT(*), 4) AS lastlogin_blank_rate,
  ROUND(COUNTIF(country IS NULL OR country = '') / COUNT(*), 4) AS country_blank_rate,
  ROUND(COUNTIF(stateorprovince IS NULL OR stateorprovince = '') / COUNT(*), 4) AS stateorprovince_blank_rate,
  ROUND(COUNTIF(traderating IS NULL OR traderating = '') / COUNT(*), 4) AS traderating_blank_rate
FROM `bgg-user-analytics.bgg_raw.user_info`;

-- [4-2] item_info.rank 결측/미랭크 비율
SELECT
  ROUND(COUNTIF(rank IS NULL OR rank = '') / COUNT(*), 4) AS rank_blank_rate,
  ROUND(COUNTIF(rank = 'Not Ranked') / COUNT(*), 4) AS rank_not_ranked_rate
FROM `bgg-user-analytics.bgg_raw.item_info`;

-- [4-3] user_item comment/status 결측 비율
SELECT
  ROUND(COUNTIF(user_rating IS NULL OR user_rating = '') / COUNT(*), 4) AS user_rating_blank_rate,
  ROUND(COUNTIF(comment IS NULL OR comment = '') / COUNT(*), 4) AS comment_blank_rate,
  ROUND(COUNTIF(own IS NULL OR own = '') / COUNT(*), 4) AS own_blank_rate,
  ROUND(COUNTIF(want IS NULL OR want = '') / COUNT(*), 4) AS want_blank_rate,
  ROUND(COUNTIF(wishlist IS NULL OR wishlist = '') / COUNT(*), 4) AS wishlist_blank_rate,
  ROUND(COUNTIF(lastmodified IS NULL OR lastmodified = '') / COUNT(*), 4) AS lastmodified_blank_rate
FROM `bgg-user-analytics.bgg_raw.user_item`;

-- ============================================================
-- 5. own=1 필터 확인
-- ⚠️ 폴백 데이터는 fallback_adapter.py가 own="1"을 채운 값이라 항상 100% 통과한다.
--    재수집 후 실측 status로 재검증해야 의미가 있다.
-- ============================================================

SELECT own, COUNT(*) AS n
FROM `bgg-user-analytics.bgg_raw.user_item`
GROUP BY own;

-- ============================================================
-- 6. 어댑터 파싱 정합성 (fallback_adapter.py 검증, 폴백 데이터 한정)
-- ============================================================

-- [6-1] item_details엔 있는데 item_link엔 한 건도 없는 objectid 수
SELECT COUNT(*) AS items_without_any_link
FROM `bgg-user-analytics.bgg_raw.item_details` d
LEFT JOIN (SELECT DISTINCT objectid FROM `bgg-user-analytics.bgg_raw.item_link`) l
  USING (objectid)
WHERE l.objectid IS NULL;

-- [6-2] item_link.ref_id가 숫자가 아닌 값 — 기대: 0행 (파싱 오류 의심)
SELECT ref_id, COUNT(*) AS n
FROM `bgg-user-analytics.bgg_raw.item_link`
WHERE SAFE_CAST(ref_id AS INT64) IS NULL
GROUP BY ref_id
ORDER BY n DESC
LIMIT 20;
