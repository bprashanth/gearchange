# TODO(prashanth@): move this to a t4g dockerhub repo? 
FROM mongo:7.0.12-jammy

RUN apt-get update && apt-get install -y \
    gnupg \
    wget \
    curl \
    python3 \
    supervisor \
    dnsutils \
    pip 

# Clean up unnecessary files
RUN apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

# Default mongod.conf used when the entrypoint fails to resolve a custom 
# mongod.conf.
COPY ./store/mongo/mongod.conf /etc/mongo/mongod_default.conf

# This entrypoint ensures the default mongo data dir (dbPath in the config) is 
# set to the right ownership and permissions. 
COPY ./store/mongo/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy supervisor configuration file
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Overwrite the baseimage entrypoint
ENTRYPOINT []

# mongo is the name of the mongo container 
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
