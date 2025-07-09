#!/bin/bash

# Load utility functions 
source ./utils/utils.sh

# Load environment variables
load_env_variables

service_name="$1"
ipAddress="$2"

mkdir -p ~/.ssh/homelab_keys/$service_name

ssh-keygen -t ed25519 -C "$USERNAME" -f ~/.ssh/homelab_keys/$service_name/$service_name -N "" -q

fileToWrite="~/.ssh/config"

echo -e "\n" >> $fileToWrite
echo "Host $service_name" >> $fileToWrite
echo "  HostName $ipAddress" >> $fileToWrite
echo "  User $USERNAME" >> $fileToWrite
echo "  IdentityFile ~/.ssh/homelab_keys/$service_name/$service_name" >> $fileToWrite