---
title: "BentoML 기초: 서비스 작성부터 모델 저장, 패키징, 컨테이너까지"
description: "BentoML로 간단한 API부터 모델 저장, 입력 검증, 배치 처리, 빌드와 컨테이너 배포까지 단계별로 익힙니다."
date: 2026-10-25T19:30:00+09:00
weight: 40
tags: ["mlops", "bentoml", "serving", "hands-on"]
---

모델을 학습했다고 예측 API가 저절로 생기지는 않습니다. 모델을 웹 요청과 연결하고, 필요한 파일과 라이브러리를 함께 묶어 배포 가능한 형태로 만들어야 합니다. BentoML은 이 과정을 Python 서비스와 Bento 패키지로 정리해 주는 모델 서빙 프레임워크입니다. 이 글에서는 Iris 분류기를 직접 저장하고 서비스로 제공한 뒤, 패키지와 Docker 이미지로 만드는 순서를 살펴봅니다.

## 1단계. BentoML을 주방에 비유해 이해하기

먼저 식당을 떠올려 보겠습니다. **레시피가 모델**, **주방과 주문 창구가 Service**, **포장 상자가 Bento**입니다. 손님이 주문을 보내면 창구가 내용을 확인하고 주방의 레시피로 음식을 만듭니다. BentoML에서는 클라이언트 요청이 API endpoint에 도착하고, Service가 모델을 호출해 예측을 반환합니다. 배포할 때에는 서비스 코드, 필요한 라이브러리, 모델을 Bento로 패키징합니다.

| 용어 | 뜻 | 이 글에서의 예 |
| --- | --- | --- |
| Service | 배포 가능한 Python 서비스 단위입니다. 서비스 클래스가 API와 초기화 로직을 가집니다. | `IrisService` |
| API endpoint | 서비스 클래스 안에서 `@bentoml.api`로 선언하는 호출 경로입니다. | `/predict` |
| Model Store, model tag | BentoML이 관리하는 모델 아티팩트 저장소와 `이름:버전` 식별자입니다. | `iris_classifier:20261025` |
| Bento | 서비스 코드와 실행 환경, 참조 모델을 묶은 배포 패키지입니다. | `iris_service:20261025` |
| bentofile, `bentoml build` | 패키지에 포함할 서비스와 의존성을 설정하고 Bento를 빌드합니다. | `bentofile.yaml` |
| `containerize` | Bento를 Docker 이미지로 변환합니다. | `bentoml containerize ...` |
| Runner | BentoML 1.0, 1.1 시기의 처리 실행 단위입니다. 예전 책에서는 `Runner`와 `runner.init_local()`을 볼 수 있습니다. | 현재 서비스 예제에서는 클래스 인스턴스에서 모델을 로드합니다. |
| `@bentoml.service` 스타일 | 현재 1.x 문서의 서비스 클래스 선언 방식입니다. API 메서드는 `@bentoml.api`로 표시합니다. | 이 글의 `IrisService` |
| BentoCloud | Bento 배포와 운영을 관리하는 선택형 관리형 플랫폼입니다. 로컬 학습에는 필요하지 않습니다. | 이 글에서는 사용하지 않습니다. |

현재 API의 요청과 패키징 흐름을 간단히 그리면 다음과 같습니다. 모델은 개발 중 Model Store에서 관리하고, 빌드된 Bento는 실행 가능한 서비스 단위가 됩니다.

```mermaid
accTitle: BentoML 요청 처리와 배포 흐름
accDescr: 클라이언트 요청이 Service API에 도착하고 서비스가 모델을 사용합니다. Model Store의 모델을 Bento로 패키징한 뒤 컨테이너로 배포합니다.
flowchart LR
    Request["클라이언트 요청"] --> Service["Service API"]
    Service --> Model["Model Store 모델"]
    Model --> Bento["Bento 패키지"]
    Bento --> Container["Docker 컨테이너"]
```

## 2단계. 고정 버전을 설치하고 Hello API 실행하기

실행 결과를 비교할 수 있도록 BentoML과 모델 라이브러리를 특정 버전으로 고정합니다. 2026년 10월 25일 PyPI에서 확인한 BentoML 최신 1.x 안정 버전은 `1.4.40`이었습니다. Python 3.12 환경에서 다음 패키지 버전을 설치했습니다.

```bash
uv venv .venv --python 3.12
source .venv/bin/activate
export BENTOML_HOME="$PWD/bentoml-home"
uv pip install bentoml==1.4.40 scikit-learn==1.9.1 mlflow==3.17.2
```

Windows 사용자는 네이티브 Windows 대신 WSL2 Ubuntu에서 같은 Bash 명령을 실행하면 됩니다. `BENTOML_HOME`을 작업 폴더 안으로 지정하면 기본 홈 디렉터리에 Model Store를 만들지 않습니다.

이제 `hello_service.py`라는 파일을 만듭니다. `@bentoml.service`가 서비스를 선언하고 `@bentoml.api`가 endpoint가 될 메서드를 표시합니다. 단순 타입 힌트도 요청의 필드와 응답 타입을 설명합니다.

```python
# hello_service.py
import bentoml


@bentoml.service
class HelloService:
    @bentoml.api
    def greet(self, name: str) -> dict[str, str]:
        return {"message": f"안녕하세요, {name}!"}
```

서비스를 로컬 주소에 바인딩합니다. 이 글에서 실행한 포트는 `3055`입니다.

```bash
bentoml serve hello_service:HelloService --host 127.0.0.1 --port 3055
```

다른 터미널에서 JSON 요청을 보내면 다음 응답을 받습니다.

```bash
curl -i -X POST http://127.0.0.1:3055/greet \
  -H 'Content-Type: application/json' \
  -d '{"name":"BentoML"}'
```

실제 응답은 HTTP `200 OK`와 `{"message": "\uc548\ub155\ud558\uc138\uc694, BentoML!"}`였습니다. BentoML 1.4.40에서는 Swagger UI가 서버 루트 `/`에서 제공되고, 이 실행에서 `/`는 HTTP 200, `/docs`는 HTTP 404였습니다. 다른 프레임워크의 기본 경로를 그대로 가정하지 말고 루트의 서비스 문서를 확인합니다.

## 3단계. Iris 모델을 학습하고 Model Store에 저장하기

BentoML의 scikit-learn 통합 API인 `bentoml.sklearn.save_model`로 모델을 저장합니다. 태그에 날짜형 버전을 지정해 예제에서 같은 모델을 불러오게 했습니다. `train_iris.py`를 작성합니다.

```python
# train_iris.py
import bentoml
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier

X, y = load_iris(return_X_y=True)
model = RandomForestClassifier(n_estimators=100, random_state=7)
model.fit(X, y)
saved = bentoml.sklearn.save_model("iris_classifier:20261025", model)
print(f"saved={saved.tag}")
```

실행하면 `saved=iris_classifier:20261025`가 출력됩니다. 목록에서도 태그와 모듈, 저장 크기를 확인할 수 있습니다.

```bash
python train_iris.py
bentoml models list
```

실행 당시 목록에는 `iris_classifier:20261025`, 모듈 `bentoml.sklearn`, 크기 `184.27 KiB`가 표시됐습니다. `latest` 대신 고정 태그를 코드에 넣으면 실수로 다른 모델 버전을 읽을 가능성이 줄어듭니다.

서비스가 시작될 때 모델을 한 번 불러오도록 `iris_service.py`를 작성합니다. `BentoModel`은 필요한 모델 태그를 선언하고, `__init__`에서 scikit-learn 모델을 로드합니다. Pydantic 입력 모델은 네 값이 모두 양수이고 합리적인 범위 안에 있는지 검사합니다.

```python
# iris_service.py
import bentoml
import numpy as np
from bentoml.models import BentoModel
from pydantic import BaseModel, Field


class IrisRequest(BaseModel):
    sepal_length: float = Field(gt=0, le=10)
    sepal_width: float = Field(gt=0, le=10)
    petal_length: float = Field(gt=0, le=10)
    petal_width: float = Field(gt=0, le=10)


class IrisResponse(BaseModel):
    class_id: int
    species: str
    probabilities: list[float]


@bentoml.service(resources={"cpu": "1"}, traffic={"timeout": 30}, workers=1)
class IrisService:
    model_ref = BentoModel("iris_classifier:20261025")

    def __init__(self) -> None:
        self.model = bentoml.sklearn.load_model(self.model_ref.tag)
        self.species = ["setosa", "versicolor", "virginica"]

    @bentoml.api
    def predict(self, request: IrisRequest) -> IrisResponse:
        row = np.array([[request.sepal_length, request.sepal_width,
                         request.petal_length, request.petal_width]])
        class_id = int(self.model.predict(row)[0])
        probabilities = self.model.predict_proba(row)[0].tolist()
        return IrisResponse(
            class_id=class_id,
            species=self.species[class_id],
            probabilities=probabilities,
        )
```

서비스를 시작합니다.

```bash
bentoml serve iris_service:IrisService --host 127.0.0.1 --port 3055
```

요청 본문에는 `request` 객체 안에 Pydantic 필드를 넣습니다. 유효한 요청의 응답은 HTTP `200 OK`와 다음 JSON이었습니다.

```bash
curl -i -X POST http://127.0.0.1:3055/predict \
  -H 'Content-Type: application/json' \
  -d '{"request":{"sepal_length":5.1,"sepal_width":3.5,"petal_length":1.4,"petal_width":0.2}}'
```

```json
{"class_id":0,"species":"setosa","probabilities":[1.0,0.0,0.0]}
```

## 4단계. 입력과 출력 계약, 잘못된 요청 확인하기

입력 모델은 필드 이름과 자료형, 허용 범위를 문서화하고 실행 시 검증합니다. 응답도 `IrisResponse`로 명시했으므로 호출자는 어떤 필드가 돌아오는지 알 수 있습니다. 필수 `request` 객체가 빠진 요청과 필드 범위를 어긴 요청은 모두 이 실험에서 HTTP `400 Bad Request`였습니다.

다음 명령은 음수 꽃받침 길이를 보내므로 Pydantic 검증에서 거부됩니다.

```bash
curl -i -X POST http://127.0.0.1:3055/predict \
  -H 'Content-Type: application/json' \
  -d '{"request":{"sepal_length":-1,"sepal_width":3.5,"petal_length":1.4,"petal_width":0.2}}'
```

관측된 오류의 핵심은 `"type":"greater_than"`, 위치 `request.sepal_length`, 메시지 `Input should be greater than 0`이며 상태 코드는 `400`입니다. 숫자 형식이 아닌 값, 누락 필드, 범위 제한을 검증할 수 있으므로 잘못된 입력이 모델까지 전달되지 않게 경계를 정합니다.

실제 API 계약은 Pydantic 외에도 NumPy 배열, Pandas 데이터 프레임 같은 BentoML 입출력 descriptor로 표현할 수 있습니다. 다만 계약을 정할 때는 스키마 검증만으로 입력의 업무상 의미까지 보장하지 않는다는 점을 구분합니다.

## 5단계. 자원과 timeout, adaptive batching 설정하기

앞의 서비스 데코레이터에는 `resources={"cpu": "1"}`, `traffic={"timeout": 30}`, `workers=1`을 지정했습니다. CPU 자원 요청, 요청 처리 timeout, 서비스 worker 수를 코드로 선언한 예입니다. 실제 운영에서는 모델의 메모리 사용량과 처리량을 측정해 worker 수와 자원 한도를 정해야 합니다.

짧은 요청을 묶어 모델 함수에 전달할 수 있는 API라면 `batchable=True`를 설정합니다. 아래 `batch_service.py`는 각 요청의 숫자 배열에 2를 곱합니다. `print`는 실제로 한 번에 합쳐진 입력 길이를 확인하기 위한 실험 계측입니다.

```python
# batch_service.py
import bentoml
import numpy as np


@bentoml.service
class BatchService:
    @bentoml.api(batchable=True, max_batch_size=8, max_latency_ms=100)
    def double(self, values: np.ndarray) -> np.ndarray:
        print(f"combined batch shape={values.shape}", flush=True)
        return values * 2
```

```bash
bentoml serve batch_service:BatchService --host 127.0.0.1 --port 3056
```

요청 네 개를 동시에 보내는 `batch_requests.py`입니다. 네 요청이 각각 두 원소를 가지므로 서비스가 묶으면 총 여덟 원소가 됩니다.

```python
# batch_requests.py
from concurrent.futures import ThreadPoolExecutor
import requests


def send(value):
    response = requests.post(
        "http://127.0.0.1:3056/double",
        json={"values": [value, value + 1]},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


with ThreadPoolExecutor(max_workers=4) as pool:
    print(list(pool.map(send, [1.0, 3.0, 5.0, 7.0])))
```

```bash
python batch_requests.py
```

실제 응답은 `[[2.0, 4.0], [6.0, 8.0], [10.0, 12.0], [14.0, 16.0]]`이었고 서비스 로그에 `combined batch shape=(8,)`가 찍혔습니다. 네 개 요청이 합쳐진 처리를 확인한 결과입니다. 배치는 각 호출 결과의 순서와 개별 응답을 유지하면서 내부 실행을 묶을 수 있습니다. 단, 호출량이 적으면 대기 시간이 늘 수 있으므로 `max_latency_ms`는 지연 시간 요구와 함께 조정합니다.

## 6단계. bentofile.yaml로 Bento 패키지 빌드하기

이 버전에서는 간단한 프로젝트의 빌드 설정 파일로 `bentofile.yaml`을 사용했습니다. `service`에는 서비스 import 경로를, `python.packages`에는 배포 환경에 필요한 고정 버전을 적습니다.

```yaml
# bentofile.yaml
service: "iris_service:IrisService"
include:
  - "iris_service.py"
python:
  packages:
    - "bentoml==1.4.40"
    - "scikit-learn==1.9.1"
```

해당 파일과 서비스 코드를 가진 디렉터리에서 빌드합니다. 이름이 점으로 시작하는 숨김 디렉터리 안에서 빌드하면 BentoML이 숨김 경로 접근을 거부했습니다. 그래서 파일을 일반 이름의 빌드 디렉터리로 복사해 `bentoml build`를 실행했습니다. 이는 패키지 설정 문제가 아니라 빌더의 숨김 경로 제한이었습니다.

```bash
bentoml build --version 20261025
bentoml list
```

빌드 로그는 `Successfully built Bento(tag="iris_service:20261025")`를 출력했습니다. 목록에는 Bento 크기 `23.99 KiB`, 모델 크기 `184.27 KiB`가 표시됐습니다. 빌드 시점의 Bento 태그를 고정했기 때문에 이어지는 컨테이너 명령에서 같은 태그를 사용할 수 있습니다.

만약 BentoML 빌더가 현재 환경에 `uv`와 `pip`가 없다고 보고한다면 다음 명령으로 빌드 도구를 환경에 추가할 수 있습니다. 이 실험의 가상환경에는 `pip`가 포함되지 않아 이 단계를 추가했습니다.

```bash
uv pip install --python .venv/bin/python pip uv
```

Bento 저장소의 패키지 디렉터리에는 `README.md`, `apis/openapi.yaml`, `apis/schema.json`, `bento.yaml`, `env/docker/Dockerfile`, `env/docker/entrypoint.sh`, `env/python/requirements.in`, `env/python/requirements.txt`, `src/iris_service.py`, `src/bentofile.yaml`이 있었습니다. 모델 파일은 Bento 패키지와 연결되어 모델 크기가 별도로 표시됩니다.

## 7단계. Docker 이미지로 변환하고 요청 보내기

`bentoml containerize`는 로컬 Bento를 Docker 이미지로 만듭니다. WSL에서 Docker Desktop에 연결되는지 `docker version`으로 확인한 뒤 이미지 빌드를 실행했습니다.

```bash
bentoml containerize iris_service:20261025
```

Docker 이미지 목록에서 `iris_service:20261025`를 확인한 뒤 컨테이너 포트 3000을 호스트의 `127.0.0.1:3057`에 연결합니다.

```bash
docker run --rm -p 127.0.0.1:3057:3000 iris_service:20261025
```

다른 터미널에서 로컬과 같은 요청을 보냅니다.

```bash
curl -i -X POST http://127.0.0.1:3057/predict \
  -H 'Content-Type: application/json' \
  -d '{"request":{"sepal_length":5.1,"sepal_width":3.5,"petal_length":1.4,"petal_width":0.2}}'
```

컨테이너에서도 HTTP `200 OK`, `{"class_id":0,"species":"setosa","probabilities":[1.0,0.0,0.0]}`를 확인했습니다. `--rm` 옵션은 컨테이너 종료 시 컨테이너를 자동 제거합니다. 이 실험에서는 요청 확인 후 컨테이너와 생성한 이미지를 제거했습니다.

## 8단계. MLflow Registry 모델을 BentoML로 가져오기

MLflow에 등록된 모델은 `bentoml.mlflow.import_model`로 BentoML Model Store에 가져올 수 있습니다. 이 실험에서는 SQLite tracking, registry를 scratch 폴더에 만들고, 작은 Iris RandomForest를 등록했습니다. 먼저 `mlflow_import.py`를 작성합니다.

```python
# mlflow_import.py
from pathlib import Path
import bentoml
import mlflow
import mlflow.sklearn
from sklearn.datasets import load_iris
from sklearn.ensemble import RandomForestClassifier

root = Path(__file__).resolve().parent
tracking_uri = f"sqlite:///{root / 'mlflow.db'}"
mlflow.set_tracking_uri(tracking_uri)
mlflow.set_registry_uri(tracking_uri)
mlflow.set_experiment("bentoml-import-demo")
X, y = load_iris(return_X_y=True)
model = RandomForestClassifier(n_estimators=20, random_state=7).fit(X, y)
with mlflow.start_run():
    info = mlflow.sklearn.log_model(
        model,
        name="iris-model",
        registered_model_name="iris_registry",
        skops_trusted_types=["sklearn.tree._tree.Tree"],
    )
print(f"registered_version={info.registered_model_version}")
imported = bentoml.mlflow.import_model(
    "iris_from_mlflow:20261025",
    "models:/iris_registry/1",
)
print(f"imported={imported.tag}")
```

`skops_trusted_types`는 이 예제에서 직접 만든 RandomForest 아티팩트의 트리 타입 하나만 신뢰 대상으로 명시합니다. 처음 실행할 때 MLflow는 해당 타입이 untrusted라고 거부했습니다. 출처를 검토하지 않은 모델에 타입 전체를 무조건 신뢰 대상으로 추가해서는 안 됩니다.

```bash
python mlflow_import.py
```

처음 등록한 실행에서는 `registered_version=1`, `imported=iris_from_mlflow:20261025`가 출력됐습니다. 반복 실행한 실험에서도 새 Registry 버전을 만들고, 고정한 버전 1을 BentoML로 가져왔습니다. 가져온 모델의 실제 예측도 확인했습니다.

```python
# verify_mlflow_load.py
import bentoml
model = bentoml.mlflow.load_model("iris_from_mlflow:20261025")
print(model.predict([[5.1, 3.5, 1.4, 0.2]]).tolist())
```

```bash
python verify_mlflow_load.py
```

관측 출력은 `[0]`이었습니다. Registry의 특정 버전을 Model Store 태그로 고정하면 서비스 배포와 실험 추적을 분리하면서도 사용할 아티팩트를 명확히 할 수 있습니다. 등록된 URI를 접근할 수 없는 환경이라면 서비스 초기화 시 `mlflow.pyfunc.load_model(...)`로 직접 읽는 방식도 대안이지만, 그 경우 MLflow 의존성과 아티팩트 접근 경로를 Bento 실행 환경에 함께 설정해야 합니다.

## 9단계. 운영 요청 경로와 KFP, Feast 연결하기

실시간 온라인 추론은 클라이언트 요청이 API gateway나 ingress를 지나 BentoML Service에 도착하고, 서비스가 시작 시 불러 둔 모델로 예측해 응답하는 경로입니다. Kubeflow Pipelines(KFP)는 학습과 데이터 준비, 정기적인 대량 배치 추론 같은 파이프라인 작업을 구성하는 데 적합합니다. 온라인 서빙과 배치 추론은 같은 모델을 사용하더라도 실행 트리거, 처리량, 지연 목표가 다릅니다.

온라인 서빙에서 Feast를 사용한다면 보통 요청에서 entity key를 얻고 Feast online store에서 feature를 조회한 뒤 모델 입력으로 전달합니다. 다음은 Feast 저장소 설정과 실행 환경이 준비되어야 하는 개념 스케치이며, 이 글의 실행 실험에는 포함하지 않았습니다.

```python
# Feast 저장소와 feature view가 준비된 프로젝트에서 사용하는 개념 스케치
from feast import FeatureStore

store = FeatureStore(repo_path="feature_repo")
features = store.get_online_features(
    features=["iris_features:sepal_length", "iris_features:petal_length"],
    entity_rows=[{"flower_id": 1}],
).to_dict()
```

실제 프로젝트에서는 feature view 이름과 entity key, 반환된 값의 결측 처리, 학습 시점과 추론 시점 간 feature 일관성을 자신의 Feast repository에 맞춰 점검해야 합니다.

모델 버전은 학습 파이프라인이 검증한 Registry 버전 또는 BentoML model tag로 고정합니다. 서비스가 각 요청을 처리할 때마다 모델 파일을 다시 읽지 말고, 서비스 초기화 시 불러와 재사용합니다. 배포가 준비되었는지는 `/readyz`, 프로세스의 생존 여부는 `/livez`, Prometheus 형식의 관측 데이터는 `/metrics`에서 확인할 수 있습니다. IrisService 실행 중 세 경로 모두 HTTP `200 OK`였고, 이 실험의 `/metrics` 본문은 길이 0이었습니다. 응답 코드만으로 실제 메트릭 샘플이 채워졌다고 단정하지 말고, 운영 환경에서 본문과 스크레이프 설정까지 확인합니다.

## 10단계. 운영에서 자주 만나는 주의점

| 주의점 | 문제가 되는 이유 | 권장하는 방식 |
| --- | --- | --- |
| 요청마다 모델을 로드 | 파일 I/O와 초기화가 반복되어 지연과 메모리 비용이 커집니다. | 서비스 생성 시 모델을 불러와 인스턴스에서 재사용합니다. |
| `latest` 태그만 사용 | 같은 서비스 코드가 다른 모델 아티팩트를 가져올 수 있습니다. | 검증한 model tag 또는 MLflow Registry 버전을 설정과 함께 고정합니다. |
| Bento에 비밀값 저장 | 이미지와 패키지에 자격 증명이 남으면 재배포 과정에서 노출될 수 있습니다. | BentoCloud secret 관리나 실행 환경의 secret manager, 환경변수 주입을 사용합니다. |
| Windows 네이티브 실행을 가정 | 일부 패키지, Docker 연동, Linux 배포 환경의 차이가 로컬에서 드러나지 않을 수 있습니다. | Linux/macOS 또는 WSL2에서 실행하고 대상 컨테이너 환경과 맞춥니다. |
| 동기식 작업을 비동기 코드 안에서 실행 | 이벤트 루프를 막으면 다른 요청의 응답 지연이 늘어날 수 있습니다. | I/O에 맞는 async 클라이언트를 쓰거나 별도 worker, 실행 풀로 분리합니다. |
| 예전 책의 Runner 예제를 현재 코드에 그대로 복사 | BentoML 1.0, 1.1의 Runner 중심 예제와 현재 `@bentoml.service` API는 사용법이 다릅니다. | 현재 문서와 설치 버전에 맞춰 서비스 클래스에서 모델을 초기화합니다. |
| 컨테이너 포트와 호스트 주소 혼동 | 호스트의 `127.0.0.1`과 컨테이너 내부 포트는 별도 네트워크 공간입니다. | `-p 127.0.0.1:호스트포트:3000`으로 명시적으로 연결합니다. |

## 11단계. 참고 링크

아래 주소는 BentoML 공식 문서입니다. 2026년 10월 25일 확인 시 모두 HTTP 200으로 응답했고, 리다이렉트 후 URL도 표에 적은 주소와 같았습니다.

| 주제 | 공식 문서 |
| --- | --- |
| 소개, Hello world | [Hello world](https://docs.bentoml.com/en/latest/get-started/hello-world.html) |
| Service와 API endpoint | [Create online API Services](https://docs.bentoml.com/en/latest/build-with-bentoml/services.html) |
| 입력, 출력 타입 | [Define input and output types](https://docs.bentoml.com/en/latest/build-with-bentoml/iotypes.html) |
| Model Store, 모델 로드와 관리 | [Load and manage models](https://docs.bentoml.com/en/latest/build-with-bentoml/model-loading-and-management.html) |
| scikit-learn 통합 | [Scikit-Learn framework API](https://docs.bentoml.com/en/latest/reference/bentoml/frameworks/sklearn.html) |
| Adaptive batching | [Adaptive batching](https://docs.bentoml.com/en/latest/get-started/adaptive-batching.html) |
| 서비스 설정과 자원 | [Configurations](https://docs.bentoml.com/en/latest/reference/bentoml/configurations.html) |
| 빌드와 패키징, Docker 배포 | [Packaging for deployment](https://docs.bentoml.com/en/latest/get-started/packaging-for-deployment.html) |
| Bento 빌드 옵션 | [Bento build options](https://docs.bentoml.com/en/latest/reference/bentoml/bento-build-options.html) |
| CLI 명령 | [BentoML CLI](https://docs.bentoml.com/en/latest/reference/bentoml/cli.html) |
| Docker 컨테이너 API | [Container APIs](https://docs.bentoml.com/en/latest/reference/bentoml/container.html) |
| MLflow 연동 | [MLflow example](https://docs.bentoml.com/en/latest/examples/mlflow.html) |
| Metrics, observability | [Metrics](https://docs.bentoml.com/en/latest/build-with-bentoml/observability/metrics.html) |
| 선택형 관리형 배포 | [BentoCloud deployment](https://docs.bentoml.com/en/latest/get-started/cloud-deployment.html) |

## 함께 읽기

- [BentoML Bookway 설계 가이드](/docs/tech/ops/mlops/bentoml/)
- [BentoML 기능 개요](/docs/tech/ops/mlops/labs/bentoml-capabilities/)
- [Serving, monitoring 실습](/docs/tech/ops/mlops/labs/ml-platform-labs-05-serving-monitoring/)
- [MLflow 기초](/docs/tech/ops/mlops/basics/mlflow/)
- [Feast 기초](/docs/tech/ops/mlops/basics/feast/)
- [Kubeflow Pipelines 기초](/docs/tech/ops/mlops/basics/kubeflow-pipelines/)
