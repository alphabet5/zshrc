


SELECT pg_terminate_backend(<pid of the process>)


## Copy a user to a new db

```
sudo -u postgres pg_dumpall -g | grep -E "username"
CREATE ROLE username;
ALTER ROLE username WITH NOSUPERUSER INHERIT NOCREATEROLE NOCREATEDB LOGIN NOREPLICATION NOBYPASSRLS PASSWORD '***';
GRANT developers TO username GRANTED BY qle;
GRANT k8saccess TO username GRANTED BY pgsql;
```

