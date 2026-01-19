import wikipediaapi
import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# TMDB image base URL - use original size for high quality
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"

class MovieDBClient:
    """
    Client for interacting with Wikipedia to fetch movie details,
    with a fallback to The Movie Database (TMDB) API v3.
    """
    TMDB_BASE_URL = "https://api.themoviedb.org/3"
    
    def __init__(self, tmdb_api_key: str = None):
        """
        Initialize the client.
        
        Args:
            tmdb_api_key (str, optional): The TMDB API Key. Required for fallback functionality.
        """
        # Wikipedia setup
        self.wiki = wikipediaapi.Wikipedia(
            user_agent='StudioZero/1.0 (contact@example.com)',
            language='en'
        )

        # TMDB setup
        self.tmdb_api_key = tmdb_api_key
        self.tmdb_session = None
        
        if self.tmdb_api_key:
            self.tmdb_session = requests.Session()
            self.tmdb_session.headers.update({
                "accept": "application/json"
            })
            # Handle Bearer token (v4) vs Query param (v3)
            if len(tmdb_api_key) > 40:
                self.tmdb_session.headers.update({
                    "Authorization": f"Bearer {self.tmdb_api_key}"
                })
            else:
                self.tmdb_session.params["api_key"] = self.tmdb_api_key

    def search_movie(self, query: str) -> dict | None:
        """
        Search for a movie by query string.
        Prioritizes Wikipedia, falls back to TMDB if configured.
        
        Returns:
            dict | None: A result dictionary with 'source' ('wiki' or 'tmdb') and data.
        """
        # 1. Try Wikipedia
        wiki_result = self._search_wikipedia(query)
        if wiki_result:
            logger.info(f"Movie found on Wikipedia: {wiki_result['title']}")
            return {"source": "wiki", "data": wiki_result}
            
        # 2. Fallback to TMDB
        if self.tmdb_session:
            logger.info(f"Wikipedia search failed for '{query}'. Falling back to TMDB.")
            tmdb_result = self._search_tmdb(query)
            if tmdb_result:
                logger.info(f"Movie found on TMDB: {tmdb_result.get('title')}")
                return {"source": "tmdb", "data": tmdb_result}
        else:
            logger.warning("Wikipedia search failed and TMDB API key is not configured.")

        return None

    def get_movie_details(self, search_result: dict) -> dict | None:
        """
        Fetch full movie details based on the search result source.
        If Wikipedia returns an empty plot, automatically falls back to TMDB.
        """
        if not search_result:
            return None

        source = search_result.get("source")
        data = search_result.get("data")

        if source == "wiki":
            details = self._get_wiki_details(data)
            # Check if Wikipedia plot is empty and fallback to TMDB
            if not details.get("plot") or not details["plot"].strip():
                if self.tmdb_session:
                    logger.info("Wikipedia plot missing, switching to TMDB...")
                    tmdb_result = self._search_tmdb(details.get("title", ""))
                    if tmdb_result:
                        tmdb_details = self._get_tmdb_details(tmdb_result)
                        if tmdb_details and tmdb_details.get("plot"):
                            details["plot"] = tmdb_details["plot"]
                            details["source"] = "Wikipedia + TMDB (plot)"
                            logger.info("Successfully retrieved plot from TMDB fallback")
                else:
                    logger.warning("Wikipedia plot missing and TMDB API key not configured")
            return details
        elif source == "tmdb":
            return self._get_tmdb_details(data)
        else:
            logger.error(f"Unknown source type: {source}")
            return None

    # --- Wikipedia Helpers ---

    def _search_wikipedia(self, query: str) -> dict | None:
        # Try direct match
        page = self.wiki.page(query)
        if page.exists():
            return {"title": page.title, "page_obj": page}
            
        # Try with " (film)" suffix
        page_film = self.wiki.page(f"{query} (film)")
        if page_film.exists():
            return {"title": page_film.title, "page_obj": page_film}
            
        return None

    # Section headers to search for plot content (in priority order)
    PLOT_SECTION_HEADERS = ["Plot", "Synopsis", "Plot summary", "Premise"]

    def _get_wiki_details(self, data: dict) -> dict:
        page = data["page_obj"]

        plot_text = ""
        # Try finding plot section using multiple possible headers
        plot_section = None
        for header in self.PLOT_SECTION_HEADERS:
            plot_section = page.section_by_title(header)
            if plot_section and plot_section.text.strip():
                break
            plot_section = None

        if plot_section:
            plot_text = plot_section.text
        else:
            # Fall back to summary if no plot section found
            plot_text = page.summary if page.summary else ""

        # Extract categories as a proxy for genre
        categories = []
        for category in page.categories:
            # Clean up category names (remove 'Category:' prefix)
            clean_cat = category.replace("Category:", "").strip()
            # Filter somewhat relevant categories to keep the list sane
            if "film" in clean_cat.lower() or "movie" in clean_cat.lower():
                categories.append(clean_cat)
        
        # If too many, just take top 10
        categories = categories[:10]

        return {
            "title": page.title,
            "plot": plot_text,
            "actors": "", # Wiki parsing is hard
            "year": "",
            "tagline": "",
            "source": "Wikipedia",
            "categories": categories
        }

    # --- TMDB Helpers ---

    def _search_tmdb(self, query: str) -> dict | None:
        url = f"{self.TMDB_BASE_URL}/search/movie"
        params = {"query": query}
        
        try:
            response = self.tmdb_session.get(url, params=params)
            response.raise_for_status()
            results = response.json().get("results", [])

            if not results:
                return None

            # Exact match check
            query_lower = query.lower()
            for movie in results:
                if movie.get("title", "").lower() == query_lower:
                    return movie
            
            return results[0]

        except requests.RequestException as e:
            logger.error(f"TMDB Search Error: {e}")
            return None

    def _get_tmdb_details(self, data: dict) -> dict | None:
        movie_id = data.get("id")
        url = f"{self.TMDB_BASE_URL}/movie/{movie_id}"
        params = {"append_to_response": "credits"}

        try:
            response = self.tmdb_session.get(url, params=params)
            response.raise_for_status()
            details = response.json()

            release_date = details.get("release_date", "")
            year = release_date[:4] if release_date else ""

            cast = details.get("credits", {}).get("cast", [])
            top_actors = [member.get("name") for member in cast[:3]]
            actors_str = ", ".join(top_actors)

            genres = [g['name'] for g in details.get('genres', [])]

            return {
                "title": details.get("title", ""),
                "year": year,
                "tagline": details.get("tagline", ""),
                "plot": details.get("overview", ""),
                "actors": actors_str,
                "source": "TMDB",
                "genres": genres,
                "poster_path": details.get("poster_path", ""),
            }

        except requests.RequestException as e:
            logger.error(f"TMDB Details Error: {e}")
            return None

    def get_tmdb_metadata(self, movie_title: str) -> dict | None:
        """
        Fetch poster, year, and tagline from TMDB for a given movie title.

        Use this to supplement Wikipedia data with TMDB visuals/metadata.

        Args:
            movie_title: The movie title to search for

        Returns:
            dict with poster_path, year, tagline, or None if not found
        """
        if not self.tmdb_session:
            logger.warning("TMDB API key not configured, cannot fetch metadata")
            return None

        search_result = self._search_tmdb(movie_title)
        if not search_result:
            logger.warning(f"Could not find '{movie_title}' on TMDB for metadata")
            return None

        movie_id = search_result.get("id")
        url = f"{self.TMDB_BASE_URL}/movie/{movie_id}"

        try:
            response = self.tmdb_session.get(url)
            response.raise_for_status()
            details = response.json()

            release_date = details.get("release_date", "")
            year = release_date[:4] if release_date else ""

            return {
                "poster_path": details.get("poster_path", ""),
                "year": year,
                "tagline": details.get("tagline", ""),
                "tmdb_id": movie_id,
            }

        except requests.RequestException as e:
            logger.error(f"TMDB metadata fetch error: {e}")
            return None

    def download_poster(self, poster_path: str, output_path: str) -> str | None:
        """
        Download a movie poster from TMDB.

        Args:
            poster_path: The poster path from TMDB (e.g., "/abc123.jpg")
            output_path: Where to save the downloaded poster

        Returns:
            The output path if successful, None otherwise
        """
        if not poster_path:
            logger.warning("No poster path provided")
            return None

        poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"

        try:
            response = requests.get(poster_url, stream=True, timeout=30)
            response.raise_for_status()

            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Downloaded poster to: {output_path}")
            return output_path

        except requests.RequestException as e:
            logger.error(f"Failed to download poster: {e}")
            return None
