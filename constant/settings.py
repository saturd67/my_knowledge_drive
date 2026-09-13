"""Setting keys, and the values the database is seeded with.

The setting table is the source of truth. The values below are only used to
create the rows the first time the database is built - nothing falls back to
them at read time, so changing one here does not change a database that has
already been seeded.

The three path settings are stored relative to BASE_DIR so the database stays
valid if the project folder moves; SettingService.get_path() resolves them.
"""

PATHS_INPUT_DIR = "paths.input_dir"
PATHS_OUTPUT_DIR = "paths.output_dir"
PATHS_CHROMA_STORE = "paths.chroma_store"

DRIVE_FOLDER_ID = "drive.folder_id"
DRIVE_SERVICE_ACCOUNT_FILE = "drive.service_account_file"
DRIVE_SCOPE = "drive.scope"

EMBEDDING_MODEL = "embedding.model"
EMBEDDING_COLLECTION = "embedding.collection"
EMBEDDING_RESULTS_PER_QUERY = "embedding.results_per_query"

# Resolved against BASE_DIR when they are not already absolute.
RELATIVE_TO_BASE_DIR = (
    PATHS_INPUT_DIR,
    PATHS_OUTPUT_DIR,
    PATHS_CHROMA_STORE,
)

SETTING_DEFAULT_VALUES = (
    (PATHS_INPUT_DIR, "resources\\files"),
    (PATHS_OUTPUT_DIR, "resources\\converted_files"),
    (PATHS_CHROMA_STORE, "resources\\my_chroma_store"),
    (DRIVE_FOLDER_ID, "1qdWetXw2gHA4RV22pZAoc-h_cEQBwoUi"),
    (DRIVE_SERVICE_ACCOUNT_FILE, "C:/secrets/my_knowledge_drive_service_account.json"),
    (DRIVE_SCOPE, "https://www.googleapis.com/auth/drive.readonly"),
    (EMBEDDING_MODEL, "all-MiniLM-L6-v2"),
    (EMBEDDING_COLLECTION, "my_knowledge_drive"),
    (EMBEDDING_RESULTS_PER_QUERY, "5"),
)
