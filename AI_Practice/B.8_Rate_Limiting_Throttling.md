# Rate Limiting & Throttling

*Backend & Production | API key and infrastructure-level limits*

## 1. What rate limiting is and why it matters

Rate limiting caps how many requests a client can make in a time window. When the cap is hit, the server rejects the request with HTTP 429. Throttling is the softer cousin: instead of rejecting, the server slows the client down (queues, delays, or lowers priority). Rate limiting protects availability (one client cannot starve the rest), budget (paid downstream calls such as LLM APIs), and security (brute force, scraping, credential stuffing).

| Term | Behaviour | Typical use |
|---|---|---|
| Rate limiting | Reject excess requests (429) | Public APIs, login endpoints |
| Throttling | Delay or slow excess requests | Background jobs, batch uploads |
| Quota | Total allowance per day/month | Plan tiers, billing |
| Concurrency limit | Cap on in-flight requests | Slow or expensive endpoints |

## 2. The two layers

Use both layers. Each catches abuse the other cannot see.

| | Infrastructure-level | API key / application-level |
|---|---|---|
| Where | CDN, WAF, load balancer, gateway (Cloudflare, NGINX, Envoy, Kong) | App code or gateway plugin with shared state (Redis) |
| Identifies by | IP, ASN, geo, TLS fingerprint, headers | API key, user ID, tenant, plan tier |
| Stops | DDoS, scraping, brute force, volumetric abuse | Quota abuse, noisy neighbours, leaked keys, cost overruns |
| Weakness | Shared IPs (NAT) cause false positives; attackers rotate IPs | Nothing happens before auth, so unauthenticated routes stay open |
| Cost to enforce | Very cheap (rejected at the edge) | One state lookup per request |

Rule of thumb: infrastructure limits protect availability, key-level limits protect business logic and budget.

### 2.1 What to key the limit on

| Key | Purpose |
|---|---|
| Per API key | Primary control; tiered by plan |
| Per IP | Pre-auth control for login, signup, password reset |
| Per endpoint | Stricter limits on expensive or sensitive routes (auth, search, export, upload) |
| Per tenant / org | Stops one customer using many keys to dodge limits |
| Global | Circuit breaker for the whole system |

## 3. Algorithms

| Algorithm | How it works | Pros | Cons |
|---|---|---|---|
| Fixed window | Counter per window, resets at boundary | Simplest, cheap | Up to 2x burst at the window edge |
| Sliding window log | Store timestamps, count those in the last N seconds | Exact | Memory grows with traffic |
| Sliding window counter | Weighted blend of current and previous window | Smooth, low memory | Approximate |
| Token bucket | Tokens refill at a steady rate; each request spends one | Allows bursts, enforces average rate | Two values to tune |
| Leaky bucket | Requests drain at a constant rate | Very smooth output | No bursts |

Token bucket is the usual default for APIs. The bucket holds up to `capacity` tokens and refills at `rate` tokens per second. A client can burst up to capacity, then is held to the refill rate.

### 3.1 Token bucket in plain Python

```python
import math
import time


class TokenBucket:
    """Allows bursts up to 'capacity', average rate of 'rate' per second."""

    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.updated = time.monotonic()  # monotonic: immune to clock changes

    def _refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    def allow(self, cost: float = 1) -> bool:
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def retry_after(self, cost: float = 1) -> int:
        """Seconds until 'cost' tokens are available (for the Retry-After header)."""
        missing = max(0.0, cost - self.tokens)
        return math.ceil(missing / self.rate)
```

This version lives in one process. With several workers or servers, each would keep its own counters and the real limit would multiply (100 per minute across 10 servers becomes 1,000). Shared state is needed, which is where Redis comes in.

## 4. Shared state with Redis

Redis suits rate limiting because operations are fast, atomic, and keys expire automatically. The common mistake is read-then-write (GET, check, SET), which races under concurrency. Use an atomic operation instead.

### 4.1 Fixed window with an atomic Lua script

```python
import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# INCR and EXPIRE run as one atomic unit inside Redis
LUA_FIXED_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def is_allowed(client_id: str, limit: int = 10, window: int = 60) -> bool:
    key = f"rl:{client_id}:{int(time.time() // window)}"
    count = r.eval(LUA_FIXED_WINDOW, 1, key, window)
    return count <= limit
```

Why a script: if INCR succeeds but the process dies before EXPIRE, the key never expires and that client is blocked forever. Running both inside Redis removes that gap.

## 5. FastAPI integration

A dependency keeps the limit visible on the route and lets you apply different limits per endpoint. A middleware applies one rule globally. Both should return 429 with a `Retry-After` header.

```python
from fastapi import Depends, FastAPI, HTTPException, Request

app = FastAPI()
buckets: dict[str, TokenBucket] = {}


def rate_limit(request: Request) -> None:
    # Key on a VALIDATED api key; fall back to IP for anonymous traffic
    key = request.headers.get("x-api-key") or (request.client.host if request.client else "unknown")
    bucket = buckets.setdefault(key, TokenBucket(rate=1.0, capacity=10))

    if not bucket.allow():
        raise HTTPException(
            status_code=429,
            detail="Too many requests",  # keep generic, do not leak thresholds
            headers={"Retry-After": str(bucket.retry_after())},
        )


@app.get("/api/data", dependencies=[Depends(rate_limit)])
async def get_data():
    return {"ok": True}
```

### 5.1 Response behaviour

- Return **429** with a **Retry-After** header.
- Expose limit state with `X-RateLimit-Limit`, `X-RateLimit-Remaining` and `X-RateLimit-Reset` so clients can back off before hitting the wall.
- Keep error bodies generic; do not reveal internal thresholds beyond what clients need.

## 6. Client side: backoff with jitter

A rate-limited client should respect `Retry-After` when present, and otherwise use exponential backoff with jitter. Jitter matters because without it, every client that was rejected retries at the same instant and causes a second spike.

```python
import asyncio
import random

import httpx


async def get_with_backoff(client: httpx.AsyncClient, url: str, max_retries: int = 5):
    for attempt in range(max_retries):
        resp = await client.get(url)
        if resp.status_code != 429:
            return resp

        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            delay = float(retry_after)                         # server told us exactly
        else:
            delay = random.uniform(0, min(30, 2 ** attempt))   # full jitter, capped

        await asyncio.sleep(delay)

    raise RuntimeError("Still rate limited after retries")
```

## 7. Common pitfalls

| Pitfall | Why it hurts | Fix |
|---|---|---|
| Trusting X-Forwarded-For blindly | Attackers spoof it to bypass IP limits | Trust it only from your known proxy; take the right-most trusted hop |
| Limiting by IP only | Botnets and residential proxies evade it | Combine IP with key, account and device signals |
| Read-then-write counters | Race conditions let bursts through | Atomic INCR/EXPIRE or Lua |
| Per-node counters | Limit multiplies by server count | Shared store (Redis) |
| Unbounded key map | Random keys grow memory without limit | Only track validated keys; use TTLs |
| Mass key creation | New keys reset the limit | Limit key issuance and signup; enforce per account |
| No fail-open/closed decision | Redis outage becomes your outage | Fail open with alerts for general API; fail closed on auth endpoints |
| Leaked keys | Limits cap damage but do not prevent it | Anomaly alerts and fast revocation |
| Skipping the observe phase | Blocks legitimate customers | Run log-only first and set thresholds above p99 |

## 8. AI and agent relevance

This is where rate limiting matters most for your target roles, in two specific ways.

### 8.1 Token-based limits for LLM APIs

One LLM request can cost 100x another, so counting requests is misleading. Limit on tokens per minute and add hard spend caps. The token bucket above already supports this through the `cost` argument.

```python
# Spend estimated tokens instead of 1 per request
est_tokens = len(prompt) // 4 + max_output_tokens
if not bucket.allow(cost=est_tokens):
    raise HTTPException(429, "Token budget exceeded", headers={"Retry-After": str(bucket.retry_after(est_tokens))})
```

Missing limits here map to the OWASP LLM Top 10 category on unbounded consumption: denial of service, runaway cost ("denial of wallet"), and model extraction through high-volume querying.

### 8.2 AgentScan as a rate-limited client

A red-teaming scanner sends many requests at someone else's endpoint. Combine an `asyncio.Semaphore` (concurrency cap) with the backoff helper from section 6 so the tool respects target limits and does not look like an attack itself. A configurable requests-per-second setting in `BaseSettings` is a reasonable first feature.

## 9. Realistic implementation timeline

| Phase | Time | What you do |
|---|---|---|
| 1. Baseline | 1-2 days | Edge/WAF rules for login and public endpoints; generous global limits |
| 2. Key-level limits | 3-7 days | Token bucket per API key in Redis; proper 429s and headers |
| 3. Observe, do not block | 1-2 weeks | Log-only mode; analyse real traffic; set thresholds above p99 |
| 4. Enforce and tier | ~1 week | Enable blocking; plan tiers; per-endpoint limits; client docs |
| 5. Harden | Ongoing | Anomaly detection, spend caps, alerting, threshold reviews |

Starting values to tune against real traffic (placeholders, not recommendations): login 5-10 attempts per minute per IP and per account; general API 60-100 requests per minute per key with burst 2x; expensive endpoints 5-10x stricter; global edge limit high enough for NAT users.
