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
echo "apt update"
apt update

echo "apt install --yes ca-certificates curl gnupg lsb-release"
apt install --yes ca-certificates curl gnupg lsb-release

# Add official gpg key 
echo "mkdir -p /etc/apt/keyrings"
mkdir -p /etc/apt/keyrings

echo "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg"
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up docker repo
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null
  
# Install Docker engine 
apt update --yes
apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin --yes

# Start and enable docker
systemctl enable docker
systemctl start docker

# Check status
# systemctl status docker

# Add user to docker group
usermod -aG docker $USER

# Logout and log back in or 
newgrp docker # or exec su -l $USER

# verify
docker run hello-world

su $USERNAME

echo "Docker setup complete. You can now run Docker commands without sudo."