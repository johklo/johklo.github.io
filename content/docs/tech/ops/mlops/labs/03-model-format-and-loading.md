---
title: "03. 모델 형식과 재사용"
description: "MLmodel, flavor, signature와 환경을 구분하고 저장 모델의 예측과 입력 계약을 확인한다."
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 30
tags: ["mlflow", "mlops", "azure-machine-learning"]
aliases:
  - "/docs/tech/mlflow-azure-machine-learning/03-model-format-and-loading/"
---

모델 파일만으로는 다른 환경에서 같은 방식으로 예측하기 어렵다. 파일, 로딩 방법, 입력 계약, 의존성을 모델 패키지로 묶는다.

## 준비 조건

[02편](/docs/tech/ops/mlops/labs/02-query-and-compare/)의 선택 파일과 `src\train.py`가 필요하다. 같은 실습 폴더에서 로컬 Tracking URI를 사용한다. 새 터미널에서는 02편의 환경 변수를 다시 지정한다. 이번 편에서는 모델 이름과 버전을 등록하지 않는다.

## MLflow 모델 폴더의 구조

모델 형식은 폴더명이 아니라 내부 `MLmodel`이 정의한다. `model` 대신 `classifier` 경로를 써도 형식은 같다.

```text
model
  MLmodel
  model.pkl
  conda.yaml
  requirements.txt
  python_env.yaml
  input_example.json
  serving_input_example.json
```

목록은 scikit-learn 예제 기준이며 프레임워크마다 가중치와 코드 형식이 다르다.

| 구성 | 설명하는 것 | 확인할 이유 |
| --- | --- | --- |
| `MLmodel` | flavor, 모델 파일 위치, signature 등 | 어떤 방식으로 모델을 읽고 실행할지 판단 |
| `model.pkl` | 이번 Pipeline의 학습된 상태 | 전처리와 분류기가 함께 저장되었는지 확인 |
| 환경 파일 | Python과 패키지 의존성 | 학습 시점과 추론 시점의 환경 비교 |
| 입력 예시 파일 | 모델에 전달할 데이터의 예 | 열 이름, 형태, 요청 예시 확인 |

파일명을 `mlflow_model`로 바꾸는 것만으로 구조가 생기지 않는다. MLflow 저장, 로깅 API로 로딩 방식과 의존성을 함께 기록한다.

## Flavor와 signature

Flavor는 모델을 저장하고 읽는 방법이다. 이번 모델의 `MLmodel`에는 `sklearn`과 `python_function` 두 flavor가 들어간다.

| 읽는 방법 | 얻는 대상 | 사용할 때의 차이 |
| --- | --- | --- |
| `mlflow.sklearn.load_model()` | 원래의 scikit-learn Pipeline | `predict()`와 `predict_proba()` 등 원래 인터페이스 사용 |
| `mlflow.pyfunc.load_model()` | 공통 `predict()` 인터페이스의 모델 래퍼 | 프레임워크에 덜 의존하는 추론 호출 |

이 모델의 PyFunc `predict()`는 클래스 번호를 반환하며 확률로 바꾸지 않는다. 확률이나 후처리가 필요하면 로깅 동작을 바꾸거나 별도 래퍼로 패키징한다.

Signature는 입력, 출력을 설명한다. Wine 모델은 수치 열 13개의 DataFrame을 받는 column 기반 형식이며, 이미지와 다차원 배열은 tensor 기반 signature로 차원과 타입을 표현한다. 타입 검증은 업무상 유효성을 보장하지 않는다.

## 모델 환경과 AML 실행 환경

모델의 `conda.yaml`은 로딩, 추론 의존성이고, 04편 루트의 `conda.yml`은 AML 학습 Job 환경이다.

| 환경 | 적용 대상 | 확인할 내용 |
| --- | --- | --- |
| 로컬 가상환경 | 학습과 조회를 실행하는 로컬 Python | MLflow와 플러그인이 실제 인터프리터에 설치되었는지 |
| MLflow 모델 환경 | 저장된 모델의 로딩과 추론 | 모델 패키지의 의존성이 충분한지 |
| AML Job 환경 | 원격 학습 컨테이너 | 학습 코드와 패키지, 이미지가 맞는지 |
| AML 배포 환경 | 온라인 또는 배치 추론 런타임 | 추론 서버와 모델 의존성, 네트워크 조건이 맞는지 |

환경 파일은 로컬 `load_model()`에서 자동 설치되지 않는다. AML no-code 배포의 환경 구성과 구분한다.

## 실습: 저장 모델과 입력 계약 확인

다음 코드를 `check_model.py`로 저장한다. 검증 데이터 두 행을 사용하므로 최종 테스트 데이터를 후보 선택에 다시 사용하는 실습은 아니다.

`check_model.py`:

```python
import json
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
from mlflow.exceptions import MlflowException

from src.train import load_data


selection = json.loads(
    Path("selected-run.json").read_text(encoding="utf-8")
)
if selection["tracking_uri"] != mlflow.get_tracking_uri():
    raise RuntimeError("Tracking backend changed; run compare.py again")

run_id = selection["run_id"]
_, X_val, _, _, _, _, fingerprint = load_data()
run = mlflow.get_run(run_id)
if run.data.params["dataset_sha256"] != fingerprint:
    raise RuntimeError("Current dataset differs from the selected run")

samples = X_val.head(2)
native = mlflow.sklearn.load_model(f"runs:/{run_id}/model")
wrapped = mlflow.pyfunc.load_model(f"runs:/{run_id}/model")
np.testing.assert_array_equal(
    native.predict(samples), wrapped.predict(samples)
)
print("native type:", type(native).__name__)
print("signature:", wrapped.metadata.signature)
print("prediction rows:", len(wrapped.predict(samples)))

try:
    wrapped.predict(samples.drop(columns=samples.columns[0]))
except MlflowException as error:
    if "missing inputs" not in str(error):
        raise
    print("expected signature error:", error)
else:
    raise AssertionError("Missing required input was accepted")
```

```powershell
.\.venv\Scripts\python.exe .\check_model.py
```

## 확인할 결과

원래 타입은 `Pipeline`이며 native와 PyFunc 예측이 같아야 한다. Signature에는 13개 열이 표시되고 두 행을 예측한다. 필수 열 누락은 `missing inputs`로 거절하며 다른 오류와 구분한다.

## 사용자 정의 모델로 확장

기본 flavor가 없거나 반환값을 바꾸려면 [기존 모델 변환](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-convert-custom-model-to-mlflow?view=azureml-api-2)과 [사용자 정의 모델 로깅](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-mlflow-models?view=azureml-api-2#log-custom-models)에서 `PythonModel`, `predict()`, 파일, signature, 환경을 함께 패키징하는 방법을 참고한다. 변환 전후의 예측 동등성도 확인한다.

## 오류 확인

| 증상 | 확인할 부분 |
| --- | --- |
| 모델 URI를 찾지 못함 | 선택한 run과 현재 추적 대상이 같은지 |
| `MLmodel`이 없음 | 원시 모델 파일만 저장했는지, 올바른 모델 폴더를 선택했는지 |
| 의존성 import 오류 | 모델 환경과 현재 가상환경의 차이 |
| 입력 열을 뺀 요청이 거절됨 | 필요한 signature 검사가 동작한 결과 |
| 확률 대신 클래스가 반환됨 | 저장된 모델의 `predict()` 동작이며 PyFunc가 이를 자동 변경하지 않음 |

## 생각할 점

모델 로딩, 코드 재실행, 동일 수치 재현은 서로 다른 검증이다. 데이터, 분할뿐 아니라 Python, 의존성, 실행 환경도 기록한다.

- 모델의 타입을 그대로 읽는 것과 공통 추론 인터페이스로 읽는 것은 언제 각각 필요한가.
- 입력 타입이 맞아도 의미가 틀린 데이터를 signature만으로 걸러낼 수 있는가.
- 모델의 환경 파일과 AML 학습 또는 배포 환경은 어떤 점에서 다른가.

## 참고 자료

- [아티팩트와 모델 형식](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow-models?view=azureml-api-2)
- [MLflow 모델 로깅](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-mlflow-models?view=azureml-api-2)
- [기존 모델의 MLflow 변환](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-convert-custom-model-to-mlflow?view=azureml-api-2)

[이전: 02. 실행 비교와 메트릭 및 아티팩트 조회](/docs/tech/ops/mlops/labs/02-query-and-compare/), [시리즈 목차](/docs/tech/ops/mlops/labs/), [다음: 04. AML 연결과 원격 학습 Job](/docs/tech/ops/mlops/labs/04-azureml-tracking-and-jobs/)
