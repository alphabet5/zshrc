function ds() {
  function search() {
    echo "looking for ${1}..."
    NAME=$(curl -s "${DOCKER_REGISTRY}/v2/_catalog?n=1000" | jq -r '.repositories[]' | grep "${1}")
    echo "${NAME}:"
    curl -s "${DOCKER_REGISTRY}/v2/${NAME}/tags/list" | jq -r '.tags[]' | sort
  }

  if [ $# -eq 0 ]; then
    curl -s "${DOCKER_REGISTRY}/v2/_catalog?n=1000" | jq -r '.repositories[]'
  else
    search "$1"
  fi
}