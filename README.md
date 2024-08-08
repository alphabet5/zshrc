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
python3 -m pip install rich --break-system-packages
python3 -m pip install jira --break-system-packages
```

- probably a bunch of things I haven't documented yet. ¯\_(ツ)_/¯

