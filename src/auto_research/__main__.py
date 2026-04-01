"""Support: python -m auto_research (used by venv bin wrapper when PYTHONPATH includes src)."""

from auto_research.cli import app

if __name__ == "__main__":
    app()
