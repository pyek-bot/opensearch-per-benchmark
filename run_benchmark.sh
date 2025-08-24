#!/bin/bash

# Activate virtual environment
source venv/bin/activate

# Run the benchmark
python main.py

# Deactivate virtual environment when done
deactivate