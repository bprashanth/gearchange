FROM mongo:7.0.12-jammy

# Default mongod.conf used when the entrypoint fails to resolve a custom 
# mongod.conf.
COPY mongod.conf /etc/mongo/mongod_default.conf

# This entrypoint ensures the default mongo data dir (dbPath in the config) is 
# set to the right ownership and permissions. 
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
