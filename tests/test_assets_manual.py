import sys
import os

# Add src to path so we can import assets
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from assets import AssetGenerator
import shutil

def test_asset_generator():
    test_output_dir = "test_output_assets"
    
    # Clean up previous runs
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)
        
    generator = AssetGenerator(test_output_dir)
    
    # Test directory creation
    if os.path.exists(test_output_dir):
        print("PASS: Output directory created.")
    else:
        print("FAIL: Output directory not created.")
        
    # Test clean_filename
    test_cases = [
        ("Hello World!", "Hello_World"),
        ("invalid/chars<>", "invalidchars"),
        ("  spaces  ", "spaces"),
        ("My-File_Name", "My-File_Name"),
        ("File Name with 123", "File_Name_with_123")
    ]
    
    for input_text, expected in test_cases:
        result = generator._clean_filename(input_text)
        if result == expected:
            print(f"PASS: '{input_text}' -> '{result}'")
        else:
            print(f"FAIL: '{input_text}' -> '{result}' (Expected: '{expected}')")

    # Clean up
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)

if __name__ == "__main__":
    test_asset_generator()
