import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

def _load_settings_file() -> dict:
    """Load settings overrides from output/settings.json if it exists."""
    settings_path = Path(__file__).resolve().parent.parent / "output" / "settings.json"
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            return data
        except Exception:
            pass
    return {}

_settings = _load_settings_file()
_creds = _settings.get("credentials", {})
_models = _settings.get("models", {})


def _get(key: str, default: str = "") -> str:
    """Return settings file value, then env var, then default."""
    return _creds.get(key) or os.getenv(key) or default


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
    PROJECTS_DIR = OUTPUT_DIR / "projects"
    SETTINGS_FILE = OUTPUT_DIR / "settings.json"

    # Load API keys (settings file overrides .env)
    GROQ_API_KEY = _get("GROQ_API_KEY")
    TMDB_API_KEY = _get("TMDB_API_KEY")
    PEXELS_API_KEY = _get("PEXELS_API_KEY")
    GEMINI_API_KEY = _get("GEMINI_API_KEY")

    # Gemini model for script generation (with Groq fallback)
    GEMINI_MODEL_NAME = _models.get("llm_model") or os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    GEMINI_IMAGE_MODEL = _models.get("image_model") or os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    VEO_MODEL = _models.get("video_model") or os.getenv("VEO_MODEL", "veo-3.1-lite-generate-preview")
    TTS_MODEL = _models.get("tts_model") or os.getenv("TTS_MODEL", "gemini-2.5-flash-preview-tts")

    # Google Cloud Vertex AI (for Veo 3.1 animated pipeline)
    VERTEX_PROJECT_ID = _get("VERTEX_PROJECT_ID")
    VERTEX_LOCATION = _get("VERTEX_LOCATION") or "us-central1"
    VERTEX_VEO_MODEL = os.getenv("VERTEX_VEO_MODEL", "veo-3.1")

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
    
    @staticmethod
    def safe_title(name: str) -> str:
        """Sanitize a string for use in file/directory names."""
        return "".join(c for c in name if c.isalnum() or c in " -_").strip().replace(" ", "_")

    @classmethod
    def validate(cls, mode: str = "movie"):
        """
        Validates that necessary API keys are present for the given pipeline mode.
        Raises a ValueError with instructions if keys are missing.
        """
        missing_keys = []
        warning_keys = []

        # GEMINI_API_KEY is required for all modes
        if not cls.GEMINI_API_KEY:
            missing_keys.append("GEMINI_API_KEY")

        if mode == "movie":
            # Movie pipeline needs all keys
            if not cls.TMDB_API_KEY:
                missing_keys.append("TMDB_API_KEY")
            if not cls.PEXELS_API_KEY:
                missing_keys.append("PEXELS_API_KEY")
            if not cls.GROQ_API_KEY:
                warning_keys.append("GROQ_API_KEY")
        elif mode in ("animated", "animation-script", "animation-render", "animation-series"):
            # Animation pipelines only need Gemini
            if not cls.GROQ_API_KEY:
                warning_keys.append("GROQ_API_KEY")

        if warning_keys:
            logger.warning(
                f"Optional API keys not set (fallback features unavailable): {', '.join(warning_keys)}"
            )

        if missing_keys:
            error_message = (
                f"Missing required environment variables for '{mode}' mode: {', '.join(missing_keys)}.\n\n"
                "-------------------------------------------------------------------\n"
                "SETUP INSTRUCTIONS:\n"
                "1. Create a file named '.env' in the project root directory.\n"
                "2. Copy the contents of '.env.template' (if available) or add the following:\n\n"
                "GEMINI_API_KEY=your_gemini_api_key_here\n"
                "GROQ_API_KEY=your_groq_api_key_here\n"
                "TMDB_API_KEY=your_tmdb_api_key_here\n"
                "PEXELS_API_KEY=your_pexels_api_key_here\n\n"
                "Where to get keys:\n"
                "- GEMINI_API_KEY: https://aistudio.google.com/apikey\n"
                "- GROQ_API_KEY: https://console.groq.com/keys\n"
                "- TMDB_API_KEY: https://www.themoviedb.org/settings/api\n"
                "- PEXELS_API_KEY: https://www.pexels.com/api/\n"
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
        cls.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# Run validation on import to ensure fail-fast behavior if preferred,
# or let the main application call Config.validate()
# For this request, we won't auto-execute validate() at module level to avoid import side-effects,
# but it is ready to be called.
