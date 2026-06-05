# use openssl to get cert info
cert()
{
host="$1"
port="${2:-443}"
openssl s_client -showcerts -verify 5 -connect $host:$port 2>&1
}

certinfo() {
    if [ -n "$1" ]; then
        openssl x509 -in "$1" -text -noout
    else
        openssl x509 -text -noout
    fi
}
