---
title: "09. 모델 학습과 검증 II"
description: "PVC로 데이터를 한 번만 준비하고, TensorBoard와 MLflow로 학습과 실행 사이의 근거를 남기며, 추천 모델의 지표와 등록 판단을 실제 실행으로 확인하기"
date: 2026-10-18T21:30:00+09:00
lastmod: 2026-11-08T18:00:00+09:00
weight: 90
draft: false
tags: ["book-club", "ml-platform-engineering", "model-training", "mlflow", "tensorboard", "kubeflow"]
---

8장의 파이프라인은 일단 돌아간다. 불편한 점은 그다음에 보인다. 다운로드 컴포넌트가 받은 데이터를 학습과 검증 컴포넌트가 또 내려받는다. 학습이 어떻게 흘러갔는지는 끝난 뒤 로그를 뒤져야 안다. 어제 모델과 오늘 모델 중 무엇을 쓸지는 사람이 기억해야 한다.

9장은 이 세 가지를 다룬다. 데이터는 PVC와 객체 저장소에 두고, 한 번의 학습 안은 TensorBoard로 보고, 여러 실행 중 무엇을 넘길지는 MLflow로 정한다. 책은 신분증 탐지(YOLO)에 PVC와 TensorBoard를, 영화 추천(MovieLens)에 객체 저장소와 MLflow를 쓴다. 도구가 갈린 것은 우열 때문이 아니라 데이터 모양과 묻는 질문이 달라서다.

두 파이프라인을 실제 클러스터에서 돌린 과정은 [실습 순서](/docs/tech/machine-learning-platform-engineering/practice/ch09/#book-ch09-sop)에 있다. 돌려 보니 책 본문과 저자 코드가 어긋나는 곳이 꽤 있었고, 파이프라인이 기록한 숫자도 생각과 다른 것을 말하고 있었다. 그 이야기를 설명 중간중간에 함께 적었다.

## 전체 그림 {#platform-map}

9장의 구성 요소는 많지만 결국 "무엇을 어디로 넘기는가"의 문제다. 아래 그림은 이번 실습에서 실제로 쓴 위치와 전달물이다. 강조된 상자가 이 장의 범위이고, 7장에서 준비한 입력과 10장 이후로 이어질 부분을 구분해 두었다.

```mermaid
%%{init: {"flowchart": {"rankSpacing": 25, "nodeSpacing": 18, "padding": 6}}}%%
flowchart LR
    accTitle: 9장 실습에서 구성 요소가 주고받는 것
    accDescr: 개발자 PC에서 컴파일한 파이프라인을 KFP에 제출하면 작업 Pod가 생성된다. 탐지 Pod는 PVC의 /data를 함께 마운트해 데이터와 학습 로그를 남기고 TensorBoard가 그 로그를 읽는다. 추천 Pod는 S3의 parquet를 직접 읽고 MLflow에 파라미터와 지표를, mlflow-artifacts 버킷에 모델 파일을 남긴다. 등록된 모델 버전과 별칭은 로컬 확인과 10장의 서빙이 사용한다.
    subgraph PC["개발자 PC"]
        SDK["KFP SDK 2.11<br/>컴파일과 제출"]
        LOCAL["로컬 Python 3.9<br/>지표 재계산"]
    end
    subgraph KIND["kind 클러스터 book-env"]
        subgraph KF["kubeflow 네임스페이스"]
            API["KFP UI와 API<br/>Argo Workflows"]
            PREP["7장 결과<br/>분할 parquet"]
            S3[("S3 데이터 버킷<br/>ch09-datasets")]
            PVC[("실행 단위 PVC<br/>RWO")]
            DET["탐지 작업 Pod<br/>YOLO 학습"]
            REC["추천 작업 Pod<br/>행렬 분해 학습"]
            TB["TensorBoard Pod"]
            ART[("S3 mlflow-artifacts<br/>model.pth")]
        end
        subgraph MLNS["mlflow 네임스페이스"]
            ML["MLflow 3.0.0<br/>실행, 레지스트리"]
        end
    end
    subgraph NEXT["10장 이후"]
        SERVE["BentoML, Yatai 서빙<br/>모니터링"]
    end
    SDK -->|"① YAML, 파라미터"| API
    PREP -->|"② 데이터셋 URI"| S3
    API -->|"③ Pod 생성"| DET
    API -->|"③"| REC
    DET -->|"④ /data 마운트"| PVC
    DET -->|"⑤ 이벤트 파일, best.pt"| PVC
    TB -->|"⑥ 읽기 전용 마운트"| PVC
    S3 -->|"⑦ parquet, Dataset"| REC
    REC -->|"⑧ 파라미터, 지표, run_id"| ML
    REC -->|"⑨ model.pth"| ART
    ML -->|"⑩ 모델 버전, staging 별칭"| LOCAL
    ML -.->|"⑪ 별칭 조회"| SERVE
    classDef thisch fill:#e8f1ff,stroke:#2f6fd6,stroke-width:2px;
    classDef prev fill:#f3f3f3,stroke:#999;
    classDef next fill:#fff6e5,stroke:#d08a00,stroke-dasharray:4 3;
    class SDK,LOCAL,API,S3,PVC,DET,REC,TB,ART,ML thisch;
    class PREP prev;
    class SERVE next;
```

| 번호 | 누가 | 무엇을 넘기는가 | 어디에 남는가 | 실습 단계 |
| --- | --- | --- | --- | --- |
| ① | 개발자 PC의 SDK | 컴파일한 파이프라인 YAML과 실행 파라미터 | KFP 파이프라인 버전과 run 기록 | [B-3](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-b-3), [D-3](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-d-3) |
| ② | 7장 데이터 준비(여기서는 대체 스크립트) | `train`, `val`, `test` parquet의 버킷과 경로 | `ch09-datasets/ml-latest-small/` | [D-1](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-d-1) |
| ③ | KFP와 Argo Workflows | 컴포넌트별 Pod와 입력 값 | `kubeflow` 네임스페이스의 Pod | [B-4](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-b-4), [D-4](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-d-4) |
| ④ | 탐지 작업 Pod가 `createpvc`의 PVC를 마운트 | `/data` 마운트 경로, 원본과 분할된 이미지, 라벨 | PVC(로컬 디스크) | [B-4](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-b-4), [B-5](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-b-5) |
| ⑤ | 탐지 학습 Pod | TensorBoard 이벤트 파일, `best.pt` | PVC의 `/data/runs`, `best.pt` 사본은 `mlpipeline` | [B-6](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-b-6) |
| ⑥ | TensorBoard Pod가 같은 PVC를 마운트 | 읽기 전용으로 이벤트 파일 읽기 | 화면만, 파일은 PVC에 있음 | [C-2](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-c-2) |
| ⑦ | 추천 데이터 준비 Pod | parquet 내용과 negative sampling 결과 | `mlpipeline` 버킷의 KFP 아티팩트 | [D-4](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-d-4) |
| ⑧ | 추천 학습, 검증 Pod | 파라미터, epoch별 손실, `precision_50`, `recall_50`, `rms` | MLflow의 PostgreSQL | [E-1](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-e-1) |
| ⑨ | 추천 학습 Pod | `model.pth`와 `MLmodel` | `mlflow-artifacts` 버킷 | [E-2](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-e-2) |
| ⑩ | promote Pod, 로컬 Python | 등록 모델 버전과 `staging` 별칭 | MLflow 모델 레지스트리 | [E-2](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-e-2), [F-2](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-f-2) |
| ⑪ | 10장 서빙 | 별칭이 가리키는 모델 | 다음 장 | 이 장에서는 실행하지 않음 |

추천 파이프라인 한 번이 주고받는 순서는 아래와 같다. 눈여겨볼 것은 `train-model`이 내놓는 **MLflow run_id 하나**다. 검증, 등록, 이후 추론이 모두 이 값으로 이어진다.

```mermaid
sequenceDiagram
    accTitle: 추천 학습 파이프라인 한 번의 실행 순서
    accDescr: KFP가 품질 검사와 데이터 준비를 실행한 뒤 학습 Pod가 MLflow에 파라미터와 손실을 기록하고 모델 파일을 S3에 올리며 run_id를 출력한다. 검증 Pod는 같은 run_id에 지표를 더하고, 등록 Pod는 현재 staging 버전과 지표를 비교해 새 버전 등록 여부를 정한다.
    participant U as 개발자
    participant K as KFP
    participant Q as qa-data
    participant P as 데이터 준비 Pod
    participant T as train-model
    participant M as MLflow
    participant S as S3 mlflow-artifacts
    participant V as validate-model
    participant R as promote
    U->>K: 실행 생성(버킷, 데이터셋, 학습률)
    K->>Q: 버킷과 데이터셋 이름
    Q-->>K: 열 수와 행 수 통과
    K->>P: negative-sampling, get-test-valid-dataset
    P-->>K: Dataset 아티팩트 3개
    K->>T: 학습 데이터, test 데이터, 사용자와 영화 수
    T->>M: 파라미터, epoch별 학습과 test 손실
    T->>S: model.pth 업로드
    T-->>K: run_id 출력
    K->>V: run_id, val 데이터
    V->>M: 같은 run_id에 precision_50, recall_50, rms
    K->>R: run_id
    R->>M: staging 별칭 버전과 지표 비교
    alt 첫 등록이거나 기준 통과
        R->>M: 새 버전 등록, staging 별칭 이동
    else 기준 미달
        R-->>K: 기존 staging 유지
    end
```

## 반복 다운로드를 PVC 하나로 묶는다 {#pvc-concepts}

8장의 탐지 파이프라인에서는 같은 데이터가 세 번 내려받아진다. 다운로드 컴포넌트가 전체를 받고, 학습 컴포넌트가 분할 결과를 다시 받고, 검증 컴포넌트가 검증 분할을 또 받는다. 컴포넌트마다 다른 Pod에서 돌고, Pod 사이에는 공유 디스크가 없기 때문이다. 그래서 KFP 아티팩트로 S3에 올렸다 내려받기를 반복한다. 노트북이었다면 같은 폴더를 계속 썼을 것이다. 데이터가 크면 이 복사가 학습보다 오래 걸린다.

Kubernetes의 답은 PersistentVolumeClaim(PVC)이다. PVC는 "이만한 크기, 이런 접근 방식의 저장 공간이 필요하다"는 요청이고, StorageClass가 그 요청을 실제 볼륨(PV)으로 만들어 붙인다. 파이프라인 맨 앞에서 PVC를 만들고 모든 컴포넌트가 이를 `/data`에 마운트하면 다운로드는 한 번으로 끝난다. 다음 단계는 로컬 파일처럼 읽으면 된다.

책이 "MinIO는 POSIX 파일시스템이 아니다"라고 강조하는 것도 같은 맥락이다. 객체 저장소에서는 파일을 옮기거나 폴더를 나누는 일이 전부 업로드와 다운로드다. 그런데 YOLO는 `images/`와 `labels/` 폴더 구조를 파일 경로로 기대한다.

대신 PVC를 쓰면 신경 쓸 것이 셋 생긴다.

첫째는 접근 모드다. 책이 쓰는 `ReadWriteOnce`(RWO)는 "한 노드에서만 읽고 쓸 수 있다"는 뜻이다. 한 Pod로 제한되는 것이 아니어서 같은 노드의 Pod 여럿은 함께 마운트할 수 있다. 노드가 하나인 kind에서는 문제가 드러나지 않는다. 노드가 여럿이면 다음 컴포넌트가 다른 노드에 배치되는 순간 마운트 대기에 걸린다. 여러 노드에서 동시에 써야 한다면 `ReadWriteMany`를 지원하는 NFS나 CephFS 같은 스토리지가 필요하다.

둘째는 의존 관계다. 아티팩트로 데이터를 넘길 때는 KFP가 입출력 연결을 보고 순서를 정했다. PVC로 넘기면 KFP는 데이터 흐름을 모르므로 `.after()`로 순서를 직접 적어야 한다. 같은 이유로 **캐시도 PVC 안의 파일을 모른다**. 입력 파라미터가 같으면 KFP는 다운로드와 분할을 "이미 했다"며 건너뛰는데, 새 실행의 PVC는 비어 있다. 실습의 [B-5](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-b-5)에서 실제로 이 실패를 만났다.

셋째는 수명이다. `CreatePVC`와 `DeletePVC`로 실행마다 볼륨을 만들고 지우지만, `DeletePVC`는 마지막 단계가 성공해야 돈다. 실패하거나 취소한 실행의 PVC는 남는다. PVC를 참조하는 Pod가 남아 있으면 삭제 요청 뒤에도 `Terminating`에 머무는데, 끝난 Argo 작업 Pod도 여기에 포함됐다. 책의 팁인 `TTL_SECONDS_AFTER_WORKFLOW_FINISH`는 끝난 워크플로와 Pod를 치워 이 참조를 끊는 설정이다.

그렇다고 PVC가 객체 저장소를 대체하지는 않는다. 둘은 역할이 다르다. 데이터셋 버전, 모델, 평가 결과처럼 실행 뒤에도 남아야 하는 것은 객체 저장소에 둔다. 실행 단위 PVC는 그 실행 동안 여러 단계가 같은 파일을 빠르게 나눠 쓰는 작업 공간이다. 책도 추천 예제에서는 S3의 parquet를 바로 읽는다. 표 데이터는 파일 몇 개라 네트워크로 읽어도 금방 시작하고, 이미지 수백 장을 반복해 읽는 탐지 학습은 로컬 볼륨이 유리하다.

| 기준 | 실행 단위 PVC | S3 직접 읽기 |
| --- | --- | --- |
| 시작 비용 | 처음에 전체 복사가 필요하다 | 바로 읽기 시작한다 |
| 반복 읽기 | 로컬 디스크 속도 | 매번 네트워크를 탄다 |
| 실행 뒤 보존 | 정리 대상이므로 원본 보관에 쓰지 않는다 | 버전을 두고 보존한다 |
| 실패한 실행 | PVC가 남아 수동 정리가 필요하다 | 남는 것이 없다 |
| 여러 노드 | RWO면 같은 노드에 묶인다 | 제약이 없다 |
| 계보 | 경로만으로는 어떤 데이터인지 알 수 없다 | 버킷과 경로가 데이터셋 이름이 된다 |

한 가지 더 있다. 공유 저장소가 계보를 대신해 주지는 않는다. 실행이 끝나 PVC가 지워지면 `/data/train`에 무엇이 있었는지 알 길이 없다. 원본 URI와 분할 시드처럼 같은 상태를 다시 만들 수 있는 정보는 실행 파라미터나 MLflow에 따로 남겨야 한다.

## 책 코드와 실제 저장소의 차이: PVC 파이프라인 {#pvc-code-gaps}

책의 리스팅 9.1~9.9는 저자 저장소 [object-detection-project](https://github.com/practical-mlops/object-detection-project)의 PVC 파이프라인(커밋 `c6afb11`)과 거의 같다. 그대로 돌리면 여러 곳에서 막힌다. 환경 탓인 것도 있지만, 일부는 어디서 돌려도 생기는 논리 문제다.

| 위치 | 책과 저자 코드 | 실제로 일어나는 일 | 이 실습의 수정 |
| --- | --- | --- | --- |
| `CreatePVC` | `storage_class_name='local-path'` | kind의 local-path 프로비저너는 `standard`라는 이름으로 등록돼 있다. 없는 클래스를 지정하면 PVC가 `Pending`에 머문다 | `standard` |
| PVC 이름 | 고정 이름 `yolo-pipeline-pvc`를 문자열로 각 단계에 전달 | 두 번째 실행부터 이름이 겹친다. 문자열 전달이라 `createpvc`와의 순서도 보장되지 않는다 | `pvc_name_suffix`로 실행마다 새 이름을 만들고 `pvc.outputs['name']`을 전달 |
| 크기 | `1Gi` | 내려받는 압축 파일이 1.2GB이고, 분할 단계가 `shutil.copy2`로 복사한다(책 주석은 "move"라고 하지만 실제로는 복사). 원본과 분할본이 함께 남는다 | `5Gi`. local-path는 크기를 강제하지 않아 1Gi도 동작은 하지만 실제 클러스터에서는 부족하다 |
| 분할 | `glob`으로 이미지 목록과 라벨 목록을 따로 만든 뒤 위치로 짝지어 `train_test_split` | 두 목록의 순서가 다르다. 이번 실행에서 570쌍 중 **570쌍이 다른 파일끼리** 묶였다. 이미지는 train으로, 그 라벨은 val로 가는 일이 생긴다 | 파일 이름 기준으로 짝을 맞춘 뒤 분할 |
| 학습 로그 위치 | 책은 "마운트 지점을 project로 쓴다"고 설명 | 코드는 `project=os.path.dirname(args.model_output)`로 KFP 출력 경로에 쓴다. PVC에는 로그가 없어 TensorBoard가 볼 것이 없다 | `project='/data/runs'` |
| TensorBoard 기록 | 언급 없음 | Ultralytics는 TensorBoard 기록이 설정으로 꺼져 있고 `tensorboard` 패키지도 필요하다 | `pip install tensorboard`, `yolo settings tensorboard=True` |
| 학습 이미지 | `python:3.11-slim`에 `apt-get install libgl1-mesa-glx` 후 `pip install ultralytics torch` | 현재 `python:3.11-slim`의 기반인 Debian trixie에는 `libgl1-mesa-glx` 패키지가 없다([Debian 패키지 검색](https://packages.debian.org/search?keywords=libgl1-mesa-glx&searchon=names&suite=all&section=all) 기준, 이 단계는 직접 실행하지 않았다). 버전을 고정하지 않은 `torch`는 CUDA 빌드를 받아 수 GB를 내려받고, 검증 컴포넌트의 `ultralytics 8.3.56`과 학습 쪽 버전도 어긋난다 | 검증과 같은 `ultralytics/ultralytics:8.3.56-cpu` 이미지 사용 |
| 캐시 | 검증 단계만 캐시를 끔 | 재실행하면 다운로드와 분할이 캐시로 건너뛰어 새 PVC가 빈 채로 학습이 실패한다 | 다운로드, 분할, 학습도 캐시를 끔 |

학습 이미지를 바꾼 탓에 문제가 하나 더 생겼다. 학습 스크립트를 `/train.py`에 쓰면 이 이미지 안의 `/ultralytics` 소스 폴더가 파이썬 경로에서 먼저 잡혀 `cannot import name 'YOLO'`가 난다. 스크립트 위치를 `/tmp/train.py`로 옮겨 피했다. 저자 코드가 아니라 이미지 교체에서 온 문제다.

## TensorBoard는 한 번의 학습 안을 본다 {#tensorboard-concepts}

PVC로 데이터 복사를 줄였다면 다음 질문은 "학습이 잘 되고 있는가"다. 끝나기 전에 알고 싶다. TensorBoard는 학습 코드가 남긴 이벤트 파일을 읽어 epoch별 손실, 학습률, 검증 지표, 모델 그래프를 그린다. 학습 Pod가 PVC에 이벤트 파일을 쓰고 TensorBoard Pod가 같은 PVC를 마운트하면, 학습 도중에도 곡선이 갱신된다. 책이 TensorBoard를 PVC 바로 뒤에 둔 이유다.

다만 이 그래프로 알 수 있는 것에는 한계가 있다. 그 실행에서 손실이 줄었는지, 학습률 스케줄이 의도대로 움직였는지, 과적합 조짐이 있는지는 보인다. 과적합 조짐이란 학습 손실은 주는데 검증 손실이 느는 현상이다. 모델 구조가 의도한 그래프인지도 확인할 수 있다.

그 검증 지표가 배포 뒤 성능을 대표하는지는 따로 따져야 한다. YOLO는 매 epoch `val` 분할로 지표를 계산하고 그 값으로 `best.pt`를 고른다. 저자의 검증 컴포넌트도 같은 `val` 분할을 다시 평가한다. 그래서 이번 실행에서 두 값이 `mAP50 0.995`, `mAP50-95 0.964`로 똑같이 나왔다. `test` 분할은 어디에서도 쓰이지 않았다. 선택에 쓴 데이터로 잰 점수는 낙관적일 수밖에 없다.

책은 Kubeflow 대시보드의 **TensorBoards** 메뉴에서 PVC를 골라 인스턴스를 띄운다. 이 메뉴는 Kubeflow 전체 설치에 딸린 컨트롤러와 웹 앱이 제공한다. KFP만 설치한 이번 환경에는 없어서, 같은 일을 하는 Deployment를 직접 만들어 PVC를 읽기 전용으로 붙였다. 해 보니 컨트롤러가 대신 해 주던 일(PVC 마운트, 포트 연결, 정리)이 오히려 또렷하게 보였다.

여러 실행을 나란히 놓고 고르는 일은 다른 도구의 몫이다. 책의 구분으로는 TensorBoard가 디버깅과 내부 관찰을, MLflow가 실험 색인과 모델 버전 관리를 맡는다. 이벤트 파일은 PVC와 함께 사라진다. 나중에도 봐야 할 곡선이라면 객체 저장소로 옮기거나 핵심 지표를 MLflow에도 남겨야 한다.

## 추천 모델은 무엇을 맞히는지부터 정한다 {#recommender-concepts}

추천 예제로 넘어가면 데이터 모양부터 다르다. 이미지 폴더가 아니라 `사용자, 영화, 평점, 시각` 네 열짜리 표다. 7장의 데이터 준비 파이프라인이 MovieLens를 parquet로 바꿔 `train`, `val`, `test`로 나눠 S3에 올려 두었고, 9장은 그 파일을 PVC 없이 바로 읽는다. 학습 파이프라인은 다음 단계로 이어진다.

1. **qa-data**: 학습 직전에 데이터 가정을 다시 확인한다. 책은 이것을 데이터 준비와 학습 파이프라인을 떼어 놓는 장치로 설명한다. 준비 쪽이 바뀌어도 학습 쪽이 잘못된 입력을 그대로 받지 않게 하는 계약 검사다.
2. **get-dataset-metadata**: 임베딩 크기를 정할 사용자 수와 영화 수를 구한다.
3. **negative-sampling**: 사용자마다 보지 않은 영화 10편을 평점 0으로 추가한다. 관측된 평점만 학습하면 "본 영화는 다 좋다"는 쪽으로 치우친다.
4. **train-model**: 사용자와 영화 임베딩을 곱한 뒤 작은 MLP로 평점을 예측하는 행렬 분해 모델이다. L1 손실로 학습하고 MLflow에 기록한다.
5. **validate-model**: `val`로 precision@50, recall@50, RMSE를 계산해 같은 MLflow run에 더한다.
6. **promote-model-to-staging**: 현재 `staging` 별칭 모델과 지표를 비교해 새 버전 등록 여부를 정한다.

### 스키마 검사가 잡아야 했던 것 {#schema-contract}

MovieLens 원본의 열 이름은 `userId`, `movieId`, `rating`, `timestamp`다. 그런데 책 리스팅 9.10의 QA는 `user_id`, `item_id`, `rating`을 찾는다. 실제 parquet에 돌리면 `AssertionError: Required columns not found. Found Index(['userId', 'movieId', 'rating', 'timestamp'])`로 실패한다.

저자 저장소의 실제 `qa_data`는 열 이름을 보지 않는다. 열 수(4)와 행 수(1,875만 이상)만 검사하고, 나머지 컴포넌트는 `userId`, `movieId`를 쓴다. 7장의 `split_dataset`에도 `ratings_df.user_id.max()`를 계산하는 줄이 있어 원본과 맞지 않는다. 책이 말하는 스키마 검증을 하려면 열 이름과 타입을 실제 데이터 계약에 맞춰 적어야 한다. 그 필요를 책 자신의 코드가 보여 주는 셈이라 조금 아이러니했다.

ID를 그대로 임베딩 인덱스로 쓰는 것도 계약의 일부다. 모델은 `userId - 1`, `movieId - 1`을 인덱스로 쓰고, 영화 수를 `movieId`의 최댓값으로 정한다. 이번에 쓴 MovieLens ml-latest-small은 영화가 9,724편인데 `movieId` 최댓값은 193,609다. 영화 임베딩이 193,610행이 되고, 학습 파라미터 389만 개 대부분이 한 번도 나오지 않는 ID의 자리다. 실서비스라면 ID를 연속 인덱스로 바꾸는 사전을 만들고, 그 사전도 모델과 함께 버전 관리해야 한다.

### 지표는 사용자 경험의 어느 부분을 재는가 {#recommendation-metrics}

책은 precision@50, recall@50, RMSE를 고른다. 세 지표는 재는 대상이 다르다. 저자 코드가 계산하는 방식까지 보면 해석은 더 달라진다.

먼저 RMSE는 평점 예측 오차다. 그런데 `validate_model`은 배치 32개의 **평균 예측과 평균 정답**으로 RMSE를 낸다. 평균을 내면 오차가 서로 상쇄돼 값이 크게 작아진다. 이번 실행에서 저자 방식의 `rms`는 0.20이었지만 평점 하나하나로 계산하면 1.08이었다. 학습 데이터 평균 평점(3.50)을 모든 영화에 똑같이 예측하는 기준선이 1.05다. 모델이 상수 예측보다도 나을 게 없었다.

precision@50과 recall@50은 이름과 달리 전체 영화에서 상위 50편을 고르는 평가가 아니다. 사용자가 이미 평점을 남긴 `val` 행들 안에서 예측 순으로 50개를 자르고, 평점 3 이상을 "관련 있음"으로 센다. `val` 평점의 81%가 3 이상이고, 사용자의 87%는 `val` 행이 50개보다 적다(중앙값 10개). 상위 50개가 대개 그 사용자의 `val` 행 전부가 되니 0.85, 0.94처럼 높게 나올 수밖에 없다. 아직 보지 않은 수천 편 중 상위 몇 편을 맞히는지, 즉 사용자가 실제로 보게 될 목록의 품질은 재지 않는다.

그래서 실습의 [F-2](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-f-2)에서 같은 모델로 보지 않은 영화 전체를 순위화해 Recall@10과 NDCG@10을 계산했다. 비교 대상은 학습 데이터에서 많이 평가된 순서대로 추천하는 인기순 기준선이다. 모델은 Recall@10 0.0002~0.0016, 인기순은 0.099였다. 추천 목록으로 보면 이 모델은 가장 단순한 기준선에도 한참 못 미친다.

NDCG는 맞힌 영화가 목록 앞쪽에 있을수록 점수를 더 준다. 사용자가 첫 화면 몇 줄만 본다면 Recall보다 경험에 가깝다. 어떤 지표를 쓰든 **기준선과 나란히 놓지 않은 숫자는 판단 근거가 되지 못한다.**

책의 표 9.1과 9.2에도 같은 함정이 있다. 책은 학습률을 1e-2로 바꾼 실행을 "조금 나빠졌다"고 했다. 그런데 표를 보면 recall은 0.63에서 0.86으로, RMSE는 0.290에서 0.284로 오히려 좋아졌다. 지표 해석을 기억에 맡기면 이런 일이 생긴다. 실험 추적이 필요한 이유이기도 하다.

### 후보는 validation으로 고르고 test는 마지막에 한 번 쓴다 {#validation-vs-test}

데이터를 셋으로 나누는 것은 역할이 달라서다. `train`으로 학습하고, `val`로 학습률이나 epoch, 모델 구조 같은 후보를 고르고, 고른 뒤 `test`로 한 번만 일반화 성능을 확인한다.

저자 코드에서는 이 역할이 섞여 있다. `train-model`은 매 epoch **`test` 분할**로 `avg_testing_loss`를 기록한다. 이 곡선을 보고 epoch나 학습률을 고르면 test가 선택에 쓰인 셈이다. 반면 등록 판단은 `val` 지표로 한다. 이 실습은 저자 구조를 유지하되 등록과 비교에는 `val` 지표만 썼고, test 지표는 따로 보고하지 않았다.

### 무작위 분할은 미래로 과거를 맞히게 한다 {#temporal-leakage}

7장의 분할은 평점 행을 무작위로 섞어 75:15:10으로 나눈다. 추천 서비스는 과거 행동으로 미래를 맞혀야 한다. 무작위 분할은 반대로 같은 사용자의 나중 평점을 학습에 넣고 더 이른 평점을 검증에 둔다.

이번 데이터에서 `val` 평점의 **98.8%**가 같은 사용자의 가장 늦은 `train` 평점보다 이른 시각이었다. 취향 변화나 새 영화의 인기처럼 실제 서비스에서 어려운 부분이 평가에서 통째로 빠진다는 뜻이다. 서비스에 가까운 평가를 원하면 시각 기준으로 자르거나 사용자별 마지막 몇 개를 남기는 방식으로 나눠야 한다.

### 콜드 스타트 {#cold-start}

임베딩 모델은 학습에서 본 사용자와 영화만 안다. 무작위 분할에서는 거의 모든 사용자가 학습에 나오므로 이 문제가 가려진다. 이번 `val`에서도 처음 보는 사용자는 0명이었다.

영화 쪽은 다르다. `val`의 635행이 학습에 없던 영화였고, 이 영화들의 임베딩은 초기화된 무작위 값 그대로다. 실습의 [F-3](/docs/tech/machine-learning-platform-engineering/practice/ch09/#ch09-f-3)에서 사용자 50의 추천 상위에 평점 수가 적은 낯선 영화가 몰린 것도 같은 현상이다. 신규 사용자와 신규 영화에는 인기순이나 장르 같은 다른 신호로 답하고, 어떤 경로로 답했는지도 기록해야 한다.

## MLflow는 실행 사이의 계보를 잇는다 {#mlflow-lineage}

TensorBoard가 한 실행의 곡선을 보여 준다면 MLflow는 실행 사이를 잇는다. 어떤 조건의 실행이 어떤 결과를 냈고, 그중 무엇을 지금 쓰는지를 남긴다. 책의 리스팅 9.13은 학습 함수의 입력 인자를 모두 파라미터로, epoch별 손실을 지표로 기록한다. 모델은 요약과 입출력 시그니처를 붙여 아티팩트로 남긴다. 검증 컴포넌트는 다른 Pod에서 돌지만 **같은 run_id**에 지표를 더하므로, 학습과 평가가 갈라져도 기록은 한 줄로 이어진다.

run_id는 KFP 컴포넌트의 문자열 출력이다. KFP는 어떤 Pod가 어떤 입력으로 돌았는지를, MLflow는 어떤 파라미터와 지표와 모델이 한 묶음인지를 기록한다. 이 둘을 잇는 것이 run_id다.

하지만 이것만으로 모델에서 데이터까지 거슬러 올라가지는 못한다. 데이터셋 버전(버킷과 경로)과 코드 버전(이미지나 커밋)을 MLflow 파라미터나 태그로 함께 남겨야 한다. 이번 실행에서도 데이터셋 이름은 파이프라인 파라미터로만 남았고 MLflow run에는 없었다.

### 모델 파일은 누가 업로드하는가 {#artifact-path}

책의 "Uploads to MLflow" 상자는 실무에서 자주 막히는 지점을 짚는다. 이 환경의 MLflow 서버는 아티팩트 저장 위치를 `s3://mlflow-artifacts` 버킷으로 지정했고 아티팩트 프록시는 쓰지 않는다. 이 구성에서 서버는 "이 경로에 올려라"라고 알려 주기만 한다. **모델 파일은 학습 Pod가 S3에 직접 올린다.**

그래서 학습 Pod에 S3 주소와 키가 없으면 메타데이터 기록은 성공하고 모델 업로드에서만 실패한다. 저자 코드에는 이 설정이 없어 학습, 검증, 등록 단계에 S3 주소와 키를 환경 변수로 넣었다. 프록시 모드를 쓰면 학습 코드는 MLflow 주소만 알면 되지만, 큰 파일이 전부 서버 한 곳을 지나간다. 책의 설명대로 권한 관리의 단순함과 전송 병목 사이의 선택이다.

MLflow 3에서는 저장 위치도 바뀌었다. 모델 파일이 run 폴더가 아니라 실험 ID 아래 `models/m-.../` 폴더에 LoggedModel로 저장된다. 그래도 책과 저자 코드의 `runs:/<run_id>/model` 주소는 MLflow 3.0.0에서 그대로 동작했다.

### 등록과 별칭은 "지금 무엇을 쓰는가"를 정한다 {#registry-alias}

실험이 쌓이면 그중 다음 단계로 넘길 모델을 골라 이름을 붙여야 한다. MLflow 레지스트리는 등록 모델 이름 아래 버전을 쌓고, `staging`이나 `prod` 같은 **별칭**이 특정 버전을 가리키게 한다. 서빙은 버전 번호 대신 별칭으로 모델을 찾는다. 롤백은 별칭을 이전 버전으로 옮기는 일이 된다. 4장에서 쓴 `Production` stage는 MLflow 3에서 사용 중단이 예고됐고, 9장은 별칭을 쓴다.

저자의 `promote_model_to_staging`은 새 run의 지표를 현재 `staging` 버전과 비교한다. RMSE가 0.0001보다 더 나빠지지 않고 precision과 recall이 각각 0.3, 0.2보다 더 떨어지지 않으면 새 버전을 `staging`으로 올린다. 구조는 합리적이지만, 실제로 써 보면 걸리는 곳이 네 군데 있다.

첫 실행에서는 `staging`이 없어 `current_staging`이 `None`인데, 바로 다음 줄이 `current_staging.run_id`를 읽어 `AttributeError`가 난다. 코드 순서상 반드시 생기는 오류라 조건을 고친 뒤 돌렸다. 파라미터로 받은 `registered_model_name`을 쓰지 않고 `recommender_production`을 하드코딩한 것도 문제다. 여러 사람이 같은 서버를 쓰면 서로의 모델 버전을 덮으므로 파라미터를 쓰도록 고쳤다.

더 근본적인 것은 비교 기준이다. `rms`, `precision_50`, `recall_50`은 앞에서 본 대로 추천 품질을 잘 대표하지 못한다. 문턱값이 아무리 정교해도 지표가 틀리면 판단도 틀린다. 마지막으로 책 리스팅 9.17과 저자 README는 `prod` 별칭을 찾지만 파이프라인은 `staging`만 만든다. `prod`로 옮기는 일은 사람이 검토할 몫으로 남겼고, 실제로 `prod`를 조회하면 `Registered model alias prod not found`가 난다.

### 모델 클래스 없이 불러온다는 말의 조건 {#pickle-python-version}

책은 MLflow 덕분에 모델 정의 없이도 모델을 불러올 수 있다고 한다. `mlflow.pytorch`가 모델 객체를 클래스 코드까지 함께 직렬화하기 때문이다. 그런데 이 직렬화에는 파이썬 바이트코드가 들어간다.

학습 컴포넌트는 KFP SDK 2.11의 기본 이미지인 `python:3.9`에서 돌았다. 이 모델을 Python 3.12에서 불러오자 `TypeError: code() argument 13 must be str, not int`로 실패했다. Python 3.9와 PyTorch 2.8.0으로 맞춘 환경에서는 문제없이 불러왔다. 모델과 함께 기록되는 `python_env.yaml`이 바로 이 조건을 적어 두는 파일이다. 서빙 이미지는 이 버전을 지켜야 한다. 오래 보관할 모델이라면 TorchScript나 ONNX처럼 파이썬 버전에 덜 묶인 형식도 함께 고려할 만하다.

## 이 장이 남기는 한계 {#remaining-limits}

9장의 구조는 데이터 준비, 학습, 검증, 등록을 한 실행으로 묶고 그 근거를 남긴다. 그래도 남은 일이 있다.

PVC는 실행 단위 작업 공간이다. 실패한 실행의 PVC와 끝난 Pod를 치우는 일은 자동화해야 하고, 데이터 버전은 객체 저장소와 실행 기록에 따로 남겨야 한다.

가장 큰 문제는 지표다. 그 숫자가 사용자 경험을 대표하는지 아무도 확인하지 않았다. 전체 후보 순위 지표, 인기순 기준선, 시간 기준 분할 없이 등록을 자동화하면 상수 예측보다 못한 모델도 `staging`에 오른다. 이번 실습에서 실제로 그렇게 됐다.

계보도 절반만 이어진다. MLflow run에 데이터셋 경로, 분할 방식, 코드 커밋이 없다. `staging`에서 `prod`로 넘기는 검토 절차와 그 기록도 아직 없다. 10장은 별칭으로 모델을 찾아 서빙하므로, 누가 어떤 별칭을 옮기는지가 곧 배포 절차가 된다.

## 실습 {#book-ch09-sop}

책 코드로 직접 실행한 순서와 결과 화면은 [9장 실습 기록](/docs/tech/machine-learning-platform-engineering/practice/ch09/)에 따로 모았다.

## 마치며 {#closing}

9장의 세 도구는 서로 다른 질문에 답한다. PVC는 이 실행 동안 데이터를 어디에 두고 누가 읽는지를, TensorBoard는 한 번의 학습 안에서 무슨 일이 있었는지를 다룬다. MLflow는 어떤 조건의 실행이 어떤 결과를 냈고 지금 무엇을 쓰는지를 남긴다.

이 연결은 생각보다 쉽게 끊긴다. 캐시는 PVC를 모르고, `DeletePVC`는 실패한 실행을 치우지 않는다. 등록 자동화는 지표가 틀려도 충실하게 등록한다. 다음 장은 `staging`과 `prod` 별칭으로 모델을 찾아 서빙한다. 이번 장에서 남긴 run_id와 별칭이 그대로 배포 경로가 되는 셈이다.

[이전: 08. 학습과 검증 I](/docs/tech/machine-learning-platform-engineering/08-training-and-validation-1/), [시리즈 목차](/docs/tech/machine-learning-platform-engineering/), [다음: 10. 추론과 서빙](/docs/tech/machine-learning-platform-engineering/10-inference-and-serving/)
