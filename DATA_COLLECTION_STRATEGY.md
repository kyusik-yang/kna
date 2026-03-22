# Korean Bill Lifecycle Master Database - Data Collection Strategy

**Project**: Life of a Bill (KR)
**Data Source**: 열린국회정보 Open API (open.assembly.go.kr)
**Created**: 2026-03-19
**Status**: 탐색 완료, 수집 미시작

---

## 1. 목표

열린국회정보 포털에 분산된 8개 이상의 API를 `BILL_ID` 기준으로 조인하여, 한국 국회 법안의 전 생애주기를 추적하는 단일 마스터 데이터베이스를 구축한다.

```
발의/제출 → 소관위 회부 → 소관위 심사 → 법사위 체계·자구심사 → 본회의 심의/표결 → 정부이송 → 공포
```

## 2. API 인증

- **키**: 열린국회정보 회원가입 후 발급 (최대 10개)
- **키 파일**: `열린국회정보.rtf` (Desktop/kyusik-claude/)
- **필수 헤더**: `User-Agent` 헤더가 없으면 400 Bad Request 반환
- **호출 형식**: `https://open.assembly.go.kr/portal/openapi/{ENDPOINT}?KEY={key}&Type=json&pIndex={p}&pSize={n}&{params}`

## 3. API 인벤토리

### 3-A. Batch API (AGE 파라미터로 대수별 전건 조회)

| # | Endpoint | 이름 | 22대 건수 | 핵심 필드 | 비고 |
|---|----------|------|-----------|-----------|------|
| 1 | `nzmimeepazxkubdpn` | 의원 발의법률안 | 16,100 | BILL_ID, BILL_NO, BILL_NAME, PROPOSE_DT, COMMITTEE, PROC_RESULT, RST_PROPOSER, PUBL_PROPOSER, RST_MONA_CD, PUBL_MONA_CD, DETAIL_LINK, MEMBER_LIST | 대표/공동발의자 이름+코드 포함. 의원 발의만 해당 (정부/위원장 제안 제외) |
| 2 | `BILLRCP` | 접수목록 | 118,458 | BILL_ID, BILL_NO, BILL_KIND, BILL_NM, PPSR_KIND, PPSL_DT, PROC_RSLT | 모든 의안 포괄 (법률안+예산안+결산+동의안 등). BILL_KIND로 유형 구분 |
| 3 | `BILLJUDGE` | 심사정보 | 35,158 | BILL_ID, BILL_NO, JRCMIT_NM, BDG_CMMT_DT, JRCMIT_PRSNT_DT, JRCMIT_PROC_DT, JRCMIT_PROC_RSLT | 소관위 심사 날짜/결과. 1 bill = 1 row |
| 4 | `ncocpgfiaoituanbr` | 의안별 표결현황 | 1,286 | BILL_ID, PROC_DT, CURR_COMMITTEE, PROC_RESULT_CD, MEMBER_TCNT, VOTE_TCNT, YES_TCNT, NO_TCNT, BLANK_TCNT | 본회의 표결 찬반 수. 표결에 부쳐진 의안만 해당 |
| 5 | `nzpltgfqabtcpsmai` | 처리의안 | 4,413 | BILL_ID, PROPOSER, PROPOSER_KIND, PROPOSE_DT, PROC_RESULT_CD, COMMITTEE_DT, PROC_DT, LAW_SUBMIT_DT, LAW_PRESENT_DT, LAW_PROC_DT, CMT_PROC_RESULT_CD, LAW_PROC_RESULT_CD, CMT_PRESENT_DT, CMT_PROC_DT | 처리 완료된 의안. 위원회+법사위+본회의 날짜 포함 |

### 3-B. Per-Bill API (BILL_ID 필수)

| # | Endpoint | 이름 | 핵심 필드 | 비고 |
|---|----------|------|-----------|------|
| 6 | `BILLINFODETAIL` | 의안 상세정보 | PPSL_DT, PPSL_SESS, JRCMIT_NM, JRCMIT_CMMT_DT, JRCMIT_PRSNT_DT, JRCMIT_PROC_DT, JRCMIT_PROC_RSLT, LAW_CMMT_DT, LAW_PRSNT_DT, LAW_PROC_DT, LAW_PROC_RSLT, RGS_PRSNT_DT, RGS_RSLN_DT, RGS_CONF_NM, RGS_CONF_RSLT, GVRN_TRSF_DT, PROM_DT, PROM_NO, PROM_LAW_NM | **핵심 API** - 전 생애주기 날짜를 한 row에 제공 |
| 7 | `BILLJUDGECONF` | 위원회 회의정보 | JRCMIT_CONF_NM, JRCMIT_CONF_DT, JRCMIT_CONF_RSLT | 1 bill = N rows (회의별). 상정/소위심사보고/축조심사/의결 등 구분 |
| 8 | `BILLLWJUDGECONF` | 법사위 회의정보 | LWCMIT_CONF_NM, LWCMIT_CONF_DT, LWCMIT_CONF_RSLT | 1 bill = N rows (회의별) |

### 3-C. 추가 확인 필요

| Endpoint | 이름 | 상태 |
|----------|------|------|
| `BILLINFOPPSR` | 제안자정보 | ERROR-300 (필수 파라미터 불명). BILL_ID로 테스트 시 데이터 없음 반환. `nzmimeepazxkubdpn`의 RST_PROPOSER/PUBL_PROPOSER로 대체 가능 |
| `ALLBILL` | 의안정보 통합 | BILL_NO 필수. `BILLINFODETAIL`과 중복 가능성 높음. 추가 테스트 필요 |
| `TVBPMBILL11` | 의안검색 | 미테스트. BILLRCP와 중복 가능성 |
| `nwbqublzajtcqpdae` | 계류의안 | 미테스트. 현재 계류 중인 의안 스냅샷 |
| `BILLCNTMAIN` 외 4개 | 통계 API | 집계 데이터. 마스터 DB에는 불필요 (원시 데이터에서 직접 산출 가능) |

## 4. 데이터 모델

### 4-A. 핵심 테이블

```
bills (core)
├── bill_id          PK    "PRC_..." 형식
├── bill_no                "2217629" 형식
├── bill_name
├── bill_kind              법률안/예산안/결산/동의안/...
├── age                    국회 대수 (21, 22, ...)
├── proposer_kind          의원/정부/위원장
├── proposer_text          "박균택의원 등 13인"
├── rst_proposer           대표발의자 이름
├── rst_mona_cd            대표발의자 코드
├── propose_dt             발의일
├── committee              소관위원회
├── committee_id           소관위 코드
│
├── [소관위 심사]
├── jrcmit_cmmt_dt         소관위 회부일
├── jrcmit_prsnt_dt        소관위 상정일
├── jrcmit_proc_dt         소관위 처리일
├── jrcmit_proc_rslt       소관위 처리결과
│
├── [법사위 심사]
├── law_cmmt_dt            법사위 회부일
├── law_prsnt_dt           법사위 상정일
├── law_proc_dt            법사위 처리일
├── law_proc_rslt          법사위 처리결과
│
├── [본회의]
├── rgs_prsnt_dt           본회의 상정일
├── rgs_rsln_dt            본회의 의결일
├── rgs_conf_nm            본회의 회차
├── rgs_conf_rslt          본회의 결과 (원안가결/수정가결/부결/...)
│
├── [후속]
├── gvrn_trsf_dt           정부이송일
├── prom_dt                공포일
├── prom_no                공포번호
├── prom_law_nm            공포법률명
│
├── [표결 상세] (표결에 부쳐진 경우만)
├── vote_total             총 투표수
├── vote_yes               찬성
├── vote_no                반대
├── vote_abstain           기권
├── member_total           재적의원수
│
├── [메타]
├── proc_result            최종 처리결과
├── proc_dt                최종 처리일
├── detail_link            LIKMS 상세 페이지 URL
└── member_list_link       공동발의자 목록 URL

sponsors (1:N)
├── bill_id          FK
├── member_name
├── member_code            MONA_CD
├── role                   대표발의/공동발의
└── party                  (MEMBER_LIST 크롤링 시 획득 가능)

committee_meetings (1:N) - BILLJUDGECONF
├── bill_id          FK
├── conf_name              회의명
├── conf_dt                회의일
└── conf_result            결과 (상정/소위심사보고/축조심사/의결)

judiciary_meetings (1:N) - BILLLWJUDGECONF
├── bill_id          FK
├── conf_name              회의명
├── conf_dt                회의일
└── conf_result            결과
```

### 4-B. 조인 키

모든 테이블의 공통 키: **`BILL_ID`** (`PRC_` prefix 문자열)

`BILL_NO`도 대부분 unique하지만, 대안(위원장안)의 경우 원안과 BILL_NO가 다를 수 있으므로 BILL_ID를 primary key로 사용.

## 5. 수집 파이프라인

### Phase 1: Batch 수집 (전체 법안 목록 + 기본 정보)

```
for each AGE in [21, 22]:  # 확장 가능
    1. nzmimeepazxkubdpn → bills_proposed_{age}.parquet
       - pSize=1000, pIndex 1부터 순차 페이징
       - 16,100건 (22대) → 약 17 requests

    2. BILLRCP → bills_received_{age}.parquet
       - 118,458건 (22대) → 약 119 requests
       - 법률안 외 의안도 포함 (BILL_KIND로 필터링 가능)

    3. BILLJUDGE → committee_review_{age}.parquet
       - 35,158건 → 약 36 requests

    4. ncocpgfiaoituanbr → votes_{age}.parquet
       - 1,286건 → 약 2 requests

    5. nzpltgfqabtcpsmai → processed_bills_{age}.parquet
       - 4,413건 → 약 5 requests
```

**예상 API 호출 수**: 22대 기준 약 179 requests (Phase 1 전체)

### Phase 2: Per-Bill 상세 수집

```
bill_ids = Phase 1에서 수집된 unique BILL_ID 목록

for each bill_id:
    6. BILLINFODETAIL → bill_detail_{age}.parquet
       - 16,100건 → 16,100 requests (1 per bill)
       - rate limit: 0.5초 간격 → 약 2.2시간

    [선택적]
    7. BILLJUDGECONF → committee_meetings_{age}.parquet
    8. BILLLWJUDGECONF → judiciary_meetings_{age}.parquet
```

**예상 API 호출 수**: 22대 기준 약 16,100 requests (Phase 2)
**예상 소요 시간**: 0.5초 간격 기준 약 2.2시간

### Phase 3: 조인 및 마스터 DB 생성

```
1. bills_proposed + BILLRCP → 기본 정보 통합
2. + BILLJUDGE → 소관위 심사 정보 추가
3. + BILLINFODETAIL → 전 생애주기 날짜 추가
4. + votes → 표결 정보 추가
5. + processed_bills → 최종 처리결과 보강
→ master_bills_{age}.parquet / .sqlite
```

## 6. 기술 고려사항

### Rate Limiting
- 열린국회정보는 명시적 rate limit 문서 없음
- 안전하게 0.5초 간격 권장 (초당 2건)
- 대량 수집 시 간헐적 타임아웃 대비 retry 로직 필요

### 페이징
- `pSize` 최대값 미확인 (1000으로 테스트 필요, 기본 100)
- `list_total_count`로 전체 건수 확인 → 필요 페이지 수 계산
- 반환 건수가 pSize보다 작으면 마지막 페이지

### 인코딩
- 응답 JSON의 한글 필드는 유니코드 이스케이프로 반환됨
- Python `json.loads()`로 자동 디코딩

### 필수 헤더
```python
headers = {"User-Agent": "Mozilla/5.0"}
```
이 헤더 없이 호출하면 400 Bad Request.

### 저장 형식
- 중간 결과: Parquet (타입 보존, 압축 효율)
- 최종 마스터: SQLite (조회 편의) + Parquet (분석 편의)
- 위치: `projects/korean-bill-lifecycle/data/`

## 7. 연구 활용 가능성

이 마스터 DB로 가능한 분석:

- **법안 통과율 분석**: 발의 대비 통과 비율, 위원회별/발의자 유형별
- **입법 소요기간**: 발의 → 소관위 → 법사위 → 본회의 → 공포까지 각 단계별 소요일
- **위원회 병목**: 어떤 위원회에서 법안이 오래 계류되는지
- **표결 패턴**: 찬반 비율 분포, 만장일치 vs 쟁점 법안
- **발의자 네트워크**: 공동발의 관계 (sponsors 테이블 기반)
- **임기만료폐기 패턴**: 어느 단계에서 폐기가 집중되는지
- **정부 vs 의원 발의 비교**: PROPOSER_KIND별 통과율, 소요기간 차이

## 8. 참고 자료

- [Velog: OpenAPI 의안 관련 참고 문서](https://velog.io/@assembly101/OpenAPI-%EC%9D%98%EC%95%88-%EA%B4%80%EB%A0%A8-%EC%82%AC%EC%9A%A9-%EC%B0%B8%EA%B3%A0-%EB%AC%B8%EC%84%9C-%EC%9E%91%EC%84%B1-%EC%A7%84%ED%96%89%EC%A4%91)
- [Kitelog: Python 국회의원 발의법률안 API + 크롤링](https://gittykite.github.io/python/billcrawling/)
- [열린국회정보 개발가이드](https://open.assembly.go.kr/portal/openapi/openApiDevPage.do)
- [공공데이터포털: 의안정보 통합 API](https://www.data.go.kr/data/15126134/openapi.do)
- [teampopong/data-for-rnd (GitHub)](https://github.com/teampopong/data-for-rnd) - 유사 프로젝트 (업데이트 중단)
