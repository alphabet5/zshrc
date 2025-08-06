# Random commands 


## inodes

```
{ find / -xdev -printf '%h\n' | sort | uniq -c | sort -k 1 -n; } 2>/dev/null
```

## os version

```bash
run-commands host1 host2 --command 'if [ "$(uname)" = "Linux" ]; then lsb_release -a; else echo "FreeBSD"; fi;' | tee -a os.json
```

```bash
cat os.json | jq -r 'select(.errors == {}) | .name + "\t" + (.simple | split("\n")[] | select(startswith("Description:")) | sub("Description:\\s*"; ""))' | sed 's/ //g'
```

## os installed date

```bash
run-commands host1 host2 --command '[ "$(uname)" = "FreeBSD" ] && date -u -r $(stat -f "%B" /) +"%Y-%m-%dT%H:%M:%SZ" || date -u -d "@$(stat -c "%W" /)" +"%Y-%m-%dT%H:%M:%SZ"'
```



## Searching git repos for credentials

```bash
brew install git-secrets
```

```bash
python3 -m pip install trufflehog --break-system-packages
```

```bash
brew install gitleaks
```

```bash
brew install detect-secrets
```

