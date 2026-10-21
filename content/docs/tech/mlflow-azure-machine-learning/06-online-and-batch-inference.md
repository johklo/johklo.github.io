---
title: "06. 온라인 및 배치 추론과 모델 교체"
description: "등록 모델을 온라인과 배치 추론에 연결하는 계약과 요청 형식, 점진적 전환을 구분하기"
date: 2026-10-21T09:55:00+09:00
lastmod: 2026-10-21T14:11:00+09:00
weight: 60
tags: ["mlflow", "mlops", "azure-machine-learning"]
---

등록한 모델을 사용하는 방식은 요청에 바로 응답하는 온라인 추론과 결과 파일을 남기는 배치 추론으로 나뉜다. 모델 버전과 실제 서비스를 연결하는 deployment, endpoint의 역할을 구분했다.

[목차의 도구 역할 비교](../#전체-mlops에서의-역할)에서 BentoML을 별도 서빙 구현의 예로 다뤘다. 이 편은 BentoML을 사용하는 실습이 아니라 AML의 MLflow 모델 배포 경로를 다룬다.

## 준비 조건과 실습 범위

[05편](../05-model-registration/)의 등록 모델과 `src\train.py`를 사용한다. 로컬에서는 요청 파일을 생성해 모델 입력과 맞는지 확인한다. 실제 endpoint와 deployment 생성은 링크한 공식 배포 절차에서 별도로 진행하는 후속 실습이다. 배포 권한, 추론 자원, 네트워크와 비용을 확인한 뒤 실행할 범위다.

## 등록된 모델을 추론에 연결

이 편에서는 [배포 지침](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-mlflow-models?view=azureml-api-2), [온라인 배포](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-mlflow-models-online-endpoints?view=azureml-api-2), [배치 배포](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-mlflow-batch?view=azureml-api-2)를 묶어 읽었다. 앞의 스크립트는 등록까지 수행한다. 아래에서는 그 모델을 소비하는 구조와 후속 실습에서 확인할 조건을 정리한다.

### 등록 모델, deployment, endpoint

| 대상 | 나타내는 것 | 모델을 바꿀 때의 관계 |
| --- | --- | --- |
| 등록 모델 버전 | 특정 모델 패키지 | 배포가 사용할 모델의 구체 버전 |
| Deployment | 모델을 실행하는 구현과 자원 설정 | 모델, 실행 환경, 컴퓨팅 등의 조합 |
| Endpoint | 사용자가 호출하는 접점 | 어떤 deployment로 요청이나 작업을 보낼지 관리 |

Registry에서 새 버전을 만들었다고 기존 deployment가 그 버전으로 교체되지는 않는다. 등록한 버전을 선택해 배포하고, 필요하면 endpoint의 연결을 변경하는 별도 과정이 있다.

```mermaid
flowchart LR
    accTitle: 모델 등록 이후의 온라인 및 배치 추론
    accDescr: 등록 모델의 구체 버전을 선택해 온라인 또는 배치 deployment를 만든다. 온라인 요청은 예측 응답으로, 배치 호출은 비동기 Job과 결과 파일로 이어진다.
    M["등록 모델의 특정 버전"] --> O["온라인 deployment"]
    M --> B["배치 deployment"]
    Q["클라이언트 요청"] --> E["온라인 endpoint"]
    E --> O
    O --> R["예측 응답"]
    D["입력 데이터 위치"] --> BE["배치 endpoint 호출"]
    BE --> B
    B --> J["추론 Job"]
    J --> F["결과 파일"]
```

### No-code 배포에서 자동화되는 범위

No-code는 추론 코드와 환경이 필요 없다는 뜻보다, 모델 계약을 읽어 AML이 기본 추론 코드와 환경을 구성한다는 뜻으로 이해했다. 자동 추론 경로에서는 `python_function`인 PyFunc flavor가 기준이 된다.

| 자동으로 처리하는 부분 | 여전히 정할 부분 |
| --- | --- |
| MLflow 모델의 로딩과 `predict()` 호출 | 어떤 모델 버전을 사용할지 |
| 모델 의존성을 바탕으로 한 추론 환경 구성 | 자원 크기, 개수, 확장과 네트워크 조건 |
| Signature를 이용한 입력 형식 확인 | 업무상 유효한 입력과 허용할 오류 |
| 기본 요청 처리 코드 | 인증, 배포 권한, 트래픽 전환과 복구 |

추론 환경을 직접 정의하는 경로에서는 모델 패키지 외에 추론 서버 패키지도 필요하다. 공식 배포 지침의 `azureml-inference-server-http`, `azureml-ai-monitoring` 등 요구 조건을 배포 방식에 맞춰 확인한다. 학습용 `conda.yml`을 그대로 추론 환경이라고 가정하지 않는다.

전처리와 후처리가 모델 안에 없거나 다른 flavor의 로딩 API가 필요하면 사용자 정의 scoring script를 선택할 수 있다. 이 경우 실행 환경도 함께 지정해야 한다. 기본 배포와 사용자 정의 배포의 책임이 달라지는 지점이다.

### 온라인 추론의 흐름

온라인 endpoint는 요청을 받고 예측을 응답하는 경로다. 후속 실습의 작업 순서는 다음과 같이 정리했다.

1. AML Models에서 배포할 이름과 구체 버전을 확인한다.
2. Endpoint의 이름, 인증 방식과 접근 범위를 정한다.
3. 해당 버전의 모델과 컴퓨팅을 사용하는 deployment를 만든다.
4. Deployment 상태와 로그를 확인하고 지정한 deployment에 테스트 요청을 보낸다.
5. 일반 요청이 해당 deployment로 가도록 트래픽을 설정한다.
6. 지연, 오류, 예측 결과를 확인한 뒤 유지 또는 복구를 판단한다.

트래픽이 배정되지 않은 deployment를 직접 지정해 테스트하는 것과 endpoint의 일반 요청을 받게 만드는 것은 다르다. 배포 완료만으로 서비스 연결까지 확인했다고 보지 않는다.

#### 요청 데이터의 형태

로컬 `model.predict(DataFrame)` 호출에는 HTTP 본문이 없다. 이를 endpoint 호출로 바꿀 때는 서버가 기대하는 JSON 구조를 확인해야 한다.

| 실행 방식 | 표 데이터 입력의 바깥 구조 |
| --- | --- |
| 로컬 Python `predict()` | DataFrame 객체 |
| MLflow 내장 서버의 표 데이터 요청 | `dataframe_split` 안에 `columns`, `data` 등 |
| AML no-code 온라인 endpoint | `input_data` 안에 `columns`, `data` 등 |

따라서 모델 폴더에 있는 serving 입력 예시를 모든 서버에 그대로 보내도 된다고 가정하지 않는다. 다음 코드는 같은 Wine 테스트 데이터에서 AML 요청 파일만 만든다. Endpoint를 생성하거나 호출하는 코드는 아니다.

`make_request.py`:

```python
import json
from pathlib import Path

from src.train import load_data


_, _, X_test, _, _, _, _ = load_data()
samples = X_test.head(2)
payload = {
    "input_data": json.loads(
        samples.to_json(orient="split", index=False)
    )
}
Path("sample-request.json").write_text(
    json.dumps(payload, indent=2), encoding="utf-8"
)
print("AML request written to sample-request.json")
```

```powershell
.\.venv\Scripts\python.exe .\make_request.py
```

후속 실습에서 workspace에 온라인 endpoint와 deployment를 만든 뒤에는 다음 형태로 특정 deployment를 테스트할 수 있다. 아래 이름은 실제 생성한 값으로 바꾸며, workspace 변수는 04편의 연결 설정에서 사용한 값과 같다.

```powershell
$endpoint = "<created-endpoint-name>"
$deployment = "<created-deployment-name>"
az ml online-endpoint invoke --name $endpoint --deployment-name $deployment --request-file .\sample-request.json --resource-group $resourceGroup --workspace-name $workspace --subscription $subscription
```

같은 두 행을 로컬의 등록 모델에 전달한 결과와 비교하면 저장 모델과 서빙 모델이 같은 입력 계약을 따르는지 확인할 수 있다. 이 비교와 별개로 동시 요청, 큰 입력, 초기화 지연, 잘못된 입력의 동작은 추가 검증 대상이다.

### 배치 추론의 흐름

배치 endpoint 호출은 요청 안의 몇 행을 바로 예측해 응답하는 온라인 호출과 다르다. 처리할 데이터 위치를 받아 비동기 추론 Job을 만들고, 결과를 저장소에 남긴다.

1. 등록한 MLflow 모델 버전과 사용할 compute cluster를 확인한다.
2. Batch endpoint와 model deployment를 만든다.
3. 입력 파일 위치, 접근 권한, 지원 형식과 signature를 확인한다.
4. Endpoint를 호출해 추론 Job ID를 받는다.
5. Job 상태와 실패한 파일, 재시도 결과를 확인한다.
6. 완료 후 결과 파일을 내려받아 입력 파일과 예측을 연결한다.

기본 MLflow 배치 경로에서 표 데이터는 CSV와 Parquet 계열을 DataFrame으로 읽고, 지원 이미지 파일은 배열로 읽는다. 그 밖의 파일 형식이나 행 단위 분할, 특별한 전처리가 필요하면 scoring script를 사용하는 경로를 검토한다.

`mini_batch_size`는 기본 경로에서 행 수가 아니라 파일 수다. CSV 파일 하나에 많은 행이 들어 있으면 작은 mini-batch 설정이어도 큰 메모리가 필요할 수 있다. 입력 파일을 나눌 단위와 각 파일의 처리 시간을 함께 봐야 한다.

Batch endpoint를 호출해 받은 Job ID는 완료된 예측 결과가 아니다. 입력 파일명과 행, 결과 파일의 예측을 연결할 기준도 남겨야 한다. Endpoint를 삭제해도 이미 만들어진 scoring Job과 결과가 함께 지워지는 것은 아니다.

### 배포 도구와 모델 전환

MLflow 형식의 모델을 배포하는 것과 모든 배포를 MLflow SDK로 관리하는 것은 다른 선택이다.

| 배포 작업 | 도구 선택 |
| --- | --- |
| 기본 온라인 배포 | MLflow 배포 클라이언트 또는 AML CLI, SDK, studio |
| 사용자 정의 scoring script를 쓰는 온라인 배포 | AML CLI, SDK, studio |
| 배치 endpoint 배포 | AML CLI, SDK, studio |
| 선언적 설정과 자동화 | YAML을 관리하는 AML CLI 또는 SDK 경로 검토 |

[점진적 전환 문서](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-mlflow-models-online-progressive?view=azureml-api-2)는 같은 endpoint 아래에 기존 deployment와 새 deployment를 두는 방법을 다룬다. 새 deployment를 일반 트래픽 0% 상태에서 직접 테스트한 뒤 일부 트래픽을 옮기고, 문제가 없으면 비중을 늘린다.

이때 바꾸는 것은 Registry의 stage 이름이 아니라 endpoint의 트래픽 설정이다. 트래픽을 이전 deployment로 돌려도 새 deployment의 자원이 자동으로 삭제되지는 않는다. 두 배포를 유지하는 기간의 비용과 제거 시점도 별도 결정이다.

## 확인할 결과

로컬 실습에서는 `sample-request.json`에 `input_data`가 있고 13개 입력 열과 두 행의 데이터가 있어야 한다. 온라인 배포를 진행했다면 같은 입력에서 등록 모델과 예측이 일치하는지 확인한다. 배치 실습은 호출 시 받은 Job ID, 작업 완료 상태, 저장된 예측 파일을 각각 확인한다.

## 오류 확인

| 증상 | 확인할 부분 |
| --- | --- |
| 온라인 요청의 본문을 해석하지 못함 | MLflow 내장 서버용 본문과 AML의 `input_data`를 혼동했는지 |
| Signature 입력 오류 | 열 이름, 타입, shape와 필수 입력 |
| Deployment 시작 또는 모델 로딩 실패 | 모델 환경, 추론 서버 패키지와 네트워크 |
| Deployment는 있지만 일반 요청이 가지 않음 | Endpoint의 트래픽 설정과 직접 테스트의 차이 |
| 배치가 느리거나 메모리 부족 | 파일 수 기준의 mini-batch와 파일 안의 행 수 |
| 새 버전 등록 후 응답이 그대로임 | 기존 deployment가 새 모델로 자동 교체되는 것은 아님 |

## 비용과 정리

01~05편의 학습 코드는 온라인 추론 엔드포인트를 만들지 않는다. 모델을 등록했다고 HTTP 서비스가 시작되는 것은 아니다. 이 편의 후속 배포 실습을 진행한다면 추론 자원과 정리 범위가 추가된다.

| 대상 | 학습 후 확인할 것 |
| --- | --- |
| 로컬 UI | 터미널에서 종료했는지 |
| AML compute cluster | 실행 중인 Job과 노드 수, 최소 노드 수, 축소 설정 |
| Compute instance | 별도로 켰다면 중지할 대상인지 |
| 모델과 아티팩트 | 저장량과 보존 기간, 남겨 둘 비교 결과 |
| 온라인 deployment | 트래픽이 없어도 유지되는 추론 자원, 전환 후 남은 이전 배포 |
| 배치 추론 | 실행 중인 scoring Job, 공유 compute, 입력과 결과 파일 |
| Workspace 관련 리소스 | 스토리지 등 컴퓨팅 중지 후에도 남는 비용 |

Job이 끝나도 모든 관련 비용이 0이 되는 것은 아니다. 공유 workspace나 공유 클러스터는 실습 종료를 이유로 삭제하지 않는다.

## 생각할 점

- 모델 signature와 HTTP 요청의 바깥 구조는 각각 무엇을 정하는가.
- 모델 버전, deployment, endpoint의 변경을 같은 작업으로 보고 있지 않은가.
- 트래픽을 되돌린 뒤에도 남는 자원과 비용은 무엇인가.

## 참고 자료

- [MLflow 모델 배포 지침](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-mlflow-models?view=azureml-api-2)
- [온라인 endpoint 배포](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-mlflow-models-online-endpoints?view=azureml-api-2)
- [배치 endpoint 배포](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-mlflow-batch?view=azureml-api-2)
- [점진적 모델 전환](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-deploy-mlflow-models-online-progressive?view=azureml-api-2)

[이전: 05. 모델 등록과 버전 관리](../05-model-registration/), [시리즈 목차](../)
