#!/bin/bash

# Upgrade pip
python3 -m pip install --upgrade pip

# Install all dependencies from requirements.txt
pip install -r requirements.txt

python3 retrieval_s3_files.py