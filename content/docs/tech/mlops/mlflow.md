---
title: "MLflow: 추천 후보에서 출시 모델까지"
description: "실험·평가·모델 버전을 연결하고 BentoML에 고정 버전을 전달하는 운영 가이드"
date: 2026-10-25T08:43:00+09:00
weight: 20
tags: ["mlops", "mlflow", "model-registry"]
---

MLflow는 Bookway의 실험 장부와 모델 보관함입니다. 학습 라이브러리가 모델을 만들고, MLflow는 **어떤 입력과 설정으로 어떤 결과가 나왔는지** 연결합니다. KFP는 실행 순서, BentoML은 서비스 요청 처리라는 다른 책임을 가집니다.

## 후보 비교에 남길 값

추천 기준선은 인기순, 후보는 개인화 순위 모델입니다. 시간 분할과 후보 도서 집합을 동일하게 유지하고 Recall@10·NDCG@10을 비교합니다. 실제 반응을 모르는 도서를 무조건 부정 표본으로 취급하면 평가가 달라지므로 표본 생성 규칙도 artifact로 보관합니다.

| MLflow 기록 | Bookway의 내용 |
| --- | --- |
| parameter | 집계 창 30일, rank, 난수 seed |
| tag | 코드 commit, 데이터 지문, 피처 계약 |
| metric | validation NDCG, cold-start 구간 성능, 추론 지연 |
| artifact | 평가 보고서, 분할 명세, 오류 분석 |
| model | 전처리를 포함한 모델과 signature, 의존성 |

다음 조각은 합성 점수를 새로 만드는 코드가 아니라 학습 단계가 생성한 파일을 기록합니다. `candidate.json`에는 `data_snapshot`, `feature_contract`, `code_revision`이, `evaluation.json`에는 수치형 `validation_ndcg_at_10`이 있다고 가정합니다.

```python
import json
from pathlib import Path
import mlflow

candidate = json.loads(Path("candidate.json").read_text(encoding="utf-8"))
evaluation = json.loads(Path("evaluation.json").read_text(encoding="utf-8"))
mlflow.set_experiment("bookway-ranking")
with mlflow.start_run() as run:
    mlflow.set_tags({key: candidate[key] for key in (
        "data_snapshot", "feature_contract", "code_revision"
    )})
    mlflow.log_metric(
        "validation_ndcg_at_10", evaluation["validation_ndcg_at_10"]
    )
    mlflow.log_artifacts("reports", artifact_path="evaluation")
    print(run.info.run_id)
```

Tracking URI와 인증은 환경에서 주입합니다. 이 기록만으로 모델 파일이 저장되지는 않습니다. 모델에 맞는 flavor로 전처리·signature와 함께 기록하고, 별도 환경에서 다시 로딩해 입출력을 확인한 뒤 Registry에 등록합니다.

## 등록과 승인을 분리하기

```text
MLflow run
  → 동일 조건의 평가 보고서
  → 품질·지연·입력 계약 검사
  → 등록 모델 bookway-ranker / 구체 버전 17
  → 서비스 명세 rec-r17
  → BentoML 패키지 / 컨테이너
```

모델 alias는 후보를 가리키기에 편리하지만 나중에 다른 버전을 가리킬 수 있습니다. `rec-r17`에는 alias를 해석한 **구체 모델 버전·artifact 지문**을 저장합니다. 서비스 시작 때마다 `latest`를 찾아오면 같은 이미지의 Pod 두 개가 다른 모델을 로딩할 수 있습니다.

## 서버와 운영 경계

팀 환경에서는 메타데이터 DB와 artifact object store를 분리하고 각각 백업·권한·보존 정책을 둡니다. 학습 작업은 기록 권한, 출시 작업은 승인된 버전 선택 권한, 서빙은 읽기 권한을 가집니다. Registry 쓰기 권한을 일반 추천 API에 주지 않습니다.

Tracking 장애에서 학습 산출물을 로컬에 남길 수는 있지만, 미기록 후보를 정상 승인된 모델로 배포해서는 안 됩니다. 모델 다운로드 실패는 readiness 실패로 드러내고 기존 정상 버전을 유지합니다.

MLflow의 LLM 추적·평가 기능도 선택지입니다. 이미 Langfuse나 LangSmith를 쓰면 실행 ID와 release를 연결하되 같은 원문을 여러 외부 서비스에 중복 전송하지 않습니다.

[공식 Tracking 문서](https://mlflow.org/docs/latest/ml/tracking/) / [기존 모델 등록 실습](../../mlflow-azure-machine-learning/) / [MLOps 전체 지도](../)
