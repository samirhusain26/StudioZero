import sys
import os
import asyncio
import shutil

# Add src to path
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src'))
sys.path.insert(0, src_path)

from assets import AssetGenerator

async def test_download():
    test_output_dir = "test_assets_download"
    
    # Clean up previous runs
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)
        
    generator = AssetGenerator(test_output_dir)
    
    print("Attempting to download test image...")
    # Use a simple prompt
    success = await generator.download_image("A futuristic city skyline at sunset", 1)
    
    if success:
        print("PASS: Download reported success.")
        expected_file = os.path.join(test_output_dir, "scene_1.jpg")
        if os.path.exists(expected_file):
             # Check if file has some size
            size = os.path.getsize(expected_file)
            if size > 1000:
                print(f"PASS: File exists and has size {size} bytes.")
            else:
                print(f"FAIL: File exists but size is suspicious ({size} bytes).")
        else:
            print("FAIL: File not found after reported success.")
    else:
        print("FAIL: Download reported failure.")

    # Clean up
    if os.path.exists(test_output_dir):
        shutil.rmtree(test_output_dir)

if __name__ == "__main__":
    asyncio.run(test_download())
