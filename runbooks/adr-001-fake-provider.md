# ADR-001: Sử dụng Fake Provider thay vì AWS Secrets Manager

## Status

**Accepted** — Exception cho môi trường lab

## Context

Lab 2.1 yêu cầu: _"App đang đọc DB password từ Secret plaintext. Chuyển sang AWS Secrets Manager + ESO tự sync."_

Tuy nhiên, môi trường lab có các hạn chế:
- Không có AWS account / IAM credentials
- Cluster chạy trên minikube local (8GB RAM)
- Mục tiêu là chứng minh **pattern** ESO, không phải integration với cloud cụ thể

## Decision

Sử dụng ESO **Fake Provider** (`spec.provider.fake`) thay vì AWS Secrets Manager.

### Fake Provider hoạt động thế nào

```yaml
# SecretStore với fake provider
spec:
  provider:
    fake:
      data:
        - key: /db/password
          value: "my-initial-db-password"
```

- ESO operator vẫn chạy đầy đủ (CRDs, controller, webhook)
- ExternalSecret vẫn sync theo `refreshInterval`
- K8s Secret vẫn được tạo và quản lý bởi ESO (creationPolicy: Owner)
- Volume mount vẫn hoạt động → pod không restart khi secret thay đổi

## Consequences

### Giống production

| Aspect | Fake Provider | AWS SM | Giống? |
|---|---|---|---|
| ESO Operator chạy đầy đủ | ✅ | ✅ | ✅ |
| SecretStore + ExternalSecret CRDs | ✅ | ✅ | ✅ |
| K8s Secret tự động sync | ✅ | ✅ | ✅ |
| Volume mount → no pod restart | ✅ | ✅ | ✅ |
| refreshInterval hoạt động | ✅ | ✅ | ✅ |
| GitOps qua ArgoCD | ✅ | ✅ | ✅ |

### Khác production

| Aspect | Fake Provider | AWS SM |
|---|---|---|
| Secret source | In-cluster (YAML) | AWS cloud |
| Authentication | Không cần | IAM Role / Access Key |
| Rotate từ bên ngoài | Sửa YAML + commit | AWS CLI / Console |
| Encryption at rest | Không | AWS KMS |

## Chuyển sang AWS (nếu cần)

Chỉ cần thay đổi `secret-store.yaml`:

```yaml
# Từ fake:
spec:
  provider:
    fake:
      data:
        - key: /db/password
          value: "..."

# Sang AWS:
spec:
  provider:
    aws:
      service: SecretsManager
      region: ap-southeast-1
      auth:
        secretRef:
          accessKeyIDSecretRef:
            name: aws-credentials
            key: access-key
          secretAccessKeySecretRef:
            name: aws-credentials
            key: secret-key
```

ExternalSecret và toàn bộ flow không cần thay đổi.

## References

- [ESO Fake Provider docs](https://external-secrets.io/latest/provider/fake/)
- Slide Lab 2.1: _"Không có AWS? fallback provider fake của ESO — vẫn chứng minh được pattern"_
