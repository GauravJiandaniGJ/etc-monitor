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
        self.available_models = []  # Store available models for fallback
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

            # List available models to find a working one
            try:
                available_models = []
                available_models_full = []  # Store full paths too
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        # Store both full path and short name
                        full_name = m.name  # e.g., "models/gemini-1.5-flash"
                        short_name = m.name.split('/')[-1] if '/' in m.name else m.name
                        available_models.append(short_name)
                        available_models_full.append(full_name)

                if available_models:
                    logger.info(f"Found {len(available_models)} available Gemini models")
                    logger.debug(f"Available models: {', '.join(available_models[:10])}")
                    self.available_models = available_models_full  # Store full paths for fallback
                else:
                    logger.warning("No models found via list_models, trying common names...")
                    available_models = []
                    self.available_models = []

                # Try models in order of preference
                models_to_try = [
                    model,  # User's preferred model first
                ]

                # Add preferred models
                preferred = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
                models_to_try.extend(preferred)

                # Add available models that match our preferences
                for avail_model in available_models:
                    if avail_model not in models_to_try:
                        models_to_try.append(avail_model)

                # Remove duplicates while preserving order
                seen = set()
                models_to_try = [m for m in models_to_try if m not in seen and not seen.add(m)]

                working_model = None
                for model_name in models_to_try:
                    try:
                        logger.debug(f"Trying model: {model_name}")
                        self.client = genai.GenerativeModel(
                            model_name=model_name,
                            generation_config={
                                "temperature": temperature,
                                "max_output_tokens": 2048,  # Increased for comprehensive responses and accuracy
                            },
                        )
                        working_model = model_name
                        logger.success(f"Gemini AI initialized: {working_model} (timeout: {timeout_seconds}s)")
                        break
                    except Exception as test_error:
                        logger.debug(f"Model {model_name} failed: {test_error}")
                        continue

                if not working_model:
                    raise Exception("No working Gemini model found. Check your API key and model availability.")

                self.model = working_model

            except Exception as list_error:
                # If list_models fails, try common model names
                logger.warning(f"Could not list models: {list_error}. Trying common model names...")
                common_models = [
                    model,  # User's preferred
                    "gemini-1.5-flash",
                    "gemini-1.5-pro",
                    "gemini-pro"
                ]

                for model_name in common_models:
                    try:
                        self.client = genai.GenerativeModel(
                            model_name=model_name,
                            generation_config={
                                "temperature": temperature,
                                "max_output_tokens": 2048,  # Increased for comprehensive responses and accuracy
                            },
                        )
                        self.model = model_name
                        logger.success(f"Gemini AI initialized: {model_name} (timeout: {timeout_seconds}s)")
                        break
                    except Exception as e:
                        logger.debug(f"Model {model_name} failed: {e}")
                        continue
                else:
                    raise Exception(f"Failed to initialize any Gemini model. Check your API key. Last error: {list_error}")

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
        # Require high confidence for accuracy (user requirement)
        if confidence < 0.8:
            logger.warning(f"[AI] Confidence too low: {confidence} (minimum: 0.8) - REJECTING")
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
        Call Gemini AI with timeout protection and model fallback.

        Args:
            text: Message text
            now: Current time

        Returns:
            Parsed result dict or None
        """
        logger.info(f'[AI] Processing: "{text[:80]}..."')

        prompt = self._build_prompt(text, now)

        # Build list of models to try
        models_to_try = []

        # Try current model in both formats
        if self.model:
            models_to_try.append(self.model)
            if not self.model.startswith('models/'):
                models_to_try.append(f"models/{self.model}")

        # Add available models from initialization (these are full paths like "models/gemini-1.5-flash")
        if self.available_models:
            for avail_model in self.available_models:
                if avail_model not in models_to_try:
                    models_to_try.append(avail_model)
                # Also try short name format
                if avail_model.startswith('models/'):
                    short_name = avail_model.split('/')[-1]
                    if short_name not in models_to_try:
                        models_to_try.append(short_name)

        # Fallback to common names if no available models
        if not self.available_models:
            common_models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
            for cm in common_models:
                if cm not in models_to_try:
                    models_to_try.append(cm)
                if f"models/{cm}" not in models_to_try:
                    models_to_try.append(f"models/{cm}")

        # Remove duplicates while preserving order
        seen = set()
        models_to_try = [m for m in models_to_try if m not in seen and not seen.add(m)]

        for model_name in models_to_try:
            try:
                # Create a new client for this model if different from current
                if model_name != self.model:
                    logger.info(f'[AI] Trying model: {model_name}')
                    client = genai.GenerativeModel(
                        model_name=model_name,
                            generation_config={
                                "temperature": self.temperature,
                                "max_output_tokens": 2048,  # Increased for comprehensive responses and accuracy
                            },
                    )
                else:
                    client = self.client

                def run_ai():
                    """Execute AI call in thread."""
                    try:
                        response = client.generate_content(prompt)
                        return response
                    except Exception as e:
                        logger.error(f'[AI] Gemini API error with {model_name}: {e}')
                        raise

                try:
                    future = self._executor.submit(run_ai)
                    response = future.result(timeout=self.timeout_seconds)
                except FutureTimeoutError:
                    logger.warning(f'[AI] Timeout after {self.timeout_seconds}s with {model_name}')
                    continue  # Try next model
                except Exception as e:
                    logger.warning(f'[AI] Model {model_name} failed: {e}')
                    # If it's a 404 (model not found), try next model
                    if "404" in str(e) or "not found" in str(e).lower():
                        continue
                    # For other errors, log and try next model
                    continue

                # Success! Update current model if different
                if model_name != self.model:
                    logger.success(f'[AI] Switched to working model: {model_name}')
                    self.model = model_name
                    self.client = client

                if not response or not response.text:
                    logger.warning(f'[AI] Empty response from {model_name}')
                    continue  # Try next model

                # Log full response for debugging
                logger.debug(f'[AI] Full response from {model_name}: {response.text[:500]}')

                result = self._parse_response(response.text)
                if result and result.get("has_deadline"):
                    deadline_text = result.get("deadline_text", "")
                    confidence = result.get("confidence", 0.0)

                    # CRITICAL VALIDATION: Check if original text has PM/AM but extracted text doesn't (or vice versa)
                    original_upper = text.upper()
                    extracted_upper = deadline_text.upper() if deadline_text else ""
                    original_has_pm_am = 'PM' in original_upper or 'AM' in original_upper
                    extracted_has_pm_am = 'PM' in extracted_upper or 'AM' in extracted_upper

                    # If original has PM/AM but extracted doesn't, it's a critical error
                    if original_has_pm_am and not extracted_has_pm_am:
                        logger.error(f'[AI] CRITICAL ERROR: Original text "{text}" contains PM/AM but extracted "{deadline_text}" does not! Rejecting extraction.')
                        return None

                    # If extracted has PM/AM but original doesn't (and it's not a context-aware addition), log warning
                    if extracted_has_pm_am and not original_has_pm_am:
                        # This is OK for context-aware additions like "12 AM" from "today 12"
                        if '12' in original_upper and ('12 AM' in extracted_upper or '12 PM' in extracted_upper or 'MIDNIGHT' in extracted_upper or 'NOON' in extracted_upper):
                            logger.debug(f'[AI] Context-aware addition of AM/PM for "{text}" → "{deadline_text}"')
                        else:
                            logger.warning(f'[AI] Extracted "{deadline_text}" has PM/AM but original "{text}" does not')

                    logger.success(f'[AI] Extracted: "{deadline_text}" (confidence: {confidence:.2f})')
                else:
                    logger.debug('[AI] No deadline found in response')

                return result

            except Exception as e:
                logger.warning(f'[AI] Failed to use model {model_name}: {e}')
                continue  # Try next model

        # All models failed
        logger.error('[AI] All models failed - no deadline extracted')
        return None

    def _build_prompt(self, text: str, now: datetime) -> str:
        """Build expert-level prompt for Gemini - handles ALL time expressions with precision."""
        current_time = now.strftime('%Y-%m-%d %H:%M:%S %Z')
        current_date = now.strftime('%A, %B %d, %Y')
        current_hour = now.hour
        current_minute = now.minute
        day_of_week = now.strftime('%A')

        # Determine time of day context
        if current_hour < 6:
            time_period = "Night (late night/early morning)"
        elif current_hour < 12:
            time_period = "Morning"
        elif current_hour < 17:
            time_period = "Afternoon"
        elif current_hour < 21:
            time_period = "Evening"
        else:
            time_period = "Night"

        return f"""You are an EXPERT deadline extraction system for ETC (Estimated Time of Completion) tracking. Your task is to identify and extract deadline commitments from natural language with MAXIMUM PRECISION and ACCURACY.

═══════════════════════════════════════════════════════════════
CURRENT CONTEXT (CRITICAL FOR ACCURATE PARSING):
═══════════════════════════════════════════════════════════════
Current Time: {current_time}
Current Date: {current_date}
Current Day: {day_of_week}
Current Hour: {current_hour:02d}:{current_minute:02d}
Time Period: {time_period}
Timezone: Asia/Kolkata (IST)

═══════════════════════════════════════════════════════════════
MESSAGE TO ANALYZE:
═══════════════════════════════════════════════════════════════
"{text}"

═══════════════════════════════════════════════════════════════
🚨 CRITICAL DECISION TREE - READ THIS FIRST 🚨
═══════════════════════════════════════════════════════════════

STEP 1: Is it RELATIVE TIME or SPECIFIC TIME?

🚨 ABSOLUTE RULE: If text contains "AM" or "PM" (case-insensitive), it is ALWAYS SPECIFIC TIME, NEVER RELATIVE TIME! 🚨

RELATIVE TIME (duration from now):
  - Contains: "min", "mins", "minute", "minutes", "hour", "hours", "hr", "hrs", "day", "days", "week", "weeks"
  - Pattern: NUMBER + TIME_UNIT (e.g., "2 mins", "5 hours", "1 day")
  - ⚠️ CRITICAL: NO "AM" or "PM" in the text!
  - Examples: "2 mins", "2mins", "2 minutes", "5 hours", "30 mins", "1 day"
  - ⚠️ NEVER interpret "2mins" as "2:30 PM" - it's ALWAYS "2 minutes from now"
  - ⚠️ NEVER interpret "2min" as "2 PM" - it's ALWAYS "2 minutes from now"
  - Extract EXACTLY as written: "2 mins", "2mins", "2 minutes"

SPECIFIC TIME (clock time):
  - 🚨 IF TEXT CONTAINS "AM" OR "PM" (any case), IT IS ALWAYS SPECIFIC TIME! 🚨
  - Contains: "AM", "PM", "am", "pm", "Am", "Pm", "aM", "pM" (ANY CASE!)
  - Pattern: NUMBER + AM/PM (e.g., "2PM", "2 PM", "2:30 PM")
  - Examples: "2PM", "2 PM", "2:30 PM", "14:30", "9:00 AM", "9am"
  - ⚠️ "2PM" is SPECIFIC TIME (2:00 PM today/tomorrow) - has "PM"!
  - ⚠️ "2 PM" is SPECIFIC TIME (2:00 PM today/tomorrow) - has "PM"!
  - ⚠️ "2:30 PM" is SPECIFIC TIME (2:30 PM today/tomorrow) - has "PM"!
  - Extract EXACTLY as written: "2PM" → "2 PM", "2:30 PM" → "2:30 PM"

CRITICAL DISTINCTION EXAMPLES:
  ❌ WRONG: "ETC by 2mins" → "2:30 PM" (NEVER DO THIS! No PM in "2mins")
  ✅ CORRECT: "ETC by 2mins" → "2 mins" (relative time - no PM/AM)

  ❌ WRONG: "ETC by 2min" → "2 PM" (NEVER DO THIS! No PM in "2min")
  ✅ CORRECT: "ETC by 2min" → "2 min" (relative time - no PM/AM)

  ✅ CORRECT: "ETC 2PM" → "2 PM" (specific time - HAS "PM"!)
  ✅ CORRECT: "ETC by 2 PM" → "2 PM" (specific time - HAS "PM"!)
  ✅ CORRECT: "ETC by 2:30 PM" → "2:30 PM" (specific time - HAS "PM"!)

  🚨 CRITICAL: "ETC 2PM" has "PM" → Extract "2 PM" (NOT "2 mins"!)
  🚨 CRITICAL: "ETC 2PM" ≠ "ETC 2 mins" - "2PM" has PM, "2 mins" has no PM!

═══════════════════════════════════════════════════════════════
COMPREHENSIVE TIME EXPRESSION PARSING RULES:
═══════════════════════════════════════════════════════════════

1. RELATIVE TIME EXPRESSIONS (duration from NOW - CRITICAL):
   ⚠️ THESE ARE DURATIONS, NOT CLOCK TIMES ⚠️
   ✓ "2 mins", "2 minutes", "2min", "2mins", "2minute" → Extract "2 mins" (NOT "2:30 PM"!)
   ✓ "5 hours", "5 hrs", "5h" → Extract "5 hours"
   ✓ "1 day", "1d" → Extract "1 day"
   ✓ "3 weeks", "3w" → Extract "3 weeks"
   ✓ "in 30 minutes" → Extract "30 minutes"
   ✓ "within 2 hours" → Extract "2 hours"
   ✓ "after 45 mins" → Extract "45 mins"
   ✓ "ETC by 2mins" → Extract "2 mins" (NOT "2:30 PM"!)
   ✓ "ETC by 2min" → Extract "2 min" (NOT "2 PM"!)
   ✓ "ETC by 5mins" → Extract "5 mins" (NOT "5:00 PM"!)

   KEY INDICATORS FOR RELATIVE TIME:
   - Word ends with: "min", "mins", "minute", "minutes", "hour", "hours", "hr", "hrs"
   - No colon (:) between number and unit
   - No AM/PM suffix
   - Examples: "2mins", "2 mins", "5hours", "30minutes"

2. TIME OF DAY EXPRESSIONS (standardized times):
   ✓ "evening" → Extract "evening" (means 18:00 / 6:00 PM)
   ✓ "morning" → Extract "morning" (means 09:00 / 9:00 AM)
   ✓ "afternoon" → Extract "afternoon" (means 14:00 / 2:00 PM)
   ✓ "night" → Extract "night" (means 21:00 / 9:00 PM)
   ✓ "noon" → Extract "noon" (means 12:00 / 12:00 PM)
   ✓ "midnight" → Extract "midnight" (means 00:00 / 12:00 AM)

3. SPECIFIC TIME EXPRESSIONS (clock time - CRITICAL):
   🚨 ABSOLUTE RULE: If text contains "AM" or "PM" (any case), it is ALWAYS SPECIFIC TIME! 🚨
   ⚠️ THESE ARE CLOCK TIMES, NOT DURATIONS ⚠️
   ✓ "2PM" → Extract "2 PM" (2:00 PM on clock - HAS "PM"!)
   ✓ "2 PM" → Extract "2 PM" (2:00 PM on clock - HAS "PM"!)
   ✓ "ETC 2PM" → Extract "2 PM" (HAS "PM" - NOT "2 mins"!)
   ✓ "ETC by 2PM" → Extract "2 PM" (HAS "PM" - NOT "2 mins"!)
   ✓ "2:30 PM", "2:30PM" → Extract "2:30 PM" (2:30 PM on clock - HAS "PM"!)
   ✓ "14:00", "14:00:00" → Extract "14:00" (24-hour format)
   ✓ "5:30 PM", "17:30" → Extract "5:30 PM" or "17:30"
   ✓ "9am", "9AM", "09:00", "9:00 AM" → Extract "9:00 AM" (HAS "AM"!)
   ✓ "half past 3" → Extract "3:30 PM"
   ✓ "quarter to 5" → Extract "4:45 PM"
   ✓ "quarter past 2" → Extract "2:15 PM"

   🚨 CRITICAL EXAMPLES TO REMEMBER:
   - "ETC 2PM" → "2 PM" (HAS "PM" = specific time, NOT "2 mins")
   - "ETC 2 mins" → "2 mins" (NO "PM" = relative time, NOT "2 PM")
   - "ETC 2PM" ≠ "ETC 2 mins" - They are DIFFERENT!

   CONTEXT-AWARE STANDALONE NUMBERS (CRITICAL):
   ⚠️ When user says just a number like "12" or "3", use CURRENT TIME to decide AM/PM ⚠️
   - Current time is {current_hour:02d}:{current_minute:02d} ({time_period})
   - If current time is PAST 12 PM (13:00 or later):
     * "12" → Extract "12 AM" or "midnight" (NOT "12 PM" - that already passed!)
     * "1", "2", "3", etc. → Extract as PM (e.g., "1 PM", "2 PM", "3 PM")
   - If current time is BEFORE 12 PM (before 13:00):
     * "12" → Extract "12 PM" or "noon" (12:00 PM today)
     * "1", "2", "3", etc. → Extract as PM (e.g., "1 PM", "2 PM", "3 PM")
   - Examples:
     * Current time: 1:07 PM → "today 12" → Extract "12 AM" or "midnight" (12 has passed today)
     * Current time: 10:00 AM → "today 12" → Extract "12 PM" or "noon" (12 PM is upcoming)
     * Current time: 1:07 PM → "today 3" → Extract "3 PM" (3 PM is upcoming today)

   KEY INDICATORS FOR SPECIFIC TIME:
   - Contains colon (:) followed by numbers (e.g., "2:30 PM")
   - Contains AM/PM suffix (e.g., "2 PM", "2:30 PM")
   - 24-hour format with colon (e.g., "14:30")
   - Standalone number (1-12) with day context (e.g., "today 12", "tomorrow 3")
   - Examples: "2:30 PM", "2 PM", "14:30", "9:00 AM", "today 12", "tomorrow 3"

   🚨 CRITICAL RULES:
   - If text contains "PM" or "AM" (any case) → ALWAYS extract as specific time
   - "2PM" has "PM" → Extract "2 PM" (NOT "2 mins"!)
   - "2 mins" has NO "PM" → Extract "2 mins" (NOT "2 PM"!)
   - "2mins" is NOT "2:30 PM" - it's "2 minutes from now" (no PM/AM)
   - "2min" is NOT "2 PM" - it's "2 minutes from now" (no PM/AM)
   - Only extract as specific time if it has AM/PM, colon (:), OR is standalone number with day context

4. DAY-BASED EXPRESSIONS:
   ✓ "today" → Extract "today"
   ✓ "tomorrow" → Extract "tomorrow"
   ✓ "Monday", "Tuesday", etc. → Extract the day name
   ✓ "next Monday" → Extract "next Monday"
   ✓ "this Friday" → Extract "this Friday"
   ✓ "Friday" → Extract "Friday"

5. COMBINED EXPRESSIONS (DAY + TIME - EXTRACT BOTH):
   ✓ "tomorrow evening" → Extract "tomorrow evening"
   ✓ "Friday 5PM" → Extract "Friday 5PM"
   ✓ "next week Monday morning" → Extract "next Monday morning"
   ✓ "tomorrow at 2PM" → Extract "tomorrow 2PM" (remove "at")
   ✓ "Monday afternoon" → Extract "Monday afternoon"
   ✓ "tomorrow 1PM" → Extract "tomorrow 1PM"
   ✓ "Friday 3:30 PM" → Extract "Friday 3:30 PM"

6. "BY" / "AT" / "BEFORE" EXPRESSIONS (CRITICAL PATTERN):
   ⚠️ FIRST CHECK: Is it RELATIVE TIME or SPECIFIC TIME? ⚠️

   RELATIVE TIME EXAMPLES:
   ✓ "ETC by 2mins" → Extract "2 mins" (NOT "2:30 PM"!)
   ✓ "ETC by 2min" → Extract "2 min" (NOT "2 PM"!)
   ✓ "ETC by 5mins" → Extract "5 mins" (NOT "5:00 PM"!)
   ✓ "ETC by 30mins" → Extract "30 mins" (NOT "30:00"!)
   ✓ "ETC by 2 hours" → Extract "2 hours"
   ✓ "ETC by 1 day" → Extract "1 day"

   SPECIFIC TIME EXAMPLES:
   ✓ "ETC by 2:30 PM" → Extract "2:30 PM" (remove "by", keep time)
   ✓ "ETC by 2PM" → Extract "2 PM"
   ✓ "ETC by tomorrow 1PM" → Extract "tomorrow 1PM"
   ✓ "ETC by Friday 5PM" → Extract "Friday 5PM"
   ✓ "complete by 3PM" → Extract "3 PM"
   ✓ "finish by 2:30 PM" → Extract "2:30 PM"

   CONTEXT-AWARE STANDALONE NUMBERS WITH DAY:
   ⚠️ Current time: {current_hour:02d}:{current_minute:02d} ({time_period}) ⚠️
   ✓ "ETC by today 12" (if current time is PAST 12 PM) → Extract "12 AM" or "midnight"
   ✓ "ETC by today 12" (if current time is BEFORE 12 PM) → Extract "12 PM" or "noon"
   ✓ "ETC by today 3" (if current time is PAST 12 PM) → Extract "3 PM"
   ✓ "ETC by today 3" (if current time is BEFORE 12 PM) → Extract "3 PM"
   ✓ "ETC by tomorrow 12" → Extract "tomorrow 12 PM" (default to PM for future days)

   OTHER EXAMPLES:
   ✓ "ETC by evening" → Extract "evening"
   ✓ "ETC by tomorrow" → Extract "tomorrow"
   ✓ "done by Friday" → Extract "Friday"
   ✓ "by close of business" → Extract "close of business" or "5 PM"
   ✓ "by EOD" → Extract "EOD"

7. COMPLEX EXPRESSIONS:
   ✓ "end of day" → Extract "end of day"
   ✓ "end of week" → Extract "end of week"
   ✓ "by close of business" → Extract "close of business" or "5 PM"
   ✓ "EOD" → Extract "EOD"
   ✓ "COB" → Extract "COB" or "5 PM"

8. NATURAL LANGUAGE VARIATIONS (REAL-WORLD CORPORATE SCENARIOS):

   STANDARD CORPORATE ETC PATTERNS:
   ✓ "My task will complete by tomorrow 1PM" → Extract "tomorrow 1PM"
   ✓ "ETC: evening" → Extract "evening"
   ✓ "I'll finish this in 2 hours" → Extract "2 hours"
   ✓ "Done by Friday" → Extract "Friday"
   ✓ "Currently facing issues but task will be finished by 2:30 PM" → Extract "2:30 PM"
   ✓ "ETC by 2:30 PM" → Extract "2:30 PM"
   ✓ "Will complete this by tomorrow morning" → Extract "tomorrow morning"
   ✓ "Task ETC: Friday afternoon" → Extract "Friday afternoon"
   ✓ "I'll be done by 5PM today" → Extract "5 PM" (today implied)
   ✓ "This should be ready by 3:45 PM" → Extract "3:45 PM"

   CORPORATE STATUS UPDATES WITH ETC:
   ✓ "Working on it, ETC: 2 hours" → Extract "2 hours"
   ✓ "Facing some blockers, but ETC by tomorrow 3PM" → Extract "tomorrow 3PM"
   ✓ "Almost done, ETC: 30 mins" → Extract "30 mins"
   ✓ "Review in progress, ETC: Friday EOD" → Extract "Friday EOD" or "Friday 5 PM"
   ✓ "Code review pending, ETC by Monday morning" → Extract "Monday morning"
   ✓ "Testing phase, ETC: tomorrow evening" → Extract "tomorrow evening"
   ✓ "Deployment scheduled, ETC by 6PM today" → Extract "6 PM"
   ✓ "Waiting for approval, ETC: next week Tuesday" → Extract "next Tuesday"

   URGENT/QUICK TURNAROUND SCENARIOS:
   ✓ "ETC: 5 mins" → Extract "5 mins" (NOT "5:00 PM"!)
   ✓ "ETC: 10mins" → Extract "10 mins" (NOT "10:00 AM"!)
   ✓ "Quick fix, ETC: 15 minutes" → Extract "15 minutes"
   ✓ "Hotfix ready, ETC by 2mins" → Extract "2 mins"
   ✓ "Urgent: ETC 30mins" → Extract "30 mins"

   BUSINESS HOURS & DEADLINES:
   ✓ "ETC: COB" → Extract "COB" or "5 PM"
   ✓ "ETC by EOD" → Extract "EOD" or "end of day"
   ✓ "ETC: close of business" → Extract "close of business" or "5 PM"
   ✓ "ETC by end of day" → Extract "end of day"
   ✓ "ETC: EOW" → Extract "end of week"
   ✓ "ETC by Friday COB" → Extract "Friday 5 PM"

   MULTI-PART & COMPLEX SCENARIOS:
   ✓ "Phase 1 ETC: today 3PM, Phase 2 ETC: tomorrow" → Extract "today 3PM" (first deadline)
   ✓ "First draft ETC: 2 hours, final ETC: Friday" → Extract "2 hours" (first deadline)
   ✓ "ETC for initial version: tomorrow, ETC for final: next week" → Extract "tomorrow" (first deadline)

   AMBIGUOUS BUT COMMON CORPORATE PHRASES:
   ✓ "ETC: later today" → Extract "today" (end of day implied)
   ✓ "ETC: soon" → Extract "soon" (but confidence < 0.8, may reject)
   ✓ "ETC: ASAP" → Extract "ASAP" (but confidence < 0.8, may reject)
   ✓ "ETC: next week" → Extract "next week" (Monday implied)
   ✓ "ETC: this week" → Extract "this week" (Friday EOD implied)

   TIMEZONE & GLOBAL TEAM SCENARIOS:
   ✓ "ETC: 9AM IST" → Extract "9 AM"
   ✓ "ETC by 5PM EST" → Extract "5 PM" (timezone noted but extract time)
   ✓ "ETC: tomorrow 10AM" → Extract "tomorrow 10 AM"

   NEGATIVE/EXCLUSION SCENARIOS (NO DEADLINE):
   ✗ "No ETC yet" → has_deadline: false
   ✗ "ETC TBD" → has_deadline: false
   ✗ "ETC: unknown" → has_deadline: false
   ✗ "What's the ETC?" → has_deadline: false (question, not commitment)
   ✗ "Status update: still working" → has_deadline: false (no deadline)

═══════════════════════════════════════════════════════════════
CORPORATE COMMUNICATION PATTERNS (REAL-WORLD SCENARIOS):
═══════════════════════════════════════════════════════════════

STANDARD ETC FORMATS:
   ✓ "ETC: [time]" → Extract time (e.g., "ETC: 2 hours" → "2 hours")
   ✓ "ETC by [time]" → Extract time (e.g., "ETC by 3PM" → "3 PM")
   ✓ "ETC [time]" → Extract time (e.g., "ETC tomorrow" → "tomorrow")
   ✓ "[action] by [time]" → Extract time (e.g., "complete by Friday" → "Friday")
   ✓ "[status], ETC: [time]" → Extract time (e.g., "Working on it, ETC: 2 hours" → "2 hours")

STATUS UPDATE PATTERNS:
   ✓ "Facing [issue], but ETC by [time]" → Extract time
   ✓ "[Phase] in progress, ETC: [time]" → Extract time
   ✓ "[Task] scheduled, ETC by [time]" → Extract time
   ✓ "Waiting for [approval], ETC: [time]" → Extract time
   ✓ "[Status]: ETC [time]" → Extract time

URGENT/QUICK TURNAROUND PATTERNS:
   ✓ "ETC: [X] mins" → Extract "[X] mins" (relative time)
   ✓ "ETC: [X]mins" → Extract "[X] mins" (relative time)
   ✓ "Quick fix, ETC: [time]" → Extract time
   ✓ "Hotfix ready, ETC by [time]" → Extract time
   ✓ "Urgent: ETC [time]" → Extract time

BUSINESS TERMINOLOGY:
   ✓ "ETC: COB" → Extract "COB" or "5 PM"
   ✓ "ETC: EOD" → Extract "EOD" or "end of day"
   ✓ "ETC: EOW" → Extract "end of week"
   ✓ "ETC: close of business" → Extract "close of business" or "5 PM"
   ✓ "[Day] COB" → Extract "[Day] 5 PM"
   ✓ "[Day] EOD" → Extract "[Day] end of day"

MULTI-PART PROJECTS:
   ✓ "Phase 1 ETC: [time], Phase 2 ETC: [time]" → Extract FIRST deadline
   ✓ "[Part] ETC: [time], [Part] ETC: [time]" → Extract FIRST deadline
   ✓ "Initial ETC: [time], final ETC: [time]" → Extract FIRST deadline

NEGATIVE/NO DEADLINE PATTERNS:
   ✗ "No ETC yet" → has_deadline: false
   ✗ "ETC TBD" → has_deadline: false
   ✗ "ETC: unknown" → has_deadline: false
   ✗ "ETC: ASAP" → has_deadline: false (too vague)
   ✗ "ETC: soon" → has_deadline: false (too vague)
   ✗ "What's the ETC?" → has_deadline: false (question)
   ✗ "Status: still working" → has_deadline: false (no deadline)

═══════════════════════════════════════════════════════════════
CRITICAL EXTRACTION RULES (MUST FOLLOW):
═══════════════════════════════════════════════════════════════

1. DEADLINE DETECTION:
   - Extract ONLY if user explicitly commits to a completion time
   - Look for keywords: "ETC", "by", "at", "in", "within", "complete by", "finish by", "done by", "will be ready by"
   - Ignore: questions, status updates without deadlines, vague statements, "TBD", "unknown", "ASAP", "soon"
   - Corporate context: "Working on it" alone = no deadline, but "Working on it, ETC: 2 hours" = has deadline

2. EXTRACTION PRECISION (CRITICAL - READ CAREFULLY):
   ⚠️ FIRST: Determine if it's RELATIVE TIME or SPECIFIC TIME ⚠️

   RELATIVE TIME RULES:
   - If text contains "min", "mins", "minute", "minutes", "hour", "hours", "hr", "hrs", "day", "days", "week", "weeks"
   - AND no colon (:) between number and unit
   - AND no AM/PM suffix
   - THEN extract EXACTLY as written: "2 mins", "2mins", "5 hours", "30mins"
   - ⚠️ NEVER convert "2mins" to "2:30 PM" - it's ALWAYS "2 mins" (relative time)
   - ⚠️ NEVER convert "2min" to "2 PM" - it's ALWAYS "2 min" (relative time)

   SPECIFIC TIME RULES:
   - If text contains colon (:) followed by numbers (e.g., "2:30 PM")
   - OR contains AM/PM suffix (e.g., "2 PM", "2:30 PM")
   - OR is 24-hour format with colon (e.g., "14:30")
   - OR is standalone number (1-12) with day context (e.g., "today 12", "tomorrow 3")
   - THEN extract with CONTEXT-AWARE interpretation:
     * For standalone numbers with day context, check current time:
       - If current time is PAST 12 PM and number is "12" → Extract "12 AM" or "midnight"
       - If current time is BEFORE 12 PM and number is "12" → Extract "12 PM" or "noon"
       - For other numbers (1-11), extract as PM (e.g., "3 PM", "5 PM")
     * For explicit times → Extract EXACTLY as written: "2:30 PM", "2 PM", "14:30"

   GENERAL RULES:
   - Extract the EXACT time phrase from the message
   - For "by X" expressions: Extract "X" (remove "by" but keep the time/day)
   - For "at X" expressions: Extract "X" (remove "at" but keep the time/day)
   - Preserve time format: "2:30 PM" stays as "2:30 PM", not "2PM" or "14:30"
   - Preserve day+time combinations: "tomorrow 1PM" stays together
   - For ambiguous standalone numbers: Use current time context to determine AM/PM
   - DO NOT modify or simplify the extracted text unnecessarily
   - DO NOT convert relative time to specific time (e.g., "2mins" → "2:30 PM" is WRONG)

3. TIME CALCULATION PRECISION:
   - For relative times: Calculate EXACTLY from current time
   - For time-of-day: Use standardized times (evening=18:00, morning=09:00, etc.)
   - For past times: Automatically move to next occurrence
   - For ambiguous days: Use next occurrence if today's time has passed
   - For standalone times (e.g., "2:30 PM"): Assume today if not past, else tomorrow

4. EXTRACTION PRIORITY:
   - If multiple deadlines exist, extract the FIRST/PRIMARY one
   - Prefer specific times over vague ones
   - Prefer earlier deadlines if ambiguous
   - For "by X" patterns, extract X (the actual deadline, not the preposition)

5. CONFIDENCE SCORING:
   - 0.95-1.0: Clear, specific deadline (e.g., "2:30 PM", "Friday 5PM", "tomorrow 1PM")
   - 0.90-0.94: Clear but slightly ambiguous (e.g., "evening", "tomorrow", "2 PM")
   - 0.85-0.89: Somewhat ambiguous but extractable (e.g., "soon", "later today")
   - 0.80-0.84: Ambiguous but has deadline intent
   - < 0.80: Too ambiguous, set has_deadline=false

6. INTENT CLASSIFICATION:
   - "new": First time setting a deadline
   - "update": Updating an existing deadline
   - "cancel": Canceling a deadline
   - "none": No deadline in message

═══════════════════════════════════════════════════════════════
OUTPUT FORMAT (STRICT JSON ONLY):
═══════════════════════════════════════════════════════════════

You MUST respond with ONLY a complete, valid JSON object. No markdown, no explanations, no extra text.

REQUIRED JSON STRUCTURE:
{{
  "has_deadline": boolean,
  "deadline_text": string or null,
  "confidence": float (0.0-1.0),
  "intent": "new" | "update" | "cancel" | "none"
}}

FIELD REQUIREMENTS:
- has_deadline: true only if a clear deadline commitment exists
- deadline_text: Exact phrase from message (e.g., "2:30 PM", "evening", "tomorrow 1PM", "Friday 5PM")
- confidence: Must be >= 0.8 if has_deadline=true, else 0.0
- intent: Classification of the message intent

═══════════════════════════════════════════════════════════════
REAL-WORLD EXAMPLES (LEARN FROM THESE):
═══════════════════════════════════════════════════════════════

Input: "ETC: 2 mins"
Output: {{"has_deadline": true, "deadline_text": "2 mins", "confidence": 0.95, "intent": "new"}}

Input: "ETC by 2mins"
Output: {{"has_deadline": true, "deadline_text": "2 mins", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: "2mins" is RELATIVE TIME (2 minutes from now), NOT "2:30 PM"!

Input: "ETC by 2min"
Output: {{"has_deadline": true, "deadline_text": "2 min", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: "2min" is RELATIVE TIME (2 minutes from now), NOT "2 PM"!

Input: "ETC: evening"
Output: {{"has_deadline": true, "deadline_text": "evening", "confidence": 0.9, "intent": "new"}}

Input: "ETC by 2:30 PM"
Output: {{"has_deadline": true, "deadline_text": "2:30 PM", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: "2:30 PM" is SPECIFIC TIME (has colon and PM), NOT relative time!

Input: "ETC by 2PM"
Output: {{"has_deadline": true, "deadline_text": "2 PM", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: "2PM" is SPECIFIC TIME (has PM), NOT relative time!

Input: "My task of this ETC will complete by tomorrow 1PM"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 1PM", "confidence": 0.95, "intent": "new"}}

Input: "Currently facing issues but task will be finished by 2:30 PM"
Output: {{"has_deadline": true, "deadline_text": "2:30 PM", "confidence": 0.95, "intent": "new"}}

Input: "ETC: Friday 5PM"
Output: {{"has_deadline": true, "deadline_text": "Friday 5PM", "confidence": 0.95, "intent": "new"}}

Input: "ETC by tomorrow"
Output: {{"has_deadline": true, "deadline_text": "tomorrow", "confidence": 0.9, "intent": "new"}}

Input: "ETC by tomorrow evening"
Output: {{"has_deadline": true, "deadline_text": "tomorrow evening", "confidence": 0.95, "intent": "new"}}

Input: "I'll finish this in 2 hours"
Output: {{"has_deadline": true, "deadline_text": "2 hours", "confidence": 0.9, "intent": "new"}}

Input: "Done by Friday"
Output: {{"has_deadline": true, "deadline_text": "Friday", "confidence": 0.9, "intent": "new"}}

Input: "How's it going?"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

Input: "Status update: working on it"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

Input: "ETC by 3:45 PM"
Output: {{"has_deadline": true, "deadline_text": "3:45 PM", "confidence": 0.95, "intent": "new"}}

Input: "Will complete by tomorrow 2PM"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 2PM", "confidence": 0.95, "intent": "new"}}

Input: "ETC by today 12" (Current time: 1:07 PM / 13:07)
Output: {{"has_deadline": true, "deadline_text": "12 AM" or "midnight", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: Current time is 1:07 PM (13:07, past 12 PM), so "12" means 12 AM (midnight), NOT 12 PM! Extract "12 AM" or "midnight".

Input: "ETC by today 12" (Current time: 10:00 AM / 10:00)
Output: {{"has_deadline": true, "deadline_text": "12 PM" or "noon", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: Current time is 10:00 AM (before 12 PM), so "12" means 12 PM (noon)! Extract "12 PM" or "noon".

Input: "ETC by today 3" (Current time: 1:07 PM / 13:07)
Output: {{"has_deadline": true, "deadline_text": "3 PM", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: Current time is 1:07 PM (13:07), so "3" means 3 PM (upcoming today)! Extract "3 PM".

Input: "ETC 2PM"
Output: {{"has_deadline": true, "deadline_text": "2 PM", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: "2PM" contains "PM" → Extract "2 PM" (SPECIFIC TIME), NOT "2 mins"!

Input: "ETC by 2PM"
Output: {{"has_deadline": true, "deadline_text": "2 PM", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: "2PM" contains "PM" → Extract "2 PM" (SPECIFIC TIME), NOT "2 mins"!

═══════════════════════════════════════════════════════════════
COMPREHENSIVE CORPORATE ETC SCENARIOS (100% COVERAGE):
═══════════════════════════════════════════════════════════════

STANDARD CORPORATE PATTERNS:
Input: "ETC: 2 hours"
Output: {{"has_deadline": true, "deadline_text": "2 hours", "confidence": 0.95, "intent": "new"}}

Input: "ETC by tomorrow 3PM"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 3PM", "confidence": 0.95, "intent": "new"}}

Input: "Working on it, ETC: 30 mins"
Output: {{"has_deadline": true, "deadline_text": "30 mins", "confidence": 0.95, "intent": "new"}}

Input: "Facing blockers, but ETC by Friday EOD"
Output: {{"has_deadline": true, "deadline_text": "Friday EOD" or "Friday 5 PM", "confidence": 0.95, "intent": "new"}}

Input: "Code review pending, ETC by Monday morning"
Output: {{"has_deadline": true, "deadline_text": "Monday morning", "confidence": 0.95, "intent": "new"}}

Input: "Deployment scheduled, ETC by 6PM today"
Output: {{"has_deadline": true, "deadline_text": "6 PM", "confidence": 0.95, "intent": "new"}}

URGENT/QUICK TURNAROUND:
Input: "ETC: 5 mins"
Output: {{"has_deadline": true, "deadline_text": "5 mins", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: "5 mins" is RELATIVE TIME, NOT "5:00 PM"!

Input: "Hotfix ready, ETC by 2mins"
Output: {{"has_deadline": true, "deadline_text": "2 mins", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: "2mins" is RELATIVE TIME, NOT "2:30 PM"!

Input: "Urgent: ETC 30mins"
Output: {{"has_deadline": true, "deadline_text": "30 mins", "confidence": 0.95, "intent": "new"}}

BUSINESS HOURS:
Input: "ETC: COB"
Output: {{"has_deadline": true, "deadline_text": "COB" or "5 PM", "confidence": 0.95, "intent": "new"}}

Input: "ETC by EOD"
Output: {{"has_deadline": true, "deadline_text": "EOD" or "end of day", "confidence": 0.95, "intent": "new"}}

Input: "ETC by Friday COB"
Output: {{"has_deadline": true, "deadline_text": "Friday 5 PM", "confidence": 0.95, "intent": "new"}}

MULTI-PART SCENARIOS (EXTRACT FIRST):
Input: "Phase 1 ETC: today 3PM, Phase 2 ETC: tomorrow"
Output: {{"has_deadline": true, "deadline_text": "today 3PM", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: Extract FIRST deadline when multiple exist!

Input: "First draft ETC: 2 hours, final ETC: Friday"
Output: {{"has_deadline": true, "deadline_text": "2 hours", "confidence": 0.95, "intent": "new"}}

CONTEXT-AWARE STANDALONE NUMBERS:
Input: "will complete by today etc evening"
Output: {{"has_deadline": true, "deadline_text": "evening", "confidence": 0.9, "intent": "new"}}

Input: "etc tomorrow by 2pm"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 2PM", "confidence": 0.95, "intent": "new"}}

NEGATIVE CASES (NO DEADLINE):
Input: "No ETC yet"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

Input: "ETC TBD"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

Input: "What's the ETC?"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

Input: "Status update: still working"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

EDGE CASES & VARIATIONS:
Input: "ETC: later today"
Output: {{"has_deadline": true, "deadline_text": "today", "confidence": 0.85, "intent": "new"}}

Input: "ETC: next week"
Output: {{"has_deadline": true, "deadline_text": "next week", "confidence": 0.85, "intent": "new"}}

Input: "ETC: this week"
Output: {{"has_deadline": true, "deadline_text": "this week", "confidence": 0.85, "intent": "new"}}

Input: "ETC: ASAP"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}
⚠️ NOTE: "ASAP" is too vague, set has_deadline=false!

Input: "ETC: soon"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}
⚠️ NOTE: "soon" is too vague, set has_deadline=false!

COMPLEX NATURAL LANGUAGE:
Input: "Currently I am facing Some Issues but the task will be finished by 2"
Output: {{"has_deadline": true, "deadline_text": "2 PM", "confidence": 0.9, "intent": "new"}}
⚠️ NOTE: Extract "2 PM" from "by 2" - context suggests PM for business hours!

Input: "Currently I am facing Some Issues but the task will be finished ETC 2"
Output: {{"has_deadline": true, "deadline_text": "2 PM", "confidence": 0.9, "intent": "new"}}
⚠️ NOTE: "ETC 2" in business context means "2 PM", not "2 minutes"!

Input: "My task of this ETC will complete by tomorrow 1PM"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 1PM", "confidence": 0.95, "intent": "new"}}

Input: "Review in progress, ETC: Friday EOD"
Output: {{"has_deadline": true, "deadline_text": "Friday EOD" or "Friday 5 PM", "confidence": 0.95, "intent": "new"}}

Input: "Testing phase, ETC: tomorrow evening"
Output: {{"has_deadline": true, "deadline_text": "tomorrow evening", "confidence": 0.95, "intent": "new"}}

Input: "Waiting for approval, ETC: next week Tuesday"
Output: {{"has_deadline": true, "deadline_text": "next Tuesday", "confidence": 0.9, "intent": "new"}}

Input: "will complete by today etc evening"
Output: {{"has_deadline": true, "deadline_text": "evening", "confidence": 0.9, "intent": "new"}}
⚠️ NOTE: Extract "evening" from "etc evening" - remove "etc" but keep time!

Input: "etc tomorrow by 2pm"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 2PM", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: Extract "tomorrow 2PM" - combine day and time!

Input: "etc by today 12" (Current time: 1:07 PM)
Output: {{"has_deadline": true, "deadline_text": "12 AM" or "midnight", "confidence": 0.95, "intent": "new"}}
⚠️ NOTE: Current time is 1:07 PM (past 12 PM), so "12" means 12 AM (midnight)!

CORPORATE STATUS UPDATES WITH MIXED FORMATS:
Input: "Working on bug fix, ETC: 1 hour"
Output: {{"has_deadline": true, "deadline_text": "1 hour", "confidence": 0.95, "intent": "new"}}

Input: "Deployment in progress, ETC by 5PM"
Output: {{"has_deadline": true, "deadline_text": "5 PM", "confidence": 0.95, "intent": "new"}}

Input: "Code review done, ETC: tomorrow 10AM"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 10 AM", "confidence": 0.95, "intent": "new"}}

Input: "Testing completed, ETC: Friday afternoon"
Output: {{"has_deadline": true, "deadline_text": "Friday afternoon", "confidence": 0.95, "intent": "new"}}

Input: "Approval received, ETC by Monday morning"
Output: {{"has_deadline": true, "deadline_text": "Monday morning", "confidence": 0.95, "intent": "new"}}

TIMEZONE AWARENESS:
Input: "ETC: 9AM IST"
Output: {{"has_deadline": true, "deadline_text": "9 AM", "confidence": 0.95, "intent": "new"}}

Input: "ETC by 5PM EST"
Output: {{"has_deadline": true, "deadline_text": "5 PM", "confidence": 0.95, "intent": "new"}}

═══════════════════════════════════════════════════════════════
STEP-BY-STEP EXTRACTION PROCESS (FOLLOW EXACTLY):
═══════════════════════════════════════════════════════════════

STEP 1: MESSAGE ANALYSIS
   - Read the entire message carefully
   - Identify if it contains an ETC indicator: "ETC", "by", "at", "complete by", "finish by", "done by"
   - If NO ETC indicator found → has_deadline: false, intent: "none"
   - If ETC indicator found → Proceed to STEP 2

STEP 2: RELATIVE vs SPECIFIC TIME DECISION
   - Check if message contains time units: "min", "mins", "minute", "minutes", "hour", "hours", "hr", "hrs"
   - If YES and NO colon (:) and NO AM/PM → RELATIVE TIME
   - If contains colon (:) OR AM/PM OR standalone number with day → SPECIFIC TIME
   - If ambiguous → Use context clues (current time, day mentions)

STEP 3: EXTRACTION
   - For RELATIVE TIME: Extract exactly as written (e.g., "2 mins", "5 hours")
   - For SPECIFIC TIME:
     * If has AM/PM or colon → Extract exactly (e.g., "2:30 PM", "2 PM")
     * If standalone number with day → Use current time context:
       - "today 12" + current time past 12 PM → "12 AM" or "midnight"
       - "today 12" + current time before 12 PM → "12 PM" or "noon"
       - "today 3" → "3 PM" (default to PM for business hours)
   - Remove prepositions ("by", "at") but keep time/day intact

STEP 4: VALIDATION
   - Verify extracted text makes sense
   - Check confidence score (0.95 for clear, 0.9 for slightly ambiguous, <0.8 reject)
   - Ensure deadline is in the future (relative times always are, specific times may need adjustment)

STEP 5: OUTPUT
   - Build JSON with all required fields
   - Ensure JSON is complete and valid
   - No markdown, no explanations, ONLY JSON

═══════════════════════════════════════════════════════════════
FINAL INSTRUCTIONS:
═══════════════════════════════════════════════════════════════

1. Read the message carefully and identify if there's a deadline commitment
2. Extract the EXACT time phrase (remove prepositions like "by", "at" but keep the time/day)
3. For "ETC by 2:30 PM" → Extract "2:30 PM" (not "by 2:30 PM")
4. For "tomorrow 1PM" → Extract "tomorrow 1PM" (keep together)
5. Preserve time format exactly as written (e.g., "2:30 PM" not "2PM" or "14:30")
6. For standalone numbers with day context, use current time to determine AM/PM
7. Calculate confidence based on clarity (specific times = higher confidence)
8. Determine intent (usually "new" for first-time deadlines)
9. Output ONLY complete, valid JSON with all required fields
10. Ensure JSON is properly closed with all braces

CRITICAL: Extract the ACTUAL deadline time/day, not the preposition. For "by 2:30 PM", extract "2:30 PM".

🚨 FINAL VALIDATION CHECKLIST 🚨
Before responding, verify:
1. ✅ Did I check if it's RELATIVE TIME (e.g., "2mins") or SPECIFIC TIME (e.g., "2:30 PM")?
2. ✅ If it's "2mins" or "2min", did I extract "2 mins" or "2 min" (NOT "2:30 PM" or "2 PM")?
3. ✅ If it's "2:30 PM" or "2 PM", did I extract it exactly as written?
4. ✅ For "today 12", did I check current time to determine if it's 12 AM or 12 PM?
5. ✅ Did I preserve the exact format from the message?
6. ✅ Is my confidence score appropriate (0.95 for clear deadlines, <0.8 for vague)?
7. ✅ Did I remove prepositions ("by", "at") but keep the actual deadline?
8. ✅ Is the JSON complete with all required fields?
9. ✅ Is the JSON properly formatted and valid?

CORPORATE ETC BEST PRACTICES:
- Always prioritize clarity and accuracy
- When in doubt, extract the most specific time mentioned
- For ambiguous cases, use current time context
- Reject vague commitments (ASAP, soon) with has_deadline: false
- Extract first deadline when multiple are mentioned

RESPOND NOW WITH COMPLETE JSON ONLY:"""

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Parse JSON from Gemini response."""
        try:
            content = response_text.strip()
            logger.debug(f"[AI] Raw response: {content[:300]}")

            # Remove markdown code blocks if present
            if "```" in content:
                content = re.sub(r"```(?:json)?\s*", "", content, flags=re.IGNORECASE)
                content = re.sub(r"```\s*", "", content)
                content = content.strip()

            # Try to find JSON object using proper brace matching
            # Find the first { and match it with the corresponding }
            start_idx = content.find("{")
            json_str = None
            if start_idx >= 0:
                brace_count = 0
                end_idx = start_idx
                in_string = False
                escape_next = False

                for i in range(start_idx, len(content)):
                    char = content[i]

                    if escape_next:
                        escape_next = False
                        continue

                    if char == '\\':
                        escape_next = True
                        continue

                    if char == '"' and not escape_next:
                        in_string = not in_string
                        continue

                    if not in_string:
                        if char == "{":
                            brace_count += 1
                        elif char == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                json_str = content[start_idx:end_idx]
                                try:
                                    data = json.loads(json_str)
                                    if isinstance(data, dict):
                                        logger.debug(f"[AI] Successfully parsed JSON: {json_str[:200]}")
                                        return data
                                except json.JSONDecodeError as e:
                                    logger.debug(f"[AI] JSON parse error: {e}, extracted: {json_str[:200]}")
                                break

                # If we found a start but no end (incomplete JSON), try to complete it intelligently
                if brace_count > 0 and json_str:
                    # Try to complete the JSON by adding missing parts
                    try:
                        # Check what's missing
                        if '"confidence"' in json_str and not json_str.rstrip().endswith('}'):
                            # Try to extract confidence value and complete
                            confidence_match = re.search(r'"confidence":\s*(\d+(?:\.\d+)?)', json_str)
                            if confidence_match:
                                # JSON is likely cut off after confidence, add closing
                                completed = json_str.rstrip().rstrip(',') + '}'
                            else:
                                # Add default confidence and close
                                completed = json_str.rstrip().rstrip(',') + ', "confidence": 0.9}'
                        else:
                            # Just add closing braces
                            completed = json_str.rstrip().rstrip(',') + '}' * brace_count

                        data = json.loads(completed)
                        if isinstance(data, dict):
                            logger.debug(f"[AI] Successfully parsed JSON (completed): {completed[:200]}")
                            return data
                    except json.JSONDecodeError as e:
                        logger.debug(f"[AI] Failed to complete JSON: {e}, partial: {json_str[:200]}")

                        # Last resort: try to build minimal valid JSON from what we have
                        try:
                            # Extract what we can
                            has_deadline = '"has_deadline": true' in json_str
                            deadline_match = re.search(r'"deadline_text":\s*"([^"]*)"', json_str)
                            deadline_text = deadline_match.group(1) if deadline_match else None

                            if has_deadline and deadline_text:
                                # Build minimal valid JSON
                                minimal_json = f'{{"has_deadline": true, "deadline_text": "{deadline_text}", "confidence": 0.85, "intent": "new"}}'
                                data = json.loads(minimal_json)
                                logger.debug(f"[AI] Built minimal JSON from partial response: {minimal_json}")
                                return data
                        except Exception:
                            pass

            # If no complete JSON found, try to extract and fix incomplete JSON
            # Look for JSON-like structure and try to complete it
            if "{" in content and "has_deadline" in content:
                # Try to extract the JSON part more carefully
                start_idx = content.find("{")
                if start_idx >= 0:
                    # Try to find the matching closing brace
                    brace_count = 0
                    end_idx = start_idx
                    for i in range(start_idx, len(content)):
                        if content[i] == "{":
                            brace_count += 1
                        elif content[i] == "}":
                            brace_count -= 1
                            if brace_count == 0:
                                end_idx = i + 1
                                break

                    if brace_count == 0:
                        json_str = content[start_idx:end_idx]
                        try:
                            data = json.loads(json_str)
                            if isinstance(data, dict):
                                logger.debug(f"[AI] Successfully parsed JSON (fixed): {json_str}")
                                return data
                        except json.JSONDecodeError as e:
                            logger.debug(f"[AI] JSON parse error: {e}, content: {json_str[:200]}")

            # Last resort: try parsing the entire content as JSON
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    logger.debug(f"[AI] Successfully parsed entire content as JSON")
                    return data
            except json.JSONDecodeError:
                pass

            logger.warning(f"[AI] No valid JSON found in response: {content[:200]}")
            return None

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
