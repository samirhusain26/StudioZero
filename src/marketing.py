"""
Marketing utilities for generating social media captions.
"""

import logging
import groq
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.config import Config
from src.narrative import VideoScript

logger = logging.getLogger(__name__)


# Genre to hashtag mapping for consistent, relevant tags
GENRE_HASHTAGS = {
    "action": ["#action", "#actionmovie", "#explosive"],
    "comedy": ["#comedy", "#funny", "#hilarious"],
    "drama": ["#drama", "#emotional", "#mustwatch"],
    "horror": ["#horror", "#scary", "#horrormovie"],
    "romance": ["#romance", "#lovestory", "#romantic"],
    "sci-fi": ["#scifi", "#sciencefiction", "#futuristic"],
    "thriller": ["#thriller", "#suspense", "#intense"],
    "fantasy": ["#fantasy", "#epic", "#magical"],
    "animation": ["#animation", "#animated", "#cartoon"],
    "documentary": ["#documentary", "#truestory", "#reallife"],
    "mystery": ["#mystery", "#whodunit", "#suspenseful"],
    "crime": ["#crime", "#truecrime", "#criminal"],
    "adventure": ["#adventure", "#epic", "#journey"],
    "war": ["#warmovie", "#military", "#history"],
    "western": ["#western", "#cowboy", "#wildwest"],
}

# Default hashtags if genre not found
DEFAULT_HASHTAGS = ["#movie", "#film", "#mustwatch"]


class CaptionGenerator:
    """
    Generates viral social media captions using Groq LLM.
    """

    def __init__(self):
        """Initialize the Groq client."""
        self.client = groq.Groq(api_key=Config.GROQ_API_KEY)

    @retry(
        retry=retry_if_exception_type((groq.RateLimitError, groq.APIConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def _generate_with_retry(self, **kwargs) -> str:
        """Wraps the Groq API call with retry logic."""
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()

    def _get_hashtags_for_genre(self, genre: str) -> list[str]:
        """Get relevant hashtags based on movie genre."""
        genre_lower = genre.lower()
        return GENRE_HASHTAGS.get(genre_lower, DEFAULT_HASHTAGS)

    def _extract_narration_summary(self, script: VideoScript) -> str:
        """Extract a brief summary from the script's narration."""
        # Combine first two scenes for context (hook + setup)
        narrations = [scene.narration for scene in script.scenes[:2]]
        return " ".join(narrations)

    def generate_social_caption(self, script: VideoScript) -> str:
        """
        Generate a viral Instagram Reel/TikTok caption from a VideoScript.

        Args:
            script: The VideoScript object containing movie details and narration.

        Returns:
            A formatted social media caption string with hook, hashtags, and CTA.
        """
        genre_hashtags = self._get_hashtags_for_genre(script.genre)
        narration_context = self._extract_narration_summary(script)

        system_prompt = """You are a social media copywriter specializing in viral movie content for TikTok and Instagram Reels.

Your task is to write a caption that:
1. HOOKS readers in the first line (question, bold statement, or intriguing claim)
2. Creates curiosity without spoiling the video
3. Feels authentic and conversational, NOT like marketing copy
4. Is optimized for engagement (saves, shares, comments)

RULES:
- First line must be a HOOK that makes people stop scrolling
- Keep it under 150 characters before hashtags
- No emojis in the hook line
- Sound like a real person, not a brand
- End with a soft CTA that feels natural"""

        user_prompt = f"""Write a viral TikTok/Instagram Reel caption for this movie recap video.

Movie: {script.title}
Genre: {script.genre}
Mood: {script.overall_mood}

Video narration preview:
{narration_context}

FORMAT YOUR RESPONSE EXACTLY LIKE THIS (no extra text):
[Hook line - attention-grabbing first line]

[1-2 short sentences that tease the content]

Follow for more movie recaps 🎬

DO NOT include hashtags - I will add them separately.
DO NOT add any explanation or commentary - just the caption."""

        try:
            caption_body = self._generate_with_retry(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=0.8,
                max_tokens=200
            )

            # Add hashtags
            hashtags = genre_hashtags + ["#movierecap", "#films"]
            hashtag_str = " ".join(hashtags[:5])  # Limit to 5 hashtags

            # Combine caption with hashtags
            full_caption = f"{caption_body}\n\n{hashtag_str}"

            logger.info(f"Generated caption for '{script.title}' ({script.genre})")
            return full_caption

        except Exception as e:
            logger.error(f"Failed to generate caption: {e}")
            raise


def generate_social_caption(script: VideoScript) -> str:
    """
    Convenience function to generate a social media caption from a VideoScript.

    Args:
        script: The VideoScript object containing movie details.

    Returns:
        A formatted social media caption string.
    """
    generator = CaptionGenerator()
    return generator.generate_social_caption(script)
