---
title: "MLflow 기초: 실험 기록부터 모델 레지스트리와 서빙까지"
description: "MLflow로 실험을 기록하고 모델 버전과 별칭을 관리해 실제 HTTP 추론까지 연결하는 흐름을 안내합니다."
date: 2026-10-25T19:30:00+09:00
weight: 10
tags: ["mlops", "mlflow", "hands-on"]
---

재료와 절차를 노트에 적고 결과물에 이름표를 붙인다고 생각해 보겠습니다. MLflow는 이 노트와 제품 카탈로그에 해당합니다. 학습 맥락과 모델 파일을 기록하고, 승인된 버전을 서비스에 연결합니다.

가상의 온라인 서점 Bookway에서 책 분류 모델을 실험합니다. scikit-learn에 포함된 Wine 데이터셋으로 실행 기록부터 Registry와 HTTP 추론까지 한 작업 폴더에서 이어갑니다.

## 1단계. MLflow의 역할과 용어 익히기

코드를 실행할 때마다 결과만 남기면, 시간이 지난 뒤 어떤 설정이 그 결과를 만들었는지 알기 어렵습니다. MLflow Tracking은 실행의 맥락을 함께 기록합니다. 모델을 만든 뒤에는 Model Registry에 버전을 등록하고, 배포 대상은 Alias로 가리킵니다. Tracking UI는 이 기록을 찾아 비교하는 화면입니다.

| 용어 | 쉬운 뜻 | MLflow에서 하는 일 |
| --- | --- | --- |
| Experiment | 관련 실험을 모아 둔 노트 묶음 | 실행들을 목적별로 분류합니다 |
| Run | 한 번 실행한 실험 기록 | 시작과 종료 시각, 파라미터, 지표, 태그를 묶습니다 |
| Parameter | 실행 전에 정한 설정값 | 모델 종류, 반복 횟수, 데이터 분할값처럼 변경 이유를 비교합니다 |
| Metric | 실행 결과를 숫자로 요약한 값 | 정확도나 손실처럼 실행 간 비교할 수 있는 값을 기록합니다. `step`을 주면 학습 순서에 따른 값도 남깁니다 |
| Artifact | 실행에서 나온 파일 | 모델, 그래프, 평가 보고서, 데이터 요약 파일을 보관합니다 |
| Model | 입력을 받아 예측하는 학습 결과물 | 서명과 입력 예시를 포함해 저장하고 다시 불러옵니다 |
| Registered model/version | 이름이 붙은 모델과 그 불변 버전 | 하나의 모델 이름 아래 새 버전을 차례로 등록합니다 |
| Alias | 특정 버전에 붙이는 움직이는 별칭 | `champion` 같은 이름으로 현재 배포 대상을 가리킵니다 |
| Tracking server | 기록을 받고 UI와 API를 제공하는 서버 | 클라이언트와 저장소 사이의 공통 접점입니다 |
| Backend store / artifact store | 기록용 장부와 파일 창고 | Backend store는 실행과 모델 버전 메타데이터를, Artifact store는 모델과 산출물 파일을 저장합니다 |

한 번 실행된 Run은 무엇을 기록할지 정하는 단위이고, Metric은 숫자, Artifact는 파일입니다. 둘을 구분하면 UI에서 숫자로 후보를 고른 다음 파일을 열어 조사할 수 있습니다. Registry의 버전은 고정된 이력이며, Alias는 배포 대상을 교체할 때 이동할 수 있는 포인터입니다.

## 2단계. 고정 버전 설치와 로컬 UI 시작하기

PyPI에서 확인한 최신 MLflow 3.x는 `3.17.2`입니다. 실습 버전은 MLflow `3.17.2`, scikit-learn `1.9.1`, pandas `3.1.0`이며 uv가 나머지 의존성을 해결합니다.

빈 작업 폴더를 현재 디렉터리로 두고 아래 명령을 실행합니다. Windows 사용자는 같은 명령을 WSL2의 Ubuntu 셸에서 실행할 수 있습니다.

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python mlflow==3.17.2 scikit-learn==1.9.1 pandas==3.1.0
```

한 터미널에서 Tracking Server를 띄웁니다. SQLite 파일과 Artifact 폴더가 있는 작업 폴더에서 시작해야 상대 경로가 예상한 위치에 만들어집니다.

```bash
source .venv/bin/activate
mlflow server --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlartifacts --host 127.0.0.1 --port 5055 --workers 1
```

`sqlite:///mlflow.db`는 실행과 Registry 메타데이터를 작업 폴더의 DB에, 모델과 첨부 파일은 `./mlartifacts`에 저장합니다. `http://127.0.0.1:5055`에서 UI를 엽니다. 서버는 루프백에만 바인딩해 공개하지 않습니다.

각 파일은 `MLFLOW_TRACKING_URI`를 사용하며, 지정하지 않으면 `http://127.0.0.1:5055`에 연결합니다. Python 파일을 같은 폴더에 저장해 실행합니다.

## 3단계. 첫 Run에 파라미터와 지표, 파일 남기기

Wine 데이터를 분리해 Logistic Regression 기준 모델을 학습합니다. 파라미터와 태그를 기록하고 검증 정확도를 `step=1`로 남긴 뒤, 요약 JSON을 Artifact로 첨부합니다. 반복 기록의 `step` 값은 그래프의 가로축입니다.

`track_first.py` 파일을 만듭니다.

```python
import json
import os
from pathlib import Path

import mlflow
import pandas as pd
from sklearn.datasets import load_wine
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5055"))
mlflow.set_experiment("bookway-wine-basics")
wine = load_wine(as_frame=True)
X = wine.data
y = wine.target
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.25, random_state=42, stratify=y
)

with mlflow.start_run(run_name="manual-logistic-baseline") as run:
    mlflow.set_tags({"project": "bookway", "dataset": "sklearn-wine", "stage": "baseline"})
    mlflow.log_params({
        "model_family": "LogisticRegression",
        "max_iter": 1000,
        "test_size": 0.25,
        "random_state": 42,
    })
    model = LogisticRegression(max_iter=10000, random_state=42)
    model.fit(X_train, y_train)
    accuracy = accuracy_score(y_test, model.predict(X_test))
    mlflow.log_metric("validation_accuracy", accuracy, step=1)
    report = {"validation_accuracy": float(accuracy), "test_rows": len(y_test)}
    Path("first_run_metrics.json").write_text(json.dumps(report, indent=2) + "\n")
    mlflow.log_artifact("first_run_metrics.json")
    print(f"run_id={run.info.run_id}")
    print(f"validation_accuracy={accuracy:.4f}")
```

실행합니다.

```bash
.venv/bin/python track_first.py
```

실행 결과에서 Run ID와 검증 정확도를 확인했습니다.

```text
run_id=dfcbea1456154840a6046446c5a2d9c0
validation_accuracy=0.9556
```

Run ID는 실행마다 달라집니다. `first_run_metrics.json`은 현재 폴더와 해당 Run의 Artifact에 저장됩니다. UI에서는 파라미터, 메트릭, 태그, 파일을 함께 봅니다.

## 4단계. scikit-learn 자동 기록 사용하기

자동 로깅은 `fit()`에서 하이퍼파라미터, 학습 지표와 모델 산출물을 기록합니다. 검증 품질은 코드에서 따로 계산해 남깁니다.

`autolog.py` 파일은 `mlflow.sklearn.autolog()`를 설정한 뒤 같은 Wine 데이터를 Random Forest에 학습합니다. 마지막에 Tracking API로 저장된 파라미터와 메트릭, Artifact 목록을 조회합니다.

```python
import os

import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient
from sklearn.datasets import load_wine
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5055"))
mlflow.set_experiment("bookway-wine-basics")
mlflow.sklearn.autolog(log_models=True, log_datasets=True)
wine = load_wine(as_frame=True)
X_train, X_test, y_train, y_test = train_test_split(
    wine.data, wine.target, test_size=0.25, random_state=42, stratify=wine.target
)

with mlflow.start_run(run_name="autolog-random-forest") as run:
    mlflow.set_tag("project", "bookway")
    mlflow.log_param("model_family", "RandomForestClassifier")
    model = RandomForestClassifier(n_estimators=120, max_depth=4, random_state=42)
    model.fit(X_train, y_train)
    accuracy = accuracy_score(y_test, model.predict(X_test))
    mlflow.log_metric("validation_accuracy", accuracy)
    logged = MlflowClient().get_run(run.info.run_id)
    artifacts = [item.path for item in MlflowClient().list_artifacts(run.info.run_id)]
    print(f"run_id={run.info.run_id}")
    print(f"logged_params={len(logged.data.params)}")
    print(f"logged_metrics={sorted(logged.data.metrics)}")
    print(f"artifact_paths={artifacts}")
```

```bash
.venv/bin/python autolog.py
```

관찰한 요약은 다음과 같습니다.

```text
logged_params=20
logged_metrics=['training_accuracy_score', 'training_f1_score', 'training_log_loss', 'training_precision_score', 'training_recall_score', 'training_roc_auc', 'training_score', 'validation_accuracy']
artifact_paths=['estimator.html', 'training_confusion_matrix.png']
```

자동 학습 메트릭과 검증 메트릭을 구분합니다. 예제의 `validation_accuracy`는 검증 분할에서 별도로 계산했습니다. 실제 서비스에는 업무에 맞는 검증 데이터와 기준이 필요합니다.

## 5단계. 서명과 입력 예시를 포함해 모델 저장하기

Model Signature는 입출력 스키마를, `input_example`은 예상 입력을 나타냅니다. 다음 코드는 서명과 예시를 저장하고 `mlflow.pyfunc.load_model()`로 다시 읽어 예측을 비교합니다.

MLflow `3.17.2`의 함수 시그니처에서 `name=`을 확인했습니다. 예제는 이전 `artifact_path=` 대신 새 API의 `name=`을 사용합니다.

`log_model.py` 파일을 저장합니다.

```python
import os

import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from sklearn.datasets import load_wine
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5055"))
mlflow.set_experiment("bookway-wine-basics")
wine = load_wine(as_frame=True)
X_train, X_test, y_train, y_test = train_test_split(
    wine.data, wine.target, test_size=0.25, random_state=42, stratify=wine.target
)
model = LogisticRegression(max_iter=10000, random_state=7)
model.fit(X_train, y_train)
accuracy = accuracy_score(y_test, model.predict(X_test))
input_example = X_test.head(2)
signature = infer_signature(input_example, model.predict(input_example))

with mlflow.start_run(run_name="signature-and-example") as run:
    mlflow.set_tag("bookway_model_role", "registry_candidate")
    mlflow.log_param("model_family", "LogisticRegression")
    mlflow.log_metric("validation_accuracy", accuracy)
    model_info = mlflow.sklearn.log_model(
        model,
        name="wine_classifier",
        signature=signature,
        input_example=input_example,
    )
    loaded = mlflow.pyfunc.load_model(model_info.model_uri)
    original = model.predict(X_test)
    restored = loaded.predict(X_test)
    print(f"run_id={run.info.run_id}")
    print(f"model_uri={model_info.model_uri}")
    print(f"validation_accuracy={accuracy:.4f}")
    print(f"predictions_match={bool((original == restored).all())}")
```

```bash
.venv/bin/python log_model.py
```

실행에서 확인한 주요 결과입니다.

```text
model_uri=models:/m-a497bab700e24c20b9a2e51907554304
validation_accuracy=0.9556
predictions_match=True
```

MLflow 3은 `models:/m-...` 형식의 Logged Model URI를 반환할 수 있습니다. `model_info.model_uri`를 그대로 등록과 로드에 재사용합니다. `predictions_match=True`는 저장 전후 예측이 같았다는 뜻입니다.

## 6단계. 조건과 지표로 Run 비교하기

`search_runs()`는 조건에 맞는 Run을 찾아 정렬합니다. 예제는 검증 정확도로 필터링하고 내림차순 정렬합니다.

`compare_runs.py` 파일을 저장합니다.

```python
import os

import mlflow
import pandas as pd

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5055"))
experiment = mlflow.get_experiment_by_name("bookway-wine-basics")
runs = mlflow.search_runs(
    experiment_ids=[experiment.experiment_id],
    filter_string="metrics.validation_accuracy >= 0",
    order_by=["metrics.validation_accuracy DESC"],
    max_results=20,
)
view = runs[["run_id", "tags.mlflow.runName", "params.model_family", "metrics.validation_accuracy"]].copy()
view["params.model_family"] = view["params.model_family"].fillna("(autologged)")
print(view.to_string(index=False, formatters={"metrics.validation_accuracy": "{:.4f}".format}))
```

```bash
.venv/bin/python compare_runs.py
```

이번 조회의 상위 결과는 다음과 같습니다.

```text
                          run_id      tags.mlflow.runName    params.model_family metrics.validation_accuracy
7fa5a13066b14c6c89a31f5502faff00    autolog-random-forest RandomForestClassifier                      1.0000
8d29a2911b1b448ea6a2849a244939a7    signature-and-example     LogisticRegression                      0.9556
dfcbea1456154840a6046446c5a2d9c0 manual-logistic-baseline     LogisticRegression                      0.9556
```

UI에서는 비교할 Run의 파라미터, 메트릭, Artifact, 상태를 함께 봅니다. 작은 검증 분할에서 나온 `1.0000`은 Bookway의 서비스 품질이나 출시 적합성을 증명하지 않습니다.

## 7단계. Registry 버전과 Alias 다루기

Registry는 출시 후보를 모델 이름과 버전으로 관리합니다. 예제는 모델을 등록하고 `champion` 별칭을 지정한 뒤, 별칭 URI와 고정 버전 URI의 예측을 비교합니다.

`register_model.py` 파일을 저장합니다.

```python
import os

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.datasets import load_wine
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

MODEL_NAME = "BookwayWineClassifier"
mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5055"))
mlflow.set_experiment("bookway-wine-basics")
wine = load_wine(as_frame=True)
X_train, X_test, y_train, y_test = train_test_split(
    wine.data, wine.target, test_size=0.25, random_state=42, stratify=wine.target
)
model = LogisticRegression(max_iter=10000, random_state=7)
model.fit(X_train, y_train)
example = X_test.head(2)
signature = infer_signature(example, model.predict(example))

with mlflow.start_run(run_name="register-wine-classifier") as run:
    model_info = mlflow.sklearn.log_model(
        model,
        name="wine_classifier",
        signature=signature,
        input_example=example,
    )
    version = mlflow.register_model(model_info.model_uri, MODEL_NAME)
    client = MlflowClient()
    client.set_registered_model_alias(MODEL_NAME, "champion", version.version)
    alias_model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@champion")
    fixed_version_model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}/{version.version}")
    same_predictions = (alias_model.predict(example) == fixed_version_model.predict(example)).all()
    print(f"run_id={run.info.run_id}")
    print(f"registered_model={version.name}")
    print(f"version={version.version}")
    print("alias=champion")
    print(f"alias_and_version_predictions_match={bool(same_predictions)}")
```

```bash
.venv/bin/python register_model.py
```

관찰한 결과는 모델 버전 `1`과 Alias `champion`이 같은 모델을 가리키며, 양쪽의 예측이 일치한다는 것입니다.

```text
registered_model=BookwayWineClassifier
version=1
alias=champion
alias_and_version_predictions_match=True
```

Alias는 버전을 가리키는 변경 가능한 이름입니다. `models:/BookwayWineClassifier@champion`은 별칭 이동에 따라 달라지지만 `models:/BookwayWineClassifier/1`은 고정 버전입니다. 배포에는 실제 버전도 기록합니다.

Registry Stages는 deprecated 흐름이며 새 설계에서는 Alias를 사용합니다. 배포 승인과 별칭 변경 이력을 버전 기록에 연결합니다.

## 8단계. Registry 모델을 HTTP로 서빙하기

모델 서버는 `/invocations` 입력을 예측으로 바꿉니다. Tracking Server는 계속 실행하고, 로컬 venv에서 `champion` 모델을 5056 포트에 제공합니다.

```bash
source .venv/bin/activate
mlflow models serve -m 'models:/BookwayWineClassifier@champion' --env-manager local --host 127.0.0.1 -p 5056
```

다른 터미널에서 저장할 `serve-request.json`에는 모델 서명과 일치하는 13개 열과 Wine 데이터 한 행을 넣습니다.

```json
{"dataframe_split":{"columns":["alcohol","malic_acid","ash","alcalinity_of_ash","magnesium","total_phenols","flavanoids","nonflavanoid_phenols","proanthocyanins","color_intensity","hue","od280/od315_of_diluted_wines","proline"],"data":[[14.23,1.71,2.43,15.6,127.0,2.8,3.06,0.28,2.29,5.64,1.04,3.92,1065.0]]}}
```

요청 파일을 `serve-request.json`으로 저장한 뒤 실제 HTTP 요청을 보냅니다.

```bash
curl --fail-with-body --silent --show-error -X POST http://127.0.0.1:5056/invocations -H 'Content-Type: application/json' --data-binary @serve-request.json
```

실행 결과는 다음과 같습니다.

```json
{"predictions": [0]}
```

응답의 `0`은 Wine 클래스 인덱스입니다. 실제 서비스에서는 업무용 레이블과 응답 스키마를 정의합니다. `--env-manager local`은 현재 venv의 의존성을 그대로 사용합니다.

## 9단계. 중첩 Run으로 하이퍼파라미터 비교하기

중첩 Run은 부모 아래에 후보 Run을 묶습니다. 예제는 `min_samples_leaf` 세 값을 비교하고 각 자식 Run에 파라미터와 정확도를 기록합니다.

`nested_runs.py` 파일을 저장합니다.

```python
import os

import mlflow
from sklearn.datasets import load_wine
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5055"))
mlflow.set_experiment("bookway-wine-basics")
wine = load_wine(as_frame=True)
X_train, X_test, y_train, y_test = train_test_split(
    wine.data, wine.target, test_size=0.25, random_state=42, stratify=wine.target
)

with mlflow.start_run(run_name="random-forest-search") as parent:
    mlflow.set_tag("project", "bookway")
    for leaf_size in (1, 3, 5):
        with mlflow.start_run(run_name=f"min-leaf-{leaf_size}", nested=True):
            model = RandomForestClassifier(
                n_estimators=100, min_samples_leaf=leaf_size, random_state=42
            )
            model.fit(X_train, y_train)
            accuracy = accuracy_score(y_test, model.predict(X_test))
            mlflow.log_params({"n_estimators": 100, "min_samples_leaf": leaf_size})
            mlflow.log_metric("validation_accuracy", accuracy)
            print(f"min_samples_leaf={leaf_size} validation_accuracy={accuracy:.4f}")
    print(f"parent_run_id={parent.info.run_id}")
```

```bash
.venv/bin/python nested_runs.py
```

이번 실행에서 기록된 후보별 결과입니다.

```text
min_samples_leaf=1 validation_accuracy=1.0000
min_samples_leaf=3 validation_accuracy=0.9778
min_samples_leaf=5 validation_accuracy=0.9556
```

검증 결과만으로 가장 높은 후보를 출시하지 않습니다. 별도 테스트와 업무 지표, 출시 기준을 적용합니다. 이 예제는 평가 API 대신 중첩 Run으로 후보를 비교했습니다.

### 팀 환경에서 저장소를 구성하는 방법

앞의 실행 흐름은 단일 머신의 SQLite와 로컬 Artifact 폴더를 사용합니다. 팀 서버는 Backend store를 PostgreSQL로, Artifact store를 S3 또는 MinIO 호환 저장소로 분리하는 구성이 일반적입니다.

`--artifacts-destination`은 서버가 관리하는 Artifact 목적지를 설정합니다. 프록시 접근을 쓰면 서버가 업로드와 다운로드를 중개해 클라이언트에 버킷 자격 증명을 배포하지 않을 수 있습니다. 백업, 접근 제어, TLS, 인증, 보존 정책은 별도로 구성합니다. 이 절은 팀 구성 설명이며 실습은 로컬 저장소를 사용했습니다.

## 10단계. 자주 만나는 문제와 점검 순서

| 증상 | 흔한 원인 | 점검과 대응 |
| --- | --- | --- |
| UI에 실행이 나타나지 않습니다 | 코드가 다른 Tracking URI나 기본 로컬 저장소에 기록했습니다 | 실행 코드의 `MLFLOW_TRACKING_URI`와 UI 주소를 맞춥니다 |
| Artifact를 찾지 못하거나 내려받지 못합니다 | 서버와 클라이언트가 저장소 경로를 공유하지 못하거나 원격 스토리지 권한이 없습니다 | 서버의 Artifact store 경로, 프록시 설정, 버킷 접근 권한과 네트워크를 확인합니다 |
| SQLite 데이터베이스가 예상 위치에 없습니다 | 상대 SQLite URI는 서버 프로세스의 현재 작업 폴더를 기준으로 해석됩니다 | 서버를 같은 프로젝트 폴더에서 시작하고 `mlflow.db`와 `mlartifacts` 위치를 함께 확인합니다 |
| 모델 로드 때 패키지 또는 입력 오류가 납니다 | 학습과 서빙 환경이 다르거나 Signature에 맞지 않는 열을 전달했습니다 | 기록된 의존성과 Signature를 확인하고 입력 열 이름, 순서, 자료형을 맞춥니다 |
| 같은 별칭이 이전과 다른 모델을 불러옵니다 | Alias는 Registry에서 이동할 수 있습니다 | 실제 버전을 배포 기록에 저장하고 재현이 필요할 때는 구체적 버전 URI를 사용합니다 |
| 학습 점수는 높은데 서비스 품질이 낮습니다 | 자동 로깅의 학습 지표를 검증 성능으로 오해했습니다 | 별도 검증 데이터와 도메인 지표를 기록하고 테스트 데이터는 모델 선택에 재사용하지 않습니다 |
| 로컬 서빙이 시작되지 않습니다 | 포트가 이미 사용 중이거나 `local` 환경에 패키지가 없습니다 | 선택한 포트를 확인하고 활성 venv에 모델 실행 의존성이 있는지 살핍니다 |

## 11단계. 공식 참고 링크

아래 공식 페이지는 요청 후 HTTP 응답과 최종 주소를 확인했습니다. 모든 링크가 `200` 응답을 반환했고, 표기한 문서 제목과 일치했습니다.

- [MLflow Tracking Quickstart](https://mlflow.org/docs/latest/ml/getting-started/quickstart/)
- [MLflow Tracking Server](https://mlflow.org/docs/latest/self-hosting/architecture/tracking-server/)
- [ML Model Registry](https://mlflow.org/docs/latest/ml/model-registry/)
- [Model Signatures and Input Examples](https://mlflow.org/docs/latest/ml/model/signatures/)
- [Deploy MLflow Model as a Local Inference Server](https://mlflow.org/docs/latest/ml/deployment/deploy-model-locally/)
- [mlflow.sklearn Python API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.sklearn.html)

## 12단계. 이어 읽기

- [MLflow 로컬 Tracking부터 모델 등록까지 이어지는 실습 묶음](/docs/tech/ops/mlops/labs/)
  - [01. 로컬 Tracking](/docs/tech/ops/mlops/labs/01-local-tracking/)
  - [02. Run 검색과 비교](/docs/tech/ops/mlops/labs/02-query-and-compare/)
  - [03. 모델 형식과 로딩](/docs/tech/ops/mlops/labs/03-model-format-and-loading/)
  - [04. Azure ML Tracking과 Job](/docs/tech/ops/mlops/labs/04-azureml-tracking-and-jobs/)
  - [05. 모델 등록](/docs/tech/ops/mlops/labs/05-model-registration/)
  - [06. 온라인 및 배치 추론](/docs/tech/ops/mlops/labs/06-online-and-batch-inference/)
- [MLflow 운영 설계 가이드](/docs/tech/ops/mlops/mlflow/)
- [Machine Learning Platform Engineering 04장: 실험, 피처, 파이프라인](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/)
- 함께 읽을 기초 가이드: [Feast](/docs/tech/ops/mlops/basics/feast/), [Kubeflow Pipelines](/docs/tech/ops/mlops/basics/kubeflow-pipelines/), [BentoML](/docs/tech/ops/mlops/basics/bentoml/)