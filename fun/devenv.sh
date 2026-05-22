dev() {
  local query="$1"
  shift
  local extra_volumes=()
  local user
  user="$(whoami)"
  local container_name="devenv"
  local ssh_port=2222
  local uid=1000
  local gid=1000

  # Parse --volume, --uid, --gid flags
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --volume|-v)
        extra_volumes+=("$1" "$2")
        shift 2
        ;;
      --volume=*|-v=*)
        extra_volumes+=("$1")
        shift
        ;;
      --volume-ro)
        extra_volumes+=("$1" "$2")
        shift 2
        ;;
      --volume-ro=*)
        extra_volumes+=("$1")
        shift
        ;;
      --uid)
        uid="$2"
        shift 2
        ;;
      --uid=*)
        uid="${1#--uid=}"
        shift
        ;;
      --gid)
        gid="$2"
        shift 2
        ;;
      --gid=*)
        gid="${1#--gid=}"
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  # Find the matching repo folder
  local repo_path
  repo_path=$(find "/Users/${user}/Documents/GitHub/" -type d -maxdepth 1 | \
    awk '{ print length($0) " " $0 }' | \
    sort -n | \
    cut -d ' ' -f 2- | \
    grep -m 1 "$query")

  if [[ -z "$repo_path" ]]; then
    echo "dev: no matching repo found for '$query'" >&2
    return 1
  fi

  local folder_name
  folder_name="$(basename "$repo_path")"

  # Ensure persistent devenv host paths exist before mounting
  mkdir -p "${HOME}/devenv/.vscode-server" "${HOME}/devenv/.claude"
  [[ -f "${HOME}/devenv/.claude.json" ]] || touch "${HOME}/devenv/.claude.json"

  # Build volume args and desired host path list in parallel
  local vol_args=()
  local desired_host_paths=()

  _add_vol() {
    vol_args+=(--volume "$1")
    desired_host_paths+=("${1%%:*}")
  }

  _add_vol "${HOME}/.ssh/id_ed25519.pub:/home/${user}/.ssh/authorized_keys:ro"
  _add_vol "${HOME}/devenv/.vscode-server:/home/${user}/.vscode-server"
  _add_vol "${HOME}/devenv/.claude:/home/${user}/.claude"
  _add_vol "${HOME}/devenv/.claude.json:/home/${user}/.claude.json"
  _add_vol "${repo_path}:/home/${user}/GitHub/${folder_name}"

  # Map extra --volume/--volume-ro paths to same path inside container
  local is_ro=false
  for vol in "${extra_volumes[@]}"; do
    if [[ "$vol" == "--volume" || "$vol" == "-v" ]]; then
      is_ro=false
      continue
    elif [[ "$vol" == "--volume-ro" ]]; then
      is_ro=true
      continue
    fi
    local host_path="${vol#--volume=}"
    host_path="${host_path#--volume-ro=}"
    host_path="${host_path#-v=}"
    host_path="${host_path%/}"
    if $is_ro; then
      _add_vol "${host_path}:${host_path}:ro"
    else
      _add_vol "${host_path}:${host_path}"
    fi
    is_ro=false
  done

  # Check if container is already running with all required volumes
  local should_start=true
  if docker inspect --format '{{.State.Running}}' "$container_name" 2>/dev/null | grep -q true; then
    local current_binds
    current_binds=$(docker inspect --format '{{range .HostConfig.Binds}}{{println .}}{{end}}' "$container_name" 2>/dev/null)
    local needs_recreate=false
    local desired
    for desired in "${desired_host_paths[@]}"; do
      if ! grep -qF "$desired" <<< "$current_binds"; then
        needs_recreate=true
        break
      fi
    done
    if $needs_recreate; then
      echo "dev: volumes changed — recreating container..."
      docker rm -f "$container_name"
    else
      echo "dev: container already running with correct volumes."
      should_start=false
    fi
  fi

  if $should_start; then
  echo "dev: starting container '$container_name'..."
  if ! docker run -d \
    --name "$container_name" \
    -p "${ssh_port}:22" \
    "${vol_args[@]}" \
    alphabet5/tools:latest --user "$user" --uid "$uid" --gid "$gid"; then
    echo "dev: failed to start container." >&2
    return 1
  fi
  fi  # end should_start

  # Wait for SSH to be ready
  echo "dev: waiting for SSH..."
  local retries=0
  until ssh -o StrictHostKeyChecking=no -o ConnectTimeout=2 -p "$ssh_port" "${user}@127.0.0.1" true 2>/dev/null; do
    retries=$((retries + 1))
    if [[ $retries -ge 20 ]]; then
      echo "dev: SSH did not become ready in time." >&2
      return 1
    fi
    sleep 1
  done

  echo "dev: opening VSCode remote session..."
  code --folder-uri "vscode-remote://ssh-remote+${user}@127.0.0.1:${ssh_port}/home/${user}/GitHub/${folder_name}"
}
