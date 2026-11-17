# Connection Pooling, Read Replicas & Scaling

*Backend & Production | short notes with black-and-white diagrams (Mermaid)*

## 1. Connection pooling

**Idea:** keep a set of already-open DB connections and reuse them, instead of opening and closing one per request.

**Why:** opening a connection costs a TCP handshake, TLS and authentication. A DB server also caps connections (Postgres default `max_connections` = 100), and each one uses real memory on the server.

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#ffffff','primaryColor':'#ffffff','primaryTextColor':'#000000','primaryBorderColor':'#000000','lineColor':'#000000','secondaryColor':'#ffffff','tertiaryColor':'#ffffff','clusterBkg':'#ffffff','clusterBorder':'#000000'}}}%%
flowchart LR
  subgraph A["WITHOUT POOL"]
    R1["Request 1"] -->|"open, auth, close"| DB1[("Database")]
    R2["Request 2"] -->|"open, auth, close"| DB1
  end
  subgraph B["WITH POOL"]
    Q1["Request 1"] --> P["Pool of open connections"]
    Q2["Request 2"] --> P
    P -->|"reused"| DB2[("Database")]
  end
  classDef w fill:#ffffff,stroke:#000000,color:#000000
  classDef k fill:#000000,stroke:#000000,color:#ffffff
  class R1,R2,Q1,Q2,P w
  class DB1,DB2 k
  style A fill:#ffffff,stroke:#000000,color:#000000
  style B fill:#ffffff,stroke:#000000,color:#000000
```

### 1.1 Checkout lifecycle

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#ffffff','primaryColor':'#ffffff','primaryTextColor':'#000000','primaryBorderColor':'#000000','lineColor':'#000000','secondaryColor':'#ffffff','tertiaryColor':'#ffffff','actorBkg':'#ffffff','actorBorder':'#000000','actorTextColor':'#000000','actorLineColor':'#000000','signalColor':'#000000','signalTextColor':'#000000','noteBkgColor':'#ffffff','noteTextColor':'#000000','noteBorderColor':'#000000','labelBoxBkgColor':'#ffffff','labelBoxBorderColor':'#000000','labelTextColor':'#000000','loopTextColor':'#000000'}}}%%
sequenceDiagram
  participant App
  participant Pool
  participant DB
  App->>Pool: checkout
  alt idle connection free
    Pool-->>App: reuse it
  else below pool_size + max_overflow
    Pool->>DB: open new connection
    Pool-->>App: new connection
  else pool exhausted
    Pool-->>App: wait pool_timeout, then TimeoutError
  end
  App->>DB: run query
  App->>Pool: return connection (stays open)
```

### 1.2 SQLAlchemy pool settings

| Setting | Default | Meaning |
|---|---|---|
| `pool_size` | 5 | Connections kept open permanently |
| `max_overflow` | 10 | Extra temporary connections allowed above `pool_size` |
| `pool_timeout` | 30 s | How long a request waits for a free connection before erroring |
| `pool_recycle` | off | Replace connections older than N seconds (avoids stale ones) |
| `pool_pre_ping` | off | Test a connection before use; reconnect if dead |

**Budget rule:** `workers x (pool_size + max_overflow)` must stay below the DB `max_connections`. Example: 4 workers x (10 + 5) = 60, under 100. Each worker process has its own pool, so more workers means more connections.

### 1.3 PgBouncer (external pooler)

A separate proxy between your apps and Postgres. Many app connections go in, few DB connections come out.

| Mode | Connection held for | Note |
|---|---|---|
| Session | Whole client session | Safest, least saving |
| Transaction | One transaction | Most common; can break session state (`SET`, advisory locks, older prepared statements) |
| Statement | One statement | No multi-statement transactions |

## 2. Read replicas

**Idea:** one **primary** takes all writes. **Replicas** are copies kept up to date by replication and serve read-only queries. This scales reads, not writes.

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#ffffff','primaryColor':'#ffffff','primaryTextColor':'#000000','primaryBorderColor':'#000000','lineColor':'#000000','secondaryColor':'#ffffff','tertiaryColor':'#ffffff'}}}%%
flowchart TB
  C["Client"] --> API["FastAPI app"]
  API -->|"writes: INSERT UPDATE DELETE"| P[("Primary")]
  API -->|"reads: SELECT"| R1[("Replica 1")]
  API -->|"reads: SELECT"| R2[("Replica 2")]
  P -.->|"async replication"| R1
  P -.->|"async replication"| R2
  classDef w fill:#ffffff,stroke:#000000,color:#000000
  classDef k fill:#000000,stroke:#000000,color:#ffffff
  class C,API w
  class P,R1,R2 k
```

### 2.1 The catch: replication lag

Replication is usually asynchronous, so a replica can be a moment behind the primary. A user who just wrote data may then read old data from a replica ("read-your-own-writes" problem).

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#ffffff','primaryColor':'#ffffff','primaryTextColor':'#000000','primaryBorderColor':'#000000','lineColor':'#000000','secondaryColor':'#ffffff','tertiaryColor':'#ffffff','actorBkg':'#ffffff','actorBorder':'#000000','actorTextColor':'#000000','actorLineColor':'#000000','signalColor':'#000000','signalTextColor':'#000000','noteBkgColor':'#ffffff','noteTextColor':'#000000','noteBorderColor':'#000000'}}}%%
sequenceDiagram
  participant U as User
  participant A as App
  participant P as Primary
  participant R as Replica
  U->>A: update profile
  A->>P: write
  P-->>A: ok
  P-->>R: replicate (async, takes time)
  U->>A: view profile right away
  A->>R: read
  R-->>A: OLD data
  Note over U,R: replica has not caught up yet
```

**Fixes:** read from the primary right after a write, or for a short window after (sticky reads); send only lag-tolerant reads (feeds, reports, search) to replicas; monitor replica lag.

### 2.2 Routing reads and writes in FastAPI

```python
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# URLs come from BaseSettings, never hardcoded
write_engine = create_async_engine(settings.primary_url, pool_size=10, max_overflow=5, pool_pre_ping=True)
read_engine = create_async_engine(settings.replica_url, pool_size=10, max_overflow=5, pool_pre_ping=True)

WriteSession = async_sessionmaker(write_engine, expire_on_commit=False)
ReadSession = async_sessionmaker(read_engine, expire_on_commit=False)


async def get_write_db():
    async with WriteSession() as session:
        yield session


async def get_read_db():
    async with ReadSession() as session:
        yield session


app = FastAPI()


@app.get("/items")                                  # SELECT -> replica
async def list_items(db=Depends(get_read_db)): ...


@app.post("/items")                                 # INSERT -> primary
async def create_item(db=Depends(get_write_db)): ...
```

## 3. Which scaling tool when

```mermaid
%%{init: {'theme':'base','themeVariables':{'background':'#ffffff','primaryColor':'#ffffff','primaryTextColor':'#000000','primaryBorderColor':'#000000','lineColor':'#000000','secondaryColor':'#ffffff','tertiaryColor':'#ffffff'}}}%%
flowchart TD
  S["Database is slow"] --> Q1{"Slow queries or missing indexes?"}
  Q1 -->|"yes"| F1["Fix queries, add indexes"]
  Q1 -->|"no"| Q2{"Too many connections or slow connects?"}
  Q2 -->|"yes"| F2["Connection pool or PgBouncer"]
  Q2 -->|"no"| Q3{"Mostly reads?"}
  Q3 -->|"yes"| F3["Cache with Redis, then read replicas"]
  Q3 -->|"no"| Q4{"Write heavy or data too big?"}
  Q4 -->|"yes"| F4["Scale up, partition, or shard"]
  classDef w fill:#ffffff,stroke:#000000,color:#000000
  classDef k fill:#000000,stroke:#000000,color:#ffffff
  class S,Q1,Q2,Q3,Q4 w
  class F1,F2,F3,F4 k
```

| Tool | Fixes | Does not fix |
|---|---|---|
| Indexes / query tuning | Slow queries | Connection limits |
| Connection pool | Connect cost, too many connections | Slow queries |
| Caching (Redis) | Repeated identical reads | Writes |
| Read replicas | Read load on the primary | Write load, replication lag |
| Sharding | Write load, data size | Complexity (cross-shard queries, harder ops), so last resort |

## 4. AI and agent relevance

- **Do not hold a DB session open while waiting on an LLM call.** Slow model responses pin connections, the pool empties, and unrelated requests start timing out. Open a short session, read or write, close it, then call the model.
- **Pool exhaustion is a denial-of-service route.** A flood of slow requests can drain the pool without any crash. Pair pool limits with rate limiting.
