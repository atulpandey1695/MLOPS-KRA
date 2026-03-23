# Kubeflow Pipelines — Local Development Setup

> **Environment:** Minikube · Kubeflow Pipelines v2.15.0 · KFP SDK 2.9.0 · Argo Workflows v3.7.3

---

## Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Architecture](#architecture)
4. [Infrastructure Components](#infrastructure-components)
5. [Pipelines](#pipelines)
   - [Hello World Pipeline](#hello-world-pipeline)
   - [Iris ML Pipeline](#iris-ml-pipeline)
6. [Pipeline Execution Flow](#pipeline-execution-flow)
7. [Storage & Artifact Path](#storage--artifact-path)
8. [Known Fixes Applied](#known-fixes-applied)
9. [Running the Pipelines](#running-the-pipelines)
10. [Accessing the UI](#accessing-the-ui)

---

## Overview

This project contains two Kubeflow Pipelines v2 examples running on a local Minikube cluster:

| Pipeline | Purpose | Components |
|---|---|---|
| `hello-world-pipeline` | Introductory greeting pipeline | 1 — string I/O |
| `iris-no-artifacts-pipeline` | End-to-end ML training pipeline | 2 — load data → train model |

Both pipelines are authored using the **KFP SDK v2 DSL**, compiled to IR YAML, and submitted to a self-hosted Kubeflow Pipelines backend.

---

## Project Structure

```
kfp/
├── hello_pipeline.py          # hello-world pipeline source (KFP DSL)
├── hello_world_pipeline.yaml  # compiled IR YAML for hello-world pipeline
├── iris_pipeline.py           # Iris ML pipeline source (KFP DSL)
└── README.md                  # this file
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Minikube Cluster                             │
│                      Namespace: kubeflow                            │
│                                                                     │
│  ┌─────────────────┐   REST/gRPC   ┌───────────────────────────┐   │
│  │   KFP SDK /     │──────────────▶│  ml-pipeline (API Server) │   │
│  │   KFP UI        │               │  :8888 (HTTP) :8887 (gRPC)│   │
│  └─────────────────┘               └────────────┬──────────────┘   │
│                                                 │                   │
│                              creates Argo Workflow CRD              │
│                                                 │                   │
│                                                 ▼                   │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │               workflow-controller (Argo)                       │ │
│  │  - Reads workflow-controller-configmap                         │ │
│  │  - Schedules pipeline pods on Minikube node                    │ │
│  └──────┬──────────────────┬──────────────────────────────────── ┘ │
│         │                  │                                        │
│ spawns  │          spawns  │                                        │
│         ▼                  ▼                                        │
│  ┌─────────────┐   ┌──────────────────┐   ┌──────────────────────┐ │
│  │ system-dag- │   │ system-container-│   │ system-container-    │ │
│  │ driver pod  │──▶│ driver pod       │──▶│ impl pod (user code) │ │
│  │(kfp-driver) │   │ (kfp-driver)     │   │ (kfp-launcher +      │ │
│  └─────────────┘   └──────────────────┘   │  user image)         │ │
│                                           └──────────┬───────────┘ │
│                                                      │             │
│               artifact upload (S3 API)               │             │
│                                                      ▼             │
│  ┌────────────────────┐    ┌──────────────────────────────────┐    │
│  │      MySQL         │    │   SeaweedFS (S3-compatible)      │    │
│  │  :3306             │    │   minio-service.kubeflow:9000    │    │
│  │  - pipeline DB     │    │   seaweedfs.kubeflow:9000 (→8333)│    │
│  │  - metadata DB     │    │   bucket: mlpipeline             │    │
│  │  - cache DB        │    └──────────────────────────────────┘    │
│  └────────────────────┘                                            │
│                                                                     │
│  ┌────────────────────┐    ┌──────────────────────────────────┐    │
│  │  metadata-grpc     │    │  cache-server                    │    │
│  │  :8080             │    │  :443                            │    │
│  │  ML Metadata store │    │  Step-level result caching       │    │
│  └────────────────────┘    └──────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Infrastructure Components

| Component | Deployment | Service / Port | Role |
|---|---|---|---|
| **ml-pipeline** (API server) | `ml-pipeline` | `:8888` HTTP, `:8887` gRPC | Accepts pipeline + run requests; generates Argo Workflow CRDs |
| **ml-pipeline-ui** | `ml-pipeline-ui` | `:80` | Web dashboard for managing runs/experiments |
| **workflow-controller** | `workflow-controller` | — | Argo controller; orchestrates pipeline pods |
| **metadata-grpc-deployment** | `metadata-grpc-deployment` | `:8080` | ML Metadata (MLMD) gRPC server; records executions and artifacts |
| **metadata-envoy-deployment** | `metadata-envoy-deployment` | `:9090` | Envoy proxy in front of MLMD |
| **metadata-writer** | `metadata-writer` | — | Writes workflow events to MLMD |
| **SeaweedFS** | `seaweedfs` | `:8333` (S3), `:9000` compat | Distributed object storage; stores artifacts and logs |
| **minio-service** | (alias for SeaweedFS) | `:9000→8333` | S3-compatible endpoint used by Argo and KFP launcher |
| **MySQL** | `mysql` | `:3306` | Relational DB for pipeline definitions, run records, cache |
| **cache-server** | `cache-server` | `:443` | Intercepts step executions; reuses cached outputs |
| **cache-deployer-deployment** | `cache-deployer` | — | Manages cache-server TLS certificates |
| **ml-pipeline-persistenceagent** | `ml-pipeline-persistenceagent` | — | Syncs Argo Workflow state back into the pipeline DB |
| **ml-pipeline-scheduledworkflow** | `ml-pipeline-scheduledworkflow` | — | Handles cron-based recurring pipeline runs |
| **ml-pipeline-viewer-crd** | `ml-pipeline-viewer-crd` | — | Renders visualizations for pipeline runs |
| **ml-pipeline-visualizationserver** | `ml-pipeline-visualizationserver` | `:8888` | Generates ROC/confusion matrix charts |
| **controller-manager** | `controller-manager` | `:443` | KFP CRD controller |

### ConfigMaps

| ConfigMap | Purpose |
|---|---|
| `workflow-controller-configmap` | Argo default artifact repo, executor settings, pod security patches |
| `pipeline-install-config` | Bucket name, DB host/port, cache config |
| `kfp-launcher` | Default pipeline root for artifact URIs |
| `metadata-grpc-configmap` | MLMD gRPC host/port (injected into step pods) |

### Persistent Volumes

| PVC | Capacity | Used by |
|---|---|---|
| `seaweedfs-pvc` | 20 Gi | SeaweedFS object storage data |
| `mysql-pv-claim` | 20 Gi | MySQL database data |

---

## Pipelines

### Hello World Pipeline

**Source:** `hello_pipeline.py`  
**Compiled YAML:** `hello_world_pipeline.yaml`

#### Description

A minimal single-step pipeline that demonstrates the KFP v2 SDK usage: defining a Python function as a component and wiring it into a pipeline DAG.

#### Component

```python
@dsl.component
def say_hello(name: str) -> str:
    hello_text = f'Hello, {name}!'
    print(hello_text)
    return hello_text
```

- **Base image:** `python:3.8`
- **Input:** `name` (STRING)
- **Output:** greeting string

#### DAG

```
[Input: recipient]
       │
       ▼
  ┌──────────┐
  │ say-hello│  ──▶  [Output: greeting string]
  └──────────┘
```

#### Pipeline Parameters

| Parameter | Type | Default |
|---|---|---|
| `recipient` | `str` | `"World"` |

#### Example Output

```
Hello, Atul!
```

---

### Iris ML Pipeline

**Source:** `iris_pipeline.py`  
**Compiled via:** `kfp.compiler.Compiler().compile(iris_pipeline, "iris_pipeline.yaml")`

#### Description

A two-step ML training pipeline on the Iris dataset. Demonstrates multi-step parameter passing without file artifacts (features and labels passed as inline parameters).

#### Components

**1. `load_data`**
- **Base image:** `python:3.8-slim`
- **Packages:** `pandas`, `scikit-learn`
- Loads `sklearn.datasets.load_iris`
- **Output:** `features` (List[List[float]]), `labels` (List[int])

**2. `train_model`**
- **Base image:** `python:3.8-slim`
- **Packages:** `scikit-learn`
- Trains a `RandomForestClassifier` with 80/20 train-test split
- **Input:** `features`, `labels` (from `load_data`)
- **Output:** `accuracy` (float)

#### DAG

```
        ┌───────────┐
        │ load_data │
        └─────┬─────┘
     features │ labels
              ▼
       ┌─────────────┐
       │ train_model │  ──▶  [Output: accuracy (float)]
       └─────────────┘
```

---

## Pipeline Execution Flow

Each pipeline run goes through the following sequence of Kubernetes pods:

```
1. API server receives run request
       │
       ▼
2. Argo Workflow CRD is created in k8s
       │
       ▼
3. workflow-controller schedules pods per template
       │
       ├──▶ system-dag-driver pod (kfp-driver)
       │       - Registers DAG execution in MLMD
       │       - Resolves step input parameters
       │       - Checks cache (via cache-server)
       │
       └──▶ For each step:
               │
               ├──▶ system-container-driver pod (kfp-driver)
               │         - Resolves task-level inputs
               │         - Generates pod-spec-patch for executor
               │
               └──▶ system-container-impl pod
                         ┌──────────────────────────────────┐
                         │ init container: argoexec         │
                         │ init container: kfp-launcher     │
                         │   (copies /kfp-launcher/launch)  │
                         │ main container: user image       │
                         │   (python:3.8 / python:3.8-slim) │
                         │   runs component logic           │
                         │ wait container: argoexec         │
                         │   uploads outputs to SeaweedFS   │
                         └──────────────────────────────────┘
                                      │
                                      ▼
                         Artifacts written to SeaweedFS
                         Outputs published to MLMD
                         DAG state updated in MySQL
```

---

## Storage & Artifact Path

Artifacts (logs, outputs) are stored in **SeaweedFS** using the S3 API.

| Setting | Value |
|---|---|
| S3 Endpoint (Argo logs) | `minio-service.kubeflow:9000` |
| S3 Endpoint (KFP launcher) | `seaweedfs.kubeflow:9000` → targets port `8333` |
| Bucket | `mlpipeline` |
| Artifact path (v2) | `minio://mlpipeline/v2/artifacts/<pipeline>/<run-id>/<step>/<exec-id>/` |
| Log path (Argo) | `private-artifacts/<namespace>/<workflow>/<date>/<pod-name>/` |
| Auth secret | `mlpipeline-minio-artifact` (keys: `accesskey`, `secretkey`) |

---

## Known Fixes Applied

The following cluster-level fixes were made during initial setup to get pipelines working on Minikube.

### 1. `workflow-controller-configmap` — podSpecPatch for Argo executor security

**Problem:** KFP-generated Argo Workflow templates set `runAsNonRoot: true` at the pod and template level. Argo's `init` and `wait` containers (`quay.io/argoproj/argoexec:v3.7.3`) run as root, causing `Init:CreateContainerConfigError`.

**Fix:** Added a global `podSpecPatch` to `workflowDefaults` in the configmap:

```yaml
workflowDefaults: |
  spec:
    podSpecPatch: |
      initContainers:
      - name: init
        securityContext:
          runAsNonRoot: false
          runAsUser: 0
      containers:
      - name: wait
        securityContext:
          runAsNonRoot: false
          runAsUser: 0
```

After patching, restart the controller:

```bash
kubectl rollout restart deployment workflow-controller -n kubeflow
```

### 2. SeaweedFS Service — add port 9000 compatibility mapping

**Problem:** KFP launcher resolves the S3 endpoint as `seaweedfs.kubeflow:9000`. The `seaweedfs` Service only exposed port `8333` for S3; port `9000` was missing, causing `dial tcp: i/o timeout` on every artifact upload.

**Fix:** Added a compatibility port to the `seaweedfs` Service:

```bash
kubectl patch svc seaweedfs -n kubeflow --type='json' \
  -p='[{"op":"add","path":"/spec/ports/-","value":{"name":"s3-compat-9000","port":9000,"protocol":"TCP","targetPort":8333}}]'
```

---

## Running the Pipelines

### Prerequisites

```bash
# Create and activate the virtual environment
python3 -m venv ~/.kfp
source ~/.kfp/bin/activate
pip install kfp==2.9.0
```

### Step 1 — Compile the pipeline

```bash
# Hello world
python hello_pipeline.py
# Output: hello_world_pipeline.yaml

# Iris ML
python iris_pipeline.py
# Output: iris_pipeline.yaml
```

### Step 2 — Port-forward the KFP API

```bash
kubectl port-forward -n kubeflow svc/ml-pipeline 8888:8888
```

### Step 3 — Submit a run

```python
from kfp import Client

client = Client(host='http://127.0.0.1:8888')

# Hello world
exp = client.create_experiment(name='hello-experiment')
run = client.run_pipeline(
    experiment_id=exp.experiment_id,
    job_name='hello-run',
    pipeline_package_path='hello_world_pipeline.yaml',
    params={'recipient': 'Atul'}
)
print(run.run_id)

# Iris ML
run = client.run_pipeline(
    experiment_id=exp.experiment_id,
    job_name='iris-run',
    pipeline_package_path='iris_pipeline.yaml'
)
```

Or use the KFP CLI:

```bash
kfp run create \
  --experiment-name hello-experiment \
  --run-name hello-run \
  --package-file hello_world_pipeline.yaml \
  --param recipient=Atul
```

### Step 4 — Monitor pods

```bash
# Watch pipeline pods
kubectl get pods -n kubeflow -w | grep -E 'hello-world|iris'

# Follow logs of the executing step
kubectl logs -n kubeflow <system-container-impl-pod-name> -c main -f
```

---

## Accessing the UI

```bash
kubectl port-forward -n kubeflow svc/ml-pipeline-ui 8080:80
```

Open [http://localhost:8080](http://localhost:8080) in your browser.

The UI provides:
- Experiment and run management
- Step-by-step execution graph with status
- Artifact viewer (logs, metrics, parameters)
- Workflow YAML inspection
