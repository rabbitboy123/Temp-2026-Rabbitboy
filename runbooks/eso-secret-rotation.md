# Runbook: ESO Secret Rotation

## Tình huống

DB password cần được rotate (ví dụ: theo policy bảo mật định kỳ, hoặc nghi ngờ bị lộ).

## Kiến trúc hiện tại

```
AWS Secrets Manager (hoặc Fake Provider)
        ↓ (ESO sync mỗi 10s)
  SecretStore → ExternalSecret
        ↓
   K8s Secret: api-db-secret
        ↓ (volume mount)
   Pod đọc /etc/secrets/password
```

- **refreshInterval**: `10s` (cấu hình trong `eso/external-secret.yaml`)
- App đọc secret qua **volume mount** (không phải env var) → pod **KHÔNG cần restart** khi secret thay đổi

## Quy trình Rotate

### Bước 1: Thay đổi giá trị tại nguồn

**Nếu dùng AWS Secrets Manager:**
```bash
aws secretsmanager update-secret \
  --secret-id /db/password \
  --secret-string "new-password-here"
```

**Nếu dùng Fake Provider (lab):**
```bash
# Sửa file eso/secret-store.yaml
# Thay value trong spec.provider.fake.data
# Commit + push → ArgoCD tự sync
```

### Bước 2: Chờ ESO sync (< 60s)

```bash
# Kiểm tra K8s Secret đã cập nhật
kubectl get secret api-db-secret -n demo -o jsonpath='{.data.password}' | base64 -d
```

### Bước 3: Verify pod KHÔNG restart

```bash
# AGE không đổi = pod không restart
kubectl get pod -n demo -l app=api

# Kiểm tra app đọc được password mới (qua volume mount)
kubectl exec -n demo deploy/api -- cat /etc/secrets/password
```

### Bước 4: Verify qua endpoint

```bash
kubectl port-forward -n demo svc/api 8080:80 &
curl http://localhost:8080/password
# Kỳ vọng: trả về password mới
```

## Tại sao pod không cần restart?

| Mount type | Khi Secret thay đổi | Cần restart? |
|---|---|---|
| **Volume mount** | kubelet tự cập nhật file | ❌ Không |
| **Env var** | Env bị freeze khi pod start | ✅ Cần restart |

→ Lab này dùng **volume mount** nên pod tự nhận password mới mà không cần restart.

## Troubleshooting

| Vấn đề | Nguyên nhân | Cách fix |
|---|---|---|
| Secret không cập nhật | ESO operator chưa chạy | `kubectl get pod -n external-secrets` |
| Secret không cập nhật | SecretStore auth sai | `kubectl describe secretstore -n demo` |
| Pod vẫn thấy password cũ | kubelet cache (tối đa ~60s) | Chờ thêm hoặc kiểm tra `subPath` mount |
| ExternalSecret status Error | Remote key không tồn tại | Kiểm tra key path trong provider |
