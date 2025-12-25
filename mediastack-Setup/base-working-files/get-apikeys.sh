#!/usr/bin/bash

# This script will extract all of the API Keys configured in the *ARR Media Library Managers
# You need to install 'yq' and 'xmllint' packages to parse configuration files

export FOLDER_FOR_YAMLS=/docker                 # <-- Folder where the yaml and .env files are located
export FOLDER_FOR_MEDIA=/docker/media           # <-- Folder where your media is locate
export FOLDER_FOR_DATA=/docker/appdata          # <-- Folder where MediaStack stores persistent data and configurations

export PUID=1000
export PGID=1000

cd $FOLDER_FOR_YAMLS
echo 
echo Extracting all current API Keys...
echo 

echo "Bazarr   API Key: " `yq -r '.auth.apikey' $FOLDER_FOR_DATA/bazarr/config/config.yaml` "  located in $FOLDER_FOR_DATA/bazarr/config/config.yaml"
echo "Lidarr   API Key: " `xmllint --xpath "string(//Config/ApiKey)" $FOLDER_FOR_DATA/lidarr/config.xml` "  located in $FOLDER_FOR_DATA/lidarr/config.xml"
echo "Mylar    API Key: " `grep '^api_key' $FOLDER_FOR_DATA/mylar/mylar/config.ini | sed -E 's/.*=\s*//'` "  located in $FOLDER_FOR_DATA/mylar/mylar/config.ini"
echo "Prowlarr API Key: " `xmllint --xpath "string(//Config/ApiKey)" $FOLDER_FOR_DATA/prowlarr/config.xml` "  located in $FOLDER_FOR_DATA/prowlarr/config.xml"
echo "Radarr   API Key: " `xmllint --xpath "string(//Config/ApiKey)" $FOLDER_FOR_DATA/radarr/config.xml` "  located in $FOLDER_FOR_DATA/radarr/config.xml"
echo "Readarr  API Key: " `xmllint --xpath "string(//Config/ApiKey)" $FOLDER_FOR_DATA/readarr/config.xml` "  located in $FOLDER_FOR_DATA/readarr/config.xml"
echo "Sonarr   API Key: " `xmllint --xpath "string(//Config/ApiKey)" $FOLDER_FOR_DATA/sonarr/config.xml` "  located in $FOLDER_FOR_DATA/sonarr/config.xml"
echo "Whisparr API Key: " `xmllint --xpath "string(//Config/ApiKey)" $FOLDER_FOR_DATA/whisparr/config.xml` "  located in $FOLDER_FOR_DATA/whisparr/config.xml"


# echo "Sonarr   API Key:" `xmllint --xpath "string(//Config/ApiKey)" $FOLDER_FOR_DATA/sonarr/config.xml`
