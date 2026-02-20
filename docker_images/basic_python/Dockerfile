# Use the official Ubuntu image as a parent image
FROM ubuntu:latest

# Set environment variables to non-interactive (this ensures that no UI prompts are shown)
ENV DEBIAN_FRONTEND=noninteractive

# Update the package list and install Python and pip
RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv && \
    apt-get install -y curl openssh-client net-tools iproute2 iputils-ping iptables && \
    apt-get install -y tcpdump libpcap-dev && \
    rm -rf /var/lib/apt/lists/*

# Set python3 as the default python
RUN ln -s /usr/bin/python3 /usr/bin/python

RUN python3 -m venv /app/venv

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
# (Optional, depending on usage)
# COPY . /app
