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
    
    # Load API keys
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")
    
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
            
        if missing_keys:
            error_message = (
                f"Missing required environment variables: {', '.join(missing_keys)}.\n\n"
                "-------------------------------------------------------------------\n"
                "SETUP INSTRUCTIONS:\n"
                "1. Create a file named '.env' in the project root directory.\n"
                "2. Copy the contents of '.env.template' (if available) or add the following:\n\n"
                "GROQ_API_KEY=your_groq_api_key_here\n"
                "TMDB_API_KEY=your_tmdb_api_key_here\n\n"
                "Where to get keys:\n"
                "- GROQ_API_KEY: https://console.groq.com/keys\n"
                "- TMDB_API_KEY: https://www.themoviedb.org/settings/api\n"
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

# Run validation on import to ensure fail-fast behavior if preferred,
# or let the main application call Config.validate()
# For this request, we won't auto-execute validate() at module level to avoid import side-effects,
# but it is ready to be called.
