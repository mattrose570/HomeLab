# On proxmox node
lxcId=115

configFile="/etc/pve/lxc/${lxcId}.conf"

cat >> "$configFile" <<EOF
lxc.cgroup2.devices.allow: c 10:200 rwm
lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
EOF

appPortNumber=5055

# Install tailscale on lxc console
curl -fsSL https://tailscale.com/install.sh | sh

# Start tailscale 
tailscale up

# Authenticate with tailscale

# Enable https 
tailscale serve --bg --https=443 "http://localhost:$appPortNumber"