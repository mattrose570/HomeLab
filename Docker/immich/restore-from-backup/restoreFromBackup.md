# Restore Immich from Backup 

```bash
dbDataLocation="./postgres"
pathToDump="/mnt/SMBShare/Media/Images/backups/immich-db-backup-1750842000006.sql.gz"
dbUsername="postgres"

docker compose down -v  # CAUTION! Deletes all Immich data to start from scratch
rm -rf $dbDataLocation  # CAUTION! Deletes all Immich data to start from scratch
docker compose pull     # Update to latest version of Immich (if desired)
docker compose create   # Create Docker containers for Immich apps without running them
docker start immich_postgres    # Start Postgres server
sleep 10                        # Wait for Postgres server to start up
# Check the database user if you deviated from the default
gunzip --stdout "/mnt/SMBShare/Media/Images/backups/immich-db-backup-1749261600006.sql.gz" \
| sed "s/SELECT pg_catalog.set_config('search_path', '', false);/SELECT pg_catalog.set_config('search_path', 'public, pg_catalog', true);/g" \
| docker exec -i immich_postgres psql --dbname=postgres --username=postgres # Restore Backup
docker compose up -d            # Start remainder of Immich apps
```