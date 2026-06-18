# Runbook: Trivy / Cosign CI Failure

## Tình huống

CI pipeline (`.github/workflows/build-push.yml`) fail ở bước Trivy scan hoặc Cosign sign.

## Pipeline Flow

```
Build image → Push to GHCR → Trivy scan → Cosign sign → Update rollout.yaml
                                  ↑              ↑
                              Fail nếu          Fail nếu
                           CVE HIGH/CRITICAL    key sai/hết hạn
```

---

## Case A: Trivy Scan Fail

### Triệu chứng
- GitHub Actions log: `Trivy found vulnerabilities`
- Exit code 1 từ trivy-action

### Nguyên nhân
Image chứa CVE mức **HIGH** hoặc **CRITICAL** (cấu hình `severity: 'CRITICAL,HIGH'`).

### Xử lý

**Bước 1: Xem chi tiết CVE**
```bash
# Chạy local để xem report
docker pull ghcr.io/rabbitboy123/w10-api:<version>
trivy image --severity HIGH,CRITICAL ghcr.io/rabbitboy123/w10-api:<version>
```

**Bước 2: Fix CVE**

| Loại CVE | Cách fix |
|---|---|
| OS package (Alpine) | Upgrade base image: `FROM python:3.13-alpine` → version mới hơn |
| Python library | Update `pip install` version hoặc thêm `requirements.txt` với pinned versions |
| Unfixed (no patch) | Nếu không có patch → xem Case C bên dưới |

**Bước 3: Rebuild**
```bash
git add src/api/Dockerfile
git commit -m "fix: upgrade base image to patch CVE-XXXX-XXXXX"
git push origin main
# CI tự chạy lại
```

---

## Case B: Cosign Sign Fail

### Triệu chứng
- GitHub Actions log: `error signing`, `no key found`, hoặc `incorrect password`

### Nguyên nhân phổ biến

| Nguyên nhân | Cách kiểm tra |
|---|---|
| `COSIGN_PRIVATE_KEY` secret chưa set | GitHub → Settings → Secrets → kiểm tra |
| `COSIGN_PASSWORD` sai | Tạo lại keypair và update secret |
| Key hết hạn hoặc bị corrupt | Generate keypair mới |

### Xử lý: Tạo lại keypair

```bash
# Generate keypair mới
cosign generate-key-pair

# Output:
# - cosign.key (PRIVATE → GitHub Secret ONLY)
# - cosign.pub (PUBLIC → commit vào repo signing/)

# Update GitHub Secrets
# 1. Vào repo → Settings → Secrets → Actions
# 2. Update COSIGN_PRIVATE_KEY = nội dung cosign.key
# 3. Update COSIGN_PASSWORD = password khi generate

# Update public key
cp cosign.pub signing/cosign.pub
# Cũng update trong policies/cluster-image-policy.yaml

# KHÔNG BAO GIỜ commit cosign.key vào repo!
rm cosign.key
```

---

## Case C: CVE không có patch (Exception)

Nếu CVE không có patch available (`ignore-unfixed: true` đã bật nhưng vẫn fail):

1. Đánh giá risk: CVE có ảnh hưởng đến app không?
2. Nếu accept risk → tạo `.trivyignore`:
   ```
   # Accepted risk - CVE has no fix available
   # Reviewed by: <name> on <date>
   CVE-XXXX-XXXXX
   ```
3. Tạo ADR document giải thích quyết định
4. Commit và re-run pipeline

---

## Verification sau khi fix

```bash
# Kiểm tra CI xanh
# GitHub → Actions → Build and Push Image → ✅

# Kiểm tra image đã signed
cosign verify --key signing/cosign.pub ghcr.io/rabbitboy123/w10-api:<version>

# Kiểm tra cluster accept image
kubectl get events -n demo --field-selector reason=FailedCreate
# Không có event reject = OK
```
