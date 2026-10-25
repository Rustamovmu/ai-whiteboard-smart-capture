# Backend

From the repository root, install `backend/requirements-lock.txt` in a Python 3.11 virtual environment and run `.venv/bin/python main.py`. The root launcher binds to 127.0.0.1:8000 with bounded WebSocket messages/queue. Use one worker.

FastAPI documentation: http://127.0.0.1:8000/docs. Tests: `.venv/bin/python -m pytest -q`. See the root README and docs/ARCHITECTURE.md for complete installation, model provisioning, APIs and local storage behavior.
