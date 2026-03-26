# LangGraph AI Agents API

FastAPI service exposing 5 LangGraph-based agents. The app runs locally with Docker and in Kubernetes (Minikube).

## What This Project Does

- `Agent Bot`: stateless chat endpoint
- `Memory Agent`: session-based chat with history
- `ReAct Agent`: math solver with tools (`add`, `subtract`, `multiply`)
- `Drafter Agent`: document drafting assistant
- `RAG Agent`: question-answering over `Agents/Stock_Market_Performance_2024.pdf`

## Architecture (High Level)

```text
Client (curl/Postman/UI)
        |
        v
FastAPI (app.py)
        |
        +--> Agent Bot Graph
        +--> Memory Agent Graph (in-memory sessions)
        +--> ReAct Graph + Tools
        +--> Drafter Graph + Tools
        +--> RAG Graph -> PDF Loader -> Text Splitter -> Chroma -> Retriever
        |
        v
LLM / Embeddings via OpenRouter-compatible API
```

## Request Flow

1. Client sends HTTP request to a route in `app.py`.
2. Route maps request to the corresponding LangGraph workflow.
3. Workflow may call tools (ReAct/Drafter/RAG).
4. For RAG, relevant PDF chunks are retrieved from Chroma.
5. Final response is returned as JSON.

## Prerequisites

- Docker
- kubectl
- Minikube
- Python 3.12+ (only if running directly without Docker)
- OpenRouter/OpenAI-compatible API key

## Environment Setup

Create `.env` in project root:

```bash
OPENAI_API_KEY="sk-or-v1-your-key"
OPENAI_API_BASE="https://openrouter.ai/api/v1"
```

Optional (defaults are already set in app/config):

```bash
MODEL_NAME="gpt-4o-mini"
EMBEDDING_MODEL="text-embedding-3-small"
APP_PORT="8000"
```

## Run The Application

### Option A: One-Command Kubernetes Deploy (Recommended)

```bash
cd Assignment_agenticAi
chmod +x deploy.sh
./deploy.sh
kubectl port-forward svc/assignment-agentic-ai-service 8080:80
```

API base URL: `http://localhost:8080`

Swagger UI: `http://localhost:8080/docs`

### Option B: Local Python Run

```bash
cd Assignment_agenticAi
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

API base URL: `http://localhost:8000`

Swagger UI: `http://localhost:8000/docs`

## API Endpoints

- `POST /api/agent-bot/chat`
- `POST /api/memory/chat`
- `POST /api/react/solve`
- `POST /api/drafter/chat`
- `POST /api/rag/query`
- `GET /health`

## Quick Test Examples

Set base URL (use `8080` for Kubernetes, `8000` for local run):

```bash
export BASE_URL="http://localhost:8080"
```

If you get no output from `curl` and exit code `3`, `BASE_URL` is usually empty or malformed.
Check with:

```bash
echo "$BASE_URL"
```

Agent Bot:

```bash
curl -s -X POST $BASE_URL/api/agent-bot/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello!"}'
```

New question example:

```bash
curl -s -X POST $BASE_URL/api/agent-bot/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain Kubeflow in simple terms and how it helps MLOps pipelines."}'
```

Memory Agent:

```bash
curl -s -X POST $BASE_URL/api/memory/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "demo-1", "message": "My name is Atul."}'
```

ReAct Agent:

```bash
curl -s -X POST $BASE_URL/api/react/solve \
  -H "Content-Type: application/json" \
  -d '{"message": "What is 35 + 17?"}'
```

Drafter Agent:

```bash
curl -s -X POST $BASE_URL/api/drafter/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "draft-1", "message": "Write a short meeting reminder email.", "document_content": ""}'
```

RAG Agent:

```bash
curl -s -X POST $BASE_URL/api/rag/query \
  -H "Content-Type: application/json" \
  -d '{"message": "What was the stock market performance in 2024?"}'
```

## Operations

Redeploy after code changes:

```bash
eval $(minikube docker-env)
docker build -t assignment-agentic-ai:latest .
kubectl rollout restart deployment/assignment-agentic-ai-deployment
kubectl rollout status deployment/assignment-agentic-ai-deployment
```

Destroy deployment:

```bash
./destroy.sh
```

## Troubleshooting

```bash
kubectl get pods -l app=assignment-agentic-ai
kubectl describe pod <pod-name>
kubectl logs <pod-name>
kubectl get svc assignment-agentic-ai-service
```
