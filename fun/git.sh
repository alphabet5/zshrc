# github desktop style stash and pop
stash(){
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "Where are you? Maybe double check"
    return 1
  }
  branch=$(git symbolic-ref --short HEAD 2>/dev/null) || {
    echo "Detached HEAD — cannot create branch stash"
    return 1
  }
  git stash push -u -m "!!GitHub_Desktop<${branch}>"
}

pop() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    echo "Where are you? Maybe double check"
    return 1
  }
  branch=$(git symbolic-ref --short HEAD 2>/dev/null) || {
    echo "Detached HEAD — cannot pop branch stash"
    return 1
  }
  stash_ref=$(git stash list | grep "!!GitHub_Desktop<${branch}>" | head -n 1 | cut -d: -f1)
  if [ -z "$stash_ref" ]; then
    echo "No GitHub Desktop stash found for branch '${branch}'"
    return 1
  fi
  git stash pop "$stash_ref"
}

