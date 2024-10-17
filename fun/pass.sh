function p() {
    op item list --format=json | jq -r '.[] | "\(.title | length) \(.id) \(.title)"' | grep -i "${1}" | sort -n | head -1 | sed -rn 's/[0-9]+ ([a-z,A-Z,0-9]+) .+/\1/p' | xargs op item get --reveal --fields=password | tr -d '\n' | pbcopy
}
