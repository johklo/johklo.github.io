---
title: "GitLab CI, Argo CD: 검사한 출시만 배포하기"
description: "이미지 빌드와 선언 동기화를 나누고 모델, 피처, 프롬프트 변경을 승인 경로에 연결"
date: 2026-10-25T08:43:00+09:00
weight: 70
tags: ["mlops", "ci-cd", "gitops", "argo-cd"]
aliases:
  - "/docs/tech/mlops/gitops/"
---

GitLab CI는 코드 검사, 평가, 이미지 빌드, Argo CD는 Git 선언과 클러스터 상태 동기화를 맡는다. CI 제품이 달라도 책임은 같다.

## `rec-r17`이 지나가는 경로

```text
모델, 서비스 변경
  → schema / 단위 / 모델 로딩 검사
  → 고정 평가집과 지연 예산 검사
  → 이미지 빌드, 검사, digest 확정
  → 배포 저장소 PR: release + digest + 피처 계약
  → 승인, 병합
  → Argo CD sync
  → 소량 트래픽 확인, 확대
```

평가 지문, 모델 재로딩, online 피처를 확인한 뒤 manifest를 바꾼다. CI artifact보다 모델 수명이 길 수 있어 영속 저장소도 둔다.

## GitLab CI의 연결 지점

다음은 파일이 구현됐다고 가정한 **CI 예시**다. 평가 거절과 실행 장애는 모두 0이 아닌 종료 코드로 반환한다.

```yaml
stages: [validate, evaluate]

validate:
  stage: validate
  script:
    - python -m unittest discover -s tests

evaluate:
  stage: evaluate
  script:
    - python tools/evaluate_release.py --manifest release.json
  artifacts:
    when: always
    paths:
      - reports/
```

`|| true`로 실패를 무시하거나 보고서 존재만 검사하면 게이트가 아니다. 의존성, runner 이미지는 lockfile, digest로 고정하고 untrusted PR에 운영 자격 증명을 주지 않는다.

## Argo CD의 자동화 범위

auto-sync는 Git 변경 반영, self-heal은 수동 drift 복구, prune은 Git에서 사라진 자원 삭제이다. 별도 위험을 가지므로 한꺼번에 켜지 않는다. 특히 모델 artifact, DB, PVC를 차트 삭제와 함께 없애지 않도록 소유권과 보존을 검토한다.

Argo CD가 `Synced`라고 평가나 트래픽 품질이 통과한 것은 아니다. 앱 건강 상태, release 확인, 오류율, 지연을 이어서 본다. 카나리 트래픽 조절은 ingress, 서비스 mesh, rollout controller 같은 별도 기능이 필요할 수 있다.

## 복구는 선언의 복구까지

운영의 수동 이미지 변경은 self-heal이 되돌릴 수 있다. 정책에 따라 동기화를 통제하고 승인된 이전 release의 **Git 선언**을 복원하되 모델, Feast, schema 호환성을 확인한다.

LLMOps의 프롬프트 라벨을 외부 레지스트리에서 바꾸는 경우도 같은 문제이다. Git 이미지가 그대로여도 실제 동작이 바뀌므로 [출시 manifest](/docs/tech/ops/llmops/release/)에 해석된 프롬프트 버전을 포함한다.

[Argo CD 동기화 정책](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/) / [GitLab CI YAML](https://docs.gitlab.com/ci/yaml/) / [MLOps 전체 지도](/docs/tech/ops/mlops/)
