#!/bin/bash

# Load utility functions 
source ./utils/utils.sh

# Load environment variables
load_env_variables

service_name="$1"

mkdir -p ~/.ssh/homelab_keys/$service_name

ssh-keygen -t ed25519 -C "$USERNAME" -f ~/.ssh/homelab_keys/$service_name/$service_name -N "" -q
