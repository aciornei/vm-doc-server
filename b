hostname
hostname -f
getent hosts "$(hostname)"
cat /etc/resolv.conf
resolvectl status 2>/dev/null
dig +search "$(hostname)"
