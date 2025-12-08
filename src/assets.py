import asyncio
import aiohttp
import os
import re
import urllib.parse
import edge_tts
from typing import List, Dict, Any

class AssetGenerator:
    def __init__(self, output_directory: str):
        """
        Initialize the AssetGenerator with an output directory.
        
        Args:
            output_directory (str): Path to the directory where assets will be saved.
        """
        self.output_directory = output_directory
        if not os.path.exists(self.output_directory):
            os.makedirs(self.output_directory, exist_ok=True)
        # Limit concurrent image downloads to 1 to avoid rate limits
        self.semaphore = asyncio.Semaphore(1)

    def _clean_filename(self, text: str) -> str:
        """
        Ensure filenames are filesystem-safe.
        
        Args:
            text (str): The text to convert into a safe filename.
            
        Returns:
            str: A filesystem-safe filename string.
        """
        # Remove any character that isn't alphanumeric, space, underscore, or hyphen
        cleaned_text = re.sub(r'[^\w\s-]', '', text)
        # Replace spaces with underscores
        cleaned_text = re.sub(r'[\s]+', '_', cleaned_text)
        # Strip leading/trailing underscores/hyphens
        return cleaned_text.strip('-_')

    async def download_image(self, prompt: str, index: int) -> bool:
        """
        Download an image from Pollinations.ai based on the prompt.
        
        Args:
            prompt (str): The prompt to generate the image.
            index (int): The index of the scene (used for filename).
            
        Returns:
            bool: True if download was successful, False otherwise.
        """
        encoded_prompt = urllib.parse.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&model=flux&nologo=true"
        filename = f"scene_{index}.jpg"
        filepath = os.path.join(self.output_directory, filename)

        async with self.semaphore:
            for attempt in range(5):
                try:
                    timeout = aiohttp.ClientTimeout(total=60)
                    # Disable SSL verification to avoid common local python cert errors on macOS
                    connector = aiohttp.TCPConnector(ssl=False)
                    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                        async with session.get(url) as response:
                            if response.status == 200:
                                with open(filepath, 'wb') as f:
                                    f.write(await response.read())
                                print(f"Successfully downloaded: {filename}")
                                # Polite cooldown
                                await asyncio.sleep(5)
                                return True
                            elif response.status == 429:
                                wait_time = 5 * (attempt + 1)
                                print(f"Rate limited (429) for {filename}. Retrying in {wait_time}s... (Attempt {attempt+1}/5)")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                print(f"Failed to download image (Status {response.status}): {url}")
                                return False
                except asyncio.TimeoutError:
                    print(f"Timeout while downloading image for prompt: {prompt}")
                    return False
                except Exception as e:
                    print(f"Error downloading image: {e}")
                    return False
            
            print(f"Failed to download {filename} after 5 attempts due to rate limits.")
            return False

    async def generate_audio(self, text: str, index: int, voice: str = 'en-US-ChristopherNeural') -> bool:
        """
        Generate audio from text using Microsoft Edge TTS.
        
        Args:
            text (str): The text to convert to speech.
            index (int): The index of the scene (used for filename).
            voice (str): The voice to use. Defaults to 'en-US-ChristopherNeural'.
            
        Returns:
            bool: True if generation was successful, False otherwise.
        """
        filename = f"scene_{index}.mp3"
        filepath = os.path.join(self.output_directory, filename)
        
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(filepath)
            print(f"Successfully generated audio: {filename}")
            return True
        except Exception as e:
            print(f"Error generating audio: {e}")
            return False

    async def generate_all_assets(self, script_json: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Generate all assets for the provided script concurrently.
        
        Args:
            script_json (dict): The script dictionary containing a 'scenes' list.
            
        Returns:
            List[dict]: A list of dictionaries with asset paths for each scene.
        """
        tasks = []
        for index, scene in enumerate(script_json.get('scenes', []), start=1):
            tasks.append(self._process_single_scene(index, scene))
        
        return await asyncio.gather(*tasks)

    async def _process_single_scene(self, index: int, scene: Dict[str, str]) -> Dict[str, Any]:
        """
        Helper method to process a single scene's assets concurrently.
        """
        image_task = self.download_image(scene.get('visual_prompt', ''), index)
        audio_task = self.generate_audio(scene.get('narration', ''), index)
        
        image_success, audio_success = await asyncio.gather(image_task, audio_task)
        
        return {
            "index": index,
            "image_path": os.path.join(self.output_directory, f"scene_{index}.jpg") if image_success else None,
            "audio_path": os.path.join(self.output_directory, f"scene_{index}.mp3") if audio_success else None
        }
