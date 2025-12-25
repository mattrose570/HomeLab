#!/usr/bin/python3

import os
import re

from pathlib import Path

use_authelia = True
use_full_vpn = True

# Check paths
FOLDER_FOR_DATA = os.getenv('FOLDER_FOR_DATA')
if not FOLDER_FOR_DATA:
    print('Data folder not in ENV.')
    exit(1)
data_dir = Path(FOLDER_FOR_DATA)
proxy_conf_dir = data_dir / 'swag/nginx/proxy-confs'
if not proxy_conf_dir.is_dir():
    print('SWAG proxy config folder does not exist.')
    exit(2)
auth_conf_path = data_dir / 'swag/nginx/site-confs/default.conf'
if not auth_conf_path.is_file():
    print('SWAG default site config does not exist.')
    exit(3)

# Container / config names
stack_network = {'authelia', 'heimdall', 'homarr', 'homepage', 'ddns-updater'}
stack_vpn = {'bazarr', 'filebot', 'flaresolverr', 'jellyfin', 'jellyseerr', 'lidarr', 'mylar', 'plex', 'portainer', 'prowlarr', 'qbittorrent', 'radarr', 'readarr', 'sabnzbd', 'sonarr', 'tdarr', 'whisparr'}
stack_full = stack_network | stack_vpn

for container in stack_full:
    print(f'Processing "{container}".')

    # Get port from env
    caps = container.upper().replace('-', '_')
    port = os.getenv(f'WEBUI_PORT_{caps}') or os.getenv(f'{caps}_PORT')

    # Read sample config
    file = proxy_conf_dir / f'{container}.subdomain.conf.sample'
    if not file.is_file():
        print(f'Can not find config file "{file}".')
        continue
    text = file.read_text()

    # Patch ports
    if port and not container in stack_network:
        text = re.sub(r'set \$upstream_port \d{2,5};', f'set $upstream_port {port};', text)
    # Activate authelia
    if use_authelia:
        text = text.replace('#include /config/nginx/authelia', 'include /config/nginx/authelia')
    # Rewire to gluetun
    if use_full_vpn and container in stack_vpn:
        text = text.replace(f'set $upstream_app {container};', 'set $upstream_app gluetun;')
    # Rename subdomain for authelia to auth
    if container == 'authelia':
        text = text.replace('server_name authelia.*;', 'server_name auth.*;')

    conf = file.with_suffix('').write_text(text)

# Activate authelia in default config
# FIXME: Do we need this?
if use_authelia:
    text = auth_conf_path.read_text()
    text = text.replace('#include /config/nginx/authelia', 'include /config/nginx/authelia')
    auth_conf_path.write_text(text)
