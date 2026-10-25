---
title: "데이터 버전: DVC와 시간 기준"
description: "Bookway의 행동 스냅샷을 코드·학습·평가와 연결하고 되돌리는 방법"
date: 2026-10-25T08:43:00+09:00
weight: 10
tags: ["mlops", "data-versioning", "dvc"]
---

재료 봉투에 이름만 적으면 어느 날 들어온 재료인지 알 수 없습니다. Bookway의 `events.csv`도 파일 이름만 같다고 같은 학습 데이터는 아닙니다. DVC는 큰 데이터 자체를 Git에 넣는 대신, **데이터를 식별하는 메타데이터를 코드와 함께 관리**하는 선택지입니다. 책의 실험·아티팩트 관리를 보완하는 계층입니다.

## 학습 입력을 정하는 계약

이벤트에는 `event_id`, `customer_id`, `book_id`, `event_time`, `ingested_at`, `event_type`이 필요합니다. 중복 제거는 이벤트 ID, 시간 분할은 업무상 발생 시각, 늦게 도착한 자료의 사용 가능 여부는 수집 시각으로 판단합니다.

```text
events-20261024
  → 중복·스키마 검사
  → train: 과거 / validation: 이후 / test: 최종 보류
  → customer_features_v1
  → MLflow run → rec-r17
```

미래 클릭을 과거 고객 집계에 넣으면 파일 버전이 완벽해도 누수입니다. 데이터 출처·시간 경계·변환 코드·삭제 정책을 함께 명세해야 합니다. 추천에서는 사용자별 cold start도 별도 집계합니다.

## DVC를 연결하는 절차

아래는 이미 Git으로 관리하는 **별도 Bookway 프로젝트**에서, 준비된 합성 `data\events.csv`를 추적하는 명령입니다. DVC가 설치된 환경을 전제로 합니다.

```powershell
dvc init
dvc add data\events.csv
git add data\events.csv.dvc data\.gitignore .dvc
git commit -m "Track Bookway event snapshot"
```

`.dvc`는 원본의 복사본이 아니라 복원에 필요한 포인터입니다. 팀이 공유하는 object store를 DVC remote로 설정하고 `dvc push`까지 마쳐야 다른 환경에서 `dvc pull`로 데이터를 가져올 수 있습니다. 인증값은 Git의 DVC 설정에 넣지 않고 실행 환경의 자격 증명을 사용합니다.

학습 명세에는 Git commit, `.dvc` 메타데이터, 변환 설정, train/validation/test 경계와 결과 행 수를 기록합니다. MLflow에는 그 명세를 artifact로 연결합니다. `dvc repro`로 단계를 묶을 수도 있지만, 여러 컨테이너의 자원·재시도·스케줄은 [KFP](../kubeflow/)의 책임과 구분합니다.

## 복원과 삭제

과거 코드와 포인터를 작업용 복제본에서 선택한 뒤 `dvc pull`과 `dvc checkout`으로 복원합니다. 이때 remote에 실제 바이트가 남아 있어야 합니다. 체크섬은 무결성을 돕지만 권한과 적법한 보관을 보장하지 않습니다.

개인정보 삭제는 최신 CSV에서 한 행을 지우는 것으로 끝나지 않습니다. 과거 스냅샷·캐시·피처·모델의 보존 정책과 재학습 필요성을 별도로 검토합니다. 운영용 원천 데이터는 공개 GitHub나 공개 object store에 올리지 않습니다.

| 문제 | 확인 위치 | 대응 |
| --- | --- | --- |
| 포인터는 있는데 다운로드 실패 | remote 경로·권한·보존 기간 | 다른 데이터로 대체하지 않고 학습 중단 |
| 같은 파일명이지만 행 수 변경 | 지문·manifest | 새 스냅샷으로 평가 |
| 지표가 갑자기 상승 | 시간 분할·집계 창 | 미래 정보 유입 조사 |

[공식 DVC 가이드](https://doc.dvc.org/start) / [MLOps 전체 지도](../) / [피처 시점 계약](../feast/)
