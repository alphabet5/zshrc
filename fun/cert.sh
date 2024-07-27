# use openssl to get cert info
cert()
{
host="$1"
port="${2:-443}"
openssl s_client -showcerts -verify 5 -connect $host:$port 2>&1
}
