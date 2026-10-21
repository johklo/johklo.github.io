---
title: "MLflow와 Azure Machine Learning"
description: "MLflow와 BentoML의 MLOps 역할부터 로컬 실험, AML 연결과 모델 등록 및 추론까지 이어지는 학습 노트"
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 3
tags: ["mlflow", "bentoml", "mlops", "azure-machine-learning"]
aliases: ["/docs/tech/2026-10-21-mlflow-to-azure-machine-learning/"]
sidebar:
  open: false
---

책에서 읽은 MLflow를 직접 실행해 보고, 같은 코드를 Azure Machine Learning에 연결하는 순서로 나눴다. Azure Machine Learning은 아래에서 AML로 줄여 쓴다. 전체 흐름은 이 목차에 두고, 개념과 실습은 주제별 여섯 편으로 구분했다.

모든 편은 같은 Wine 분류 예제를 이어서 사용한다. 서로 다른 프로젝트를 매번 만드는 것이 아니라 하나의 `mlflow-aml-lab` 폴더에 파일과 실행 기록을 추가하는 구조다.

## MLflow와 BentoML의 의미

### MLflow

MLflow는 실험 추적, 모델 평가, 모델 패키징과 버전 관리, 배포 도구를 제공하는 오픈소스 프로젝트다. [공식 ML 문서](https://mlflow.org/docs/latest/ml/)도 이 기능들을 하나의 모델 개발 생애주기로 다룬다.

이 시리즈에서는 어떤 데이터와 설정으로 학습했고 어떤 결과를 얻었는지 남기는 Tracking, 모델을 다시 읽기 위한 모델 형식, 선택한 모델을 관리하는 Registry에 초점을 둔다. 학습 자체는 scikit-learn이 실행하고 MLflow는 그 과정과 결과를 기록한다.

예를 들어 같은 데이터로 규제 설정을 세 번 바꾸면 MLflow에는 세 개의 run이 남는다. 그중 하나의 모델을 선택해 이름과 버전을 부여하면, 나중에 배포한 모델이 어느 실험에서 나왔는지 연결할 근거가 생긴다.

MLflow를 실험 기록 전용 도구로만 이해하지는 않았다. 자체 모델 서빙과 배포 연동 기능도 있다. 다만 MLflow API를 쓴다는 사실만으로 학습용 컴퓨팅이나 운영 인프라까지 자동으로 준비되는 것은 아니다.

### BentoML

BentoML은 학습한 모델을 사용하는 추론 서비스의 코드, 입출력과 실행 환경을 정의하고 배포하는 오픈소스 서빙 프레임워크다. [Service 문서](https://docs.bentoml.com/en/latest/build-with-bentoml/services.html)는 모델 로딩, 전처리와 예측 같은 처리 흐름을 API로 노출하는 단위로 Service를 설명한다.

모델의 `predict()`가 메모리 안의 함수 호출이라면, BentoML Service는 외부 요청을 받아 그 함수를 실행하고 응답을 돌려주는 서비스 구현에 해당한다. 입력 형식, 전처리, 여러 모델의 호출, 시간 제한과 자원 설정 같은 결정을 함께 다룰 수 있다.

Bento는 이런 서비스를 배포하기 위한 패키지다. [패키징 문서](https://docs.bentoml.com/en/latest/get-started/packaging-for-deployment.html)는 서비스 코드, Python 의존성, 모델 관련 파일과 설정을 묶는 형식으로 설명한다. 모델 참조와 패키지 구성을 바탕으로 컨테이너 이미지를 만들 수도 있다.

BentoML과 BentoCloud는 구분한다. BentoML로 서비스를 만들고 컨테이너 환경에서 실행할 수 있으며, BentoCloud는 그 위에서 배포와 컴퓨팅 운영을 제공하는 관리형 플랫폼이다. BentoML을 사용한다는 사실이 반드시 BentoCloud를 사용한다는 뜻은 아니다.

### 두 도구를 구분할 기준

| 관점 | MLflow | BentoML |
| --- | --- | --- |
| 이 학습에서의 중심 질문 | 어떤 조건으로 만든 모델이며 왜 선택했는가 | 선택한 모델을 어떤 서비스로 실행할 것인가 |
| 대표 기록이나 결과물 | run, 메트릭, 모델 패키지와 등록 버전 | Service 코드, Bento와 컨테이너 이미지 |
| 모델을 다루는 방식 | 실험 출처와 모델 버전을 연결 | 서비스에서 사용할 모델을 읽고 배포 구성에 연결 |
| 실행 시 확인할 것 | 기록 대상, 비교 조건, 모델과 환경의 재현성 | 요청 처리, 입출력, 자원과 서비스 동작 |

기능이 완전히 나뉘는 것은 아니다. MLflow에도 서빙 기능이 있고 BentoML에도 모델 저장과 관리 기능이 있다. 이 표는 기능의 존재 여부보다 각각을 어떤 책임으로 사용하는지 구분하기 위한 것이다.

## 전체 MLOps에서의 역할

MLOps는 모델을 학습하고 API로 만드는 두 작업만을 뜻하지 않는다. 업무 목적과 데이터의 정의, 학습과 검증, 출시 판단, 운영 관측과 개선을 반복 가능하게 연결하는 일이다.

```mermaid
flowchart TD
    accTitle: 전체 MLOps에서의 MLflow와 BentoML 역할
    accDescr: 업무 목적과 데이터 준비에서 학습과 평가로 이어지고 MLflow로 실험 및 모델 버전을 관리한다. 선택한 모델은 AML 추론이나 BentoML 서비스 같은 서빙 경로로 연결하며 운영 결과는 데이터와 모델의 재검토에 사용한다.
    A["업무 목적과 평가 기준"] --> B["데이터 준비와 품질 검사"]
    B --> C["학습과 모델 평가"]
    C --> M["MLflow: 실험 기록과 모델 패키지 및 버전 관리"]
    M -->|"이 시리즈의 추론 경로"| E["AML 온라인 또는 배치 추론"]
    M -->|"별도의 서빙 구현을 구성하는 예"| S["BentoML: Service와 Bento"]
    S --> I["컨테이너 실행 환경 또는 BentoCloud"]
    E --> O["운영 관측과 대응"]
    I --> O
    O -->|"데이터와 입력 변화 확인"| B
    O -->|"후보 모델 재검증"| C
```

위 도식은 서빙 경로를 비교한 예시이지 모든 시스템이 두 도구를 함께 사용해야 한다는 뜻은 아니다. 각 단계에서 기록할 정보와 다음 단계에 넘길 계약을 기준으로 역할을 나누었다.

| MLOps 구간 | MLflow를 연결할 부분 | BentoML을 연결할 부분 |
| --- | --- | --- |
| 데이터 준비와 품질 확인 | 사용한 데이터의 정보와 검사 결과를 실행 기록에 연결 | 추론 요청의 입력 검사와 전처리 구현 |
| 학습과 평가 | 설정, 지표, 보고서와 모델을 run에 기록 | 학습 루프보다 학습된 모델의 서비스 구현에 초점 |
| 모델 선택과 관리 | 선택 근거와 모델 버전, 원천 run의 관계 보관 | 서비스가 사용할 모델과 패키지 버전의 관계 관리 |
| 배포와 추론 | 모델의 로딩 계약과 배포 연동 제공 | API 처리와 실행 환경을 서비스 단위로 패키징 |
| 운영과 개선 | 평가와 재학습 결과를 새 실행 및 모델 이력에 연결 | 서빙 동작과 관측 지점을 구성하고 서비스 변경 반영 |

두 도구가 데이터 품질 기준, 출시 승인, 접근 제어, 장애 대응의 책임까지 대신 결정하지는 않는다. 운영 관측에서도 서비스 지연과 오류, 입력 변화, 정답 기반 모델 품질을 구분할 필요가 있다.

## 이 시리즈에서 사용하는 경로

이 시리즈는 MLflow로 기록한 모델을 AML에 등록하고, AML의 온라인 또는 배치 추론으로 소비하는 경로를 다룬다. AML의 MLflow no-code 배포에서는 모델 계약을 읽어 기본 추론 코드와 환경을 구성하므로, 이 경로를 따라가기 위해 BentoML을 추가할 필요는 없다.

서비스의 입출력이나 여러 모델의 호출을 별도 애플리케이션으로 구성하려는 경우에는 BentoML 같은 서빙 프레임워크를 다른 선택지로 검토할 수 있다. [BentoML의 MLflow 연동 예제](https://docs.bentoml.com/en/latest/examples/mlflow.html)는 MLflow 모델을 가져와 BentoML의 모델 저장소와 Service에서 사용하는 흐름을 보여 준다.

이 경우에도 MLflow의 모델 버전과 Bento의 패키지 버전은 다른 식별자다. 어떤 모델을 어떤 서비스 코드와 환경으로 배포했는지 연결해 남겨야 한다. AML에 모델이 등록되었다고 BentoML 서비스까지 자동 생성되거나, BentoML을 사용한다고 AML 인증과 모델 접근이 자동 구성되지는 않는다.

BentoML은 여기서 역할을 비교하는 대상이며 여섯 편의 실행 예제에 추가 설치하지 않는다. MLflow와 AML을 먼저 익히고, 별도 서빙 구현이 필요한지 판단할 때 이어서 볼 범위로 두었다.

## 학습 순서

{{< section-list >}}

| 순서 | 준비 조건 | 남길 결과 |
| --- | --- | --- |
| 01 | Python 3.11과 로컬 작업 폴더 | 세 번의 학습 run과 보고서 및 모델 |
| 02 | 01편의 실행 기록 | 비교 결과와 `selected-run.json` |
| 03 | 02편에서 선택한 run | 모델 계약과 재로딩 및 입력 검사 결과 |
| 04 | 01~03편의 코드와 AML workspace | AML에 남은 로컬 학습 기록과 원격 Job |
| 05 | 04편의 AML 기록과 선택 파일 | 모델 이름과 구체 버전 |
| 06 | 등록한 모델과 배포를 검토할 환경 | 추론 요청 파일과 배포 및 전환의 확인 기준 |

## 전체 흐름: 로컬 학습 결과를 AML 모델로 등록하기

이 예제에서 MLflow는 로컬 Python 코드가 호출하는 라이브러리다. 별도의 로컬 MLflow 서버에 모델을 보낸 뒤 그 서버가 AML로 옮기는 구조가 아니다. `azureml-mlflow` 플러그인을 설치하고 기록 대상을 AML workspace로 지정하면, 같은 Python 코드의 MLflow 호출이 AML에 실행 정보와 모델을 남긴다.

학습, 실행 기록, 모델 등록을 나누어 보니 흐름을 이해하기 쉬웠다. `model.fit()`은 모델을 학습하고, `log_model()`은 학습한 모델을 특정 run의 결과물로 기록하며, `register_model()`은 그 결과물을 모델 이름 아래의 버전으로 등록한다. 모델을 학습했다는 사실만으로 뒤의 두 작업까지 수행되지는 않는다.

### 로컬 Python과 AML 사이의 호출 순서

아래는 04편의 AML 연결과 05편의 모델 등록을 기준으로 그린 흐름이다. 학습과 비교 코드는 로컬에서 실행하고, 기록과 등록은 같은 AML workspace를 대상으로 한다. SDK와 플러그인도 로컬 Python 프로세스 안에서 동작하는 라이브러리이며, 그림에서 나눈 칸은 별도 서버를 뜻하지 않는다.

```mermaid
sequenceDiagram
    accTitle: 로컬 학습부터 AML 모델 버전 등록까지
    accDescr: 로컬 Python이 MLflow SDK와 Azure 플러그인으로 AML에 run을 만들고 학습 결과를 기록한다. 기록된 모델 중 하나를 선택한 뒤 같은 workspace에 이름과 버전으로 등록한다.
    participant P as 로컬 Python
    participant M as MLflow SDK와 azureml-mlflow
    participant A as AML workspace
    P->>M: AML Tracking URI와 Registry URI 지정
    Note over P,A: Azure CLI 로그인과 workspace 접근 권한 필요
    P->>M: start_run()
    M->>A: 인증 후 experiment에 run 생성
    A-->>M: run_id
    M-->>P: run_id
    P->>P: model.fit()으로 로컬 학습
    P->>M: log_params()와 log_metrics()
    M->>A: 설정과 검증 지표 기록
    P->>M: sklearn.log_model(artifact_path="model")
    M->>A: 해당 run에 모델 파일과 메타데이터 기록
    Note over A: 모델 참조는 runs:/run_id/model
    P->>M: search_runs()로 후보 비교
    M->>A: 기록된 실행과 지표 조회
    A-->>M: 후보 실행의 결과
    M-->>P: 비교할 결과와 선택할 run_id
    P->>M: register_model()에 선택한 모델 URI 전달
    M->>A: wine-logistic-study 이름 아래 새 버전 등록
    A-->>M: 등록된 모델 이름과 버전
    M-->>P: models:/wine-logistic-study/version
```

AML이 실행 메타데이터를 관리하고, 모델 파일과 보고서는 workspace에 연결된 아티팩트 저장소에 보관한다. `log_model()` 단계에서는 모델 파일도 원격에 기록한다. 모델 이름과 버전을 부여하는 등록 요청은 이 예제의 `register_model()` 단계에서 별도로 보낸다.

### 각 호출이 만드는 결과

| 순서 | 코드나 설정 | 남는 결과 |
| --- | --- | --- |
| 1. 대상 지정 | 두 URI를 AML workspace로 설정 | 이후 기록과 등록을 보낼 대상이 정해짐. 아직 학습이나 모델 등록은 없음 |
| 2. 실행 시작 | `mlflow.start_run()` | experiment 아래에 run이 생기고 `run_id`를 받음 |
| 3. 학습과 평가 | `model.fit()`, 검증 코드 | 로컬 메모리에 학습한 모델과 평가 결과가 생김 |
| 4. 결과 기록 | `log_params()`, `log_metrics()`, `sklearn.log_model()` | AML에 설정, 지표, 모델이 해당 run의 결과로 남음 |
| 5. 후보 선택 | `compare.py`의 `search_runs()` | 검증 결과로 선택한 `run_id`를 `selected-run.json`에 남김 |
| 6. 버전 등록 | `finalize.py`의 `register_model()` | `wine-logistic-study`라는 모델 이름 아래 새 버전이 생김 |

05편의 `finalize.py`에서 등록에 사용하는 호출은 다음 부분이다. 아래는 전체 파일에서 등록 요청만 뽑은 코드이며, `run_id`는 같은 AML workspace에서 선택한 실행의 ID다.

```python
registered = mlflow.register_model(
    model_uri=f"runs:/{run_id}/model",
    name="wine-logistic-study",
)
```

`runs:/<run_id>/model`은 로컬 폴더 경로가 아니다. 현재 Tracking URI가 가리키는 저장소에서 특정 run에 기록한 `model`을 참조한다. Registry URI도 같은 AML workspace로 맞췄으므로 그 모델이 같은 workspace의 모델 버전으로 등록된다.

AML studio에서는 실행과 지표를 Jobs의 experiment에서, 등록한 모델 이름과 버전을 Models에서 확인한다. 로컬에서 학습한 실행도 Jobs에 보일 수 있다. 화면에 Job으로 표시된다는 사실과 AML 클러스터가 학습을 수행했다는 사실은 구분한다.

## 라이브러리와 서비스의 역할

[MLflow 개요](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow?view=azureml-api-2)는 AML이 오픈소스 MLflow 서버 인스턴스를 호스팅하는 것이 아니라 호환 API를 제공한다고 설명한다. 서버 프로세스의 설치와 AML workspace 연결을 같은 작업으로 보지 않았다.

| 구성 요소 | 맡는 일 | 이 시리즈의 사용 위치 |
| --- | --- | --- |
| `mlflow` | 실행 기록, 조회, 모델 패키징과 로딩 | 학습 및 비교 스크립트 |
| `azureml-mlflow` | `azureml://` 대상과의 연동, 인증과 아티팩트 처리 | AML에 연결하는 Python 환경 |
| `azure-ai-ml`의 `MLClient` 또는 Azure CLI의 `ml` 확장 | workspace, compute, Job, 모델 자산과 배포 관리 | CLI로 URI 조회와 Job 제출 |
| AML workspace | 실험과 실행, 모델 자산을 관리하는 서비스 범위 | 기록과 등록의 대상 |
| 아티팩트 저장소 | 모델과 보고서 등의 실제 파일 보관 | workspace에 연결된 저장소 |

AML SDK v2의 `MLClient`를 만든다고 학습 메트릭이 자동으로 기록되는 것은 아니다. 리소스와 Job 관리는 CLI나 SDK v2로, 학습 결과의 구조화된 기록은 MLflow로 나누었다. 이 시리즈는 CLI를 사용하므로 로컬에 `azure-ai-ml`을 별도로 설치하지 않는다.

## 로컬 연습과 AML 연결의 구분

01~03편에서는 로컬 SQLite와 파일 저장소를 사용한다. 이 단계의 모델은 AML에 등록된 것이 아니다. 04편에서 기록 대상을 AML workspace로 바꾸고, 05편에서 선택한 모델을 이름과 버전으로 등록한다. 06편의 추론 서비스 배포는 등록과 별개의 작업이다.

Tracking URI를 바꾸는 것만으로 이전 로컬 run이 AML로 복사되지는 않는다. 예제에서는 같은 학습 코드를 다시 실행해 원격에 새 기록을 만든다. 이미 가진 모델을 다시 학습하지 않고 가져오는 경로는 05편에서 따로 다룬다.

## 실습 폴더와 파일의 연결

| 파일 | 처음 만드는 편 | 사용하는 단계 |
| --- | --- | --- |
| `requirements.txt`, `src\train.py` | 01 | 학습과 모델 기록 |
| `compare.py`, `inspect_run.py` | 02 | 후보 선택과 기록 조회 |
| `check_model.py` | 03 | 모델 재로딩과 signature 확인 |
| `requirements-azure.txt`, `conda.yml`, `job.yml` | 04 | AML 연결과 원격 실행 |
| `finalize.py` | 05 | 선택한 모델의 평가와 버전 등록 |
| `make_request.py` | 06 | AML 온라인 추론용 입력 작성 |

코드는 해당 편에 파일명과 함께 제시했다. 명령은 Windows PowerShell을 기준으로 하며 가상환경을 활성화하지 않고 `.venv` 안의 실행 파일을 직접 호출한다. 각 편의 명령은 같은 실습 폴더의 루트에서 실행한다.

## 실행 범위와 비용

로컬 학습과 비교, 모델 재로딩 및 등록, 자동 기록, 요청 파일 생성은 로컬에서 확인한 범위다. 실제 AML workspace 연결, 원격 학습과 배포는 사용하는 구독의 권한, 네트워크와 컴퓨팅 조건에서 별도로 확인한다.

04편부터는 AML 리소스와 비용이 관계된다. 06편은 등록 모델을 온라인 또는 배치 추론에 연결하는 후속 학습이다. 학습 코드를 실행했다고 endpoint가 자동 생성되지는 않는다. 공유 리소스를 실습 종료를 이유로 삭제하지 않는다.

## 다른 Azure 실행 환경으로 확장

로컬 Python에서 기록 대상과 모델 등록 대상을 구분한 뒤에는 실행 환경을 Databricks나 Synapse로 옮겨 볼 수 있다. 학습이 실행되는 제품과 모델을 관리하거나 배포하는 제품이 반드시 같아야 하는 것은 아니다.

| 확장 경로 | 문서에서 구분하는 것 | 앞의 실습과 다른 준비 |
| --- | --- | --- |
| Azure Databricks | 양쪽 workspace에 기록하는 dual tracking과 AML 전용 기록, 별도로 선택하는 모델 Registry | Databricks 실행 환경, 라이브러리와 인증, 두 추적 대상의 관계 |
| Azure Synapse Analytics | Spark 환경에서 AML로 기록한 뒤 AML 배포나 Spark 추론으로 소비하는 경로 | Spark pool의 패키지, 추적 URI, 인증과 데이터 접근 |
| 기본 flavor가 없는 모델 | 원래 모델의 로딩과 `predict()`를 감싸는 PyFunc 패키지 | 전처리와 후처리, 추가 파일과 의존성, 입출력 동등성 |

Databricks의 dual tracking이 모델 Registry에도 자동으로 이중 등록한다는 뜻은 아니다. 기록 대상과 등록 대상을 별도로 확인해야 한다. 해당 문서는 Private Link를 사용하는 AML workspace에 대한 dual tracking 제약도 설명하므로, 같은 설정을 모든 네트워크에 적용하지 않는다.

Synapse에서는 패키지를 로컬 PC에 설치한 것만으로 Spark 세션에서 사용할 수 있는 것은 아니다. 관리 대상인 pool 또는 실행 환경의 의존성과 인증을 확인해야 한다. Spark UDF로 모델을 실행하는 것과 AML endpoint에 모델을 배포하는 것도 별도 경로다.

## 참고 자료와 학습 후 확인할 결과

아래는 세 출발 문서와 직접 연결된 주요 문서를 읽으며 정리한 범위다. AML의 모든 기능을 같은 실습에 넣지는 않고, 기본 경로와 후속 확장 경로를 나누었다. 확인 기준은 2026-10-21이다.

### 도구의 의미와 역할 비교

| 공식 문서 | 이 목차에서 확인한 부분 |
| --- | --- |
| [MLflow의 ML 기능 개요](https://mlflow.org/docs/latest/ml/) | 실험 추적, 평가, 모델 Registry와 배포의 범위 |
| [BentoML 개요](https://docs.bentoml.com/en/latest/) | 서빙 프레임워크와 추론 플랫폼의 관계 |
| [BentoML Service](https://docs.bentoml.com/en/latest/build-with-bentoml/services.html) | 모델 로딩과 예측 코드를 API로 노출하는 구현 단위 |
| [Bento 패키징](https://docs.bentoml.com/en/latest/get-started/packaging-for-deployment.html) | 코드, 모델과 환경을 배포 단위로 구성하는 방식 |
| [MLflow 모델의 BentoML 연동](https://docs.bentoml.com/en/latest/examples/mlflow.html) | MLflow 모델 가져오기와 BentoML Service의 연결 |
| [BentoCloud 배포](https://docs.bentoml.com/en/latest/get-started/cloud-deployment.html) | 오픈소스 프레임워크와 관리형 배포 플랫폼의 구분 |

### 개념과 기본 학습 경로

| 공식 문서 | 정리한 논점 | 학습 후 확인할 것 |
| --- | --- | --- |
| [MLflow와 Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow?view=azureml-api-2) | 호환 API와 도구별 책임, Tracking과 Jobs의 관계 | MLflow 서버 설치와 AML 연결을 구분할 수 있는지 |
| [아티팩트와 모델](https://learn.microsoft.com/en-us/azure/machine-learning/concept-mlflow-models?view=azureml-api-2) | `MLmodel`, flavor, signature, 모델 환경과 로딩 방식 | 저장한 폴더를 보고 실행 계약을 설명할 수 있는지 |
| [실험과 실행 추적](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-cli-runs?view=azureml-api-2&tabs=interactive%2Ccli) | 대화형 실행과 AML Job의 experiment 및 run 설정 | 실행 주체가 달라도 같은 학습 기록을 남길 수 있는지 |
| [MLflow 연결 설정](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-configure-tracking?view=azureml-api-2) | Tracking URI, 인증, 자동 설정되는 실행 문맥 | 대상 workspace와 실제 실행 환경을 확인할 수 있는지 |
| [메트릭, 파라미터, 파일 기록](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-view-metrics?view=azureml-api-2) | 수동 기록, 자동 기록, 파일과 메트릭, 비동기 기록 | stdout와 구조화된 기록, 최신 값과 이력을 구분하는지 |
| [MLflow 모델 로깅](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-log-mlflow-models?view=azureml-api-2) | 모델 형식, signature와 의존성, 버전 조건, 사용자 정의 모델 | 원시 파일 업로드와 모델 기록이 왜 다른지 |
| [실행 조회와 비교](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-track-experiments-mlflow?view=azureml-api-2) | 검색, 필터, 메트릭 이력, 아티팩트 조회와 지원 표 | 비교 조건을 고정하고 필요한 파일을 다시 읽을 수 있는지 |
| [모델 Registry 관리](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-manage-models-mlflow?view=azureml-api-2) | run 또는 로컬 폴더의 등록, 버전과 stage, workspace 경계 | 등록할 모델의 원천과 대상, 구체 버전을 설명할 수 있는지 |

### 모델 소비와 후속 확장

| 공식 문서 | 정리한 논점 | 학습 후 확인할 것 |
| --- | --- | --- |
| [MLflow 모델 배포 지침](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-mlflow-models?view=azureml-api-2) | No-code 범위, 환경과 입력 계약, 배포 도구의 차이 | 모델 등록과 실행 서비스를 구분할 수 있는지 |
| [온라인 endpoint 배포](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-mlflow-models-online-endpoints?view=azureml-api-2) | 모델 선택, endpoint와 deployment 생성, 요청과 트래픽 | 같은 입력의 로컬 및 원격 결과를 비교할 수 있는지 |
| [배치 endpoint 배포](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-mlflow-batch?view=azureml-api-2) | 입력 데이터, 비동기 scoring Job, 파일 단위 분산과 결과 | 호출 성공과 Job 완료, 결과 파일을 구분하는지 |
| [온라인 배포의 점진적 전환](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-mlflow-models-online-progressive?view=azureml-api-2) | 복수 deployment의 직접 테스트와 트래픽 이동 | 모델 버전 변경과 트래픽 전환, 복구를 구분하는지 |
| [기존 모델을 MLflow로 변환](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-convert-custom-model-to-mlflow?view=azureml-api-2) | 기존 모델 파일을 PyFunc, 환경과 signature로 패키징 | 변환 전후 같은 입력에서 예측이 유지되는지 |
| [Azure Databricks 연결](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-azure-databricks?view=azureml-api-2) | Dual tracking, AML 전용 기록, 별도의 Registry 대상 | 어느 쪽에 기록하고 등록했는지 설명할 수 있는지 |
| [Azure Synapse Analytics 연결](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-use-mlflow-azure-synapse?view=azureml-api-2) | Spark 환경의 패키지와 인증, AML 기록과 모델 소비 | Spark 실행과 AML 모델 관리의 경계를 확인하는지 |

### 리소스와 실행 준비

| 공식 문서 | 이 실습에서 확인한 부분 |
| --- | --- |
| [Workspace와 초기 리소스](https://learn.microsoft.com/en-us/azure/machine-learning/quickstart-create-resources?view=azureml-api-2) | workspace 준비와 compute instance의 역할, 생성 비용과 정리 |
| [Compute cluster 만들기](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-attach-compute-cluster?view=azureml-api-2) | 학습 실행 자원, 최소 및 최대 노드 수, 유휴 시 축소 |
| [Workspace 권한](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-assign-roles?view=azureml-api-2) | 실험과 Job, 모델 관리, compute와 배포 권한의 구분 |
| [Command Job YAML 명세](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-command?view=azureml-api-2) | 코드 업로드 범위, inputs, 환경, compute와 Job 이름 |

MLflow API, AML 서비스의 지원 범위, 플러그인의 의존성은 따로 바뀐다. 환경을 다시 만들 때는 이 노트의 고정 버전과 공식 문서의 버전 조건을 함께 확인한다.
