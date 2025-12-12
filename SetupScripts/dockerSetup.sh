#!/bin/bash

# Load utility functions 
source ./utils/utils.sh

# Check if user is running script using or as root
root_check

# Load environment variables
load_env_variables

# Remove components if they exist
echo "apt remove docker docker-engine docker.io containerd runc"
apt remove docker docker-engine docker.io containerd runc

# Install dependencies
echo "apt-get update"
apt-get update

echo "apt-get install --yes ca-certificates curl gnupg lsb-release"
apt-get install --yes ca-certificates curl gnupg lsb-release

# Add official gpg key 
echo "mkdir -p /etc/apt/keyrings"
mkdir -p /etc/apt/keyrings

echo "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes

# Set up docker repo
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
  

sudo -u $TRUENAS_USERNAME # docker run hello-world
# Install Docker engine 
apt-get update --yes
apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin --yes


# Start and enable docker

echo "DEBUG: systemctl enable docker"
systemctl enable docker
echo "DEBUG: systemctl start docker"
systemctl start docker

# Check status
echo "DEBUG: systemctl status docker"
systemctl --no-pager status docker

# Add user to docker group
echo "DEBUG: usermod -aG docker $TRUENAS_USERNAME"
usermod -aG docker $TRUENAS_USERNAME

# Logout and log back in or 
exec su -l $TRUENAS_USERNAME

# verify
echo "DEBUG: docker run hello-world"
# docker run hello-world
sudo -u $TRUENAS_USERNAME docker run hello-world

# echo "DEBUG: su $TRUENAS_USERNAME"
# su $TRUENAS_USERNAME

echo "Docker setup complete. You can now run Docker commands without sudo."

# Manual commands:
# newgrp docker
# sudo usermod -aG docker $USER
# groups