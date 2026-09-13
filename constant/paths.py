from pathlib import Path

# Where the app is installed. Not configuration - every configurable path is a
# row in the setting table, stored relative to this.
BASE_DIR = str(Path(__file__).parent.parent)

DB_PATH = BASE_DIR + "\\resources\\knowledge_drive.db"
