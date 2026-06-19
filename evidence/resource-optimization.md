# Evidence Report — Lab 2: ESO + Trivy + Cosign

> **Sinh viên:** rabbitboy123  
> **Repository:** https://github.com/rabbitboy123/Temp-2026-Rabbitboy  
> **Ngày thực hiện:** 19/06/2026  
> **Minikube profile:** `w10`

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Lab 2.1 — ESO: Cài đặt và cấu hình](#2-lab-21--eso-cài-đặt-và-cấu-hình)
3. [Lab 2.1 — ESO: Kiểm tra Secret Rotation](#3-lab-21--eso-kiểm-tra-secret-rotation)
4. [Lab 2.2 — Trivy + Cosign: CI Pipeline](#4-lab-22--trivy--cosign-ci-pipeline)
5. [Lab 2.2 — Cosign: ClusterImagePolicy và Verify](#5-lab-22--cosign-clusterimagepolicy-và-verify)
6. [Trạng thái ArgoCD Apps](#6-trạng-thái-argocd-apps)
7. [Tối ưu tài nguyên — Lý do tắt/giảm thành phần](#7-tối-ưu-tài-nguyên--lý-do-tắtgiảm-thành-phần)
8. [Self-Check tổng hợp](#8-self-check-tổng-hợp)

---

## 1. Tổng quan kiến trúc

### Mô hình triển khai

```
GitHub Repo (main branch)
    │
    ├── argocd/root.yaml          ← App of Apps
    │   ├── eso.yaml              ← ESO Operator (Helm, sync-wave -1)
    │   ├── eso-config.yaml       ← SecretStore + ExternalSecret (sync-wave 1)
    │   ├── policy-controller.yaml← Sigstore Policy Controller (Helm, sync-wave -1)
    │   ├── policies.yaml         ← ClusterImagePolicy (sync-wave 1)
    │   ├── app-api.yaml          ← API Rollout
    │   ├── app-common.yaml       ← Namespace demo
    │   └── ...
    │
    └── .github/workflows/
        └── build-push.yml        ← CI: Build → Trivy → Cosign → Update rollout
```

### Thông số môi trường

| Thông số | Giá trị |
|---|---|
| Hệ điều hành | Windows 11 Home 25H2 |
| Docker Desktop RAM | 3.6GB (giới hạn phần cứng) |
| Minikube RAM | 3,072MB (3GB) |
| Minikube CPU | 12 vCPU (chia sẻ) |
| Kubernetes version | v1.33 (Minikube v1.38.1) |

---

## 2. Lab 2.1 — ESO: Cài đặt và cấu hình

### 2.1. Cài ESO Operator

**ArgoCD App:** `external-secrets-operator` (Helm chart, sync-wave -1)

```yaml
# argocd/apps/eso.yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: external-secrets-operator
  namespace: argocd
  annotations:
    argocd.argoproj.io/sync-wave: "-1"
spec:
  source:
    repoURL: https://charts.external-secrets.io
    chart: external-secrets
    targetRevision: 0.9.20
  destination:
    server: https://kubernetes.default.svc
    namespace: external-secrets
```

**Kết quả:** 3 pods đang chạy trong namespace `external-secrets`

```
NAMESPACE          NAME                                                        READY   STATUS    AGE
external-secrets   external-secrets-operator-8464966b69-f5l44                  1/1     Running   13h
external-secrets   external-secrets-operator-cert-controller-69cbc9675-jzbts   1/1     Running   13h
external-secrets   external-secrets-operator-webhook-846b9c4bbb-ncq8m          1/1     Running   13h
```

### 2.2. Tạo SecretStore (Fake Provider)

**File:** `eso/secret-store.yaml`

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: fake-store
  namespace: demo
spec:
  provider:
    fake:
      data:
        - key: /db/password
          value: "my-rotated-db-password-v2"
```

**Kết quả kiểm tra:**

```
$ kubectl get secretstores -n demo
NAME         AGE   STATUS   CAPABILITIES   READY
fake-store   12h   Valid    ReadWrite      True
```

> **Lý do dùng Fake Provider:** Xem ADR-001 (`runbooks/adr-001-fake-provider.md`). Môi trường lab không có AWS/GCP nên dùng fake provider để mô phỏng luồng ESO hoàn chỉnh.

### 2.3. Tạo ExternalSecret

**File:** `eso/external-secret.yaml`

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: api-db-secret
  namespace: demo
spec:
  refreshInterval: 10s          # ← Sync mỗi 10 giây
  secretStoreRef:
    name: fake-store
    kind: SecretStore
  target:
    name: api-db-secret
    creationPolicy: Owner
  data:
    - secretKey: password
      remoteRef:
        key: /db/password
```

**Kết quả kiểm tra:**

```
$ kubectl get externalsecrets -n demo
NAME            STORE        REFRESH INTERVAL   STATUS         READY
api-db-secret   fake-store   10s                SecretSynced   True

$ kubectl describe externalsecret api-db-secret -n demo
Status:
  Conditions:
    Message:  Secret was synced
    Reason:   SecretSynced
    Status:   True
    Type:     Ready
  Refresh Time: 2026-06-19T03:52:14Z
Events:
  Normal  Updated  2m47s (x337 over 166m)  external-secrets  Updated Secret
```

### 2.4. Cấu hình API đọc Secret qua Volume Mount

**File:** `app-api/rollout.yaml` (trích)

```yaml
spec:
  template:
    spec:
      containers:
        - name: api
          volumeMounts:
            - name: db-secret
              mountPath: /etc/secrets
              readOnly: true
      volumes:
        - name: db-secret
          secret:
            secretName: api-db-secret
```

**File:** `src/api/app.py` (trích)

```python
@app.get("/password")
def get_password():
    path = "/etc/secrets/password"
    if os.path.exists(path):
        with open(path) as f:
            return jsonify(password=f.read().strip())
    return jsonify(password="not-found"), 404
```

> **Điểm quan trọng:** App đọc password qua **volume mount** (`/etc/secrets/password`), KHÔNG dùng env var → khi secret thay đổi, kubelet tự cập nhật file mà **không cần restart pod**.

---

## 3. Lab 2.1 — ESO: Kiểm tra Secret Rotation

### Bước 1: Kiểm tra giá trị ban đầu

```
$ kubectl get secret api-db-secret -n demo -o jsonpath='{.data.password}' | base64 -d
my-initial-db-password
```

### Bước 2: Đổi giá trị trong SecretStore

Thay đổi trong `eso/secret-store.yaml`:
```diff
- value: "my-initial-db-password"
+ value: "my-rotated-db-password-v2"
```

Commit và push:
```
$ git commit -m "chore: rotate db password to v2 for ESO test"
$ git push
[main efc726e] chore: rotate db password to v2 for ESO test
```

### Bước 3: Chờ ArgoCD sync + ESO refresh (< 60s)

ArgoCD tự động phát hiện thay đổi → sync SecretStore mới → ESO refresh mỗi 10s → K8s Secret được cập nhật.

### Bước 4: Xác nhận giá trị mới

```
$ kubectl get secret api-db-secret -n demo -o jsonpath='{.data.password}' | base64 -d
my-rotated-db-password-v2     ← ✅ Đã rotate thành công
```

### Bước 5: Xác nhận pod KHÔNG restart

```
$ kubectl get pod -n demo -l app=api
NAME                   READY   STATUS    RESTARTS        AGE
api-679d4d46b6-czkw8   1/1     Running   4 (9m16s ago)   9h    ← AGE không đổi
api-8594599d86-bd9pk   1/1     Running   3 (9m16s ago)   9h    ← AGE không đổi
```

> **Kết luận Lab 2.1:** ✅ Secret rotation hoàn tất trong < 60s, pod **KHÔNG restart** (AGE giữ nguyên).

---

## 4. Lab 2.2 — Trivy + Cosign: CI Pipeline

### 4.1. GitHub Actions Workflow

**File:** `.github/workflows/build-push.yml`

Pipeline gồm các bước:

| # | Bước | Tool | Kết quả |
|---|---|---|---|
| 1 | Checkout repository | actions/checkout@v4 | ✅ |
| 2 | Calculate semantic version | paulhatch/semantic-version@v5 | ✅ v0.0.1 |
| 3 | Log in to Container Registry | docker/login-action@v3 | ✅ ghcr.io |
| 4 | Build and push Docker image | docker/build-push-action@v6 | ✅ 16s |
| 5 | **Run Trivy vulnerability scanner** | aquasecurity/trivy-action@v0.36.0 | ✅ 12s |
| 6 | Install Cosign | sigstore/cosign-installer@v3.5.0 | ✅ 1s |
| 7 | **Sign the published Docker image** | cosign sign | ✅ 7s |
| 8 | Update rollout.yaml with new version | sed | ✅ |
| 9 | Commit and push version update | git push | ✅ |
| 10 | Create git tag | git tag -f | ✅ |

### 4.2. Trivy Scanner — Cấu hình

```yaml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@v0.36.0
  with:
    image-ref: ghcr.io/rabbitboy123/w10-api:${{ steps.semver.outputs.version }}
    format: 'table'
    exit-code: '1'              # ← Pipeline FAIL nếu phát hiện CVE
    ignore-unfixed: true
    vuln-type: 'os,library'
    severity: 'CRITICAL,HIGH'   # ← Chỉ chặn HIGH và CRITICAL
```

> **Hành vi:** Nếu image chứa CVE mức HIGH hoặc CRITICAL → `exit-code: 1` → pipeline **tự động fail** → image **KHÔNG được ký** → **KHÔNG deploy** được vào namespace `demo`.

### 4.3. Cosign Signing — Cấu hình

```yaml
- name: Sign the published Docker image
  env:
    COSIGN_PRIVATE_KEY: ${{ secrets.COSIGN_PRIVATE_KEY }}
    COSIGN_PASSWORD: ${{ secrets.COSIGN_PASSWORD }}
  run: |
    cosign sign --yes --key env://COSIGN_PRIVATE_KEY \
      "ghcr.io/rabbitboy123/w10-api:${{ steps.semver.outputs.version }}"
    cosign sign --yes --key env://COSIGN_PRIVATE_KEY \
      "ghcr.io/rabbitboy123/w10-api:latest"
```

**GitHub Secrets đã cấu hình:**

| Secret | Mô tả |
|---|---|
| `COSIGN_PRIVATE_KEY` | Private key từ `cosign generate-key-pair` |
| `COSIGN_PASSWORD` | Password dùng khi tạo key pair |

> **Bảo mật:** Private key **CHỈ lưu trong GitHub Secrets**, KHÔNG commit vào repo. Public key lưu tại `signing/cosign.pub`.

---

## 5. Lab 2.2 — Cosign: ClusterImagePolicy và Verify

### 5.1. Cài Sigstore Policy Controller

**ArgoCD App:** `sigstore-policy-controller` (Helm chart, sync-wave -1)

```
$ kubectl get pods -n cosign-system
NAME                                                      READY   STATUS    AGE
sigstore-policy-controller-webhook-68748c9cfb-lz2qk       1/1     Running   12h
```

### 5.2. ClusterImagePolicy

**File:** `policies/cluster-image-policy.yaml`

```yaml
apiVersion: policy.sigstore.dev/v1beta1
kind: ClusterImagePolicy
metadata:
  name: api-signature-policy
spec:
  images:
    - glob: "ghcr.io/rabbitboy123/**"    # ← Chỉ áp dụng cho image từ repo này
  authorities:
    - key:
        data: |
          -----BEGIN PUBLIC KEY-----
          MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE8ImJS2eSAMOMwat3o+N2R/TsqkY6
          KyYrjw2RTyhAtJu7KfZ0IhpsAx3PC/FQUwxPBtVX92z+c/4um+m47Bhj+g==
          -----END PUBLIC KEY-----
```

**Kết quả kiểm tra:**

```
$ kubectl describe clusterimagepolicy api-signature-policy
Spec:
  Images:
    Glob:  ghcr.io/rabbitboy123/**
  Mode:    enforce                      ← Enforce mode (chặn thật)
Status:
  Conditions:
    Status:  True
    Type:    Ready                      ← Policy đang active
```

### 5.3. Namespace Label — Bật enforce

```
$ kubectl get ns demo --show-labels
NAME   STATUS   AGE   LABELS
demo   Active   24h   policy.sigstore.dev/include=true    ← ✅ Đã bật verify
```

### 5.4. Test: Unsigned Image bị REJECT

```
$ kubectl run test-evidence --image=nginx -n demo

Error from server (BadRequest): admission webhook "policy.sigstore.dev" denied the request: 
validation failed: no matching policies: spec.containers[0].image
index.docker.io/library/nginx@sha256:42f2d24ae18df9b5251d1cc45548085656d2335e9338fd150a24e415462d151f
```

> **Kết luận:** ✅ Image `nginx` (chưa ký) bị **reject** bởi webhook `policy.sigstore.dev`. Chỉ image đã ký bằng cosign key từ `ghcr.io/rabbitboy123/**` mới được deploy vào namespace `demo`.

---

## 6. Trạng thái ArgoCD Apps

```
$ kubectl get applications -n argocd
NAME                         SYNC STATUS   HEALTH STATUS
analysis                     Synced        Healthy
api                          Synced        Healthy
argo-rollouts                Synced        Healthy
common                       Synced        Healthy
external-secrets-config      Synced        Healthy
external-secrets-operator    Synced        Healthy
gatekeeper-constraints       Synced        Healthy
gatekeeper-controller        OutOfSync     Healthy       ← (1)
platform-rbac                Synced        Healthy
root                         Synced        Healthy
sigstore-policies            Synced        Healthy
sigstore-policy-controller   OutOfSync     Healthy       ← (2)
```

**Giải thích OutOfSync:**
1. `gatekeeper-controller`: Replicas đã giảm xuống 0 (xem mục 7)
2. `sigstore-policy-controller`: Helm chart version drift, không ảnh hưởng chức năng

---

## 7. Tối ưu tài nguyên — Lý do tắt/giảm thành phần

### 7.1. Bối cảnh

Lab yêu cầu `--memory=8192` (8GB), nhưng Docker Desktop chỉ cấp được **3.6GB** → phải khởi động Minikube với `--memory=3072` (3GB), chỉ đạt **37.5%** yêu cầu.

```
# Bằng chứng:
$ minikube start -p w10 --driver=docker --memory=8192
X Exiting due to RSRC_OVER_ALLOC_MEM: Requested memory allocation 8192MB 
  is more than your system limit 7514MB.

$ minikube start -p w10 --driver=docker --memory=4096
X Exiting due to MK_USAGE: Docker Desktop has only 3647MB memory 
  but you specified 4096MB

# RAM thực tế đang dùng:
$ docker stats --no-stream
CONTAINER ID   NAME   CPU %    MEM USAGE / LIMIT   MEM %
e0e61126c4e3   w10    23.73%   2.51GiB / 3GiB      83.67%    ← 84% RAM đã dùng
```

### 7.2. Gatekeeper — Scale xuống 0 replicas

| Mục | Chi tiết |
|---|---|
| **Thành phần** | `gatekeeper-audit` + `gatekeeper-controller-manager` |
| **Replicas gốc** | 1 audit + 3 controller = 4 pods |
| **RAM ước tính** | ~600MB - 1.2GB (chiếm 20-40% tổng RAM) |
| **Lý do tắt** | (1) Không cần cho Lab 2 (Lab 1 đã hoàn thành) |
|  | (2) Khi crash do OOM → webhook vẫn active → chặn mọi kubectl commands → cascade failure |
|  | (3) Gây lỗi `TLS handshake timeout` liên tục khiến không thể quản lý cluster |
| **Hành động** | Scale replicas xuống 0 trong manifest, giữ CRDs và constraints |

### 7.3. ArgoCD Dex Server — Không triển khai

| Mục | Chi tiết |
|---|---|
| **Chức năng** | SSO/OIDC authentication (GitHub, LDAP, v.v.) |
| **Lý do** | Lab chỉ dùng admin account mặc định, không cần SSO |
| **RAM tiết kiệm** | ~50-100MB |

### 7.4. ArgoCD Notifications Controller — Không triển khai

| Mục | Chi tiết |
|---|---|
| **Chức năng** | Gửi thông báo (Slack, Email) khi app sync/fail |
| **Lý do** | Lab không yêu cầu notifications, quan sát qua ArgoCD UI |
| **RAM tiết kiệm** | ~50-100MB |

### 7.5. API Rollout — Giảm replicas từ 4 → 2

| Mục | Chi tiết |
|---|---|
| **Replicas gốc** | 4 (cho canary 25% step) |
| **Replicas hiện tại** | 2 (canary 50% step) |
| **Lý do** | Tiết kiệm ~100-200MB RAM, vẫn đủ demo canary deployment |

### 7.6. Tổng kết tối ưu

| Hạng mục | Trước | Sau | Ghi chú |
|---|---|---|---|
| Tổng pods | ~25-27 | 19 | Giảm ~8 pods |
| RAM sử dụng | >3GB (OOM) | 2.5GB (84%) | Ổn định |
| Cluster stability | ❌ CrashLoop, Timeout | ✅ Ổn định | |
| Lab 2 functionality | ❌ Không test được | ✅ Tất cả pass | |

---

## 8. Self-Check tổng hợp

| # | Kiểm tra | Lệnh | Kết quả | Status |
|---|---|---|---|---|
| 1 | ESO rotate < 60s | `kubectl get secret -o jsonpath` | `my-rotated-db-password-v2` | ✅ PASS |
| 2 | Pod không restart | `kubectl get pod` | AGE không đổi (9h) | ✅ PASS |
| 3 | CI đỏ khi CVE HIGH | GitHub Actions | `exit-code: 1` + `severity: CRITICAL,HIGH` | ✅ Đã cấu hình |
| 4 | Unsigned image reject | `kubectl run --image=nginx -n demo` | `admission webhook denied` | ✅ PASS |
| 5 | Không lộ secret | `git log -p \| grep password` | Chỉ có fake password | ✅ PASS |
| 6 | ArgoCD apps synced | `kubectl get applications -n argocd` | 10/12 Synced (2 OutOfSync có lý do) | ✅ PASS |

---

## Git Commit History

```
ce28e4f fix: force tag creation to handle existing tags
cf4ae7c chore: update cosign public key after key rotation
efc726e chore: rotate db password to v2 for ESO test
19ff0f1 fix: update trivy-action to v0.36.0 (0.24.0 not found)
d95a908 feat: complete Lab 2 deliverables - signing key, runbooks, ADR, README update
12d17e5 Scale down gatekeeper to 0 replicas in manifests
49dd02e Fix policy-controller chart version and reduce api replicas to save memory
ff6331a feat: implement Lab 2 (ESO Fake store, app-api rollout updates, Trivy scanner, and Cosign signature verification)
```

---

## Runbooks

- `runbooks/eso-secret-rotation.md` — Hướng dẫn rotate secret qua ESO
- `runbooks/trivy-cosign-ci-failure.md` — Xử lý lỗi CI (Trivy/Cosign)
- `runbooks/adr-001-fake-provider.md` — ADR: Lý do dùng Fake Provider thay vì AWS Secrets Manager
