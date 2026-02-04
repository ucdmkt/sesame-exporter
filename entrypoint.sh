#!/bin/bash

# Install the package and its dependencies
uv pip install --system .

# Run the exporter
exec sesame-exporter "$@"
