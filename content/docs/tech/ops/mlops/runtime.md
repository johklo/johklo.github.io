---
title: "Docker, Kubernetes, Helm: 모델이 실행되는 기반"
description: "Bookway API의 이미지, 자원, 상태 검사, 네트워크와 배포 패키지를 분리"
date: 2026-10-25T08:43:00+09:00
weight: 60
tags: ["mlops", "docker", "kubernetes", "helm"]
aliases:
  - "/docs/tech/mlops/runtime/"
---

Docker는 실행 환경을 이미지화하고 Kubernetes는 컨테이너, 네트워크를 관리하며 Helm은 선언을 템플릿화한다. 추천 품질, 승인은 이 도구들의 책임이 아니다.

## Bookway의 배포 단위

`rec-r17`은 모델 17, 피처 v1, 전처리, image digest를 식별한다. 이미지를 키우면 모델 다운로드를 줄이고, 외부 다운로드는 무결성, 권한, 보존, 준비 상태를 검사한다.

| 객체 | 책임 | 놓치기 쉬운 조건 |
| --- | --- | --- |
| Deployment | API 복제와 교체 | 새 Pod의 모델 로딩 시간 |
| Service | Pod 집합에 대한 안정된 주소 | selector와 실제 label |
| Secret | 자격 증명 전달 | 암호화, RBAC, 교체는 별도 구성 |
| ConfigMap | 비밀이 아닌 설정 | 설정 변경과 release 연결 |
| requests/limits | 자원 예약, 제한 | CPU 제한, 메모리 종료, GPU 개수 |

## 상태 검사의 의미

아래 YAML은 이미 존재하는 컨테이너 spec의 probe 부분이다. 앱이 `/startup`, `/ready`, `/live`를 실제 구현했다는 전제이다.

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

startup은 모델 초기화, readiness는 트래픽 준비, liveness는 프로세스 복구를 검사한다. Feast 장애를 liveness에 연결하면 Pod가 모두 재시작할 수 있으므로 외부 장애 반영 위치를 정한다.

## Helm과 환경 차이

차트는 Deployment, Service를 공유하고 환경별 values로 replica, 자원, endpoint를 나눈다. Secret을 Git에 두지 말고 승인 경로로 주입해 렌더링, schema, 시험 namespace를 검증한다.

운영 이미지는 digest로 고정하고 비특권, 최소 권한, 취약점 검사를 적용한다. 네트워크는 필요한 Feast, 관측 통신만 허용하고 내부 인증 없는 서비스를 외부에 노출하지 않는다.

## 배포 장애의 분류

`Pending`은 자원, 스케줄링, `ImagePullBackOff`는 이미지, 인증, `CrashLoopBackOff`는 시작, 설정, 의존성을 본다. Service 장애는 selector, port, readiness, 네트워크로 나누며 오답은 replica로 해결되지 않는다.

LLMOps에서는 여기에 GPU 메모리, 모델 가중치, 동시 sequence 제한이 추가된다. 앱 Pod와 추론 Pod를 분리하면 검색 API 확장과 GPU 확장을 독립적으로 조절할 수 있다.

[Kubernetes probe 문서](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/) / [Helm 차트](https://helm.sh/docs/topics/charts/) / [기존 Kubernetes 실행 기록](/docs/tech/machine-learning-platform-engineering/03-kubernetes-foundation/)
