---
title: "Feast 기초: 피처 정의부터 과거 조회, 온라인 서빙까지"
description: "Feast의 핵심 개념을 익히고, 피처를 등록해 과거 시점 학습 데이터와 온라인 서빙 결과를 조회합니다."
date: 2026-10-25T19:30:00+09:00
weight: 20
tags: ["mlops", "feast", "feature-store", "hands-on"]
---

주방과 매장이 같은 레시피 카드를 사용한다고 생각해 봅니다. 주방은 어제 손님에게 내놓았던 메뉴를 그때의 재료 수량으로 재현하고, 매장은 지금 주문한 손님에게 필요한 재료를 바로 꺼냅니다. 같은 기준표가 두 경로를 잇습니다. Feast는 머신러닝의 피처를 정의하고, 학습에 필요한 과거 값을 찾고, 온라인 예측에 필요한 최신 값을 내주는 **피처 스토어**입니다.

평소에는 클릭 로그와 구매 이력을 따로 처리해도 모델을 학습할 때, API에서 예측할 때는 같은 의미의 피처가 필요합니다. 학습 때는 그날 알 수 있었던 값이어야 하고, 온라인 요청에는 빠르게 조회할 현재 값이어야 합니다. Feast는 두 용도를 나누어 다루고, FeatureService로 모델이 쓰는 피처 묶음을 고정합니다.

공식 Quickstart 저장소를 살펴본 뒤, 고객 구매 요약 데이터로 과거 조회, 온라인 조회와 요청 시점 계산을 실행합니다. 명령은 bash 기준이며, Windows 사용자는 WSL2의 Ubuntu에서 실행할 수 있습니다.

## 1단계. 용어를 먼저 지도처럼 펼쳐 봅니다

| 용어 | 쉬운 설명 | Feast에서 하는 일 |
| --- | --- | --- |
| Entity | 레시피에 적는 손님 번호 | 피처를 누구의 값인지 식별하는 키입니다. 예를 들어 `customer_id`입니다. |
| Data source | 재료를 가져오는 창고 | 이벤트 시각이 포함된 Parquet 파일이나 데이터 웨어하우스 테이블입니다. |
| FeatureView | 한 종류의 재료 묶음과 보관 규칙 | Entity, 원천, TTL, 스키마와 피처를 묶어 과거 조회와 온라인 저장에 사용합니다. |
| Field, schema | 재료 이름과 계량 단위 | 피처 이름과 자료형을 정의합니다. 예를 들어 `purchase_count`는 정수입니다. |
| FeatureService | 특정 메뉴를 위한 고정 레시피 | 모델 버전이 사용할 FeatureView와 피처의 집합입니다. |
| Registry | 레시피 목록을 보관하는 서랍 | `feast apply`로 등록한 Entity, FeatureView, FeatureService 같은 정의와 메타데이터를 기록합니다. |
| Offline store | 과거 장부 보관함 | 학습 또는 배치 점수 계산에 필요한 이력 데이터를 조회합니다. |
| Online store | 오늘의 안내판 | 온라인 예측에 쓸 Entity별 최신 피처를 빠르게 읽습니다. |
| Materialization | 오늘 쓸 재료를 안내판에 옮겨 놓기 | Offline source의 피처 값을 Online store에 기록합니다. |
| Feature server | 안내판을 읽게 해 주는 창구 | HTTP 또는 gRPC 요청으로 온라인 피처를 반환하는 서버입니다. |
| TTL | 과거 조회에서 허용할 유효 기간 | FeatureView 기준으로 과거 조회의 시간 범위를 제한합니다. Redis key 만료와는 다른 설정입니다. |
| Point-in-time join | 주문 시각에 맞는 과거 장부 행 찾기 | Entity의 요청 시각보다 늦지 않은 피처 중 최신 행을 고릅니다. |

피처는 `purchase_count=5`처럼 숫자 하나만을 뜻하지 않습니다. 어떤 Entity의 값인지, 그 값이 언제 알려졌는지, 어떤 모델이 어떤 이름으로 소비하는지까지 알아야 학습과 예측이 같은 뜻을 유지합니다.

## 2단계. Feast를 고정 버전으로 설치합니다

PyPI에서 확인한 최신 안정 버전은 Feast `0.67.0`입니다. Feast CLI뿐 아니라 아래에서 UI와 HTTP API에 사용하는 gRPC 의존성도 고정합니다. Python 3.12와 `uv`를 사용합니다.

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python "feast[grpcio]==0.67.0" "grpcio==1.84.1" "grpcio-health-checking==1.84.1" "grpcio-reflection==1.84.1"
source .venv/bin/activate
```

`feast[grpcio]`는 registry API가 필요한 UI 실행에 사용합니다. 실습 당시 Feast `0.67.0`, gRPC 관련 패키지 `1.84.1`이 설치됐습니다.

## 3단계. 공식 예제 저장소를 생성합니다

`feast init`은 실행 중인 디렉터리 아래에 예제 프로젝트와 파일 기반 저장소를 만듭니다.

```bash
feast init feast_demo
cd feast_demo/feature_repo
```

이 버전에서 생성된 저장소의 중요한 파일은 다음과 같습니다.

| 생성 파일 | 실제로 들어 있는 내용 |
| --- | --- |
| `feature_store.yaml` | 프로젝트 이름 `feast_demo`, 기본 파일 registry `data/registry.db`, 로컬 provider와 SQLite online store 경로입니다. |
| `feature_definitions.py` | `driver` Entity, `driver_hourly_stats` FeatureView, 예제 FeatureService, RequestSource와 on-demand feature view를 포함한 정의입니다. |
| `data/driver_stats.parquet` | 시간별 운전자 통계의 예제 원천입니다. |
| `data/driver_quality_labels.parquet` | 예제 운전자 품질 라벨의 Parquet 파일입니다. |
| `test_workflow.py` | apply, historical retrieval, materialization, online retrieval을 순서대로 실행하는 예제 코드입니다. |

공식 FeatureView에는 `conv_rate`, `acc_rate`, `avg_daily_trips`뿐 아니라 Map, JSON, Struct 필드도 있습니다. Parquet 예제에는 `event_timestamp`, `created` 같은 시각 필드가 있으며 이를 원천과 정의에서 연결합니다. CLI 옵션은 릴리스마다 달라질 수 있으므로 실제 설치된 CLI의 `feast init --help`도 함께 확인합니다.

## 4단계. `feast apply`로 정의를 Registry에 등록합니다

현재 위치에서 명령을 실행합니다.

```bash
feast apply
```

공식 예제 저장소에서 실행했을 때 `Applying changes for project feast_demo`, `Created entity driver`, `Created feature view driver_hourly_stats`, `Created feature service driver_activity_v1`와 같은 메시지를 확인했습니다. `feast apply`의 역할은 코드에 정의된 객체와 메타데이터를 Registry에 반영하는 것입니다. 이 명령만으로 Parquet의 과거 값을 Online store에 모두 적재하지는 않습니다. Registry에 피처 정의가 있는 일과 온라인 요청에 피처 값이 있는 일은 별개의 단계입니다.

## 5단계. 고객 피처 예제를 파일로 정의합니다

이제 `feast_demo`와 분리된 작은 저장소를 만듭니다. 작업 디렉터리에는 `walkthrough/`와 `scripts/`를 형제 폴더로 둡니다. Feast는 저장소 안의 Python 정의 파일을 읽으므로, 실행용 스크립트는 저장소 바깥 `scripts/`에 둡니다.

저장소 구조는 `walkthrough/feature_store.yaml`, `walkthrough/feature_repo/feature_definitions.py`, `walkthrough/data/`, `scripts/prepare_data.py`, `scripts/historical.py`, `scripts/online.py`입니다. `data/customer_features.parquet`는 아래 데이터 생성 코드가 만듭니다.

`walkthrough/feature_store.yaml`은 프로젝트, 파일 registry, 로컬 SQLite online store를 지정합니다.

```yaml
project: feast_beginner
registry: data/registry.db
provider: local
online_store:
  type: sqlite
  path: data/online_store.db
entity_key_serialization_version: 3
auth:
  type: no_auth
```

`walkthrough/feature_repo/feature_definitions.py`에는 Entity와 시간별 통계 FeatureView를 정의합니다. `checkout_features`는 요청에만 들어오는 `basket_adjustment`를 더하는 on-demand feature view입니다. float 덧셈 결과는 Feast가 `Float64`로 추론하므로 스키마에도 같은 형식을 지정합니다.

```python
from datetime import timedelta

import pandas as pd
from feast import Entity, FeatureService, FeatureView, Field, FileSource, RequestSource
from feast.on_demand_feature_view import on_demand_feature_view
from feast.types import Float32, Float64, Int64
from feast.value_type import ValueType

customer = Entity(name="customer", join_keys=["customer_id"], value_type=ValueType.STRING)
customer_source = FileSource(
    name="customer_stats_source",
    path="data/customer_features.parquet",
    timestamp_field="event_timestamp",
    created_timestamp_column="created",
)
customer_stats = FeatureView(
    name="customer_stats",
    entities=[customer],
    ttl=timedelta(days=7),
    schema=[
        Field(name="purchase_count", dtype=Int64),
        Field(name="avg_basket", dtype=Float32),
    ],
    source=customer_source,
    online=True,
)
request_source = RequestSource(
    name="checkout_request",
    schema=[Field(name="basket_adjustment", dtype=Float32)],
)


@on_demand_feature_view(
    sources=[customer_stats, request_source],
    schema=[Field(name="adjusted_avg_basket", dtype=Float64)],
)
def checkout_features(inputs: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {"adjusted_avg_basket": inputs["avg_basket"] + inputs["basket_adjustment"]}
    )


customer_checkout_v1 = FeatureService(
    name="customer_checkout_v1",
    features=[customer_stats, checkout_features],
)
```

`Entity`의 `join_keys`가 피처 파일의 `customer_id`와 대응합니다. `event_timestamp`는 피처가 관측된 시각이고, `created`는 원천 행이 생성된 시각입니다. 이 예제에서는 Entity 하나에 두 시각의 장바구니 평균이 있다고 가정합니다.

## 6단계. 이벤트 시각이 있는 데이터를 만들고 등록합니다

`scripts/prepare_data.py`를 저장하고 `walkthrough/`를 현재 디렉터리로 둔 뒤 실행합니다. 첫 행은 현재 UTC 시각보다 24시간 전, 둘째 행은 30분 전입니다. 예제 출력은 실행 시각에 따라 달라집니다.

```python
from pathlib import Path

import pandas as pd

output = Path("data/customer_features.parquet")
output.parent.mkdir(parents=True, exist_ok=True)
now = pd.Timestamp.now(tz="UTC").floor("min")
event_times = [now - pd.Timedelta("24h"), now - pd.Timedelta("30min")]
pd.DataFrame(
    {
        "customer_id": ["c-001", "c-001"],
        "event_timestamp": event_times,
        "created": [time + pd.Timedelta("1min") for time in event_times],
        "purchase_count": [3, 5],
        "avg_basket": [120.0, 200.0],
    }
).to_parquet(output, index=False)
print(pd.read_parquet(output).to_string(index=False))
```

저장소 디렉터리에서 정의를 등록합니다.

```bash
cd walkthrough
python ../scripts/prepare_data.py
feast apply
```

출력에서 `Created project feast_beginner`, `Created entity customer`, `Created feature view customer_stats`, `Created on demand feature view checkout_features`, `Created feature service customer_checkout_v1`를 확인했습니다. 이 단계에서 registry와 SQLite feature-view 테이블은 생겼지만 값 공급은 아직 `materialize` 단계입니다.

## 7단계. 과거 시점의 값을 조회합니다

과거 장부에서 10시 30분 주문을 처리한다고 생각해 봅니다. 9시에 기록한 구매 수 3건, 평균 장바구니 120은 그 시각에 알 수 있습니다. 12시에 기록된 구매 수 5건, 평균 200은 요청보다 뒤의 값이므로 결과에 들어오면 안 됩니다. `event_timestamp`가 있는 Entity DataFrame이 요청 시각을 전달합니다.

`scripts/historical.py`는 FeatureService를 통해 과거 값과 요청 시점 계산 결과를 함께 가져옵니다. 실행 시각을 기준으로 12시간 전을 요청 시각으로 잡았으므로 첫 번째 원천 행만 선택됩니다.

```python
import pandas as pd
from feast import FeatureStore

store = FeatureStore(repo_path=".")
service = store.get_feature_service("customer_checkout_v1")
request_time = pd.Timestamp.now(tz="UTC").floor("min") - pd.Timedelta("12h")
requests = pd.DataFrame(
    {
        "customer_id": ["c-001"],
        "event_timestamp": [request_time],
        "basket_adjustment": [5.0],
    }
)
result = store.get_historical_features(
    entity_df=requests,
    features=service,
).to_df()
print(result.to_string(index=False))
```

현재 실행에서는 `purchase_count=3`, `avg_basket=120.0`, `adjusted_avg_basket=125.0`을 반환했습니다. 요청 시각 뒤의 행은 선택되지 않았습니다.



이것이 point-in-time join입니다. Entity와 요청 시각을 기준으로, 그 시점에 이용 가능했던 최신 행을 고릅니다. 데이터의 각 행에 올바른 이벤트 시각이 입력돼야 하며, 시각 컬럼이 잘못됐거나 집계 값 자체에 미래 데이터가 섞였다면 Feast가 이를 자동으로 바로잡지는 않습니다.

## 8단계. Materialization으로 최신 값을 온라인에 공급합니다

학습 조회는 이력을 사용하는 반면, 온라인 예측은 빠른 최신값을 요구합니다. 전체 과거 범위를 적재할 때는 `feast materialize`를 사용합니다. 이 예제는 CLI가 허용하는 전체 원천 범위 옵션을 사용합니다.

```bash
feast materialize --disable-event-timestamp
```

실행 결과에서 `Materializing 1 feature views from 1970-01-01 ... into the sqlite online store`와 `customer_stats` materialization을 확인했습니다. 이후의 데이터만 주기적으로 공급할 때는 시작점 이후부터 지정한 끝 시각까지 가져오는 incremental 명령을 사용합니다.

```bash
end_ts=$(python -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())')
feast materialize-incremental "$end_ts"
```

실행 결과는 `Materializing 1 feature views to ... into the sqlite online store`와 조회 범위였습니다. `materialize-incremental`은 끝 시각을 인자로 받습니다. 이를 주기 실행에 넣을 때는 스케줄러가 실행 시각과 성공 여부, 처리 범위를 기록하게 합니다.

## 9단계. FeatureService로 과거와 온라인 계약을 고정합니다

`scripts/historical.py`는 이미 `customer_checkout_v1`을 과거 조회에 사용했습니다. 같은 이름의 FeatureService를 온라인 조회에도 사용하면 학습과 서빙이 읽는 피처 목록이 일치합니다. `scripts/online.py`는 알려진 Entity와 없는 Entity를 함께 요청합니다.

```python
from feast import FeatureStore

store = FeatureStore(repo_path=".")
service = store.get_feature_service("customer_checkout_v1")
result = store.get_online_features(
    features=service,
    entity_rows=[
        {"customer_id": "c-001", "basket_adjustment": 5.0},
        {"customer_id": "c-999", "basket_adjustment": 5.0},
    ],
)
print(result.to_dict())
```

조회 결과는 실제로 `purchase_count: [5, None]`, `avg_basket: [200.0, None]`, `adjusted_avg_basket: [205.0, None]`였습니다. 과거 조회는 3건과 120.0을 선택했지만 온라인 조회는 materialize한 최신값 5건과 200.0을 반환합니다. 두 결과의 차이는 오류가 아니라 조회 기준이 다르기 때문입니다.

FeatureService는 특정 모델 버전의 피처 계약입니다. 모델 코드 곳곳에 문자열 피처 목록을 흩어 놓으면 학습 목록만 바뀌고 예측 목록은 그대로 남는 실수가 생기기 쉽습니다. 서비스 이름으로 정의를 선택하면 어떤 FeatureView와 피처 집합을 모델이 요구하는지 Registry에서 추적할 수 있습니다.

## 10단계. 모르는 Entity의 온라인 응답을 구분합니다

피처가 없는 고객을 `0`으로 채우면 “조회하지 못함”을 “구매 수가 실제로 0”이라고 바꾸어 해석할 수 있습니다. 이는 모델 입력 분포와 의사결정을 바꾸는 문제입니다. Feast SDK의 `.to_dict()` 예제에서 누락된 Entity 피처 값은 `None`으로 나왔습니다.

같은 저장소에서 feature server를 시작합니다. 첫 번째 터미널은 저장소 디렉터리에서 실행하고, 다른 터미널에서 아래 요청을 보냅니다.

```bash
feast serve --host 127.0.0.1 --port 6567
```

```bash
curl -sS -X POST http://127.0.0.1:6567/get-online-features \
  -H 'Content-Type: application/json' \
  -d '{"feature_service":"customer_checkout_v1","entities":{"customer_id":["c-001","c-999"],"basket_adjustment":[5.0,5.0]}}'
```

요청에서 반환된 핵심 상태는 구매 수와 평균 장바구니 피처에 대해 `PRESENT`와 `NOT_FOUND`였습니다. 응답의 해당 벡터 값은 각각 `[5, null]`, `[200.0, null]`입니다. `NOT_FOUND`와 `null`을 별도의 상태로 다루면 진짜 0과 미등록 Entity, 원천 누락을 구분하는 정책을 만들 수 있습니다. Feature server는 `no_auth` 구성에서는 인증 없이 동작하므로 로컬 실습과 인증을 갖춘 서비스 환경을 구분합니다.

## 11단계. 요청 시점 변환과 Feast UI를 살펴봅니다

`checkout_features`는 저장된 `avg_basket`에 요청에서만 알 수 있는 `basket_adjustment`를 더합니다. 이것이 on-demand feature view입니다. 방금 실행한 역사 조회에서는 120.0에 5.0을 더해 125.0을 반환했고, 온라인 조회에서는 200.0에 5.0을 더해 205.0을 반환했습니다. 같은 정의가 두 경로에서 쓰이므로 변환 규칙을 나란히 유지할 필요가 줄어듭니다.

Feast `0.67.0`에서 생성된 공식 예제에도 `@on_demand_feature_view`, `RequestSource`, FeatureService가 포함돼 있습니다. 로컬 데이터프레임 기반 on-demand feature view는 이 실습에서 등록과 과거, 온라인 조회까지 동작했습니다. 다만 Feast CLI는 이 기능을 experimental이라고 경고하며, Offline store의 대규모 retrieval에 적합하지 않을 수 있다고 안내합니다. 처리량과 실행 위치를 고려해 검증해야 합니다.

UI는 별도 터미널에서 저장소 디렉터리에서 실행합니다.

```bash
feast ui --host 127.0.0.1 --port 8889
```

실행 로그에 `Uvicorn running on http://127.0.0.1:8889`가 나타났고, 다른 터미널에서 `curl -sS -o /dev/null -w 'feast_ui_http=%{http_code}\n' http://127.0.0.1:8889/`를 실행해 `feast_ui_http=200` 응답을 확인했습니다. 실습이 끝나면 UI와 Feature server 터미널에서 `Ctrl+C`로 종료합니다.

## 12단계. 로컬 실습을 운영 구성에 대응시킵니다

**구성 설명:** 아래는 클러스터용 운영 구성을 생각할 때의 연결입니다. 로컬 실습의 `feature_store.yaml`에 추가해 그대로 실행하는 단계가 아닙니다.

Registry를 노트북이나 임시 Pod의 로컬 파일 대신 공유 객체 저장소로 두려면 `registry: s3://feature-registry/registry.db`처럼 설정할 수 있습니다. Feast의 S3 호환 객체 저장소 연결에는 실행 환경의 AWS 자격 증명과 MinIO endpoint 환경 변수 `FEAST_S3_ENDPOINT_URL`이 필요합니다. MinIO 예시 endpoint는 `http://minio-service.kubeflow.svc.cluster.local:9000`입니다. Registry 파일은 정의 카탈로그이고 피처 이력 데이터의 Offline store와 동일한 저장소는 아닙니다.

Feast의 로컬 예제처럼 Parquet 파일을 Offline source로 쓸 수 있습니다. 파일 소스가 커지면 Dask, Spark, 또는 데이터 웨어하우스 계열 Offline store가 처리에 더 알맞을 수 있습니다. S3 경로를 파일 원천으로 읽을 때는 선택한 엔진과 파일 포맷, S3 호환 인증 설정을 함께 확인합니다.

온라인 저장소는 Redis로 분리할 수 있습니다. Redis 연결 예시는 `online_store.type: redis`, `online_store.connection_string: "redis:6379"`입니다. 쿠버네티스에서는 서비스 DNS와 인증 정보를 환경별로 관리합니다. Feast의 `FeatureView.ttl`은 과거 조회 창의 폭을 나타내며, Redis에서 Entity key를 실제 만료시키려면 별도 `key_ttl_seconds` 설정을 검토합니다.

이 글에서 다루는 책 *Machine Learning Platform Engineering*의 클러스터 예시는 MinIO Registry를 `s3://feature-registry/registry.db`로 사용하고, Redis를 온라인 저장소로 둡니다. Kubernetes Job이 `feast apply`를 실행하며 Pod 환경 변수 `FEAST_S3_ENDPOINT_URL=http://minio-service.kubeflow.svc.cluster.local:9000`으로 클러스터 내부 MinIO 주소를 전달합니다. 노트북의 `localhost` registry 경로와 Pod의 공유 Registry 경로가 달라지면 서로 다른 정의를 보게 되므로, 모든 실행 환경에서 같은 공유 Registry와 네트워크 주소를 사용하도록 배포 구성을 관리합니다.

## 13단계. MLflow와 Kubeflow Pipelines를 연결합니다

Feast는 모델을 알지 못하고, MLflow는 피처의 의미나 Feast Registry를 알지 못합니다. 연결 지점은 학습 코드입니다. 학습 코드는 FeatureService로 이력 데이터를 조회해 학습하고, MLflow run과 모델 버전의 태그에 FeatureService 이름과 피처 정의 버전, `feature_definitions.py` 또는 registry snapshot 위치를 기록합니다. `feature_store.yaml`은 저장소 연결 설정이지 피처 정의 자체의 재현 기록은 아닙니다.

Kubeflow Pipelines 컴포넌트도 같은 Feast 조회 코드를 호출해 학습 데이터나 배치 예측 피처를 준비할 수 있습니다. `feast apply`를 실행하는 배포 Job, 정기 materialization 작업, 데이터 조회 및 모델 학습 작업을 분리하면 각각의 변경과 실패를 추적하기 쉽습니다.

## 14단계. 자주 놓치는 운영 조건을 점검합니다

| 놓치는 부분 | 문제가 되는 이유 | 점검 기준 |
| --- | --- | --- |
| 시간대가 없는 timestamp | UTC 또는 로컬 시각 해석이 달라져 잘못된 과거 행이 선택될 수 있습니다. | 원천과 요청 Entity DataFrame을 timezone-aware UTC로 정규화합니다. |
| TTL과 온라인 만료를 같은 설정으로 취급 | FeatureView TTL은 historical retrieval 기간이고, 그 자체가 온라인 키를 지우지는 않습니다. | Redis 만료가 필요하면 online store의 key TTL 설정을 별도로 봅니다. |
| materialization 생략 | Registry에 정의만 있고 온라인 저장소에는 조회할 값이 없을 수 있습니다. | 온라인 요청 전 materialization의 범위, 완료 시각, 행 수를 확인합니다. |
| 노트북과 클러스터의 Registry 경로 불일치 | 로컬 경로와 Pod 내부 경로는 서로 다른 Registry를 가리킬 수 있습니다. | S3 Registry 주소, endpoint, 접근 권한이 모든 실행 환경에서 같은지 확인합니다. |
| 원천 스키마 변경 | 필드 형식이나 이름이 바뀌면 조회나 학습 입력이 깨질 수 있습니다. | Field 타입, 원천 스키마, FeatureService 버전을 함께 검증합니다. |
| Online store로 학습 데이터 만들기 | 최신값만 읽으면 과거 시점 정보와 미래 누수 방지 조건을 잃습니다. | 학습은 Offline store와 timestamp Entity DataFrame으로 historical retrieval을 사용합니다. |
| 누락값을 바로 0으로 치환 | 실제 0건과 피처 누락, 서비스 오류가 같은 숫자로 보입니다. | 상태를 분리해 기록하고 모델별 cold-start 정책을 적용합니다. |

## 참고 링크

아래 링크는 공식 Feast 문서이며, 페이지의 최종 URL과 응답을 확인했습니다. FeatureService 설명은 별도 최신 개념 페이지 대신 Feature retrieval 문서의 Feature services 절에 있습니다.

- [Quickstart](https://docs.feast.dev/getting-started/quickstart)
- [Feature view](https://docs.feast.dev/getting-started/concepts/feature-view)
- [Feature retrieval, FeatureService와 historical retrieval 포함](https://docs.feast.dev/getting-started/concepts/feature-retrieval)
- [Data ingestion, batch materialization](https://docs.feast.dev/getting-started/concepts/data-ingestion)
- [Python feature server](https://docs.feast.dev/reference/feature-servers/python-feature-server)
- [On-demand feature view](https://docs.feast.dev/reference/beta-on-demand-feature-view)
- [Registry](https://docs.feast.dev/getting-started/components/registry)
- [Redis online store](https://docs.feast.dev/reference/online-stores/redis)
- [File data source](https://docs.feast.dev/reference/data-sources/file)
- [Dask offline store](https://docs.feast.dev/reference/offline-stores/dask)
- [Spark offline store](https://docs.feast.dev/reference/offline-stores/spark)

## 관련 글

- [Bookway Feast 설계 가이드](/docs/tech/ops/mlops/feast/)
- [ML 플랫폼 실습 03, Feast](/docs/tech/ops/mlops/labs/ml-platform-labs-03-feast/)
- [Machine Learning Platform Engineering 4~5장, 실험과 피처 파이프라인](/docs/tech/machine-learning-platform-engineering/04-experiments-features-pipelines/)
- [MLflow 기초](/docs/tech/ops/mlops/basics/mlflow/)
- [Kubeflow Pipelines 기초](/docs/tech/ops/mlops/basics/kubeflow-pipelines/)
- [BentoML 기초](/docs/tech/ops/mlops/basics/bentoml/)