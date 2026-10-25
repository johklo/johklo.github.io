---
title: "05. 모델 등록과 버전 관리"
description: "AML에 기록한 모델의 출처를 유지하며 이름과 구체 버전으로 등록하고 다시 읽기"
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 50
tags: ["mlflow", "mlops", "azure-machine-learning"]
aliases:
  - "/docs/tech/mlflow-azure-machine-learning/05-model-registration/"
---

실행에 모델 파일을 남기는 일과 관리할 모델 버전을 만드는 일을 나눴다. 여러 후보 중 선택한 run의 모델을 같은 AML workspace의 Models에 등록하는 흐름이다.

## 준비 조건

[04편](/docs/tech/ops/mlops/labs/04-azureml-tracking-and-jobs/)에서 학습을 마치고 AML을 대상으로 `compare.py`를 실행한 상태를 기준으로 한다. Tracking URI와 Registry URI는 같은 AML workspace여야 하며, 모델을 등록할 권한도 필요하다. 로컬 SQLite를 대상으로 실행하면 등록되는 곳도 로컬이며 AML 등록을 확인한 것은 아니다.

## 등록 전 대상 확인

```powershell
.\.venv\Scripts\python.exe -c "import mlflow; print('tracking:', mlflow.get_tracking_uri()); print('registry:', mlflow.get_registry_uri())"
```

두 URI와 `selected-run.json`의 기록 대상이 같은지 확인한다. 대상이 바뀌었다면 현재 대상에서
`compare.py`를 다시 실행한다. 로컬 선택 파일의 run ID를 AML에 그대로 넘기지 않는다.

## 모델 재로딩과 버전 등록

학습 때 사용한 Python 객체가 아니라 저장된 모델을 다시 읽어 예측한다. 테스트 데이터는 이 단계에서 선택된 후보에만 적용한다. 테스트 결과를 보며 계속 다른 `C`를 고르면 이 데이터도 모델 선택에 사용된 셈이 된다.

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

등록 후에는 처리 결과로 받은 구체적인 버전을 사용한다. 다시 실행하면 새 버전이 만들어지므로 항상 `1`이라고 가정하지 않는다.

모델 등록은 배포가 아니다. 아직 HTTP API나 추론용 VM을 만든 것은 아니다. 학습 환경과 다른 Python 환경에서 모델을 읽을 때는 필요한 의존성을 별도로 갖춰야 한다. 직렬화된 모델을 읽는 작업이므로, 출처를 신뢰할 수 없는 모델 파일을 가져와 실행하지 않는다.

### 저장, 기록, 등록의 차이

| 작업 | 대표 API | 달라지는 것 |
| --- | --- | --- |
| 로컬 모델 폴더 생성 | `mlflow.sklearn.save_model()` | 지정한 로컬 경로에 MLflow 모델 형식으로 저장 |
| 실행 결과로 모델 기록 | `mlflow.sklearn.log_model()` | 현재 추적 대상의 run에 모델 연결 |
| 관리할 버전 등록 | `mlflow.register_model()` | Registry에 모델 이름과 버전 생성 |
| 모델 재사용 | `mlflow.pyfunc.load_model()` | 참조한 모델을 읽고 현재 Python에서 추론 |

`log_model()`에 `registered_model_name`을 지정해 기록과 등록을 함께 수행하는 방식도 있다. 이번 예제는 여러 후보를 기록한 뒤 선택한 것만 등록하려고 두 단계를 분리했다. 자동 기록이 모든 후보를 곧바로 출시 가능한 모델로 만든다는 뜻은 아니다.

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

폴더를 가져와 등록했다고 이전 학습의 코드, 데이터, 메트릭이 새로운 AML run으로 복원되지는 않는다. 모델을 실행할 수 있다는 확인과 학습 이력을 복원했다는 확인은 다르다.

### Workspace 모델과 공유 Registry

이 노트의 Registry는 같은 AML workspace 안의 Models를 뜻한다. 여러 workspace 사이에서 자산을 공유하는 별도 AML registry 리소스와 같지 않다.

[모델 관리 지원 표](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models-mlflow?view=azureml-api-2#review-supported-capabilities-for-managing-models)에 따르면 MLflow의 run 참조를 이용한 등록은 같은 workspace 안에서 수행하며, 조직 단위 registry 관리는 AML CLI나 SDK 등 별도 경로로 다룬다. Tracking URI와 Registry URI를 각각 임의의 다른 workspace로 바꿔도 같은 run을 등록할 수 있다고 일반화하지 않는다.

MLflow stage도 배포 상태와 다르다. AML에서는 stage를 MLflow SDK로 다루는 범위와 studio 또는 배포에서 쓰는 범위가 같지 않다. 모델을 `Production` stage로 표시하는 작업이 온라인 트래픽 전환을 실행하는 것은 아니다. 이 예제는 배포나 재로딩의 대상을 설명할 때 구체적인 모델 버전을 사용한다.

## 확인할 결과

`finalize.py`는 테스트 정확도와 `models:/wine-logistic-study/<version>` 형태의 URI를 출력한다. 고정한 예제의 로컬 확인에서는 테스트 정확도가 약 `0.9722`였다. 실제 AML 결과는 해당 실행에서 확인한다. Models에서는 이름과 버전, 원천 run을 함께 확인한다. 등록된 모델을 다시 읽은 예측은 원천 run에서 읽은 모델과 같아야 한다.

## 오류 확인

| 증상 | 확인할 부분 |
| --- | --- |
| 추적 대상이 바뀌었다는 오류 | AML에서 `compare.py`를 다시 실행했는지 |
| 원천 run이나 `model` 경로를 찾지 못함 | run ID, 추적 대상, 모델을 기록한 artifact 경로 |
| 등록 때만 403 발생 | 실행 기록과 별개인 모델 생성 및 갱신 권한 |
| 예상한 버전이 아닌 번호를 받음 | 같은 이름의 이전 등록 이력이 있는지 |
| 로컬 폴더 가져오기 실패 | `MLmodel`이 있는 완성된 폴더와 파일 URI인지 |

## 생각할 점

등록 성공이 성능, 지연, 입력 품질, 접근 제어를 충족했다는 뜻은 아니다. 이 실습의 검증 점수를 그대로 프로덕션 승인 기준으로 쓰지는 않는다.

- 모델을 파일로 가져온 것과 원래 학습 이력을 복원한 것은 왜 다른가.
- 구체 버전을 쓰지 않고 최신 모델을 참조하면 재실행에서 무엇이 달라질 수 있는가.
- 등록 성공과 출시 승인 사이에 어떤 검증과 책임이 남는가.

## 참고 자료

- [모델 Registry 관리](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models-mlflow?view=azureml-api-2)
- [아티팩트와 모델](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow-models?view=azureml-api-2)
- [기존 모델의 MLflow 변환](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-convert-custom-model-to-mlflow?view=azureml-api-2)

[이전: 04. AML 연결과 원격 학습 Job](/docs/tech/ops/mlops/labs/04-azureml-tracking-and-jobs/), [시리즈 목차](/docs/tech/ops/mlops/labs/), [다음: 06. 온라인 및 배치 추론과 모델 교체](/docs/tech/ops/mlops/labs/06-online-and-batch-inference/)
