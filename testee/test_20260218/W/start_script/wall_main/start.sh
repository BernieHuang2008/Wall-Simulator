#!/bin/bash

# creat venv
python3 -m venv wall_main.venv
source wall_main.venv/bin/activate

# Install Python dependencies (flask, scapy, verify netifaces) inside venv
./wall_main.venv/bin/pip3 install scapy netifaces

# Run main script using venv python
nohup ./wall_main.venv/bin/python3 wall_main/main.py > wall_main/wall_main.log 2>&1 &
