#!/bin/bash
# Install dependencies if not already installed
# pip install -r requirements.txt

# Format code
# python3 -m black app.py

# Run the Flask app
export PYTHONWARNINGS="ignore:application data after close notify,ignore:ResourceWarning,ignore:SSL"
python3 app.py
