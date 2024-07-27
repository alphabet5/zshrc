# clear dns cache
mdns()
{
sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder
}
