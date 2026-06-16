# W9 Starter Kit

Đây là template repo của W9, dùng để thực hành tiếp cho W10

## Yêu cầu

- Cài sẵn Docker Desktop
- Cài sẵn kubectl
- Cài sẵn minikube
- Cài sẵn git
- Đã có AWS account
- Biết cách dựng lại W9

## Structure

```
demo/
├── k8s/                  
├── k8s-api/              
├── argocd/
│   ├── apps/          
│   └── root.yaml      
├── app/             
│   ├── app.py
│   └── Dockerfile
└── .github/workflows/   
    └── validate.yml
```

## Setup GitOps

### Lab 0: Setup cluster + repo
```bash
minikube start -p w10 --driver=docker
kubectl config use-context w10

# Clone repo teamplate này về
git clone https://github.com/Vuong-Bach/w10.git
```

### Lab 1: Cài ArgoCD
```bash
kubectl create ns argocd
kubectl apply --server-side -n argocd \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server
```

### Lab 2: Tạo Application
- Trong `argocd/apps/web.yaml` đã có sẵn Deployment cho nginx

### Lab 5: app-of-apps
- Trong `argocd/` đã có sẵn cấu hình của App-of-Apps