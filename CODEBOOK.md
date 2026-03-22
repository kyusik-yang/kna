# Korean Bill Lifecycle Master Database - Codebook

**Dataset**: `master_bills_22.parquet` / `master_bills_22.sqlite` (table: `bills`)
**Unit of observation**: Bill (의안)
**N**: 17,205 (22대 국회, 2024-05-30 ~ 2026-03-20)
**Variables**: 42
**Last updated**: 2026-03-21

---

## Variable Index

| # | Variable | Type | Coverage | Group |
|---|----------|------|----------|-------|
| 1 | `bill_id` | str | 100% | ID |
| 2 | `bill_no` | str | 100% | ID |
| 3 | `age` | int | 100% | ID |
| 4 | `bill_kind` | str | 100% | ID |
| 5 | `bill_nm` | str | 100% | ID |
| 6 | `ppsr_kind` | str | 100% | Proposer |
| 7 | `proposer_text` | str | 93.8% | Proposer |
| 8 | `rst_proposer` | str | 93.8% | Proposer |
| 9 | `rst_mona_cd` | str | 93.8% | Proposer |
| 10 | `publ_proposer` | str | 93.7% | Proposer |
| 11 | `publ_mona_cd` | str | 93.7% | Proposer |
| 12 | `ppsl_dt` | datetime | 100% | Lifecycle |
| 13 | `committee_dt` | datetime | 93.4% | Lifecycle |
| 14 | `bdg_cmmt_dt` | datetime | 22.4% | Lifecycle |
| 15 | `cmt_present_dt` | datetime | 75.2% | Lifecycle |
| 16 | `jrcmit_prsnt_dt` | datetime | 21.8% | Lifecycle |
| 17 | `cmt_proc_dt` | datetime | 23.6% | Lifecycle |
| 18 | `jrcmit_proc_dt` | datetime | 21.9% | Lifecycle |
| 19 | `law_submit_dt` | datetime | 3.0% | Lifecycle |
| 20 | `law_present_dt` | datetime | 2.7% | Lifecycle |
| 21 | `law_proc_dt` | datetime | 2.7% | Lifecycle |
| 22 | `proc_dt` | datetime | 21.3% | Lifecycle |
| 23 | `jrcmit_proc_rslt` | str | 22.4% | Result |
| 24 | `cmt_proc_result_cd` | str | 24.1% | Result |
| 25 | `law_proc_result_cd` | str | 2.7% | Result |
| 26 | `proc_rslt` | str | 27.5% | Result |
| 27 | `status` | str | 100% | Result |
| 28 | `passed` | int | 100% | Result |
| 29 | `enacted` | int | 100% | Result |
| 30 | `vote_result_cd` | str | 7.2% | Vote |
| 31 | `vote_member_total` | float | 7.2% | Vote |
| 32 | `vote_total` | float | 7.2% | Vote |
| 33 | `vote_yes` | float | 7.2% | Vote |
| 34 | `vote_no` | float | 7.2% | Vote |
| 35 | `vote_abstain` | float | 7.2% | Vote |
| 36 | `committee_nm` | str | 93.4% | Committee |
| 37 | `committee_id` | str | 93.4% | Committee |
| 38 | `jrcmit_nm` | str | 22.4% | Committee |
| 39 | `link_url` | str | 100% | Meta |
| 40 | `member_list` | str | 93.8% | Meta |
| 41 | `days_to_proc` | float | 21.3% | Derived |
| 42 | `days_to_committee` | float | 22.4% | Derived |

---

## Detailed Variable Descriptions

### Group 1: Identifiers

#### `bill_id`
- **Description**: 법안 고유 식별자 (Primary Key)
- **Type**: `str` (object)
- **Format**: `PRC_` + 30-char alphanumeric / `ARC_` + 30-char alphanumeric
- **Example**: `PRC_Y2Z6X0Y2F1G3E1D1D1B1C2Y6Y0W6X6`
- **Length**: 34 characters (fixed)
- **Unique**: 17,205 (100%)
- **Null**: 0
- **Notes**: `PRC_` prefix for most bills (87,871 in BILLRCP); `ARC_` prefix for some older/special bills (4,650 in BILLRCP). Some non-standard IDs exist in historical data (4-digit numeric prefix). This is the master join key across all tables.

#### `bill_no`
- **Description**: 의안 번호
- **Type**: `str` (object)
- **Format**: 7-digit numeric string
- **Example**: `2217673`
- **Unique**: 17,197
- **Near-unique**: 8 duplicate bill_no values exist (대안 등으로 동일 번호 부여 가능)
- **Null**: 0
- **Notes**: 일반적으로 unique하지만 BILL_ID를 primary key로 사용해야 함. 첫 두 자리 `22`는 22대를 의미.

#### `age`
- **Description**: 국회 대수
- **Type**: `int64`
- **Values**: 22 (현재 데이터셋)
- **Null**: 0
- **Notes**: 확장 시 17~22 범위. 22대 = 2024.5.30 임기 시작.

#### `bill_kind`
- **Description**: 의안 유형
- **Type**: `str` (object)
- **Values** (9 categories):

| Value | N | % | Description |
|-------|---|---|-------------|
| 법률안 | 16,907 | 98.3% | 법률 제정/개정안 (핵심 분석 대상) |
| 결의안 | 112 | 0.7% | 국회 의사 표명 (법적 구속력 없음) |
| 동의안 | 54 | 0.3% | 헌법/법률에 따른 동의 요청 |
| 예산안 | 41 | 0.2% | 정부 예산안 |
| 중요동의 | 35 | 0.2% | 국군 해외파견 등 중요 동의 |
| 승인안 | 32 | 0.2% | 조약 비준 동의 등 |
| 선출안 | 20 | 0.1% | 인사 선출 |
| 규칙안 | 2 | <0.1% | 국회 규칙 |
| 결산 | 2 | <0.1% | 결산 심사 |

- **Null**: 0
- **Notes**: 대부분 연구에서는 `bill_kind == '법률안'`으로 필터링하여 사용.

#### `bill_nm`
- **Description**: 법안명 (의안 제목)
- **Type**: `str` (object)
- **Example**: `약사법 일부개정법률안`, `국민연금법 일부개정법률안`
- **Unique**: 2,984 (같은 법률에 대한 여러 개정안은 동일 이름)
- **Length**: 4~105 characters
- **Null**: 0
- **Notes**: 같은 법률에 대해 여러 의원이 개정안을 제출하므로 중복됨. 조세특례제한법이 661건으로 최다. NLP 분석 시 법률명 + 개정 내용 구분 필요.

---

### Group 2: Proposer Information

#### `ppsr_kind`
- **Description**: 발의/제안 주체 유형
- **Type**: `str` (object)
- **Values** (5 categories):

| Value | N | % | Description |
|-------|---|---|-------------|
| 의원 | 16,231 | 94.3% | 국회의원 발의 (대표발의자 + 공동발의자) |
| 위원장 | 635 | 3.7% | 상임위원회 위원장 제안 (대안, 위원회안) |
| 정부 | 294 | 1.7% | 정부 제출 법안 |
| 의장 | 41 | 0.2% | 국회의장 제안 (예산안 등) |
| 기타 | 4 | <0.1% | 기타 |

- **Null**: 0
- **Notes**: 의원 발의만 `rst_proposer`, `rst_mona_cd` 등 상세 발의자 정보 보유. 위원장/정부/의장 발의는 해당 필드가 null.

#### `proposer_text`
- **Description**: 발의자 전체 텍스트
- **Type**: `str` (object)
- **Example**: `김종민의원 등 10인`, `민형배의원 등 10인`
- **Format**: `{이름}의원 등 {N}인`
- **Length**: 10~24 characters
- **Null**: 1,063 (6.2%) - 의원 발의가 아닌 법안
- **Notes**: 공동발의자 수는 이 텍스트에서 정규식으로 추출 가능: `(\d+)인$`. 대표발의자 이름도 포함.

#### `rst_proposer`
- **Description**: 대표발의자 이름
- **Type**: `str` (object)
- **Example**: `김종민`, `윤준병`, `추미애`
- **Unique**: 421 (22대 국회의원 중 법안 발의자)
- **Length**: 2~11 characters
- **Null**: 1,063 (의원 발의가 아닌 법안)
- **Notes**: 22대 국회의원 300명 중 법안을 1건 이상 대표발의한 의원 수. 다른 프로젝트와 연결 시 `rst_mona_cd`를 사용해야 함 (이름 동명이인 존재 가능).

#### `rst_mona_cd`
- **Description**: 대표발의자 의원 코드 (MONA_CD)
- **Type**: `str` (object)
- **Format**: 8-character alphanumeric (일반적), 일부 더 긴 코드 존재
- **Example**: `M2Q9024I`, `JC14718Q`
- **Unique**: 421
- **Length**: 8~26 characters
- **Null**: 1,063
- **Notes**: **핵심 조인 키**. 다른 프로젝트(committee-witnesses-korea의 `naas_cd`, legislator-assets-korea 등)와 의원 단위 연결에 사용. 열린국회정보 의원 API에서 의원 메타데이터(정당, 지역구, 선수 등) 매칭 가능.

#### `publ_proposer`
- **Description**: 공동발의자 이름 목록
- **Type**: `str` (object)
- **Format**: 쉼표 구분 이름 목록
- **Example**: `허성무,최혁진,손솔,한창민,윤종오,김승원,전종덕,안호영,황운하`
- **Length**: 30~756 characters
- **Unique**: 13,894
- **Null**: 1,085
- **Notes**: Cosponsorship 네트워크 구축 시 파싱 필요. 이름만 포함 (코드 없음). 코드가 필요하면 `publ_mona_cd` 사용.

#### `publ_mona_cd`
- **Description**: 공동발의자 의원 코드 목록
- **Type**: `str` (object)
- **Format**: 쉼표 구분 MONA_CD 목록
- **Example**: `HHB5652A,CC78321E,2KM3589W,...`
- **Length**: 71~1,709 characters
- **Unique**: 13,894
- **Null**: 1,085
- **Notes**: `publ_proposer`와 1:1 대응 (같은 순서). 네트워크 분석 시 이 필드를 파싱하여 edge list 생성 가능. `member_list` URL을 크롤링하면 더 정확한 데이터 확보 가능.

---

### Group 3: Lifecycle Timestamps

모든 날짜는 `datetime64[ns]` 타입. 법안이 해당 단계에 도달하지 않은 경우 `NaT` (Not a Time).

#### `ppsl_dt` (발의일/제출일)
- **Coverage**: 100% (17,205)
- **Range**: 2024-05-30 ~ 2026-03-20
- **Notes**: 모든 법안의 시작점. 22대 국회 개원일은 2024-05-30.

#### `committee_dt` (소관위원회 회부일)
- **Source**: nzmimeepazxkubdpn `COMMITTEE_DT`
- **Coverage**: 93.4% (16,071)
- **Range**: 2024-06-11 ~ 2026-03-20
- **Null reason**: 발의 직후 아직 회부되지 않았거나, 비의원발의 법안
- **Notes**: 발의 후 회부까지 중위 1일, 평균 3.6일. 거의 자동적으로 회부됨.

#### `bdg_cmmt_dt` (소관위 회부일 - BILLJUDGE 소스)
- **Source**: BILLJUDGE `BDG_CMMT_DT`
- **Coverage**: 22.4% (3,859)
- **Notes**: BILLJUDGE 데이터의 소관위 회부일. `committee_dt`와 유사하나 다른 API 소스. BILLJUDGE에 데이터가 있는 법안만 해당 (22대 3,859건).

#### `cmt_present_dt` (위원회 상정일)
- **Source**: nzmimeepazxkubdpn `CMT_PRESENT_DT`
- **Coverage**: 75.2% (12,935)
- **Range**: 2024-06-12 ~ 2026-03-19
- **Notes**: 소관위원회에서 안건으로 상정된 날짜. 회부와 상정은 다름 - 회부는 행정적 배분, 상정은 실질적 심사 개시.

#### `jrcmit_prsnt_dt` (소관위 상정일 - BILLJUDGE 소스)
- **Source**: BILLJUDGE `JRCMIT_PRSNT_DT`
- **Coverage**: 21.8% (3,759)
- **Notes**: BILLJUDGE의 소관위 상정일. `cmt_present_dt`와 동일 의미, 다른 소스.

#### `cmt_proc_dt` (소관위 처리일)
- **Source**: nzmimeepazxkubdpn `CMT_PROC_DT`
- **Coverage**: 23.6% (4,060)
- **Range**: 2024-06-18 ~ 2026-03-18
- **Notes**: 소관위에서 최종 처리(가결/폐기 등)된 날짜.

#### `jrcmit_proc_dt` (소관위 처리일 - BILLJUDGE 소스)
- **Source**: BILLJUDGE `JRCMIT_PROC_DT`
- **Coverage**: 21.9% (3,761)
- **Notes**: BILLJUDGE의 소관위 처리일.

#### `law_submit_dt` (법사위 회부일)
- **Source**: nzmimeepazxkubdpn `LAW_SUBMIT_DT`
- **Coverage**: 3.0% (510)
- **Range**: 2024-06-18 ~ 2026-03-17
- **Notes**: 소관위를 통과한 법안 중 법사위(법제사법위원회)에 회부된 법안만. 법사위는 체계/자구 심사를 담당. 매우 낮은 coverage는 대부분의 법안이 이 단계에 도달하지 못함을 의미.

#### `law_present_dt` (법사위 상정일)
- **Source**: nzmimeepazxkubdpn `LAW_PRESENT_DT`
- **Coverage**: 2.7% (464)
- **Notes**: 법사위에서 안건 상정. `law_submit_dt`보다 약간 적음 (회부 후 아직 상정되지 않은 법안 존재).

#### `law_proc_dt` (법사위 처리일)
- **Source**: nzmimeepazxkubdpn `LAW_PROC_DT`
- **Coverage**: 2.7% (459)
- **Notes**: 법사위 심사 완료일.

#### `proc_dt` (최종 처리일)
- **Source**: nzmimeepazxkubdpn `PROC_DT`
- **Coverage**: 21.3% (3,664)
- **Range**: 2024-06-10 ~ 2026-03-20
- **Notes**: 법안의 최종 처리 완료일. 원안가결/수정가결/폐기/철회 등 최종 상태가 결정된 날짜. `days_to_proc` 계산에 사용.

#### Phase 2 추가 필드 (수집 중)

Phase 2 (BILLINFODETAIL)가 완료되면 다음 필드가 추가됩니다:

| 필드 | 설명 |
|------|------|
| `jrcmit_cmmt_dt` | 소관위 회부일 (BILLINFODETAIL 소스, 가장 정확) |
| `law_cmmt_dt` | 법사위 회부일 (BILLINFODETAIL) |
| `law_prsnt_dt` | 법사위 상정일 (BILLINFODETAIL) |
| `law_proc_rslt` | 법사위 처리결과 |
| `rgs_prsnt_dt` | 본회의 상정일 |
| `rgs_rsln_dt` | 본회의 의결일 |
| `rgs_conf_nm` | 본회의 회차 |
| `rgs_conf_rslt` | 본회의 결과 |
| `gvrn_trsf_dt` | 정부이송일 |
| `prom_dt` | 공포일 |
| `prom_no` | 공포번호 |
| `prom_law_nm` | 공포법률명 |

---

### Group 4: Processing Results

#### `jrcmit_proc_rslt` (소관위 처리결과)
- **Source**: BILLJUDGE
- **Coverage**: 22.4% (3,859)
- **Values** (11 categories):

| Value | N | Description |
|-------|---|-------------|
| 대안반영폐기 | 3,101 | 법안 내용이 위원장 대안에 반영된 후 폐기 |
| 수정가결 | 376 | 수정을 거쳐 가결 |
| 원안가결 | 212 | 원안 그대로 가결 |
| 철회 | 114 | 발의자가 자진 철회 |
| 수정안반영폐기 | 39 | 수정안에 내용 반영 후 폐기 |
| 부결 | 5 | 위원회에서 부결 |
| 폐기 | 5 | 위원회에서 폐기 결정 |
| 보류 | 3 | 심사 보류 |
| 철수 | 2 | 철수 |
| 임기만료폐기 | 1 | 임기 만료로 자동 폐기 |
| 수정안가결 | 1 | 수정안 형태로 가결 |

#### `cmt_proc_result_cd` (소관위 처리결과 - 코드)
- **Source**: nzmimeepazxkubdpn/nzpltgfqabtcpsmai
- **Coverage**: 24.1% (4,153)
- **Notes**: `jrcmit_proc_rslt`와 유사하나 다른 API 소스. 약간의 분류 차이 있을 수 있음.

#### `law_proc_result_cd` (법사위 처리결과)
- **Coverage**: 2.7% (459)
- **Values**: 수정가결 (264), 원안가결 (195)
- **Notes**: 법사위까지 도달한 법안은 거의 가결됨 (부결 없음).

#### `proc_rslt` (최종 처리결과)
- **Coverage**: 27.5% (4,727)
- **Values**:

| Value | N | Description |
|-------|---|-------------|
| 대안반영폐기 | 3,101 | 내용이 대안에 반영되어 실질적 "통과" |
| 원안가결 | 977 | 원안 그대로 최종 가결 → 법률 |
| 수정가결 | 422 | 수정 후 최종 가결 → 법률 |
| 철회 | 146 | 발의자 자진 철회 |
| 수정안반영폐기 | 39 | 수정안에 반영 후 폐기 |
| 부결 | 33 | 최종 부결 |
| 폐기 | 9 | 최종 폐기 |

- **Null**: 12,478 (72.5%) - 아직 처리되지 않은 계류 법안

#### `status` (현재 상태)
- **Coverage**: 100%
- **Values**: `proc_rslt`의 값 + "계류중" (proc_rslt이 null인 경우)
- **Derivation**: `proc_rslt.fillna("계류중")`
- **Notes**: 분석에서 가장 자주 사용할 상태 변수.

#### `passed` (통과 여부 - 넓은 정의)
- **Type**: `int64` (binary: 0/1)
- **Coverage**: 100%
- **Values**: 0 = 미통과 (12,705), 1 = 통과 (4,500)
- **Definition**: `proc_rslt in ['원안가결', '수정가결', '대안반영폐기']`
- **Notes**: "대안반영폐기"를 통과로 포함. 법안 내용이 다른 법안(주로 위원장 대안)에 반영된 것이므로 실질적 입법 기여로 간주. 한국 국회의 관행상 의원 발의 법안은 위원장 대안에 병합되는 것이 일반적.

#### `enacted` (가결 여부 - 좁은 정의)
- **Type**: `int64` (binary: 0/1)
- **Coverage**: 100%
- **Values**: 0 = 미가결 (15,806), 1 = 가결 (1,399)
- **Definition**: `proc_rslt in ['원안가결', '수정가결']`
- **Notes**: 해당 법안 자체가 법률로 확정된 경우만. 대안반영폐기 제외. 연구 설계에 따라 `passed`와 `enacted` 중 선택.

---

### Group 5: Vote Details

본회의 표결에 부쳐진 법안만 해당 (N = 1,236, 전체의 7.2%). 대부분의 법안은 표결 없이 처리됨 (위원회 단계에서 종료되거나, 본회의에서 이의 없이 통과).

#### `vote_result_cd` (표결 결과)
- **Values**: 원안가결 (843), 수정가결 (391), 부결 (2)

#### `vote_member_total` (재적의원수)
- **Range**: 295~300
- **Notes**: 22대 의원 정수 300명. 사직/보궐 등으로 변동.

#### `vote_total` (투표 참여 의원수)
- **Range**: 150~297 (mean: 230.4, median: 238)

#### `vote_yes` (찬성)
- **Range**: 75~297 (mean: 222.5, median: 229)

#### `vote_no` (반대)
- **Range**: 0~181 (mean: 4.0, median: 0)
- **Notes**: 대부분의 표결에서 반대 0. 중위수 0은 만장일치 투표가 지배적임을 의미.

#### `vote_abstain` (기권)
- **Range**: 0~44 (mean: 3.9, median: 2)

---

### Group 6: Committee Information

#### `committee_nm` (소관위원회 이름)
- **Coverage**: 93.4% (16,068)
- **Unique**: 25 committees
- **Top 5**: 행정안전위원회(2,117), 법제사법위원회(1,519), 기후에너지환경노동위원회(1,406), 국토교통위원회(1,374), 보건복지위원회(1,364)
- **Null reason**: 비의원발의 법안 중 위원회 미배정 건

#### `committee_id` (소관위원회 코드)
- **Coverage**: 93.4% (16,068)
- **Format**: 7-digit numeric string (e.g., `9700480`)
- **Notes**: `committee_nm`과 1:1 대응. 위원회 코드로 조인 시 사용.

#### `jrcmit_nm` (소관위 - BILLJUDGE 소스)
- **Coverage**: 22.4% (3,858)
- **Unique**: 30 (위원회 명칭 변경 반영)
- **Notes**: BILLJUDGE에서의 소관위 이름. `committee_nm`과 약간의 명칭 차이 가능 (22대 위원회 개편 반영 여부 차이).

---

### Group 7: Metadata

#### `link_url` (LIKMS 상세 페이지)
- **Coverage**: 100%
- **Format**: `http://likms.assembly.go.kr/bill/billDetail.do?billId={BILL_ID}&ageFrom=22&ageTo=22`
- **Notes**: 국회 입법정보시스템 상세 페이지. 법안 원문(PDF), 심사 경과, 회의록 링크 등 확인 가능. 법안 원문 크롤링의 진입점.

#### `member_list` (공동발의자 목록 URL)
- **Coverage**: 93.8% (16,142)
- **Format**: `http://likms.assembly.go.kr/bill/coactorListPopup.do?billId={BILL_ID}`
- **Notes**: 크롤링하면 공동발의자 상세 정보(이름, 정당, 선수 등) 획득 가능. Cosponsorship 네트워크 구축의 원천 데이터.

---

### Group 8: Derived Variables

#### `days_to_proc` (발의~처리 소요일)
- **Coverage**: 21.3% (3,664) - 처리 완료된 법안만
- **Derivation**: `(proc_dt - ppsl_dt).days`
- **Distribution**: min 0, Q1 99, median 171, mean 210, Q3 290, max 645
- **Unit**: Days
- **Notes**: 0일은 발의 당일 처리 (주로 위원장안). 645일은 22대 초기 발의 후 최근 처리된 법안.

#### `days_to_committee` (발의~소관위 회부 소요일)
- **Coverage**: 22.4% (3,859)
- **Derivation**: `(bdg_cmmt_dt - ppsl_dt).days`
- **Distribution**: min 0, Q1 0, median 1, mean 3.6, max 495
- **Unit**: Days
- **Notes**: 중위 1일로 거의 자동적 회부. 495일 이상 소요는 극단적 예외.

---

## Satellite Tables

### `committee_meetings` (위원회 회의정보)

**Source**: BILLJUDGECONF (Phase 2, 수집 중)
**Unit**: Bill-Meeting (1 bill = N meetings)
**Estimated rows**: ~50,000

| Variable | Type | Description |
|----------|------|-------------|
| `bill_id` | str | 법안 ID (FK → bills) |
| `jrcmit_conf_nm` | str | 회의명 (예: "제419회 국회 보건복지위원회") |
| `jrcmit_conf_dt` | str | 회의 날짜 |
| `jrcmit_conf_rslt` | str | 회의 결과 (상정, 소위심사보고, 축조심사, 의결 등) |

### `judiciary_meetings` (법사위 회의정보)

**Source**: BILLLWJUDGECONF (Phase 2, 수집 중)
**Unit**: Bill-Meeting (1 bill = N meetings)
**Estimated rows**: ~5,000

| Variable | Type | Description |
|----------|------|-------------|
| `bill_id` | str | 법안 ID (FK → bills) |
| `lwcmit_conf_nm` | str | 법사위 회의명 |
| `lwcmit_conf_dt` | str | 법사위 회의 날짜 |
| `lwcmit_conf_rslt` | str | 법사위 회의 결과 |

---

## Coverage Notes

### 왜 많은 필드가 낮은 coverage인가?

22대 국회는 현재 **진행 중** (2024.5 ~ 현재). 17,205건 중 12,478건(72.5%)이 아직 계류 상태.

| 단계 | 도달 법안 수 | 전체 대비 |
|------|------------|----------|
| 발의 | 17,205 | 100% |
| 소관위 회부 | ~16,071 | 93.4% |
| 소관위 상정 | ~12,935 | 75.2% |
| 소관위 처리 | ~4,060 | 23.6% |
| 법사위 회부 | ~510 | 3.0% |
| 법사위 처리 | ~459 | 2.7% |
| 본회의 표결 | ~1,236 | 7.2% |
| 최종 처리 | ~4,727 | 27.5% |

이 "깔때기" 구조 자체가 연구 대상임 - 법안이 어느 단계에서 사라지는지.

### 중복 날짜 필드 설명

일부 날짜가 여러 API 소스에서 중복 수집됨:
- `committee_dt` (nzmimeepazxkubdpn) vs `bdg_cmmt_dt` (BILLJUDGE)
- `cmt_present_dt` (nzmimeepazxkubdpn) vs `jrcmit_prsnt_dt` (BILLJUDGE)
- `cmt_proc_dt` (nzmimeepazxkubdpn) vs `jrcmit_proc_dt` (BILLJUDGE)

nzmimeepazxkubdpn이 의원 발의 법안 전체를 커버(16,142건)하고, BILLJUDGE는 처리된 법안 위주(3,859건). 둘 다 보유하여 cross-validation 가능.

Phase 2의 BILLINFODETAIL은 가장 포괄적인 lifecycle 데이터를 제공하므로, 완료 후 이 필드들의 coverage가 크게 개선될 예정.

---

## Cross-Project Join Keys

| This DB | Other Project | Join Key | Notes |
|---------|---------------|----------|-------|
| `rst_mona_cd` | committee-witnesses-korea (`naas_cd`) | 의원 코드 | 형식 확인 필요 |
| `rst_mona_cd` | legislator-assets-korea | 의원 코드 | 발의 행태 + 자산 연결 |
| `bill_id` | na-legislative-events-korea | 법안 ID | 동일 소스, 직접 조인 |
| `rst_proposer` | korean-politics-youtube (`HG_NM`) | 의원 이름 | 동명이인 주의, 코드 선호 |
| `committee_nm` | committee-witnesses-korea | 위원회명 | harmonization 필요 |
