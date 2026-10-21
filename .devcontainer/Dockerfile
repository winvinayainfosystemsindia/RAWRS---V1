FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm
# The image's yarn apt source has an expired signing key, which fails every
# `apt-get update` - and with it the sshd feature and post-create.sh.
RUN rm -f /etc/apt/sources.list.d/yarn.list
