# Korean Bill Lifecycle - Master Data Plan

**Created**: 2026-03-21
**Status**: Phase 1 완료, Phase 2 수집 중 (22대 전체 17,256건)

---

## 1. 현재 데이터 구조

### 1-A. Master Bills Table (core, 1 row per bill)

| Column Group | Key Fields | Source | Status |
|-------------|------------|--------|--------|
| **Identifiers** | bill_id (PK), bill_no, age, bill_kind, bill_nm | BILLRCP + nzmimeepazxkubdpn | Collected |
| **Proposer** | ppsr_kind, proposer_text, rst_proposer, rst_mona_cd | nzmimeepazxkubdpn | Collected (의원발의만) |
| **Committee Review** | committee_nm, bdg_cmmt_dt, jrcmit_prsnt_dt, jrcmit_proc_dt, jrcmit_proc_rslt | BILLJUDGE | Collected |
| **Judiciary Review** | law_cmmt_dt, law_prsnt_dt, law_proc_dt, law_proc_rslt | BILLINFODETAIL | Phase 2 (수집 중) |
| **Plenary** | rgs_prsnt_dt, rgs_rsln_dt, rgs_conf_nm, rgs_conf_rslt | BILLINFODETAIL | Phase 2 (수집 중) |
| **Post-passage** | gvrn_trsf_dt, prom_dt, prom_no, prom_law_nm | BILLINFODETAIL | Phase 2 (수집 중) |
| **Vote Tally** | vote_total, vote_yes, vote_no, vote_abstain | ncocpgfiaoituanbr | Collected |
| **Derived** | status, passed, enacted, days_to_proc, days_to_committee | Computed | Computed |

### 1-B. Satellite Tables (1:N per bill)

| Table | Source | Rows (est.) | Status |
|-------|--------|-------------|--------|
| committee_meetings | BILLJUDGECONF | ~50,000 | Phase 2 (수집 중) |
| judiciary_meetings | BILLLWJUDGECONF | ~5,000 | Phase 2 (수집 중) |

### 1-C. 현재 통계 (Phase 1 기준, 22대)

```
Total bills:   17,205
 법률안:       16,907  (98.3%)
 기타:            298  (결의안 112, 동의안 54, 예산안 41, ...)

Proposer:
 의원:         16,231  (94.3%)
 위원장:          635  (3.7%)
 정부:            294  (1.7%)
 의장/기타:        45  (0.3%)

Status:
 계류중:       12,478  (72.5%)
 대안반영폐기:  3,101  (18.0%)
 원안가결:        977  (5.7%)
 수정가결:        422  (2.5%)
 기타:            227  (철회 146, 수정안반영폐기 39, 부결 33, 폐기 9)

Passage rate:   26.2% (대안반영 포함) / 8.1% (원안+수정 가결만)
Processing time: mean 210 days, median 171 days
```

---

## 2. 22대 완전 수집 체크리스트

### Phase 1 - Batch (완료)

| API | 이름 | 건수 | 비고 |
|-----|------|------|------|
| nzmimeepazxkubdpn | 의원발의법률안 | 16,142 | 22대 only, AGE 필터 정상 |
| BILLRCP | 접수목록 | 118,466 | **전체 대수 반환** (22대=4,719) |
| BILLJUDGE | 심사정보 | 35,165 | **17~22대 반환** (22대=3,859) |
| ncocpgfiaoituanbr | 의안별표결현황 | 1,286 | 22대 only |
| nzpltgfqabtcpsmai | 처리의안 | 4,421 | 22대 only |

**발견: BILLRCP/BILLJUDGE의 AGE 파라미터는 필터링하지 않음. ERACO 컬럼으로 사후 필터링 필요.**

### Phase 2 - Per-Bill (수집 중)

| API | 이름 | 대상 건수 | 예상 시간 |
|-----|------|-----------|----------|
| BILLINFODETAIL | 의안상세정보 | 17,256 | ~2.4h |
| BILLJUDGECONF | 위원회회의정보 | 17,256 | ~2.4h |
| BILLLWJUDGECONF | 법사위회의정보 | 17,256 | ~2.4h |

### Phase 3 - Integration

- [ ] Phase 2 완료 후 `python3 integrate.py` 재실행
- [ ] 전체 lifecycle 날짜 coverage 확인
- [ ] 최종 validation report 생성

---

## 3. 확장 로드맵

### Tier 1: 즉시 가능 (추가 API 호출 없음)

이미 수집된 BILLRCP (전 대수)와 BILLJUDGE (17~22대) 데이터를 활용.

| 확장 | 데이터 원천 | 추가 작업 | 결과물 |
|------|------------|----------|--------|
| **17~21대 기본 정보** | BILLRCP (ERACO 필터링) | integrate.py에 multi-age 로직 추가 | master_bills_all.parquet |
| **17~22대 심사정보** | BILLJUDGE (이미 전건) | 같은 ERACO 필터링 | 위원회별 처리 통계 6개 대수 |

### Tier 2: 추가 수집 필요 (Phase 2 반복)

| 확장 | BILL_ID 원천 | 추가 호출 수 | 예상 시간 |
|------|------------|-------------|----------|
| **21대 의원발의** | nzmimeepazxkubdpn AGE=21 | ~25,000 × 3 | ~10.4h |
| **20대 의원발의** | nzmimeepazxkubdpn AGE=20 | ~24,000 × 3 | ~10.0h |
| **19대 의원발의** | nzmimeepazxkubdpn AGE=19 | ~17,000 × 3 | ~7.1h |
| **17~18대** | nzmimeepazxkubdpn AGE=17,18 | ~12,000 × 3 | ~5.0h |

**총 확장 소요: ~32.5시간** (하루+반 정도). 백그라운드 수집으로 점진적 확장 가능.

### Tier 3: 외부 데이터 연동

| 데이터 | 소스 | 조인 키 | 용도 |
|--------|------|---------|------|
| **의원 메타데이터** | 열린국회정보 의원 API | MONA_CD / rst_mona_cd | 의원 정당, 선수, 지역구, 위원회 |
| **법안 원문 텍스트** | LIKMS 크롤링 (link_url) | BILL_ID | NLP 분석, 주제 분류 |
| **본회의 개별 투표** | 열린국회정보 표결 API | BILL_ID + MONA_CD | 의원별 투표 기록, ideal point |
| **공동발의자 목록** | member_list URL 크롤링 | BILL_ID | cosponsorship 네트워크 |
| **위원회 회의록** | Pharos API | 회의 ID | 법안별 심의 내용 텍스트 |

---

## 4. 기존 프로젝트 연동 계획

### 4-A. committee-witnesses-korea

**연결 방식**: 위원회 회의일 + 위원회명 기준 시간적 매칭
**활용**:
- 특정 법안이 논의된 위원회 회의에서의 질의 강도 측정
- 위원회별 법안 처리 효율과 oversight 강도의 관계
- `jrcmit_nm` (소관위) ↔ CW의 committee harmonized key 매칭

### 4-B. na-legislative-events-korea

**연결 방식**: BILL_ID 직접 조인 (이미 같은 데이터 소스)
**활용**:
- cosponsorship 네트워크에 bill outcome(passed/failed) 가중치 추가
- seminar cohosting → cosponsorship → bill passage의 인과 경로
- 현재 20~22대 → lifecycle DB로 17대까지 확장 가능

### 4-C. legislator-assets-korea

**연결 방식**: rst_mona_cd ↔ naas_cd (의원 코드)
**활용**:
- 부유한 의원의 법안 발의 패턴 (부동산 관련 법안 발의 빈도)
- 발언(speech) 뿐 아니라 발의(proposal) 행태까지 분석 확장
- bill_nm 텍스트에서 부동산 키워드 매칭

### 4-D. korean-politics-youtube

**연결 방식**: rst_proposer (의원 이름) 또는 MONA_CD ↔ channel_meta
**활용**:
- YouTube 활동과 입법 생산성의 관계
- 특정 법안의 YouTube 홍보 여부와 통과율

### 4-E. dual-office

**연결 방식**: 겸직 장관의 의원 시절 MONA_CD
**활용**:
- 겸직 전후 법안 발의 패턴 변화
- 겸직 장관 소관 위원회의 법안 처리 속도

---

## 5. 데이터 품질 관리

### 알려진 이슈

| 이슈 | 심각도 | 대응 |
|------|--------|------|
| BILLRCP/BILLJUDGE AGE 필터 미작동 | 중 | ERACO 컬럼으로 사후 필터링 (구현 완료) |
| PPSL_DT에 '0' 값 존재 (BILLRCP) | 낮음 | safe_date() 함수로 NaT 변환 (구현 완료) |
| 계류 법안 lifecycle 불완전 | 예상됨 | 진행 중인 법안이므로 정상. status='계류중'으로 표기 |
| BILLLWJUDGECONF 데이터 없는 법안 다수 | 예상됨 | 법사위 심사를 거치지 않는 법안 (정상) |
| BILLRCP 22대 카운트 < nzmimeepazxkubdpn | 중 | ERACO 태깅이 처리 완료 법안에만 적용되는 것으로 추정 |

### 정기 검증 항목

Phase 2 완료 후 실행할 검증:

```bash
python3 collect.py validate    # 수집 건수 확인
python3 integrate.py           # 마스터 DB 재구축
```

검증 항목:
1. BILLINFODETAIL 수집률: 17,256건 중 몇 건에 데이터가 있는지
2. 위원회 회의 coverage: 법안당 평균 회의 수
3. 법사위 회의 coverage: 법사위를 거친 법안 비율
4. lifecycle 완결성: 공포(prom_dt)까지 도달한 법안 수

---

## 6. 파일 구조

```
korean-bill-lifecycle/
├── collect.py                          # Phase 1+2 수집 스크립트
├── integrate.py                        # Phase 3 통합 스크립트
├── DATA_COLLECTION_STRATEGY.md         # 원본 전략 문서
├── MASTER_DATA_PLAN.md                 # 이 문서
├── logs/
│   ├── collect.log                     # 수집 로그
│   └── integrate.log                   # 통합 로그
└── data/
    ├── raw/                            # API 원본 응답 (parquet)
    │   ├── nzmimeepazxkubdpn_22.parquet
    │   ├── BILLRCP_22.parquet
    │   ├── BILLJUDGE_22.parquet
    │   ├── ncocpgfiaoituanbr_22.parquet
    │   ├── nzpltgfqabtcpsmai_22.parquet
    │   ├── BILLINFODETAIL_22.parquet       # Phase 2
    │   ├── BILLJUDGECONF_22.parquet        # Phase 2
    │   ├── BILLLWJUDGECONF_22.parquet      # Phase 2
    │   ├── phase1_meta_22.json
    │   └── phase2_checkpoint_22.json       # Resume 지점
    └── processed/                      # 분석용 최종 산출물
        ├── master_bills_22.parquet     # 마스터 테이블
        ├── master_bills_22.sqlite      # SQLite (indexed)
        ├── committee_meetings_22.parquet
        └── judiciary_meetings_22.parquet
```

---

## 7. 연구 활용 우선순위

| 순위 | 분석 | 필요 데이터 | 추가 수집 |
|------|------|------------|----------|
| 1 | **법안 통과 예측 + 생존분석** | master_bills (22대) | 없음 |
| 2 | **위원회 병목 분석** | master_bills + committee_meetings | 없음 |
| 3 | **발의자 유형별 통과율** | master_bills (multi-age) | Tier 1 확장 |
| 4 | **의제 공간 매핑** | bill_nm 텍스트 + 법안 원문 | Tier 3 (크롤링) |
| 5 | **cosponsorship + outcome** | master_bills + na-legislative-events | Tier 3 (공동발의자) |
| 6 | **입법 생산성 패널** | master_bills + 의원 메타 | Tier 3 (의원 API) |
