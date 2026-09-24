import os
import sys

# Tests import the backend as a package rooted at backend/ (same as uvicorn does).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
