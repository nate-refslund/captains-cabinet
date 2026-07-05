# syntax=docker/dockerfile:1
# cabinet/deploy/docker/Dockerfile — the `docker` deployment target (axes spec
# 2026-07-05 §3, AX-4). Revives the extinct /opt/founders-cabinet ancestry as
# a first-class target on the modern kernel.
#
# TRUST BOUNDARY: not in this image. The image bakes the repo read-write; the
# germline boundary is the HOST's read-only bind mounts (docker-compose.yml)
# over the germline dirs + posture.yml + standing-grants.yml — mounts the
# container cannot remount at ANY privilege (CAP_SYS_ADMIN dropped,
# no-new-privileges). framework/authority/posture.py attests those files via
# the `ro_mount` backend (O_NOFOLLOW open-append probe + a ro /proc/mounts
# entry); ANY ambiguity resolves guardian. Everything else in the image being
# immutable-by-rebuild is a bonus, not the boundary.
#
# Build from the REPO ROOT context (compose does this for you):
#   docker build -f cabinet/deploy/docker/Dockerfile -t captains-cabinet:docker .

FROM python:3.12-slim-bookworm

# cron  = the schedule renderer's target (one manifest, two renderers — see
#         cabinet/scripts/generate-services-cron.py)
# redis-tools = trigger/heartbeat plumbing; git = repo-aware scripts
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash cron git redis-tools \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir pyyaml pytest

WORKDIR /opt/cabinet
COPY . /opt/cabinet

ENV CABINET_ROOT=/opt/cabinet \
    PYTHONUNBUFFERED=1

RUN mkdir -p /var/log/cabinet

# Clean-room CI gate (axes spec §6.2): the full framework suite must pass on
# this bare instance — no personal sources, no screenpipe, no vault:
#   docker run --rm captains-cabinet:docker python3 -m pytest framework/ -q

# Render the container schedule from the ONE fleet manifest, install it, and
# run cron in the foreground. Manifest rows must OPT IN with
# `platform: linux|any` (default darwin = launchd-only, renders header-only
# until rows are verified container-safe). REDIS_HOST defaults to the compose
# sidecar's hostname.
CMD ["bash", "-c", "mkdir -p /var/log/cabinet \
    && python3 cabinet/scripts/generate-services-cron.py \
         --root /opt/cabinet \
         --redis-host \"${REDIS_HOST:-redis}\" \
         --output /tmp/cabinet.cron \
    && crontab /tmp/cabinet.cron \
    && exec cron -f"]
