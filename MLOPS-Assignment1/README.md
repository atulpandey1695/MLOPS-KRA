# MLOPS-Assignment1

Kidney CT scan tumor classification service built with Flask and TensorFlow. This repo includes a production-oriented inference container, GitHub Actions CI for image build and push, and a local Minikube deployment script.

## Project Scope

- Inference API: [app.py](/data/workspace/MLOPS-assignment1/MLOPS-Assignment1/app.py)
- Model weights loaded from [model/model.h5](/data/workspace/MLOPS-assignment1/MLOPS-Assignment1/model/model.h5)
- Prediction pipeline in [src/cnnClassifier/pipeline/prediction.py](/data/workspace/MLOPS-assignment1/MLOPS-Assignment1/src/cnnClassifier/pipeline/prediction.py)
- Kubernetes manifests in [k8s/deployment.yaml](/data/workspace/MLOPS-assignment1/MLOPS-Assignment1/k8s/deployment.yaml) and [k8s/service.yaml](/data/workspace/MLOPS-assignment1/MLOPS-Assignment1/k8s/service.yaml)

## API

- `GET /` returns the HTML UI
- `POST /predict` accepts JSON with an `image` field containing base64 image content

Example payload:

```json
{
	"image": "<base64-image-string>"
}
```

## Local Docker Run

```bash
docker build -t kidney-ct-classifier:local .
docker run -p 8080:8080 kidney-ct-classifier:local
```

Open `http://localhost:8080`.

## GitHub Actions

Workflow file: [.github/workflows/ci-cd.yml](/data/workspace/MLOPS-assignment1/MLOPS-Assignment1/.github/workflows/ci-cd.yml)

CI:
- Lints Python code
- Builds the inference image
- Pushes image to Docker Hub on `main`

Required GitHub secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

## Minikube Deployment

Deployment to Minikube is local-only. GitHub-hosted runners cannot reach a Minikube cluster running on your machine.

Prerequisites on your local machine:

- Docker installed and running
- Minikube installed and started
- Kubectl installed

Start Minikube if needed:

```bash
minikube start
kubectl config use-context minikube
```

Deploy the latest pushed image locally:

```bash
chmod +x scripts/deploy_minikube.sh
./scripts/deploy_minikube.sh
```

Use a specific image tag if needed:

```bash
IMAGE=atul1695/kidney-ct-classifier:sha-<commit-sha> ./scripts/deploy_minikube.sh
```

Access the app:

```bash
minikube service kidney-ct-classifier-svc -n kidney-ct
```

The script pulls the image, loads it into Minikube, applies the Kubernetes manifests, updates the Deployment image, and waits for rollout.