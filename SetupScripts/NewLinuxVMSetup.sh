#!/bin/bash

# Load utility functions 
source ./utils/utils.sh

# Check if user is running script using or as root
root_check

# Load environment variables
load_env_variables

if [ -d "/mnt/$SHARE_NAME" ]; then
  echo "Directory '/mnt/$SHARE_NAME' exists."
else
  echo "Directory '$DIRECTORY' does not exist."
  echo "Proceeding to create and mount NAS."
  ./NASMountSetup.sh
fi
