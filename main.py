"""Local development entry point. Run with .venv/bin/python main.py."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000,
                ws_max_size=3 * 1024 * 1024, ws_max_queue=1)
