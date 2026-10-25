---
title: "pgvector: 정책 행과 벡터를 함께 관리하기"
description: "PostgreSQL 필터·권한·인덱스를 Bookway 검색의 정확성과 연결"
date: 2026-10-25T08:43:00+09:00
weight: 30
tags: ["llmops", "pgvector", "postgresql"]
---

pgvector는 PostgreSQL 안에 벡터 검색을 추가합니다. Bookway의 정책 메타데이터·권한·적용 시점이 이미 관계형 DB에 있다면, 별도 벡터 서비스와 동기화하는 부담을 줄일 수 있습니다. DB를 공유하는 대신 검색 부하가 주문 트랜잭션에 미치는 영향은 분리해야 합니다.

## 스키마와 정확 검색

아래 SQL은 pgvector 확장이 설치된 **개발 DB**의 작은 예제입니다. 실제 문서 임베딩은 더 큰 차원이며 여기서는 3차원 합성 벡터를 사용합니다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE bookway_policy_chunks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id text NOT NULL,
    policy_version text NOT NULL,
    source_id text NOT NULL,
    body text NOT NULL,
    embedding vector(3) NOT NULL
);
INSERT INTO bookway_policy_chunks
    (tenant_id, policy_version, source_id, body, embedding)
VALUES
    ('bookway', 'policy-v3', 'returns-v3#1',
     'Synthetic return-policy excerpt', '[1,0,0]');

SELECT source_id, body, embedding <=> '[0.9,0.1,0]' AS distance
FROM bookway_policy_chunks
WHERE tenant_id = 'bookway' AND policy_version = 'policy-v3'
ORDER BY embedding <=> '[0.9,0.1,0]'
LIMIT 5;
```

`<=>`는 코사인 거리입니다. 실제 앱에서는 query vector·tenant·version을 DB 드라이버의 바인딩 값으로 전달합니다. SQL 문자열에 사용자 입력을 이어 붙이지 않습니다. tenant는 인증 결과에서 결정합니다.

## 근사 검색으로 바꿀 때

기본 정확 검색은 기준선이 됩니다. 데이터가 커져 HNSW·IVFFlat을 추가하면 응답 시간뿐 아니라 필터 후 recall을 다시 평가합니다. ANN에서 필터링과 후보 탐색이 결합되는 방식에 따라 허용된 결과가 부족해질 수 있습니다.

거리 연산과 인덱스 operator class를 맞추고 `EXPLAIN (ANALYZE, BUFFERS)`로 실제 실행 계획을 봅니다. pgvector 버전의 iterative scan 지원도 확인합니다. 단순히 인덱스 생성 성공을 검색 품질의 근거로 삼지 않습니다.

## 권한과 운영 분리

Row Level Security를 적용할 수 있지만 정책·DB role·connection pool의 tenant context를 정확히 구성해야 합니다. 테이블 소유자나 우회 권한으로 접속하면 기대한 격리가 적용되지 않을 수 있습니다. 앱 필터와 DB 권한을 함께 테스트합니다.

정책 갱신은 원문·벡터·버전을 transaction으로 정합성 있게 반영할 수 있습니다. 다만 외부 embedding API 호출은 DB transaction과 하나의 원자적 작업이 아니므로 staging → embedding 완료 → 게시 순서가 필요합니다.

검색용 replica나 전용 DB를 두고 backup·PITR·vacuum·연결 수·메모리를 운영합니다. replica lag가 새 정책 게시에 미치는 영향도 확인합니다. 삭제 시 원문 행뿐 아니라 [Redis 캐시](../redis/)와 trace 보존 정책도 연결합니다.

[pgvector 공식 문서](https://github.com/pgvector/pgvector) / [Qdrant와의 선택 기준](../qdrant/) / [출시 계약](../release/)
