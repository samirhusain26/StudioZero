import json
import logging
import os
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

def _load_settings_file() -> dict:
    """Load settings overrides from output/settings.json (or $STORY_SETTINGS_FILE) if it exists."""
    settings_path = Path(
        os.getenv("STORY_SETTINGS_FILE")
        or Path(__file__).resolve().parent.parent / "output" / "settings.json"
    )
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
_video_gen = _settings.get("video_generation", {})


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
    TTS_MODEL = _models.get("tts_model") or os.getenv("TTS_MODEL", "gemini-2.5-flash-preview-tts")

    # fal.ai API key (for multi-model video generation)
    FAL_KEY = _get("FAL_KEY")

    # Video generation model selection (from settings.json video_generation section)
    ACTIVE_VIDEO_MODEL = _video_gen.get("active_model") or os.getenv("ACTIVE_VIDEO_MODEL", "veo-3.1-fast")
    ACTIVE_VIDEO_TIER = _video_gen.get("active_tier") or os.getenv("ACTIVE_VIDEO_TIER", "recommended")
    VIDEO_MAX_BUDGET = float(_video_gen.get("max_budget", os.getenv("VIDEO_MAX_BUDGET", "10.0")))
    VIDEO_AUTO_DOWNGRADE = _video_gen.get("auto_downgrade", True)

    # Series audio policy (review B3): clips keep the model's native audio where the model
    # has it (requested and priced); clips without audio get silence; the final episode
    # always has one AAC 48 kHz stereo track. There is no narration or TTS step in a series.
    SERIES_NATIVE_AUDIO = os.getenv("SERIES_NATIVE_AUDIO", "1") not in ("0", "false", "no")

    # Recap music: "catalog" = a CC0 track from the motion engine's music catalog (local
    # sources, licence recorded); "none" = narration only. assets/music is never used:
    # its licences are unknown (contract v2 refuses unknown licences).
    RECAP_MUSIC = os.getenv("RECAP_MUSIC", "catalog")
    MUSIC_CATALOG = PROJECT_ROOT.parent / "motion" / "music" / "catalog.json"

    # Caption font: an OFL font shipped with the engine (fonts/, licence next to it)
    FONTS_DIR = PROJECT_ROOT / "fonts"
    CAPTION_FONT = "Fraunces Black"  # family name inside fonts/fraunces-latin-900-normal.woff

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
    def reload_settings(cls):
        """Reload settings from disk so API-driven changes take effect immediately."""
        settings = _load_settings_file()
        creds = settings.get("credentials", {})
        vg = settings.get("video_generation", {})
        models = settings.get("models", {})
        # Models apply to the next run without a restart (review B5)
        cls.GEMINI_MODEL_NAME = models.get("llm_model") or os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        cls.GEMINI_IMAGE_MODEL = models.get("image_model") or os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
        cls.TTS_MODEL = models.get("tts_model") or os.getenv("TTS_MODEL", "gemini-2.5-flash-preview-tts")
        cls.FAL_KEY = creds.get("FAL_KEY") or os.getenv("FAL_KEY") or ""
        cls.export_fal_key()
        # Refresh video generation settings
        cls.ACTIVE_VIDEO_MODEL = vg.get("active_model") or os.getenv("ACTIVE_VIDEO_MODEL", "veo-3.1-fast")
        cls.ACTIVE_VIDEO_TIER = vg.get("active_tier") or os.getenv("ACTIVE_VIDEO_TIER", "recommended")
        cls.VIDEO_MAX_BUDGET = float(vg.get("max_budget", os.getenv("VIDEO_MAX_BUDGET", "10.0")))
        cls.VIDEO_AUTO_DOWNGRADE = vg.get("auto_downgrade", True)

    @classmethod
    def export_fal_key(cls):
        """fal_client reads only the FAL_KEY environment variable (review B5)."""
        if cls.FAL_KEY and not os.environ.get("FAL_KEY"):
            os.environ["FAL_KEY"] = cls.FAL_KEY

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


# A FAL_KEY from output/settings.json reaches fal_client too (review B5).
Config.export_fal_key()
