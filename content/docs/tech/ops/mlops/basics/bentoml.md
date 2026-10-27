---
title: "BentoML 기초: 서비스 작성부터 모델 저장, 패키징, 컨테이너까지"
description: "BentoML로 API 작성, 모델 저장, 입력 검증, 배치 처리, 빌드와 컨테이너 배포를 익힌다."
date: 2026-10-25T19:30:00+09:00
weight: 40
tags: ["mlops", "bentoml", "serving", "hands-on"]
---

학습 모델은 API에 연결하고 필요한 파일과 라이브러리와 함께 배포한다. BentoML은 Python Service와 Bento 패키지로 이를 구성하는 프레임워크다. 여기서는 Iris 모델을 저장하고 서빙한 뒤 Docker 이미지로 만든다.

## 1단계. BentoML을 주방에 비유해 이해하기

**모델은 레시피**, **Service는 주방과 주문 창구**, **Bento는 포장 상자**에 해당한다. 요청은 API endpoint에서 모델 예측으로 이어지고, 배포 시 서비스 코드, 라이브러리, 모델을 Bento로 묶는다.

| 용어 | 뜻 | 이 글에서의 예 |
| --- | --- | --- |
| Service | API와 초기화 로직을 담는 배포용 Python 서비스다. | `IrisService` |
| API endpoint | `@bentoml.api`로 선언하는 호출 경로다. | `/predict` |
| Model Store, model tag | 모델 저장소와 `이름:버전` 식별자다. | `iris_classifier:20261025` |
| Bento | 서비스 코드, 실행 환경, 참조 모델을 묶은 패키지다. | `iris_service:20261025` |
| bentofile, `bentoml build` | 서비스와 의존성을 설정해 Bento를 빌드한다. | `bentofile.yaml` |
| `containerize` | Bento를 Docker 이미지로 만든다. | `bentoml containerize ...` |
| Runner | BentoML 1.0, 1.1의 실행 단위다. 구판은 `Runner`, `runner.init_local()`을 쓴다. | 현재는 클래스 인스턴스에서 모델을 로드한다. |
| `@bentoml.service` 스타일 | 현재 1.x 서비스 클래스 방식이다. API 메서드는 `@bentoml.api`로 표시한다. | 이 글의 `IrisService` |
| BentoCloud | Bento 배포와 운영을 관리하는 플랫폼이며 로컬 학습에는 불필요하다. | 이 글에서는 사용하지 않는다. |

Model Store에서 관리한 모델을 Bento로 패키징하면 실행 가능한 서비스가 된다.

```mermaid
accTitle: BentoML 요청 처리와 배포 흐름
accDescr: 클라이언트 요청이 Service API에 도착하면 서비스가 모델을 호출한다. Model Store의 모델을 Bento로 패키징해 컨테이너로 배포한다.
flowchart LR
    Request["클라이언트 요청"] --> Service["Service API"]
    Service --> Model["Model Store 모델"]
    Model --> Bento["Bento 패키지"]
    Bento --> Container["Docker 컨테이너"]
```

## 2단계. 고정 버전을 설치하고 Hello API 실행하기

버전 비교를 위해 BentoML과 모델 라이브러리를 고정한다. 2026년 10월 25일 PyPI에서 확인한 최신 BentoML 1.x 안정판은 `1.4.40`이며 Python 3.12에서 설치한다.

```bash
uv venv .venv --python 3.12
source .venv/bin/activate
export BENTOML_HOME="$PWD/bentoml-home"
uv pip install bentoml==1.4.40 scikit-learn==1.9.1 mlflow==3.17.2
```

Windows 사용자는 네이티브 Windows 대신 WSL2 Ubuntu에서 같은 Bash 명령을 실행하면 된다. `BENTOML_HOME`을 작업 폴더로 지정해 기본 홈에는 Model Store를 만들지 않는다.

`hello_service.py`를 만든다. `@bentoml.service`가 서비스를 선언하고 `@bentoml.api`가 endpoint가 될 메서드를 표시한다. 단순 타입 힌트도 요청의 필드와 응답 타입을 설명한다.

```python
# hello_service.py
import bentoml


@bentoml.service
class HelloService:
    @bentoml.api
    def greet(self, name: str) -> dict[str, str]:
        return {"message": f"안녕하세요, {name}!"}
```

서비스를 로컬 주소에 바인딩한다. 이 글에서 실행한 포트는 `3055`이다.

```bash
bentoml serve hello_service:HelloService --host 127.0.0.1 --port 3055
```

다른 터미널에서 JSON 요청을 보내고 응답을 확인한다.

```bash
curl -i -X POST http://127.0.0.1:3055/greet \
  -H 'Content-Type: application/json' \
  -d '{"name":"BentoML"}'
```

HTTP `200 OK`와 `{"message": "\uc548\ub155\ud558\uc138\uc694, BentoML!"}`를 받았다. BentoML 1.4.40의 Swagger UI는 `/`에 있고 `/docs`는 HTTP 404였다. 기본 경로를 가정하지 말고 서비스 문서를 확인한다.

## 3단계. Iris 모델을 학습하고 Model Store에 저장하기

`bentoml.sklearn.save_model`로 모델을 저장하고 날짜형 태그로 버전을 고정한다. `train_iris.py`를 작성한다.

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

출력은 `saved=iris_classifier:20261025`다. 목록에서 태그, 모듈, 크기를 확인한다.

```bash
python train_iris.py
bentoml models list
```

실행 당시 목록에는 `iris_classifier:20261025`, 모듈 `bentoml.sklearn`, 크기 `184.27 KiB`가 표시됐다. `latest` 대신 고정 태그를 사용해 버전 혼동을 줄인다.

`iris_service.py`는 시작 시 모델을 한 번 로드한다. `BentoModel`이 태그를 선언하고 `__init__`이 scikit-learn 모델을 읽는다. Pydantic은 네 입력값의 양수 여부와 범위를 검사한다.

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

서비스를 시작한다.

```bash
bentoml serve iris_service:IrisService --host 127.0.0.1 --port 3055
```

요청 본문에는 `request` 객체 안에 Pydantic 필드를 넣는다. 유효한 요청의 응답은 HTTP `200 OK`와 다음 JSON이었다.

```bash
curl -i -X POST http://127.0.0.1:3055/predict \
  -H 'Content-Type: application/json' \
  -d '{"request":{"sepal_length":5.1,"sepal_width":3.5,"petal_length":1.4,"petal_width":0.2}}'
```

```json
{"class_id":0,"species":"setosa","probabilities":[1.0,0.0,0.0]}
```

## 4단계. 입력과 출력 계약, 잘못된 요청 확인하기

입력 모델은 필드명, 타입, 범위를 선언하고 요청 시 검증한다. `IrisResponse`는 응답 필드를 고정한다. 필수 `request` 누락과 범위 위반은 모두 HTTP `400 Bad Request`를 반환했다.

다음 명령은 음수 꽃받침 길이를 보내므로 Pydantic 검증에서 거부된다.

```bash
curl -i -X POST http://127.0.0.1:3055/predict \
  -H 'Content-Type: application/json' \
  -d '{"request":{"sepal_length":-1,"sepal_width":3.5,"petal_length":1.4,"petal_width":0.2}}'
```

오류는 `greater_than`, `request.sepal_length`, `Input should be greater than 0`, HTTP `400`을 반환했다. 타입, 필드 누락, 범위를 검증해 잘못된 입력을 모델에서 차단한다.

API 계약은 Pydantic 외에 NumPy 배열이나 Pandas DataFrame 등 BentoML descriptor로 정의할 수 있다. 스키마 검증은 업무상 의미까지 보장하지 않는다.

## 5단계. 자원과 timeout, adaptive batching 설정하기

앞의 서비스 데코레이터에는 `resources={"cpu": "1"}`, `traffic={"timeout": 30}`, `workers=1`을 지정했다. CPU 자원 요청, 요청 처리 timeout, 서비스 worker 수를 코드로 선언한 예이다. 실제 운영에서는 모델의 메모리 사용량과 처리량을 측정해 worker 수와 자원 한도를 정해야 한다.

짧은 요청을 묶어 모델 함수에 전달할 수 있는 API라면 `batchable=True`를 설정한다. 아래 `batch_service.py`는 각 요청의 숫자 배열에 2를 곱한다. `print`는 실제로 한 번에 합쳐진 입력 길이를 확인하기 위한 실험 계측이다.

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

요청 네 개를 동시에 보내는 `batch_requests.py`이다. 네 요청이 각각 두 원소를 가지므로 서비스가 묶으면 총 여덟 원소가 된다.

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

실제 응답은 `[[2.0, 4.0], [6.0, 8.0], [10.0, 12.0], [14.0, 16.0]]`이었고 서비스 로그에 `combined batch shape=(8,)`가 찍혔다. 네 개 요청이 합쳐진 처리를 확인한 결과이다. 배치는 각 호출 결과의 순서와 개별 응답을 유지하면서 내부 실행을 묶을 수 있다. 단, 호출량이 적으면 대기 시간이 늘 수 있으므로 `max_latency_ms`는 지연 시간 요구와 함께 조정한다.

## 6단계. bentofile.yaml로 Bento 패키지 빌드하기

이 버전에서는 간단한 프로젝트의 빌드 설정 파일로 `bentofile.yaml`을 사용했다. `service`에는 서비스 import 경로를, `python.packages`에는 배포 환경에 필요한 고정 버전을 적다.

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

서비스 파일이 있는 일반 디렉터리에서 빌드한다. 숨김 디렉터리에서는 빌더가 접근을 거부해 일반 이름의 디렉터리로 복사했다. 원인은 패키지 설정이 아닌 숨김 경로 제한이다.

```bash
bentoml build --version 20261025
bentoml list
```

빌드는 `iris_service:20261025`를 만들었다. Bento 크기는 `23.99 KiB`, 모델은 `184.27 KiB`였으며 이후 명령에서 같은 태그를 쓴다.

빌더가 `uv`나 `pip`를 찾지 못하면 다음 명령으로 설치한다. 이 실험 환경에는 `pip`가 없어 추가했다.

```bash
uv pip install --python .venv/bin/python pip uv
```

패키지에는 `README.md`, `apis/openapi.yaml`, `apis/schema.json`, `bento.yaml`, Dockerfile, entrypoint, Python requirements, 서비스 코드와 bentofile이 포함된다. 모델 파일은 별도 크기로 표시된다.

## 7단계. Docker 이미지로 변환하고 요청 보내기

`bentoml containerize`는 로컬 Bento를 Docker 이미지로 만든다. WSL에서 Docker Desktop에 연결되는지 `docker version`으로 확인한 뒤 이미지 빌드를 실행했다.

```bash
bentoml containerize iris_service:20261025
```

이미지 `iris_service:20261025`의 컨테이너 포트 3000을 호스트 `127.0.0.1:3057`에 연결한다.

```bash
docker run --rm -p 127.0.0.1:3057:3000 iris_service:20261025
```

다른 터미널에서 같은 요청을 보낸다.

```bash
curl -i -X POST http://127.0.0.1:3057/predict \
  -H 'Content-Type: application/json' \
  -d '{"request":{"sepal_length":5.1,"sepal_width":3.5,"petal_length":1.4,"petal_width":0.2}}'
```

컨테이너도 HTTP `200 OK`와 같은 JSON을 반환했다. `--rm`은 종료 시 컨테이너를 지우며, 요청 확인 후 이미지도 제거했다.

## 8단계. MLflow Registry 모델을 BentoML로 가져오기

`bentoml.mlflow.import_model`로 등록 모델을 Model Store에 가져온다. 여기서는 scratch 폴더의 SQLite tracking과registry에 Iris RandomForest를 등록하고 `mlflow_import.py`를 실행한다.

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

`skops_trusted_types`에는 직접 만든 RandomForest의 트리 타입만 지정한다. MLflow는 처음에 이를 untrusted로 거부했다. 출처를 검토하지 않은 모델의 타입 전체를 신뢰하지 않는다.

```bash
python mlflow_import.py
```

첫 실행은 `registered_version=1`, `imported=iris_from_mlflow:20261025`를 출력했다. 재실행은 새 Registry 버전을 만들지만 BentoML에는 고정된 버전 1을 가져온다. 예측도 확인했다.

```python
# verify_mlflow_load.py
import bentoml
model = bentoml.mlflow.load_model("iris_from_mlflow:20261025")
print(model.predict([[5.1, 3.5, 1.4, 0.2]]).tolist())
```

```bash
python verify_mlflow_load.py
```

출력은 `[0]`이었다. Registry 버전을 Model Store 태그로 고정하면 배포와 추적을 분리할 수 있다. URI 접근이 안 되면 초기화 시 `mlflow.pyfunc.load_model(...)`로 읽되 Bento 환경에 MLflow와 아티팩트 접근을 설정한다.

## 9단계. 운영 요청 경로와 KFP, Feast 연결하기

실시간 온라인 추론은 클라이언트 요청이 API gateway나 ingress를 지나 BentoML Service에 도착하고, 서비스가 시작 시 불러 둔 모델로 예측해 응답하는 경로이다. Kubeflow Pipelines(KFP)는 학습과 데이터 준비, 정기적인 대량 배치 추론 같은 파이프라인 작업을 구성하는 데 적합하다. 온라인 서빙과 배치 추론은 같은 모델을 사용하더라도 실행 트리거, 처리량, 지연 목표가 다르다.

Feast 온라인 서빙은 요청의 entity key로 online store에서 feature를 조회해 모델에 전달한다. 아래는 실행에 포함하지 않은 개념 예시다.

```python
# Feast 저장소와 feature view가 준비된 프로젝트에서 사용하는 개념 스케치
from feast import FeatureStore

store = FeatureStore(repo_path="feature_repo")
features = store.get_online_features(
    features=["iris_features:sepal_length", "iris_features:petal_length"],
    entity_rows=[{"flower_id": 1}],
).to_dict()
```

실제 저장소의 feature view, entity key, 결측 처리, 학습, 추론 feature 일관성을 확인한다.

검증된 Registry 버전이나 BentoML tag를 고정하고 서비스 초기화 때 모델을 읽어 재사용한다. `/readyz`는 준비 상태, `/livez`는 생존, `/metrics`는 Prometheus 데이터를 제공한다. IrisService에서 모두 HTTP `200 OK`였지만 `/metrics` 본문은 비어 있었다. 상태 코드만으로 샘플 수집을 단정하지 말고 본문과 scrape 설정을 확인한다.

## 10단계. 운영에서 자주 만나는 주의점

| 주의점 | 문제가 되는 이유 | 권장하는 방식 |
| --- | --- | --- |
| 요청마다 모델을 로드 | 파일 I/O와 초기화가 반복돼 지연과 메모리 비용이 커진다. | 서비스 생성 시 모델을 불러와 인스턴스에서 재사용한다. |
| `latest` 태그만 사용 | 같은 서비스 코드가 다른 모델 아티팩트를 가져올 수 있다. | 검증한 model tag 또는 MLflow Registry 버전을 설정과 함께 고정한다. |
| Bento에 비밀값 저장 | 이미지와 패키지에 자격 증명이 남으면 재배포 과정에서 노출될 수 있다. | BentoCloud secret 관리나 실행 환경의 secret manager, 환경변수 주입을 사용한다. |
| Windows 네이티브 실행을 가정 | 일부 패키지, Docker 연동, Linux 배포 환경의 차이가 로컬에서 드러나지 않을 수 있다. | Linux/macOS 또는 WSL2에서 실행해 대상 컨테이너 환경에 맞춘다. |
| 동기식 작업을 비동기 코드 안에서 실행 | 이벤트 루프를 막으면 다른 요청의 응답 지연이 늘어날 수 있다. | I/O에 맞는 async 클라이언트를 쓰거나 별도 worker, 실행 풀로 분리한다. |
| 예전 책의 Runner 예제를 현재 코드에 그대로 복사 | BentoML 1.0, 1.1의 Runner 중심 예제와 현재 `@bentoml.service` API는 사용법이 다르다. | 현재 문서와 설치 버전에 맞춰 서비스 클래스에서 모델을 초기화한다. |
| 컨테이너 포트와 호스트 주소 혼동 | 호스트의 `127.0.0.1`과 컨테이너 내부 포트는 별도 네트워크 공간이다. | `-p 127.0.0.1:호스트포트:3000`으로 명시적으로 연결한다. |

## 11단계. 참고 링크

아래 주소는 BentoML 공식 문서이다. 2026년 10월 25일 확인 시 모두 HTTP 200으로 응답했고, 리다이렉트 후 URL도 표에 적은 주소와 같았다.

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
