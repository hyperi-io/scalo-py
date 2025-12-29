# hs-pylib App HELM Chart

Production-ready HELM chart for hs-pylib applications (API, Daemon, MCP).

## Features

- Support for all hs-pylib application types (API, Daemon, MCP)
- Profile-based configuration (dev/docker/prod)
- Health checks with custom dependency checks
- Prometheus metrics with ServiceMonitor
- KEDA autoscaling or HPA
- Ingress with TLS support
- ConfigMap and Secret management
- Pod Disruption Budget
- Security best practices (non-root, dropped capabilities)

## Installation

### Basic Install

```bash
helm install my-app ./templates/helm/hs-pylib-app \
  --set app.name=my-app \
  --set app.type=api \
  --set image.repository=my-app \
  --set image.tag=1.0.0
```

### API Application

```bash
helm install my-api ./templates/helm/hs-pylib-app \
  --set app.type=api \
  --set image.repository=my-api \
  --set image.tag=1.0.0 \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=api.example.com
```

### Daemon Application

```bash
helm install my-daemon ./templates/helm/hs-pylib-app \
  --set app.type=daemon \
  --set image.repository=my-daemon \
  --set image.tag=1.0.0 \
  --set service.http.enabled=false \
  --set keda.enabled=true
```

### With Custom Values

```bash
helm install my-app ./templates/helm/hs-pylib-app -f values-prod.yaml
```

## Configuration

### Application Types

Set `app.type` to one of:
- `api` - REST API (FastAPI)
- `daemon` - Background worker
- `mcp` - Model Context Protocol server

### Profiles

Set `app.profile` to one of:
- `dev` - Development (console logs, no health checks)
- `docker` - Docker Compose (JSON logs, health checks)
- `prod` - Production (JSON logs, health checks, metrics) - **Default**

### Health Checks

All application types include:
- Liveness probe: `/health` (is app running?)
- Readiness probe: `/ready` (can app serve traffic?)
- Startup probe: `/health` (slow startup protection)

Timing can be customized:

```yaml
healthCheck:
  enabled: true
  liveness:
    initialDelaySeconds: 30
    periodSeconds: 10
  readiness:
    initialDelaySeconds: 5
    periodSeconds: 5
  startup:
    failureThreshold: 30  # Allow up to 150s for startup
```

### Autoscaling

#### KEDA (Recommended)

```yaml
keda:
  enabled: true
  minReplicaCount: 2
  maxReplicaCount: 20
  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus:9090
      metricName: http_requests_rate
      query: rate(http_requests_total{app="my-app"}[1m])
      threshold: "100"
```

#### HPA (Kubernetes built-in)

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

### Prometheus Metrics

Enable ServiceMonitor for Prometheus Operator:

```yaml
prometheus:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 15s
```

### Ingress

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: my-app.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: my-app-tls
      hosts:
        - my-app.example.com
```

### ConfigMap and Secrets

```yaml
configMap:
  enabled: true
  data:
    DATABASE_HOST: "postgres.default.svc.cluster.local"
    REDIS_URL: "redis://redis:6379"

secret:
  enabled: true
  data:
    DATABASE_PASSWORD: "changeme"
    API_KEY: "changeme"
```

**Production:** Use external-secrets or sealed-secrets instead of inline secrets.

### Environment Variables

```yaml
env:
  - name: LOG_LEVEL
    value: INFO
  - name: DATABASE_HOST
    valueFrom:
      configMapKeyRef:
        name: my-app-config
        key: DATABASE_HOST

envFrom:
  - configMapRef:
      name: my-app-config
  - secretRef:
      name: my-app-secrets
```

## Values Files

### Development (values-dev.yaml)

```yaml
app:
  profile: dev
replicaCount: 1
resources:
  requests:
    cpu: 50m
    memory: 64Mi
healthCheck:
  enabled: false
```

### Staging (values-staging.yaml)

```yaml
app:
  profile: docker
replicaCount: 2
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 5
```

### Production (values-prod.yaml)

```yaml
app:
  profile: prod
replicaCount: 3
keda:
  enabled: true
  minReplicaCount: 3
  maxReplicaCount: 20
prometheus:
  enabled: true
  serviceMonitor:
    enabled: true
podDisruptionBudget:
  enabled: true
  minAvailable: 2
```

## Examples

See complete examples:
- [examples/api-container](../../examples/api-container) - REST API
- [examples/daemon-container](../../examples/daemon-container) - Background worker

## Upgrading

```bash
# Dry run
helm upgrade my-app ./templates/helm/hs-pylib-app --dry-run --debug

# Apply upgrade
helm upgrade my-app ./templates/helm/hs-pylib-app

# Rollback if needed
helm rollback my-app
```

## Uninstalling

```bash
helm uninstall my-app
```

## See Also

- [hs-pylib Documentation](https://github.com/hypersec-io/hs-pylib/tree/main/docs)
- [Kubernetes Guide](../../../docs/KUBERNETES.md)
- [Profiles Guide](../../../docs/PROFILES.md)
