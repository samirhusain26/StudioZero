import json
import groq
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.config import Config

class StoryGenerator:
    """
    Generates story content using the Groq API.
    """
    def __init__(self):
        """
        Initialize the Groq client.
        """
        self.client = groq.Groq(api_key=Config.GROQ_API_KEY)

    @retry(
        retry=retry_if_exception_type(groq.RateLimitError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def _generate_with_retry(self, **kwargs):
        """
        Wraps the Groq API call with retry logic for rate limits.
        
        Args:
            **kwargs: Arguments to pass to the chat.completions.create method.
            
        Returns:
            The API response.
        """
        return self.client.chat.completions.create(**kwargs)

    def generate_script(self, movie_data, style):
        """
        Generates a video script based on movie data and style.

        Args:
            movie_data (dict): Dictionary containing 'title', 'plot', and 'actors'.
            style (str): The requested style of the script (e.g., 'Noir', 'Comedy').

        Returns:
            dict: The generated script as a dictionary.
        """
        system_prompt = (
            "You are a charismatic screenwriter. You must output strictly valid JSON. "
            "Do not include markdown formatting."
        )

        user_prompt = (
            f"Create a video script for a movie with the following details:\n"
            f"Title: {movie_data.get('title')}\n"
            f"Plot: {movie_data.get('plot')}\n"
            f"Actors: {', '.join(movie_data.get('actors', []))}\n"
            f"Style: {style}\n\n"
            "The output must be strictly valid JSON observing this schema:\n"
            "{\n"
            "  'title': 'Video Title',\n"
            "  'scenes': [\n"
            "    {\n"
            "      'narration': 'The voiceover text...',\n"
            "      'visual_prompt': 'A detailed description for an AI image generator...'\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Request exactly 5 scenes."
        )

        response = self._generate_with_retry(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        return json.loads(content)
