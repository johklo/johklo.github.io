---
title: "06. 모델을 프로덕션으로"
description: "배치 추론에서 요청 기반 서비스로 옮기는 설계와 입력 변화, 품질 판단, 대응 정책의 연결을 BentoML과 Evidently로 이해하기"
date: 2026-10-18T21:30:00+09:00
lastmod: 2026-11-07T22:30:00+09:00
weight: 60
draft: false
tags: ["book-club", "ml-platform-engineering", "bentoml", "monitoring"]
---

4~5장에서는 MLflow에 등록한 소득 분류 모델과 Feast의 피처를 KFP 배치 추론으로 연결했다. 사용자 목록과 기준 시각을 파일로 받고 결과를 저장하는 흐름이다. 6장은 같은 모델을 사용자 ID가 들어올 때마다 예측하는 API로 바꾸고, 배포 뒤 들어오는 입력이 학습 때와 달라지는지 살펴본다.

이 전환에서 질문은 **요청을 안정적으로 처리할 수 있는가**와 **현재 데이터에서도 예측을 믿을 수 있는가**로 나뉜다. BentoML은 모델과 요청 처리 코드를 배포 단위로 묶고, Evidently는 기준 데이터와 현재 입력을 비교한다. 서빙이 동작해도 품질이 유지된다는 보장은 없고, 데이터 변화가 보여도 곧바로 재학습할 이유가 되는 것은 아니다.

책의 6.1을 읽을 때는 모델, Service, Runner와 Bento가 각각 무엇을 책임지는지, 6.2에서는 보고서의 수치가 무엇을 증명하는지에 집중하면 된다. 이를 [운영 인프라에서 관측을 연결하는 방식](#production-monitoring)으로 이어 설명하고, 뒤의 [실습 순서](#book-ch06-sop)에서 같은 흐름을 실제 클러스터에서 실행한 명령과 화면으로 따라간다.

## 전체 그림 {#platform-map}

6장에는 MLflow, Feast, BentoML, Yatai, Kubeflow Pipelines와 Evidently가 함께 등장한다. 도구마다 따로 읽으면 각자 무엇을 하는지는 알아도 무엇이 어디서 어디로 넘어가는지는 잘 보이지 않는다. 아래 그림은 이번 실습 클러스터에서 각 구성 요소가 실행되는 위치와, 4~5장의 산출물이 API와 드리프트 관측으로 이어지는 순서를 번호로 표시한 것이다.

파란 상자가 이 장에서 새로 만드는 부분이고, 회색 상자는 4~5장에서 이미 만든 부분이다. 점선 주황 상자는 7장 이후에 이어질 부분이다. Yatai 영역 아래의 점선 경로는 이 실습에서 함께 확인한 대안 경로로, 같은 Bento 이미지를 일반 Deployment와 Service로 배포한다.

```mermaid
flowchart LR
    accTitle: 6장 플랫폼 구성 요소의 실행 위치와 산출물 이동 순서
    accDescr: 개발자 PC의 학습 노트북이 MLflow와 S3, Feast Registry와 Redis를 준비한다. bentoml CLI가 MLflow 모델을 가져와 Bento를 만들고 Yatai에 push하면 이미지 빌더가 이미지를 만들고 BentoDeployment가 API Server와 Runner Pod를 실행한다. 대안 경로는 같은 이미지를 일반 Deployment로 실행한다. API는 요청마다 Redis에서 피처를 읽어 Runner로 예측하고 입력 윈도우를 Evidently로 보낸다. KFP 파이프라인의 드리프트 검사 작업도 Evidently workspace에 보고서를 올린다.
    subgraph PC["개발자 PC"]
        NB["JupyterLab<br/>4장 학습 노트북"]
        CLI["bentoml CLI<br/>import, build, push"]
        SDK["KFP SDK<br/>파이프라인 컴파일"]
        USER["요청 클라이언트<br/>Swagger UI"]
    end
    subgraph KF["kind 클러스터: kubeflow 네임스페이스"]
        KFP["KFP UI와 API"]
        TASK["파이프라인 작업 Pod<br/>대상 읽기, 피처 조회, 추론"]
        S3[("SeaweedFS S3<br/>업무 버킷과 mlpipeline")]
        FREG["Feast Registry 파일<br/>feature-registry 버킷"]
    end
    subgraph MLNS["mlflow 네임스페이스"]
        MLF["MLflow Tracking과<br/>Model Registry"]
        PG[("Postgres<br/>메타데이터")]
    end
    subgraph RNS["redis 네임스페이스"]
        RD[("Redis<br/>Feast 온라인 저장소")]
    end
    subgraph YNS["yatai-system와 서빙 네임스페이스"]
        YAT["Yatai<br/>모델과 Bento 저장소"]
        IMB["yatai-image-builder<br/>kaniko Job"]
        REG[("컨테이너 레지스트리")]
        BD["BentoDeployment<br/>yatai-deployment"]
        APIP["API Server Pod<br/>Service, Feast 조회, 인코딩"]
        RUNP["Runner Pod<br/>random-forest-classifier"]
        ALT["대안: 일반 Deployment와 Service<br/>ch06-serving 네임스페이스"]
    end
    subgraph OBS["관측"]
        DRIFT["KFP 드리프트 검사 작업"]
        EVW["Evidently workspace와 대시보드"]
    end
    NEXT["7장 이후<br/>데이터 계약과 학습 파이프라인"]

    NB -->|"① 등록 모델 버전 + run_id"| MLF
    MLF --- PG
    NB -->|"② 모델 파일, column_list.pkl, 기준 CSV"| S3
    NB -->|"③ feature_store.yaml, Registry"| FREG
    NB -->|"④ materialize: 사용자별 최신 피처"| RD
    MLF -->|"⑤ Production 모델 import"| CLI
    CLI -->|"⑥ bentoml push: Bento 태그와 모델"| YAT
    YAT -->|"⑦ BentoRequest"| IMB
    IMB -->|"⑧ 컨테이너 이미지"| REG
    REG -->|"⑨ 이미지 pull과 Pod 생성"| BD
    BD --> APIP
    BD --> RUNP
    CLI -.->|"⑨' containerize와 kind load"| ALT
    MLF -->|"⑩ 시작 시 column_list.pkl"| APIP
    FREG -->|"⑩ 시작 시 feature_store.yaml"| APIP
    USER -->|"⑪ 요청 user_id"| APIP
    RD -->|"⑫ 온라인 피처"| APIP
    APIP -->|"⑬ 인코딩한 입력과 예측 클래스"| RUNP
    SDK -->|"⑭ 파이프라인 YAML"| KFP
    KFP --> TASK
    TASK -->|"⑮ parquet 데이터셋 URI"| S3
    S3 -->|"⑮ 현재 피처 parquet"| DRIFT
    DRIFT -->|"⑯ 배치 드리프트 보고서"| EVW
    APIP -->|"⑰ 현재 입력 윈도우 보고서"| EVW
    EVW -.->|"재학습과 계약 검토"| NEXT

    classDef thisch fill:#e8f1ff,stroke:#2f6fd6,stroke-width:2px;
    classDef prev fill:#f3f3f3,stroke:#999;
    classDef next fill:#fff6e5,stroke:#d08a00,stroke-dasharray:4 3;
    class CLI,USER,YAT,IMB,REG,BD,APIP,RUNP,ALT,DRIFT,EVW,SDK thisch;
    class NB,KFP,TASK,S3,FREG,MLF,PG,RD prev;
    class NEXT next;
```

| 번호 | 누가 | 무엇을 넘기는가 | 어디에 남는가 | 실습 단계 |
| --- | --- | --- | --- | --- |
| ① | 4장 학습 노트북 | 등록 모델 `random-forest-classifier` 버전과 원천 run_id | MLflow Model Registry, Postgres | A-2, A-3 |
| ② | 4장 학습 노트북 | 모델 파일, `column_list.pkl`, 학습과 기준 CSV | `mlflow-artifacts`, `mlflow-datasets` 버킷 | A-3 |
| ③ | `feast apply`와 5장 Job | Feast 정의와 설정 파일 | `feature-registry` 버킷 | A-2 |
| ④ | `feast materialize` | 사용자별 최신 피처 | Redis | A-2 |
| ⑤ | `download_model.py` | MLflow의 Production 모델 | 로컬 BentoML 모델 저장소 | B-1 |
| ⑥ | `bentoml build`, `bentoml push` | Bento 태그와 모델 태그 | 로컬 Bento 저장소, Yatai | C-1, C-4 |
| ⑦ | Yatai | 이미지를 만들 Bento 요청 | `BentoRequest` 리소스 | C-4 |
| ⑧ | yatai-image-builder | kaniko로 만든 컨테이너 이미지 | 클러스터 안 레지스트리 | C-4 |
| ⑨ | yatai-deployment | API Server와 Runner Pod | `yatai` 네임스페이스 | C-4 |
| ⑨' | `bentoml containerize`, `kind load` | 같은 Bento의 이미지 | `ch06-serving` 네임스페이스 | C-2, C-3 |
| ⑩ | API 서버 초기화 | `column_list.pkl`, `feature_store.yaml` | API 프로세스 메모리와 작업 폴더 | B-2, B-3 |
| ⑪ | 클라이언트 | `{"user_id": ...}` 요청 | HTTP 요청 | B-3, C-3 |
| ⑫ | Feast SDK | 해당 사용자의 온라인 피처 | API 프로세스 메모리 | B-3, B-4 |
| ⑬ | API 서버와 Runner | 학습 열 순서로 인코딩한 입력, 예측 클래스 | 응답 `income_category` | B-3, B-4 |
| ⑭ | KFP SDK | 드리프트 검사를 넣은 파이프라인 YAML | KFP 파이프라인 버전 | D-2 |
| ⑮ | KFP 작업 Pod | 조회한 피처 parquet의 아티팩트 URI | `mlpipeline` 버킷 | D-2 |
| ⑯ | 드리프트 검사 작업 | reference와 current 비교 보고서 | Evidently workspace | D-3 |
| ⑰ | 드리프트 API 서비스 | 최근 요청 윈도우의 보고서 | Evidently workspace | D-4 |

그림을 읽을 때는 저장소와 실행 주체를 구분하면 된다. MLflow, S3, Redis는 상태를 보관하고, 노트북과 CLI, KFP 작업 Pod, API Pod는 그 상태를 읽어 다음 산출물을 만든다. Yatai는 예측을 계산하지 않고, Bento를 받아 이미지와 Pod로 바꾸는 배포 제어 계층이다.

아래는 이 장의 핵심 실행 경로를 시간 순서로 다시 그린 것이다. 앞의 그림에서 ⑥부터 ⑰까지가 한 번의 배포와 요청에서 어떻게 이어지는지 보여 준다.

```mermaid
sequenceDiagram
    accTitle: Bento 빌드부터 Yatai 배포, 요청 처리와 드리프트 윈도우까지
    accDescr: 개발자가 Bento를 빌드해 Yatai에 push하면 Yatai가 이미지 빌드를 요청하고 BentoDeployment가 API Server와 Runner Pod를 띄운다. Pod는 시작할 때 MLflow와 S3에서 열 목록과 Feast 설정을 받는다. 요청이 오면 Redis에서 피처를 읽고 인코딩해 Runner가 예측하며, 드리프트 서비스는 입력을 윈도우에 쌓아 크기가 차면 Evidently 보고서를 만든다.
    participant D as 개발자 PC<br/>bentoml CLI
    participant Y as Yatai
    participant B as image builder<br/>kaniko
    participant K as yatai-deployment
    participant A as API Server Pod
    participant R as Runner Pod
    participant F as Feast와 Redis
    participant E as Evidently
    D->>D: bentoml build로 Bento 태그 생성
    D->>Y: bentoml push로 모델과 Bento 업로드
    D->>Y: 배포 생성 요청 Bento 태그와 자원
    Y->>B: BentoRequest
    B->>B: Bento 내려받기와 이미지 빌드
    B-->>K: 레지스트리의 이미지 주소
    Y->>K: BentoDeployment
    K->>A: Deployment와 Service 생성
    K->>R: Runner Deployment와 Service 생성
    A->>A: 시작 시 column_list.pkl과 feature_store.yaml 준비
    R->>R: 모델 로드 후 준비 완료
    Note over A,R: 여기서부터 요청 가능한 상태
    D->>A: POST /predict와 user_id
    A->>F: get_online_features()
    F-->>A: 사용자 피처
    A->>A: 인코딩과 열 순서 맞추기
    A->>R: 모델 입력
    R-->>A: 예측 클래스
    A-->>D: income_category와 user_id
    opt 드리프트 서비스로 배포한 경우
        A->>A: 입력을 윈도우에 추가
        A->>E: 윈도우가 차면 reference와 비교한 보고서
    end
```

## 배치 추론을 BentoML의 요청 경로로 옮긴다 {#model-serving}

모델의 `predict()`를 호출하는 것과 다른 애플리케이션이 사용할 서비스를 운영하는 것은 다르다. 함수 호출에는 메모리 안의 입력과 모델이 있으면 되지만, 서비스에는 요청 규격, 전처리, 모델 로드, 동시 요청 처리와 실패 응답도 필요하다.

5장의 대상 읽기, 피처 조회, 추론과 결과 저장은 한 묶음의 작업이 끝나는 흐름이었다. 6장에서는 사용자 ID를 요청으로 받고, 온라인 피처를 조회하고, 같은 모델 입력으로 변환해 응답하는 경로가 된다. 모델이 바뀌기보다 그 모델을 둘러싼 실행과 실패의 조건이 바뀐다.

| 구분 | 배치 추론 | 온라인 추론 |
| --- | --- | --- |
| 실행 계기 | 일정이나 준비된 데이터 묶음 | 사용자와 애플리케이션의 요청 |
| 입력 | 파일, 테이블, 대상 기간 | 요청 본문과 요청 시점에 조회한 피처 |
| 응답 시점 | 작업 완료 후 결과 파일 제공 | 요청을 기다리는 클라이언트에 응답 |
| 주요 운영 기준 | 완료 시간, 처리량, 재실행과 결과 중복 | 지연, 동시성, 가용성과 오류 처리 |
| 이 책의 예 | 5장의 대상 목록과 과거 피처 | 6장의 사용자 ID와 온라인 피처 |

온라인이라고 모델을 매번 새로 학습하는 것은 아니다. 이미 학습한 모델을 메모리에 올리고 여러 요청에서 재사용한다. 요청마다 피처 조회, 전처리와 예측이 발생하므로 전체 지연에는 모델 계산 외의 시간도 포함된다. Redis 조회가 느리면 Runner만 늘려도 API 지연이 충분히 줄지 않을 수 있다.

### 모델을 가져오는 것과 서비스를 묶는 것은 다르다

3장에서는 FastAPI, Docker와 Kubernetes 명세를 직접 연결했다. BentoML은 이 반복적인 배포 준비를 ML 서비스의 패키지 구조로 표준화한다. 학습 프레임워크를 대체하는 것이 아니라 서로 다른 프레임워크의 모델과 그 앞뒤의 처리, 실행 환경을 배포 단위로 묶는 역할이다. 책에서 사용하는 1.1.10의 주요 개념은 다음과 같다.

| 구성 | 의미 | 소득 분류에서의 역할 |
| --- | --- | --- |
| Model store | 이름과 태그로 모델을 보관하는 저장소 | MLflow에서 가져온 분류기 보관 |
| Service | API의 입출력과 처리 흐름 정의 | 사용자 ID 검사, Feast 조회, 전처리와 응답 |
| Runnable | 실행할 연산과 지원 자원 등을 정의하는 단위 | 모델 프레임워크가 제공하는 예측 연산 |
| Runner | Runnable을 worker에서 실행하는 계산 단위 | 분류기를 로드하고 예측 호출 처리 |
| Bento | 서비스 코드, 모델과 의존성 구성을 묶은 배포 산출물 | 같은 서비스를 다시 실행할 패키지 |
| 컨테이너 이미지 | Bento를 컨테이너 런타임에서 실행할 이미지 | 클러스터에 전달할 실행 환경 |
| Deployment | 특정 버전을 자원, 복제본, 주소와 함께 실행한 상태 | 실제 요청을 받는 API와 Runner |

Service는 요청을 어떻게 해석하고 어떤 연산을 호출할지 정한다. Runner는 모델 계산을 worker에서 실행한다. 두 역할을 나누면 API 처리량과 모델 계산에 필요한 자원을 따로 조정할 수 있다. Runner는 Kubernetes의 학습 Job을 뜻하지 않으며, 항상 별도 Pod인 것도 아니다. 로컬 실행에서는 worker 프로세스로, 책의 Yatai 배포에서는 분리된 Pod로 실행하는 구성을 다룬다.

![Service가 있는 API 서버와 모델이 있는 Runner 서버가 HTTP 또는 gRPC로 통신하는 BentoML 구조.](https://raw.githubusercontent.com/bentoml/BentoML/fa278835a5333c5d378a0b03a9b56a9fc4ce21e4/docs/source/_static/img/concepts/runners/default.png)

그림 6-1. API 처리와 모델 실행을 분리한 Runner 구조. 출처: [BentoML 1.1.10 공식 문서](https://github.com/bentoml/BentoML/blob/fa278835a5333c5d378a0b03a9b56a9fc4ce21e4/docs/source/concepts/runner.rst), [Apache-2.0](https://github.com/bentoml/BentoML/blob/fa278835a5333c5d378a0b03a9b56a9fc4ce21e4/LICENSE). 원본 도식을 변경 없이 사용했다.

그림의 경계는 API 요청을 처리하는 프로세스와 계산을 실행하는 프로세스의 구분이다. 아래는 여기에 이 장의 Feast 조회와 전처리를 넣어 읽은 흐름이다.

```mermaid
flowchart LR
    accTitle: API 처리와 모델 계산을 분리한 BentoML 서빙 구조
    accDescr: API 서버는 요청을 검사하고 피처를 조회해 전처리한다. 모델 계산은 Runner worker가 담당하며 결과를 API 서버가 후처리해 응답한다. 두 실행 계층의 자원과 복제본은 배포 구성에서 따로 정할 수 있다.
    C["클라이언트"] --> API["API 서버<br/>입력 검사와 요청 처리"]
    API --> F["Feast<br/>피처 조회"]
    F --> PRE["학습과 같은 전처리"]
    PRE --> R["Runner worker<br/>모델 계산"]
    R --> POST["후처리와 응답"]
    POST --> C
```

MLflow Registry는 모델의 이름, 버전과 학습 출처를 관리한다. BentoML의 Model store는 서빙에 가져온 모델을, Bento는 그 모델을 사용하는 서비스 전체를 식별한다. 모델 버전이 같아도 피처 조회나 전처리 코드가 달라지면 다른 서비스가 된다. 따라서 모델 버전만으로 배포를 재현할 수는 없다.

책의 가져오기, 빌드, push와 배포는 같은 등록 작업을 반복하는 것이 아니다. 학습 결과를 서빙 모델로 가져오고, 그 모델을 사용하는 서비스를 패키지로 만들고, 실행할 위치에 전달한 뒤 요청 가능한 상태로 바꾸는 과정이다. 어느 저장소에 목록이 보이는지보다 지금 확인한 상태가 어디까지인지 구분해야 한다.

### 같은 모델 입력을 만들면서 요청 부하를 처리한다

API의 계약에는 JSON 필드와 타입뿐 아니라 의미도 들어간다. `user_id`가 문자열이라는 검사와 그 사용자에게 유효한 온라인 피처가 있다는 검사는 다르다. 응답의 확률, 클래스 번호와 소득 범주도 서로 구분해야 한다.

전처리는 학습 때의 의미를 유지해야 한다. 범주 인코딩, 결측 처리, 열 순서와 단위가 바뀌면 같은 모델에 다른 입력을 주게 된다. API가 정상 응답했는지와 학습과 같은 변환을 거쳤는지는 별도로 확인한다.

소득 분류의 단일 요청이 이 문제를 보여 준다. 배치에서는 여러 범주를 보고 원-핫 열을 만들 수 있지만 한 행에는 그 범주들이 모두 나타나지 않는다. 저자 코드의 `get_dummies(drop_first=True)`는 한 범주뿐인 열을 없앨 수 있고, 뒤에서 학습 열 목록으로 맞춰도 의미가 복원되지 않는다. 같은 사용자의 배치와 API 입력을 대조하고, 학습에서 fit한 인코더를 서비스에서도 재사용해야 한다.

Runner는 모델과 설정이 지원하면 여러 요청의 계산을 묶는 adaptive batching을 사용할 수 있다. 벡터화와 GPU 활용에는 유리하지만 묶음을 기다리는 시간이 더해지므로 처리량과 개별 요청 지연의 절충이 생긴다. 이 기능은 5장처럼 대상 파일 전체를 처리하는 배치 추론과 다르다. 책의 기본 소득 분류 서비스가 자동으로 적절한 배칭 정책까지 갖췄다는 뜻도 아니다.

### 빌드, 레지스트리와 Yatai의 책임

`bentofile.yaml`은 어떤 서비스와 파일, 모델, 의존성을 포함할지 선언한다. 빌드는 이 선언으로 Bento를 만드는 작업이고, push는 만들어진 산출물을 원격 저장소로 전달하는 작업이다. 패키지 저장과 서비스 실행은 다른 상태다.

책의 Yatai는 Kubernetes에서 Bento의 배포를 관리하는 제어 계층이다. 모델과 Bento의 관리, 이미지 빌드, API 서버와 Runner의 자원 및 복제본 설정, 서비스 노출을 연결한다. 실제 계산은 배포된 worker와 Pod가 수행한다. Yatai가 모델의 예측 품질이나 학습 데이터의 적합성을 판정하지는 않는다.

| 관리 대상 | 필요한 이유 |
| --- | --- |
| 모델 태그와 Bento 태그 | 무엇을 어떤 코드로 서비스했는지 구분 |
| 컨테이너 이미지와 의존성 | 다른 환경에서도 같은 실행 조건 구성 |
| CPU, 메모리, GPU와 복제본 | 모델 크기와 요청 부하에 맞는 실행 용량 |
| 준비 상태와 서비스 주소 | 모델 로드 전의 실행과 요청 가능한 상태 구분 |
| 배포 버전과 전환 기록 | 새 서비스의 문제를 추적하고 이전 구성으로 복구 |

API 복제본을 늘리는 것과 Runner 복제본을 늘리는 것은 같은 조정이 아니다. 모델을 여러 worker에 올리면 메모리 사용량도 증가한다. 전처리, 모델 계산, 저장소 중 어느 구간이 병목인지 측정한 뒤 자원을 조정해야 한다.

### 서비스 관측과 모델 관측

BentoML의 `/metrics`와 Prometheus 연계는 요청 수, 지연과 오류 같은 서비스 동작을 관찰하는 데 쓰인다. 메트릭을 노출하는 것, Prometheus가 수집하는 것, 대시보드와 알림을 만드는 것은 별도 구성이다.

요청이 빠르고 HTTP 200이 많아도 예측이 틀릴 수 있다. 반대로 모델 품질이 유지되어도 피처 조회 장애로 서비스를 쓰지 못할 수 있다. 그래서 이 장의 다음 주제인 데이터와 모델 관측을 인프라 관측과 구분한다.

## 요청이 정상이어도 입력과 예측 품질은 달라질 수 있다 {#drift-concepts}

배포 시점의 검증이 계속 유효하려면 현재 요청이 어떤 입력을 사용하는지 알아야 한다. 서버의 가용성과 지연은 실행 상태를 보여 주고, Evidently의 데이터 비교는 모델이 받는 입력의 변화를 보여 준다. 그 변화가 실제 품질에 영향을 주는지는 정답과 업무 기준으로 다시 판단한다.

### 입력, 정답과 예측의 변화

입력 피처를 `X`, 실제 정답을 `y`, 모델의 예측을 `y_hat`으로 두면 무엇이 바뀌었는지 나눠 볼 수 있다.

| 변화 | 달라지는 것 | 해석 |
| --- | --- | --- |
| Covariate shift | 입력 분포 `P(X)` | 직업이나 학력 구성이 달라짐. 엄밀한 구분에서는 `P(y\|X)`가 유지된다고 가정 |
| Label / prior shift | 정답 비율 `P(y)` | 소득 범주 비율이 달라짐. 엄밀한 label shift는 `P(X\|y)`의 안정성을 가정 |
| Concept drift | 입력과 정답의 관계 `P(y\|X)` | 같은 피처 조건에서도 소득 범주의 발생 관계가 달라짐 |
| Prediction drift | 예측 분포 `P(y_hat)` | 모델이 반환하는 범주나 확률의 구성이 달라짐 |

이 구분은 원인을 설명하는 틀이며, 운영에서는 여러 변화가 함께 발생할 수 있다. 입력 분포만 비교해서 concept drift를 확인했다고 할 수는 없다. 정답이 늦게 도착하는 서비스에서는 입력과 예측의 변화를 먼저 관찰하고, 정답이 모였을 때 실제 품질을 확인한다.

예를 들어 직업 분류를 수집하는 시스템이 바뀌어 특정 값이 대량으로 결측 처리되면 모델 재학습보다 수집 경로 복구가 우선일 수 있다. 반면 같은 직업과 학력에서도 소득 관계가 지속적으로 달라졌다면 모델과 피처의 재검토가 필요하다.

개별 요청이 특이한지를 보는 이상치 검사와 분포를 비교하는 드리프트 검사도 다르다. 한 사용자의 드문 직업은 이상치일 수 있지만 사용자 전체의 구성이 바뀌었다는 증거는 아니다.

### Reference와 current를 비교하는 방법

Evidently는 기준 데이터(reference)와 평가할 현재 데이터(current)를 받아 열별 변화와 요약을 계산한다. 기준은 학습 데이터일 수도 있고 검증된 정상 기간일 수도 있다. 어느 모델과 기간을 대표하는지에 따라 보고서의 의미가 달라진다.

학습 데이터를 기준으로 삼는 이유는 단순히 파일이 이미 있어서가 아니다. 선택한 모델이 어떤 입력 조건에서 평가됐는지를 현재 입력과 비교하려는 것이다. 그래서 4장의 데이터 출처 기록이 6장의 관측 입력으로 다시 쓰인다. 모델을 고르는 단계와 배포 뒤 살피는 단계가 같은 원천 run으로 연결된다.

열의 타입과 표본 수에 따라 비교 방법도 달라진다. 책의 예제와 같은 구버전 API의 선택 규칙은 [Evidently의 드리프트 알고리즘 문서](https://docs-old.evidentlyai.com/reference/data-drift-algorithm)에 정리되어 있다.

| 방법 | 비교하는 것 | 결과를 읽는 기준 |
| --- | --- | --- |
| Kolmogorov–Smirnov(KS) 검정 | 수치형 변수의 경험적 누적분포 차이 | p-value와 분포 차이의 크기를 함께 확인 |
| 카이제곱 검정 | 범주별 관측 빈도 차이 | 범주별 표본과 기대 빈도, p-value 확인 |
| Wasserstein distance | 한 수치 분포를 다른 분포로 옮기는 차이 | 거리, 정규화 방식, 임계치 확인 |
| Jensen–Shannon 계열 지표 | 범주별 확률분포 차이 | 거리나 발산의 정의, 적용한 임계치 확인 |
| PSI | 구간이나 범주별 비율의 변화 | 구간 정의와 비교 임계치 확인 |

![occupation 피처의 reference와 current 분포, 선택한 PSI 지표와 드리프트 판정을 함께 보여 주는 Evidently 보고서.](https://raw.githubusercontent.com/evidentlyai/evidently/49cce31eaa49ec354d32ccd2edb3c9d492949db1/docs/book/.gitbook/assets/reports/metric_data_drift_table_expand_1-min.png)

그림 6-2. 직업 피처의 분포와 검사 결과를 함께 보는 공식 보고서 예시. 출처: [Evidently 0.5.0 보고서 이미지](https://github.com/evidentlyai/evidently/blob/49cce31eaa49ec354d32ccd2edb3c9d492949db1/docs/book/.gitbook/assets/reports/metric_data_drift_table_expand_1-min.png), [Apache-2.0](https://github.com/evidentlyai/evidently/blob/49cce31eaa49ec354d32ccd2edb3c9d492949db1/LICENSE). 이 글의 실습 결과가 아닌 공식 예제다.

표본 수가 다르면 원시 건수로 그린 막대의 높이도 달라진다. 그림의 인상만으로 판정하지 말고 상대 비율과 선택한 검사, 임계치를 함께 확인한다. 화면의 PSI 값은 아래에서 설명하는 p-value와 같은 지표가 아니다.

p-value는 “드리프트가 발생했을 확률”이 아니다. 같은 분포라는 가정 아래 관측 차이가 얼마나 이례적인지를 해석하는 값이다. 표본이 매우 크면 작은 차이도 통계적으로 드러날 수 있고, 표본이 적으면 중요한 변화를 놓칠 수 있다.

거리 기반 값도 모델 정확도와 같은 지표는 아니다. 선택한 방법, 표본 수, 변화의 크기와 업무 영향을 함께 보고 임계치를 정해야 한다. 서로 다른 검사에서 나온 drift score를 같은 단위처럼 비교하지 않는다.

### 열별 검사와 데이터셋 수준 판정

열별 drift는 어떤 피처가 달라졌는지 보여 준다. 데이터셋 수준 판정은 그 결과를 묶어 “전체 입력을 변화한 것으로 볼 것인가”를 결정하는 규칙이다.

예를 들어 검사 열 8개 중 2개가 변하면 변한 열의 비율은 0.25다. 이것은 예측의 25%가 틀렸다는 뜻이 아니다. 변한 두 열이 모델에 중요한지와 변화가 어느 사용자 집단에 집중되는지도 확인해야 한다.

각 열의 분포가 비슷해도 열 사이의 관계는 바뀔 수 있다. 열별 검사만으로 모든 다변량 변화를 포착하지는 못한다. 많은 열을 반복 검사하면 우연한 경고도 늘어날 수 있으므로 경고의 지속성과 재현 여부를 함께 본다.

결측률과 스키마는 분포 검사와 별도로 다룬다. 결측값을 제외하고 분포를 비교하는 검사에서는 결측 급증을 놓칠 수 있다. 원본이 `DatasetMissingValuesMetric`과 `ColumnSummaryMetric`을 drift metric과 함께 넣는 이유다.

### Metric, Report, Test와 대시보드

| 구성 | 역할 | 그 자체로 하지 않는 것 |
| --- | --- | --- |
| Metric | 결측 비율, 분포 차이, 모델 오차 등의 값 계산 | 모든 지표에 업무상 합격 기준 부여 |
| Report | 선택한 지표와 시각화 결과를 묶음 | 파이프라인이나 API를 자동 차단 |
| Test / Test Suite | 지정한 조건에 대한 통과나 실패 판정 | 재학습과 출시 승인 정책 전체 구현 |
| Workspace / Project | 보고서와 실행 구간을 모아 관리 | 기준 데이터의 적합성 자동 결정 |
| Dashboard | 기간별 지표와 변화 추세 표시 | 원인 분석과 서비스 유지 판단 대체 |

정답이 있으면 문제 유형에 맞는 분류나 회귀 성능도 계산할 수 있지만, 입력만 있는 보고서가 정확도를 새로 알아내는 것은 아니다. 보고서를 만든 뒤 경고, 처리 보류나 추가 평가로 연결하는 정책은 별도로 정해야 한다. 뒤의 D-2에서는 이 구분을 저자의 실제 코드와 대조한다.

### 배치, 마이크로배치와 슬라이딩 윈도우

배치에서는 처리할 묶음 자체가 current가 된다. API는 요청 하나가 표본 하나에 가까우므로 여러 입력을 모아 비교한다.

| 비교 단위 | 특징 | 정할 것 |
| --- | --- | --- |
| 배치 | 파일이나 대상 기간 단위로 비교 | 같은 대상의 재실행, 검사 후 추론 정책 |
| 고정 윈도우 | 고정된 시간이나 건수로 나눈 겹치지 않는 묶음 | 보고서 간격, 트래픽이 적을 때의 최소 표본 |
| 슬라이딩 윈도우 | 최근 표본을 유지하며 반복 비교 | 윈도우 크기, 검사 간격과 겹침 |

작은 윈도우는 빠르게 반응하지만 변동이 크고, 큰 윈도우는 안정적이지만 변화 발견이 늦을 수 있다. 요일과 시간대의 정상적인 변화를 서로 다른 기준과 비교하면 경고가 반복될 수 있다. 겹치는 윈도우의 연속 경고도 독립된 여러 사건처럼 세지 않는다.

책의 그림 6.21에서는 크기 50의 API 윈도우로 검사했을 때 `share_of_drifted_columns`가 약 0.875로 나온다. 이는 검사한 열 중 약 87.5%가 설정된 변화 조건을 넘었다는 뜻이지 예측의 87.5%가 틀렸다는 뜻이 아니다. 책에서도 학습 데이터에서 가져온 사용자로 요청했는데 이런 결과가 나온 점을 작은 표본과 연결해 설명한다.

같은 원천에서 가져왔어도 작은 현재 표본이 전체 기준 분포를 그대로 대표하지는 않는다. 따라서 이 화면은 운영 환경이 실제로 변했다는 증거보다 윈도우와 비교 조건을 검토해야 할 사례로 읽는 편이 맞다. 충분한 표본, 사용자 선택 방식과 실제 분포를 확인한 뒤 검사 방법과 경고 조건을 조정해야 한다. 경고를 없애려고 임계치만 높이는 것과는 다르다.

새로운 current를 매번 reference로 교체하면 지속적인 변화를 정상으로 흡수할 수 있다. 기준을 고정할지 갱신할지, 갱신 전에 무엇을 검증할지도 관측 설계의 일부다.

## 서빙 인프라에서 드리프트를 다루는 방식 {#production-monitoring}

비교 원리를 알았다면 남는 문제는 현재 표본을 어디서 모으고 언제 검사할지이다. 한 요청의 입력 유효성은 실행 전에 확인할 수 있지만 분포 변화는 여러 표본과 적절한 기준이 있어야 해석할 수 있다. 관측 데이터를 수집하는 경로와 예측을 반환하는 경로를 나누는 이유이다.

### 추론 경로와 관측 경로를 나눈다

실시간으로 예측하는 서비스라도 통계 검사를 요청마다 실행할 필요는 없다. [Evidently의 모니터링 구조](https://docs-old.evidentlyai.com/user-guide/monitoring/monitoring_overview)는 온라인 추론을 로그로 남긴 뒤 별도 작업에서 평가하는 방식과, collector가 입력을 모아 계산하는 방식을 구분한다. [Azure ML 모델 모니터링](https://learn.microsoft.com/en-us/azure/machine-learning/concept-model-monitoring?view=azureml-api-2)도 추론 데이터 수집과 정해진 주기의 모니터링 작업을 분리한다.

공통점은 **사용자가 기다리는 예측 경로와 여러 표본을 비교하는 관측 경로의 책임을 나누는 것**이다. 모든 시스템이 같은 주기나 제품을 사용한다는 뜻은 아니다.

```mermaid
flowchart TD
    accTitle: 예측 응답과 드리프트 평가를 분리한 운영 참조 구조
    accDescr: API는 피처 조회와 입력 검사를 거쳐 예측을 응답한다. 실제 사용한 피처와 예측의 관측 기록은 별도 수집 경로로 보내 저장한다. 모니터링 작업은 버전이 맞는 기준 데이터와 현재 윈도우를 비교하고 지표와 경고를 만든다. 늦게 도착한 정답은 예측 ID로 연결해 성능을 평가한다.
    C["클라이언트"] --> API["API와 피처 조회"]
    API --> V["요청 단위 입력 검사"]
    V --> M["모델 추론"]
    M --> R["응답"]
    R --> C
    API -.-> E["관측 기록<br/>실제 피처, 예측, 버전, 시각"]
    M -.-> E
    E --> COL["수집기 또는 이벤트와 로그 경로"]
    COL --> STORE[("추론 데이터 저장소")]
    STORE --> JOB["별도 모니터링 작업<br/>스케줄 또는 윈도우 트리거"]
    REF[("모델에 대응하는 기준 데이터")] --> JOB
    JOB --> MET["지표, 보고서, 경고"]
    LABEL["나중에 도착한 정답"] --> JOIN["예측 ID로 연결"]
    STORE --> JOIN
    JOIN --> PERF["실제 모델 성능 평가"]
    PERF --> MET
    MET --> TRIAGE["원인과 영향 조사, 대응 결정"]
```

점선은 서비스가 관측용 기록을 남긴다는 관계이며, 수집 자체가 무조건 지연이나 실패 없이 끝난다는 뜻은 아니다. collector 전송을 동기 호출하면 그 시간과 실패도 요청 경로에 영향을 줄 수 있다. 비동기 전송, 버퍼나 별도 로그 경로를 택하더라도 메모리 한도, 재시도, 누락과 밀린 기록의 처리가 필요하다.

관측 시스템이 일시적으로 중단됐을 때 예측을 계속할지, 기록이 반드시 남아야 하므로 요청도 제한할지는 서비스 요구사항으로 정한다. 단순히 보고서 계산 실패를 예측 실패로 전파하는 것과 의도적으로 정한 정책은 다르다.

### 어디에서 무엇을 수집하는가

이 책의 `/predict`는 `user_id`만 받는다. HTTP 요청과 응답만 저장하면 사용자 ID와 소득 범주는 남지만, 실제 모델이 본 학력과 직업 등의 분포는 알 수 없다.

따라서 피처 조회 후의 값, 필요하다면 전처리 후의 모델 입력을 관측 대상으로 삼아야 한다. 나중에 같은 사용자 ID로 Redis를 다시 조회하면 값이 바뀌어 있을 수 있으므로 당시 입력을 재구성한 것이 되지 않는다. [Azure ML 데이터 수집 문서](https://learn.microsoft.com/en-us/azure/machine-learning/concept-data-collection?view=azureml-api-2)도 HTTP payload logging과 전처리 전, 처리 중, 처리 후의 데이터를 남기는 custom logging을 구분한다.

| 관측 지점 | 알 수 있는 것 | 기준 데이터와 맞출 것 |
| --- | --- | --- |
| 외부 요청 | 입력 규격, 요청 대상과 오류 | API 계약 |
| Feast 조회 직후 | 실제 사용한 피처, 결측과 최신성 | 같은 피처 정의와 시점 의미의 reference |
| 전처리 직후 | 인코딩, 스케일과 모델 입력 형태 | 같은 전처리 버전의 입력 표현 |
| 모델 출력 | 범주나 확률의 분포, 모델 동작 | 같은 모델 버전의 비교 가능한 예측 |
| 실제 결과 도착 후 | 예측 오차와 집단별 품질 | 예측과 연결되는 정답과 평가 기간 |

다음은 특정 플랫폼의 필수 형식이 아니라 관측 기록에 담을 항목의 예다.

| 항목 | 필요한 이유 |
| --- | --- |
| `prediction_id`, 예측 시각 | 요청, 응답, 늦게 도착한 결과 연결 |
| 모델 버전과 배포 버전 | 트래픽 분할이나 모델 교체의 영향 구분 |
| 피처 정의, 전처리, 스키마 버전 | 서로 다른 의미의 값을 같은 분포로 섞지 않기 위해 |
| 선택한 피처와 예측값 | 분포, 결측과 예측 변화 계산 |
| 피처 시각과 조회 상태 | 오래된 피처, 조회 실패와 실제 값 변화 구분 |
| 표본 추출 조건과 데이터 구간 | 전체 트래픽을 얼마나 대표하는지 해석 |

사용자 ID는 한 사람의 여러 예측에서 반복되므로 예측 사건의 고유 ID를 대신하지 못한다. 원문 전체를 저장해야만 관측이 가능한 것도 아니다. 허용된 피처와 보존 범위를 정하고, 표본 추출을 쓴다면 특정 집단이나 실패 요청이 빠지는지 함께 확인한다.

### 요청 안에서 하는 검사와 밖에서 하는 검사

| 검사 | 실행 위치의 예 | 실패의 의미 |
| --- | --- | --- |
| 필수 필드, 타입, 크기 검사 | API 요청 경로 | 이 요청이 계약을 위반함 |
| 피처 누락, 허용 범위, 최신성 검사 | 피처 조회 후, 추론 전 | 유효한 모델 입력을 만들지 못함 |
| 입력과 예측 분포 비교 | 별도 배치 작업 또는 collector의 윈도우 | 입력 집단이나 모델 동작이 기준과 달라짐 |
| 정답 기반 품질 평가 | 결과가 모인 뒤 별도 작업 | 실제 예측 품질이 평가 기준과 다름 |
| 배치 데이터 품질 게이트 | 배치 추론 파이프라인 내부 | 해당 묶음의 후속 처리를 보류할 조건 |

필수 피처가 없는 요청을 거절하는 것과 “최근 사용자 구성에 변화가 있다”는 이유로 모든 요청을 거절하는 것은 다른 정책이다. 분포 경고가 개별 요청의 잘못을 증명하지는 않는다.

빠른 탐지가 필요하면 [Evidently collector 구조](https://docs-old.evidentlyai.com/user-guide/monitoring/collector_service)처럼 별도 서비스가 건수나 시간 조건으로 윈도우를 모아 계산할 수 있다. 온라인 추론이라는 이유만으로 각 API worker가 보고서 전체를 계산해야 하는 것은 아니다. 반대로 배치 작업에서는 명시적인 품질 검사 결과에 따라 다음 단계를 중단하는 구성이 유효하다.

![ML 서비스가 입력과 예측을 별도 collector에 보내고, collector가 검사 결과를 snapshot으로 저장해 대시보드에 전달하는 구조.](https://raw.githubusercontent.com/evidentlyai/evidently/49cce31eaa49ec354d32ccd2edb3c9d492949db1/docs/book/.gitbook/assets/monitoring/monitoring_collector_min.png)

그림 6-3. 추론 서비스와 collector를 분리한 관측 구조. 출처: [Evidently collector 공식 문서](https://docs-old.evidentlyai.com/user-guide/monitoring/collector_service), [원본 이미지](https://github.com/evidentlyai/evidently/blob/49cce31eaa49ec354d32ccd2edb3c9d492949db1/docs/book/.gitbook/assets/monitoring/monitoring_collector_min.png), [Apache-2.0](https://github.com/evidentlyai/evidently/blob/49cce31eaa49ec354d32ccd2edb3c9d492949db1/LICENSE). 원본 도식을 변경 없이 사용했다.

POST는 수집 지점으로 데이터를 보내는 동작이고, 보고서를 계산하는 작업은 collector의 트리거를 따른다. 그림처럼 역할을 나눠도 전송 지연과 누락을 어떻게 처리할지는 서비스에서 정해야 한다.

### 모니터링 작업 자체의 입력과 상태

모니터링 작업에는 기준 버전, 현재 데이터 구간, 검사할 열, 비교 방법, 최소 표본과 경고 조건이 필요하다. 모델이 교체됐는데 이전 모델의 전처리와 예측 기준을 새 결과와 섞으면 배포 차이를 데이터 변화로 오해할 수 있다.

| 설계 항목 | 판단할 내용 |
| --- | --- |
| 주기와 윈도우 | 얼마나 빨리 알아야 하는지, 그동안 충분한 표본이 쌓이는지 |
| 지연 도착 | 예측 시각과 수집 시각 중 어떤 시간으로 묶고 얼마나 기다릴지 |
| 집단과 버전 | 모델, 지역, 사용자 유형별 변화가 전체 평균에 가려지는지 |
| 기준 갱신 | 정상으로 검증한 새 기준인지, 단순히 최근 자료로 덮어쓰는 것인지 |
| 경고의 지속 조건 | 한 번의 변동과 반복되는 변화를 어떻게 구분할지 |
| 수집과 작업 상태 | 누락, 처리 지연, 마지막 성공 시각과 실제 평가 행 수 |

표본이 없거나 너무 적으면 “드리프트 없음”보다 “평가할 자료 부족”으로 표현해야 한다. 수집이 멈췄는데 마지막 정상 보고서만 계속 보여 주면 서비스가 안정적이라는 잘못된 인상을 줄 수 있다.

Prometheus에는 요청 수, 지연, 수집 오류, 작업 성공 시각과 같은 운영 지표를 내보낼 수 있다. 요청별 피처, 사용자 ID, 예측 ID를 모두 시계열 label로 넣는 방식은 다른 문제다. [Prometheus의 계측 지침](https://prometheus.io/docs/practices/instrumentation/)도 label 조합이 늘 때의 비용을 설명한다. 개별 예측 기록은 평가용 저장소에서, 집계된 운영 상태는 메트릭에서 다루는 역할 구분이 필요하다.

### 정답은 나중에 연결할 수 있어야 한다

입력 drift와 prediction drift는 정답 없이 계산할 수 있지만 정확도와 오차는 실제 결과가 있어야 계산할 수 있다. [Evidently의 지연 정답 처리](https://docs-old.evidentlyai.com/user-guide/monitoring/batch_monitoring)는 입력 검사, 예측 변화, 정답 도착 후 성능 평가를 별도로 수행하는 흐름을 설명한다.

예측 ID와 모델 버전을 기준으로 결과를 연결하고, 결과가 충분히 도착한 예측 구간을 평가한다. 정답이 있는 일부 사례의 품질을 전체 트래픽의 품질로 바로 해석하지 말고 라벨 도착률과 평가 대상도 함께 남긴다. 이 소득 분류 예제에 `/predict`가 있다는 사실만으로 실제 소득 정답까지 수집되는 것은 아니다.

### 경고에서 대응으로 넘어가는 과정

드리프트 경고는 조사할 근거이지 새 모델의 배포 승인 신호가 아니다. [Evidently의 대응 지침](https://www.evidentlyai.com/blog/ml-monitoring-data-drift-how-to-handle)도 수집과 품질 오류를 먼저 확인하고, 변화의 의미에 따라 유지, 재학습, 재보정을 구분한다.

| 조사 결과 | 대응 방향 |
| --- | --- |
| 로그 누락이나 collector 장애로 집단 비율이 달라짐 | 수집 경로 복구와 해당 구간 재평가 |
| Feast 정의 변경 뒤 특정 피처가 결측으로 바뀜 | 피처와 변환 경로 수정, 잘못된 입력의 처리 정책 적용 |
| 계절성이나 알려진 사용자 구성 변화, 품질 유지 | 세부 집단 확인과 관측 지속, 필요하면 기준과 경고 조건 검토 |
| 새로운 집단에서 지속적인 품질 저하 | 필요한 라벨과 데이터 확보, 후보 재학습과 같은 조건의 평가 |
| 새 배포 뒤 오류나 잘못된 전처리가 증가 | 해당 배포 조사, 호환되는 이전 구성으로 복구 검토 |

재학습을 자동으로 시작할 수는 있지만, 새 데이터의 검증과 기존 모델 대비 평가, 서비스 제약 확인, 배포 전환은 서로 다른 판단이다. 어떤 단계까지 자동화할지 정하지 않고 경고가 날 때마다 최신 모델을 바꾸면 데이터 오류를 학습하거나 더 나쁜 모델로 전환할 수 있다.

정답을 빠르고 신뢰할 수 있게 얻는 서비스라면 실제 품질을 주된 경고 신호로 삼고 드리프트는 진단에 활용할 수도 있다. [Evidently도 드리프트 관측이 항상 필수인 것은 아니라고 설명](https://www.evidentlyai.com/blog/ml-monitoring-do-i-need-data-drift)한다. 모델과 업무에 맞는 증거가 무엇인지가 도구의 수보다 중요하다.

### 같은 검사를 배치와 API에서 다르게 연결하는 이유

5장의 배치에는 이미 처리 대상 묶음이 있다. 조회한 피처를 current로 삼고 모델의 원천 run에서 reference를 가져오면 추론 전에 비교할 수 있다. 책의 6.2.2는 이 위치에 검사 컴포넌트를 넣고 드리프트가 있으면 중단한다는 의도를 설명한다.

다만 고정한 저자 코드의 `detect_drift.py`는 보고서를 만들고 올릴 뿐 변화 판정을 읽어 차단하는 분기를 구현하지 않는다. `.after(detect_drift_task)`는 선행 작업의 완료 의존성이다. **책이 설명한 품질 게이트와 저장소가 구현한 보고서 생성은 다른 상태**이므로, 읽으면서 추론이 왜 계속되는지 혼동하지 않아야 한다. 중단하려면 판정 출력과 조건 분기 또는 명시적인 실패 정책이 추가로 필요하다.

API에서는 한 요청이 비교할 분포가 되지 못하므로 여러 입력을 윈도우로 모은다. 책의 6.2.3은 API 프로세스 안에서 최근 표본을 유지하고 윈도우가 찬 뒤 새 요청마다 보고서를 다시 만드는 경로를 보여 준다. 윈도우 크기는 한 번에 비교하는 표본 수이고, 검사 간격은 계산을 반복하는 주기다. 두 값은 같지 않다.

이 직접적인 예제는 원리를 보여 주지만 여러 worker의 상태 공유, 재시작과 수집 누락까지 해결하지는 않는다. 요청 경로 안의 보고서 계산은 응답 지연에도 영향을 준다. 운영에서는 앞에서 본 별도 관측 경로로 표본을 모으고 적절한 주기에 평가하는 구성을 검토한다. 온라인 예측이 필요하다는 것과 모든 통계 계산이 요청 안에서 끝나야 한다는 것은 다른 요구다.

결국 두 예제가 공유하는 것은 비교 원리이고, 다른 것은 current를 모으는 단위와 검사 결과를 실행에 연결하는 위치다. [7장의 데이터 계약](../07-data-preparation/#training-serving-contract)에서 다룰 스키마, 전처리, 데이터 버전은 두 경우 모두 비교 대상이 같은 의미의 입력이게 만드는 기반이다.

6장의 변화는 모델 파일을 서비스에 올린 것만이 아니다. 요청, 피처, 전처리와 모델 버전을 하나의 실행으로 묶고, 배포 뒤에는 서비스 상태와 입력 변화, 정답 기반 품질을 다른 증거로 확인하는 구조가 됐다. 다음 장에서 데이터 준비로 돌아가는 이유도 이 계약을 신분증 탐지와 영화 추천이라는 다른 문제에 처음부터 세우기 위해서다.

## 실습 순서 {#book-ch06-sop}

6장의 실습은 4~5장에서 만든 모델과 피처를 그대로 쓴다. 학습을 다시 하는 장이 아니라 **등록된 모델을 요청 기반 API로 옮기고, 그 API와 배치 파이프라인의 입력을 관측하는 장**이다. 그래서 MLflow의 Production 모델과 Redis의 온라인 피처가 준비되어 있는지부터 확인한다.

아래 절차는 2026년 11월 Windows 11 PowerShell에서 [저자의 chapter-6 코드](https://github.com/practical-mlops/chapter-6/tree/890db04409cb3f48c4e493470d79095ec6ab63d6)를 [4~5장 실습](../04-experiments-features-pipelines/#book-lab-sop)과 같은 kind 클러스터에 붙여 실제로 실행한 기록이다. 그대로 동작하지 않은 부분은 원인과 고친 내용을 해당 단계에 적었다.

```mermaid
flowchart LR
    accTitle: 책 6장을 따라가는 실습 순서
    accDescr: 앞 장의 모델과 피처를 확인한 뒤 MLflow 모델을 BentoML로 가져와 로컬 API를 실행한다. Bento를 빌드해 컨테이너와 클러스터에 배포하고, Evidently로 배치 파이프라인과 API 입력의 드리프트를 확인한 뒤 결과를 해석하고 정리한다.
    A["A. 앞 장 산출물<br/>모델과 피처 확인"] --> B["B. BentoML<br/>로컬 API"]
    B --> C["C. Bento 빌드와<br/>클러스터 배포"]
    C --> D["D. Evidently<br/>드리프트 관측"]
    D --> E["E. 결과 해석과 정리"]
```

| 구간 | 끝났을 때 남는 것 |
| --- | --- |
| A. 앞 장 산출물 | `random-forest-classifier` v1의 Production 지정, 원천 run의 `column_list.pkl`과 입력 기록, Redis의 온라인 피처, 6장 저자 코드와 Python 3.10 가상환경 |
| B. 로컬 API | BentoML 모델 저장소의 `random-forest-classifier`, `http://127.0.0.1:3000/predict`의 실제 응답 |
| C. 배포 | Bento `income_classifier_service`, 컨테이너 이미지, kind의 `ch06-serving` 배포, Yatai에 push한 모델과 Bento |
| D. 드리프트 | Evidently workspace, 드리프트 검사를 넣은 KFP 실행, 보고서와 대시보드 |
| E. 결과 확인 | 성공 조건별 확인 결과와 정리 명령 |

명령은 [4~5장 실습](../04-experiments-features-pipelines/#book-lab-sop)과 같이 `ml-platform-book-env` 저장소 최상위 폴더를 기준으로 한다. 6장 코드는 `upstream\chapter-6`에 받으며, `cd`가 있는 단계만 작업 위치가 달라진다. 터미널은 세 개를 쓴다. **터미널 1**은 `python bookenv.py forward`를 계속 켜 두는 창, **터미널 2**는 BentoML 서비스를 실행하는 창, **터미널 3**은 나머지 명령을 실행하는 창이다.

## A. 앞 장의 산출물 준비와 확인

지금 위치: [전체 그림](#platform-map)의 ①~④. 4장의 노트북이 MLflow, S3, Feast Registry와 Redis를 채우는 구간이다.

### A-1. 클러스터와 포트포워딩

1. [4~5장 실습](../04-experiments-features-pipelines/#book-lab-sop)의 A-2 클러스터 설치와 A-3 포트포워딩을 마친다. 터미널 1에서 다음을 켜 둔다.
   ```powershell
   python bookenv.py forward
   ```
2. 버킷이 없다면 만든다. 이미 있으면 그대로 두며, 다시 실행해도 결과는 같다.
   ```powershell
   python bookenv.py buckets
   ```

새 클러스터에서 시작했다면 B와 C의 확인 화면은 모두 비어 있다. 6장에서 필요한 상태는 아래 A-2를 끝내야 생긴다.

### A-2. 4장 노트북과 5장 Registry 다시 만들기

클러스터를 새로 만들었다면 4장의 두 노트북과 5장의 클러스터용 Registry 준비를 다시 실행한다. 이미 4~5장 실습을 끝낸 클러스터라면 A-3으로 넘어간다.

1. JupyterLab에서 `ch04/01_mlflow_tracking.ipynb`를 처음부터 끝까지 실행한다. 마지막 두 셀의 출력이 다음과 같으면 된다. run 이름과 ID는 실행마다 다르다.
   ```text
   powerful-kit-773 0.8480364138495673 random-forest-classifier 1
   1 Production 8015f99a55f1487796aaa6382af8ad0e
   ```
2. `ch04/02_feast_feature_store.ipynb`를 처음부터 끝까지 실행한다. `feast apply`에서 `Deploying infrastructure` 세 줄, `materialize`에서 `Materializing 3 feature views`, 마지막 셀에서 `['feature_store.yaml', 'registry_local.db']`가 나오면 된다.
3. 5장의 클러스터용 Registry와 입력 파일을 준비한다. 4~5장 실습의 D-1부터 D-4까지와 같은 명령이다.
   ```powershell
   python book/ch05/prepare.py
   python bookenv.py load book-ch5/feast-job:0.1
   python bookenv.py load book-ch5/components:0.1
   kubectl apply -f book/ch05/feast-job.yaml
   kubectl -n kubeflow wait --for=condition=complete --timeout=300s job/feast-job
   python book/ch05/upload_inputs.py
   ```
   마지막 출력에 `feature-registry ['feature_store.yaml', 'feature_store_k8s.yaml', 'registry.db', 'registry_local.db']`가 보이면 된다.

같은 폴더에서 Feast 노트북을 두 번째로 실행했을 때 `feast apply`가 `Feature view demographic does not exist`로 실패했다. 앞선 실행이 `feature_repo`에 복사한 `retrieve_features.py`와 `retrieve_online_features.py`를 `feast apply`가 정의 파일로 import하면서, 아직 등록되지 않은 FeatureView를 조회했기 때문이다. 두 파일을 지우고 다시 실행하면 된다. 두 파일은 노트북의 뒤쪽 셀이 다시 복사한다.

```powershell
Remove-Item book/ch04/feature_repo/retrieve_features.py, book/ch04/feature_repo/retrieve_online_features.py
```

### A-3. MLflow에서 모델과 원천 run 확인

6장의 서비스는 MLflow에서 두 가지를 다시 찾는다. 모델 파일은 BentoML로 가져오고, 같은 버전의 원천 run에서는 `column_list.pkl`과 기준 데이터 기록을 읽는다.

1. http://localhost:5000 에서 **Models → random-forest-classifier → Version 1**을 연다. Stage가 `Production`이고 Source Run이 연결되어 있는지 확인한다.

   ![Production으로 지정한 random-forest-classifier 버전 1.](/images/ml-platform-engineering/sop/ch06-a-mlflow-model-version.png)

2. **Source Run**을 눌러 원천 run을 연다. **Datasets used**에 입력 기록이 세 개(training과 +2) 있고, Registered models에 `random-forest-classifier v1`이 보이면 된다.

   ![모델 버전의 원천 run과 입력 기록.](/images/ml-platform-engineering/sop/ch06-a-mlflow-source-run.png)

3. **Artifacts** 탭에서 `column_list.pkl`을 확인한다. 경로가 `s3://mlflow-artifacts/...`이므로 이 파일을 받는 쪽은 S3 접속 정보도 필요하다.

   ![원천 run의 column_list.pkl.](/images/ml-platform-engineering/sop/ch06-a-mlflow-artifacts.png)

4. 드리프트 비교에 쓸 기준 데이터의 위치를 API로 확인한다.
   ```powershell
   $mv = Invoke-RestMethod "http://127.0.0.1:5000/api/2.0/mlflow/model-versions/search?filter=name%3D'random-forest-classifier'"
   $run = (Invoke-RestMethod "http://127.0.0.1:5000/api/2.0/mlflow/runs/get?run_id=$($mv.model_versions[0].run_id)").run
   $run.inputs.dataset_inputs | ForEach-Object { $_.tags.value + ' :: ' + $_.dataset.source }
   ```
   ```text
   training :: {"uri": "mlflow-datasets/income-classifier-datasets/train-93b1a894054240b1b3e89f4d24949408.csv"}
   testing :: {"uri": "mlflow-datasets/income-classifier-datasets/test-93b1a894054240b1b3e89f4d24949408.csv"}
   reference_features :: {"uri": "mlflow-datasets/income-classifier-datasets/feature_df-93b1a894054240b1b3e89f4d24949408.csv"}
   ```

여기서 두 가지를 볼 수 있다. 첫째, 모델 버전의 `source`는 run의 아티팩트 경로가 아니라 `models:/m-...`이다. MLflow 3은 `log_model()`의 결과를 run과 별개인 LoggedModel로 저장하므로, 원천 run은 모델 버전의 `run_id`로 찾아야 한다. 저자 코드도 `run_id`를 쓰므로 그대로 동작한다.

둘째, Random Forest run의 입력 기록이 앞선 Decision Tree run(`93b1a...`)의 파일을 가리킨다. 노트북은 Random Forest run에서 `feature_df`를 기록할 때 `source`에 테스트 CSV 경로를 넣었지만, MLflow는 같은 내용(같은 digest)의 데이터셋을 이미 기록된 항목으로 재사용했다. 그래서 `reference_features`의 실제 위치는 첫 run이 올린 `feature_df` CSV가 됐다. 이번에는 원-핫 인코딩 전 범주형 열이 그대로 담긴 파일이라 드리프트 비교에 쓸 수 있지만, 입력 기록의 경로는 기록 방식에 따라 기대와 다를 수 있으므로 위처럼 실제 값을 확인해야 한다.

### A-4. 저자 코드와 Python 3.10 가상환경

1. 저자 코드를 받는다.
   ```powershell
   git clone https://github.com/practical-mlops/chapter-6.git upstream\chapter-6
   git -C upstream\chapter-6 checkout 890db04409cb3f48c4e493470d79095ec6ab63d6
   ```
2. BentoML 1.1.10은 저자 README대로 Python 3.10에서 실행한다. 4~5장의 `.venv-book`(Python 3.11, MLflow 3.0.0)과 섞지 않도록 6장 전용 환경을 만든다.
   ```powershell
   uv venv .venv-ch06 --python 3.10
   uv pip install --python .venv-ch06 "bentoml==1.1.10" -r upstream\chapter-6\bentoml\requirements.txt "setuptools<70" "click==8.1.7" "scikit-learn==1.5.2"
   .\.venv-ch06\Scripts\Activate.ps1
   ```
3. 버전을 확인한다.
   ```powershell
   python -c "import bentoml, mlflow, feast, sklearn; print(bentoml.__version__, mlflow.__version__, feast.__version__, sklearn.__version__)"
   ```
   ```text
   1.1.10 3.0.0 0.40.1 1.5.2
   ```

추가로 고정한 세 패키지는 모두 실제 오류 때문이다.

| 고정 | 고정하지 않았을 때 본 오류 | 이유 |
| --- | --- | --- |
| `setuptools<70` | `import bentoml`에서 `No module named 'pkg_resources'` | BentoML 1.1.10이 쓰는 `fs` 패키지가 최신 setuptools에서 빠진 `pkg_resources`를 import |
| `click==8.1.7` | `bentoml containerize`에서 `NotImplementedError` | click 8.2 이후의 옵션 처리 변경을 BentoML 1.1.10이 지원하지 않음 |
| `scikit-learn==1.5.2` | 정상 동작하지만 버전 불일치 경고 | 4장에서 모델을 저장한 scikit-learn과 맞춤 |

의존성 파일도 하나가 아니다. 기본 서비스의 `requirements.txt`는 MLflow 3.0.0, 드리프트 서비스의 `requirements_with_drift.txt`는 MLflow 2.7.0과 Evidently 0.5.0을 지정한다. D-4에서는 별도 가상환경을 만든다.

## B. MLflow 모델을 BentoML API로

지금 위치: 전체 그림의 ⑤와 ⑩~⑬. MLflow의 모델을 BentoML 모델 저장소로 가져오고, PC에서 API를 실행해 요청 하나가 Redis 조회와 Runner 예측을 거치는지 확인한다.

### B-1. 모델 가져오기

터미널 3에서 6장 가상환경을 활성화하고 실행한다.

```powershell
cd upstream\chapter-6\bentoml
python .\scripts\download_model.py
bentoml models list
```

```text
 Tag                            Module          Size       Creation Time
 random-forest-classifier:zv2…  bentoml.mlflow  37.00 MiB  2026-11-07 19:48:44
```

목록에서는 태그가 줄여 표시되며, 전체 태그는 `zv2wqy62tcgfhlaz`였다. `download_model.py`는 `models:/random-forest-classifier/Production`을 내려받아 BentoML 모델 저장소(기본 위치 `~\bentoml\models`)에 새 태그로 저장한다. MLflow의 버전 번호 `1`과 BentoML 태그 `zv2wqy62tcgfhlaz`는 서로 다른 식별자다. 둘을 함께 기록해 두어야 나중에 어느 학습 결과를 서비스했는지 거꾸로 찾을 수 있다.

MLflow 3에서 stage는 deprecated이지만 조회는 여전히 동작했다. 운영에서는 stage나 alias 대신 `models:/random-forest-classifier/1`처럼 구체 버전으로 가져오는 편이 안전하다.

### B-2. 설정 파일 맞추기

저자의 `.env`는 컨테이너에서 PC의 포트포워딩에 접속하는 `host.docker.internal`과 저자 환경의 Redis 비밀번호를 담고 있다. 이 환경에서 PC의 Python으로 실행하려면 두 가지를 바꾼다.

```powershell
(Get-Content .env) -replace 'host\.docker\.internal','localhost' -replace '^FEAST_REDIS_PASSWORD=.*','FEAST_REDIS_PASSWORD=redis123' | Set-Content .env
```

`production.env`는 C-3에서 Pod 안에서 쓸 설정이다. 저자 파일의 `MLFLOW_HOST`에는 `http://`가 빠져 있고, Feast 설정은 4장의 localhost용 파일을 가리킨다. 5장에서 올린 클러스터용 파일로 바꾼다.

```powershell
(Get-Content production.env) `
  -replace '^MLFLOW_HOST=.*','MLFLOW_HOST=http://mlflow-service.mlflow.svc.cluster.local:5000' `
  -replace '^FEAST_REDIS_PASSWORD=.*','FEAST_REDIS_PASSWORD=redis123' `
  -replace '^FEATURE_REGSITRY_FILE_NAME=.*','FEATURE_REGSITRY_FILE_NAME=feature_store_k8s.yaml' `
  -replace '^EVIDENTLY_WORKSPACE_URL=.*','EVIDENTLY_WORKSPACE_URL=http://evidently-service-internal.evidently.svc.cluster.local:8000' |
  Set-Content production.env
```

| 설정 | `.env` (PC에서 실행) | `production.env` (Pod에서 실행) |
| --- | --- | --- |
| `MLFLOW_HOST` | `http://localhost:5000` | `http://mlflow-service.mlflow.svc.cluster.local:5000` |
| `MINIO_HOST` | `localhost:9000` | `minio-service.kubeflow.svc.cluster.local:9000` |
| `FEAST_REDIS_HOST` | `localhost` | `redis-deployment-master.redis.svc.cluster.local` |
| `FEATURE_REGSITRY_FILE_NAME` | `feature_store.yaml` | `feature_store_k8s.yaml` |
| `FEAST_REDIS_PASSWORD` | `redis123` | `redis123` |

`src\constants.py`는 `ENV_NAME=production`일 때만 `production.env`를 읽는다. 설정 키 `FEATURE_REGSITRY_FILE_NAME`의 철자는 소스가 쓰는 그대로 둔다.

### B-3. 로컬 서비스 실행과 요청

기본 서비스의 진입점은 `service:svc`다. 요청 하나는 다음 순서로 처리된다.

```mermaid
sequenceDiagram
    accTitle: 소득 분류 API의 사용자 조회와 예측
    accDescr: 서비스 초기화에서 열 목록과 Feast를 준비한다. 요청마다 온라인 피처를 조회하고 학습 입력 열로 변환한 뒤 Runner를 호출한다. 응답은 소득 범주와 요청한 사용자 ID를 담는다.
    participant C as 요청자
    participant S as BentoML Service
    participant F as Feast와 Redis
    participant R as 모델 Runner
    Note over S,R: 시작 시 모델과 열 목록의 버전 확인
    C->>S: POST /predict와 user_id
    S->>F: get_online_features()
    F-->>S: 해당 사용자의 피처
    S->>S: 입력 검사와 인코딩
    S->>R: 모델 입력
    R-->>S: 예측 클래스
    S-->>C: income_category와 user_id
```

입력은 사용자 ID 하나이며 피처 전체를 클라이언트가 보내는 형태가 아니다. 응답의 `income_category`는 예측 클래스를 `<=50K`, `>50k`로 바꾼 값이며, 5장의 확률 열과 같은 형식이 아니다.

1. 터미널 2에서 같은 가상환경을 활성화하고 `bentoml` 폴더에서 서비스를 실행한다. MLflow 아티팩트를 S3에서 받으므로 S3 자격 증명을 환경 변수로 준다.
   ```powershell
   $env:AWS_ACCESS_KEY_ID = "minio"; $env:AWS_SECRET_ACCESS_KEY = "minio123"
   bentoml serve service:svc --port 3000 --api-workers 1
   ```
   `Starting production HTTP BentoServer ... listening on http://0.0.0.0:3000`이 나온 뒤 30초 정도 지나 초기화 로그가 멈추면 준비된 것이다.
2. 터미널 3에서 요청을 보낸다.
   ```powershell
   $body = @{ user_id = "9f2ac416-06e1-44a0-87bd-d4787c85bf66" } | ConvertTo-Json
   Invoke-RestMethod http://127.0.0.1:3000/predict -Method Post -ContentType application/json -Body $body
   ```
   ```text
   income_category user_id
   --------------- -------
   <=50K           9f2ac416-06e1-44a0-87bd-d4787c85bf66
   ```
3. 브라우저에서 http://127.0.0.1:3000 을 열면 BentoML이 만든 Swagger UI가 나온다. **POST /predict → Try it out**에서 `user_id`를 넣고 **Execute**를 누른다. 아래는 B-4의 수정 뒤에 다른 사용자로 요청한 결과다.

   ![Swagger UI에서 보낸 /predict 요청과 응답.](/images/ml-platform-engineering/sop/ch06-b-swagger-predict.png)

`--api-workers 1`은 Windows에서 필요했다. 기본값은 CPU 수만큼 API worker를 띄우는데, 모든 worker가 시작할 때 같은 작업 폴더에 `feature_store.yaml`을 내려받아 다시 쓴다. 16개 worker가 동시에 같은 파일을 쓰다가 `PermissionError: [WinError 32] 다른 프로세스가 파일을 사용 중`으로 모두 시작에 실패했다. Linux 컨테이너에서는 같은 오류가 나지 않았지만, 여러 프로세스가 공유 경로에 설정 파일을 쓰는 구조 자체가 경쟁 조건이므로 C-3의 Pod에도 worker를 하나로 지정했다.

### B-4. 단일 요청의 입력 인코딩 확인과 수정

[본문](#model-serving)에서 다룬 단일 요청의 원-핫 인코딩 문제를 실제로 확인했다. 같은 사용자의 온라인 피처를 저자의 `InputMapper`로 변환하면 다음과 같았다.

```text
Race                     White
Native_country   United-States
Sex                       Male
Marital-Status   Never-married
Relationship     Not-in-family
Education            Bachelors
Occupation        Adm-clerical
Workclass            State-gov
columns: 91 nonzero: 0
without drop_first nonzero: 7 ['Workclass_ State-gov', 'Education_ Bachelors', 'Marital-Status_ Never-married', ...]
```

`get_dummies(drop_first=True)`는 각 열에서 첫 번째 범주를 버린다. 행이 하나면 범주도 하나뿐이라 모든 열이 사라지고, 학습 열 91개로 맞추면 **모든 값이 0인 입력**이 된다. 실제로 저자의 mock 요청 100건을 보낸 결과는 전부 `<=50K`였다. 없는 사용자 `no-such-user`를 보내도 HTTP 200과 `<=50K`가 돌아왔다.

학습 때의 `drop_first=True`는 이미 `column_list.pkl`에 반영되어 있다. 추론에서는 모든 범주의 열을 만든 뒤 학습 열 목록으로 재정렬하면 학습에서 버린 기준 범주 열은 자연스럽게 빠진다. 그래서 `src\data_mapper.py`의 한 줄만 바꿨다.

```python
dummyfied_input_data = pd.get_dummies(
    self.data, drop_first=False, sparse=False, dtype=float
)
```

서비스를 `Ctrl+C`로 멈추고 다시 실행한 뒤 같은 mock 요청 100건을 보냈다.

```powershell
$ids = (Import-Csv .\scripts\mock_request_data.csv).user_id
$ids | ForEach-Object { (Invoke-RestMethod http://127.0.0.1:3000/predict -Method Post -ContentType application/json -Body (@{ user_id = $_ } | ConvertTo-Json)).income_category } | Group-Object | Select-Object Name, Count
```

| 입력 변환 | `<=50K` | `>50k` |
| --- | --- | --- |
| 저자 코드 `drop_first=True` | 100 | 0 |
| 수정 `drop_first=False` | 75 | 25 |

이 수정은 열 이름이 학습 때와 같은 문자열로 만들어진다는 전제에 기대는 최소한의 보완이다. 피처 값의 앞 공백(`' State-gov'`)까지 같아야 하고, 학습에 없던 범주는 여전히 조용히 0이 된다. 없는 사용자도 여전히 정상 응답한다. 운영에서는 학습에서 fit한 인코더를 모델과 함께 저장해 재사용하고, 온라인 피처가 비어 있으면 예측 대신 오류를 반환하게 해야 한다.

## C. Bento 빌드와 클러스터 배포

지금 위치: 전체 그림의 ⑥~⑨. 로컬에서 동작한 서비스를 Bento로 묶고, 이미지를 만들어 클러스터에서 요청을 받게 한다. 책은 Yatai를 쓰고, 이 실습은 같은 이미지를 일반 Deployment로도 배포했다.

### C-1. Bento 빌드

`bentoml` 폴더에서 실행한다.

```powershell
bentoml build -f .\bento\bentofile.yaml
bentoml list
```

```text
Successfully built Bento(tag="income_classifier_service:aevxrk62tokqzlaz").

 Tag                                Size       Model Size  Creation Time
 income_classifier_service:aevxrk…  21.74 KiB  37.00 MiB   2026-11-07 20:04:30
```

Bento 태그 `aevxrk62tokqzlaz`는 서비스 코드와 설정, 의존성 선언과 모델 참조를 묶은 산출물의 식별자다. B-1의 모델 태그와 다르며, 모델이 같아도 서비스 코드를 바꾸면 새 Bento 태그가 생긴다. 실제 크기도 코드는 21.74 KiB이고 모델이 37 MiB다.

저자 README의 `bentofile_with_drift_detection.yaml`은 실제로 없는 파일이다. 드리프트 서비스의 파일은 `bento\bentofile_with_drift.yaml`이다. 또 `bentofile.yaml`은 `*.env`를 포함하므로 B-2에서 넣은 접속 정보가 Bento와 이미지 안에 들어간다. 실습용 계정이라 그대로 두었지만, 실제 자격 증명을 쓰는 환경이라면 패키지에서 빼고 Secret으로 전달해야 한다.

### C-2. 컨테이너 이미지 만들기

```powershell
bentoml containerize income_classifier_service:aevxrk62tokqzlaz
```

처음에는 Python 3.10 기반 이미지를 받고 의존성을 설치하느라 약 8분 걸렸고, 마지막에 `Successfully built Bento container for "income_classifier_service:aevxrk62tokqzlaz"`가 나왔다.

README의 다음 단계대로 바로 실행하면 서비스가 시작되지 않는다.

```powershell
docker run --rm -p 3001:3000 income_classifier_service:aevxrk62tokqzlaz
```

```text
[WARNING] [api_server:1] Retrying (...) after connection broken by 'NewConnectionError("HTTPConnection(host='localhost', port=5000): Failed to establish a new connection ...
```

이미지에는 B-2에서 PC용으로 바꾼 `.env`가 들어 있고, 컨테이너 안의 `localhost`는 PC가 아니라 컨테이너 자신이다. 저자가 `.env`에 `host.docker.internal`을 썼던 이유가 이것이다. 이 실습에서는 컨테이너를 PC의 Docker가 아니라 클러스터에서 실행하므로 C-3에서 `ENV_NAME=production`으로 클러스터 주소를 쓰게 했다. `Ctrl+C`로 멈춘다.

### C-3. 대안 경로: kind에 일반 Deployment로 배포

Yatai가 하는 일 중 이미지 빌드와 Pod 생성을 손으로 한 경로다. [전체 그림](#platform-map)의 ⑨'에 해당한다.

1. 이미지를 kind 노드에 넣는다.
   ```powershell
   kind load docker-image income_classifier_service:aevxrk62tokqzlaz --name book-env
   ```
2. 아래 내용을 `ch06-serving.yaml`로 저장하고 적용한다.
   ```yaml
   apiVersion: v1
   kind: Namespace
   metadata:
     name: ch06-serving
   ---
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: income-classifier
     namespace: ch06-serving
   spec:
     replicas: 1
     selector:
       matchLabels:
         app: income-classifier
     template:
       metadata:
         labels:
           app: income-classifier
       spec:
         containers:
           - name: bento
             image: income_classifier_service:aevxrk62tokqzlaz
             imagePullPolicy: Never
             args: ["serve"]
             env:
               - name: ENV_NAME
                 value: production
               - name: BENTOML_CONFIG_OPTIONS
                 value: api_server.workers=1
             ports:
               - containerPort: 3000
             readinessProbe:
               httpGet:
                 path: /readyz
                 port: 3000
               initialDelaySeconds: 20
               periodSeconds: 10
               failureThreshold: 30
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: income-classifier
     namespace: ch06-serving
   spec:
     selector:
       app: income-classifier
     ports:
       - port: 3000
         targetPort: 3000
   ```
   ```powershell
   kubectl apply -f ch06-serving.yaml
   kubectl -n ch06-serving rollout status deploy/income-classifier --timeout=400s
   kubectl -n ch06-serving get deploy,pod,svc
   ```
   ```text
   NAME                                READY   UP-TO-DATE   AVAILABLE   AGE
   deployment.apps/income-classifier   1/1     1            1           78s

   NAME                                     READY   STATUS    RESTARTS   AGE
   pod/income-classifier-79c5bdbc66-799mc   1/1     Running   0          78s

   NAME                        TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)    AGE
   service/income-classifier   ClusterIP   10.96.19.220   <none>        3000/TCP   78s
   ```
3. 새 터미널에서 서비스를 PC의 3002 포트로 연결한다.
   ```powershell
   kubectl -n ch06-serving port-forward svc/income-classifier 3002:3000
   ```
4. http://127.0.0.1:3002 의 Swagger UI에서 B-3과 같이 요청한다. mock 요청 100건의 결과도 로컬과 같은 `<=50K` 75건, `>50k` 25건이었다.

   ![kind에 배포한 Bento 이미지가 응답한 결과.](/images/ml-platform-engineering/sop/ch06-c-kind-predict.png)

여기서 Pod는 PC의 포트포워딩을 쓰지 않는다. MLflow, S3, Redis 모두 `production.env`의 클러스터 서비스 주소로 접속한다. Bento 이미지 안에서는 `bentoml serve`가 API 서버와 Runner를 같은 컨테이너의 프로세스로 띄우므로, 이 경로에서는 Runner가 별도 Pod가 아니다.

### C-4. 책의 경로: Yatai로 배포

책은 Bento를 Yatai에 push하고 Yatai UI에서 배포를 만든다. Yatai가 이미지 빌드 Job을 실행하고, 끝나면 API Server Pod와 Runner Pod를 띄운다. 2026년 11월 기준 [bentoml/Yatai 저장소](https://github.com/bentoml/Yatai)는 archived 상태이고 마지막 릴리스는 2023년 10월의 v1.1.13이다. README는 BentoML 1.2용 Yatai가 아직 만들어지는 중이라고 안내한다. 따라서 Yatai 1.x는 이 책처럼 BentoML 1.1의 Service와 Runner로 만든 Bento에만 맞는다. 그래도 Helm 차트와 이미지는 아직 받을 수 있어서 같은 kind 클러스터에 설치해 책의 경로를 끝까지 실행했다.

책의 부록과 Yatai의 quick-install 스크립트는 PostgreSQL HA와 MinIO operator를 따로 설치한다. 여기서는 클러스터에 이미 있는 PostgreSQL과 S3를 재사용했다. 설치한 구성은 다음과 같다.

| 구성 | 버전 | 네임스페이스 | 역할 |
| --- | --- | --- | --- |
| cert-manager | v1.13.3 | `cert-manager` | image builder와 deployment의 webhook 인증서 |
| yatai | 차트 1.1.13 | `yatai-system` | UI, API, 모델과 Bento 저장소 |
| yatai-image-builder | 3.0.48 | `yatai-image-builder` | `BentoRequest`를 받아 kaniko Job으로 이미지 빌드 |
| yatai-deployment | 1.1.21 | `yatai-deployment` | `BentoDeployment`를 Deployment, Service, HPA로 변환 |
| 레지스트리 | `registry:2` | `yatai-image-builder` | 빌드한 이미지를 보관. NodePort 30500 |
| 배포 대상 | | `yatai` | API Server와 Runner Pod |

1. Helm 저장소와 차트를 준비한다. Helm 3가 필요하다.
   ```powershell
   helm repo add bentoml https://bentoml.github.io/helm-charts
   helm repo update bentoml
   kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml
   kubectl -n cert-manager rollout status deploy/cert-manager-webhook --timeout=300s
   ```
2. Yatai용 데이터베이스와 버킷을 만들고 Yatai를 설치한다. PostgreSQL 비밀번호는 `postgres` 네임스페이스의 Secret에 있는 실습용 값이다.
   ```powershell
   kubectl -n postgres exec deploy/postgres-release-postgresql -- sh -c 'PGPASSWORD=postgres123 psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE yatai"'
   python -c "from minio import Minio; c=Minio('localhost:9000',access_key='minio',secret_key='minio123',secure=False); [c.make_bucket(b) for b in ('ch06-yatai','ch06-yatai-images') if not c.bucket_exists(b)]"
   helm upgrade --install yatai bentoml/yatai --version 1.1.13 -n yatai-system --create-namespace `
     --set postgresql.host=postgres-release-postgresql.postgres.svc.cluster.local `
     --set postgresql.user=postgres --set postgresql.password=postgres123 --set postgresql.database=yatai `
     --set s3.endpoint=minio-service.kubeflow.svc.cluster.local:9000 --set s3.region=us-east-1 `
     --set s3.bucketName=ch06-yatai --set s3.secure=false --set s3.accessKey=minio --set s3.secretKey=minio123
   ```
3. 새 터미널에서 Yatai를 연다. 8080은 KFP가 쓰고 있으므로 8091을 쓴다.
   ```powershell
   kubectl -n yatai-system port-forward svc/yatai 8091:80
   ```
   초기화 토큰을 읽어 `http://127.0.0.1:8091/setup?token=<토큰>`을 열고 관리자 계정을 만든다.
   ```powershell
   $t = kubectl get secret yatai-env -n yatai-system -o jsonpath="{.data.YATAI_INITIALIZATION_TOKEN}"
   [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($t))
   ```

   ![Yatai의 초기 관리자 계정 설정 화면.](/images/ml-platform-engineering/sop/ch06-c-yatai-setup.png)

4. API 토큰을 만들고 BentoML CLI로 로그인해 B-1의 모델과 C-1의 Bento를 push한다. 이 실습에서는 관리자로 로그인한 브라우저 세션에서 UI가 쓰는 `POST /api/v1/api_tokens`를 호출해 `api`, `read_organization`, `write_organization`, `read_cluster`, `write_cluster` 권한의 토큰을 만들었다.
   ```powershell
   bentoml yatai login --api-token <API-토큰> --endpoint http://127.0.0.1:8091
   bentoml push income_classifier_service:aevxrk62tokqzlaz
   ```
   ```text
   Successfully logged in to Cloud for admin in default
   Successfully pushed model "random-forest-classifier:zv2wqy62tcgfhlaz"
   Successfully pushed bento "income_classifier_service:aevxrk62tokqzlaz"
   ```
   **모델**과 **Bentos** 메뉴에 같은 태그가 보이면 된다. 책의 그림 6.3, 6.4에 해당한다.

   ![Yatai 모델 저장소의 random-forest-classifier.](/images/ml-platform-engineering/sop/ch06-c-yatai-models.png)

   ![Yatai Bento 저장소의 income_classifier_service.](/images/ml-platform-engineering/sop/ch06-c-yatai-bentos.png)

5. 이미지 빌더와 배포 컴포넌트를 설치한다. 이미지를 보관할 레지스트리는 kind 노드가 `127.0.0.1:30500`으로 받을 수 있게 NodePort로 띄운다. containerd는 `localhost` 레지스트리를 HTTP로 허용하므로 kind 설정을 바꾸지 않아도 된다.
   ```powershell
   helm upgrade --install yatai-image-builder-crds bentoml/yatai-image-builder-crds --version 3.0.48 -n yatai-image-builder --create-namespace
   kubectl apply -f ch06-registry.yaml
   kubectl create namespace yatai
   helm upgrade --install yatai-deployment-crds bentoml/yatai-deployment-crds --version 1.1.21 -n yatai-deployment --create-namespace
   helm upgrade --install yatai-image-builder bentoml/yatai-image-builder --version 3.0.48 -n yatai-image-builder `
     --set yatai.endpoint=http://yatai.yatai-system.svc.cluster.local --set yatai.apiToken=<API-토큰> `
     --set dockerRegistry.server=127.0.0.1:30500 `
     --set dockerRegistry.inClusterServer=ch06-registry.yatai-image-builder.svc.cluster.local:5000 `
     --set dockerRegistry.secure=false --set internal.disableYataiComponentRegistration=false `
     --set global.s3.endpoint=minio-service.kubeflow.svc.cluster.local:9000 --set global.s3.secure=false `
     --set global.s3.accessKeyId=minio --set global.s3.secretAccessKey=minio123 --set global.s3.bucketName=ch06-yatai-images `
     --set "global.deploymentNamespaces={yatai,yatai-system}"
   helm upgrade --install yatai-deployment bentoml/yatai-deployment --version 1.1.21 -n yatai-deployment `
     --set yatai.endpoint=http://yatai.yatai-system.svc.cluster.local --set yatai.apiToken=<API-토큰> `
     --set layers.network.domainSuffix=ch06.local --set layers.network.automaticDomainSuffixGeneration=false
   ```
   `ch06-registry.yaml`은 다음과 같다. 노드가 Docker Hub에서 `registry:2`를 받지 못하면 PC에서 받아 넣는다. `kind load docker-image`가 `content digest ... not found`로 실패해서 `docker save --platform linux/amd64 registry:2 -o registry2.tar`와 `kind load image-archive registry2.tar --name book-env`를 썼다.
   ```yaml
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: ch06-registry
     namespace: yatai-image-builder
   spec:
     replicas: 1
     selector:
       matchLabels:
         app: ch06-registry
     template:
       metadata:
         labels:
           app: ch06-registry
       spec:
         containers:
           - name: registry
             image: registry:2
             ports:
               - containerPort: 5000
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: ch06-registry
     namespace: yatai-image-builder
   spec:
     type: NodePort
     selector:
       app: ch06-registry
     ports:
       - port: 5000
         targetPort: 5000
         nodePort: 30500
   ```
6. 차트를 그대로 설치하면 배포가 시작되지 않는다. 아래 세 가지를 고쳐야 했다.

   | 증상 | 원인 | 조치 |
   | --- | --- | --- |
   | image builder가 `Endpoint: does not follow ip address` 오류로 재시작 | 3.0.48은 `global.s3` 설정이 비어 있으면 시작 검사에서 실패 | 위 명령의 `global.s3.*` 지정 |
   | 배포 생성 시 `yatai` 서비스 계정이 `bentorequests`를 `get`할 수 없음 | 차트의 RoleBinding이 주체 네임스페이스를 `yatai-system`이 아니라 배포 네임스페이스로 렌더링 | RoleBinding의 subject 네임스페이스를 `yatai-system`으로 수정 |
   | image builder가 `yatai-system/yatai-common-env`를 읽지 못함 | 감시 네임스페이스에 `yatai-system`이 없으면 Secret 캐시가 비어 있음 | `global.deploymentNamespaces`에 `yatai-system` 추가 |

   네임스페이스를 둘 지정하면 차트의 range 템플릿이 문서 구분자 없이 렌더링되어 `yatai` 쪽 Role과 RoleBinding이 빠진다. 그래서 `yatai`용만 따로 렌더링해 적용하고 주체를 고쳤다.
   ```powershell
   helm template yatai-image-builder bentoml/yatai-image-builder --version 3.0.48 -n yatai-image-builder `
     --show-only templates/range-role.yaml --show-only templates/range-rolebinding.yaml `
     --show-only templates/role-yatai-with-bento-request.yaml --show-only templates/rolebinding-yatai-with-bento-request.yaml |
     kubectl apply -f -
   kubectl -n yatai patch rolebinding yatai-with-bento-request --type=json -p '[{\"op\":\"replace\",\"path\":\"/subjects/0/namespace\",\"value\":\"yatai-system\"}]'
   kubectl -n yatai-image-builder rollout restart deploy/yatai-image-builder
   ```
7. 배포를 만든다. 책은 Yatai UI의 **배포 → 생성** 화면에서 이름, Bento와 태그, 복제본과 자원을 입력한다. 이 실습에서는 같은 내용을 UI가 호출하는 `POST /api/v1/clusters/default/deployments`로 보냈다. 핵심 값은 다음과 같다.
   ```json
   {
     "name": "ch06-income-classifier",
     "kube_namespace": "yatai",
     "targets": [{
       "type": "stable",
       "bento_repository": "income_classifier_service",
       "bento": "aevxrk62tokqzlaz",
       "config": {
         "hpa_conf": { "min_replicas": 1, "max_replicas": 1 },
         "resources": { "requests": { "cpu": "200m", "memory": "512Mi" }, "limits": { "cpu": "2000m", "memory": "2Gi" } },
         "envs": [{ "key": "ENV_NAME", "value": "production" }, { "key": "BENTOML_CONFIG_OPTIONS", "value": "api_server.workers=1" }],
         "runners": { "random-forest-classifier": { "hpa_conf": { "min_replicas": 1, "max_replicas": 1 } } },
         "enable_ingress": false
       }
     }]
   }
   ```
   `ENV_NAME=production`이 없으면 Pod가 PC용 `.env`를 읽어 C-2와 같은 `localhost` 연결 오류가 난다.
8. 배포를 만들면 `yatai` 네임스페이스에 `BentoRequest`와 `BentoDeployment`가 생기고 kaniko Job이 실행된다.
   ```powershell
   kubectl -n yatai get bentorequest,bentodeployment,jobs,pods
   ```
   kaniko는 Bento의 Dockerfile대로 `python:3.10-slim`을 Docker Hub에서 받아 의존성을 설치하고, 결과를 클러스터 안 레지스트리로 push한다. 첫 시도는 Docker Hub 연결 시간 초과(`dial tcp ...:443: i/o timeout`)로 실패했다. 실패한 Job을 지우자 image builder가 Job을 다시 만들었고, 두 번째 시도는 약 3분 만에 끝났다.
   ```text
   INFO[0190] Pushing image to ch06-registry.yatai-image-builder.svc.cluster.local:5000/yatai-bentos:yatai.income_classifier_service.aevxrk62tokqzlaz
   ```
9. 빌드가 끝나면 Pod 두 개가 뜬다. 책의 그림 6.9처럼 **레플리카** 탭에서 API Server와 Runner가 따로 보인다.
   ```text
   NAME                                               READY   STATUS    RESTARTS   AGE
   ch06-income-classifier-7fd67bd9c6-sj8x4            3/3     Running   0          7m14s
   ch06-income-classifier-runner-0-6ffb5b488b-n662f   2/2     Running   0          7m14s
   ```

   ![Yatai 배포 목록의 ch06-income-classifier.](/images/ml-platform-engineering/sop/ch06-c-yatai-deployments.png)

   ![배포 개요의 클러스터 내부 URL과 이미지 빌드 Pod.](/images/ml-platform-engineering/sop/ch06-c-yatai-deployment-detail.png)

   ![API Server와 Runner로 나뉜 레플리카.](/images/ml-platform-engineering/sop/ch06-c-yatai-replicas.png)

10. 서비스를 3003 포트로 연결해 요청한다. mock 요청 100건의 결과도 C-3과 같은 75건과 25건이었다.
    ```powershell
    kubectl -n yatai port-forward svc/ch06-income-classifier 3003:3000
    ```

    ![Yatai가 배포한 서비스의 /predict 응답.](/images/ml-platform-engineering/sop/ch06-c-yatai-predict.png)

C-3과 비교하면 Yatai가 대신한 일이 분명해진다. `bentoml containerize`와 `kind load` 대신 image builder가 클러스터 안에서 이미지를 만들었고, 직접 쓴 Deployment 대신 yatai-deployment가 API Server와 Runner를 **별도 Deployment와 Service**로 만들었다. API Pod의 컨테이너가 셋인 것은 본 서비스 외에 메트릭 변환과 프록시 사이드카가 붙기 때문이다. HPA도 함께 만들어지지만 kind에는 metrics-server가 없어 `FailedGetResourceMetric` 경고만 남고 복제본은 1로 유지됐다.

배포 중간에 Docker Desktop의 디스크가 차서 kind 노드가 재시작되는 일이 있었다. 재시작 뒤 Yatai 배포는 같은 user에게 `<=50K`만 돌려줬는데, 원인은 Redis였다. 실습 Redis는 영속 볼륨이 없어서 재시작과 함께 온라인 피처가 모두 사라졌고(`dbsize` 0), API는 빈 피처를 0으로 채워 HTTP 200으로 응답했다. 4장 피처 저장소 폴더에서 `feast materialize 2022-09-16T00:00:00 2023-09-17T00:00:00`을 다시 실행해 30,162건을 적재하자 원래 결과로 돌아왔다.

## D. Evidently로 데이터 드리프트 관측

지금 위치: 전체 그림의 ⑭~⑰. 같은 기준 데이터를 두 곳에서 비교한다. 배치 파이프라인에서는 KFP 작업이 조회한 피처 전체를, API에서는 최근 요청 윈도우를 current로 쓴다.

드리프트 검사는 기준(reference)과 현재(current) 입력의 분포를 비교한다. 기준 데이터는 아무 학습 CSV가 아니라 서비스 모델의 학습 조건과 연결되어 있어야 한다. 저자 코드는 모델의 원천 run을 찾고, `run.inputs.dataset_inputs`에서 `REFERENCE_DATASET_NAME`(`reference_features`)과 같은 태그의 입력 기록을 찾아 CSV를 받는다. A-3에서 확인한 `feature_df-93b1a....csv`가 그 파일이다.

| 확인할 것 | 이유 |
| --- | --- |
| 원천 run과 모델 버전 | 다른 모델의 학습 데이터와 비교하지 않기 위해 |
| 입력 기록의 태그와 dataset source | 이름이 맞아도 파일 위치가 다르거나 형식이 다를 수 있음 |
| 비교할 열과 타입 | 원-핫 인코딩 전 범주형 피처끼리 비교해야 함 |
| 현재 데이터의 기간과 표본 수 | 변화가 어느 구간에서 생겼는지 해석하기 위해 |
| 기준 파일의 버전 | 같은 경로의 파일이 바뀌면 비교 기준도 달라짐 |

### D-1. Evidently workspace와 검사 이미지

저자 README는 클러스터의 `evidently` 네임스페이스에 `evidently-service-internal` 서비스가 있다고 가정하지만, 그 서버를 설치하는 명세는 저장소에 없다. `create_remote_project.py`와 `build_evidently_dashboard.py`는 이미 떠 있는 workspace에 프로젝트와 패널을 만드는 스크립트다. 그래서 검사 작업 이미지를 먼저 만들고, 같은 이미지로 workspace 서버도 띄웠다.

1. 검사 이미지를 만든다. 저자 Dockerfile은 `python:3.10-slim-buster`라 5장과 같은 이유로 그대로는 빌드되지 않는다. bookworm으로 바꿔 전체 의존성을 새로 설치하는 빌드도 시도했지만 실습 PC의 디스크 여유가 부족했다. 그래서 5장 컴포넌트 이미지(Python 3.10, MLflow 3.0.0, Feast 0.40.1, KFP 2.9.0)에 Evidently 0.5.0만 더했다. 저자는 MLflow 2.7.0을 지정했지만 `detect_drift.py`가 쓰는 API는 3.0.0에서도 동작했다.
   ```powershell
   New-Item -ItemType Directory -Force ch06-drift-image | Out-Null
   Copy-Item -Recurse upstream\chapter-6\evidently\kubeflow-pipeline\src ch06-drift-image\
   Set-Content ch06-drift-image\Dockerfile "FROM book-ch5/components:0.1`nRUN pip install --no-cache-dir evidently==0.5.0`nCOPY src/detect_drift /app/src/detect_drift`n"
   docker build -t ch06/detect-drift:0.1 ch06-drift-image
   kind load docker-image ch06/detect-drift:0.1 --name book-env
   ```
2. 아래 내용을 `ch06-evidently.yaml`로 저장하고 적용한다. 저장소가 `emptyDir`이므로 Pod가 재시작되면 보고서도 사라진다. 실습용 구성이다.
   ```yaml
   apiVersion: v1
   kind: Namespace
   metadata:
     name: evidently
   ---
   apiVersion: apps/v1
   kind: Deployment
   metadata:
     name: evidently-ui
     namespace: evidently
   spec:
     replicas: 1
     selector:
       matchLabels:
         app: evidently-ui
     template:
       metadata:
         labels:
           app: evidently-ui
       spec:
         containers:
           - name: evidently
             image: ch06/detect-drift:0.1
             imagePullPolicy: Never
             command: ["evidently", "ui", "--host", "0.0.0.0", "--port", "8000", "--workspace", "/data/workspace"]
             ports:
               - containerPort: 8000
             volumeMounts:
               - name: data
                 mountPath: /data
         volumes:
           - name: data
             emptyDir: {}
   ---
   apiVersion: v1
   kind: Service
   metadata:
     name: evidently-service-internal
     namespace: evidently
   spec:
     selector:
       app: evidently-ui
     ports:
       - port: 8000
         targetPort: 8000
   ```
   ```powershell
   kubectl apply -f ch06-evidently.yaml
   kubectl -n evidently rollout status deploy/evidently-ui --timeout=300s
   kubectl -n evidently port-forward svc/evidently-service-internal 8000:8000
   ```
3. 드리프트 서비스용 가상환경을 따로 만든다. `requirements_with_drift.txt`의 MLflow 2.7.0이 A-4의 3.0.0과 충돌하기 때문이다.
   ```powershell
   uv venv .venv-ch06-drift --python 3.10
   uv pip install --python .venv-ch06-drift "bentoml==1.1.10" -r upstream\chapter-6\bentoml\requirements_with_drift.txt "setuptools<70" "click==8.1.7" "scikit-learn==1.5.2" "litestar==2.12.1"
   uv pip uninstall --python .venv-ch06-drift multipart
   uv pip install --python .venv-ch06-drift --reinstall-package python-multipart "python-multipart==0.0.32"
   ```
   `litestar` 고정과 `multipart` 제거는 실제 충돌 때문이다. Evidently UI가 쓰는 최신 litestar는 `multipart`라는 다른 패키지를 요구하는데, 이 패키지가 BentoML 1.1.10이 쓰는 `python-multipart`와 같은 모듈 이름을 차지한다. 그대로 두면 `import bentoml`이 `No module named 'multipart.multipart'`로, 반대로 고치면 `from evidently.ui.workspace import RemoteWorkspace`가 `cannot import name 'MultipartSegment'`로 실패했다. 자체 multipart 처리를 쓰던 litestar 2.12.1로 내리자 둘 다 import됐다.
4. 같은 가상환경에서 프로젝트와 대시보드를 만든다.
   ```powershell
   cd upstream\chapter-6\evidently
   ..\..\..\.venv-ch06-drift\Scripts\python.exe scripts\build_evidently_dashboard.py
   Invoke-RestMethod http://127.0.0.1:8000/api/projects | Select-Object id, name
   ```
   ```text
   id                                   name
   --                                   ----
   01a1b610-1d4e-76e3-aecc-652f3f24ac2d income-classifier
   ```
   `build_evidently_dashboard.py`는 같은 이름의 프로젝트가 없으면 만들기 때문에 README의 `create_remote_project.py`를 먼저 실행하지 않아도 된다. `create_remote_project.py`는 검색 없이 만들므로 여러 번 실행하면 같은 이름의 프로젝트가 늘어난다. 출력된 `id`는 D-4에서 쓴다.

### D-2. 배치 파이프라인에 드리프트 검사 넣기

`evidently\kubeflow-pipeline`의 흐름은 다음과 같다.

```mermaid
flowchart LR
    accTitle: 드리프트 보고서를 추가한 배치 추론
    accDescr: 대상과 피처를 읽은 뒤 드리프트 보고서를 만들고 추론을 실행한다. 추론은 검사 작업의 완료를 기다리지만 보고서의 드리프트 여부를 해석해 차단하는 조건은 원본에 없다.
    A["대상 읽기"] --> B["Feast 과거 피처 조회"]
    B --> C["드리프트 보고서 생성"]
    B --> D["모델 추론"]
    C -->|"작업 완료 의존성"| D
    D --> E["예측 결과 저장"]
```

1. 다섯 컴포넌트의 이미지를 바꾼다. 대상 읽기, 피처 조회, 추론, 결과 쓰기의 소스는 5장 저장소와 한 줄도 다르지 않아 `book-ch5/components:0.1`을 그대로 쓴다.
   ```powershell
   cd upstream\chapter-6\evidently\kubeflow-pipeline\components
   foreach ($c in 'read_data','retrieve_features','run_inference','write_data') {
     (Get-Content "$c\component.yaml") -replace "image: 'varunmallya/[^']+'","image: 'book-ch5/components:0.1'" | Set-Content "$c\component.yaml"
   }
   (Get-Content detect_drift\component.yaml) -replace "image: 'varunmallya/[^']+'","image: 'ch06/detect-drift:0.1'" | Set-Content detect_drift\component.yaml
   cd ..
   ```
2. 4~5장의 `.venv-book`(KFP SDK 2.9.0)으로 컴파일하고 이미지를 확인한다.
   ```powershell
   ..\..\..\..\.venv-book\Scripts\python.exe inference_pipeline.py
   Select-String income_classifier_pipeline_with_drift.yaml -Pattern "image:"
   ```
   ```text
   income_classifier_pipeline_with_drift.yaml:172:        image: ch06/detect-drift:0.1
   income_classifier_pipeline_with_drift.yaml:196:        image: book-ch5/components:0.1
   ...
   ```
3. KFP UI에서 4~5장 실습의 D-5와 같이 업로드한다. 5장 파이프라인과 겹치지 않게 이름을 `ch06-income-classifier-drift`로, 실험을 `ch06-drift`로 했다.
4. 실행 파라미터는 5장의 표에 세 개를 더하고, 5장 결과를 덮어쓰지 않게 출력 파일 이름을 바꾼다.

   | 파라미터 | 값 |
   | --- | --- |
   | reference_dataset_name | `reference_features` |
   | evidently_workspace_url | `http://evidently-service-internal.evidently.svc.cluster.local:8000` |
   | evidently_ui_project_name | `income-classifier` |
   | output_file_name | `ch06_income_predictions_with_drift.parquet` |

5. 실행 `ch06-drift-run-1`은 약 2분 만에 다섯 작업이 모두 초록색으로 끝났다. `detect-drift`가 `retrieve-features-from-feast`의 `data_output`을 입력으로 받고, `model-inference`가 `detect-drift` 뒤에 실행되는 것을 그래프에서 볼 수 있다.

   ![드리프트 검사가 추가된 KFP 실행 그래프.](/images/ml-platform-engineering/sop/ch06-d-kfp-drift-run.png)

6. **detect-drift → Logs**에서 `report written`과 `project retreived`를 확인한다.

   ![detect-drift 작업의 로그.](/images/ml-platform-engineering/sop/ch06-d-kfp-drift-logs.png)

추론 작업의 `.after(detect_drift_task)`는 실행 순서만 정한다. **원본 `detect_drift.py`에는 드리프트 결과가 임계치를 넘으면 실패시키는 분기가 없다.** 보고서를 생성하고 workspace에 올린 뒤 작업을 끝낸다. 검사 프로세스가 오류로 실패하면 후속 작업이 진행되지 않는 것과, 데이터 변화 때문에 의도적으로 차단하는 것은 다르다. 품질 게이트로 쓰려면 검사 결과를 명시적 출력으로 내보내고 조건 분기나 실패 정책을 추가해야 한다.

### D-3. 배치 보고서와 대시보드 읽기

1. http://127.0.0.1:8000 에서 `income-classifier` 프로젝트를 열면 대시보드가 보인다. **Model Calls**는 보고서들의 current 행 수 합계, **Share of Drifted Features**는 마지막 보고서의 드리프트 열 비율이다.

   ![배치 보고서 하나가 올라간 Evidently 대시보드.](/images/ml-platform-engineering/sop/ch06-d-evidently-dashboard.png)

2. **Reports**에서 보고서를 열면 열 8개 중 드리프트가 감지된 열이 0개다.

   ![배치 추론 입력 30,162행과 기준 데이터를 비교한 보고서.](/images/ml-platform-engineering/sop/ch06-d-evidently-report.png)

이 결과는 당연하다. 5장의 `entity_df.parquet`는 학습에 쓴 사용자 30,162명이고, Feast가 돌려준 피처도 같은 원천에서 나왔다. 열별 Jensen-Shannon 거리는 `Workclass`의 0.0034를 빼면 모두 0이었다. 드리프트 없음은 이 파이프라인의 연결이 맞다는 확인이지, 운영 데이터가 안정적이라는 증거가 아니다.

current에는 `event_timestamp` 열이 더 있지만 reference에 없는 열이라 드리프트 계산에서는 빠지고 결측 표에만 나타난다. 비교할 열 목록을 명시하지 않으면 이런 차이가 조용히 무시된다.

### D-4. API 입력 윈도우 검사

`service_with_drift_detection.py`는 피처 조회 뒤 `MonitoringService.iterate()`를 호출한다. `data_drift.py`는 입력을 메모리의 DataFrame에 붙이고 최근 `window_size`행만 유지한다.

| 상태 | 원본 코드의 동작 |
| --- | --- |
| 윈도우보다 표본이 적음 | 기다린다는 로그를 남기고 반환 |
| 윈도우를 채움 | reference와 비교해 보고서 생성 |
| 가득 찬 뒤 새 요청이 들어옴 | 최근 윈도우를 유지하고 다시 보고서 생성 |
| 서비스 재시작 또는 worker 분리 | 윈도우는 프로세스 메모리 상태이므로 공유되거나 보존되지 않음 |

1. `bentoml\.env`의 `EVIDENTLY_PROJECT_ID`를 D-1에서 얻은 `id`로 바꾼다. `EVIDENTLY_WORKSPACE_URL`은 B-2에서 이미 `http://localhost:8000`이 됐다.
   ```powershell
   cd upstream\chapter-6\bentoml
   (Get-Content .env) -replace '^EVIDENTLY_PROJECT_ID=.*','EVIDENTLY_PROJECT_ID=01a1b610-1d4e-76e3-aecc-652f3f24ac2d' | Set-Content .env
   ```
2. 터미널 2에서 기본 서비스를 멈추고 드리프트 서비스를 3004 포트로 실행한다.
   ```powershell
   $env:AWS_ACCESS_KEY_ID = "minio"; $env:AWS_SECRET_ACCESS_KEY = "minio123"
   ..\..\..\.venv-ch06-drift\Scripts\bentoml.exe serve service_with_drift_detection:svc --port 3004 --api-workers 1
   ```
   시작 로그에 기준 파일 위치 `mlflow-datasets income-classifier-datasets/feature_df-93b1a....csv`가 찍힌다. MLflow 2.7.0 클라이언트로 3.0.0 서버를 조회하고, MLflow 3.0.0으로 저장한 모델을 Runner가 읽는 데에도 문제가 없었다.
3. 터미널 3에서 저자의 mock 요청 100건을 보낸다.
   ```powershell
   cd scripts
   $env:BENTO_ENDPOINT = "http://127.0.0.1:3004/predict"
   ..\..\..\..\.venv-ch06-drift\Scripts\python.exe generate_mock_requests.py
   ```
   서비스 로그는 99건까지 기다리다가 100번째 요청에서 보고서를 만든다.
   ```text
   [INFO] Not enough data for measurement: 98 of 100. Waiting more data
   [INFO] Not enough data for measurement: 99 of 100. Waiting more data
   [INFO] Running report
   ```
4. 같은 사용자 5명을 더 요청하면 요청마다 보고서가 하나씩 늘어난다. **Reports**에 API 보고서 6개가 생겼다.

   ![윈도우가 찬 뒤 요청마다 쌓인 API 보고서.](/images/ml-platform-engineering/sop/ch06-d-evidently-reports.png)

5. 첫 API 보고서를 연다. 열 8개 중 4개에서 드리프트가 감지됐고 데이터셋 드리프트 판정도 참이다.

   ![요청 100건의 윈도우를 기준 데이터와 비교한 보고서.](/images/ml-platform-engineering/sop/ch06-d-evidently-api-report.png)

| 열 | Jensen-Shannon 거리 | 판정 (임계값 0.1) |
| --- | --- | --- |
| Native_country | 0.1761 | 드리프트 |
| Education | 0.1670 | 드리프트 |
| Marital-Status | 0.1194 | 드리프트 |
| Occupation | 0.1157 | 드리프트 |
| Relationship | 0.0695 | 정상 |
| Race | 0.0648 | 정상 |
| Workclass | 0.0532 | 정상 |
| Sex | 0.0420 | 정상 |

mock 요청의 사용자도 학습 데이터에서 뽑은 사람들이라 실제 분포는 기준과 같다. 그런데도 드리프트로 판정된 것은 **표본 100개로 범주가 많은 열의 분포를 추정했기 때문**이다. 국적처럼 범주가 40개가 넘는 열은 100건 안에 드물게 나타나는 범주가 빠지거나 몰리기 쉽고, 그 우연한 차이가 거리 임계값을 넘는다. D-3의 30,162행 비교와 같은 기준 데이터를 썼는데도 결론이 반대로 나온 이유다. 윈도우 크기와 검정 방법, 임계값을 정하지 않은 채 경고를 운영 대응에 연결하면 이런 판정을 계속 받게 된다.

요청 지연도 함께 바뀌었다. 윈도우가 차기 전 99건의 API 처리 시간은 평균 67.6ms였고, 이후 요청은 2,597~2,796ms였다. Runner의 예측 시간은 계속 약 10ms였다. 늘어난 시간은 보고서 계산과 workspace 전송이 요청 안에서 실행된 결과다. [본문](#production-monitoring)에서 관측 경로를 추론 경로와 분리하라고 한 이유를 실제 숫자로 확인한 셈이다.

보고서 시각도 다르게 기록됐다. API 보고서는 `datetime.now()`로 PC의 한국 시각(22:06)을, KFP 작업은 Pod의 UTC 시각(12:52)을 썼다. 같은 대시보드에서 시간축으로 비교하려면 시간대를 맞춰야 한다.

## E. 결과 해석과 정리

### E-1. 서로 다른 성공 조건

| 확인 수준 | 이 실습에서 남긴 결과 |
| --- | --- |
| API 동작 | 로컬과 kind에서 `/predict` HTTP 200, 응답의 `user_id`가 요청과 같음 |
| 입력 의미 | 저자 코드는 모든 요청을 0 벡터로 변환했고, 수정 뒤 예측이 사용자별로 달라짐 |
| 버전 연결 | MLflow v1과 run `8015f99a...`, BentoML 모델 `zv2wqy62tcgfhlaz`, Bento `aevxrk62tokqzlaz` |
| 드리프트 관측 | reference 파일 위치, 현재 데이터의 행 수와 비교 열, 보고서 |
| 모델 품질 | 이 장의 실습에는 정답 연결이 없으므로 판단하지 않음 |

HTTP 200과 드리프트 없음은 정확도 보증이 아니다. B-4에서 본 것처럼 모든 요청이 같은 답을 내도 API는 정상 응답했다. 분포가 바뀌어도 모델이 잘 예측할 수 있고, 입력 분포가 비슷해도 입력과 정답의 관계가 바뀔 수 있다. 수집 장애, 사용자 구성 변화와 실제 품질 하락을 구분해 대응한다.

### E-2. 실패한 연결에서 확인할 것

| 증상 | 확인할 것 |
| --- | --- |
| `No module named 'pkg_resources'` | `setuptools<70` 고정 |
| `bentoml containerize`의 `NotImplementedError` | `click==8.1.7` 고정 |
| `feast apply`의 `Feature view demographic does not exist` | `feature_repo`에 남은 `retrieve_*.py` 삭제 |
| `bentoml serve`의 `PermissionError: [WinError 32]` | `--api-workers 1` |
| BentoML 모델을 찾지 못함 | B-1 실행 여부, 서비스와 같은 사용자와 `BENTOML_HOME` |
| MLflow Production 모델 조회 실패 | 모델 이름, stage 지정과 서버 주소 |
| `column_list.pkl` 다운로드에서 S3 인증 오류 | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` 환경 변수 |
| 모든 요청이 같은 범주 | 단일 행 인코딩, 사용자 ID와 온라인 적재 |
| 컨테이너에서 `localhost:5000` 연결 재시도 | `ENV_NAME`과 실행 위치에 맞는 설정 파일 |
| Pod의 `ErrImageNeverPull` | `kind load docker-image`를 다시 실행 |
| 드리프트 서비스의 `multipart` import 오류 | `litestar==2.12.1` 고정 |
| 기준 데이터가 없다는 오류 | A-3의 입력 기록 태그와 source URI |
| 보고서는 있는데 추론이 계속됨 | 보고서 작성과 차단 정책이 별개인지 |
| 요청 지연이 검사 후 늘어남 | 요청 안에서 수행하는 보고서 계산과 workspace 전송 |

### E-3. 실습 종료

로컬 서비스는 터미널 2에서 `Ctrl+C`로, 포트포워딩은 각 창에서 `Ctrl+C`로 끈다. BentoML 모델과 Bento는 `~\bentoml`에 남는다. 앞 장의 모델, 피처와 클러스터는 다음 장에서도 쓰므로 지우지 않는다. 6장에서 만든 클러스터 자원만 지우려면 다음을 실행한다.

```powershell
helm uninstall yatai-deployment yatai-deployment-crds -n yatai-deployment
helm uninstall yatai-image-builder yatai-image-builder-crds -n yatai-image-builder
helm uninstall yatai -n yatai-system
kubectl delete namespace ch06-serving evidently yatai yatai-system yatai-image-builder yatai-deployment
kubectl delete -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.3/cert-manager.yaml
kubectl -n postgres exec deploy/postgres-release-postgresql -- sh -c 'PGPASSWORD=postgres123 psql -U postgres -h 127.0.0.1 -c "DROP DATABASE yatai"'
docker rmi income_classifier_service:aevxrk62tokqzlaz ch06/detect-drift:0.1
```

`ch06-yatai`, `ch06-yatai-images` 버킷과 KFP의 `ch06-income-classifier-drift` 파이프라인, `ch06-drift` 실험은 저장소 화면과 KFP UI에서 지운다. 로컬 BentoML 저장소는 `bentoml delete income_classifier_service`와 `bentoml models delete random-forest-classifier`로 정리한다. 이미지는 크기가 2.5GB를 넘으므로 디스크가 부족하면 kind에 적재한 뒤 바로 지워도 된다.

## 참고 자료

- [Evidently 모니터링 구조](https://docs-old.evidentlyai.com/user-guide/monitoring/monitoring_overview), [배치와 지연 정답 평가](https://docs-old.evidentlyai.com/user-guide/monitoring/batch_monitoring), [collector](https://docs-old.evidentlyai.com/user-guide/monitoring/collector_service): 온라인 예측과 별도 관측 작업의 연결.
- [Azure ML 모델 모니터링](https://learn.microsoft.com/en-us/azure/machine-learning/concept-model-monitoring?view=azureml-api-2), [추론 데이터 수집](https://learn.microsoft.com/en-us/azure/machine-learning/concept-data-collection?view=azureml-api-2): 수집 지점, 기준 데이터, 윈도우와 예약 평가의 구체적인 예.
- [Evidently의 드리프트 대응](https://www.evidentlyai.com/blog/ml-monitoring-data-drift-how-to-handle): 원인 조사와 재학습 외의 대응 선택지.
- [출판사의 6장 개요](https://www.manning.com/preview/machine-learning-platform-engineering/chapter-6): BentoML과 Yatai를 이용한 서빙, Evidently 관측의 장별 범위.
- [BentoML 1.1.10의 Service](https://github.com/bentoml/BentoML/blob/v1.1.10/docs/source/concepts/service.rst), [Runner](https://github.com/bentoml/BentoML/blob/v1.1.10/docs/source/concepts/runner.rst), [Bento](https://github.com/bentoml/BentoML/blob/v1.1.10/docs/source/concepts/bento.rst): 책에서 사용하는 버전의 책임과 실행 구조.
- [Evidently 구버전의 드리프트 알고리즘](https://docs-old.evidentlyai.com/reference/data-drift-algorithm): 열별 검사와 데이터셋 수준 판정, 입력 조건.
- [저자 chapter-6 README와 코드](https://github.com/practical-mlops/chapter-6/tree/890db04409cb3f48c4e493470d79095ec6ab63d6): BentoML 1.1.10, 기본 서비스와 Evidently 통합 경로.
- [입력 변환 코드](https://github.com/practical-mlops/chapter-6/blob/890db04409cb3f48c4e493470d79095ec6ab63d6/bentoml/src/data_mapper.py): 요청 단위의 원-핫 인코딩.
- [드리프트 컴포넌트](https://github.com/practical-mlops/chapter-6/blob/890db04409cb3f48c4e493470d79095ec6ab63d6/evidently/kubeflow-pipeline/src/detect_drift/detect_drift.py): 기준 데이터 조회와 보고서 작성.
- [API 입력 윈도우](https://github.com/practical-mlops/chapter-6/blob/890db04409cb3f48c4e493470d79095ec6ab63d6/bentoml/data_drift.py): 표본 누적과 보고서 호출 시점.

[이전: 04~05. 실험, 피처, 파이프라인](../04-experiments-features-pipelines/), [시리즈 목차](../), [다음: 07. 데이터 분석과 준비](../07-data-preparation/)
