# Gunicorn/Uvicorn Workers & CI/CD Pipelines

---

## Table of Contents
1. [Why Workers Exist](#1-why-workers-exist)
2. [Uvicorn — ASGI Server](#2-uvicorn--asgi-server)
3. [Gunicorn + Uvicorn Workers](#3-gunicorn--uvicorn-workers)
4. [Choosing Worker Count](#4-choosing-worker-count)
5. [Production Command](#5-production-command)
6. [CI/CD Pipelines — Core Concepts](#6-cicd-pipelines--core-concepts)
7. [GitHub Actions Example](#7-github-actions-example)
8. [CI/CD + Docker Together](#8-cicd--docker-together)

---

## 1. Why Workers Exist

A single running Python process handles requests **one at a time per process** (even with `async def`, a single process is still one OS process — async helps with I/O waiting, not with using multiple CPU cores).

```
1 process, 1 core used  →  requests queue up under load
N processes, N cores used →  requests spread across processes
```

**Worker** = a separate process running a copy of your app, so multiple requests can be handled truly in parallel (across CPU cores), not just concurrently (within one core via async).

---

## 2. Uvicorn — ASGI Server

Uvicorn is the server that actually runs your FastAPI app and speaks the ASGI protocol (the async version of WSGI).

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

This runs **one process**. Fine for development, not ideal alone for production — no auto-restart on crash, no multi-process management.

Uvicorn does support running multiple workers itself:
```bash
uvicorn main:app --workers 4
```
But Gunicorn is generally preferred to manage workers in production because of its more mature process management (auto-restart crashed workers, graceful reloads, logging).

---

## 3. Gunicorn + Uvicorn Workers

Gunicorn is a battle-tested **process manager** (originally built for WSGI/Flask-style apps). It doesn't natively understand async apps — so you run it with **Uvicorn's worker class**, combining Gunicorn's process management with Uvicorn's ASGI serving.

```bash
gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

**What's happening:**
```
┌─────────────────────────────────────────────┐
│               Gunicorn (master)               │
│   manages worker processes, restarts crashed  │
│   ones, handles graceful reloads              │
└───────────────┬───────────────────────────────┘
                 │ spawns
     ┌───────────┼───────────┬───────────┐
     ▼           ▼           ▼           ▼
 ┌────────┐ ┌────────┐  ┌────────┐  ┌────────┐
 │Worker 1│ │Worker 2│  │Worker 3│  │Worker 4│
 │(Uvicorn│ │(Uvicorn│  │(Uvicorn│  │(Uvicorn│
 │process)│ │process)│  │process)│  │process)│
 └────────┘ └────────┘  └────────┘  └────────┘
   each runs a full copy of your FastAPI app
```

If Worker 2 crashes, Gunicorn detects it and spawns a replacement — your app keeps serving requests on the other 3 workers in the meantime.

---

## 4. Choosing Worker Count

Common starting formula:
```
workers = (2 x CPU_cores) + 1
```

Example: 4-core machine → `(2 × 4) + 1 = 9` workers (rule of thumb, not an exact science — tune based on actual load testing).

Too few workers → requests queue under load.
Too many workers → excessive memory usage, context-switching overhead.

---

## 5. Production Command

```bash
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile -
```

- `--timeout 120` — kill and restart a worker stuck on a request longer than 120s
- `--access-logfile -` — log access logs to stdout (so Docker/container logs pick them up)

This is usually the final `CMD` in a production Dockerfile's runtime stage.

---

## 6. CI/CD Pipelines — Core Concepts

**CI (Continuous Integration):** Automatically build + test your code every time you push, catching bugs before merge.

**CD (Continuous Deployment/Delivery):** Automatically deploy that tested code to a server/environment once it passes CI.

```
Developer pushes code
        │
        ▼
┌─────────────────┐
│   CI: Build      │  install deps, build Docker image
├─────────────────┤
│   CI: Test       │  run pytest, lint (ruff/mypy)
├─────────────────┤
│   CI: Gate       │  fail pipeline if tests fail — nothing deploys
├─────────────────┤
│   CD: Deploy     │  push image to registry, deploy to server
└─────────────────┘
```

**Why it matters:** Removes manual "build it, test it, upload it" steps — every push is automatically validated and (optionally) shipped, reducing human error.

---

## 7. GitHub Actions Example

A pipeline is defined in `.github/workflows/<name>.yml`.

```yaml
name: CI Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run lint
        run: ruff check .

      - name: Run tests
        run: pytest
```

**Key terms:**
- `on:` — what triggers the pipeline (push, pull_request, schedule, etc.)
- `jobs:` — one or more independent tasks (can run in parallel)
- `steps:` — sequential actions within a job
- `uses:` — reuses a pre-built action (like `actions/checkout` to pull your repo code)
- `run:` — runs a shell command directly

If any step fails (e.g., a test fails), the whole job is marked failed — this is the **gate** that prevents broken code from merging/deploying.

---

## 8. CI/CD + Docker Together

A common full pipeline builds the Docker image and pushes it to a registry (Docker Hub, GitHub Container Registry) after tests pass:

```yaml
jobs:
  build-and-push:
    runs-on: ubuntu-latest
    needs: test   # only runs if 'test' job succeeded
    steps:
      - uses: actions/checkout@v4

      - name: Log in to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: myusername/myapp:latest
```

**Key points:**
- `needs: test` — this job waits for the `test` job to pass first (the CI gate in action)
- `secrets.DOCKER_USERNAME` / `secrets.DOCKER_PASSWORD` — stored securely in GitHub repo settings (Settings → Secrets), never hardcoded
- After this, a deployment step (SSH into server, pull new image, restart container) would typically follow — often via another job or a tool like Watchtower/Kubernetes rolling update

---

**Full flow, end to end:**
```
git push → GitHub Actions triggers
    │
    ├─► Run tests (pytest, ruff)
    │        │ pass
    │        ▼
    ├─► Build Docker image (multi-stage, from earlier topic)
    │        │
    │        ▼
    ├─► Push image to registry
    │        │
    │        ▼
    └─► Deploy (pull image on server, restart with Gunicorn+Uvicorn workers)
```

---

**End of Document**
