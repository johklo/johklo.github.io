---
title: "07. 데이터 분석과 준비"
description: "탐색에서 정한 데이터 의미를 재현 가능한 준비 파이프라인으로 옮기고 탐지와 추천의 검증, 학습과 서빙 계약으로 연결하기"
date: 2026-10-18T21:30:00+09:00
lastmod: 2026-11-08T15:00:00+09:00
weight: 70
draft: false
tags: ["book-club", "ml-platform-engineering", "kubeflow", "data-engineering"]
---

6장에서는 소득 분류 모델을 서비스로 옮기고 입력 변화를 관측했다. 7장부터는 그 플랫폼에 신분증 탐지와 영화 추천이라는 새 프로젝트를 올린다. 새 프로젝트에서 먼저 정할 것은 학습 코드가 아니다. 어떤 데이터가 있는지, 무엇을 예측할지, 어떤 낯선 사례로 평가할지가 먼저다.

이 장은 노트북에서 찾은 처리 규칙을 다음 실행에서도 똑같이 반복되는 준비 파이프라인으로 옮기는 과정이다. 탐색으로 데이터의 의미를 정하고, 컴포넌트 사이의 전달 계약으로 산출물을 잇고, 학습 목적에 맞는 품질 검사로 쓸 입력을 가려낸다. 세 일은 성공의 기준이 서로 다르다. 파일이 내려받아졌다고 다음 Pod가 읽을 수 있는 것도, 읽힌다고 학습에 맞는 데이터인 것도 아니다.

책은 노트북 설정으로 탐색 환경을, 데이터 전달 예제로 작업 사이의 경계를, 두 프로젝트로 그 경계를 지나는 데이터의 의미를 다룬다. 셋은 결국 [학습, 서빙, 관측에 이어지는 계약](#training-serving-contract)으로 모인다. 이 장이 플랫폼의 어느 구간인지는 [전체 그림](#platform-map)에, 실제로 돌려 보는 과정은 [실습 순서](#book-ch07-sop)에 있다.

## 전체 그림 {#platform-map}

7장은 새 구성 요소를 설치하지 않는다. 4~6장에서 만든 KFP, S3 저장소, MLflow, Feast, 서빙과 관측 도구 사이에서 **다음 단계가 믿고 읽을 데이터셋을 만드는 구간**을 채운다. 7장이 채우는 부분은 파란 상자이고, 8장 이후에 이 데이터를 쓰는 부분은 점선이다.

```mermaid
flowchart LR
    accTitle: 7장 데이터 준비가 놓이는 플랫폼 전체 그림
    accDescr: 개발자 PC의 노트북에서 찾은 규칙을 컴포넌트 코드로 옮기고 KFP SDK로 컴파일해 KFP에 올린다. KFP 작업 Pod는 원천을 내려받아 mlpipeline 버킷의 아티팩트와 datasets 버킷의 분할 파일을 남기고 QA를 실행한다. 8장과 9장의 학습은 이 데이터를 읽어 MLflow에 모델을 등록하고, 10장의 BentoML과 Yatai 서빙, 11장의 Evidently 관측이 그 뒤를 잇는다. 파란 상자는 7장, 회색은 앞 장, 주황 점선은 다음 장의 범위다.
    SRC["원천<br/>GroupLens ZIP<br/>신분증 압축 파일"]
    USER["서비스 요청"]
    subgraph PC["개발자 PC"]
        NB["JupyterLab<br/>탐색 노트북"]
        CODE["컴포넌트 코드<br/>@dsl.component"]
        SDK["KFP SDK<br/>compile"]
        BCLI["bentoml CLI<br/>build"]
    end
    subgraph KF["kind 클러스터: kubeflow 네임스페이스"]
        API["KFP UI와 API"]
        POD["작업 Pod<br/>다운로드, 변환, 분할"]
        QA["QA 작업 Pod"]
        MLP[("S3 mlpipeline<br/>KFP 아티팩트")]
        DS[("S3 datasets<br/>업무용 데이터셋")]
        TRAIN["8~9장 학습 작업 Pod"]
    end
    subgraph MLFNS["mlflow"]
        TRK["Tracking과<br/>Model Registry"]
        PG[("Postgres<br/>메타데이터")]
        MART[("S3 mlflow-artifacts")]
    end
    subgraph RDNS["redis"]
        FEAST[("Feast online store")]
        FREG[("S3 feature-registry<br/>Feast registry")]
    end
    subgraph SVNS["yatai-system / 서빙 네임스페이스"]
        YAT["Yatai: Bento 저장소,<br/>이미지 빌더, BentoDeployment<br/>대안: Deployment와 Service"]
        SPOD["10장 서빙 Pod<br/>API 서버와 Runner"]
    end
    subgraph OBS["관측"]
        EVI["Evidently<br/>보고서와 workspace"]
        DRIFT["11장 drift 점검 작업"]
    end
    SRC -->|"① 표본 파일"| NB
    NB -->|"② 열 이름, 짝짓기, 분할 규칙"| CODE
    CODE -->|"③ 파이프라인 함수"| SDK
    SDK -->|"④ 파이프라인 YAML"| API
    API -->|"⑤ 파라미터 seed, dataset"| POD
    SRC -->|"⑥ 원천 압축 파일"| POD
    POD -->|"⑦ Output .path 기록, .uri로 저장"| MLP
    MLP -->|"⑧ 다음 작업의 Input .path"| POD
    POD -->|"⑨ train, val, test parquet"| DS
    DS -->|"⑩ 업로드된 분할과 movies"| QA
    MLP -.->|"⑪ YOLO 분할 아티팩트"| TRAIN
    DS -.->|"⑫ parquet 데이터셋 URI"| TRAIN
    TRAIN -.->|"⑬ 모델, run_id, 데이터 버전"| TRK
    TRK --- PG
    TRK --- MART
    TRK -.->|"⑭ 등록 모델 버전"| BCLI
    BCLI -.->|"⑮ Bento 태그"| YAT
    YAT -.->|"⑯ 컨테이너 이미지"| SPOD
    USER -.->|"⑰ 요청 user_id"| SPOD
    FREG --- FEAST
    FEAST -.->|"⑱ 온라인 피처"| SPOD
    SPOD -.->|"⑲ 현재 입력 윈도우"| DRIFT
    DS -.->|"⑳ 준비 단계의 기준 분포"| DRIFT
    DRIFT -.-> EVI
    classDef thisch fill:#e8f1ff,stroke:#2f6fd6,stroke-width:2px;
    classDef prev fill:#f3f3f3,stroke:#999;
    classDef next fill:#fff6e5,stroke:#d08a00,stroke-dasharray:4 3;
    class NB,CODE,SDK,POD,QA,MLP,DS thisch
    class API,TRK,PG,MART,FEAST,FREG,YAT,EVI prev
    class TRAIN,BCLI,SPOD,DRIFT,USER next
```

| 번호 | 누가 | 무엇을 넘기는가 | 어디에 남는가 | 실습 단계 |
| --- | --- | --- | --- | --- |
| ① | 원천에서 노트북으로 | `ml-latest-small` CSV, 합성 신분증 이미지와 라벨 | PC의 `data` 폴더 | A-3 |
| ② | 노트북에서 컴포넌트 코드로 | `userId`, `movieId` 열 이름, stem 짝짓기, clip 단위 분할 규칙 | 탐색 노트북과 `ch07\*.py` | A-4 |
| ③ | 컴포넌트 코드에서 SDK로 | `@dsl.component`와 `@dsl.pipeline` 함수 | PC의 Python 파일 | B-1 |
| ④ | SDK에서 KFP로 | 컴파일한 파이프라인 YAML | KFP의 파이프라인과 버전 | B-2 |
| ⑤ | KFP에서 작업 Pod로 | `random_state`, `dataset`, 버킷 이름 같은 파라미터 | 실행 기록의 Input Parameters | B-3 |
| ⑥ | 원천에서 작업 Pod로 | GroupLens ZIP, `ch07-raw`의 합성 압축 파일 | 다운로드 작업의 출력 아티팩트 | C-1, D-3 |
| ⑦ | 작업 Pod에서 KFP 아티팩트로 | `output.path`에 쓴 파일과 폴더 | `mlpipeline/v2/artifacts/...`의 `.uri` | B-4, C-3 |
| ⑧ | KFP 아티팩트에서 다음 작업으로 | 앞 작업의 `.uri`를 내려받은 `input.path` | 다음 Pod의 `/minio/mlpipeline/...` | B-4, C-2 |
| ⑨ | 작업 Pod에서 업무용 버킷으로 | train, val, test와 movies parquet | `datasets/ml-latest-small/` | D-3 |
| ⑩ | 업무용 버킷에서 QA로 | 업로드된 네 파일 | QA 로그와 Metrics 아티팩트 | C-3, D-4 |
| ⑪ | KFP 아티팩트에서 학습으로 | YOLO 구조의 train, validation, test 폴더 | 8장 학습 작업의 입력 | 8장 |
| ⑫ | 업무용 버킷에서 학습으로 | `s3://datasets/...` parquet 위치 | 9장 학습 작업의 입력 | 9장 |
| ⑬ | 학습에서 MLflow로 | 모델, `run_id`, 데이터 버전과 지표 | Postgres 메타데이터, `mlflow-artifacts` | 8~9장 |
| ⑭ | MLflow에서 BentoML로 | 등록 모델 버전 | 로컬 Bento 저장소 | 10장 |
| ⑮ | BentoML에서 Yatai로 | Bento 태그 | Yatai의 Bento 저장소 | 6장, 10장 |
| ⑯ | Yatai에서 서빙 Pod로 | 컨테이너 이미지와 BentoDeployment | Deployment와 Service | 6장, 10장 |
| ⑰ | 사용자에서 서빙 Pod로 | 추천할 `user_id` 또는 판별할 이미지 | API 요청 로그 | 10장 |
| ⑱ | Feast에서 서빙 Pod로 | 온라인 피처 | Redis | 4장, 6장 |
| ⑲ | 서빙 Pod에서 drift 점검으로 | 현재 입력 윈도우 | 요청 기록 | 11장 |
| ⑳ | 업무용 버킷에서 drift 점검으로 | 7장 QA에서 확인한 기준 분포 | Evidently 보고서 | 11장 |

Yatai 상자의 '대안'은 6장 실습에서 Yatai 대신 컨테이너로 만든 Bento를 kind의 Deployment와 Service로 띄운 경로를 가리킨다. 7장의 실습에서 실제로 돌리는 것은 ①부터 ⑩까지다. ⑪ 이후는 이 결과가 어디로 이어지는지 보여 주려고 함께 그렸다.

핵심 경로만 떼어 보면 다음과 같다. 노트북에서 정한 규칙이 컴포넌트로 굳고, KFP가 Pod 사이에서 아티팩트를 옮기고, QA를 통과한 데이터만 학습으로 넘어간다.

```mermaid
sequenceDiagram
    accTitle: 노트북 탐색에서 학습 가능한 데이터셋까지의 실행 순서
    accDescr: 노트북에서 정한 규칙을 컴포넌트 코드로 옮겨 컴파일하고 KFP에 올린다. 앞 작업 Pod는 output.path에 파일을 쓰고 launcher가 이를 output.uri로 업로드한다. 다음 작업은 같은 uri를 input.path로 받아 처리하고 업무용 버킷에 결과를 올린다. QA가 통과해야 학습이 데이터셋을 읽는다.
    participant N as JupyterLab
    participant C as 컴포넌트 코드와 SDK
    participant K as KFP API
    participant A as 앞 작업 Pod
    participant S as S3 저장소
    participant B as 다음 작업 Pod
    participant Q as QA 작업 Pod
    participant T as 8~9장 학습
    N->>C: ② 열 이름, 짝짓기, 분할 규칙
    C->>C: ③ compile로 YAML 생성
    C->>K: ④ 업로드와 실행 요청
    K->>A: ⑤ Pod 생성과 파라미터
    S->>A: ⑥ 원천 압축 파일
    A->>A: output.path에 파일 기록
    A->>S: ⑦ 종료 뒤 output.uri로 업로드
    K->>B: 입력 아티팩트의 uri
    S->>B: ⑧ input.path로 내려받기
    B->>S: ⑨ datasets 버킷에 parquet 업로드
    K->>Q: 업로드 작업이 끝난 뒤 실행
    S->>Q: ⑩ 분할과 movies 읽기
    alt 검사 통과
        Q-->>K: QA passed와 Metrics
        S-->>T: ⑪ ⑫ 데이터셋 위치
    else 검사 실패
        Q-->>K: 실패 상태와 진단 로그
        Note over T: 학습을 시작하지 않는다
    end
```

## 노트북에서 데이터의 의미와 처리 규칙을 찾는다 {#notebook-concepts}

데이터 분석은 파일을 열어 보고 그래프 몇 장을 그리는 데서 끝나지 않는다. 한 행이나 이미지 한 장이 무엇을 뜻하는지, 정답은 어떻게 만들어졌는지 알아내야 한다. 학습과 평가를 흔들 조건도 이때 찾는다.

| 관점 | 신분증 탐지 | 영화 추천 |
| --- | --- | --- |
| 표본의 단위 | 이미지와 그 안의 문서 객체 | 사용자가 영화에 남긴 평점 |
| 관측 조건 | 촬영 기기, 조명, 배경, 회전과 문서 유형 | 사용자 활동량, 영화 노출과 평가 시점 |
| 정답의 의미 | 클래스와 객체 위치 | 관측된 선호와 평점 |
| 확인할 분포 | 클래스별 수, 박스 크기, 촬영 조건 | 사용자별, 영화별 평점 수, 평점 값과 시간 |
| 누락의 의미 | 라벨 누락인지 객체가 없는 이미지인지 | 보지 않았는지, 봤지만 평가하지 않았는지 |

평점이 비어 있다고 낮은 점수를 준 것은 아니다. 라벨 없는 이미지도 진짜 배경 사진인지, 주석이 빠진 것인지에 따라 다르게 다뤄야 한다. 결측이나 빈 파일을 0으로 채우기 전에 그 빈칸이 무슨 뜻인지부터 정한다.

탐색에서 정한 정규화, 결측 대체, 범주 사전은 학습 데이터로만 fit하고, 다른 분할에는 그 변환을 그대로 적용한다. 전체 데이터로 통계를 낸 뒤 나누면 검증과 테스트의 정보가 학습에 새어 들어갈 수 있다.

### 자유롭게 탐색하되 실행 조건은 다시 만들 수 있어야 한다

큰 자료를 PC로 계속 복사하면 전송 시간과 저장 공간이 든다. PC에 없는 GPU나 메모리는 쓸 수도 없다. Kubeflow Notebooks에서는 개발자가 브라우저로 작업하고, 실제 분석은 데이터와 가까운 클러스터에서 돈다.

공유 클러스터에서 각자 원하는 환경을 끝없이 띄울 수는 없다. 관리자가 쓸 수 있는 이미지와 자원 범위를 정하고, 개발자는 그 안에서 작업에 맞는 환경을 고른다. 같은 클러스터에 있다고 원천 데이터 권한이 생기거나 파이프라인과 환경이 저절로 맞춰지지도 않는다.

책이 workspace, data volume, PodDefault, 이미지 메뉴를 차례로 다루는 것도 이 조건을 하나씩 정하기 위해서다. 볼륨은 무엇을 남기고 공유할지, PodDefault는 어떤 공통 설정을 넣을지, 이미지는 어떤 의존성으로 실행할지를 정한다. 탐색을 묶어 두려는 장치라기보다, 탐색에서 얻은 결과를 다른 실행으로 넘기기 위한 바탕이다.

사용자가 Notebook을 만들면 Kubeflow의 제어기가 거기 적힌 이미지, 자원, 볼륨을 실제 워크로드로 띄운다. Notebook 리소스는 원하는 구성을 적은 선언이다. 브라우저 요청을 받는 것은 그 구성으로 뜬 서버다.

```mermaid
flowchart LR
    accTitle: Kubeflow Notebook의 선언과 실행 상태
    accDescr: 사용자는 노트북 UI에서 이미지, 자원과 볼륨을 고른다. Notebook 리소스의 구성을 제어기가 워크로드로 반영하고 브라우저는 실행된 노트북 서버에 접속한다. 영속 데이터는 Pod의 메모리가 아니라 연결한 저장소에 남는다.
    U["사용자와 노트북 UI"] --> N["Notebook 리소스<br/>이미지, 자원, 볼륨 선언"]
    N --> C["Notebook Controller"]
    C --> P["Notebook 서버 Pod"]
    B["브라우저"] -->|"서비스와 접속 경로"| P
    P --> V[("Workspace와 data volume")]
    P --> S[("데이터 저장소")]
```

커널 메모리, Pod의 임시 파일, 영속 볼륨은 수명이 저마다 다르다. Pod가 바뀌면 메모리의 DataFrame은 사라지고, PVC로 연결한 파일은 볼륨과 보존 정책에 따라 남을 수 있다. 노트북 파일이 남았다고 셀을 실행한 상태까지 돌아오지는 않는다.

### 이미지 계층과 개발 환경의 재현성

노트북 이미지는 층을 쌓은 구조다. OS와 시스템 라이브러리 위에 노트북 서버, ML 라이브러리, 프로젝트 의존성이 차례로 올라간다. GPU를 쓰려면 CUDA 같은 실행 조건도 맞춰야 한다.

```mermaid
flowchart TD
    accTitle: Kubeflow 공식 노트북 이미지의 계층
    accDescr: 공통 base image에서 JupyterLab과 code-server가 나뉜다. JupyterLab 위에 SciPy, PyTorch, TensorFlow 환경을 만들고 필요한 경우 CUDA를 포함한 이미지를 선택한다.
    BASE["공통 base image"] --> JUP["JupyterLab"]
    BASE --> CODE["code-server"]
    JUP --> SCI["SciPy"]
    JUP --> PT["PyTorch"]
    JUP --> TF["TensorFlow"]
    PT --> PTGPU["PyTorch + CUDA"]
    TF --> TFGPU["TensorFlow + CUDA"]
```

그림 7-1. 공통 기반에서 개발 서버와 ML 환경이 나뉘는 이미지 계층. 출처: [Kubeflow Container Images](https://github.com/kubeflow/website/blob/796db696b45fd48ef5fe0ab20e82217a322529b2/content/en/docs/components/notebooks/container-images.md), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 공식 도식의 일부 계층을 골라 재구성했다.

| 계층 | 포함하는 것 | 관리 이유 |
| --- | --- | --- |
| 기본 OS와 런타임 | Python, 시스템 라이브러리와 필요한 GPU 런타임 | 네이티브 의존성과 실행 기반 |
| 노트북 서버 | JupyterLab 같은 브라우저 개발 환경 | 서버 시작, 접속과 작업 사용자 구성 |
| 공통 ML 환경 | 데이터 처리와 학습 라이브러리 | 팀에서 함께 쓰는 의존성 |
| 프로젝트 환경 | 추가 패키지와 설정 | 특정 분석과 전처리 코드의 요구사항 |
| 외부 데이터와 작업 볼륨 | 원천 데이터, 노트북과 결과 | 이미지와 분리한 영속성과 버전 관리 |

셀에서 패키지를 설치해도 이미지에는 남지 않는다. 같은 환경을 다시 만들려면 의존성 선언과 이미지 빌드 기록이 있어야 한다. 이미지 생성, 검사, 레지스트리 게시를 CI/CD에 넣어 두면 공통 환경을 몇 번이고 다시 준비할 수 있다.

탐색 이미지와 파이프라인 이미지는 기반을 공유해도 되지만 꼭 같을 필요는 없다. 파이프라인에는 노트북 UI가 필요 없을 수도 있다. 맞춰야 하는 것은 전처리와 실행에 쓰는 의존성과 그 버전이다.

### 자원, PodDefault와 관리자가 제공하는 선택지

CPU와 메모리의 requests는 스케줄링에 쓰는 요구량이고, limits는 실행 중 넘을 수 없는 한도다. 큰 파일을 통째로 메모리에 읽으면 노트북이 멀쩡히 떠 있다가도 한도에 걸려 종료될 수 있다. GPU는 고르는 것만으로 부족하다. 그 자원이 있는 노드와 맞는 이미지도 있어야 한다.

Affinity는 어느 노드에 놓을지에 대한 조건이나 선호를 적고, toleration은 특정 taint를 허용한다고 적는다. PodDefault는 조건에 맞는 Pod에 공통 환경 변수나 볼륨을 넣어 주는 Kubeflow 설정이다. 셋 다 배치와 설정을 다룰 뿐, 데이터 접근 권한이나 올바른 전처리까지 책임지지는 않는다.

책은 관리자가 노트북 웹 앱의 이미지 목록과 자원 기본값을 고치는 부분도 다룬다. 메뉴에 선택지를 두는 일과 실제 Pod에 들어가는 설정은 따로 봐야 한다. 플랫폼은 사용자에게 필요한 환경을 내주면서 클러스터 용량, 작업 보존, 유휴 종료도 함께 관리한다.

## 탐색 규칙을 컴포넌트의 입력과 출력으로 고정한다 {#pipeline-data-concepts}

탐색 환경과 원본이 준비되면 다운로드, 변환, 분할을 반복 실행할 작업으로 옮긴다. 노트북 셀은 메모리를 공유하지만 파이프라인의 작업은 그렇지 않다. 입력, 출력, 실행 환경을 명시해서 이어야 한다. 파일을 만든 작업이 성공했는지와 다음 작업이 그 파일을 읽을 수 있는지는 따로 확인할 일이다.

### 탐색 코드를 컴포넌트로 바꾸는 이유

노트북은 셀 실행 순서와 앞서 남은 메모리 상태에 기대기 쉽다. 컴포넌트는 입력, 출력, 실행 환경을 인터페이스로 못 박는다. 그래서 필요한 작업만 다시 돌릴 수 있고 다른 파이프라인에서도 가져다 쓸 수 있다.

파이프라인 정의는 이 컴포넌트들의 의존 관계를 조립한다. Python 코드를 컴파일하는 순간에는 데이터를 받지도, 학습하지도 않는다. 실행 명세가 만들어질 뿐이고, 실제 입력 값과 파일 경로는 작업이 돌 때 정해진다.

책의 농담 생성, 단어 수 세기, 결과 출력 예제는 ML 알고리즘을 가르치려는 것이 아니다. 메모리를 공유하지 않는 세 작업을 어떻게 잇는지 작은 데이터로 보여 준다. 처음에는 농담 문자열을 값으로 넘기고, 다음 예제에서는 농담을 파일에 써서 아티팩트로 넘긴다. 뒤에서 이미지 묶음과 평점 파일을 잇는 원리가 바로 이 차이다.

### 세 가지 컴포넌트 작성 방식

| 방식 | 코드와 의존성 준비 | 적합한 상황 |
| --- | --- | --- |
| Lightweight Python component | 함수 코드를 추출하고 `base_image`, `packages_to_install`로 실행 환경 구성 | 작고 독립적인 Python 처리 |
| Containerized Python component | Python 컴포넌트 코드와 의존성을 `target_image` 대상으로 미리 빌드 | 반복 설치를 줄이고 실행 환경을 고정할 때 |
| Container component | 준비된 이미지의 실행 명령과 인자를 `ContainerSpec`으로 연결 | 별도 프로그램, 시스템 의존성이나 복잡한 실행 구조 |

Lightweight 컴포넌트는 개발 PC의 가상환경을 통째로 가져가지 않는다. 필요한 모듈은 함수 안에서 import하고, 그 의존성은 실행 이미지에 있어야 한다. 바깥 셀의 변수나 옆의 Python 파일이 함께 실려 간다고 가정하면 안 된다.

`packages_to_install`은 작업이 시작될 때 패키지를 설치해 주니 간단하다. 대신 네트워크와 설치 시간이 실행 조건에 끼어든다. 미리 빌드한 이미지는 시작 시 설치를 줄이지만, 이미지를 빌드하고 갱신하는 일이 새로 생긴다. `target_image`를 적거나 YAML을 컴파일했다고 그 이미지가 빌드되거나 게시되지는 않는다.

### 값 전달과 파일 전달

KFP는 작은 설정과 결과는 파라미터로, 데이터셋과 모델 같은 산출물은 아티팩트로 나눈다.

| 구분 | 파라미터 | 아티팩트 |
| --- | --- | --- |
| 의미 | 작은 값의 전달 | 파일 내용과 산출물 식별 정보의 전달 |
| 예 | seed, 버킷 이름, 행 수, 작은 설정 목록 | 이미지 묶음, Parquet, 모델과 보고서 |
| 인터페이스 | `str`, `int`, `float`, `bool` 등 지원 타입 | `Input[Dataset]`, `Output[Model]` 등 |
| 전달 내용 | 직렬화된 값 | URI, 메타데이터와 실행 시 사용할 경로 |
| 책임 | 값의 형식과 의미 정의 | 선언한 출력에 파일 작성, 내용의 검증 |

저장소 URI를 문자열 파라미터로 넘길 수도 있다. 그러면 파일을 읽고 권한과 버전을 확인하는 일은 코드 몫이 된다. 경로처럼 생긴 문자열이라고 KFP가 파일 아티팩트로 추적해 주지는 않는다.

KFP 아티팩트에는 세 가지가 붙는다. `.uri`는 저장 위치이고, `.path`는 작업 안에서 읽고 쓸 로컬 경로이며, `.metadata`에는 부가 정보를 남길 수 있다. 출력 아티팩트는 받은 경로에 내용을 써야 한다. 다른 폴더에 만든 파일까지 알아서 모아 주지는 않는다.

다운로드 컴포넌트가 `output_dataset.path`에 파일을 쓰면, 다음 컴포넌트는 자기 `input_dataset.path`에서 그 산출물을 읽는다. 두 Pod의 경로 문자열은 달라도 된다. 같아야 하는 것은 전달되는 파일의 내용과 구조다. 컴포넌트를 호출할 때 출력 경로를 넘기지 않아도 되는 것은 런타임이 출력 아티팩트와 경로를 마련해 주기 때문이다.

책은 파일 경로, MinIO 위치, 아티팩트를 오가며 설명한다. 이때 가려 볼 것은 하나다. 경로가 가리키는 내용이 실제 데이터인가, 다른 저장소를 가리키는 참조인가. 파일 내용이 URI 한 줄이면 다음 코드는 그 URI를 읽어 데이터를 다시 가져와야 한다. 압축을 푼 데이터 자체를 썼다면 다음 코드는 그 디렉터리 구조를 읽는다. `Output[Dataset]`으로 선언했다고 두 경우가 같아지지는 않는다.

경로로 넘긴다고 큰 데이터를 옮기는 비용이 사라지지도 않는다. 제어 메시지에 데이터를 싣지 않을 뿐, 실제 파일은 저장소와 작업 사이를 오간다. 읽을 열과 묶음을 줄이거나 원격 자료를 직접 읽는 것은 별개의 전략이다. 아티팩트 전달이 메모리 초과를 막아 주지는 않는다.

![KFP API 서버와 파이프라인 작업 네임스페이스가 객체 저장소에 접근하고, 작업 아티팩트의 저장소는 Launcher 설정을 따르는 구조.](https://raw.githubusercontent.com/kubeflow/website/796db696b45fd48ef5fe0ab20e82217a322529b2/content/en/docs/components/pipelines/operator-guides/images/kfp-obj-store-configurations.png)

그림 7-2. 파이프라인 정의와 작업 아티팩트의 객체 저장소 설정. 출처: [Kubeflow 공식 도식](https://github.com/kubeflow/website/blob/796db696b45fd48ef5fe0ab20e82217a322529b2/content/en/docs/components/pipelines/operator-guides/images/kfp-obj-store-configurations.png), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 원본 도식을 변경 없이 사용했다.

그림에서 파이프라인 정의를 저장하는 API 서버와, 실제 산출물을 읽고 쓰는 작업 쪽 설정은 서로 다른 지점이다. 한 Pod 안의 경로가 다른 Pod에서 그대로 보이는 것은 아니다. 둘 사이를 잇는 것은 아티팩트 저장소와 실행 설정이다.

### 아티팩트 타입과 lineage

| 타입 | 표현하는 산출물 |
| --- | --- |
| `Dataset` | 학습과 검증 등에 사용할 데이터 |
| `Model` | 학습한 모델 파일과 관련 정보 |
| `Metrics` | 이름과 수치로 된 평가 결과 |
| `ClassificationMetrics` | 혼동행렬 등 분류 평가 정보 |
| `HTML`, `Markdown` | 사람이 읽을 보고서 |
| `Artifact` | 더 구체적인 타입으로 표현하지 않은 일반 산출물 |

![여러 KFP 예제 실행의 accuracy와 precision을 비교하고 혼동행렬, ROC, HTML, Markdown 탭으로 결과를 구분하는 화면.](https://raw.githubusercontent.com/kubeflow/website/796db696b45fd48ef5fe0ab20e82217a322529b2/content/en/docs/images/pipelines/v2/run-comparison/scalar-metrics.png)

그림 7-3. KFP 공식 예제의 평가 지표 비교 화면. 출처: [Kubeflow run comparison 이미지](https://github.com/kubeflow/website/blob/796db696b45fd48ef5fe0ab20e82217a322529b2/content/en/docs/images/pipelines/v2/run-comparison/scalar-metrics.png), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). 이 글의 탐지나 추천 모델에서 측정한 점수가 아니다.

타입은 컴포넌트 연결 검사, 결과 표시, 산출물 이력에 쓰인다. 여러 작업이 같은 이름의 파일을 만들어도 어느 실행이 어떤 입력으로 만들었는지 가려낼 수 있다. KFP는 이런 입출력 관계를 메타데이터로 관리한다.

하지만 `Dataset` 타입이 열 이름이나 평점 범위를 검사해 주지는 않는다. 모델을 만든 데이터를 추적할 수 있다는 것과 그 데이터가 적합하다는 것은 다른 이야기다. 스키마와 도메인 검사는 따로 써야 한다.

### 캐시, 외부 상태와 실행 비용

컴포넌트를 나누면 중간 결과를 재사용할 수 있다. 그런데 같은 URI의 파일 내용이 바뀌어도 입력 식별자에 반영되지 않으면 오래된 결과를 쓰게 된다. 원천 checksum이나 스냅샷을 입력으로 남기고, 재사용해도 되는 작업과 매번 돌릴 작업을 나눈다.

캐시를 모두 끄면 다운로드와 변환을 매번 반복한다. 컴포넌트를 너무 잘게 쪼개면 Pod 시작과 파일 이동 비용도 커진다. 재사용, 자원, 실패와 재시도의 단위가 달라지는 지점에서 나누는 편이 낫다.

## 모델이 배울 관계에 맞춰 데이터와 분할을 검증한다 {#dataset-concepts}

전달 경로가 이어져도 산출물 내용이 맞는지는 별개의 문제다. 이미지에서는 대상의 위치와 라벨이, 평점에서는 사용자와 영화의 관계가 학습 입력이 된다. 책은 비슷한 다운로드와 분할을 두 번 보여 주지만, 탐지는 이미지와 위치 라벨의 대응을, 추천은 사용자, 영화, 관측 시점의 관계를 지켜야 한다. 공통 컴포넌트는 재사용하더라도 도메인 검사를 따로 두는 이유다.

### 탐지 데이터는 이미지와 위치 라벨이 한 표본이다

객체 탐지는 이미지 안에 무엇이 어디에 있는지 배운다. 이미지 전체에 라벨 하나를 붙이는 분류와도, 픽셀마다 영역을 정답으로 주는 분할과도 다르다. 이 장의 YOLO 데이터에서는 클래스와 bounding box의 조합이 핵심이다.

YOLO 형식에서 객체 하나는 `class_id x_center y_center width height` 한 행이다. 클래스 ID는 클래스 목록과 이어지고, 좌표는 이미지 크기로 정규화한다.

```text
이미지 크기: W, H
픽셀 박스: (x_min, y_min), (x_max, y_max)

x_center = (x_min + x_max) / (2 * W)
y_center = (y_min + y_max) / (2 * H)
width    = (x_max - x_min) / W
height   = (y_max - y_min) / H
```

객체가 여러 개면 라벨도 여러 행이다. 원천이 문서의 네 꼭짓점을 준다면 축에 맞춘 박스로 바꿀지, 회전 박스를 쓸지부터 정한다. 주석 형식이 다른 좌표를 그대로 옮기면 같은 데이터가 되지 않는다.

책의 프로젝트는 이미 YOLO 형식으로 정리된 배포 데이터를 전제로 한다. 다운로드와 분할 컴포넌트가 원천 주석을 변환해 주는 것은 아니다. 그래서 같은 stem의 이미지와 라벨, 클래스 매핑, 좌표 의미를 먼저 확인해야 한다. 파일 수가 맞아도 엉뚱한 이미지의 라벨과 짝지어지면, 작업은 성공하고 정답만 틀린다.

### 추천 데이터는 사용자와 영화 사이의 관측된 관계다

추천은 사용자와 아이템 사이에 관측된 상호작용을 다룬다. MovieLens 평점은 사용자가 직접 남긴 명시적 피드백이다. 클릭이나 시청 기록에서 추정하는 암묵적 피드백과는 성격이 다르다. 관측되지 않은 사용자와 영화 조합을 모두 낮은 평점의 정답으로 만들 수는 없다.

사용자 ID와 영화 ID는 조인과 모델 입력의 키다. 파일끼리의 일관성과 모델이 쓰는 ID 매핑을 지켜야 한다. 원천 ID의 최대값이 곧 서로 다른 ID의 개수라고 볼 수도 없다.

### CSV, Parquet과 데이터 규모

CSV는 사람이 보기 쉽지만 값의 타입, 구분자, 인코딩을 따로 정해야 한다. Parquet은 타입을 가진 열 단위 형식이라 압축과 필요한 열만 읽기에 유리하다. 형식 변환은 물리적 표현을 바꿀 뿐, 잘못된 값이나 중복을 고치지는 않는다.

Parquet을 써도 DataFrame 전체를 메모리에 올리는 코드라면 한계는 그대로다. 코드가 전체를 읽는지, 필요한 열만 읽는지, 묶음으로 처리하는지를 Pod의 메모리 요구와 함께 봐야 한다.

MovieLens 예제가 다운로드, 압축 해제, Parquet 변환, 업로드를 나눈 것은 데이터 준비의 책임을 보여 주기 위해서다. 영화와 평점 변환에 같은 컴포넌트를 재사용할 수 있지만, 모든 변환을 별도 Pod로 둬야 한다는 설계 규칙은 아니다. 책도 실제 운영에서는 데이터 이동 비용 때문에 일부 작업을 합칠 수 있다고 말한다.

MovieLens의 `ratings.csv`에는 `userId`, `movieId`, `rating`, `timestamp`가 있다. [원천 설명](https://files.grouplens.org/datasets/movielens/ml-25m-README.html)에 따르면 평점은 0.5~5.0의 반점 단위이고 timestamp는 UTC 기준 Unix 초다. 시간 기준과 값의 범위도 스키마에 들어간다.

### 분할은 평가하려는 상황을 만드는 작업

| 분할 | 주된 용도 | 다른 분할과 구분할 일 |
| --- | --- | --- |
| 학습 | 모델과 전처리의 파라미터 학습 | 학습에 사용한 통계와 사전 기록 |
| 검증 | 설정과 후보 선택, 개발 중 평가 | 선택 과정의 영향을 받는다는 점 인식 |
| 테스트 | 선택을 마친 뒤 독립적인 최종 평가 | 반복 확인하며 모델을 고르는 자료로 쓰지 않음 |

무작위 분할은 표본이 서로 충분히 독립이라는 가정에서 출발한다. 같은 영상의 프레임이나 같은 문서를 여러 번 찍은 사진은 독립 표본으로 보기 어렵다. 처음 보는 문서에서의 성능을 알고 싶다면 문서나 영상 단위로 나누는 편이 맞을 수 있다.

추천에서 미래 행동을 예측하려면 시간이 중요하다. 과거 기록으로 학습하고 이후 행동으로 평가하는 것과, 같은 시기의 평점 일부를 가려 놓고 맞히는 것은 다른 문제다. 신규 사용자와 신규 영화의 cold start도 따로 봐야 한다.

시드를 고정하면 정해진 절차의 무작위성만 통제된다. 평가 설계가 잘못됐다면 그 잘못은 그대로 남는다. 분할 비율보다 어떤 표본과 시간이 경계를 넘으면 안 되는지를 먼저 정한다.

그래서 책의 75/15/10 분할은 파일을 세 산출물로 나누는 예제로 읽는 것이 맞다. 모든 탐지와 추천 서비스에 맞는 답은 아니다. 같은 문서의 비슷한 사진이 여러 분할에 흩어지거나 미래 평점이 과거 학습에 섞이면, 평가가 실제보다 쉬워진다. 서비스가 처음 마주칠 대상과 시점을 정하고 거기에 맞춰 나눈다.

### 품질 검사와 재현 가능한 데이터 준비

데이터 준비는 다운로드, 파싱, 변환, 분할, 저장, QA가 이어진 사슬이다. 각 단계가 성공해도 다음 단계가 원하는 데이터인지는 검사해 봐야 안다.

| 검사 계층 | 예 |
| --- | --- |
| 파일과 저장소 | 다운로드 성공, 압축 형식, 필요한 객체 존재 |
| 스키마 | 열 이름과 타입, 이미지와 라벨의 형식, 좌표 단위 |
| 의미와 관계 | 평점 범위, ID 조인, 이미지와 라벨의 대응 |
| 분할과 누수 | 같은 원천 그룹과 미래 정보의 혼입 여부 |
| 계보와 버전 | 원천 checksum, 변환 코드, 분할 기준과 결과 위치 |

로그는 어느 단계가 실패했는지 찾는 데 쓰고, QA는 넘기면 안 되는 입력을 걸러 낸다. 데이터를 통째로 로그에 찍는 것과 재현 가능한 진단 정보를 남기는 것은 다르다. 원천 식별자, 행과 파일 수, 스키마, 실패 유형만 남겨도 데이터를 다 출력하지 않고 조사 범위를 좁힐 수 있다.

책의 파일 목록 출력과 MovieLens QA는 이런 검증의 출발점이다. 고정한 원본 코드의 train QA는 열 수와 최소 행 수만 본다. 평점 범위, ID 관계, 다른 분할은 아직 검사하지 않는다. **파이프라인의 초록색 성공 표시는 구현한 작업이 끝났다는 뜻일 뿐, 구현하지 않은 데이터 조건까지 보증하지 않는다.**

이 구분이 필요한 까닭은 데이터 오류가 꼭 학습 실패로 드러나지는 않아서다. 이미지와 라벨이 어긋나거나 미래 평점이 섞여도 학습은 잘 돈다. 준비 단계에서 기대 조건을 적고 검사해야, 나중에 나온 점수가 무엇을 평가한 결과인지 설명할 수 있다.

## 데이터 준비와 서빙을 잇는 계약 {#training-serving-contract}

이 검증 기준은 학습 한 번으로 쓰임이 끝나지 않는다. 6장에서 본 API와 관측 작업도 같은 의미의 피처와 버전을 알아야 한다. 원천에서 만든 데이터셋, 학습 때 fit한 전처리, 서비스 입력을 이어 두어야 변환 오류와 실제 분포 변화를 가를 수 있다.

### 원천 파일에서 모델 입력까지 무엇이 바뀌는가

준비 단계의 출력은 학습 코드만 읽는 파일이 아니다. 서비스는 같은 의미의 입력을 만들고, 관측 작업은 그 입력을 맞는 기준과 비교해야 한다.

```mermaid
flowchart TD
    accTitle: 데이터 준비에서 학습, 서빙과 관측으로 이어지는 계약
    accDescr: 원천 스냅샷을 스키마와 의미 규칙으로 검증하고 분할 이력을 남긴다. 학습 데이터로 fit한 전처리는 모델과 함께 버전으로 관리한다. 서빙은 호환되는 계약을 사용하고 실제 입력을 기록한다. 모니터링은 같은 표현의 기준 데이터와 서빙 입력을 비교한다.
    RAW[("원천 스냅샷")] --> QA["스키마, 의미, 관계 검사"]
    QA --> SPLIT["분할과 manifest<br/>샘플, 그룹, 시각 기록"]
    SPLIT --> TRAIN["학습 분할"]
    SPLIT --> EVAL["분리된 평가 분할"]
    TRAIN --> FIT["전처리 fit와 모델 학습"]
    FIT --> BUNDLE["모델 + 전처리 + 스키마 버전"]
    EVAL --> CHECK["평가와 적합성 확인"]
    BUNDLE --> CHECK
    CHECK --> SERVE["같은 계약으로 서빙"]
    QA --> REF[("비교할 표현과 기간을 정한 기준 데이터")]
    SERVE --> LOG[("실제 입력, 예측, 버전 기록")]
    REF --> MON["품질, skew, drift 관측"]
    LOG --> MON
```

그림은 계약을 지키기 위한 참조 구조다. 저자 코드가 이 산출물을 모두 자동으로 등록해 주는 것은 아니다. 남겨 둘 버전은 종류별로 나눠 볼 수 있다.

| 산출물 | 다음 단계에 필요한 정보 |
| --- | --- |
| 원천 스냅샷 | 출처, 수집 시각과 내용의 식별자 |
| 스키마와 의미 규칙 | 열과 타입, 좌표, 시간, 평점의 단위와 허용 범위 |
| 분할 manifest | 어느 샘플, 그룹, 기간을 각 분할에 넣었는지 |
| 변환 코드와 실행 이미지 | 어떤 코드와 의존성으로 데이터를 만들었는지 |
| fit한 전처리 | 범주 사전, 스케일과 결측 대체값이나 ID 매핑 |
| QA 결과 | 검사한 규칙, 실패 항목과 평가 대상 |
| 관측 기준 | 어떤 모델, 표현, 집단과 기간을 비교하는 reference인지 |

`latest` 경로의 파일을 덮어쓰거나 seed 하나만 저장하면 이 관계는 되살리기 어렵다. 다시 찾아야 하는 것은 같은 이름의 파일이 아니라 같은 내용과 처리 과정이다.

### 스키마 위반, training-serving skew와 drift의 차이

[TensorFlow Data Validation](https://www.tensorflow.org/tfx/data_validation/get_started)은 스키마 검증, 학습과 서빙 사이의 skew, 시점이 다른 데이터 사이의 drift를 나눠 다룬다. 이 장의 환경에 TFDV를 넣자는 것은 아니다. 검사 목적을 나눠 보는 예로 빌려 왔다.

| 구분 | 묻는 것 | 예 |
| --- | --- | --- |
| 스키마와 의미 위반 | 이 데이터가 합의한 형식과 값의 조건에 맞는가 | `rating`이 문자열, 좌표 단위 오류, 필수 키 결측 |
| Training-serving skew | 학습과 서비스가 같은 의미의 입력을 만드는가 | 학습은 UTC 초, 서비스는 밀리초를 사용 |
| 시간에 따른 drift | 같은 의미로 측정한 데이터의 분포가 달라졌는가 | 새 사용자 집단 유입으로 선호와 직업 구성이 변화 |

두 분포가 다르다는 관측만으로 원인을 정할 수는 없다. 분포는 사용자 환경이 바뀌어서도, 파싱이나 변환이 틀려서도 달라진다. 계약과 데이터 생성 경로가 같은지부터 확인한다.

학습 데이터에는 정답 열이 있지만 서빙 입력에는 없을 수 있다. 그러니 학습과 서빙이 모든 열을 글자 그대로 공유해야 한다는 규칙도 맞지 않는다. 예상된 차이는 스키마에 적어 두고, 모델이 실제로 쓰는 피처의 계약을 맞춘다.

### 같은 변환과 같은 시점이라는 조건

범주 사전이나 스케일을 학습 때 만들었다면, 추론 때 입력 한 건을 보고 다시 만들지 않는다. fit은 학습 데이터에서 하고, 검증, 테스트, 서빙에는 같은 변환을 적용한다.

| 프로젝트 | 유지할 계약 | 깨졌을 때의 결과 |
| --- | --- | --- |
| 소득 분류 | 범주 인코딩, 열 순서와 피처 최신성 | 같은 열 수라도 다른 의미의 모델 입력 |
| 객체 탐지 | 클래스 매핑, 이미지 전처리와 좌표 정의 | 다른 클래스 해석이나 잘못된 박스 |
| 영화 추천 | 사용자 ID와 영화 ID의 매핑, 사용 가능한 이력의 시점 | 다른 아이템을 가리키거나 미래 행동 혼입 |

이미지 크기 조정이나 픽셀 정규화처럼 학습과 추론 모두에 필요한 전처리가 있고, 학습 자료를 늘리는 augmentation이 있다. 둘은 구분한다. 학습에 쓴 무작위 증강을 평가나 서비스에 똑같이 적용해야 하는 것은 아니다.

피처 저장소를 쓴다면 조회 시점도 계약에 들어간다. 학습 표본의 기준 시각 뒤에야 알려진 값을 붙이거나 과거 이력을 현재 최신값으로 덮어쓰면, 실제 서비스 조건을 재현하지 못한다. 저장소를 두었다고 point-in-time 조건이 지켜지는 것은 아니니 따로 확인한다.

### 준비 단계의 통계가 운영 관측의 기준이 된다

소득 분류 서비스에서 학력과 직업 분포를 지켜보려면 어떤 학습 집단과 피처 정의를 기준으로 삼았는지 알아야 한다. 인코딩 전 범주 분포와 인코딩 후 수치 열은 서로 직접 비교할 수 없다.

추천에서는 사용자 활동량이나 영화별 평점 수가, 탐지에서는 촬영 조건이나 문서 유형의 변화가 조사의 출발점이 될 수 있다. 어떤 집단과 표현을 비교할지 먼저 정하고, 그에 필요한 자료나 통계를 준비 단계에서 남긴다. 표 데이터용 분포 검사를 이미지 픽셀에 그대로 돌린다고 관측 설계가 끝나지는 않는다.

[6장의 관측 구조](../06-productionizing-models/#production-monitoring)는 이 reference와 서비스의 실제 입력 기록을 잇는다. 사용자 ID만 저장해 두고 나중에 최신 피처를 다시 읽으면, 당시 어떤 값으로 예측했는지 알 길이 없다. 데이터 준비와 운영 관측이 같은 버전과 같은 시간 개념을 써야 하는 이유다.

### 실패를 어디에서 중단할지 정한다

노트북은 탐색을 돕는다. 운영 파이프라인은 언제 실패하고 언제 다시 돌릴지까지 분명해야 한다. 스키마 위반이나 이미지와 라벨의 불일치는 학습 전에 멈출 이유가 될 수 있다. 다운로드의 일시 장애와 달리, 다시 시도한다고 잘못된 데이터가 맞아지지는 않는다.

일부 출력만 남은 실행과 검증을 마친 데이터 묶음도 구분한다. 같은 위치에 덮어쓰는 구성이라면 일부 파일만 새 버전이 되는 일을 막거나, manifest로 일관된 완료 단위를 식별할 수 있어야 한다.

품질 검사를 통과한 데이터로 학습했다고 출시가 승인된 것은 아니다. 데이터 QA, 모델 평가, 서빙 성능, 배포 전환은 이어져 있지만 책임이 다르다. 이 경계가 살아 있어야 6장의 drift 경고가 데이터 수정, 추가 평가, 재학습 중 어디로 이어질지 판단할 수 있다.

결국 7장이 만드는 것은 다운로드가 끝난 폴더가 아니라, 다음 단계가 의미를 알고 읽을 수 있는 데이터셋이다. 아티팩트 전달과 QA를 따로 두는 이유도 여기 있다. 학습이 정상 종료됐다고 입력이 옳았다는 뜻은 아니다. 원천, 라벨, 분할, 버전의 연결이 분명해야 다음 장에서 성능 차이를 모델의 변화로 읽을 수 있고, 서빙에서도 같은 계약을 지킬 수 있다.

## 실습 순서 {#book-ch07-sop}

이 실습은 책의 두 데이터 준비 파이프라인을 [4~5장](../04-experiments-features-pipelines/)에서 만든 `book-env` 클러스터에서 돌린다. 저자 코드를 먼저 그대로 실행해 어디서 멈추는지 보고, 필요한 부분만 고친 컴포넌트로 다시 실행해 KFP 화면과 저장소에서 결과를 확인한다.

```mermaid
flowchart LR
    accTitle: 책 7장을 따라가는 실습 순서
    accDescr: 탐색 환경과 노트북을 준비하고 파라미터와 아티팩트 전달을 작은 파이프라인으로 확인한다. 이어서 신분증 탐지 데이터와 MovieLens 데이터를 준비하는 파이프라인을 원본과 수정본으로 실행하고 결과를 정리한다.
    A["A. 탐색 환경과 노트북"] --> B["B. 파라미터와<br/>아티팩트 전달"]
    B --> C["C. 신분증 탐지<br/>데이터 준비"]
    C --> D["D. MovieLens<br/>준비와 QA"]
    D --> E["E. 결과 정리와<br/>다음 단계"]
```

| 구간 | 끝났을 때 남는 것 |
| --- | --- |
| A. 탐색 환경 | `.venv-ch07`, 저자 저장소 두 개, `data\ml-latest-small`, 합성 신분증 120장, 실행된 탐색 노트북 |
| B. 데이터 전달 | KFP 실험 `ch07-data-prep`, 성공한 joke 실행 두 개 |
| C. 신분증 데이터 | `ch07-raw` 버킷의 원천, 실패한 원본 분할 실행, 성공한 수정 실행과 세 분할 아티팩트 |
| D. MovieLens | `datasets/ml-latest-small/`의 parquet 네 개, 원본 분할과 QA의 실패 기록, 수정 QA 통과 기록 |
| E. 정리 | 다음 장이 읽을 데이터 위치와 계약, 정리 명령 |

책과 달라진 조건은 다음과 같다. 자세한 이유와 수정 내용은 해당 단계에서 다룬다.

| 책의 조건 | 이 실습 | 이유 |
| --- | --- | --- |
| Kubeflow Notebooks의 노트북 서버 | PC의 JupyterLab | `book-env`는 KFP standalone이라 Notebooks가 없다 |
| Manning Box의 신분증 압축 파일 | 직접 만든 합성 신분증 120장 | 2026-11-07 기준 저자 URL이 HTTP 404를 반환했다 |
| MovieLens 25M | MovieLens `ml-latest-small` | 25M은 압축 파일만 약 261MB이고 Pod 메모리와 시간이 크게 든다 |
| 저자 컴포넌트 그대로 | 원본을 먼저 실행한 뒤 고친 컴포넌트 | 원본의 실패 위치를 확인하고 고친 부분만 바꾸기 위해서다 |

명령은 [ml-platform-book-env](https://github.com/johklo/ml-platform-book-env) 최상위 폴더의 Windows PowerShell에서 실행한다. 4장의 A-3처럼 `python bookenv.py forward`를 다른 창에 켜 둔 상태여야 한다.

## A. 탐색 환경과 노트북

지금 위치는 전체 그림의 ①~②다.

### A-1. 앞 장의 환경 확인

1. 클러스터와 포트포워딩 상태를 확인한다.
   ```powershell
   python bookenv.py status
   ```
   KFP, S3, MLflow, Redis Pod가 모두 `Running`이어야 한다.
2. http://localhost:8080 의 KFP와 http://localhost:8888/buckets/ 의 저장소가 열리는지 본다. 버킷이 하나도 없다면 4장 A-4처럼 `python bookenv.py buckets`로 만든다. `datasets`와 `ch07-raw`는 7장의 파이프라인이 직접 만들므로 미리 만들 필요가 없다.

[4~5장](../04-experiments-features-pipelines/)의 JupyterLab은 PC에서 돌린 개발 환경이다. kind에는 KFP standalone만 설치했으므로 Kubeflow 대시보드의 Notebooks 메뉴나 Notebook Controller가 없다.

| 구분 | PC의 JupyterLab | Kubeflow Notebooks |
| --- | --- | --- |
| 실행 위치 | PC의 Python 프로세스 | 클러스터의 Notebook Pod |
| 환경 | 로컬 가상환경 | Notebook 이미지 |
| 파일 | PC의 작업 폴더 | 연결한 볼륨 또는 Pod의 임시 공간 |
| 서비스 접속 | localhost 포트포워딩 | 클러스터 DNS와 권한 |
| 자원 | PC의 CPU, 메모리, GPU | Pod의 요청량과 제한, 노드 배치 |

책처럼 Kubeflow Notebooks를 쓰려면 따로 설치해야 한다. 이 차이를 알고 있어야 4장의 localhost 설정을 Pod에 그대로 넣는 실수를 피한다.

### A-2. 저자 코드와 가상환경

1. 저자 코드를 `upstream\`에 받는다. 책이 안내하는 `chapter-7` 저장소는 2026-11-07 기준 공개되어 있지 않다. 7장 코드는 두 프로젝트 저장소에 나뉘어 있다.
   ```powershell
   git clone https://github.com/practical-mlops/object-detection-project.git upstream\object-detection-project
   git -C upstream\object-detection-project checkout c6afb114e628e776a76f9ac50b45899aff5e8eaf
   git clone https://github.com/practical-mlops/movie-recommender-project.git upstream\movie-recommender-project
   git -C upstream\movie-recommender-project checkout 4e0a808e0dca3aef16850cd14df47d2fda9f9bd2
   ```

   | 프로젝트 | 기준 커밋 | 데이터 준비 진입점 |
   | --- | --- | --- |
   | [object-detection-project](https://github.com/practical-mlops/object-detection-project/tree/c6afb114e628e776a76f9ac50b45899aff5e8eaf) | `c6afb114`, 2025-01-02 | `data_prep_pipeline.py`, `chapter_7\*.py` |
   | [movie-recommender-project](https://github.com/practical-mlops/movie-recommender-project/tree/4e0a808e0dca3aef16850cd14df47d2fda9f9bd2) | `4e0a808e`, 2025-04-18 | `01_data_preparation_pipeline.py` |

2. 컴파일과 탐색에 쓸 가상환경을 따로 만든다. 영화 추천 저장소의 requirements가 KFP 2.11.0이므로 앞 글의 `.venv-book`(KFP 2.9.0)을 덮어쓰지 않는다.
   ```powershell
   uv venv .venv-ch07 --python 3.12
   uv pip install --python .venv-ch07 kfp==2.11.0 jupyterlab pandas pyarrow matplotlib pillow boto3
   .\.venv-ch07\Scripts\Activate.ps1
   python -c "import kfp; print(kfp.__version__)"
   ```
   `2.11.0`이 나오면 된다. 이 SDK로 만든 YAML은 KFP 서버 2.4.1에서 이번 실습 범위 안에서 문제없이 돌았다.
3. 이 장에서 만드는 스크립트를 둘 `ch07` 폴더와 데이터 폴더를 만든다.
   ```powershell
   New-Item -ItemType Directory -Force ch07, data | Out-Null
   ```

이 환경은 탐색 노트북을 돌리고 파이프라인 정의를 YAML로 바꾸는 데 쓴다. 실제 작업 Pod의 의존성은 컴포넌트의 `packages_to_install`이 정한다. PC에 KFP를 설치했다고 다운로드와 변환 작업의 환경까지 고정되지는 않는다.

### A-3. 탐색할 데이터 준비

1. MovieLens 작은 데이터셋을 내려받는다. GroupLens 이용 조건에 따라 데이터는 각자 내려받고 저장소에 다시 배포하지 않는다.
   ```powershell
   curl.exe -sSL -o data\ml-latest-small.zip https://files.grouplens.org/datasets/movielens/ml-latest-small.zip
   Expand-Archive -Force data\ml-latest-small.zip data
   Get-Content data\ml-latest-small\ratings.csv -TotalCount 3
   ```
   ```text
   userId,movieId,rating,timestamp
   1,1,4.0,964982703
   1,3,4.0,964981247
   ```
2. 책의 신분증 데이터 주소를 확인한다.
   ```powershell
   curl.exe -sIL https://manning.box.com/shared/static/34dbdkmhahuafcxh0yhiqaf05rqnzjq9.gz | Select-String "HTTP/"
   ```
   이번 확인에서는 `HTTP/1.1 404 Not Found`가 나왔다. 원본 다운로드 컴포넌트는 응답 상태를 보지 않으므로, 404 페이지를 압축 파일로 저장한 뒤 `tarfile`에서 실패하게 된다. 원본 컴포넌트를 클러스터에서 그대로 실행해 보지는 않았다.
3. 그래서 저자 코드가 기대하는 `MINIDATA/images`, `MINIDATA/labels` 구조로 합성 데이터를 만든다. 배경 위에 `SAMPLE ID` 카드를 그린 이미지라 실제 신분증이나 개인정보는 없다. MIDV-500이 영상에서 뽑은 프레임이라는 점을 흉내 내어, 12개 clip마다 카드가 조금씩 움직이는 프레임 10장을 만든다. `ch07\make_synthetic_idcards.py`로 저장한다.
   ```python
   """Synthetic ID-card detection data in the layout the author's split code expects.

   No real documents or personal data: each image is a drawn card with the word
   SAMPLE on a noisy background. Frames of the same clip share a background and
   drift slightly, imitating adjacent video frames in MIDV-500.
   """
   import argparse
   import random
   import tarfile
   from pathlib import Path

   from PIL import Image, ImageDraw, ImageFilter

   W, H = 320, 240


   def make_frame(rng, clip_bg, card, jitter):
       img = Image.new("RGB", (W, H), clip_bg)
       draw = ImageDraw.Draw(img)
       for _ in range(40):
           x, y = rng.randrange(W), rng.randrange(H)
           c = tuple(max(0, min(255, v + rng.randint(-40, 40))) for v in clip_bg)
           draw.ellipse([x, y, x + rng.randint(5, 30), y + rng.randint(5, 30)], fill=c)
       cx, cy, cw, ch, color = card
       cx += rng.randint(-jitter, jitter)
       cy += rng.randint(-jitter, jitter)
       x0, y0 = max(0, cx - cw // 2), max(0, cy - ch // 2)
       x1, y1 = min(W - 1, cx + cw // 2), min(H - 1, cy + ch // 2)
       draw.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=color, outline=(40, 40, 40), width=2)
       draw.rectangle([x0 + 8, y0 + 8, x0 + 8 + (x1 - x0) // 4, y1 - 8], fill=(200, 200, 210))
       draw.text((x0 + (x1 - x0) // 3, y0 + 10), "SAMPLE ID", fill=(20, 20, 60))
       for i in range(3):
           ly = y0 + 30 + i * 14
           if ly < y1 - 6:
               draw.line([x0 + (x1 - x0) // 3, ly, x1 - 10, ly], fill=(90, 90, 90), width=2)
       img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0, 0.8)))
       xc, yc = (x0 + x1) / 2 / W, (y0 + y1) / 2 / H
       return img, f"0 {xc:.6f} {yc:.6f} {(x1 - x0) / W:.6f} {(y1 - y0) / H:.6f}\n"


   def main():
       p = argparse.ArgumentParser()
       p.add_argument("--out", default="synthetic-idcards")
       p.add_argument("--clips", type=int, default=12)
       p.add_argument("--frames", type=int, default=10)
       p.add_argument("--seed", type=int, default=7)
       a = p.parse_args()
       rng = random.Random(a.seed)
       root = Path(a.out) / "MINIDATA"
       (root / "images").mkdir(parents=True, exist_ok=True)
       (root / "labels").mkdir(parents=True, exist_ok=True)
       for c in range(1, a.clips + 1):
           bg = tuple(rng.randint(60, 200) for _ in range(3))
           card = (rng.randint(110, 210), rng.randint(90, 150), rng.randint(140, 200),
                   rng.randint(90, 120), tuple(rng.randint(200, 250) for _ in range(3)))
           for f in range(1, a.frames + 1):
               stem = f"clip{c:02d}_frame{f:03d}"
               img, label = make_frame(rng, bg, card, jitter=6)
               img.save(root / "images" / f"{stem}.png")
               (root / "labels" / f"{stem}.txt").write_text(label)
       archive = Path(a.out).with_suffix(".tar.gz")
       with tarfile.open(archive, "w:gz") as tar:
           tar.add(root, arcname="MINIDATA")
       print(f"{a.clips * a.frames} images, archive {archive} ({archive.stat().st_size} bytes)")


   if __name__ == "__main__":
       main()
   ```
4. 실행한다.
   ```powershell
   python ch07\make_synthetic_idcards.py --out data\synthetic-idcards
   ```
   ```text
   120 images, archive data\synthetic-idcards.tar.gz (828926 bytes)
   ```

### A-4. JupyterLab에서 탐색

1. 저장소 화면의 8888과 겹치지 않게 8890으로 실행한다.
   ```powershell
   jupyter lab --notebook-dir ch07 --port 8890
   ```
2. 출력된 주소를 열고 `ch07_explore.ipynb`를 새로 만든다. 첫 셀에 경로를 정하고 MovieLens의 스키마부터 본다.
   ```python
   from pathlib import Path
   import os
   import pandas as pd
   import matplotlib.pyplot as plt
   from PIL import Image, ImageDraw

   DATA = Path('../data')
   ML = DATA / 'ml-latest-small'
   IDC = DATA / 'synthetic-idcards' / 'MINIDATA'

   ratings = pd.read_csv(ML / 'ratings.csv')
   ratings.info()
   ratings.head()
   ```
3. 다음 셀에서 컴포넌트로 옮길 조건을 확인한다.
   ```python
   print('user_id' in ratings.columns, 'userId' in ratings.columns)
   print(sorted(ratings.rating.unique()))
   print('null cells:', int(ratings.isna().sum().sum()))
   print('duplicate (userId, movieId):', int(ratings.duplicated(['userId', 'movieId']).sum()))
   ts = pd.to_datetime(ratings.timestamp, unit='s')
   print('time range:', ts.min(), '~', ts.max())
   ```
   ```text
   False True
   [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
   null cells: 0
   duplicate (userId, movieId): 0
   time range: 1996-03-29 18:36:55 ~ 2018-09-24 14:27:30
   ```
   (실제 출력의 평점 목록은 `np.float64(0.5)` 형식으로 표시된다.)

   ![JupyterLab에서 MovieLens 열 이름과 품질 조건을 확인한 화면.](/images/ml-platform-engineering/sop/ch07-a-jupyter-schema.png)

   열 이름이 `user_id`가 아니라 `userId`라는 점이 D-2에서 원본 분할이 실패하는 이유가 된다. 사용자당 평점 수는 최소 20, 중앙값 70.5, 최대 2,698개로 차이가 크다. 이 장의 무작위 분할은 이 차이를 반영하지 않는다.
4. 신분증 데이터는 이미지와 라벨이 같은 stem으로 짝을 이루는지, 박스가 객체를 감싸는지 본다.
   ```python
   imgs = os.listdir(IDC / 'images')
   lbls = os.listdir(IDC / 'labels')
   stem = lambda f: os.path.splitext(f)[0]
   print(len(imgs), len(lbls), sorted({stem(f) for f in imgs} ^ {stem(f) for f in lbls}))

   def show(stem_name, ax):
       img = Image.open(IDC / 'images' / f'{stem_name}.png').convert('RGB')
       w, h = img.size
       c, xc, yc, bw, bh = map(float, (IDC / 'labels' / f'{stem_name}.txt').read_text().split())
       ImageDraw.Draw(img).rectangle([(xc - bw / 2) * w, (yc - bh / 2) * h,
                                      (xc + bw / 2) * w, (yc + bh / 2) * h], outline=(255, 0, 0), width=3)
       ax.imshow(img); ax.set_title(stem_name); ax.axis('off')

   fig, ax = plt.subplots(1, 3, figsize=(12, 3))
   for a, s in zip(ax, ['clip01_frame001', 'clip01_frame002', 'clip05_frame001']):
       show(s, a)
   ```
   `120 120 []`이 나오고 빨간 박스가 카드와 겹치면 YOLO의 정규화 중심 좌표를 맞게 읽은 것이다.

   ![합성 신분증 이미지 위에 YOLO 라벨 박스를 그린 화면.](/images/ml-platform-engineering/sop/ch07-a-jupyter-labels.png)

   같은 clip의 두 프레임은 배경과 카드 위치가 거의 같다. 이런 프레임이 학습과 평가에 나뉘어 들어가면 평가가 쉬워진다. 이 관찰을 C-3의 분할 규칙으로 옮긴다.

여기까지 하면 노트북에 다섯 가지 규칙이 남는다. 열 이름, 평점 범위, 결측과 중복, 이미지와 라벨의 짝, 그룹 단위다. 다음 단계부터 이 규칙을 컴포넌트의 입력, 출력, 검사로 옮긴다.

### A-5. 책의 Kubeflow 노트북에서 정하는 것

책처럼 Kubeflow Notebooks를 쓰면 노트북은 브라우저 화면이 아니라 자원과 저장소를 쓰는 워크로드가 된다. 이 실습에서는 만들지 않았지만, 다음 설정이 PC의 가상환경과 폴더 역할을 맡는다.

| 설정 | 확인할 내용 |
| --- | --- |
| 이미지 | Python, 데이터 라이브러리, OS 의존성과 버전 |
| Namespace | 서비스 계정, 네트워크 접근과 자원 할당 범위 |
| Workspace volume | 노트북 재시작 뒤에도 남길 코드와 작업 파일 |
| Data volume | 여러 작업이 읽을 데이터와 읽기 및 쓰기 권한 |
| PodDefault | 해당 설정을 적용하는 구성에서 공통 환경과 볼륨 주입 |
| Affinity / toleration | 자원에 맞는 노드 선택과 taint 허용 |
| GPU와 유휴 종료 | 탐색에 필요한 자원과 사용하지 않을 때 반환할 정책 |

toleration은 특정 taint를 허용할 뿐, 그 노드에 꼭 배치하라는 뜻은 아니다. 같은 이미지를 써도 데이터 버전, 설정, 숨은 셀 상태가 다르면 결과가 달라진다.

## B. 파라미터와 아티팩트 전달

지금 위치는 전체 그림의 ③~⑧이다.

책은 데이터 준비에 앞서 작은 joke 파이프라인으로 두 전달 방식을 보여 준다. 저자 저장소의 `chapter_7\pipeline.py`는 문자열과 정수를 파라미터로, `chapter_7\generate_jokes_pipeline.py`는 파일을 아티팩트로 넘긴다.

### B-1. 두 파이프라인 컴파일

```powershell
Push-Location upstream\object-detection-project\chapter_7
python pipeline.py
python generate_jokes_pipeline.py
Get-Item _pipeline.yaml, generate_jokes_pipeline.yaml
Pop-Location
```

`_pipeline.yaml`과 `generate_jokes_pipeline.yaml`이 생기면 된다. 컴파일은 함수 본문을 실행하지 않는다. 각 컴포넌트의 이미지, 설치할 패키지, 입출력 타입을 YAML에 적을 뿐이다. 기본 이미지를 지정하지 않은 컴포넌트에서 `python:3.9` 기본값 경고가 나오지만 실행에는 지장이 없었다.

### B-2. 업로드와 실행

KFP 화면에서 올려도 되지만 이 장은 파이프라인이 일곱 개라서, [4장 D-5](../04-experiments-features-pipelines/#d-5-파이프라인-업로드)의 화면 절차 대신 SDK로 올리는 스크립트를 쓴다. `ch07\submit.py`로 저장한다.

```python

"""Uploads a compiled pipeline to KFP and starts one run in the ch07 experiment."""

import argparse


import kfp


p = argparse.ArgumentParser()

p.add_argument("yaml")

p.add_argument("name")

p.add_argument("--run", required=True)

a = p.parse_args()


client = kfp.Client(host="http://127.0.0.1:8080")

pid = client.get_pipeline_id(a.name)

if pid is None:

    pipeline = client.upload_pipeline(a.yaml, pipeline_name=a.name)

    pid = pipeline.pipeline_id

    version_id = client.list_pipeline_versions(pid).pipeline_versions[0].pipeline_version_id

else:

    version_id = client.upload_pipeline_version(a.yaml, pipeline_version_name=a.run, pipeline_id=pid).pipeline_version_id

exp = client.create_experiment("ch07-data-prep")

run = client.run_pipeline(experiment_id=exp.experiment_id, job_name=a.run, pipeline_id=pid, version_id=version_id)

print("run", run.run_id)

print(f"http://127.0.0.1:8080/#/runs/details/{run.run_id}")
```

```powershell
python ch07\submit.py upstream\object-detection-project\chapter_7\_pipeline.yaml ch07-joke-parameters --run ch07-joke-parameters-1
python ch07\submit.py upstream\object-detection-project\chapter_7\generate_jokes_pipeline.yaml ch07-joke-artifacts --run ch07-joke-artifacts-1
```

출력된 주소를 열면 실행 화면이 나온다. 두 실행 모두 2분 안팎에 끝났다. 첫 실행은 작업 Pod가 `python:3.11` 이미지를 받고 `pyjokes`를 설치하느라 더 걸릴 수 있다.

docker.io에서 이미지를 받다가 시간 초과가 반복되면 PC에서 받아 kind 노드에 넣는다. `kind load docker-image`가 `content digest ... not found`로 실패하면 플랫폼을 지정해 저장한 파일로 적재한다.

```powershell
docker pull python:3.11
docker save --platform linux/amd64 python:3.11 -o python311.tar
kind load image-archive python311.tar --name book-env
Remove-Item python311.tar
```

### B-3. 파라미터 전달 확인

`ch07-joke-parameters-1`에서 **count-words → Input/Output**을 연다.

![파라미터로 문자열을 받고 정수를 돌려준 count-words 작업.](/images/ml-platform-engineering/sop/ch07-b-param-io.png)

앞 작업이 반환한 농담 문자열이 `input` 파라미터에 그대로 보이고, 결과 `14`는 Output Parameters에 남는다. 값이 실행 기록에 직접 저장되니 작은 설정과 결과에 알맞다. 10GB 데이터셋을 이렇게 넘길 수는 없다.

### B-4. 아티팩트 전달과 .path, .uri

1. `ch07-joke-artifacts-1`의 그래프를 본다. 작업 사이에 노란 폴더 모양의 `output_jokes` 아티팩트가 생긴다.

   ![generate-joke와 count-words 사이에 output_jokes 아티팩트가 있는 그래프.](/images/ml-platform-engineering/sop/ch07-b-art-graph.png)

2. **count-words → Input/Output**을 연다.

   ![count-words가 입력 아티팩트의 S3 주소를 받은 화면.](/images/ml-platform-engineering/sop/ch07-b-art-io.png)

   Input Artifacts에 보이는 것은 내용이 아니라 `minio://mlpipeline/v2/artifacts/joke-pipeline/<run_id>/generate-joke/<id>/output_jokes` 주소다. 이것이 아티팩트의 `.uri`다. `Error in retrieving artifact preview`는 화면이 미리보기를 만들지 못했다는 뜻일 뿐이다. 이 아티팩트는 `jokes.txt`를 담은 폴더이고, 작업이 이 주소의 파일을 읽어 세 농담의 단어 수 `43`을 Output Parameters에 남겼으니 전달은 성공했다.

코드에서 쓰는 `.path`는 Pod 안의 로컬 경로다. C-3의 실제 로그를 보면 같은 아티팩트가 다음처럼 두 이름을 가진다.

```text
.path  /minio/mlpipeline/v2/artifacts/ch07-idcard-prep-fixed/d55c041d-.../download-dataset-from-s3/453d4471-.../output_dataset
.uri   minio://mlpipeline/v2/artifacts/ch07-idcard-prep-fixed/d55c041d-.../split-dataset-by-stem/1afb190a-.../train_dataset
```

```mermaid
sequenceDiagram
    accTitle: 데이터 준비 컴포넌트 사이의 아티팩트 전달
    accDescr: KFP는 분할 시드 같은 작은 값을 파라미터로 전달한다. 다운로드 Pod가 출력 경로에 기록한 파일은 아티팩트 저장소를 거쳐 다음 Pod의 입력 경로에 연결된다.
    participant K as KFP
    participant A as 다운로드 Pod
    participant S as 아티팩트 저장소
    participant B as 변환과 분할 Pod
    K->>A: 원천과 실행 설정
    A->>A: Output의 path에 파일 기록
    A->>S: 아티팩트 저장
    K->>B: 분할 시드와 입력 아티팩트 참조
    S->>B: Input의 path로 파일 제공
    B->>B: 입력을 읽고 새 출력 작성
```

| 전달 방식 | 적합한 것 | 확인할 조건 |
| --- | --- | --- |
| 파라미터 | seed, 버킷 이름, 원천 버전 같은 작은 설정 | 값의 타입과 의미 |
| KFP 아티팩트 | 데이터셋, 파일 묶음, 모델, 평가 보고서 | 선언한 출력 경로에 실제 파일을 썼는지 |
| S3 URI | 장기 보관할 업무 데이터의 위치 | 다음 작업의 주소, 권한과 객체 버전 |
| 공유 볼륨 | 명시적으로 마운트한 공통 파일 | PVC, 접근 모드, 마운트 경로와 동시 쓰기 |

KFP가 정한 `output.path`와 `s3://datasets/ml-latest-small/train.parquet.gzip`은 역할이 다른 경로다. 앞의 것은 실행 사이의 산출물 연결이고, 뒤의 것은 코드가 boto3로 직접 올린 장기 보관 위치다. `Input[Dataset]`은 입력의 의도를 나타낼 뿐 CSV 열이나 YOLO 라벨을 검증하지 않는다. 내용 검사는 C와 D의 QA 컴포넌트가 맡는다.

B를 마치면 실험 `ch07-data-prep`에 성공한 실행 두 개가 남는다. 파라미터는 값으로, 아티팩트는 주소로 기록된다는 차이를 화면으로 본 셈이다.

## C. 신분증 탐지 데이터 준비

지금 위치는 전체 그림의 ⑤~⑩ 가운데 신분증 데이터 경로다.

```mermaid
flowchart LR
    accTitle: 신분증 이미지와 라벨의 데이터 준비
    accDescr: 압축 데이터를 다운로드하고 해제한 뒤 이미지와 라벨의 대응을 확인한다. 분할 컴포넌트는 학습, 검증, 테스트 아티팩트를 만들고 각 아티팩트 안에 images와 labels를 둔다.
    A["원천 압축 파일"] --> B["다운로드와 해제"]
    B --> C["이미지와 라벨 대응 확인"]
    C --> D["분할 컴포넌트"]
    D --> T["train_dataset<br/>images와 labels"]
    D --> V["validation_dataset<br/>images와 labels"]
    D --> E["test_dataset<br/>images와 labels"]
```

객체 탐지 저장소의 루트 `data_prep_pipeline.py`에 다운로드, 분할, 파일 목록 출력 컴포넌트가 함께 들어 있다. `data_preparation` 폴더에는 `/mnt/pipeline`을 쓰는 다른 코드도 있으니 두 경로를 섞지 않는다. 이 진입점은 배포된 압축 파일을 받아 나눌 뿐, 원천 MIDV 주석을 YOLO 형식으로 바꾸지 않는다. 그 변환은 저자가 미리 해 두었다고 책도 설명한다.

### C-1. 원천 올리기와 다운로드 컴포넌트 교체

1. A-3에서 만든 압축 파일을 `ch07-raw` 버킷에 올린다. `ch07\upload_raw.py`로 저장하고 실행한다.
   ```python
   """Uploads the synthetic ID-card archive to s3://ch07-raw through the forwarded S3 port."""
   import boto3
   from botocore.exceptions import ClientError

   s3 = boto3.client("s3", endpoint_url="http://127.0.0.1:9000",
                     aws_access_key_id="minio", aws_secret_access_key="minio123")
   try:
       s3.head_bucket(Bucket="ch07-raw")
   except ClientError:
       s3.create_bucket(Bucket="ch07-raw")
   s3.upload_file("data/synthetic-idcards.tar.gz", "ch07-raw", "synthetic-idcards.tar.gz")
   for obj in s3.list_objects_v2(Bucket="ch07-raw")["Contents"]:
       print(obj["Key"], obj["Size"])
   ```
   ```powershell
   python ch07\upload_raw.py
   ```
   ```text
   synthetic-idcards.tar.gz 828926
   ```

   ![ch07-raw 버킷에 올린 합성 신분증 압축 파일.](/images/ml-platform-engineering/sop/ch07-c-raw-bucket.png)

2. 저자의 `download_dataset`에서 Box 주소로 받던 부분만 S3로 바꾼다. 압축 해제 위치(`output_dataset.path/DATASET`)는 그대로 두어 저자의 `split_dataset`이 같은 경로를 찾게 한다. 해제할 때는 경로 밖으로 쓰지 못하게 `filter="data"`를 붙였다. 파일의 나머지 두 컴포넌트는 C-2와 C-3에서 쓴다. `ch07\idcard_components.py`로 저장한다.
   ```python
   from kfp import dsl
   from kfp.dsl import Dataset, Input, Metrics, Output

   S3_ENDPOINT = "http://minio-service.kubeflow:9000"


   @dsl.component(base_image="python:3.11", packages_to_install=["boto3"])
   def download_dataset_from_s3(
       output_dataset: Output[Dataset],
       source_bucket: str = "ch07-raw",
       source_key: str = "synthetic-idcards.tar.gz",
       output_dir: str = "DATASET",
   ):
       """Replaces the author's Box download, which now returns 404."""
       import os
       import tarfile

       import boto3

       s3 = boto3.client("s3", endpoint_url="http://minio-service.kubeflow:9000",
                         aws_access_key_id="minio", aws_secret_access_key="minio123")
       s3.download_file(source_bucket, source_key, "DATASET.gz")
       extraction_path = os.path.join(output_dataset.path, output_dir)
       os.makedirs(extraction_path, exist_ok=True)
       with tarfile.open("DATASET.gz", "r:gz") as tar:
           tar.extractall(extraction_path, filter="data")
       for root, _, files in os.walk(extraction_path):
           if files:
               print(root, len(files), "files")


   @dsl.component(base_image="python:3.11")
   def check_split_pairs(
       train_dataset: Input[Dataset],
       validation_dataset: Input[Dataset],
       test_dataset: Input[Dataset],
       report: Output[Metrics],
       fail_on_error: bool = True,
   ):
       """Checks every split: image/label pairing by stem, YOLO format, clip leakage."""
       import os

       def labels_in(path):
           return {os.path.splitext(f)[0]: os.path.join(path, f) for f in os.listdir(path)}

       errors, clips = [], {}
       for name, ds in [("train", train_dataset), ("validation", validation_dataset), ("test", test_dataset)]:
           imgs = labels_in(os.path.join(ds.path, "images"))
           lbls = labels_in(os.path.join(ds.path, "labels"))
           unmatched = sorted(set(imgs) ^ set(lbls))
           bad = 0
           for stem, path in lbls.items():
               for line in open(path).read().splitlines():
                   parts = line.split()
                   if len(parts) != 5 or parts[0] != "0" or not all(0 <= float(v) <= 1 for v in parts[1:]):
                       bad += 1
           clips[name] = {s.split("_")[0] for s in imgs}
           print(f"{name}: images={len(imgs)} labels={len(lbls)} unmatched={len(unmatched)} bad_label_lines={bad}")
           if unmatched:
               print("  e.g.", unmatched[:4])
           report.log_metric(f"{name}_images", len(imgs))
           report.log_metric(f"{name}_unmatched", len(unmatched))
           if unmatched or bad:
               errors.append(f"{name}: {len(unmatched)} unmatched, {bad} bad lines")
       for a, b in [("train", "validation"), ("train", "test"), ("validation", "test")]:
           shared = sorted(clips[a] & clips[b])
           print(f"clips shared by {a} and {b}: {len(shared)} {shared[:6]}")
           report.log_metric(f"shared_clips_{a}_{b}", len(shared))
           if shared:
               errors.append(f"{a}/{b} share clips {shared[:6]}")
       if errors and fail_on_error:
           raise SystemExit("QA failed: " + "; ".join(errors))
       print("QA passed" if not errors else "QA found problems (not failing)")


   @dsl.component(base_image="python:3.11")
   def split_dataset_by_stem(
       random_state: int,
       input_dataset: Input[Dataset],
       train_dataset: Output[Dataset],
       validation_dataset: Output[Dataset],
       test_dataset: Output[Dataset],
       base_path: str = "MINIDATA",
   ):
       """Pairs files by stem before splitting and keeps each clip in one split."""
       import os
       import random
       import shutil

       root = os.path.join(input_dataset.path, "DATASET", base_path)
       imgs = {os.path.splitext(f)[0]: f for f in os.listdir(os.path.join(root, "images"))}
       lbls = {os.path.splitext(f)[0]: f for f in os.listdir(os.path.join(root, "labels"))}
       missing = sorted(set(imgs) ^ set(lbls))
       if missing:
           raise SystemExit(f"image/label stems do not match: {missing[:10]}")

       clips = sorted({s.split("_")[0] for s in imgs})
       random.Random(random_state).shuffle(clips)
       n_train = round(len(clips) * 0.75)
       n_val = round(len(clips) * 0.15)
       parts = [clips[:n_train], clips[n_train:n_train + n_val], clips[n_train + n_val:]]

       for out, chosen in zip([train_dataset, validation_dataset, test_dataset], parts):
           os.makedirs(os.path.join(out.path, "images"), exist_ok=True)
           os.makedirs(os.path.join(out.path, "labels"), exist_ok=True)
           stems = sorted(s for s in imgs if s.split("_")[0] in chosen)
           for s in stems:
               shutil.copy2(os.path.join(root, "images", imgs[s]), os.path.join(out.path, "images", imgs[s]))
               shutil.copy2(os.path.join(root, "labels", lbls[s]), os.path.join(out.path, "labels", lbls[s]))
           print(f"{out.uri}: {len(stems)} pairs from clips {sorted(chosen)}")
   ```

`check_split_pairs`는 train만 출력하던 저자의 `output_file_contents`를 대신한다. 세 분할 모두에서 이미지와 라벨의 stem 대응, YOLO 라벨의 다섯 항목과 0~1 범위, 같은 clip이 두 분할에 걸쳤는지를 검사하고 결과를 Metrics로 남긴다.

### C-2. 저자의 분할을 그대로 실행

1. 다운로드만 바꾸고 저자의 `split_dataset`과 `output_file_contents`는 그대로 가져온 파이프라인을 만든다. `ch07\idcard_original_pipeline.py`로 저장한다.
   ```python
   """Author's split_dataset unchanged; only the Box download is replaced by S3."""
   import sys
   from pathlib import Path

   from kfp import compiler, dsl

   sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "upstream" / "object-detection-project"))
   from data_prep_pipeline import output_file_contents, split_dataset  # noqa: E402

   from idcard_components import check_split_pairs, download_dataset_from_s3  # noqa: E402


   @dsl.pipeline(name="ch07-idcard-original-split")
   def pipeline(random_state: int = 42):
       download_op = download_dataset_from_s3()
       split_op = split_dataset(random_state=random_state, input_dataset=download_op.outputs["output_dataset"])
       output_file_contents(dataset=split_op.outputs["train_dataset"])
       check_split_pairs(
           train_dataset=split_op.outputs["train_dataset"],
           validation_dataset=split_op.outputs["validation_dataset"],
           test_dataset=split_op.outputs["test_dataset"],
       )


   if __name__ == "__main__":
       compiler.Compiler().compile(pipeline, "ch07_idcard_original.yaml")
   ```
2. 컴파일하고 실행한다.
   ```powershell
   Push-Location ch07
   python idcard_original_pipeline.py
   Pop-Location
   python ch07\submit.py ch07\ch07_idcard_original.yaml ch07-idcard-original-split --run ch07-idcard-original-1
   ```
3. 약 3분 뒤 그래프를 보면 `split-dataset`은 성공하고 `check-split-pairs`만 빨간색으로 끝난다.

   ![저자 분할 뒤 검사 작업이 실패한 실행 그래프.](/images/ml-platform-engineering/sop/ch07-c-orig-graph.png)

4. **check-split-pairs → Logs**를 연다.

   ![분할마다 짝이 맞지 않는 stem과 clip 중복이 나온 로그.](/images/ml-platform-engineering/sop/ch07-c-orig-qa-log.png)

   ```text
   train: images=90 labels=90 unmatched=46 bad_label_lines=0
   validation: images=18 labels=18 unmatched=28 bad_label_lines=0
   test: images=12 labels=12 unmatched=24 bad_label_lines=0
   clips shared by train and validation: 10 [...]
   clips shared by train and test: 9 [...]
   clips shared by validation and test: 7 [...]
   ```

분할마다 이미지와 라벨 수는 같다. 그런데 train의 이미지 90장 중 23장은 자기 라벨이 다른 분할로 갔고, 그 자리에 다른 이미지의 라벨 23개가 들어왔다. `unmatched=46`은 짝 없는 이미지와 라벨 stem을 더한 수다.

원인은 목록을 만드는 방식에 있다. 원본은 `glob`으로 이미지 목록과 라벨 목록을 따로 만든 뒤 같은 `random_state`로 나눈다. 그런데 `glob`은 파일을 이름순으로 정렬하지 않는다. 이번 Linux 컨테이너에서는 두 폴더의 나열 순서가 서로 달라, 같은 위치의 이미지와 라벨이 같은 표본이 아니게 됐다. Windows의 탐색 노트북에서는 두 목록이 모두 이름순으로 나와 문제가 보이지 않았다. PC에서 멀쩡하던 코드가 컨테이너에서만 어긋난다는 점이 이 장에서 가장 의외였다. 파일 수만 출력하는 저자의 `output_file_contents`는 성공으로 끝났다.

라벨 형식 오류(`bad_label_lines`)는 0이니 형식 검사로는 이 문제를 잡을 수 없다. 이대로 학습하면 실행은 되지만 다른 이미지의 박스를 정답으로 배운다. clip 중복은 무작위 분할의 결과로, 같은 영상의 인접 프레임이 학습과 평가에 함께 들어갔다는 뜻이다.

### C-3. stem으로 짝짓고 clip 단위로 나누기

1. C-1 파일의 `split_dataset_by_stem`은 다음 순서로 동작한다.

   | 단계 | 원본 | 수정 |
   | --- | --- | --- |
   | 짝짓기 | 이미지와 라벨 목록을 따로 `glob` | stem을 키로 묶고 짝이 없으면 중단 |
   | 분할 단위 | 파일 하나 | clip 하나 |
   | 비율 | 파일 수 기준 75/15/10 | clip 12개를 반올림해 9/2/1 |
   | 검사 | train 파일 목록 출력 | 세 분할의 짝, 라벨 형식, clip 중복 |

2. 수정 파이프라인을 만든다. `ch07\idcard_fixed_pipeline.py`로 저장한다.
   ```python
   """Fixed ID-card preparation: stem pairing, clip-level split, QA on all splits."""
   from kfp import compiler, dsl

   from idcard_components import check_split_pairs, download_dataset_from_s3, split_dataset_by_stem


   @dsl.pipeline(name="ch07-idcard-prep-fixed")
   def pipeline(random_state: int = 42):
       download_op = download_dataset_from_s3()
       split_op = split_dataset_by_stem(random_state=random_state, input_dataset=download_op.outputs["output_dataset"])
       check_split_pairs(
           train_dataset=split_op.outputs["train_dataset"],
           validation_dataset=split_op.outputs["validation_dataset"],
           test_dataset=split_op.outputs["test_dataset"],
       )


   if __name__ == "__main__":
       compiler.Compiler().compile(pipeline, "ch07_idcard_fixed.yaml")
   ```
3. 컴파일하고 실행한다.
   ```powershell
   Push-Location ch07
   python idcard_fixed_pipeline.py
   Pop-Location
   python ch07\submit.py ch07\ch07_idcard_fixed.yaml ch07-idcard-prep-fixed --run ch07-idcard-fixed-1
   ```
4. 약 2분 뒤 세 작업이 모두 초록색이 된다.

   ![stem 분할과 검사가 모두 성공한 실행 그래프.](/images/ml-platform-engineering/sop/ch07-c-fixed-graph.png)

5. **split-dataset-by-stem → Input/Output**에서 입력 하나와 출력 세 개의 주소를 확인한다.

   ![분할 작업의 입력 아티팩트와 세 출력 아티팩트 주소.](/images/ml-platform-engineering/sop/ch07-c-fixed-split-io.png)

   같은 작업의 Logs에는 분할마다 어떤 clip이 들어갔는지 나온다.
   ```text
   .../train_dataset: 90 pairs from clips ['clip03', 'clip04', 'clip05', 'clip06', 'clip07', 'clip08', 'clip09', 'clip10', 'clip12']
   .../validation_dataset: 20 pairs from clips ['clip01', 'clip02']
   .../test_dataset: 10 pairs from clips ['clip11']
   ```
6. **check-split-pairs → Logs**에서 `QA passed`를 확인한다.

   ![세 분할의 짝과 clip 중복이 모두 0인 검사 로그.](/images/ml-platform-engineering/sop/ch07-c-fixed-qa-log.png)

7. 저장소 화면에서 출력 아티팩트의 `.uri`가 실제 폴더임을 확인한다. http://localhost:8888/buckets/mlpipeline/v2/artifacts/ch07-idcard-prep-fixed/ 아래에서 실행 ID와 `split-dataset-by-stem` 폴더로 들어간다.

   ![mlpipeline 버킷에 남은 세 분할 아티팩트 폴더.](/images/ml-platform-engineering/sop/ch07-c-fixed-artifacts.png)

   각 폴더 안에 `images`와 `labels`가 있다. 책 목록 7.10의 YOLO 구조와 같고, 8장의 학습 작업이 이 세 아티팩트를 입력으로 받는다.

C를 마치면 짝이 맞고 clip이 섞이지 않은 train 90장, validation 20장, test 10장이 KFP 아티팩트로 남는다. 합성 데이터 120장은 파이프라인 동작을 확인하는 용도다. 이 데이터로 학습한 탐지 성능을 실제 신분증 탐지 성능으로 읽으면 안 된다.

### C-4. 실제 데이터에서 분할 전에 확인할 것

| 검사 | 확인 방법 |
| --- | --- |
| 파일 대응 | 이미지와 라벨을 파일명 stem으로 연결 |
| 중복과 누락 | 중복 stem, 라벨 없는 이미지, 이미지 없는 라벨 탐지 |
| 라벨 형식 | 클래스 ID와 좌표 항목의 개수, 타입 확인 |
| 좌표 의미 | YOLO의 정규화된 중심 좌표, 너비, 높이인지 확인 |
| 데이터 단위 | 문서, 사람, 촬영 영상 등 동일 원천의 그룹 기록 |
| 샘플 표시 | 이미지 위에 박스를 그려 위치와 클래스 확인 |

YOLO 박스라면 클래스 ID, 중심 좌표 x와 y, 너비, 높이의 의미와 범위를 확인한다. 좌상단과 우하단 좌표를 그대로 넣거나 픽셀 값을 정규화 값처럼 다루면, 학습은 돌아가도 다른 박스를 배운다. 배경만 있는 이미지를 허용한다면 빈 라벨 파일과 라벨 누락을 가르는 규칙도 필요하다. 이번 검사는 빈 라벨을 오류로 보지 않으니, 실제 데이터에서는 이 조건을 더한다.

## D. MovieLens 평점 데이터 준비

지금 위치는 전체 그림의 ⑤~⑩ 가운데 추천 데이터 경로다.

### D-1. 컴포넌트와 데이터 규모

영화 추천 프로젝트는 MovieLens의 `ratings.csv`와 `movies.csv`를 읽는다. 데이터 준비는 모델 학습과 분리된 별도 파이프라인이다.

```mermaid
flowchart LR
    accTitle: 영화 평점 데이터의 변환과 분할
    accDescr: MovieLens 압축 파일을 내려받아 ratings와 movies CSV를 분리한다. ratings는 Parquet으로 변환해 세 분할로 나누고 movies와 함께 S3에 업로드한다. QA는 두 업로드가 끝난 뒤 네 파일을 읽는다.
    DL["MovieLens ZIP 다운로드"] --> UN["압축 해제"]
    UN --> R["ratings.csv"]
    UN --> M["movies.csv"]
    R --> RP["Parquet 변환"]
    RP --> SP["75/15/10 무작위 분할"]
    SP --> UP["분할 파일 업로드"]
    M --> MP["Parquet 변환과 업로드"]
    UP --> S3[("datasets/ml-latest-small")]
    MP --> S3
    UP --> QA["네 파일 QA"]
    MP --> QA
```

저자의 컴포넌트는 `data_components\dataset_preparation.py`에 있다.

| 컴포넌트 | 입력과 출력 | 이 실습에서 |
| --- | --- | --- |
| `download_ml25m_data` | GroupLens ZIP을 출력 아티팩트에 기록 | 데이터셋 이름을 파라미터로 바꾼 `download_movielens` |
| `unzip_data` | ZIP에서 ratings와 movies를 별도 CSV로 분리 | 폴더 이름을 파라미터로 바꾼 `unzip_movielens` |
| `csv_to_parquet` | CSV를 gzip 압축 Parquet으로 변환 | 그대로 사용 |
| `split_dataset` | ratings를 train, val, test 파일로 작성 | D-2에서 실패 확인 후 `split_ratings` |
| `put_to_minio` | 업무용 버킷의 `ml-25m` 경로에 업로드 | 경로를 파라미터로 바꾼 `put_to_s3` |
| `qa_data` | 업로드된 train Parquet의 열 수와 행 수 확인 | D-4에서 실패 확인 후 `qa_movielens` |

25M은 평점 2,500만 개에 압축 파일만 약 261MB다. 해제한 CSV, Parquet, 세 분할을 Pod 안에서 pandas로 메모리에 올리니 공유 kind 클러스터에는 부담이 크다. 그래서 같은 열 구조의 `ml-latest-small`(평점 100,836개, 사용자 610명, 영화 9,742편)을 쓴다. 작은 자료는 평점 시점과 사용자 구성이 달라서 여기서 나온 수치를 25M의 결과로 읽지 않는다. 파이프라인 동작과 검사 조건을 확인하는 데만 쓴다. 저장 위치도 `ml-25m` 대신 `datasets/ml-latest-small/`로 나눠 다른 데이터와 섞이지 않게 했다.

Parquet은 저장 형식이지 분할 정책이 아니다. 압축과 열 단위 읽기가 편해도 데이터 누수나 식별자 오류를 해결해 주지는 않는다.

### D-2. 저자의 분할을 그대로 실행

1. 수정 컴포넌트 파일부터 만든다. 다운로드와 해제는 데이터셋 이름만 파라미터로 바꿨다. TLS 검증을 끄던 `verify=False`는 없애고, HTTP 상태 확인과 sha256 기록을 넣었다. `ch07\movielens_components.py`로 저장한다.
   ```python
   from kfp import dsl
   from kfp.dsl import Artifact, Input, Metrics, Output


   @dsl.component(base_image="python:3.11", packages_to_install=["requests"])
   def download_movielens(output_path_one: Output[Artifact], dataset: str = "ml-latest-small"):
       """Author's download with the dataset name as a parameter and TLS verification on."""
       import hashlib

       import requests

       url = f"https://files.grouplens.org/datasets/movielens/{dataset}.zip"
       response = requests.get(url, stream=True, timeout=60)
       response.raise_for_status()
       digest = hashlib.sha256()
       with open(output_path_one.path, "wb") as file:
           for chunk in response.iter_content(chunk_size=1024 * 1024):
               if chunk:
                   file.write(chunk)
                   digest.update(chunk)
       output_path_one.metadata["source_url"] = url
       output_path_one.metadata["sha256"] = digest.hexdigest()
       print(url, digest.hexdigest())


   @dsl.component(base_image="python:3.11")
   def unzip_movielens(input_path: Input[Artifact], ratings_output_path: Output[Artifact],
                       movies_output_path: Output[Artifact], dataset: str = "ml-latest-small"):
       import zipfile

       with zipfile.ZipFile(input_path.path, "r") as z:
           with open(ratings_output_path.path, "wb") as f:
               f.write(z.read(f"{dataset}/ratings.csv"))
           with open(movies_output_path.path, "wb") as f:
               f.write(z.read(f"{dataset}/movies.csv"))


   @dsl.component(base_image="python:3.11", packages_to_install=["scikit-learn", "pandas", "fastparquet"])
   def split_ratings(input_parquet: Input[Artifact], dataset_path: Output[Artifact], random_state: int = 42):
       """Author's split_dataset without the two user_id/item_id lines."""
       import os

       import pandas as pd
       from sklearn.model_selection import train_test_split

       ratings_df = pd.read_parquet(input_parquet.path)
       print("columns:", list(ratings_df.columns), "rows:", len(ratings_df))
       train, test = train_test_split(ratings_df, test_size=0.25, random_state=random_state)
       val, test = train_test_split(test, test_size=0.10 / 0.25, random_state=random_state)
       os.mkdir(dataset_path.path)
       for name, df in [("train", train), ("val", val), ("test", test)]:
           df.to_parquet(os.path.join(dataset_path.path, f"{name}.parquet.gzip"), compression="gzip")
           print(name, df.shape)


   @dsl.component(base_image="python:3.11", packages_to_install=["boto3"])
   def put_to_s3(inputFile: Input[Artifact], upload_file_name: str = "", bucket: str = "datasets",
                 prefix: str = "ml-latest-small"):
       """Author's put_to_minio with a prefix parameter and an idempotent bucket check."""
       import os

       import boto3
       from botocore.exceptions import ClientError

       s3 = boto3.client("s3", endpoint_url="http://minio-service.kubeflow:9000",
                         aws_access_key_id="minio", aws_secret_access_key="minio123")
       try:
           s3.head_bucket(Bucket=bucket)
       except ClientError:
           s3.create_bucket(Bucket=bucket)
       if os.path.isdir(inputFile.path):
           files = [(os.path.join(inputFile.path, f), f) for f in sorted(os.listdir(inputFile.path))]
       else:
           files = [(inputFile.path, upload_file_name or os.path.basename(inputFile.path))]
       for local, name in files:
           s3.upload_file(local, bucket, f"{prefix}/{name}")
           print(f"uploaded s3://{bucket}/{prefix}/{name} ({os.path.getsize(local)} bytes)")


   @dsl.component(base_image="python:3.11", packages_to_install=["pyarrow", "pandas"])
   def qa_movielens(report: Output[Metrics], bucket: str = "datasets", dataset: str = "ml-latest-small",
                    min_total_rows: int = 100000):
       """Checks all splits and movies, not only the train column count."""
       import pandas as pd
       from pyarrow import fs, parquet

       s3 = fs.S3FileSystem(endpoint_override="http://minio-service.kubeflow:9000",
                            access_key="minio", secret_key="minio123", scheme="http")

       def read(name):
           with s3.open_input_file(f"{bucket}/{dataset}/{name}.parquet.gzip") as f:
               return parquet.read_table(f).to_pandas()

       errors = []
       splits = {name: read(name) for name in ["train", "val", "test"]}
       movies = read("movies")
       total = sum(len(df) for df in splits.values())
       expected = ["userId", "movieId", "rating", "timestamp"]
       for name, df in splits.items():
           if list(df.columns) != expected:
               errors.append(f"{name} columns {list(df.columns)}")
               continue
           nulls = int(df[expected].isna().sum().sum())
           out_of_range = int((~df.rating.between(0.5, 5.0)).sum())
           print(f"{name}: rows={len(df)} share={len(df) / total:.3f} nulls={nulls} rating_out_of_range={out_of_range}")
           report.log_metric(f"{name}_rows", len(df))
           if nulls or out_of_range:
               errors.append(f"{name} nulls={nulls} out_of_range={out_of_range}")
       keys = {n: set(zip(df.userId, df.movieId)) for n, df in splits.items()}
       overlap = len(keys["train"] & keys["val"]) + len(keys["train"] & keys["test"]) + len(keys["val"] & keys["test"])
       all_ratings = pd.concat(splits.values())
       unknown_movies = int((~all_ratings.movieId.isin(movies.movieId)).sum())
       print(f"total={total} duplicate_keys_across_splits={overlap} ratings_with_unknown_movie={unknown_movies}")
       print("timestamp range:", pd.to_datetime(all_ratings.timestamp.min(), unit="s"),
             pd.to_datetime(all_ratings.timestamp.max(), unit="s"))
       report.log_metric("total_rows", total)
       report.log_metric("duplicate_keys_across_splits", overlap)
       report.log_metric("unknown_movies", unknown_movies)
       if total < min_total_rows:
           errors.append(f"total rows {total} < {min_total_rows}")
       if overlap or unknown_movies:
           errors.append(f"overlap={overlap} unknown_movies={unknown_movies}")
       if errors:
           raise SystemExit("QA failed: " + "; ".join(errors))
       print("QA passed!")
   ```
2. 다운로드와 해제만 바꾸고 저자의 `csv_to_parquet`, `split_dataset`을 그대로 쓰는 파이프라인을 만든다. `ch07\movielens_original_split_pipeline.py`로 저장한다.
   ```python
   """Author's csv_to_parquet and split_dataset unchanged; only the dataset size differs."""
   import sys
   from pathlib import Path

   from kfp import compiler, dsl

   sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "upstream" / "movie-recommender-project"))
   from data_components import csv_to_parquet, split_dataset  # noqa: E402

   from movielens_components import download_movielens, unzip_movielens  # noqa: E402


   @dsl.pipeline(name="ch07-movielens-original-split")
   def pipeline(dataset: str = "ml-latest-small", random_init: int = 42):
       download = download_movielens(dataset=dataset)
       unzip = unzip_movielens(input_path=download.outputs["output_path_one"], dataset=dataset)
       ratings = csv_to_parquet(inputFile=unzip.outputs["ratings_output_path"])
       split_dataset(input_parquet=ratings.output, random_state=random_init)


   if __name__ == "__main__":
       compiler.Compiler().compile(pipeline, "ch07_movielens_original_split.yaml")
   ```
3. 컴파일하고 실행한다.
   ```powershell
   Push-Location ch07
   python movielens_original_split_pipeline.py
   Pop-Location
   python ch07\submit.py ch07\ch07_movielens_original_split.yaml ch07-movielens-original-split --run ch07-movielens-original-split-1
   ```
4. 약 4분 뒤 `split-dataset`이 실패한다. **split-dataset → Logs**를 연다.

   ![저자 split_dataset이 user_id 열을 찾지 못해 실패한 로그.](/images/ml-platform-engineering/sop/ch07-d-orig-split-log.png)

   ```text
   n_users = ratings_df.user_id.max()
   AttributeError: 'DataFrame' object has no attribute 'user_id'. Did you mean: 'userId'?
   ```

MovieLens의 열 이름은 `userId`, `movieId`, `rating`, `timestamp`다. 그런데 원본 `split_dataset`에는 `ratings_df.user_id`, `ratings_df.item_id`로 최대값을 읽는 두 줄이 남아 있다. 앞의 CSV 변환에도 이 이름으로 바꾸는 단계가 없으니 25M을 받아도 같은 줄에서 실패한다.

두 값은 함수 뒤쪽에서 쓰이지 않는다. 그래서 `split_ratings`에서는 이 두 줄만 지웠다. 학습 전처리도 `userId`, `movieId`를 쓰므로, 이 두 줄을 통과시키려고 열 이름 전체를 바꾸지는 않는다. 컴파일은 DataFrame 연산까지 실행하지 않는다. YAML이 만들어졌다고 이 오류가 걸러지는 것은 아니다.

### D-3. 고친 준비 파이프라인 실행

1. 수정 파이프라인을 만든다. 원본은 QA가 분할 업로드(`u2`) 뒤에만 돌았는데, 여기서는 movies 업로드(`u1`)도 기다리게 했다. `ch07\movielens_fixed_pipeline.py`로 저장한다.
   ```python
   """MovieLens preparation with the schema fix, prefix parameter and full QA."""
   import sys
   from pathlib import Path

   from kfp import compiler, dsl

   sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "upstream" / "movie-recommender-project"))
   from data_components import csv_to_parquet  # noqa: E402

   from movielens_components import (  # noqa: E402
       download_movielens, put_to_s3, qa_movielens, split_ratings, unzip_movielens)


   @dsl.pipeline(name="ch07-movielens-prep")
   def pipeline(minio_bucket: str = "datasets", dataset: str = "ml-latest-small", random_init: int = 42,
                min_total_rows: int = 100000):
       download = download_movielens(dataset=dataset)
       unzip = unzip_movielens(input_path=download.outputs["output_path_one"], dataset=dataset)
       ratings = csv_to_parquet(inputFile=unzip.outputs["ratings_output_path"])
       movies = csv_to_parquet(inputFile=unzip.outputs["movies_output_path"])
       split = split_ratings(input_parquet=ratings.output, random_state=random_init)
       u1 = put_to_s3(inputFile=movies.output, upload_file_name="movies.parquet.gzip",
                      bucket=minio_bucket, prefix=dataset)
       u2 = put_to_s3(inputFile=split.output, bucket=minio_bucket, prefix=dataset)
       qa = qa_movielens(bucket=minio_bucket, dataset=dataset, min_total_rows=min_total_rows).after(u1, u2)
       for task in [download, unzip, ratings, movies, split, u1, u2, qa]:
           task.set_caching_options(False)


   if __name__ == "__main__":
       compiler.Compiler().compile(pipeline, "ch07_movielens_prep.yaml")
   ```
2. 컴파일하고 실행한다.
   ```powershell
   Push-Location ch07
   python movielens_fixed_pipeline.py
   Pop-Location
   python ch07\submit.py ch07\ch07_movielens_prep.yaml ch07-movielens-prep --run ch07-movielens-prep-1
   ```
3. 이번 실행은 약 7분 걸렸고, 대부분은 작업 Pod마다 pandas와 pyarrow를 설치하는 시간이었다. 여덟 작업이 모두 초록색이면 된다.

   ![MovieLens 준비의 여덟 작업이 모두 성공한 실행 그래프.](/images/ml-platform-engineering/sop/ch07-d-prep-graph.png)

   그래프의 `csv-to-parquet`과 `csv-to-parquet-2`는 같은 컴포넌트를 ratings와 movies에 한 번씩 쓴 것이다. `put-to-s3`, `put-to-s3-2`도 마찬가지다.
4. http://localhost:8888/buckets/datasets/ml-latest-small/ 에서 네 파일을 확인한다.

   ![datasets 버킷의 ml-latest-small 아래 네 parquet 파일.](/images/ml-platform-engineering/sop/ch07-d-datasets-bucket.png)

   ```text
   datasets
     ml-latest-small
       movies.parquet.gzip
       train.parquet.gzip
       val.parquet.gzip
       test.parquet.gzip
   ```

원본의 `put_to_minio`는 `create_bucket`이 `BucketAlreadyExists`를 던질 때만 넘어간다. 같은 계정이 이미 만든 버킷이면 S3 구현에 따라 `BucketAlreadyOwnedByYou`가 올 수 있어서, 수정본은 `head_bucket`으로 먼저 확인한다. 이 부분은 코드를 읽고 고친 것이고, 원본 업로드를 이 환경에서 따로 돌려 보지는 않았다. Pod에서 쓰는 S3 주소 `http://minio-service.kubeflow:9000`과 계정은 책과 같다.

### D-4. QA가 검사하는 것

1. 저자의 `qa_data`를 작은 데이터에 그대로 돌려 본다. `ch07\movielens_original_qa_pipeline.py`로 저장한다.
   ```python
   """Author's qa_data unchanged, pointed at the small dataset uploaded by ch07-movielens-prep."""
   import sys
   from pathlib import Path

   from kfp import compiler, dsl

   sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "upstream" / "movie-recommender-project"))
   from data_components import qa_data  # noqa: E402


   @dsl.pipeline(name="ch07-movielens-original-qa")
   def pipeline(minio_bucket: str = "datasets", dataset: str = "ml-latest-small"):
       qa_data(bucket=minio_bucket, dataset=dataset).set_caching_options(False)


   if __name__ == "__main__":
       compiler.Compiler().compile(pipeline, "ch07_movielens_original_qa.yaml")
   ```
   ```powershell
   Push-Location ch07
   python movielens_original_qa_pipeline.py
   Pop-Location
   python ch07\submit.py ch07\ch07_movielens_original_qa.yaml ch07-movielens-original-qa --run ch07-movielens-original-qa-1
   ```
2. **qa-data → Logs**에서 `AssertionError`를 확인한다.

   ![25M 기준 행 수 조건 때문에 저자 QA가 실패한 로그.](/images/ml-platform-engineering/sop/ch07-d-orig-qa-log.png)

   원본은 train의 열 수가 4인지, 행 수가 `0.75 × 25 × 1,000,000` 이상인지 assert로 확인한다. 작은 자료의 train은 75,627행이라 데이터에 아무 문제가 없어도 실패한다. 거꾸로 열 이름이 틀리거나 평점이 범위를 벗어나도, 열이 네 개이고 행만 많으면 통과한다.
3. D-3 실행의 **qa-movielens → Logs**를 연다.

   ![네 파일의 행 수, 결측, 평점 범위, 분할 간 중복을 확인한 QA 로그.](/images/ml-platform-engineering/sop/ch07-d-prep-qa-log.png)

   ```text
   train: rows=75627 share=0.750 nulls=0 rating_out_of_range=0
   val: rows=15125 share=0.150 nulls=0 rating_out_of_range=0
   test: rows=10084 share=0.100 nulls=0 rating_out_of_range=0
   total=100836 duplicate_keys_across_splits=0 ratings_with_unknown_movie=0
   timestamp range: 1996-03-29 18:36:55 2018-09-24 14:27:30
   QA passed!
   ```

수정 QA가 확인하는 범위와 아직 남은 것은 다음과 같다.

| 확인 범위 | 이번 QA | 추가로 볼 내용 |
| --- | --- | --- |
| 스키마 | 네 분할의 열 이름과 순서 | 타입과 시간 단위 |
| 식별자 | `userId`, `movieId` 결측, movies에 없는 영화 | 중복 키의 의미 |
| 값 | 평점 0.5~5.0 범위 | 잘못된 timestamp |
| 분할 | 행 수와 비율, (userId, movieId) 키의 분할 간 중복 | 시간 순서와 분할 목적의 적합성 |
| 저장 결과 | 네 파일이 모두 읽히는지 | 같은 원천 버전의 묶음인지, 이전 실행의 파일이 섞이지 않았는지 |
| 재현 정보 | 다운로드 아티팩트의 `sha256` 메타데이터 | 코드 커밋과 산출물 위치를 함께 남기는 manifest |

`min_total_rows`는 파라미터라서 25M을 쓸 때는 `dataset=ml-25m`, `min_total_rows=25000000`으로 바꿔 실행하면 된다. 이 조합은 이번에 돌려 보지 않았다.

## E. 결과 정리와 다음 단계

지금 위치는 전체 그림의 ⑩에서 ⑪, ⑫로 넘어가는 지점이다.

### E-1. 실행 기록 확인

KFP의 **Experiments → ch07-data-prep**에서 일곱 실행을 본다.

![ch07-data-prep 실험의 실행 일곱 개와 상태.](/images/ml-platform-engineering/sop/ch07-e-runs.png)

| 실행 | 결과 | 확인한 것 |
| --- | --- | --- |
| `ch07-joke-parameters-1` | 성공 | 값으로 전달되는 파라미터 |
| `ch07-joke-artifacts-1` | 성공 | 주소로 전달되는 아티팩트 |
| `ch07-idcard-original-1` | 실패 | 저자 분할의 이미지와 라벨 어긋남, clip 중복 |
| `ch07-idcard-fixed-1` | 성공 | stem 짝짓기와 clip 단위 분할 |
| `ch07-movielens-original-split-1` | 실패 | `user_id` 열 이름 오류 |
| `ch07-movielens-prep-1` | 성공 | 네 parquet 업로드와 수정 QA |
| `ch07-movielens-original-qa-1` | 실패 | 25M 고정 행 수 조건 |

실패한 실행도 지우지 않는다. 어떤 입력과 코드에서 어떻게 실패했는지가 수정의 근거가 된다.

### E-2. 무작위 분할과 서비스의 시간

책 코드의 무작위 분할은 예제 흐름을 이해하는 출발점으로 충분하다. 실제로 미래 추천을 평가하려면 학습에 미래 평점이 섞이지 않는지, 사용자별 시점과 후보 영화를 어떻게 정할지 따로 설계해야 한다. 이번 QA의 timestamp 범위는 세 분할이 모두 1996~2018년을 섞어 갖는다는 뜻이다.

신규 사용자 추천과 기존 사용자의 미래 행동 예측도 서로 다른 평가 문제다. 시간 순서로 한 번 나눴다고 두 문제를 모두 검증한 것은 아니다.

누수의 원인은 도메인마다 다르다. 탐지에서는 C-2에서 본 clip 중복처럼 문서, 영상, 사람의 중복이, 추천에서는 미래 행동과 집계값이 문제가 된다.

### E-3. 데이터 계약 예시

다음 YAML은 실행 설정이 아니다. MovieLens 출력의 확인 항목을 정리한 예시로, 이번 수정 QA가 구현한 항목과 남은 항목을 함께 적었다.

```yaml
dataset: movie-ratings
contract_version: "1"
location: s3://datasets/ml-latest-small/
required_columns: [userId, movieId, rating, timestamp]
checks:
  - identifiers_are_not_null          # 구현
  - ratings_are_within_agreed_range   # 구현, 0.5~5.0
  - all_expected_splits_are_present   # 구현
  - no_key_overlap_across_splits      # 구현
  - timestamps_use_the_agreed_unit    # 남음
split:
  source_example: random_75_15_10
  evaluation_purpose: define_before_training
lineage:
  - source_checksum                   # 다운로드 아티팩트 메타데이터
  - code_commit
  - split_seed
  - output_snapshot
on_failure:
  action: stop_and_keep_diagnostic_results
```

검사가 실패하면 학습으로 넘기지 않고 원천 식별자와 오류 보고서를 보관한다. 원본을 덮어써서 고치면 어떤 입력에서 실패했는지 재현하기 어렵다. 신분증 데이터와 진단 자료는 허용된 접근과 보존 범위 안에서 다룬다.

### E-4. 실패 위치와 확인할 것

| 증상 | 확인할 것 |
| --- | --- |
| Notebooks 메뉴가 없음 | KFP standalone과 전체 Kubeflow 설치의 차이 |
| 신분증 다운로드 작업이 `tarfile` 오류로 실패 | Box 주소의 HTTP 404, C-1의 S3 원천으로 교체했는지 |
| PC의 파일을 다음 Pod가 찾지 못함 | KFP 입출력 아티팩트 또는 실제 공유 볼륨 연결 |
| 이미지나 라벨이 0개로 잡힘 | 압축 내부의 `MINIDATA`/`DATA` 경로와 해제 결과 |
| 이미지와 박스가 맞지 않음 | stem 대응, 좌표 형식, 변환과 분할 이전의 파일 쌍 |
| MovieLens split의 AttributeError | `user_id`/`item_id`와 실제 CSV 열 이름 차이 |
| 업로드 단계 실패 | Pod 기준 S3 주소, 버킷 생성 권한과 기존 버킷 처리 |
| 작은 데이터에서 저자 QA 실패 | 25M 전체 자료를 전제로 한 고정 행 수 조건 |
| QA는 성공했지만 후속 학습 실패 | 열 이름과 타입, 모든 분할과 movies 객체의 존재 여부 |
| 작업 Pod가 `ImagePullBackOff` | docker.io 시간 초과, B-2의 이미지 적재 방법 |
| `kind load docker-image`의 `content digest not found` | `docker save --platform linux/amd64`로 저장한 뒤 `kind load image-archive` |
| 작업이 오래 `Running` | Pod 안의 `pip install`, 처음 실행은 패키지 설치 시간이 대부분 |

다운로드 코드에서는 HTTP 성공 여부, TLS 검증, 압축 파일 형식도 확인한다. ZIP이나 tar는 경로를 검증해 의도한 작업 폴더 안에만 풀고, 외부 응답을 검증 없이 학습 데이터로 취급하지 않는다.

### E-5. 실습 종료

1. JupyterLab 창을 `Ctrl+C`로 끈다.
2. 8장에서 이 데이터를 쓸 계획이면 클러스터와 버킷은 그대로 둔다. 7장 결과만 지우려면 저장소 화면에서 `ch07-raw` 버킷과 `datasets/ml-latest-small` 폴더를 지우고, KFP에서 `ch07-` 실행을 **Archive**한 뒤 파이프라인을 삭제한다.
3. 클러스터 전체를 지우는 방법은 [4장의 실습 종료](../04-experiments-features-pipelines/#실습-종료)와 같다.

로컬 노트북과 컴파일을 끝내도 클러스터의 실행 기록과 S3 객체는 따로 남는다. 이전 장의 클러스터를 지우기보다, 남길 실행의 아티팩트와 데이터 스냅샷을 골라 관리한다.

## 참고 자료

- [TensorFlow Data Validation의 시작 안내](https://www.tensorflow.org/tfx/data_validation/get_started): 통계와 스키마, 이상 데이터 검증, training-serving skew와 drift의 구분.
- [출판사의 7장 개요](https://www.manning.com/preview/machine-learning-platform-engineering/chapter-7): 노트북 환경, 데이터 전달과 컴포넌트 작성 방식, 두 데이터 준비 프로젝트의 범위.
- [Kubeflow 노트북 이미지](https://www.kubeflow.org/docs/components/notebooks/container-images/): 서버 이미지와 ML 프레임워크 이미지의 계층.
- [KFP 데이터 타입](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/data-types/), [아티팩트 전달](https://www.kubeflow.org/docs/components/pipelines/user-guides/data-handling/artifacts/): 타입, 경로와 메타데이터의 역할.
- [YOLO 탐지 데이터 형식](https://docs.ultralytics.com/datasets/detect/): 클래스와 정규화 박스 좌표.
- [MovieLens 25M 데이터 설명](https://files.grouplens.org/datasets/movielens/ml-25m-README.html): 파일 간 ID, 평점과 시간 필드의 의미.
- [Kubeflow Notebooks 개요](https://www.kubeflow.org/docs/components/notebooks/overview/): 클러스터 안에서 실행하는 개발 환경의 범위.
- [객체 탐지 데이터 준비 진입점](https://github.com/practical-mlops/object-detection-project/blob/c6afb114e628e776a76f9ac50b45899aff5e8eaf/data_prep_pipeline.py): 다운로드, 분할과 파일 목록 출력.
- [영화 추천 데이터 준비 파이프라인](https://github.com/practical-mlops/movie-recommender-project/blob/4e0a808e0dca3aef16850cd14df47d2fda9f9bd2/01_data_preparation_pipeline.py): 컴포넌트 연결과 실행 파라미터.
- [영화 데이터 준비 컴포넌트](https://github.com/practical-mlops/movie-recommender-project/blob/4e0a808e0dca3aef16850cd14df47d2fda9f9bd2/data_components/dataset_preparation.py): 변환, 분할, 업로드와 실제 QA 범위.
- [영화 학습 전처리](https://github.com/practical-mlops/movie-recommender-project/blob/4e0a808e0dca3aef16850cd14df47d2fda9f9bd2/training_and_validation_components/data_preprocessing.py): 다음 단계가 기대하는 열과 저장 경로.

[이전: 06. 모델을 프로덕션으로](../06-productionizing-models/), [시리즈 목차](../)
