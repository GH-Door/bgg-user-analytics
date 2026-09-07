# 데이터 품질 체크리스트 결과

실행일: 2026-08-16 · 대상: `bgg-user-analytics.bgg_raw` (2024 폴백 데이터, `fallback_adapter.py`로 변환 후 적재) · 쿼리: `sql/staging/data_quality_checks.sql`

> ⚠️ **이 결과는 2024 폴백 데이터 기준이다.** 재수집 후 실제 데이터로 raw가 교체되면 같은 SQL을 재실행해 재검증해야 한다. 특히 §5(own 필터)와 §6(어댑터 파싱)은 폴백 데이터에서만 의미가 제한적인 체크다.
>
> **✅ 09/08 업데이트 — 위 경고가 실현됨.** 재수집 후 실측 결과는 이 문서를 다시 실행하는 대신 `jupyter/01.EDA.ipynb`의 데이터 품질 검증(1~4절)에 반영돼 있다. 아래 §1 커버리지 수치가 특히 크게 달라졌다 — 재수집 데이터는 `item_info`↔`item_details`/`item_stats`/`item_link` 3테이블 조인 일치율이 **93.8%**(80,127/85,442)로, 2024 폴백의 56.3%와는 전혀 다르다. §4 결측률도 재수집 데이터로는 `user_rating` 47.2%(01.EDA 1-5), `country` 18.1%(01.EDA 1-2)로 확인돼 아래 표의 2024 수치와 차이가 있다. §5(own=1 필터)·§6(어댑터 파싱)은 폴백 전용 체크라 재수집 이후엔 해당 없음. 이 문서는 "2024 폴백 데이터로 파이프라인을 먼저 완성했다"는 히스토리 기록으로 남기고, 최신 수치가 필요하면 위 `01.EDA.ipynb`를 참고할 것.

## 요약 — 가장 중요한 발견 2가지

1. **`item_info`의 44%(22,841개 게임)가 `item_details`/`item_link`에 대응 데이터가 없다.** 즉 복잡도(`avg_weights`)나 카테고리/메커닉 정보가 없는 게임이 절반 가까이 된다. `item_info`와 `item_details`/`item_link`을 조인하는 모든 분석(복잡도 기반 세그먼트, 카테고리 트렌드)은 **반드시 LEFT JOIN**을 쓰고 커버리지를 명시해야 한다 — INNER JOIN을 쓰면 게임 절반이 조용히 사라진다.
2. **결측이 예상보다 큰 컬럼 몇 개**: `user_rating` 47.8% 결측(소유는 했지만 평가 안 한 게임 — 정상적인 암묵적 피드백 패턴), `comment` 89.5% 결측(자유 텍스트라 당연), `stateorprovince` 52.3% 결측. 전부 "잘못됨"이 아니라 "이런 분포다"로 받아들이고 지표 설계에 반영해야 한다.

부수 발견: 결측률 체크를 처음에 `컬럼 = ''`로만 짰다가 전부 0%로 나와서 이상해서 재확인했는데, **원본 CSV의 빈 필드가 pandas에서 NaN → BigQuery 적재 시 빈 문자열이 아니라 실제 NULL**로 들어간다는 걸 발견했다. SQL을 `IS NULL OR = ''`로 고쳐서 재실행했다 (아래 §4).

---

## 1. 유일성

| 체크 | 결과 | 판정 |
|---|---|---|
| `user_info.user_id` 중복 | 0건 | ✅ |
| `item_info.objectid` 중복 | 0건 | ✅ |
| `user_item` (user_id, objectid) 중복 쌍 | 0건 | ✅ (정보성 체크였는데 실제로도 0) |

## 2. 참조 무결성

| 체크 | 결과 | 판정 | 후속 조치 |
|---|---|---|---|
| `user_item.objectid` ⊆ `item_info.objectid` | orphan 825건 (0.045%) | ⚠️ | 규모가 작아 원인 추적 안 함 — staging에서 LEFT JOIN으로 자연 배제 |
| `item_link.objectid` ⊆ `item_info.objectid` | orphan 0건 | ✅ | |
| `item_details` ↔ `item_info` 모집단 일치 | `item_details`에만 있는 것 0건 / `item_info`에만 있는 것 **22,841건** | ❌ (요약 §1 참고) | 모든 조인에서 LEFT JOIN 필수, 커버리지(52,290분의 29,449 = 56.3%) 리포트에 명시 |

## 3. 값 범위

| 체크 | 결과 | 판정 |
|---|---|---|
| `user_rating` 1~10 범위 이탈 | 0건 | ✅ |
| `avg_weights` 0~5 범위 이탈 | 0건 | ✅ |
| `yearpublished` 1900~2027 이탈 | 다수(1500, 1000, 1890 등) | ℹ️ 오류 아님 — 체스·바둑 등 전통 게임의 실제 출시연도. 애초에 잡은 범위(1900~)가 틀렸음, staging에서 하한 제거 |
| 숫자 컬럼(`numowned`/`average`/`bayesaverage`/`stddev`/`rank`) CAST 실패 | 전부 0건 | ✅ staging에서 안전하게 캐스팅 가능 |

## 4. 결측률

| 테이블.컬럼 | 결측률 | 비고 |
|---|---|---|
| `user_info.country` | 28.8% | |
| `user_info.stateorprovince` | 52.3% | |
| `user_info.yearregistered`/`lastlogin`/`traderating` | 0% | |
| `item_info.rank` (blank) | 0% | |
| `item_info.rank = "Not Ranked"` | 54.9% | 절반 이상이 비랭크 게임 — BGG 특성상 정상 |
| `user_item.user_rating` | 47.8% | 소유했지만 미평가 — 정상 패턴, "결측=미평가"로 지표 설계에 반영 |
| `user_item.comment` | 89.5% | 자유 텍스트, 정상 |
| `user_item.own` | 0% | 폴백 어댑터가 전부 채움 |
| `user_item.want`/`wishlist`/`lastmodified` | **100%** | 2024엔 없던 필드라 폴백에서 백필 불가 — 재수집 후에만 채워짐 |

## 5. own=1 필터 확인

| own 값 | 행수 |
|---|---|
| 1 | 1,827,152 (100%) |

⚠️ 폴백 데이터는 `fallback_adapter.py`가 `own="1"`을 채운 값이라 항상 100%다 — **이 체크는 재수집 후 실측 status로 다시 돌려야 의미가 있다.**

## 6. 어댑터 파싱 정합성 (`fallback_adapter.py` 검증)

| 체크 | 결과 | 판정 |
|---|---|---|
| `item_details`엔 있는데 `item_link`엔 한 건도 없는 objectid | 0건 | ✅ 튜플 문자열 파싱이 29,449개 게임 전부에서 정상 동작 |
| `item_link.ref_id` 숫자 아닌 값 | 0건 | ✅ |

---

## 다음 단계(`sql/staging/preprocessing.sql`)로 넘어갈 항목

1. 숫자 컬럼 STRING → INT64/FLOAT64 캐스팅 (안전 확인됨, §3)
2. `item_info.rank`: `"Not Ranked"` → NULL 처리 후 캐스팅
3. `item_details.yearpublished`(폴백 기간 100% NULL) → `item_info.yearpublished`로 COALESCE
4. `item_link` → `link_type`별 뷰(`item_category`, `item_mechanic` 등) 분리
5. `item_info` ↔ `item_details`/`item_link` 조인은 전부 LEFT JOIN, 커버리지 56.3% 명시
6. `user_item.user_rating` 결측을 "미평가"로 명확히 구분(0으로 채우지 않음 — 평점 0과 미평가는 다른 의미)
