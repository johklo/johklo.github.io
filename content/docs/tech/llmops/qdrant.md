---
title: "Qdrant: 필터가 있는 정책 벡터 서비스"
description: "Bookway 청크·payload·권한 범위·컬렉션 교체와 검색 운영"
date: 2026-10-25T08:43:00+09:00
weight: 20
tags: ["llmops", "qdrant", "vector-search"]
---

FAISS가 서가 안의 색인이라면 Qdrant는 여러 앱이 사용하는 검색 창구에 가깝습니다. 벡터와 payload를 저장하고 검색·필터·업데이트를 서비스로 제공합니다. Bookway에서는 정책 청크를 찾는 후보 검색 계층이며 답변 생성과 정책의 진위 판정은 하지 않습니다.

## 컬렉션과 point 계약

한 point에는 안정된 청크 ID, 벡터, `document_id`, `policy_version`, `tenant_id`, `valid_from`, `parent_id`를 둡니다. embedding revision·차원·거리 척도를 컬렉션 계약으로 정합니다. 같은 차원이어도 다른 모델의 벡터를 섞을 수는 없습니다.

아래는 Qdrant 서버 없이 `qdrant-client`의 메모리 모드에서 필터를 확인하는 합성 예제입니다.

```python
from qdrant_client import QdrantClient, models

client = QdrantClient(":memory:")
client.create_collection(
    collection_name="bookway_policy_v3",
    vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
)
client.upsert(
    collection_name="bookway_policy_v3",
    points=[models.PointStruct(
        id=1, vector=[1.0, 0.0],
        payload={"tenant_id": "bookway", "policy_version": "policy-v3"},
    )],
)
result = client.query_points(
    collection_name="bookway_policy_v3",
    query=[0.9, 0.1],
    query_filter=models.Filter(must=[
        models.FieldCondition(
            key="tenant_id", match=models.MatchValue(value="bookway")
        )
    ]),
    limit=3,
)
print([point.id for point in result.points])
```

메모리 모드는 분산 운영·서버 인증·영속성을 검증하지 않습니다. 운영에서는 HTTP/gRPC endpoint와 TLS·API 인증을 구성하고 payload index를 실제 필터 패턴에 맞춥니다.

## 인증과 필터는 다른 계층

`tenant_id`는 인증 서버에서 결정해 매 검색에 강제합니다. 질문이나 LLM이 만든 filter에만 맡기면 안 됩니다. 테넌트 내부에서도 문서별 ACL이 있다면 허용 집합이나 그룹 조건을 추가하고, empty scope가 전체 검색으로 바뀌지 않게 합니다.

일치 결과가 없는 경우와 Qdrant timeout은 다릅니다. 전자는 근거 부족, 후자는 검색 장애입니다. 둘을 빈 배열로 통합하면 장애 중에 모델이 근거 없는 답을 만들 수 있습니다.

## 업데이트와 확장

새 `policy-v4`는 별도 컬렉션에서 전량 색인·평가한 뒤 앱 release가 참조하도록 바꿉니다. alias를 쓰더라도 release에는 해석된 컬렉션·snapshot·embedding 계약을 기록합니다. 같은 ID의 upsert가 삭제된 청크까지 제거하지는 않으므로 삭제 목록도 관리합니다.

관측은 검색 p95·빈 결과율·filter별 후보 수·인덱스 크기·업로드 실패를 봅니다. snapshot 복원은 벡터뿐 아니라 외부 원문 저장소 버전도 맞아야 합니다. 높은 similarity score만으로 “반품 가능”을 결정하지 않고 원문 조건과 인용을 최종 검사합니다.

[공식 필터 문서](https://qdrant.tech/documentation/concepts/filtering/) / [FAISS와 색인 계약](../ingestion-faiss/) / [pgvector 대안](../pgvector/)
