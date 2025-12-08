import requests

import logging

logger = logging.getLogger(__name__)

class MovieDBClient:
    """
    Client for interacting with The Movie Database (TMDB) API v3.
    """
    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str):
        """
        Initialize the client with an API key (v3) or Read Access Token (v4).
        
        Args:
            api_key (str): The TMDB API Key (v3) or Read Access Token (v4).
        """
        self.api_key = api_key
        self.session = requests.Session()
        
        # Common headers
        self.session.headers.update({
            "accept": "application/json"
        })

        # Heuristic: v3 API keys are 32 chars, v4 tokens are much longer (JWT)
        if len(api_key) > 40:
            # Assume v4 Read Access Token (Bearer Auth)
            self.session.headers.update({
                "Authorization": f"Bearer {self.api_key}"
            })
        else:
            # Assume v3 API Key (Query Param)
            self.session.params["api_key"] = self.api_key

    def search_movie(self, query: str) -> dict | None:
        """
        Search for a movie by query string.

        Args:
            query (str): The movie title to search for.

        Returns:
            dict | None: The movie data if found, else None.
        """
        url = f"{self.BASE_URL}/search/movie"
        params = {"query": query}
        
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])

            if not results:
                logger.info(f"No results found for query: '{query}'")
                return None

            # Check for exact match (case-insensitive)
            query_lower = query.lower()
            for movie in results:
                if movie.get("title", "").lower() == query_lower:
                    logger.info(f"Exact match found for: '{query}'")
                    return movie

            # If no exact match, return the first result
            first_result = results[0]
            logger.info(f"Exact match not found for '{query}', using closest match: '{first_result.get('title')}'")
            return first_result

        except requests.RequestException as e:
            logger.error(f"Error searching for movie '{query}': {e}")
            return None

    def get_movie_details(self, movie_id: int) -> dict | None:
        """
        Fetch full movie details including credits.

        Args:
            movie_id (int): The TMDB movie ID.

        Returns:
            dict | None: A structured dictionary with movie details, or None on error.
        """
        url = f"{self.BASE_URL}/movie/{movie_id}"
        params = {"append_to_response": "credits"}

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # Extract year from release_date
            release_date = data.get("release_date", "")
            year = release_date[:4] if release_date else ""

            # Extract top 3 actors
            cast = data.get("credits", {}).get("cast", [])
            top_actors = [member.get("name") for member in cast[:3]]
            actors_str = ", ".join(top_actors)

            return {
                "title": data.get("title", ""),
                "year": year,
                "tagline": data.get("tagline", ""),
                "plot": data.get("overview", ""),
                "actors": actors_str
            }

        except requests.RequestException as e:
            logger.error(f"Error fetching details for movie ID '{movie_id}': {e}")
            return None
