# syntax=docker/dockerfile:1

# This Dockerfile is based on the Dockerfile defined by @cloudflare/sandbox. 
# It has been modified significantly to support pywrangler. The base image is
# different because the originally used bun base image caused issues with pyodide-build.

FROM ubuntu:rolling
# Set destination for COPY
WORKDIR /app

# Install packages that we need to run pywrangler and its dependencies
RUN apt-get update && apt-get install -y git wget pipx ca-certificates build-essential curl python3 coreutils unzip nodejs && update-ca-certificates
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
RUN pipx install uv && pipx install pyodide-cli
ENV PATH="/root/.local/bin:${PATH}"
RUN uv --version

# Install bun.
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"
RUN bun --version

# Copy over the source code for the app that Bun will run
COPY node_modules/@cloudflare/sandbox/container_src/* ./
# Copy over our files for pywrangler to work.
COPY container_files/pyproject.toml ./pyproject.toml
COPY container_files/wrangler.jsonc ./wrangler.jsonc
COPY container_files/pywrangler /root/.local/bin/pywrangler
RUN chmod +x /root/.local/bin/pywrangler

# Ensure pywrangler is operational
RUN pywrangler --version

# Run sync to pre-warm caches
RUN pywrangler --debug sync

# Clear the vendor files that pywrangler created.
RUN rm -r /app/src/vendor

EXPOSE 3000
# Run
CMD ["bun", "index.ts"]

