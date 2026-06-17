# tradingview_mcp/core/utils/save_utils.py
import os
import json
from datetime import datetime
from .path_utils import get_project_root

def save_result_to_json(result: dict, feature_name: str, symbol: str = "general"):
    """Saves a result dictionary to a JSON file in the result directory."""
    try:
        project_root = get_project_root()
        output_dir = os.path.join(project_root, "result")
        os.makedirs(output_dir, exist_ok=True)
        
        # Use symbol from result if available, otherwise use the provided symbol parameter
        symbol_to_use = result.get("symbol", symbol).replace("/", "-") # Sanitize for filename

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{symbol_to_use}_{feature_name}_{timestamp}.json"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    except Exception as e:
        # In a real app, you might want a more robust logging solution
        print(f"[ERROR] Failed to save '{feature_name}' result to JSON: {e}")
