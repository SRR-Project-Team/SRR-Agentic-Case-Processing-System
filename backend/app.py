#!/usr/bin/env python3
"""
Alternative entry point for Google Cloud Buildpacks (app.py)
This file is used when buildpacks are used instead of Dockerfile
"""
import os
import sys

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the FastAPI app
from src.api.main import app

# Export app for buildpack detection
__all__ = ['app']


























