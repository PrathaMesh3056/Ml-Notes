# Multi-stage Builds & NGINX Configuration

---

## Table of Contents
1. [Multi-stage Docker Builds](#1-multi-stage-docker-builds)
2. [Why Multi-stage Builds Matter](#2-why-multi-stage-builds-matter)
3. [NGINX Basics](#3-nginx-basics)
4. [NGINX as Reverse Proxy](#4-nginx-as-reverse-proxy)
5. [Common Patterns](#5-common-patterns)

---

## 1. Multi-stage Docker Builds

A multi-stage build splits a Dockerfile into multiple `FROM` stages. Only the **final stage** is shipped as the resulting image — earlier stages are used purely to produce artifacts (compiled code, build output) that get copied forward.

```dockerfile
# STAGE 1 — build (large image, has compilers/build tools)
FROM node:20 AS builder
WORKDIR /app
COPY . .
RUN npm install && npm run build

# STAGE 2 — runtime (slim image, only this one ships)
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

**Flow:**
```
STAGE 1 (builder)              STAGE 2 (runtime)
┌──────────────────┐           ┌──────────────────┐
│ FROM node AS      │           │ FROM nginx:alpine │
│ builder            │  copy    │                    │
│                    │  only    │ COPY --from=builder│
│ npm install        │  built   │   /app/dist →      │
│ npm run build       │  files   │   nginx html dir   │
│                    │ ───────► │                    │
│ (node_modules,     │           │ (no node_modules,  │
│  build tools stay  │           │  no build tools —  │
│  here, discarded)  │           │  just static files │
└──────────────────┘           │  + nginx)           │
                                 └──────────────────┘
```

---

## 2. Why Multi-stage Builds Matter

| Without multi-stage | With multi-stage |
|---|---|
| Final image includes `node_modules`, build tools, source code | Final image only has the built output + runtime (e.g. nginx) |
| Image size: often 500MB-1GB+ | Image size: often 20-50MB (alpine-based) |
| Larger attack surface (unused compilers, dev dependencies shipped to production) | Smaller attack surface — nothing unnecessary in the container |
| Slower to pull/deploy | Faster to pull/deploy, faster cold starts |

**Key syntax:**
```dockerfile
FROM <image> AS <stage_name>        # name a stage
COPY --from=<stage_name> <src> <dst>  # copy artifacts from a named stage into the current one
```

You can have more than 2 stages (e.g., a separate "test" stage that runs in CI but is never shipped).

---

## 3. NGINX Basics

NGINX is a web server / reverse proxy. Its config is organized into `server` blocks, each containing `location` blocks that match request paths.

```nginx
server {
    listen 80;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
}
```

**Key directives:**
- `listen` — port NGINX listens on
- `location <path>` — matches incoming request paths, decides how to handle them
- `root` — directory where static files are served from
- `index` — default file to serve for a directory request
- `try_files` — fallback chain: try the exact file, then a directory, then fall back (commonly used for single-page apps like React/Vue, so client-side routing works on refresh)

---

## 4. NGINX as Reverse Proxy

NGINX can forward requests to another service (e.g., your FastAPI/Node backend) instead of serving files directly — this is a **reverse proxy**.

```nginx
location /api/ {
    proxy_pass http://backend:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

**Flow:**
```
Client ──► NGINX (port 80) ──► location /api/ ──► proxy_pass ──► backend:8000
```

**Why this matters:** NGINX becomes the single entry point — it can serve your frontend's static files AND forward API requests to a separate backend container, all on one port (80/443), while the backend itself stays unexposed to the outside world.

**Key directives:**
- `proxy_pass` — forwards the request to another address (can be another container, by service name, in Docker Compose/Kubernetes)
- `proxy_set_header` — preserves original client request info (IP, host) since the backend now sees NGINX as the caller, not the original client

---

## 5. Common Patterns

**Full example — frontend + API behind one NGINX:**

```nginx
server {
    listen 80;

    # Serve built frontend (React/Vue/etc.)
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    # Proxy API calls to backend container
    location /api/ {
        proxy_pass http://backend:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Docker Compose context (how this typically gets wired):**
```yaml
services:
  frontend:
    build: ./frontend   # multi-stage build, produces nginx image
    ports:
      - "80:80"
  backend:
    build: ./backend
    expose:
      - "8000"   # not published to host, only reachable inside the compose network
```

This way, `backend` is never directly exposed to the internet — only NGINX is, and it proxies internally.

---

**End of Document**
