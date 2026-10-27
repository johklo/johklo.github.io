---
title: "05. 모델 등록과 버전 관리"
description: "AML에 기록한 모델의 출처를 유지하며 이름과 버전으로 등록하고 다시 읽는다."
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 50
tags: ["mlflow", "mlops", "azure-machine-learning"]
aliases:
  - "/docs/tech/mlflow-azure-machine-learning/05-model-registration/"
---

run에 모델을 기록하는 것과 Registry 버전을 만드는 것은 별개다. 선택한 run의 모델을 같은 AML workspace에 등록한다.

## 준비 조건

[04편](/docs/tech/ops/mlops/labs/04-azureml-tracking-and-jobs/)에서 학습을 마치고 AML을 대상으로 `compare.py`를 실행한 상태를 기준으로 한다. Tracking URI와 Registry URI는 같은 AML workspace여야 하며, 모델을 등록할 권한도 필요하다. 로컬 SQLite를 대상으로 실행하면 등록되는 곳도 로컬이며 AML 등록을 확인한 것은 아니다.

## 등록 전 대상 확인

```powershell
.\.venv\Scripts\python.exe -c "import mlflow; print('tracking:', mlflow.get_tracking_uri()); print('registry:', mlflow.get_registry_uri())"
```

두 URI와 `selected-run.json`의 기록 대상이 같은지 확인한다. 대상이 바뀌었다면 현재 대상에서
`compare.py`를 다시 실행한다. 로컬 선택 파일의 run ID를 AML에 그대로 넘기지 않는다.

## 모델 재로딩과 버전 등록

학습 객체 대신 저장 모델을 다시 읽어 예측한다. 테스트 데이터는 선택 후보에 한 번 적용하며, 결과를 보고 `C`를 바꾸면 테스트 데이터가 선택에 사용된 셈이다.

`finalize.py`:

```python
import json
from pathlib import Path

import mlflow
import mlflow.pyfunc
import numpy as np
from sklearn.metrics import accuracy_score

from src.train import load_data


selection = json.loads(
    Path("selected-run.json").read_text(encoding="utf-8")
)
if selection["tracking_uri"] != mlflow.get_tracking_uri():
    raise RuntimeError("Tracking backend changed; run compare.py again")
if mlflow.get_registry_uri() != mlflow.get_tracking_uri():
    raise RuntimeError("This lab requires tracking and registry in the same backend")

run_id = selection["run_id"]
run = mlflow.get_run(run_id)
_, _, X_test, _, _, y_test, fingerprint = load_data()
if run.data.params["dataset_sha256"] != fingerprint:
    raise RuntimeError("Current dataset differs from the selected run")

model = mlflow.pyfunc.load_model(f"runs:/{run_id}/model")
predictions = model.predict(X_test)
print(f"test_accuracy={accuracy_score(y_test, predictions):.4f}")

registered = mlflow.register_model(
    model_uri=f"runs:/{run_id}/model",
    name="wine-logistic-study",
)
model_uri = f"models:/{registered.name}/{registered.version}"
registered_model = mlflow.pyfunc.load_model(model_uri)
np.testing.assert_array_equal(
    predictions, registered_model.predict(X_test)
)
print(f"registered_model_uri={model_uri}")
```

```powershell
.\.venv\Scripts\python.exe .\finalize.py
```

| URI | 가리키는 대상 |
| --- | --- |
| `runs:/<run-id>/model` | 특정 실행에 기록한 모델 |
| `models:/wine-logistic-study/<version>` | 이름과 버전으로 등록한 모델 |

등록 결과의 구체 버전을 사용한다. 재실행 시 새 버전이 생길 수 있으므로 `1`로 고정하지 않는다.

등록은 배포가 아니며 HTTP API나 추론 VM도 만들지 않는다. 다른 Python 환경에서는 의존성을 준비하고, 출처를 신뢰할 수 없는 직렬화 모델은 실행하지 않는다.

### 저장, 기록, 등록의 차이

| 작업 | 대표 API | 달라지는 것 |
| --- | --- | --- |
| 로컬 모델 폴더 생성 | `mlflow.sklearn.save_model()` | 지정한 로컬 경로에 MLflow 모델 형식으로 저장 |
| 실행 결과로 모델 기록 | `mlflow.sklearn.log_model()` | 현재 추적 대상의 run에 모델 연결 |
| 관리할 버전 등록 | `mlflow.register_model()` | Registry에 모델 이름과 버전 생성 |
| 모델 재사용 | `mlflow.pyfunc.load_model()` | 참조한 모델을 읽고 현재 Python에서 추론 |

`log_model()`의 `registered_model_name`으로 기록과 등록을 묶을 수도 있다. 여기서는 후보를 비교한 뒤 선택 모델만 등록하며, 자동 기록이 출시 승인을 뜻하지는 않는다.

### 이미 학습한 모델을 가져오는 경로

AML에 모델을 등록하기 위해 언제나 다시 학습해야 하는 것은 아니다. [모델 관리 문서](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models-mlflow?view=azureml-api-2)는 기존 run에서의 등록과 로컬 MLflow 모델 폴더에서의 등록을 모두 다룬다.

| 현재 가진 것 | 필요한 과정 | 남길 출처 |
| --- | --- | --- |
| 같은 AML workspace의 run 모델 | `runs:/run_id/model`로 등록 | 원래 학습 run과 연결 |
| `MLmodel`이 있는 로컬 모델 폴더 | 로컬 폴더의 파일 URI로 등록 | 원래 학습 코드와 데이터의 이력을 별도 확인 |
| 가중치나 pickle 파일만 있는 기존 모델 | 지원 flavor의 `save_model()` 또는 PyFunc 래퍼로 패키징 후 등록 | 전처리, 의존성, 입력 계약과 기존 결과의 동등성 |

예를 들어 `exported_model`이 이미 완성된 MLflow 모델 폴더이고 Tracking과 Registry가 AML로 설정된 상태라면 아래처럼 등록할 수 있다. 이 코드는 앞의 학습 실습과 별개인 기존 모델 가져오기 예시다.

```python
from pathlib import Path

import mlflow


model_directory = Path("exported_model").resolve()
registered = mlflow.register_model(
    model_uri=model_directory.as_uri(),
    name="wine-logistic-import",
)
```

폴더 등록은 이전 코드, 데이터, 메트릭을 AML run으로 복원하지 않는다. 모델 실행 가능성과 학습 이력 복원은 별개다.

### Workspace 모델과 공유 Registry

여기서 Registry는 workspace 내부 Models다. 여러 workspace 간 자산 공유용 AML registry와 다르다.

[모델 관리 지원 표](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models-mlflow?view=azureml-api-2#review-supported-capabilities-for-managing-models)에 따르면 MLflow의 run 참조를 이용한 등록은 같은 workspace 안에서 수행하며, 조직 단위 registry 관리는 AML CLI나 SDK 등 별도 경로로 다룬다. Tracking URI와 Registry URI를 각각 임의의 다른 workspace로 바꿔도 같은 run을 등록할 수 있다고 일반화하지 않는다.

MLflow stage는 배포 상태가 아니다. `Production` 표시는 온라인 트래픽을 전환하지 않으며 AML SDK, Studio, 배포의 지원 범위도 다르다. 이 예제는 구체 버전을 사용한다.

## 확인할 결과

`finalize.py`는 테스트 정확도와 `models:/wine-logistic-study/<version>`를 출력한다. 고정 로컬 예제는 약 `0.9722`였으며 AML 값은 해당 실행에서 확인한다. Models의 이름, 버전, 원천 run과 재로딩 예측의 일치도 확인한다.

## 오류 확인

| 증상 | 확인할 부분 |
| --- | --- |
| 추적 대상이 바뀌었다는 오류 | AML에서 `compare.py`를 다시 실행했는지 |
| 원천 run이나 `model` 경로를 찾지 못함 | run ID, 추적 대상, 모델을 기록한 artifact 경로 |
| 등록 때만 403 발생 | 실행 기록과 별개인 모델 생성 및 갱신 권한 |
| 예상한 버전이 아닌 번호를 받음 | 같은 이름의 이전 등록 이력이 있는지 |
| 로컬 폴더 가져오기 실패 | `MLmodel`이 있는 완성된 폴더와 파일 URI인지 |

## 생각할 점

등록은 성능, 지연, 입력 품질, 접근 제어의 충족을 뜻하지 않는다. 실습 점수를 프로덕션 승인 기준으로 쓰지 않는다.

- 모델을 파일로 가져온 것과 원래 학습 이력을 복원한 것은 왜 다른가.
- 구체 버전을 쓰지 않고 최신 모델을 참조하면 재실행에서 무엇이 달라질 수 있는가.
- 등록 성공과 출시 승인 사이에 어떤 검증과 책임이 남는가.

## 참고 자료

- [모델 Registry 관리](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models-mlflow?view=azureml-api-2)
- [아티팩트와 모델](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow-models?view=azureml-api-2)
- [기존 모델의 MLflow 변환](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-convert-custom-model-to-mlflow?view=azureml-api-2)

[이전: 04. AML 연결과 원격 학습 Job](/docs/tech/ops/mlops/labs/04-azureml-tracking-and-jobs/), [시리즈 목차](/docs/tech/ops/mlops/labs/), [다음: 06. 온라인 및 배치 추론과 모델 교체](/docs/tech/ops/mlops/labs/06-online-and-batch-inference/)
