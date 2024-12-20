SAVEHIST=1000000000  # Save most-recent lines
HISTFILE=~/.zsh_history
HISTSIZE=1000000000
MYDIR="/Users/$(whoami)/Documents/GitHub/zshrc"

export PATH="${KREW_ROOT:-$HOME/.krew}/bin:$PATH"

setopt inc_append_history
setopt appendhistory
alias sed=gsed
ssh-add

eval "$(
  cat $MYDIR/init/.env | awk '!/^\s*#/' | awk '!/^\s*$/' | while IFS='' read -r line; do
    key=$(echo "$line" | cut -d '=' -f 1)
    value=$(echo "$line" | cut -d '=' -f 2-)
    echo "export $key=\"$value\""
  done
)"

source $MYDIR/aliases/alias.sh
for file in $(ls $MYDIR/fun); do source $MYDIR/fun/$file;done;
for file in $(ls $MYDIR/remote-run); do source $MYDIR/remote-run/$file;done;
for file in $(ls $MYDIR/temp); do source $MYDIR/temp/$file;done;
