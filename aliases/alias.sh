# use gsed if on mac
if [[ $(uname -a) == *"Darwin"* ]]; then
  # echo "I'm a mac, so I'm using gsed instead of sed."
  alias sed=gsed
fi
