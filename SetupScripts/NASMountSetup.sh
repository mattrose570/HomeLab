#!/bin/bash

# Load utility functions 
source ./utils/utils.sh

# Check if user is running script using or as root
root_check

# Load environment variables
load_env_variables

# mounting SMB fileshare on linux
# Install tools 
apt install cifs-utils --yes

# Create mount point 
mkdir -p "/mnt/$SHARE_NAME"

# Create credentials file in $SMB_CREDENTIALS_LOCATION
echo -e "username=$TRUENAS_USERNAME\npassword=$TRUENAS_PASSWORD" > $SMB_CREDENTIALS_LOCATION

# Secure the file 
chmod 600 $SMB_CREDENTIALS_LOCATION

# Mount the fileshare
mount -t cifs "//$NAS_IP/SMB" /mnt/$SHARE_NAME -o credentials=$SMB_CREDENTIALS_LOCATION


# Auto-Mounting configuration
# Add line to /etc/fstab
echo -e "//$NAS_IP/SMB /mnt/$SHARE_NAME cifs credentials=$SMB_CREDENTIALS_LOCATION,iocharset=utf8,uid=1000,gid=1000 0 0" > /etc/fstab

# test with command
mount -a