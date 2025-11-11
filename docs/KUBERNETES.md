# Kubernetes Deployment Guide

Production Kubernetes deployment with HELM, ArgoCD, and KEDA autoscaling.

## Quick Start

### 1. Create Application

```python
# src/my_app/__init__.py
from hyperlib import Application

app = Application.api(
    name="my-app",
    version="1.0.0",
    profile="prod"  # Enables health checks, metrics, JSON logs
)

@app.health_check
def check_database():
    try:
        db.ping()
        return True
    except Exception:
        return False

@app.route("/")
def root():
    return {"status": "ok"}
```

### 2. Create Kubernetes Manifest

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
  labels:
    app: my-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: my-app
  template:
    metadata:
      labels:
        app: my-app
    spec:
      containers:
      - name: api
        image: my-app:1.0.0
        ports:
        - containerPort: 8000
          name: http
        - containerPort: 8080
          name: health
        - containerPort: 9090
          name: metrics
        env:
        - name: HYPERLIB_PROFILE
          value: "prod"
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2
        startupProbe:
          httpGet:
            path: /health/live
            port: 8080
          initialDelaySeconds: 0
          periodSeconds: 5
          failureThreshold: 30
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 500m
            memory: 512Mi
```

### 3. Deploy

```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml

# Check deployment
kubectl get pods
kubectl logs -f deployment/my-app
```

## Health Probes

### Liveness Probe

Checks if the application is running:

```yaml
livenessProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 30   # Wait 30s after container start
  periodSeconds: 10         # Check every 10s
  timeoutSeconds: 3         # Fail if no response in 3s
  failureThreshold: 3       # Restart after 3 failed checks
```

### Readiness Probe

Checks if the application can serve traffic:

```yaml
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 5    # Start checking after 5s
  periodSeconds: 5          # Check every 5s
  timeoutSeconds: 3
  failureThreshold: 2       # Remove from load balancer after 2 failures
```

**Note**: `/health/ready` returns 503 if any custom health check fails:

```python
@app.health_check
def check_database():
    return db.ping()  # False = 503 response
```

### Startup Probe

Protects slow-starting containers:

```yaml
startupProbe:
  httpGet:
    path: /health/live
    port: 8080
  initialDelaySeconds: 0
  periodSeconds: 5
  failureThreshold: 30      # Allow up to 150s for startup (30 * 5s)
```

## Services

### ClusterIP (Internal)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app
spec:
  type: ClusterIP
  selector:
    app: my-app
  ports:
  - name: http
    port: 80
    targetPort: 8000
  - name: metrics
    port: 9090
    targetPort: 9090
```

### LoadBalancer (External)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app-external
spec:
  type: LoadBalancer
  selector:
    app: my-app
  ports:
  - name: http
    port: 80
    targetPort: 8000
```

### Headless (StatefulSet)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-app-headless
spec:
  clusterIP: None
  selector:
    app: my-app
  ports:
  - name: http
    port: 8000
```

## ConfigMaps and Secrets

### ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: my-app-config
data:
  DATABASE_HOST: "postgres.default.svc.cluster.local"
  DATABASE_PORT: "5432"
  REDIS_HOST: "redis.default.svc.cluster.local"
```

### Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: my-app-secrets
type: Opaque
stringData:
  DATABASE_PASSWORD: "secret123"
  API_KEY: "sk-..."
```

### Using in Deployment

```yaml
spec:
  containers:
  - name: api
    envFrom:
    - configMapRef:
        name: my-app-config
    - secretRef:
        name: my-app-secrets
```

## Prometheus Integration

### ServiceMonitor (Prometheus Operator)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: my-app
  labels:
    app: my-app
spec:
  selector:
    matchLabels:
      app: my-app
  endpoints:
  - port: metrics
    path: /metrics
    interval: 15s
    scrapeTimeout: 10s
```

### Metrics Available

```
# HTTP metrics (API applications)
http_requests_total{method,endpoint,status}
http_request_duration_seconds{method,endpoint}

# Task metrics (Daemon applications)
task_execution_total{task,status}
task_execution_duration_seconds{task}

# Process metrics
process_cpu_seconds_total
process_resident_memory_bytes
```

## KEDA Autoscaling

### Install KEDA

```bash
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda --namespace keda --create-namespace
```

### ScaledObject (Prometheus Trigger)

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: my-app-scaler
spec:
  scaleTargetRef:
    name: my-app
  minReplicaCount: 2
  maxReplicaCount: 10
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus:9090
      metricName: http_requests_rate
      query: |
        rate(http_requests_total{app="my-app"}[1m])
      threshold: "100"
```

### ScaledObject (CPU/Memory)

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: my-app-cpu-scaler
spec:
  scaleTargetRef:
    name: my-app
  minReplicaCount: 2
  maxReplicaCount: 20
  triggers:
  - type: cpu
    metricType: Utilization
    metadata:
      value: "70"
  - type: memory
    metricType: Utilization
    metadata:
      value: "80"
```

### ScaledObject (Queue Length)

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: worker-scaler
spec:
  scaleTargetRef:
    name: my-worker
  minReplicaCount: 1
  maxReplicaCount: 50
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus:9090
      metricName: task_queue_depth
      query: |
        task_queue_depth{app="my-worker",queue="pending"}
      threshold: "10"
```

## HELM Charts

### Create Chart

```bash
mkdir -p templates/helm/my-app
cd templates/helm/my-app
```

### Chart.yaml

```yaml
apiVersion: v2
name: my-app
description: My Application
type: application
version: 1.0.0
appVersion: "1.0.0"
```

### values.yaml

```yaml
replicaCount: 3

image:
  repository: my-app
  pullPolicy: IfNotPresent
  tag: "1.0.0"

service:
  type: ClusterIP
  port: 80
  targetPort: 8000
  metricsPort: 9090

ingress:
  enabled: false
  className: nginx
  hosts:
    - host: my-app.example.com
      paths:
        - path: /
          pathType: Prefix

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

healthCheck:
  enabled: true
  port: 8080
  livenessProbe:
    initialDelaySeconds: 30
    periodSeconds: 10
  readinessProbe:
    initialDelaySeconds: 5
    periodSeconds: 5

metrics:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 15s

keda:
  enabled: false
  minReplicaCount: 2
  maxReplicaCount: 20
  triggers: []
```

### templates/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "my-app.fullname" . }}
  labels:
    {{- include "my-app.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "my-app.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "my-app.selectorLabels" . | nindent 8 }}
    spec:
      containers:
      - name: {{ .Chart.Name }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - name: http
          containerPort: {{ .Values.service.targetPort }}
        {{- if .Values.healthCheck.enabled }}
        - name: health
          containerPort: {{ .Values.healthCheck.port }}
        {{- end }}
        {{- if .Values.metrics.enabled }}
        - name: metrics
          containerPort: {{ .Values.service.metricsPort }}
        {{- end }}
        {{- if .Values.healthCheck.enabled }}
        livenessProbe:
          httpGet:
            path: /health/live
            port: health
          {{- toYaml .Values.healthCheck.livenessProbe | nindent 10 }}
        readinessProbe:
          httpGet:
            path: /health/ready
            port: health
          {{- toYaml .Values.healthCheck.readinessProbe | nindent 10 }}
        {{- end }}
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
```

### Install with HELM

```bash
# Install
helm install my-app ./templates/helm/my-app

# Upgrade
helm upgrade my-app ./templates/helm/my-app

# Uninstall
helm uninstall my-app

# Override values
helm install my-app ./templates/helm/my-app \
  --set replicaCount=5 \
  --set image.tag=1.0.1
```

## ArgoCD GitOps

### Application Manifest

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/myorg/my-app
    targetRevision: main
    path: templates/helm/my-app
    helm:
      values: |
        replicaCount: 3
        image:
          tag: "1.0.0"
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
```

### Deploy with ArgoCD

```bash
# Apply application
kubectl apply -f argocd/application.yaml

# Sync manually
argocd app sync my-app

# Check status
argocd app get my-app
```

## Multi-Environment Deployment

### Dev Environment

```yaml
# values-dev.yaml
replicaCount: 1
resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 256Mi
autoscaling:
  enabled: false
```

### Staging Environment

```yaml
# values-staging.yaml
replicaCount: 2
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi
keda:
  enabled: true
  maxReplicaCount: 5
```

### Production Environment

```yaml
# values-prod.yaml
replicaCount: 3
resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 1000m
    memory: 1Gi
keda:
  enabled: true
  minReplicaCount: 3
  maxReplicaCount: 20
```

Deploy:

```bash
helm install my-app-dev ./helm/my-app -f values-dev.yaml -n dev
helm install my-app-staging ./helm/my-app -f values-staging.yaml -n staging
helm install my-app-prod ./helm/my-app -f values-prod.yaml -n production
```

## Best Practices

### Resource Limits

Always set requests and limits:

```yaml
resources:
  requests:
    cpu: 100m      # Guaranteed
    memory: 128Mi
  limits:
    cpu: 500m      # Maximum allowed
    memory: 512Mi
```

### Health Check Timing

Configure based on application startup time:

```yaml
# Fast startup (< 10s)
readinessProbe:
  initialDelaySeconds: 5
livenessProbe:
  initialDelaySeconds: 15

# Slow startup (30-60s)
startupProbe:
  failureThreshold: 30  # 30 * 5s = 150s max
readinessProbe:
  initialDelaySeconds: 5
livenessProbe:
  initialDelaySeconds: 60
```

### Rolling Updates

Zero-downtime deployments:

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0     # Keep all pods running
      maxSurge: 1           # Add 1 extra pod during update
```

### Pod Disruption Budgets

Maintain availability during updates:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: my-app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: my-app
```

## Troubleshooting

### Pods Not Ready

```bash
# Check pod status
kubectl get pods -l app=my-app

# Check logs
kubectl logs -f deployment/my-app

# Check events
kubectl describe pod my-app-xxx

# Test health endpoint
kubectl exec -it my-app-xxx -- curl http://localhost:8080/health/ready
```

### Health Checks Failing

```bash
# Check readiness
kubectl exec -it my-app-xxx -- curl -v http://localhost:8080/ready

# Check liveness
kubectl exec -it my-app-xxx -- curl -v http://localhost:8080/health

# View health check failures
kubectl describe pod my-app-xxx | grep -A 10 "Liveness\|Readiness"
```

### KEDA Not Scaling

```bash
# Check ScaledObject
kubectl get scaledobject
kubectl describe scaledobject my-app-scaler

# Check metrics
kubectl get --raw /apis/external.metrics.k8s.io/v1beta1 | jq .

# Test Prometheus query
curl "http://prometheus:9090/api/v1/query?query=rate(http_requests_total[1m])"
```

## See Also

- [Container Deployment](CONTAINER_DEPLOYMENT.md) - Docker basics
- [Profiles Guide](PROFILES.md) - Environment configuration
- [Application Types](README.md) - API, Daemon, MCP guides
