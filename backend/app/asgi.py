"""Production entry point.

Kept separate from main.py on purpose: this module builds the app at import time, which requires
every environment variable to be set. Tests import create_app from main.py and pass their own
settings, so they never touch this file.

    uvicorn backend.app.asgi:app --host 0.0.0.0 --port $PORT
"""
from backend.app.main import create_app

app = create_app()
