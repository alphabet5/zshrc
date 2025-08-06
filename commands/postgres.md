
## Reload pg_hba file

```sql
SELECT pg_reload_conf();  
```

```bash
su - postgres -c "/usr/bin/pg_ctl reload"  
```

## Kill a long running query
```sql
SELECT pg_terminate_backend(<pid of the process>)
```

## Copy a user to a new db

```
sudo -u postgres pg_dumpall -g | grep -E "username"
CREATE ROLE username;
ALTER ROLE username WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS PASSWORD '***';
GRANT developers TO username GRANTED BY qle;
GRANT k8saccess TO username GRANTED BY pgsql;
```

## Long running transactions

```
SELECT 
    pid,
    usename as user,
    client_addr as client_ip,
    client_hostname,
    application_name,
    state,
    query_start,
    xact_start,
    now() - xact_start as transaction_duration,
    now() - query_start as query_duration,
    left(query, 100) as current_query
FROM pg_stat_activity 
WHERE state NOT IN ('idle', 'idle in transaction')
    AND query NOT LIKE 'autovacuum:%'
    AND NOT (query ~* '^VACUUM( ANALYZE)?(?! FULL)')
    AND pg_stat_activity.xact_start IS NOT NULL
    AND EXTRACT(EPOCH FROM clock_timestamp() - pg_stat_activity.xact_start) > 30
    AND NOT (query ~* '^REFRESH MATERIALIZED VIEW CONCURRENTLY')
    AND NOT (query ~* '^BEGIN ISOLATION LEVEL READ UNCOMMITTED')
ORDER BY xact_start ASC;
```

less filtered

```
SELECT 
    pid,
    usename as user,
    client_addr as client_ip,
    client_hostname,
    application_name,
    state,
    query_start,
    xact_start,
    now() - xact_start as transaction_duration,
    now() - query_start as query_duration,
    left(query, 100) as current_query
FROM pg_stat_activity 
WHERE state NOT IN ('idle', 'idle in transaction')
    AND pg_stat_activity.xact_start IS NOT NULL
    AND EXTRACT(EPOCH FROM clock_timestamp() - pg_stat_activity.xact_start) > 1
ORDER BY xact_start ASC;
```

## Queries with share locks and client ip

```
SELECT 
    l.pid,
    a.usename AS username,
    a.datname AS database,
    a.client_addr AS client_ip,
    a.application_name,
    l.locktype,
    l.mode AS lock_mode,
    CASE 
        WHEN c.relname IS NOT NULL THEN c.relname 
        ELSE l.relation::text 
    END AS relation_name,
    l.granted,
    a.state,
    a.query_start,
    EXTRACT(EPOCH FROM (now() - a.query_start))::int AS query_duration_seconds,
    LEFT(a.query, 100) AS query_preview
FROM pg_locks l
JOIN pg_stat_activity a ON l.pid = a.pid
LEFT JOIN pg_class c ON l.relation = c.oid
WHERE 
    -- Filter for shared lock modes only
    l.mode IN ('AccessShareLock', 'RowShareLock')
    -- Only show active queries (not idle connections)
    AND a.state = 'active'
    -- Exclude system processes
    AND a.datname IS NOT NULL
ORDER BY 
    a.query_start DESC,
    l.pid,
    l.mode;
```