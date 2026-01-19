import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """
    Configuration class to manage environment variables and directory paths.
    """
    
    # Define project root relative to this file (src/config.py)
    # .parent is src/, .parent.parent is project root
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    
    # Define directories using pathlib for cross-platform compatibility
    ASSETS_DIR = PROJECT_ROOT / "assets"
    OUTPUT_DIR = PROJECT_ROOT / "output"
    TEMP_DIR = OUTPUT_DIR / "temp"
    FINAL_DIR = OUTPUT_DIR / "final"
    LOGS_DIR = OUTPUT_DIR / "pipeline_logs"
    
    # Load API keys
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")
    PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

    # Gemini model for script generation (with Groq fallback)
    GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-flash-latest")

    # Google service account credentials for Drive and Sheets
    DRIVE_APPLICATION_CREDENTIALS = os.getenv("DRIVE_APPLICATION_CREDENTIALS")

    # Google Drive folder IDs for batch runner uploads
    DRIVE_VIDEO_FOLDER_ID = os.getenv("DRIVE_VIDEO_FOLDER_ID")
    DRIVE_LOGS_FOLDER_ID = os.getenv("DRIVE_LOGS_FOLDER_ID")

    # Google Sheet URL for batch processing queue
    BATCH_SHEET_URL = os.getenv("BATCH_SHEET_URL")

    # iCloud export path (optional, defaults to ~/Library/Mobile Documents/com~apple~CloudDocs/StudioZero/Videos)
    ICLOUD_EXPORT_PATH = os.getenv(
        "ICLOUD_EXPORT_PATH",
        str(Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "StudioZero" / "Videos")
    )
    
    @classmethod
    def validate(cls):
        """
        Validates that necessary API keys are present.
        Raises a ValueError with instructions if keys are missing.
        """
        missing_keys = []
        if not cls.GROQ_API_KEY:
            missing_keys.append("GROQ_API_KEY")
        if not cls.TMDB_API_KEY:
            missing_keys.append("TMDB_API_KEY")
        if not cls.PEXELS_API_KEY:
            missing_keys.append("PEXELS_API_KEY")
        # Note: GEMINI_API_KEY is not required - Cloud TTS uses service account credentials
        # Set GOOGLE_APPLICATION_CREDENTIALS env var or use gcloud auth application-default login

        if missing_keys:
            error_message = (
                f"Missing required environment variables: {', '.join(missing_keys)}.\n\n"
                "-------------------------------------------------------------------\n"
                "SETUP INSTRUCTIONS:\n"
                "1. Create a file named '.env' in the project root directory.\n"
                "2. Copy the contents of '.env.template' (if available) or add the following:\n\n"
                "GROQ_API_KEY=your_groq_api_key_here\n"
                "TMDB_API_KEY=your_tmdb_api_key_here\n"
                "PEXELS_API_KEY=your_pexels_api_key_here\n\n"
                "Where to get keys:\n"
                "- GROQ_API_KEY: https://console.groq.com/keys\n"
                "- TMDB_API_KEY: https://www.themoviedb.org/settings/api\n"
                "- PEXELS_API_KEY: https://www.pexels.com/api/\n\n"
                "For Gemini TTS (Google Cloud Text-to-Speech):\n"
                "- Enable Cloud Text-to-Speech API in GCP Console\n"
                "- Set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json\n"
                "- Or run: gcloud auth application-default login\n"
                "-------------------------------------------------------------------\n"
            )
            raise ValueError(error_message)

    @classmethod
    def ensure_directories(cls):
        """
        Ensures that the content directories exist.
        """
        cls.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        cls.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cls.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        cls.FINAL_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Run validation on import to ensure fail-fast behavior if preferred,
# or let the main application call Config.validate()
# For this request, we won't auto-execute validate() at module level to avoid import side-effects,
# but it is ready to be called.
