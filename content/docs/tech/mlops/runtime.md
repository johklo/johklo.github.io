---
title: "Docker·Kubernetes·Helm: 모델이 실행되는 기반"
description: "Bookway API의 이미지·자원·상태 검사·네트워크와 배포 패키지를 분리"
date: 2026-10-25T08:43:00+09:00
weight: 60
tags: ["mlops", "docker", "kubernetes", "helm"]
---

같은 조리법도 가스와 냉장고가 없으면 실행되지 않습니다. Docker는 실행 환경을 이미지로 포장하고, Kubernetes는 컨테이너의 실행·교체·네트워크를 관리하며, Helm은 관련 선언을 템플릿과 설정으로 묶습니다. 세 도구 모두 추천 품질이나 승인 기준을 판단하지 않습니다.

## Bookway의 배포 단위

`rec-r17`은 모델 17·피처 v1·전처리·이미지 digest를 가리킵니다. 이미지에 모델을 포함하면 크기는 늘지만 초기화 시 외부 다운로드를 줄일 수 있습니다. 별도로 다운로드하면 무결성·접근 권한·보존·준비 상태 검사가 필요합니다.

| 객체 | 책임 | 놓치기 쉬운 조건 |
| --- | --- | --- |
| Deployment | API 복제와 교체 | 새 Pod의 모델 로딩 시간 |
| Service | Pod 집합에 대한 안정된 주소 | selector와 실제 label |
| Secret | 자격 증명 전달 | 암호화·RBAC·교체는 별도 구성 |
| ConfigMap | 비밀이 아닌 설정 | 설정 변경과 release 연결 |
| requests/limits | 자원 예약·제한 | CPU 제한, 메모리 종료, GPU 개수 |

## 상태 검사의 의미

아래 YAML은 이미 존재하는 컨테이너 spec의 probe 부분입니다. 앱이 `/startup`, `/ready`, `/live`를 실제 구현했다는 전제입니다.

```yaml
startupProbe:
  httpGet: {path: /startup, port: 3000}
  periodSeconds: 5
  failureThreshold: 60
readinessProbe:
  httpGet: {path: /ready, port: 3000}
  periodSeconds: 5
livenessProbe:
  httpGet: {path: /live, port: 3000}
  periodSeconds: 10
```

startup은 모델 초기화, readiness는 트래픽을 받을 준비, liveness는 프로세스 복구 필요성을 뜻하도록 나눕니다. Feast 장애를 매번 liveness 실패로 연결하면 모든 Pod가 재시작하며 상황을 악화시킬 수 있습니다. 외부 의존성 장애는 요청 오류·readiness·대체 경로 정책 중 어디에 반영할지 설계해야 합니다.

## Helm과 환경 차이

차트에서 공통 Deployment·Service를 정의하고 환경별 values로 replica·자원·endpoint를 분리합니다. Secret 값은 values를 Git에 쓰지 않고 승인된 secret 주입 경로로 전달합니다. 렌더링된 YAML 검토, schema 검사, 시험 namespace 적용을 순서대로 진행합니다.

운영 이미지는 digest로 고정하고 비특권 사용자·최소 권한·이미지 취약점 검사를 적용합니다. 네트워크 정책은 추천 API가 Feast·관측 endpoint 등에 필요한 통신만 하게 제한합니다. 인증이 없는 내부 서비스가 외부 LoadBalancer로 노출되지 않도록 합니다.

## 배포 장애의 분류

`Pending`은 자원·스케줄링, `ImagePullBackOff`는 이미지·인증, `CrashLoopBackOff`는 앱 시작·설정·의존성부터 봅니다. Service가 응답하지 않으면 selector·port·readiness·네트워크를 분리합니다. 예측 값이 틀린 문제를 replica 증가로 해결할 수는 없습니다.

LLMOps에서는 여기에 GPU 메모리·모델 가중치·동시 sequence 제한이 추가됩니다. 앱 Pod와 추론 Pod를 분리하면 검색 API 확장과 GPU 확장을 독립적으로 조절할 수 있습니다.

[Kubernetes probe 문서](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) / [Helm 차트](https://helm.sh/docs/topics/charts/) / [기존 Kubernetes 실행 기록](../../machine-learning-platform-engineering/03-kubernetes-foundation/)
