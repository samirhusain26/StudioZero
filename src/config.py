import os
from pathlib import Path

class Config:
    def __init__(self):
        self._secrets = {}
        # Detect if running in Colab
        try:
            # Check if get_ipython exists in globals (standard way to check for IPython/Colab)
            # We also check if 'google.colab' is in the string representation of the ipython instance
            # to be extra sure, though usually just importing google.colab works too.
            # The user provided logic:
            self.is_colab = "google.colab" in str(get_ipython()) if "get_ipython" in globals() else False
        except NameError:
            self.is_colab = False

        self._load_secrets()

    def _load_secrets(self):
        if self.is_colab:
            # Production: Google Colab User Data
            try:
                from google.colab import userdata
                self._secrets["GROQ_API_KEY"] = userdata.get("GROQ_API_KEY")
            except ImportError:
                # Fallback or error handling if google.colab is not actually available
                print("Warning: Detected Colab but could not import google.colab.userdata")
        else:
            # Development: Local .env file
            from dotenv import load_dotenv
            load_dotenv()
            self._secrets["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

    def get(self, key):
        return self._secrets.get(key)
