---
title: "Redis, RedisVL: 다시 써도 되는 답만 캐시하기"
description: "Bookway 정책, 권한, 출시별 정확 캐시와 의미 캐시의 경계"
date: 2026-10-25T08:43:00+09:00
weight: 100
tags: ["llmops", "redis", "redisvl", "semantic-cache"]
---

이전 고객에게 했던 안내를 다음 고객에게 그대로 말해도 되는 경우와 아닌 경우가 있습니다. Redis는 key/value 기반 재사용과 상태 저장에, RedisVL은 벡터 검색, 의미 캐시 등에 사용할 수 있습니다. 질문이 비슷하다는 이유만으로 같은 답이 허용되지는 않습니다.

## Bookway의 캐시 범위

공개 배송, 반품 정책은 후보가 될 수 있지만, 내 주문, 환불, 재고 같은 개인화, 실시간, 거래 결과는 기본적으로 완성 답변 캐시에서 제외합니다. 정책에도 국가, 회원 유형, 구매일 조건이 있으면 그 범위를 키와 검색 필터에 포함합니다.

```text
인증, 허용 범위 결정
  → cache scope 생성
  → 동일 scope 안에서만 정확/의미 검색
  → 적중 답의 source, 유효 시점, release 검사
  → 통과하면 반환
  → 미적중이면 RAG 후 저장 가능성 판단
```

## 먼저 정확 캐시의 키를 고정하기

아래는 외부 Redis 없이 실행되는 **키 설계 예제**입니다. 해시는 식별에 사용하며 암호화나 익명화의 보증이 아닙니다.

```python
import hashlib
import json

scope = {
    "tenant": "bookway",
    "access_scope": "public-policy",
    "release": "help-r8",
    "policy": "policy-v3",
    "locale": "ko-KR",
    "question": "Synthetic return-policy question",
}
encoded = json.dumps(
    scope, sort_keys=True, ensure_ascii=False, separators=(",", ":")
).encode("utf-8")
key = "bookway:answer:" + hashlib.sha256(encoded).hexdigest()
print(key)
```

실제 앱은 이 키에 검증된 답, source, 생성 시점, 유효 기한을 함께 저장하고 TTL을 적용합니다. Redis 연결 오류는 cache miss와 구분해 계측합니다. 우회 생성은 권한, 예산이 허용한 정책일 때만 사용하고 비용 폭증에 대비합니다.

## RedisVL 의미 캐시를 추가하는 절차

벡터 검색을 지원하는 Redis 배포와 RedisVL, embedding provider를 준비합니다. `SemanticCache`의 이름, vectorizer, distance threshold, TTL, filter schema를 고정하고, 저장과 조회 양쪽에 같은 권한, release 필터를 강제합니다. 이름만 테넌트별로 만들면 세부 ACL까지 해결되는 것은 아닙니다.

처음에는 정확 캐시와 미적중 RAG를 기준선으로 둡니다. “종이책을 반품할 수 있나요?”와 “전자책을 반품할 수 있나요?”처럼 표현은 비슷하고 조건은 다른 질문으로 오적중을 평가한 뒤 threshold를 정합니다. cosine **거리**의 낮은 값과 정답 확률은 다릅니다.

## 무효화와 비용

정책, 프롬프트, 모델, 검색 설정이 바뀌면 namespace를 새 release로 분리하거나 명시적으로 무효화합니다. TTL만 짧게 둔다고 정책 변경 직후의 오류가 없어지지는 않습니다. 삭제된 source를 참조한 답도 제거합니다.

관측은 hit율뿐 아니라 오적중, 허용 범위 위반, 절약한 생성 비용, embedding 조회 비용, p95를 봅니다. vLLM의 KV cache, embedding cache, 완성 답변 cache는 다른 계층이며 같은 무효화 규칙을 쓰지 않습니다.

[RedisVL 공식 저장소](https://github.com/redis/redis-vl-python) / [공식 의미 캐시 가이드](https://docs.redisvl.com/en/stable/user_guide/03_llmcache.html) / [출시 버전과 무효화](../release/)
