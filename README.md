# zshrc
 This is my zshrc.

## Installation

```bash
git clone github.com/alphabet5/zshrc
cd zshrc
echo "source $(pwd)/init/init.sh" >> ~/.zshrc
```

## Requirements (on mac)

- kubectl 
```bash
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/darwin/arm64/kubectl"
```
- gnu sed (without --with-default-names)
```bash
brew uninstall gnu-sed
```
- python
```bash
brew install python3
echo "You really shouldn't do this, but if you must:"
python3 -m pip install rich textual jira requests pyperclip --break-system-packages
```

```bash
brew install mcs
```

### coredns
```bash
git clone https://github.com/coredns/coredns
cd coredns
make
cp ./coredns /usr/local/bin/coredns
sudo launchctl load $MYDIR/dns/coredns.plist
cp dns/Corefile 
```

### Other brew stuff

```bash
brew install rsync

```

#### dns/Corefile example

```text
.:53 {
    forward . 1.1.1.1
    errors
}

example.local:53 {
    forward . 192.2.0.1 1.1.1.1 {
        policy sequential
        prefer_udp
        max_fails 1
        health_check 5s
    }
    errors
}
```

### Environment Variables

```
JIRA_API_TOKEN
JIRA_EMAIL=
JIRA_SERVER=https://xxx.atlassian.net/
JIRA_PROJECT=MYPROJECT
ELASTIC_HOST=elastic.example.local
ELASTIC_PORT=9200
ELASTIC_CREDENTIALS
GEOIPUPDATE_LICENSE_KEY
GEOIPUPDATE_ACCOUNT_KEY
VPN_DNS_IP
PD_API_KEY
DOCKER_REGISTRY=https://docker-registry.example.local
IDRAC_USER=
IDRAC_PASSWORD=
NETBOX_URL=
NETBOX_TOKEN=
KUBESEAL_CERT="/path/to/sealedsecrets.crt"
KUBESEAL_SCOPE="cluster-wide"
```

## ksniff

If ctr doesn't exist in the path

```
cd /bin ; sudo ln -s /var/lib/rancher/rke2/bin/ctr ctr
```

- probably a bunch of things I haven't documented yet. ¯\_(ツ)_/¯