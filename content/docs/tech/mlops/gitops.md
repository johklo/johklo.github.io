---
title: "GitLab CI, Argo CD: 검사한 출시만 배포하기"
description: "이미지 빌드와 선언 동기화를 나누고 모델, 피처, 프롬프트 변경을 승인 경로에 연결"
date: 2026-10-25T08:43:00+09:00
weight: 70
tags: ["mlops", "ci-cd", "gitops", "argo-cd"]
---

검사 부서가 제품을 확인하고 출고 부서가 승인된 상자를 보내듯, CI와 CD도 구분합니다. GitLab CI는 코드 검사, 평가, 이미지 빌드를 실행하고 Argo CD는 Git의 배포 선언과 클러스터 상태를 맞춥니다. GitHub Actions 등으로 CI를 대체해도 이 책임은 같습니다.

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

학습이 끝났다고 곧바로 운영 manifest를 바꾸지 않습니다. 평가 보고서가 후보 지문과 맞는지, 모델을 다시 읽을 수 있는지, online 피처가 준비됐는지 확인합니다. CI artifact 보존 기간보다 운영 모델 수명이 길 수 있으므로 영속 저장소도 별도로 둡니다.

## GitLab CI의 연결 지점

아래 조각은 Bookway에 이 파일들이 구현됐다는 전제의 **CI 단계 예시**입니다. 평가 스크립트는 거절, 실행 장애 모두 0이 아닌 종료 코드로 반환해야 합니다.

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

스크립트가 실패했는데 `|| true`로 넘기거나 보고서 파일 존재만 검사하면 게이트가 아닙니다. 환경 의존성과 runner 이미지는 프로젝트 lockfile, digest에 고정하고, 운영 자격 증명은 untrusted PR에 제공하지 않습니다.

## Argo CD의 자동화 범위

auto-sync는 Git 변경 반영, self-heal은 수동 drift 복구, prune은 Git에서 사라진 자원 삭제입니다. 별도 위험을 가지므로 한꺼번에 켜지 않습니다. 특히 모델 artifact, DB, PVC를 차트 삭제와 함께 없애지 않도록 소유권과 보존을 검토합니다.

Argo CD가 `Synced`라고 평가나 트래픽 품질이 통과한 것은 아닙니다. 앱 건강 상태, release 확인, 오류율, 지연을 이어서 봅니다. 카나리 트래픽 조절은 ingress, 서비스 mesh, rollout controller 같은 별도 기능이 필요할 수 있습니다.

## 복구는 선언의 복구까지

운영에서만 이미지를 수동 변경하면 self-heal이 원래 Git 상태로 되돌릴 수 있습니다. 사고 대응 정책에 따라 동기화를 잠시 통제하고, 승인된 이전 release로 **Git 선언 자체**를 복원합니다. 모델과 Feast 계약, schema가 맞아야 합니다.

LLMOps의 프롬프트 라벨을 외부 레지스트리에서 바꾸는 경우도 같은 문제입니다. Git 이미지가 그대로여도 실제 동작이 바뀌므로 [출시 manifest](../../llmops/release/)에 해석된 프롬프트 버전을 포함합니다.

[Argo CD 동기화 정책](https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/) / [GitLab CI YAML](https://docs.gitlab.com/ci/yaml/) / [MLOps 전체 지도](../)
