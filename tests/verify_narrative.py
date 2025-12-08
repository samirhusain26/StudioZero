
import sys
import os
from unittest.mock import MagicMock

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def run_tests():
    try:
        from src.narrative import StoryGenerator
        print("Successfully imported StoryGenerator")
        
        # Instantiate
        # we can mock Config if needed, but assuming os.getenv returns None is safe for init usually,
        # unless Groq client validates immediately.
        # To be safe, we can mock the Groq client injection or Config.
        generator = StoryGenerator()
        print("Successfully instantiated StoryGenerator")
        
        # Mocking the API call to test generate_script logic without using API quota/keys
        mock_response = MagicMock()
        mock_response.choices[0].message.content = """
        {
          "title": "Mock Movie",
          "scenes": [
            {
              "narration": "Scene 1 narration",
              "visual_prompt": "Scene 1 visual"
            },
            {
                "narration": "Scene 2",
                "visual_prompt": "Visual 2"
            },
            {
                "narration": "Scene 3",
                "visual_prompt": "Visual 3"
            },
            {
                "narration": "Scene 4",
                "visual_prompt": "Visual 4"
            },
            {
                "narration": "Scene 5",
                "visual_prompt": "Visual 5"
            }
          ]
        }
        """
        
        # Replace the real method with a mock that returns our structure
        generator._generate_with_retry = MagicMock(return_value=mock_response)
        
        # Test Data
        movie_data = {
            "title": "Test Movie",
            "plot": "A test plot",
            "actors": ["Actor A", "Actor B"]
        }
        style = "Comedy"
        
        # Call the method
        print("Calling generate_script...")
        script = generator.generate_script(movie_data, style)
        
        # Validation
        if script['title'] == "Mock Movie":
            print("SUCCESS: Script generated and parsed correctly.")
            print(f"Scenes count: {len(script['scenes'])}")
        else:
            print("FAILURE: Script content mismatch.")
            
    except ImportError as e:
        print(f"ImportError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        # In case init failed due to keys, we print it but don't fail hard if we just want to verify structure.
        # But here we want to verify the method logic.
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
