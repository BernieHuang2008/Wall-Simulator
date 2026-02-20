#!/bin/bash

# use venv
source /app/venv/bin/activate

# Install Python dependencies (flask, scapy, verify netifaces) inside venv
/app/venv/bin/pip3 install scapy netifaces

# Run main script using venv python
nohup /app/venv/bin/python3 proxy/proxy_client.py > proxy/proxy_client.log 2>&1 &
