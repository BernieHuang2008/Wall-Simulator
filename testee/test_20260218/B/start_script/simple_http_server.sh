#!/bin/bash

nohup python3 -m http.server 5001 --directory / > simple_http_server.log 2>&1 &
