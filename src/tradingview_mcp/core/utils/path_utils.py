# tradingview_mcp/core/utils/path_utils.py
import os

def get_project_root():
    """Navigates up from the current file to find the project root (where pyproject.toml is)."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    while True:
        if "pyproject.toml" in os.listdir(current_dir):
            return current_dir
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir: # Reached the filesystem root
            # Fallback for safety, though it shouldn't be needed in this project structure
            return os.getcwd()
        current_dir = parent_dir
