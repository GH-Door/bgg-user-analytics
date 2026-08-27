# 2024 팀 프로젝트 데이터셋 vs 신규 수집 데이터셋 비교

이 문서는 이전 팀 프로젝트(2024년 7월 수집, 이 저장소 밖에 로컬로 보관 — 재현 불가능한 원본이라 `data/` 원칙상 여기 포함하지 않는다)의 CSV + 수집/EDA 노트북과, 이번 프로젝트에서 새로 설계한 수집 스키마(`src/collectors/*.py`)의 피처를 테이블 단위로 대조한다. 목적은 두 가지다.

1. 폴백(2024 데이터)으로 먼저 파이프라인을 완성할 때, staging 단계에서 어떤 컬럼이 있고 없는지 미리 파악
2. 재수집 시 "무엇을 새로 얻는지 / 무엇을 의도적으로 버리는지"를 근거와 함께 남김

참고한 2024 원본: `data/*.csv` 5개 + `jupyter/Data collection/*.ipynb`(수집 로직) + `jupyter/EDA.ipynb`, `jupyter/Cluster.ipynb`, `jupyter/Hard_user/EDA.ipynb`(피처 활용 방식).

**신규 필드 검증 방법 (08/16)**: BGG API 토큰이 아직 없어 이번 세션에서 직접 인증 호출은 못 했다. 대신 오픈소스 BGG API 파이썬 래퍼 [`lcosmin/boardgamegeek`](https://github.com/lcosmin/boardgamegeek)의 테스트 픽스처(`test/xml/*`)를 확인했다 — 이건 실제로 BGG 서버가 응답한 원문 XML을 캡처해 저장해둔 것이라, 문서가 아니라 **실측 응답**에 가까운 증거다. `item_stats`(wishing/wanting/trading/owned/numcomments/numweights/averageweight), `item_rank`(type/friendlyname/value/bayesaverage, `"Not Ranked"` 문자열 포함), `item_link`(type/id/value), `user_play`(id/date/quantity/length/incomplete/location, 페이지네이션 `total` 속성), thing API 콤마 배치 호출(`id=31260,283`)까지 전부 실제 응답에서 확인됨. `collection_collector.py`의 XML 경로(`stats/rating/average` 등)도 실제 구조와 정확히 일치함을 재확인했다. 다만 이건 다른 애플리케이션이 과거에 캡처한 응답이라 **BGG가 스키마를 바꾸지 않았다는 가정** 위에 있다 — 토큰 발급 후 첫 실제 호출로 최종 재확인 필요 (PLAN.md TODO에 반영).

---

## 1. 테이블 단위 요약

| 2024 파일 (행수) | 신규 테이블 | 관계 |
|---|---|---|
| `user_info.csv` (10,754) | `user_info` | 컬럼 축소 (§2-1) |
| `user_list.csv` (194,643) | (수집 대상 목록, 그대로 재사용 예정) | 동일 역할 |
| `user_item.csv` (1,827,152) | `user_item` + `item_info` | collection API 응답을 2개 테이블로 분리 (동일). 최초 `wc -l` 집계치(197만)는 `comment` 필드 내 개행 때문에 부정확했음 — `csv`/`pandas`로 재확인(08/16, `fallback_adapter.py` 테스트 중 발견) |
| `item_info.csv` (52,290) | `item_info` | 거의 동일 + `rank`가 대표 1건만 (subtype별은 `item_rank`로 분리) |
| `item_details.csv` (29,449) | `item_details` + `item_stats` + `item_link` (신규 정규화) | link 컬럼 5개를 long 포맷 1개로 통합 |
| `국현user_item-2.csv` / `국현user_item_info-2.csv` | — | 개인 부분 수집본, 스키마는 `item_info`/`user_item`과 동일. 최종 병합본에 흡수된 것으로 보여 신규 설계에 별도 반영 안 함 |
| `item_feature.csv` (29,213행 × 약 470컬럼) | — | DS 파생 산출물(카테고리/메커닉/테마/랭크를 정규화 가중치로 원-핫). §4에서 별도 설명 |
| `item_cluster.csv` (29,213) | — | 위 피처로 만든 UMAP 클러스터 라벨. DS 산출물, 이번 범위 밖 |
| — | `user_play` (신규) | 기존에 없던 테이블. §3 참고 |

---

## 2. 컬럼 단위 diff

### 2-1. `user_info`

| 2024 컬럼 | 신규 `user_info` | 비고 |
|---|---|---|
| `user_id` | ✅ | |
| `firstname`, `lastname` | ❌ | 분석에 안 씀, 개인식별 정보라 수집 범위 축소 |
| `avatarlink` | ❌ | 프로필 이미지 URL, 분석 무관 |
| `yearregistered` | ✅ | 퍼널/코호트 핵심 피처 |
| `lastlogin` | ✅ | Proxy 코호트 계산용 (한계는 PLAN.md §10) |
| `stateorprovince` | ✅ | |
| `country` | ✅ | |
| `traderating` | ✅ | |
| `webaddress` | ❌ | 개인 홈페이지 URL, 분석 무관 |
| `xboxaccount`, `wiiaccount`, `psnaccount`, `battlenetaccount`, `steamaccount` | ❌ | 2024 EDA에서 국가별 분포 정도만 참고용으로 훑어봤을 뿐 본 분석(퍼널/코호트/세그먼트)에 쓰이지 않음. 결측이 대부분이라 수집 비용 대비 가치 낮다고 판단해 제외 |

**요약**: 15개 → 6개. 분석에 실제로 쓰이는 피처만 남김 (개인식별/외부 계정 정보 제외).

### 2-2. `user_item` / `item_info` (collection API)

| 2024 컬럼 (`user_item.csv`) | 신규 `user_item` | 비고 |
|---|---|---|
| `user_id, objectid, name, user_rating, numplays, comment` | `user_id, objectid, user_rating, numplays, comment` | `name`은 `item_info`에 이미 있어 중복 저장 제거 (정규화) |

| 2024 컬럼 (`item_info.csv`) | 신규 `item_info` | 비고 |
|---|---|---|
| `objectid, objecttype, subtype, name, yearpublished, image, thumbnail, maxplayers, minplayers, maxplaytime, minplaytime, numowned, playingtime, average, bayesaverage, stddev, rank` | `objectid, name, yearpublished, minplayers, maxplayers, minplaytime, maxplaytime, playingtime, numowned, average, bayesaverage, stddev, rank` | `objecttype`(항상 "thing"), `subtype`(수집 단계에서 이미 boardgame으로 필터링), `image`, `thumbnail`은 분석에 안 씀 → 제외 |

**`rank`의 의미 차이(중요)**: 2024는 collection 응답의 대표 rank 1개만 저장했다. 신규 설계도 `item_info.rank`는 동일하게 대표 1개만 두지만, thing API에서 **subtype별 전체 순위**(`Strategy Game Rank`, `Family Game Rank` 등)를 `item_rank` 테이블로 별도 확보한다 — 2024 데이터에는 없던 정보.

### 2-3. `item_details` → `item_details` + `item_stats` + `item_link` (신규 분리)

| 2024 컬럼 (`item_details.csv`) | 신규 위치 | 비고 |
|---|---|---|
| `objectid, name, minage, description, avg_weights` | `item_details` | 동일 |
| `category, mechanic, family, expansion, accessory, implementation, designer, artist, publisher` | `item_link` (long 포맷: `objectid, link_type, ref_id, value`) | 2024는 `"[('1050', 'Ancient'), ...]"` 같은 **파이썬 튜플 문자열**로 저장되어 SQL에서 재파싱이 필요했다. 신규는 수집 단계에서부터 행 단위로 분리해 저장 — PLAN.md §4-4 결함 목록에 없던 항목이지만 실질적으로 가장 큰 스키마 개선점 |
| `rating_cnt` | `item_stats.usersrated` (또는 `numcomments`, thing API 응답 필드명과 1:1 매칭 재확인 필요) | 이름을 BGG 응답 원문 태그명으로 통일 |
| `type` (`"['Strategy Game Rank', 'Family Game Rank']"` 리스트 문자열) | `item_rank.rank_type` (long 포맷) | 마찬가지로 문자열 파싱 문제 해결 |
| *(없음)* | `item_stats`: `wanting, wishing, trading, owned, numcomments, numweights, averageweight` | **신규 확보.** 2024는 `avg_weights` 하나만 있었고 위시리스트 관련 수치가 전혀 없었다 — 기획서의 Play-to-Wish Ratio 가설은 2024 데이터만으로는 애초에 검증 불가능했다는 뜻. 같은 `thing?stats=1` 호출 응답에 이미 포함되어 있어 추가 API 비용 없이 확보 |

### 2-4. `user_play` (완전 신규 테이블)

2024 데이터에는 대응하는 파일이 전혀 없다. `plays` API를 아예 호출하지 않았다.

| 신규 컬럼 | 설명 |
|---|---|
| `play_id, user_id, objectid, play_date, quantity, length, incomplete, location` | 유저가 기록한 개별 플레이 로그(날짜 포함) |

**의미**: 2024 코호트 분석은 `lastlogin`(마지막 로그인 1개) 기반 Proxy로 근사할 수밖에 없었다. `user_play`가 있으면 가입월×실제 플레이월 조합으로 **진짜 월별 코호트 리텐션**을 계산할 수 있다 — PLAN.md §4-3에 기록한 결정의 데이터적 근거.

---

## 3. 이번에 가져가지 않는 것 (2024에는 있었음)

- **개인식별/외부 계정 정보**: `firstname`, `lastname`, `avatarlink`, `webaddress`, 게임기 계정 5종 (§2-1)
- **표시용 메타데이터**: `image`, `thumbnail` (분석에 안 씀)
- **DS 파생 산출물**: `item_feature.csv`(카테고리/메커닉/테마/랭크를 정규화 가중치로 인코딩한 약 470컬럼 원-핫 행렬), `item_cluster.csv`(그 위에서 만든 UMAP 클러스터), `Soft_User_TOP*.csv` / `Hard_User_TOP*.csv`(ALS/BPR/VAE 추천 결과) — 이번 프로젝트는 추천 모델링을 배제하고 SQL 기반 분석에 집중하기로 했으므로(PLAN.md §"DA스럽게 만드는 장치") 재현하지 않는다. 다만 `item_feature.csv`가 `item_link`를 원-핫으로 펼친 것과 같은 정보이므로, 필요해지면 신규 `item_link` 테이블에서 언제든 동일하게 파생시킬 수 있다.
- **`국현user_item-2.csv` / `국현user_item_info-2.csv`**: 개인 부분 수집본. 최종 병합 파일(`user_item.csv`, `item_info.csv`)에 흡수된 것으로 보여 별도 대응 테이블을 만들지 않는다.

## 4. 이번에 새로 얻는 것

- **`item_stats`의 위시/원트/트레이딩 수치** (`wishing, wanting, trading, owned, numcomments, numweights`) — 기획서의 Play-to-Wish Ratio 가설을 실제로 검증 가능하게 만드는 핵심 데이터. 2024 데이터로는 이 가설을 애초에 검증할 수 없었다.
- **`item_rank`의 subtype별 순위 전체** — 2024는 대표 순위 1개뿐이었다.
- **`item_link`의 정규화된 category/mechanic/family/designer/publisher** — 2024는 튜플 문자열이라 분석 전 파싱이 필요했다.
- **`user_play` 실제 플레이 로그(샘플)** — 코호트 분석을 Proxy에서 실측으로 승격.
- **`user_item`의 `status` 플래그**(`own, prevowned, fortrade, want, wanttoplay, wanttobuy, wishlist, wishlistpriority, preordered, lastmodified`, 08/16 추가) — 2024에도 없던 필드다. 이미 부르는 collection API 응답에 공짜로 포함되어 있는데 2024도, 이번 신규 설계 초안도 놓치고 있었다. `rating`/`numplays`보다 세밀한 암묵적 피드백 신호(예: "소유했지만 `fortrade`로 표시" = 부정적 신호, "`wanttoplay`=1" = 관심 있지만 아직 안 함)라 향후 추천 시스템을 붙일 때 유용. 2024 데이터로는 백필 불가 — `own`만 "1"로 채우고 나머지는 폴백 기간 동안 빈 값.

---

## 5. 참고: 2024 노트북에서 발견한 세그먼트 정의 방식 (참고용, 채택 안 함)

`jupyter/Hard_user/EDA.ipynb`에서 헤비유저("hard_user")를 유저별 **평점 개수(`rating_count`) 11~109건** 구간으로 정의했다 (`hard_user['rating_count'].transform('count')` 후 필터링). 이번 프로젝트는 PLAN.md §8에서 `numplays` 총합 기준 3분위로 세그먼트를 정의하기로 했는데, 이는 의도적으로 다른 기준이다 — 평점 개수는 "얼마나 많은 게임을 접했는가"에 가깝고, `numplays`는 "실제로 얼마나 많이 플레이했는가"에 더 가깝다고 판단했기 때문. 두 정의 중 무엇이 더 적절한지는 실제 데이터 분포를 보고 `docs/metrics.md`에서 최종 확정한다.

또한 2024 노트북은 동명 게임 처리를 위해 `item_info`를 `name` 기준으로 `drop_duplicates`했다(연도 최신 것만 남김). 신규 설계는 애초에 `objectid`가 유일 키이므로 이 문제 자체가 발생하지 않는다 — PLAN.md §4-4 결함 #7과 같은 맥락.
