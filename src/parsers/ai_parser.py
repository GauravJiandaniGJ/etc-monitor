"""
AI-based ETC (Estimated Time of Completion) deadline parser using Gemini AI.

Production-grade implementation with:
- Fast async processing with proper timeout handling
- Always-on AI parsing (no skipping)
- Robust error handling and fallback
- Optimized for real-time responses
"""

import json
import re
from datetime import datetime
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import threading

from src.core.models import ParsedDeadline
from src.utils.logger import get_logger
from src.utils.timezone import now_ist

logger = get_logger("AIParser")

# Gemini availability check
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai not installed. AI parsing disabled.")


class AIParser:
    """
    Production-grade AI-based ETC parser.

    Design principles:
    - Always use AI first (no skipping)
    - Fast timeout (5 seconds max)
    - Robust error handling
    - Thread-safe execution
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.15,
        timeout_seconds: int = 5,
    ):
        """Initialize AI parser.

        Args:
            api_key: Gemini API key
            model: Gemini model name
            temperature: Model temperature (0.0-1.0)
            timeout_seconds: Maximum time to wait for AI response
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.client = None
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ai-parser")
        self._lock = threading.Lock()

        if not GEMINI_AVAILABLE:
            logger.warning("Gemini library not available")
            return

        if not api_key:
            logger.warning("Gemini API key not configured")
            return

        try:
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(
                model_name=model,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": 512,  # Reduced for faster responses
                },
            )
            logger.success(f"Gemini AI initialized: {model} (timeout: {timeout_seconds}s)")
        except Exception as e:
            logger.error("Failed to initialize Gemini", exc=e)
            self.client = None

    def is_available(self) -> bool:
        """Check if AI parser is available."""
        return self.client is not None

    def parse_deadline(
        self, text: str, reference_time: Optional[datetime] = None
    ) -> Optional[ParsedDeadline]:
        """
        Parse ETC deadline from text using AI.

        Args:
            text: Message text to parse
            reference_time: Reference time for relative dates

        Returns:
            ParsedDeadline or None if parsing fails
        """
        if not self.is_available() or not text:
            return None

        now = reference_time or now_ist()
        result = self._call_ai(text, now)

        if not result or not result.get("has_deadline"):
            return None

        confidence = float(result.get("confidence", 0.0))
        if confidence < 0.6:
            logger.debug(f"AI confidence too low: {confidence}")
            return None

        deadline_text = result.get("deadline_text", text)

        return ParsedDeadline(
            original_text=deadline_text,
            deadline_datetime=now,  # Will be resolved by datetime parser
            reminder_datetime=now,   # Will be calculated later
            confidence=confidence,
            parsed_by="ai"
        )

    def get_deadline_text(self, text: str) -> Optional[str]:
        """
        Extract deadline text from message (lightweight).

        Args:
            text: Message text

        Returns:
            Extracted deadline text or None
        """
        if not self.is_available() or not text:
            return None

        result = self._call_ai(text, now_ist())
        if result and result.get("has_deadline"):
            return result.get("deadline_text")
        return None

    def _call_ai(self, text: str, now: datetime) -> Optional[Dict]:
        """
        Call Gemini AI with timeout protection.

        Args:
            text: Message text
            now: Current time

        Returns:
            Parsed result dict or None
        """
        logger.info(f'[AI] Processing: "{text[:80]}..."')

        prompt = self._build_prompt(text, now)

        def run_ai():
            """Execute AI call in thread."""
            try:
                response = self.client.generate_content(prompt)
                return response
            except Exception as e:
                logger.error(f'[AI] Gemini API error: {e}')
                raise

        try:
            future = self._executor.submit(run_ai)
            response = future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError:
            logger.warning(f'[AI] Timeout after {self.timeout_seconds}s')
            return None
        except Exception as e:
            logger.error(f'[AI] Execution failed: {e}', exc=e)
            return None

        if not response or not response.text:
            logger.warning('[AI] Empty response from Gemini')
            return None

        result = self._parse_response(response.text)
        if result and result.get("has_deadline"):
            deadline_text = result.get("deadline_text", "")
            confidence = result.get("confidence", 0.0)
            logger.success(f'[AI] Extracted: "{deadline_text}" (confidence: {confidence:.2f})')
        else:
            logger.debug('[AI] No deadline found in response')

        return result

    def _build_prompt(self, text: str, now: datetime) -> str:
        """Build optimized prompt for Gemini."""
        return f"""You are an ETC (Estimated Time of Completion) parser. Extract deadline commitments from messages.

Current: {now.strftime('%Y-%m-%d %H:%M:%S')} IST

Message: {text}

Rules:
- Extract ONLY if user commits to a completion time
- Support: "ETC 2 mins", "etc is 2 hours", "my etc for project is 5 hours", "within 3 hours", "with in 5 hours" (typo)
- Return JSON only, no markdown

Output JSON:
{{
  "has_deadline": true/false,
  "deadline_text": "exact time phrase or null",
  "confidence": 0.0-1.0,
  "intent": "new|update|cancel|none"
}}

If unsure, has_deadline=false."""

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Parse JSON from Gemini response."""
        try:
            content = response_text.strip()

            # Remove markdown code blocks if present
            if "```" in content:
                content = re.sub(r"```(?:json)?\s*", "", content, flags=re.IGNORECASE)
                content = re.sub(r"```\s*", "", content)
                content = content.strip()

            # Extract JSON object
            match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content, re.S)
            if not match:
                logger.warning(f"[AI] No JSON found in response: {content[:200]}")
                return None

            data = json.loads(match.group(0))

            if not isinstance(data, dict):
                return None

            return data

        except json.JSONDecodeError as e:
            logger.warning(f"[AI] JSON parse error: {e}, response: {response_text[:200]}")
            return None
        except Exception as e:
            logger.error(f"[AI] Parse error: {e}", exc=e)
            return None

    def __del__(self):
        """Cleanup executor on destruction."""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)
