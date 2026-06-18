# W10 - Progressive Delivery + Security Labs

GitOps setup for API deployment với Argo Rollouts + ESO + Trivy + Cosign.

## Labs Overview

| Lab | Chủ đề | Mô tả |
|---|---|---|
| Lab 1 | Progressive Delivery | Canary rollout + AnalysisTemplate + Gatekeeper |
| Lab 2.1 | ESO | Rotate secret không restart pod |
| Lab 2.2 | Trivy + Cosign | Scan CVE + ký image + admission verify |

## Requirements

- Docker Desktop
- kubectl
- minikube (8GB RAM)
- git

## Structure

```
w10/
├── app-api/              # API Rollout manifests
│   └── rollout.yaml      # Argo Rollout + volume mount secret
├── app-analysis/         # Analysis manifests
│   └── analysis-template.yaml
├── app-alert/            # Alert manifests
│   └── prometheus-rules.yaml
├── app-common/           # Common resources
│   └── demo-namespace.yaml  # label: policy.sigstore.dev/include=true
├── src/api/              # Flask API source
│   ├── app.py            # Endpoint / + /healthz + /password
│   └── Dockerfile
├── eso/                  # Lab 2.1 - External Secrets
│   ├── secret-store.yaml     # SecretStore (fake provider)
│   └── external-secret.yaml  # ExternalSecret → K8s Secret
├── signing/              # Lab 2.2 - Cosign
│   └── cosign.pub            # Public key (KHÔNG commit private)
├── policies/             # Lab 2.2 - Admission
│   └── cluster-image-policy.yaml  # ClusterImagePolicy verify signature
├── gatekeeper/           # Lab 1.2 - OPA Gatekeeper
│   ├── controller/
│   └── constraints/
├── runbooks/             # Lab 2 - Operational docs
│   ├── eso-secret-rotation.md      # Runbook: rotate secret
│   ├── trivy-cosign-ci-failure.md  # Runbook: CI failure handling
│   └── adr-001-fake-provider.md    # ADR: fake provider exception
├── argocd/
│   ├── apps/             # ArgoCD Application manifests
│   │   ├── app-api.yaml
│   │   ├── app-analysis.yaml
│   │   ├── app-common.yaml
│   │   ├── eso.yaml              # ESO operator (sync-wave -1)
│   │   ├── eso-config.yaml       # ESO config (sync-wave 1)
│   │   ├── policy-controller.yaml # Sigstore (sync-wave -1)
│   │   ├── policies.yaml         # ClusterImagePolicy (sync-wave 1)
│   │   ├── gatekeeper.yaml
│   │   ├── k8s-rollout.yaml
│   │   └── rbac.yaml
│   └── root.yaml         # App of Apps pattern
├── .github/workflows/
│   └── build-push.yml    # CI: build → push → Trivy → Cosign → update rollout
└── README.md
```

## Quick Start

### 1. Setup Cluster
```bash
minikube start -p w10 --driver=docker --memory=8192
kubectl config use-context w10
```

### 2. Install ArgoCD
```bash
kubectl create ns argocd
kubectl apply --server-side -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server
```

### 3. Access ArgoCD UI
```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443 &
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 -d; echo
```

### 4. Deploy App of Apps
```bash
kubectl apply -f argocd/root.yaml
```

---

## Lab 2.1 — ESO: Rotate Secret không Restart Pod

### Kiến trúc

```
Fake Provider (SecretStore)
      ↓ (ESO sync mỗi 10s)
ExternalSecret → K8s Secret: api-db-secret
      ↓ (volume mount)
Pod đọc /etc/secrets/password
```

### Cách hoạt động
- **SecretStore**: Dùng fake provider (xem [ADR-001](runbooks/adr-001-fake-provider.md))
- **ExternalSecret**: refreshInterval `10s`, map key `/db/password` → K8s Secret
- **App**: Đọc password qua **volume mount** (không phải env) → pod không cần restart khi secret thay đổi

### Sync Wave Order
1. `eso.yaml` (wave -1): Cài ESO operator trước
2. `eso-config.yaml` (wave 1): Apply SecretStore + ExternalSecret sau khi CRDs có sẵn

### Verify
```bash
# Kiểm tra secret đã sync
kubectl get secret api-db-secret -n demo -o jsonpath='{.data.password}' | base64 -d

# Đổi value trong secret-store.yaml → commit + push → chờ < 60s
kubectl get secret api-db-secret -n demo -o jsonpath='{.data.password}' | base64 -d
# → Phải thấy value mới

# Pod không restart (AGE không đổi)
kubectl get pod -n demo -l app=api
```

---

## Lab 2.2 — Trivy + Cosign: Scan + Ký + Verify Image

### CI Pipeline (`.github/workflows/build-push.yml`)

```
Build → Push GHCR → Trivy scan (exit-code 1) → Cosign sign → Update rollout.yaml
```

| Step | Tool | Hành vi |
|---|---|---|
| Scan CVE | Trivy | Fail pipeline nếu có HIGH/CRITICAL |
| Ký image | Cosign | Sign với private key (GitHub Secret) |
| Verify admission | Policy Controller | Reject unsigned image vào namespace `demo` |

### Cosign Key Management
- **Private key**: Chỉ lưu trong GitHub Secrets (`COSIGN_PRIVATE_KEY`, `COSIGN_PASSWORD`)
- **Public key**: Commit tại `signing/cosign.pub` và dùng trong `policies/cluster-image-policy.yaml`
- **KHÔNG BAO GIỜ commit private key vào repo**

### ClusterImagePolicy
```yaml
# Chỉ cho phép image đã ký từ ghcr.io/rabbitboy123/**
spec:
  images:
    - glob: "ghcr.io/rabbitboy123/**"
  authorities:
    - key:
        data: |
          -----BEGIN PUBLIC KEY-----
          ...
          -----END PUBLIC KEY-----
```

### Namespace Label
```yaml
# demo namespace phải có label để policy enforce
metadata:
  labels:
    policy.sigstore.dev/include: "true"
```

### Verify
```bash
# Verify image đã ký
cosign verify --key signing/cosign.pub ghcr.io/rabbitboy123/w10-api:<version>

# Test unsigned image bị reject
kubectl run test --image=nginx -n demo
# → Phải bị reject bởi policy controller
```

---

## Self-Check trước khi nộp

| # | Kiểm tra | Lệnh | Kỳ vọng |
|---|---|---|---|
| 1 | ESO rotate < 60s | `kubectl get secret -o jsonpath` | Value mới sau < 60s |
| 2 | Pod không restart | `kubectl get pod` | AGE không đổi |
| 3 | CI đỏ khi CVE HIGH | GitHub Actions | Pipeline fail |
| 4 | Unsigned image reject | `kubectl run test --image=nginx -n demo` | Bị reject |
| 5 | Không lộ secret | `git log -p \| grep -i password` | Không có secret thật |
| 6 | Fresh apply → tự xanh | `kubectl apply -f argocd/root.yaml` | Tất cả app synced |

## Runbooks

- [ESO Secret Rotation](runbooks/eso-secret-rotation.md)
- [Trivy / Cosign CI Failure](runbooks/trivy-cosign-ci-failure.md)
- [ADR-001: Fake Provider Exception](runbooks/adr-001-fake-provider.md)

## Cleanup

```bash
kubectl delete -f argocd/root.yaml
kubectl get all -n demo
kubectl delete ns argocd
minikube stop -p w10
minikube delete -p w10
```
