# 1. Install SMB client tools
apt install -y cifs-utils

# 2. Create credentials file (edit the values below first!)
mkdir -p /root/.smb
cat > /root/.smb/truenas.cred <<EOF
username=mattrose570
password=rush2112
EOF
chmod 600 /root/.smb/truenas.cred

# 3. Create the mount point
# mkdir -p /mnt/truenas-smb
mkdir -p /mnt/lxc-shares/truenas-smb
# 4. Append to /etc/fstab
cat >> /etc/fstab <<'EOF'
//192.168.1.142/SMB  /mnt/lxc-shares/truenas-smb  cifs  credentials=/root/.smb/truenas.cred,uid=100000,gid=100000,file_mode=0770,dir_mode=0770,noserverino,x-systemd.automount,_netdev  0  0
EOF

# 5. Reload systemd and mount
systemctl daemon-reload
mount -a

# 6. Verify
ls /mnt/lxc-shares/truenas-smb