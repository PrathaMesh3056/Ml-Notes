# PostgreSQL Fundamentals & Schema Design

---

## Table of Contents
1. [Primary Key & Foreign Key](#1-primary-key--foreign-key)
2. [Schema Setup](#2-schema-setup)
3. [Basic Queries](#3-basic-queries)
4. [Constraints & CASCADE](#4-constraints--cascade)
5. [JOINs](#5-joins)
6. [GROUP BY & HAVING](#6-group-by--having)
7. [Indexing](#7-indexing)

---

## 1. Primary Key & Foreign Key

**Primary Key:** Uniquely identifies each row in a table. Cannot be NULL, cannot repeat.

**Foreign Key:** A column in one table that references the primary key of another table. Lives on the "many" side of a relationship and enforces that the referenced row actually exists.

```
users.id        → PRIMARY KEY
posts.user_id   → FOREIGN KEY, references users(id)
```

One user → many posts. The foreign key (`user_id`) lives in `posts` (the "many" side), pointing back to `users` (the "one" side).

---

## 2. Schema Setup

**Note:** Reconstructed to match the columns used in this session's queries (`users.name`, `users.age`, `users.email`, `posts.title`, `posts.user_id`). Adjust if your actual table differs.

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100) UNIQUE,
    age INTEGER
);

CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200),
    user_id INTEGER REFERENCES users(id)
);
```

---

## 3. Basic Queries

```sql
-- View all users
SELECT * FROM users;
```

**Other core commands from the video (for reference):**
```sql
-- INSERT
INSERT INTO users (name, email, age) VALUES ('Alice', 'alice@ex.com', 25);

-- SELECT with filter
SELECT * FROM users WHERE age > 18;

-- UPDATE
UPDATE users SET age = 26 WHERE name = 'Alice';

-- DELETE
DELETE FROM users WHERE name = 'Alice';
```

---

## 4. Constraints & CASCADE

```sql
-- CHECK constraint example
ALTER TABLE users ADD CONSTRAINT age_check CHECK (age >= 0);

-- DELETE CASCADE: deleting a user also deletes their posts
ALTER TABLE posts
DROP CONSTRAINT posts_user_id_fkey,
ADD CONSTRAINT posts_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
```

---

## 5. JOINs

### INNER JOIN — only matching rows in both tables
```sql
SELECT u.name, p.title
FROM users u
INNER JOIN posts p ON p.user_id = u.id;
```
Users with zero posts are excluded entirely.

### LEFT JOIN — all rows from left table, matched where possible
```sql
SELECT u.name, p.title
FROM users u
LEFT JOIN posts p ON p.user_id = u.id;
```
Users with no posts still appear, with `p.title` as `NULL`.

### RIGHT JOIN — all rows from right table, matched where possible
```sql
SELECT u.name, p.title
FROM users u
RIGHT JOIN posts p ON p.user_id = u.id;
```

### FULL OUTER JOIN — all rows from both tables, matched where possible
```sql
SELECT u.name, p.title
FROM users u
FULL OUTER JOIN posts p ON p.user_id = u.id;
```
Shows unmatched rows from both sides (NULLs on whichever side has no match).

### CROSS JOIN — every row from left paired with every row from right
```sql
SELECT u.name, s.status
FROM users u
CROSS JOIN (VALUES ('published'), ('draft'), ('archived')) AS s(status);
```
Every user gets paired with every status — no join condition, just full combination.

### SELF JOIN — a table joined to itself
```sql
SELECT a.name, b.name, a.age
FROM users a
JOIN users b ON a.age = b.age AND a.id > b.id;
```
Finds users with the same age, paired against each other (the `a.id > b.id` avoids duplicate/mirror pairs and self-matching).

---

## 6. GROUP BY & HAVING

```sql
SELECT name, age, COUNT(p.id) AS post_count
FROM users u
JOIN posts p ON p.user_id = u.id
WHERE age > 18
GROUP BY u.id, name, age
HAVING COUNT(p.id) > 1;
```

- **WHERE** filters rows *before* grouping (here: `age > 18`)
- **GROUP BY** collapses rows into groups (here: per user)
- **HAVING** filters *after* grouping, works on aggregates (here: only users with more than 1 post)

---

## 7. Indexing

```sql
-- Create an index on a frequently-queried column
CREATE INDEX id_index ON posts(user_id);

-- Check query performance
EXPLAIN ANALYZE
SELECT * FROM posts
WHERE user_id = (SELECT id FROM users WHERE email = 'admin@ex.com');
```

Indexes speed up lookups/filters on a column (like `WHERE user_id = ...`) at the cost of slightly slower writes and extra storage. `EXPLAIN ANALYZE` shows whether PostgreSQL is actually using the index (or doing a full table scan).

---

**End of Document**
