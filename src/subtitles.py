"""
Subtitles module for generating Hormozi-style ASS subtitles.

This module creates single-word animated subtitles from Whisper transcription
segments using pysubs2. Each word appears one at a time in a clean,
slightly transparent white.
"""

import string
from pathlib import Path
from typing import List

import pysubs2
from pysubs2 import SSAFile, SSAEvent, SSAStyle, Color


# ASS color format is &HAABBGGRR& (Alpha, Blue, Green, Red)
# For pysubs2 Color: Color(r, g, b, a) where a=0 is opaque, a=255 is transparent
WHITE = Color(255, 255, 255, 0)          # &H00FFFFFF
WHITE_SEMI = Color(255, 255, 255, 40)    # Slightly transparent white for subtitles
BLACK = Color(0, 0, 0, 0)                # &H00000000
BLACK_SEMI = Color(0, 0, 0, 128)         # &H80000000 (semi-transparent for background box)


def generate_karaoke_subtitles(
    whisper_segments: List[dict],
    output_ass_path: str,
    words_per_line: int = 1,
) -> str:
    """
    Generates Hormozi-style ASS subtitles from Whisper transcription segments.

    Creates single-word subtitles where each word appears one at a time
    in a clean, slightly transparent white.

    Args:
        whisper_segments: List of Whisper segment dictionaries. Each segment
            should have 'words' list with 'word', 'start', 'end' keys.
            Example:
            [
                {
                    "text": "Hello world",
                    "start": 0.0,
                    "end": 1.0,
                    "words": [
                        {"word": "Hello", "start": 0.0, "end": 0.5},
                        {"word": "world", "start": 0.5, "end": 1.0}
                    ]
                }
            ]
        output_ass_path: Path where the ASS file will be saved.
        words_per_line: Number of words to display per subtitle line.

    Returns:
        The path to the generated ASS file.

    Raises:
        ValueError: If no words are found in the segments.
    """
    # Create new subtitle file
    subs = SSAFile()

    # Set video resolution for 1080p
    subs.info["PlayResX"] = "1920"
    subs.info["PlayResY"] = "1080"

    # Create Hormozi style
    style_name = _create_hormozi_style(subs)

    # Extract all words with timestamps from segments
    all_words = _extract_words(whisper_segments)

    if not all_words:
        raise ValueError("No words found in whisper segments")

    # Group words into lines
    word_groups = [
        all_words[i:i + words_per_line]
        for i in range(0, len(all_words), words_per_line)
    ]

    # Create subtitle events for each word highlight
    for group in word_groups:
        _create_karaoke_events(subs, group, style_name)

    # Ensure output directory exists and save
    output_path = Path(output_ass_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subs.save(str(output_path))

    return str(output_path)


def _create_hormozi_style(subs: SSAFile) -> str:
    """
    Creates and adds the Hormozi style to the subtitle file.

    Style settings:
        - Font: Arial Black (fallback: Roboto-Bold)
        - FontSize: 80 (large for 1080p Hormozi style)
        - PrimaryColor: White
        - OutlineColor: Black
        - BackColour: Semi-transparent black for shadow
        - Alignment: Middle Center (vertically centered)

    Args:
        subs: The SSAFile to add the style to.

    Returns:
        The name of the created style.
    """
    style_name = "Hormozi"

    style = SSAStyle(
        fontname="Arial Black",
        fontsize=80,
        bold=True,
        primarycolor=WHITE_SEMI,
        secondarycolor=WHITE_SEMI,
        outlinecolor=BLACK,
        backcolor=BLACK_SEMI,
        outline=4,
        shadow=2,
        alignment=5,  # Middle center (numpad style: 5 = center)
        marginl=20,
        marginr=20,
        marginv=0,
        borderstyle=1,  # Outline + shadow (cleaner look)
    )

    subs.styles[style_name] = style
    return style_name


def _extract_words(whisper_segments: List[dict]) -> List[dict]:
    """
    Extracts all words with timestamps from Whisper segments.

    Args:
        whisper_segments: List of Whisper segment dictionaries.

    Returns:
        List of word dictionaries with 'word', 'start', 'end' keys.
    """
    all_words = []

    for segment in whisper_segments:
        words = segment.get("words", [])

        if not words:
            # Fallback: treat entire segment text as a single word
            text = segment.get("text", "").strip()
            if text:
                all_words.append({
                    "word": text,
                    "start": segment.get("start", 0),
                    "end": segment.get("end", 0),
                })
        else:
            for word_info in words:
                word_text = word_info.get("word", "").strip()
                if word_text:
                    all_words.append({
                        "word": word_text,
                        "start": word_info.get("start", 0),
                        "end": word_info.get("end", 0),
                    })

    return all_words


def _create_karaoke_events(
    subs: SSAFile,
    word_group: List[dict],
    style_name: str,
) -> None:
    """
    Creates subtitle events for a group of words.

    For single-word mode (Hormozi style), displays one word at a time
    in a clean, slightly transparent white.

    Args:
        subs: The SSAFile to add events to.
        word_group: List of word dictionaries for this line.
        style_name: Name of the style to apply.
    """
    if not word_group:
        return

    # Fixed position at center of 1080p screen (960, 540)
    position_tag = r"{\pos(960,540)}"

    for word_info in word_group:
        # Calculate timing in milliseconds
        start_ms = int(word_info["start"] * 1000)
        end_ms = int(word_info["end"] * 1000)

        # Ensure minimum duration of 100ms
        if end_ms - start_ms < 100:
            end_ms = start_ms + 100

        # Clean word: lowercase, no punctuation
        clean_word = word_info["word"].lower().strip(string.punctuation)
        line_text = position_tag + clean_word

        # Create subtitle event
        event = SSAEvent(
            start=start_ms,
            end=end_ms,
            text=line_text,
            style=style_name,
        )
        subs.events.append(event)
