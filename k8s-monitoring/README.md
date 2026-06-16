# Monitoring Setup

## Setup Secrets (Manual - KHÔNG commit vào Git!)

### 1. Email Secret

```bash
# Copy template
cp email-secret.yaml.example email-secret.yaml

# Edit với credentials thật
vim email-secret.yaml

# Apply
kubectl apply -f email-secret.yaml
```

### 2. AlertManager Config

```bash
# Copy template
cp alertmanager-config.yaml.template alertmanager-config.yaml

# Replace placeholders:
# - <YOUR_EMAIL> → vuongbachdoan@gmail.com
# - <YOUR_GMAIL_APP_PASSWORD> → your-app-password

# Apply
kubectl apply -f alertmanager-config.yaml

# Restart AlertManager
kubectl -n monitoring delete pod -l app.kubernetes.io/name=alertmanager
```

## Files

- `prometheus-rules.yaml` - SLO alert rules ✅ commit vào Git
- `email-secret.yaml.example` - Email secret template ✅ commit vào Git
- `alertmanager-config.yaml.template` - AlertManager config template ✅ commit vào Git
- `email-secret.yaml` - Email credentials ⛔ GIT IGNORED
- `alertmanager-config.yaml` - AlertManager config with real password ⛔ GIT IGNORED
- `README.md` - Setup instructions ✅ commit vào Git

## Email Template Features

Professional HTML email với:
- 🎨 Gradient header (orange → red)
- 🔴 Critical alerts: Red badge + red border
- ⚠️ Warning alerts: Orange badge + orange border
- 📊 Metric details: Status, timestamp, namespace, pod
- 💅 Responsive design với inline CSS
