import sys
import os
import unittest
from unittest.mock import MagicMock, patch
import logging

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))

from moviedbapi import MovieDBClient

# Configure logging to see output during tests
logging.basicConfig(level=logging.INFO)

class TestMovieDBClient(unittest.TestCase):
    def setUp(self):
        self.v3_key = "12345678901234567890123456789012" # 32 chars
        self.v4_token = "A" * 100 # Long token
        self.client = MovieDBClient(self.v4_token) # Default client for method tests

    def test_init_v3_key(self):
        client = MovieDBClient(self.v3_key)
        self.assertEqual(client.session.params['api_key'], self.v3_key)
        self.assertNotIn("Authorization", client.session.headers)
        self.assertEqual(client.session.headers['accept'], "application/json")

    def test_init_v4_token(self):
        client = MovieDBClient(self.v4_token)
        self.assertEqual(client.session.headers['Authorization'], f"Bearer {self.v4_token}")
        self.assertNotIn("api_key", client.session.params)
        self.assertEqual(client.session.headers['accept'], "application/json")

    @patch('requests.Session.get')
    def test_search_movie_exact_match(self, mock_get):
        # Mock response for exact match
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"title": "Inception", "id": 1},
                {"title": "Inception 2", "id": 2}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test
        result = self.client.search_movie("Inception")
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], "Inception")
        self.assertEqual(result['id'], 1)

    @patch('requests.Session.get')
    def test_search_movie_closest_match(self, mock_get):
        # Mock response for partial/closest match
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"title": "Harry Potter and the Philosopher's Stone", "id": 10},
                {"title": "Harry Potter and the Chamber of Secrets", "id": 11}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test searching for "Harry Potter" should return the first result
        result = self.client.search_movie("Harry Potter")
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], "Harry Potter and the Philosopher's Stone")

    @patch('requests.Session.get')
    def test_search_movie_no_results(self, mock_get):
        # Mock empty response
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test
        result = self.client.search_movie("NonExistentMovie12345")
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_search_movie_error(self, mock_get):
        # Mock exception
        import requests
        mock_get.side_effect = requests.RequestException("API Error")

        # Test
        result = self.client.search_movie("ErrorMovie")
        self.assertIsNone(result)

    @patch('requests.Session.get')
    def test_get_movie_details_success(self, mock_get):
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "title": "Inception",
            "release_date": "2010-07-16",
            "tagline": "Your mind is the scene of the crime.",
            "overview": "Cobb, a skilled thief...",
            "credits": {
                "cast": [
                    {"name": "Leonardo DiCaprio"},
                    {"name": "Joseph Gordon-Levitt"},
                    {"name": "Elliot Page"},
                    {"name": "Tom Hardy"}
                ]
            }
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test
        result = self.client.get_movie_details(27205)
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], "Inception")
        self.assertEqual(result['year'], "2010")
        self.assertEqual(result['tagline'], "Your mind is the scene of the crime.")
        self.assertEqual(result['actors'], "Leonardo DiCaprio, Joseph Gordon-Levitt, Elliot Page")

    @patch('requests.Session.get')
    def test_get_movie_details_missing_fields(self, mock_get):
        # Mock response with minimal data
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "title": "Mystery Movie"
            # Missing release_date, tagline, overview, credits
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        # Test
        result = self.client.get_movie_details(999)
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], "Mystery Movie")
        self.assertEqual(result['year'], "")
        self.assertEqual(result['tagline'], "")
        self.assertEqual(result['plot'], "")
        self.assertEqual(result['actors'], "")

    @patch('requests.Session.get')
    def test_get_movie_details_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("API Error")

        result = self.client.get_movie_details(0)
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
