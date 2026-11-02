# Transactions & Indexing / Query Optimization

---

## Table of Contents
1. [Transactions](#1-transactions)
2. [ACID Properties](#2-acid-properties)
3. [Isolation Levels](#3-isolation-levels)
4. [Indexing Recap](#4-indexing-recap)
5. [Reading EXPLAIN ANALYZE](#5-reading-explain-analyze)
6. [When Indexes Get Ignored](#6-when-indexes-get-ignored)

---

## 1. Transactions

A transaction groups multiple SQL statements into a single unit — either **all** of them succeed, or **none** do.

```sql
BEGIN;

UPDATE accounts SET balance = balance - 500 WHERE id = 1;
UPDATE accounts SET balance = balance + 500 WHERE id = 2;

COMMIT;   -- makes changes permanent
-- OR
ROLLBACK; -- undoes everything since BEGIN
```

**Critical rule:** `ROLLBACK` only works **before** `COMMIT`. Once committed, changes are permanent — you cannot roll back. Undoing a committed change requires a backup, audit log, or a new compensating transaction.

### Why This Matters — Bank Transfer Example

Without a transaction, if the first `UPDATE` succeeds but the second fails (crash, bug, network issue), money disappears — deducted from account 1, never added to account 2. Wrapping both in one transaction guarantees it's all-or-nothing.

---

## 2. ACID Properties

| Letter | Property | Meaning |
|---|---|---|
| **A** | Atomicity | All steps in a transaction succeed, or none do — no partial state |
| **C** | Consistency | The database moves from one valid state to another; constraints (CHECK, FOREIGN KEY, etc.) are never violated |
| **I** | Isolation | Concurrent transactions don't see each other's uncommitted changes |
| **D** | Durability | Once committed, data survives even an immediate crash (written to disk) |

### Isolation — Why It Matters (Race Condition Example)

Without isolation, two transactions reading the same balance *before* either writes can both pass a validation check that should have only passed once:

```
Account balance = 100

Transaction 1 (withdraw 80):          Transaction 2 (withdraw 80):
  READ balance → 100                    READ balance → 100
  check: 100 >= 80 OK                   check: 100 >= 80 OK
  WRITE balance = 20                    WRITE balance = 20

Final balance: 20 (but 160 was withdrawn from a 100 balance — bug)
```

Proper isolation prevents this by making one transaction wait, or forcing a re-check, when a conflicting transaction is still in progress.

---

## 3. Isolation Levels

PostgreSQL supports multiple isolation levels, each trading strictness for performance:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
-- queries
COMMIT;
```

| Level | Protects Against | Cost |
|---|---|---|
| **Read Committed** (Postgres default) | Dirty reads (reading another transaction's uncommitted data) | Fastest |
| **Repeatable Read** | + Non-repeatable reads (a row changing mid-transaction) | Medium |
| **Serializable** | + Phantom reads / race conditions (the withdrawal example above) | Slowest, strictest |

For race-condition-sensitive operations (like the bank withdrawal), `Serializable` or explicit row locking is what actually prevents the bug:

```sql
SELECT * FROM accounts WHERE id = 1 FOR UPDATE;  -- locks the row until commit/rollback
```

---

## 4. Indexing Recap

An index lets PostgreSQL jump directly to matching rows instead of scanning the whole table — at the cost of extra storage and slightly slower writes.

```sql
CREATE INDEX idx_posts_user_id ON posts(user_id);

-- Composite index (multiple columns)
CREATE INDEX idx_posts_user_created ON posts(user_id, created_at);
```

---

## 5. Reading EXPLAIN ANALYZE

```sql
EXPLAIN ANALYZE
SELECT * FROM posts WHERE user_id = 5;
```

**Seq Scan (Sequential Scan):**
```
Seq Scan on posts  (cost=0.00..18.50 rows=850 width=36) (actual time=0.015..0.312 rows=1000 loops=1)
```
Reads every row in the table and checks it against the `WHERE` condition. No index used.

**Index Scan:**
```
Index Scan using idx_posts_user_id on posts  (cost=0.29..8.31 rows=1 width=36) (actual time=0.025..0.027 rows=1 loops=1)
```
Jumps directly to the matching row(s) via the index.

If a query shows `Seq Scan` despite a relevant index existing, the planner decided the index wasn't worth using — not necessarily a bug.

---

## 6. When Indexes Get Ignored

The query planner always picks the **cheaper** option — having an index doesn't guarantee it gets used.

**Common reasons:**

1. **Small table** — if the table fits in one or two 8KB disk pages, reading it sequentially (1 read) is cheaper than using the index (index page read + table page read = 2+ reads). The crossover point is usually in the thousands of rows, not tens.
2. **Low selectivity** — if the `WHERE` condition matches a large percentage of rows (e.g., `WHERE is_active = true` when 90% of rows are active), scanning sequentially is cheaper than jumping around via index.
3. **Stale statistics** — PostgreSQL's planner relies on table statistics to estimate costs. Refresh them with:
   ```sql
   ANALYZE posts;
   ```

---

**End of Document**
