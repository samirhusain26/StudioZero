import asyncio
import os
import subprocess
import re
import difflib
import edge_tts
import whisper
import functools
from typing import List, Dict, Any, Callable, Optional

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
        # Limit concurrent Whisper transcriptions to 1 to avoid Numba threading issues
        self.transcription_semaphore = asyncio.Semaphore(1)
        # Load Whisper model
        print("Loading Whisper model (tiny)...")
        self.whisper_model = whisper.load_model("tiny")
        print("Whisper model loaded.")

    def _align_words_with_original(self, whisper_words: List[Dict], original_text: str) -> List[Dict]:
        """
        Align Whisper-transcribed words with the original script text to correct spelling mistakes.
        
        Uses SequenceMatcher to find the best alignment between transcribed and original words,
        then replaces the Whisper word text with the original spelling while keeping the timing.
        
        Args:
            whisper_words: List of dicts with 'word', 'start', 'end' from Whisper
            original_text: The original script text used to generate the audio
            
        Returns:
            List of dicts with corrected words and original timing
        """
        if not whisper_words or not original_text:
            return whisper_words
        
        # Tokenize original text into words (handle punctuation attached to words)
        original_words = re.findall(r"[\w']+|[.,!?;:]", original_text)
        # Filter out standalone punctuation for alignment purposes
        original_words_clean = [w for w in original_words if re.match(r"[\w']+", w)]
        
        # Extract just the word strings from Whisper output for alignment
        whisper_word_strings = [w['word'].strip().lower() for w in whisper_words]
        original_words_lower = [w.lower() for w in original_words_clean]
        
        # Use SequenceMatcher to find best alignment
        matcher = difflib.SequenceMatcher(None, whisper_word_strings, original_words_lower)
        
        corrected_words = []
        used_original_indices = set()
        
        for opcode, w_start, w_end, o_start, o_end in matcher.get_opcodes():
            if opcode == 'equal':
                # Words match - use original spelling with Whisper timing
                for i, w_idx in enumerate(range(w_start, w_end)):
                    orig_idx = o_start + i
                    if orig_idx < len(original_words_clean):
                        corrected_words.append({
                            'word': original_words_clean[orig_idx],
                            'start': whisper_words[w_idx]['start'],
                            'end': whisper_words[w_idx]['end']
                        })
                        used_original_indices.add(orig_idx)
            elif opcode == 'replace':
                # Words differ - use original spelling (correct) with Whisper timing
                whisper_range = list(range(w_start, w_end))
                original_range = list(range(o_start, o_end))
                
                # Match up words by position, handling length differences
                for i, w_idx in enumerate(whisper_range):
                    if i < len(original_range):
                        orig_idx = original_range[i]
                        corrected_words.append({
                            'word': original_words_clean[orig_idx],
                            'start': whisper_words[w_idx]['start'],
                            'end': whisper_words[w_idx]['end']
                        })
                        used_original_indices.add(orig_idx)
                    else:
                        # More Whisper words than original - keep Whisper word
                        corrected_words.append(whisper_words[w_idx])
                
                # Handle extra original words (Whisper may have merged words)
                for j, orig_idx in enumerate(original_range[len(whisper_range):]):
                    if whisper_range and orig_idx < len(original_words_clean):
                        # Estimate timing by using the last matched word's end time
                        last_timing = corrected_words[-1] if corrected_words else {'start': 0, 'end': 0.1}
                        corrected_words.append({
                            'word': original_words_clean[orig_idx],
                            'start': last_timing['end'],
                            'end': last_timing['end'] + 0.1
                        })
                        used_original_indices.add(orig_idx)
            elif opcode == 'insert':
                # Words in original not in Whisper - insert with estimated timing
                for orig_idx in range(o_start, o_end):
                    if orig_idx < len(original_words_clean):
                        last_timing = corrected_words[-1] if corrected_words else {'start': 0, 'end': 0.1}
                        corrected_words.append({
                            'word': original_words_clean[orig_idx],
                            'start': last_timing['end'],
                            'end': last_timing['end'] + 0.1
                        })
                        used_original_indices.add(orig_idx)
            elif opcode == 'delete':
                # Words in Whisper not in original - skip (likely transcription noise)
                pass
        
        print(f"Word alignment: {len(whisper_words)} Whisper words -> {len(corrected_words)} corrected words")
        return corrected_words

    async def generate_audio(self, text: str, index: int, voice: str = 'en-US-AriaNeural', rate: str = '+20%') -> tuple[bool, list[dict]]:
        """
        Generate audio from text using Microsoft Edge TTS.
        
        Args:
            text (str): The text to convert to speech.
            index (int): The index of the scene (used for filename).
            voice (str): The voice to use. Defaults to 'en-US-ChristopherNeural'.
            
        Returns:
            tuple[bool, list[dict]]: (Success status, List of word timestamps)
        """
        filename = f"scene_{index}.mp3"
        filepath = os.path.join(self.output_directory, filename)
        
        try:
            # Generate audio with edge-tts
            # Using a peppy voice (AriaNeural is often good) and faster rate
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(filepath)
            print(f"Successfully generated audio: {filename}")

            # Transcribe with Whisper to get word timestamps
            # This is a separate try-except so audio generation can succeed even if Whisper fails
            word_timestamps = []
            try:
                # Serialize transcription to avoid Numba threading issues
                async with self.transcription_semaphore:
                    # Preprocess audio: convert to WAV (16kHz mono) for reliable Whisper compatibility
                    wav_path = filepath.replace('.mp3', '_temp.wav')
                    preprocess_cmd = [
                        'ffmpeg', '-y', '-i', filepath,
                        '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path
                    ]
                    subprocess.run(preprocess_cmd, capture_output=True, check=True)
                    
                    loop = asyncio.get_running_loop()
                    transcription_result = await loop.run_in_executor(
                        None, 
                        functools.partial(self.whisper_model.transcribe, wav_path, word_timestamps=True)
                    )
                    
                    # Clean up temp WAV file
                    if os.path.exists(wav_path):
                        os.remove(wav_path)

                    for segment in transcription_result.get('segments', []):
                        for word in segment.get('words', []):
                            word_timestamps.append({
                                'word': word['word'].strip(),
                                'start': word['start'],
                                'end': word['end']
                            })
                    print(f"Transcription successful: {len(word_timestamps)} words extracted")
                    
                    # Align Whisper words with original text to correct spelling mistakes
                    word_timestamps = self._align_words_with_original(word_timestamps, text)
            except Exception as whisper_error:
                print(f"Warning: Whisper transcription failed (subtitles disabled): {whisper_error}")
                # Clean up temp WAV file on error
                wav_path = filepath.replace('.mp3', '_temp.wav')
                if os.path.exists(wav_path):
                    os.remove(wav_path)
                # Continue with empty timestamps - video will render without subtitles
            
            return True, word_timestamps

        except Exception as e:
            print(f"Error generating audio: {e}")
            return False, []

    async def generate_all_assets(self, script_data: Dict[str, Any], callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
        """
        Generate all assets for the provided script concurrently.
        
        Args:
            script_data (dict): The script dictionary containing 'timeline' -> 'beats'.
            
        Returns:
            List[dict]: A list of dictionaries with asset paths for each scene/beat.
        """
        tasks = []
        
        # Determine where the beats/scenes are located
        # Support both old 'scenes' format and new 'timeline' -> 'beats' format
        if 'timeline' in script_data and 'beats' in script_data['timeline']:
            items = script_data['timeline']['beats']
        else:
            items = script_data.get('scenes', [])

        for item in items:
            # Use 'id' from beat or fallback to index if enumerate was used (but beats have explicit IDs)
            index = item.get('id') 
            tasks.append(self._process_single_scene(index, item, callback))
        
        results = await asyncio.gather(*tasks)
        # Filter out None results if any failed completely (though _process_single_scene returns dicts with None paths)
        return results

    async def _process_single_scene(self, index: int, scene_data: Dict[str, Any], callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        Helper method to process a single scene's assets.
        
        NOTE: Image generation is currently disabled. Visual prompts are logged
        but not sent to Pollinations. Base videos will be used instead.
        """
        # Map fields from potentially different schemas
        vis_prompt = scene_data.get('visual_prompt') or scene_data.get('visual_prompt', '')
        audio_text = scene_data.get('audio_script') or scene_data.get('narration', '')

        if callback:
            callback('log', f"Scene {index}: Starting asset generation (audio only - images disabled).")
            callback('data', f"Scene {index} Visual Prompt (not generating)", vis_prompt)
            callback('data', f"Scene {index} Audio Text", audio_text)

        # Image generation disabled - using base videos instead
        # The visual_prompt is still in the JSON from Groq for future use
        # image_task = self.download_image(vis_prompt, index)
        
        audio_success, audio_timestamps = await self.generate_audio(audio_text, index)
        
        return {
            "index": index,
            "image_path": None,  # Images disabled - using base videos
            "visual_prompt": vis_prompt,  # Keep prompt for reference
            "audio_path": os.path.join(self.output_directory, f"scene_{index}.mp3") if audio_success else None,
            "audio_word_timestamps": audio_timestamps if audio_success else []
        }
