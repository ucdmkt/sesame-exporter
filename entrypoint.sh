#!/bin/bash

# Install the package and its dependencies
python3 -m pip install --no-cache-dir --upgrade pip
python3 -m pip install --no-cache-dir .

# Run the exporter
exec sesame-exporter "$@"
