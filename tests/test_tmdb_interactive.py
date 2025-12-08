import sys
import os
import logging
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from moviedbapi import MovieDBClient

# Configure logging to show info
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    print("--- TMDB API Interactive Test ---")
    
    # Get API Key from env or user input
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        print("TMDB_API_KEY not found in environment variables.")
        api_key = input("Please enter your TMDB Read Access Token (v4 Auth): ").strip()
    
    if not api_key:
        print("Error: API Key is required.")
        return

    try:
        client = MovieDBClient(api_key)
        
        while True:
            print("\n--------------------------------")
            query = input("Enter movie name to search (or 'q' to quit): ").strip()
            
            if query.lower() == 'q':
                break
                
            if not query:
                continue
                
            print(f"Searching for '{query}'...")
            movie = client.search_movie(query)
            
            if movie:
                print(f"Found: {movie.get('title')} (ID: {movie.get('id')})")
                print("Fetching full details...")
                
                details = client.get_movie_details(movie.get('id'))
                
                if details:
                    print("\n--- Movie Details ---")
                    print(f"Title:   {details.get('title')}")
                    print(f"Year:    {details.get('year')}")
                    print(f"Tagline: {details.get('tagline')}")
                    print(f"Cast:    {details.get('actors')}")
                    print(f"Plot:    {details.get('plot')}")
                else:
                    print("Error: Could not fetch movie details.")
            else:
                print("No movie found.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
