# Homelab docs

## Local Layout

### docker-services -- 192.168.1.45
| Service    | Port   | RP-Address                   |
|------------|--------|------------------------------|
| HomeBridge | 8581   | homebridge.mattswoodwork.com |
| Authentik  | 80/443 | authentik.mattswoodwork.com  |
| HomeBox    | 3100   | homebox.mattswoodwork.com    |
### caddyserver     -- 192.168.1.148

### NAS -- 192.168.1.142

#### NAS Services


### Proxmox

pve  -- 192.168.1.30
pve2 -- 192.168.1.32
pve3 -- 192.168.1.92
pangolin -- 192.168.1.214

## Services
Glance (LXC-pve) -- 192.168.1.197:8080 [url](http://192.168.1.197:8080)
  - Config: `/opt/glance/glance.yml`

## Common Issues:

### Docker will not start on docker-services

```bash
# Get crash reason 
journalctl -u docker.service --no-pager -n 200

# If the errors contain "read-only file system..."
sudo mount -o remount,rw /
sudo systemctl start docker
```

### Proxmox node UI not available after restart

```bash
# Check if file system remounted as read-only
apt-get update

# Remount if necessary 
mount -o remount,rw /

# Check if pveproxy is running 
pveproxy status

# Start if it is stopped
pveproxy start
```


### Setting k8 config to localhost IP
`sudo sed -i "s/127.0.0.1/$(hostname -I | awk '{print $1}')/" ~/.kube/config`