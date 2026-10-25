---
title: "03. 모델 형식과 재사용"
description: "MLmodel, flavor, signature와 환경을 구분하고 저장 모델의 예측과 입력 계약을 확인하기"
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 30
tags: ["mlflow", "mlops", "azure-machine-learning"]
aliases:
  - "/docs/tech/mlflow-azure-machine-learning/03-model-format-and-loading/"
---

모델 파일을 보관하는 것만으로는 다른 환경에서 같은 방식으로 읽고 예측하기 어렵다. 저장된 파일과 로딩 방법, 입력 계약, 의존성을 하나의 모델 패키지로 묶는 의미를 정리했다.

## 준비 조건

[02편](/docs/tech/ops/mlops/labs/02-query-and-compare/)의 선택 파일과 `src\train.py`가 필요하다. 같은 실습 폴더에서 로컬 Tracking URI를 사용한다. 새 터미널에서는 02편의 환경 변수를 다시 지정한다. 이번 편에서는 모델 이름과 버전을 등록하지 않는다.

## MLflow 모델 폴더의 구조

모델의 기준은 폴더 이름이 아니라 안에 있는 `MLmodel` 파일이다. 이 실습에서는 `model`이라는 경로를 선택했지만, 이름을 `classifier`로 바꾸어도 같은 형식을 쓸 수 있다.

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

위 목록은 이번 scikit-learn 예제의 구조다. 다른 프레임워크는 가중치 파일이나 추가 코드의 형식이 달라질 수 있다.

| 구성 | 설명하는 것 | 확인할 이유 |
| --- | --- | --- |
| `MLmodel` | flavor, 모델 파일 위치, signature 등 | 어떤 방식으로 모델을 읽고 실행할지 판단 |
| `model.pkl` | 이번 Pipeline의 학습된 상태 | 전처리와 분류기가 함께 저장되었는지 확인 |
| 환경 파일 | Python과 패키지 의존성 | 학습 시점과 추론 시점의 환경 비교 |
| 입력 예시 파일 | 모델에 전달할 데이터의 예 | 열 이름, 형태, 요청 예시 확인 |

모델 파일 하나를 임의의 폴더에 넣고 이름만 `mlflow_model`로 지정해도 이 구조가 생기는 것은 아니다. MLflow의 저장 또는 로깅 API로 모델의 로딩 방식과 의존성까지 표현해야 한다.

## Flavor와 signature

Flavor는 모델을 저장하고 읽는 방법이다. 이번 모델의 `MLmodel`에는 `sklearn`과 `python_function` 두 flavor가 들어간다.

| 읽는 방법 | 얻는 대상 | 사용할 때의 차이 |
| --- | --- | --- |
| `mlflow.sklearn.load_model()` | 원래의 scikit-learn Pipeline | `predict()`와 `predict_proba()` 등 원래 인터페이스 사용 |
| `mlflow.pyfunc.load_model()` | 공통 `predict()` 인터페이스의 모델 래퍼 | 프레임워크에 덜 의존하는 추론 호출 |

이 예제의 PyFunc `predict()`는 클래스 번호를 반환한다. PyFunc로 읽었다고 예측 확률로 바뀌지는 않는다. 확률이나 후처리 결과를 반환하려면 로깅 단계에서 예측 동작을 바꾸거나 별도 래퍼로 패키징해야 한다.

Signature는 그 인터페이스가 기대하는 입력과 출력을 설명한다. Wine 예제는 13개 수치 열을 가진 DataFrame을 받는 column 기반 signature다. 이미지나 다차원 배열은 tensor 기반 signature로 차원과 타입을 표현할 수 있다. 타입 검사를 통과했다는 사실과 값이 업무상 올바르다는 사실은 다르다.

## 모델 환경과 AML 실행 환경

MLflow 모델의 `conda.yaml`은 모델을 읽고 예측하는 데 필요한 의존성이다. 04편에서 만드는 실습 루트의 `conda.yml`은 AML 학습 Job의 실행 환경이다. 이름이 비슷해도 적용 대상이 다르다.

| 환경 | 적용 대상 | 확인할 내용 |
| --- | --- | --- |
| 로컬 가상환경 | 학습과 조회를 실행하는 로컬 Python | MLflow와 플러그인이 실제 인터프리터에 설치되었는지 |
| MLflow 모델 환경 | 저장된 모델의 로딩과 추론 | 모델 패키지의 의존성이 충분한지 |
| AML Job 환경 | 원격 학습 컨테이너 | 학습 코드와 패키지, 이미지가 맞는지 |
| AML 배포 환경 | 온라인 또는 배치 추론 런타임 | 추론 서버와 모델 의존성, 네트워크 조건이 맞는지 |

환경 파일이 있다고 로컬의 `load_model()`이 의존성을 자동 설치하는 것은 아니다. AML의 no-code 배포가 모델 환경으로 추론 환경을 구성하는 것과도 구분한다.

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

원래 모델의 타입은 `Pipeline`이며, native와 PyFunc 경로의 예측이 같아야 한다. 입력 signature에는 Wine 데이터의 13개 열이 나타나고 예측 행 수는 2다. 필수 열을 뺀 요청은 `missing inputs` 오류로 거절되어야 한다. 예상한 입력 오류와 그 밖의 실행 오류를 구분해 처리했다.

## 사용자 정의 모델로 확장

기본 flavor가 없거나 예측 반환값을 바꾸려는 경우는 자동 기록만으로 해결되지 않을 수 있다. [기존 모델의 MLflow 변환](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-convert-custom-model-to-mlflow?view=azureml-api-2)과 [사용자 정의 모델 로깅](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-mlflow-models?view=azureml-api-2#log-custom-models)은 `PythonModel`의 로딩과 `predict()` 구현, 모델 파일, signature, 환경을 함께 패키징하는 방식으로 연결해 읽었다. 변환 전후의 같은 입력에서 예측이 유지되는지 별도 확인할 대상이다.

## 오류 확인

| 증상 | 확인할 부분 |
| --- | --- |
| 모델 URI를 찾지 못함 | 선택한 run과 현재 추적 대상이 같은지 |
| `MLmodel`이 없음 | 원시 모델 파일만 저장했는지, 올바른 모델 폴더를 선택했는지 |
| 의존성 import 오류 | 모델 환경과 현재 가상환경의 차이 |
| 입력 열을 뺀 요청이 거절됨 | 필요한 signature 검사가 동작한 결과 |
| 확률 대신 클래스가 반환됨 | 저장된 모델의 `predict()` 동작이며 PyFunc가 이를 자동 변경하지 않음 |

## 생각할 점

저장한 모델을 읽는 것, 같은 코드를 실행하는 것, 같은 수치를 얻는 것은 다른 확인이다. 데이터와 분할 조건에 더해 Python, 의존성, 실행 환경까지 기록하는 이유로 남았다.

- 모델의 타입을 그대로 읽는 것과 공통 추론 인터페이스로 읽는 것은 언제 각각 필요한가.
- 입력 타입이 맞아도 의미가 틀린 데이터를 signature만으로 걸러낼 수 있는가.
- 모델의 환경 파일과 AML 학습 또는 배포 환경은 어떤 점에서 다른가.

## 참고 자료

- [아티팩트와 모델 형식](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow-models?view=azureml-api-2)
- [MLflow 모델 로깅](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-mlflow-models?view=azureml-api-2)
- [기존 모델의 MLflow 변환](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-convert-custom-model-to-mlflow?view=azureml-api-2)

[이전: 02. 실행 비교와 메트릭 및 아티팩트 조회](/docs/tech/ops/mlops/labs/02-query-and-compare/), [시리즈 목차](/docs/tech/ops/mlops/labs/), [다음: 04. AML 연결과 원격 학습 Job](/docs/tech/ops/mlops/labs/04-azureml-tracking-and-jobs/)
