import json
import logging
from pathlib import Path
from typing import List, Callable, Optional
from datetime import datetime
import groq
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.config import Config
from src.config_mappings import (
    TTS_VOICES,
    MUSIC_GENRES,
    SCENE_MOOD_SPEEDS,
    get_music_for_genre,
    get_voice_for_genre,
    get_available_voices_for_groq,
    get_lang_code_for_voice,
)


logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models - Video Director Pro Schema
# ============================================================================

class Scene(BaseModel):
    """A single scene with narration, visual search queries, and TTS customization."""
    scene_index: int = Field(..., description="The scene index (0-based)")
    narration: str = Field(
        ...,
        description="The voiceover narration for this scene (25-40 words). Conversational tone, like telling a friend what happened."
    )
    visual_queries: List[str] = Field(
        ...,
        min_length=3,
        max_length=3,
        description="3 Pexels search queries: Option 1 (Literal/Action), Option 2 (Abstract/Mood/Metaphorical), Option 3 (Atmospheric/Lighting/Vibe/Texture)"
    )
    visual_style_modifiers: List[str] = Field(
        ...,
        description="Visual style modifiers e.g. ['4k', 'cinematic lighting', 'slow motion', 'drone shot']"
    )
    # TTS Customization Fields
    mood: str = Field(
        default="neutral",
        description="The emotional mood of this scene for TTS pacing. Options: tense, suspenseful, dramatic, sad, happy, exciting, calm, mysterious, romantic, action, horror, comedic, epic, neutral"
    )
    tts_speed: float = Field(
        default=1.25,
        ge=1.0,
        le=1.6,
        description="TTS speech speed for this scene (1.0-1.6). Use 1.0-1.1 for dramatic/sad, 1.35-1.5 for action/tense."
    )


class VideoScript(BaseModel):
    """Complete video script output from the Video Director."""
    title: str = Field(..., description="The movie title")
    genre: str = Field(
        ...,
        description="The primary genre of the movie (e.g., action, thriller, horror, comedy, romance, drama, sci-fi, etc.)"
    )
    overall_mood: str = Field(
        default="neutral",
        description="The overall mood/tone for TTS voice consistency across ALL scenes. Options: tense, suspenseful, dramatic, sad, happy, exciting, calm, mysterious, romantic, action, horror, comedic, epic, neutral"
    )
    selected_voice_id: str = Field(
        ...,
        description="The selected voice ID based on genre/mood"
    )
    selected_music_file: str = Field(
        default="",
        description="The background music file (auto-selected based on genre)"
    )
    lang_code: str = Field(
        default="a",
        description="Language/accent code for TTS. 'a'=American, 'b'=British, 'e'=Spanish, 'f'=French, 'j'=Japanese, etc."
    )
    bpm: int = Field(
        ...,
        ge=60,
        le=200,
        description="Estimated tempo/BPM for the video pacing (e.g., 120)"
    )
    scenes: List[Scene] = Field(
        ...,
        min_length=6,
        max_length=6,
        description="List of exactly 6 scenes covering the full narrative arc"
    )


# ============================================================================
# StoryGenerator Class - Video Director
# ============================================================================

class StoryGenerator:
    """
    Generates structured video scripts using a Groq-powered Storyteller.

    The Storyteller creates complete movie recap scripts with:
        - Voice selection based on genre/mood
        - Background music selection
        - 6-scene narrative arc (Setup -> Catalyst -> Rising -> Twist -> Climax -> Resolution)
        - Past tense storytelling with spoilers included
        - Multi-option visual queries per scene
    """

    def __init__(self, log_dir: Optional[Path] = None):
        """
        Initialize Gemini (primary) and Groq (fallback) clients.

        Args:
            log_dir: Directory to save results. If None, uses output/pipeline_logs/
        """
        # Primary: Gemini client
        self.gemini_client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.gemini_model = Config.GEMINI_MODEL_NAME

        # Fallback: Groq client
        self.groq_client = groq.Groq(api_key=Config.GROQ_API_KEY)

        self.log_dir = log_dir or Config.LOGS_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _generate_with_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """
        Generate script using Google Gemini with structured JSON output.

        Args:
            system_prompt: The system instruction prompt
            user_prompt: The user's request prompt

        Returns:
            Raw JSON string response from Gemini

        Raises:
            Exception: On API errors (rate limit, server errors, etc.)
        """
        # Build the combined prompt (Gemini uses a single prompt, not system/user split)
        combined_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

        # Get the JSON schema from the Pydantic model
        schema = VideoScript.model_json_schema()

        response = self.gemini_client.models.generate_content(
            model=self.gemini_model,
            contents=combined_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )

        return response.text

    @retry(
        retry=retry_if_exception_type((groq.RateLimitError, groq.BadRequestError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def _generate_with_groq(self, **kwargs) -> str:
        """
        Generate script using Groq as fallback with retry logic.

        Returns:
            Raw JSON string response from Groq
        """
        response = self.groq_client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def _log_result(self, movie_title: str, data: dict) -> Path:
        """
        Save result to a JSON file for debugging.

        Args:
            movie_title: The movie being processed
            data: The data to log

        Returns:
            Path to the log file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() else "_" for c in movie_title)[:30]
        filename = f"{timestamp}_{safe_title}_video_script.json"
        log_path = self.log_dir / filename

        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Logged video script to {log_path}")
        return log_path

    def _build_system_prompt(self) -> str:
        """Build the Storyteller system prompt with available genres and TTS customization."""
        available_genres = list(MUSIC_GENRES.keys())
        available_moods = list(SCENE_MOOD_SPEEDS.keys())
        available_voices = get_available_voices_for_groq()

        schema = VideoScript.model_json_schema()

        system_prompt = f"""You are a conversational storyteller who explains movie plots for social media - fast, engaging, with a killer hook.

Your task is to TELL THE STORY of a movie in 45-60 seconds. This is for TikTok/Reels/Shorts - you have 3 seconds to hook them or they scroll.

## SOCIAL MEDIA PACING (CRITICAL):
- **Scene 1 MUST start with a HOOK** - the most interesting, shocking, or intriguing part of the story
- Lead with conflict, death, betrayal, twist, or stakes - NOT "This is a story about..."
- Keep it FAST - every sentence should move the plot forward
- No filler, no setup that doesn't pay off, no slow burns
- Think "wait, WHAT?" energy in the first 5 seconds

## HOOK FORMULAS (Scene 1 must use one):
- Start with the twist/conflict: "So this guy finds out his wife has been dead for 3 years - but she's standing right in front of him."
- Start with stakes: "He's got 24 hours to find $2 million or his daughter dies."
- Start with action: "She wakes up covered in blood with no memory of the last 6 hours."
- Start with the weird: "This dude can see exactly how everyone around him is going to die."
- Start mid-story: "So he's standing there with a gun to his best friend's head, and we gotta rewind to see how he got here."

## ANTI-TRAILER RULES:
- NO dramatic one-liners or taglines ("Everything changed...", "Nothing would ever be the same...")
- NO hype language ("epic showdown", "ultimate battle", "thrilling conclusion")
- NO vague mystery-building ("little did he know...", "what he discovered would shock him...")
- NO trailer cadence with dramatic pauses on every sentence
- YES: Just tell me what happened, plainly but engagingly
- YES: Be specific about plot points, not vague and teasing
- YES: Sound like a person recounting events, not a movie announcer

## Your Responsibilities:

1. **Genre Classification**: Identify the PRIMARY genre of the movie. Choose the single best match from:
   {available_genres}

   Be specific! A horror movie is "horror", not "thriller". A sci-fi movie is "sci-fi", not "action".

2. **Voice Selection**: Choose the best voice for this movie's tone from:
{available_voices}

3. **Overall Mood for TTS**: Choose ONE overall_mood that defines the consistent tone for the ENTIRE video's voice narration.
   This ensures the TTS voice sounds consistent across all scenes rather than changing tone between scenes.
   Choose from: {available_moods}
   Examples:
   - Horror movies: "horror" or "suspenseful"
   - Action movies: "action" or "exciting"
   - Drama movies: "dramatic" or "sad"
   - Comedy movies: "comedic" or "happy"
   - Romance movies: "romantic" or "calm"

4. **BPM/Tempo**: Estimate an appropriate tempo (60-200 BPM) for the video pacing.

5. **Scene Creation**: Create exactly 6 scenes that cover the FULL arc of the movie:
   - **narration**: Conversational storytelling text (25-40 words).
     * **Tone**: Like you're explaining the movie to a friend. Past tense. Factual but engaging.
     * **Prohibited**: "In a world...", "Coming soon...", "Watch to find out...", rhetorical questions, dramatic taglines, hype words.
     * **Style**: Natural speech patterns. How would you actually tell someone this story out loud?

   ## CRITICAL - Narration Flow & Coherence:
   The 6 scenes must read as ONE continuous story when played back-to-back, not 6 separate paragraphs.

   **Character Name Rules**:
   - Introduce the protagonist's name ONCE in Scene 1 only.
   - After Scene 1, use PRONOUNS ("he", "she", "they") or descriptive references ("the detective", "our hero").
   - NEVER repeat the character's name in every scene. Maximum 2 name mentions across all 6 scenes.

   **Sentence Structure Variety** (MANDATORY - vary these across scenes):
   - Start with context: "So basically..." / "The thing is..."
   - Start with what happens: "He ends up..." / "She finds out that..."
   - Start with transition: "Meanwhile..." / "At the same time..."
   - Start with revelation: "Turns out..." / "Here's the twist..."
   - Start with time: "A few days later..." / "That night..."
   - Start with consequence: "That's when things go wrong..." / "The problem is..."

   **Scene Transitions**: Each scene should feel like you're continuing the same story:
   - Scene 2 should pick up where Scene 1 left off
   - Use natural connectors: "So then...", "Turns out...", "The problem was...", "That's when...", "And here's where it gets crazy..."
   - Avoid starting every scene the same way

   **Bad Example** (slow start, no hook, vague):
   - Scene 1: "So there's this cop named John Carter, and he's been working undercover for years."
   - Scene 2: "One day he gets a letter from his dead father."
   - Scene 3: "He travels to Mexico to find answers."
   - Scene 4: "He meets people along the way. Some help, some don't."

   **Good Example** (hook first, fast-paced, specific):
   - Scene 1: "John Carter just got a letter from his father - who's been dead for 10 years. It says 'I'm alive. Come find me. Tell no one.'"
   - Scene 2: "Turns out his dad faked his death because he'd been laundering money for the cartel. He's been hiding in Mexico ever since."
   - Scene 3: "John tracks him down, but the cartel finds out. They grab both of them. Now they've got 24 hours before execution."
   - Scene 4: "Here's the twist - the journalist helping John? She's cartel. She's been feeding them info the whole time."
   - **visual_queries**: Generate exactly 3 distinct Pexels search queries:
     * Option 1 (Literal/Action): Direct visual representation of the scene action.
     * Option 2 (Metaphorical/Abstract): Symbolic or mood-based visual.
     * Option 3 (Vibe/Texture/Atmospheric): Lighting, texture, or atmospheric shot.
   - **visual_style_modifiers**: Production modifiers like "4k", "cinematic lighting", "slow motion", "drone shot", "handheld".
   - **mood**: The emotional mood of this scene. Choose from: {available_moods}
     This controls TTS pacing - dramatic/sad scenes are slower, action/tense scenes are faster.
   - **tts_speed**: Speech speed multiplier (1.0-1.6). All speeds 25% faster for social media:
     * 1.0-1.15: Dramatic reveals, deaths, sad moments (slightly slower for impact)
     * 1.2-1.3: Normal narration, context, setup
     * 1.3-1.4: Most scenes - keep energy up
     * 1.4-1.5: Action sequences, chase scenes, tension peaks, exciting moments

## Phonetic Punctuation (TTS Optimization):
Use punctuation to make speech sound natural, not dramatic:
   - **Commas `,`**: Natural breath pauses, like how you'd actually speak.
   - **Periods `.`**: End thoughts cleanly. Don't run on.
   - **Ellipses `...`**: Use SPARINGLY for genuine pauses, not for fake drama. Once or twice per script max.
   - **Dashes `-`**: Good for asides or quick interjections - like this one - that feel natural.

## Narrative Arc (Social Media Structure):
Hook them in Scene 1, then tell the story fast. Every scene moves the plot forward.

- **Scene 1 (THE HOOK)**: Start with the most interesting part - conflict, stakes, twist, or action. Name the protagonist here.
  BAD: "So Marcus Chen is this FBI agent who's been undercover for five years."
  GOOD: "Marcus Chen just found out his own FBI handler sold him out to the mob. He's got 48 hours before they find him."
  mood: "tense" or "mysterious", tts_speed: 1.25-1.35

- **Scene 2 (Quick Context)**: Now fill in just enough backstory - keep it brief. Use pronouns.
  Example: "See, he'd been undercover for five years, and someone leaked his identity. The family was already hunting him."
  mood: "mysterious" or "exciting", tts_speed: 1.25-1.35

- **Scene 3 (Escalation)**: Things get worse or more complicated. Keep the momentum.
  Example: "He tries to get his informant out, but the FBI cuts him loose. They're hanging him out to dry."
  mood: varies by genre, tts_speed: 1.3-1.4

- **Scene 4 (The Turn)**: Major twist or revelation. This should hit hard.
  Example: "Then he finds out the handler didn't just leak him - the guy's been working with the mob for years. Marcus was set up from day one."
  mood: "dramatic" or "tense", tts_speed: 1.2-1.25

- **Scene 5 (Climax)**: Final confrontation. Fast and intense.
  Example: "He tracks the handler to this embassy party. Corners him in the bathroom. Gun to his head."
  mood: "action" or "tense", tts_speed: 1.4-1.5

- **Scene 6 (Resolution)**: How it ends - be specific and satisfying. Can use name again.
  Example: "Marcus lets him live but takes the evidence. Fakes his own death. Last shot - he's running a bar in Argentina, finally free."
  mood: varies, tts_speed: 1.2-1.25

6. **Visual Query Guidelines**:
   - Include photographic terms: 'blue hour', 'golden hour', 'silhouette', 'macro', 'wide angle', 'bokeh', 'aerial'
   - Be specific: "hacker typing green code dark room" not "cyberpunk"

Output MUST be valid JSON matching this schema:
{json.dumps(schema, indent=2)}

CRITICAL:
- Output ONLY valid JSON, no markdown.
- genre MUST be exactly one of: {available_genres}
- overall_mood MUST be exactly one of: {available_moods} (this is the global TTS tone for consistency)
- mood (per scene) is for pacing reference only, but overall_mood controls actual TTS voice tone
- tts_speed MUST be between 1.0 and 1.6 (faster pacing for social media)
- selected_voice_id should match one of the available voices listed above
- Summarize the ENTIRE plot including the ending. Do not use cliffhangers."""

        return system_prompt

    def generate_script(
        self,
        movie_title: str,
        plot: str,
        callback: Callable = None
    ) -> VideoScript:
        """
        Generate a complete video script using the Storyteller.

        Args:
            movie_title: The name of the movie
            plot: The Wikipedia plot text
            callback: Optional callback for progress updates

        Returns:
            VideoScript with complete production metadata (6-scene recap)
        """
        system_prompt = self._build_system_prompt()

        user_prompt = f"""Tell me this movie's story for social media - hook me in the first line, then keep it fast (60-second recap).

**Movie Title**: {movie_title}

**Plot Context**:
{plot}

**Instructions**:
- Scene 1 MUST start with a HOOK - the most interesting/shocking part. Not "This is about a guy who..."
- Tell the whole story fast - every sentence moves the plot forward.
- Be SPECIFIC about what happens. No vague teasing.
- Create 6 scenes with narration and 3 visual search options per scene.

**CRITICAL - SOCIAL MEDIA FORMAT**:
- HOOK FIRST: Start with conflict, stakes, twist, or action. Example: "This guy just found out his wife has been dead for 3 years - but she's standing right in front of him."
- Keep it FAST: No filler, no slow setup. Get to the action.
- NO trailer language: avoid "epic", "ultimate", "nothing would ever be the same"
- Mention protagonist's name in Scene 1 (during the hook), then use pronouns for Scenes 2-5.
- Be specific: "he gets shot in the leg and crawls to the car" NOT "he faced impossible odds"

Output ONLY valid JSON."""

        if callback:
            callback('log', f"Storyteller generating script for: {movie_title}")
            callback('data', "System Prompt", system_prompt)
            callback('data', "User Prompt", user_prompt)

        content = None
        provider_used = "gemini"

        # Try Gemini first (primary)
        try:
            if callback:
                callback('log', f"Attempting script generation with Gemini ({self.gemini_model})...")
            content = self._generate_with_gemini(system_prompt, user_prompt)
            logger.info(f"Script generated successfully with Gemini")
        except Exception as e:
            # Gemini failed - log warning and fall back to Groq
            logger.warning(f"[WARN] Gemini failed: {e}. Switching to Groq fallback...")
            if callback:
                callback('log', f"[WARN] Gemini failed: {e}. Switching to Groq fallback...")
            provider_used = "groq"

        # Fallback to Groq if Gemini failed
        if content is None:
            try:
                if callback:
                    callback('log', "Attempting script generation with Groq fallback...")
                content = self._generate_with_groq(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    model="llama-3.3-70b-versatile",
                    response_format={"type": "json_object"}
                )
                logger.info(f"Script generated successfully with Groq fallback")
            except Exception as e:
                raise RuntimeError(f"Both Gemini and Groq failed. Last error: {e}")

        try:
            raw_json = json.loads(content)
            result = VideoScript.model_validate(raw_json)

            # Auto-select voice and music based on genre if not properly set
            if result.selected_voice_id not in TTS_VOICES:
                result.selected_voice_id = get_voice_for_genre(result.genre)
            result.selected_music_file = get_music_for_genre(result.genre)

            # Set lang_code based on selected voice
            result.lang_code = get_lang_code_for_voice(result.selected_voice_id)

            # Log result
            self._log_result(movie_title, {
                "input": {"title": movie_title, "plot_length": len(plot)},
                "output": result.model_dump(),
                "raw_response": content,
                "provider": provider_used
            })

            if callback:
                callback('data', "Video Script Result", result.model_dump())
                callback('log', f"Script complete ({provider_used}): {len(result.scenes)} scenes, genre={result.genre}, voice={result.selected_voice_id}, lang={result.lang_code}, music={result.selected_music_file}")

            return result

        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}")
        except ValidationError as e:
            raise ValueError(f"Response doesn't match VideoScript schema: {e}")

