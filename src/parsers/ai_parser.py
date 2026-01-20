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

                    # CRITICAL VALIDATION: Multiple checks to ensure correct extraction
                    original_upper = text.upper()
                    extracted_upper = deadline_text.upper() if deadline_text else ""
                    original_has_pm_am = 'PM' in original_upper or 'AM' in original_upper
                    extracted_has_pm_am = 'PM' in extracted_upper or 'AM' in extracted_upper

                    # Check for colon-separated time in original (e.g., "2:30", "14:30")
                    original_has_colon_time = bool(re.search(r'\d{1,2}:\d{2}', text))
                    extracted_has_colon_time = bool(re.search(r'\d{1,2}:\d{2}', deadline_text)) if deadline_text else False

                    # Check for relative time indicators in extracted text
                    relative_time_indicators = ['MIN', 'MINS', 'MINUTE', 'MINUTES', 'HOUR', 'HOURS', 'HR', 'HRS', 'DAY', 'DAYS', 'WEEK', 'WEEKS']
                    extracted_has_relative = any(ind in extracted_upper for ind in relative_time_indicators)

                    # CRITICAL CHECK 1: If original has PM/AM but extracted doesn't, it's a critical error
                    if original_has_pm_am and not extracted_has_pm_am:
                        logger.error(f'[AI] CRITICAL ERROR: Original text "{text}" contains PM/AM but extracted "{deadline_text}" does not! Rejecting extraction.')
                        return None

                    # CRITICAL CHECK 2: If original has specific time (colon format like "2:30") but extracted is relative time, reject
                    if original_has_colon_time and extracted_has_relative:
                        logger.error(f'[AI] CRITICAL ERROR: Original text "{text}" contains specific time (colon format) but extracted "{deadline_text}" is relative time! Rejecting extraction.')
                        return None

                    # CRITICAL CHECK 3: If original has "X:XX PM/AM" pattern but extracted doesn't preserve the time
                    if original_has_pm_am and original_has_colon_time:
                        # Original has something like "2:30 PM", extracted should preserve this
                        original_time_match = re.search(r'(\d{1,2}):(\d{2})\s*(?:AM|PM)', text, re.IGNORECASE)
                        if original_time_match:
                            original_hour = original_time_match.group(1)
                            original_minute = original_time_match.group(2)
                            # Check if extracted preserves the same time components
                            if not (original_hour in deadline_text and original_minute in deadline_text):
                                logger.error(f'[AI] CRITICAL ERROR: Original time "{original_time_match.group(0)}" not preserved in extracted "{deadline_text}"! Rejecting extraction.')
                                return None

                    # CRITICAL CHECK 4: Validate that key numbers from original are preserved
                    # Find all numbers in original text
                    original_numbers = re.findall(r'\d+', text)
                    extracted_numbers = re.findall(r'\d+', deadline_text) if deadline_text else []

                    # For relative time patterns, check that the main number is preserved
                    # E.g., "ETC 5 minutes" should extract something with "5" in it
                    relative_words_in_original = any(word in text.lower() for word in ['min', 'minute', 'hour', 'hr', 'day', 'week'])
                    if relative_words_in_original and original_numbers:
                        # CRITICAL: If original has relative time (minutes/hours) but extracted has PM/AM, REJECT
                        # Example: "3 minutes" should NOT become "3:30 PM"
                        if extracted_has_pm_am:
                            logger.error(f'[AI] CRITICAL ERROR: Original "{text}" has relative time (minutes/hours) but extracted "{deadline_text}" has PM/AM! Rejecting extraction.')
                            return None

                        # Find the number closest to the relative time word
                        main_number = original_numbers[0]  # Usually the first number
                        for num in original_numbers:
                            # Check if this number is directly before a time unit
                            if re.search(rf'{num}\s*(?:min|minute|hour|hr|day|week)', text.lower()):
                                main_number = num
                                break

                        if main_number not in extracted_numbers:
                            logger.error(f'[AI] CRITICAL ERROR: Original number "{main_number}" from "{text}" not found in extracted "{deadline_text}"! Rejecting extraction.')
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
        """Build a professional, comprehensive prompt for deadline extraction."""
        current_date = now.strftime('%Y-%m-%d')
        current_day = now.strftime('%A')
        current_time_str = now.strftime('%H:%M')
        current_hour = now.hour

        # Determine time period for context
        if current_hour < 12:
            time_period = "morning"
        elif current_hour < 17:
            time_period = "afternoon"
        else:
            time_period = "evening"

        return f"""You are a precise deadline extraction system for ETC (Estimated Time of Completion) tracking in a corporate environment.

═══════════════════════════════════════════════════════════════
CURRENT CONTEXT
═══════════════════════════════════════════════════════════════
Date: {current_date} ({current_day})
Time: {current_time_str} ({time_period})
Timezone: Asia/Kolkata (IST)

═══════════════════════════════════════════════════════════════
MESSAGE TO ANALYZE
═══════════════════════════════════════════════════════════════
"{text}"

═══════════════════════════════════════════════════════════════
EXTRACTION RULES (MUST FOLLOW EXACTLY)
═══════════════════════════════════════════════════════════════

RULE 1: PRESERVE EXACT NUMBERS
- Extract the EXACT number from the message
- If message says "5 minutes" → extract "5 minutes"
- If message says "10 mins" → extract "10 mins"
- If message says "3 hours" → extract "3 hours"
- NEVER substitute different numbers

RULE 2: IDENTIFY TIME TYPE

RELATIVE TIME (duration from now):
- Contains units: min, mins, minute, minutes, hour, hours, hr, hrs, day, days, week, weeks
- Pattern: NUMBER + UNIT (e.g., "15 mins", "3 hours", "1 day")
- NO AM/PM indicator
- Extract exactly: "15 mins" → "15 mins"

SPECIFIC TIME (clock time):
- Contains AM/PM (any case): "3 PM", "3pm", "3:30 PM"
- Contains colon with time: "14:30", "9:00"
- Extract exactly: "3:30 PM" → "3:30 PM"

TIME OF DAY:
- Words: morning, afternoon, evening, night, noon, midnight, EOD, COB
- Extract exactly: "evening" → "evening"

DAY REFERENCES:
- Words: today, tomorrow, Monday-Sunday, next week
- Can combine with time: "tomorrow 5PM" → "tomorrow 5PM"

RULE 3: HANDLE COMMON PATTERNS

"ETC: [time]" → Extract [time]
"ETC by [time]" → Extract [time] (remove "by")
"ETC [time]" → Extract [time]
"will complete by [time]" → Extract [time]
"done by [time]" → Extract [time]
"[status], ETC: [time]" → Extract [time]

RULE 4: CONFIDENCE SCORING
- 0.95: Clear, specific deadline (e.g., "3:45 PM", "tomorrow 2PM", "45 minutes")
- 0.90: Clear with slight ambiguity (e.g., "evening", "tomorrow", "Friday")
- 0.85: Somewhat ambiguous (e.g., "later today", "end of day")
- Below 0.80: Too vague, set has_deadline=false

RULE 5: REJECT NON-DEADLINES
Set has_deadline=false for:
- Questions: "What's the ETC?", "When will it be done?"
- Vague: "soon", "ASAP", "later"
- No time info: "Working on it", "In progress"
- Uncertain: "ETC TBD", "ETC unknown", "No ETC yet"

═══════════════════════════════════════════════════════════════
OUTPUT FORMAT (STRICT JSON)
═══════════════════════════════════════════════════════════════
{{
    "has_deadline": boolean,
    "deadline_text": "extracted text or null",
    "confidence": float (0.0-1.0),
    "intent": "new" | "update" | "cancel" | "none"
}}

═══════════════════════════════════════════════════════════════
EXAMPLES (LEARN THE PATTERN)
═══════════════════════════════════════════════════════════════

RELATIVE TIME EXAMPLES:
Input: "ETC 5 minutes"
Output: {{"has_deadline": true, "deadline_text": "5 minutes", "confidence": 0.95, "intent": "new"}}

Input: "ETC: 45 mins"
Output: {{"has_deadline": true, "deadline_text": "45 mins", "confidence": 0.95, "intent": "new"}}

Input: "i still need some time ETC 10 minutes"
Output: {{"has_deadline": true, "deadline_text": "10 minutes", "confidence": 0.95, "intent": "new"}}

Input: "Working on it, ETC 3 hours"
Output: {{"has_deadline": true, "deadline_text": "3 hours", "confidence": 0.95, "intent": "new"}}

Input: "Quick fix needed, ETC 15 mins"
Output: {{"has_deadline": true, "deadline_text": "15 mins", "confidence": 0.95, "intent": "new"}}

SPECIFIC TIME EXAMPLES:
Input: "ETC by 2:30 PM"
Output: {{"has_deadline": true, "deadline_text": "2:30 PM", "confidence": 0.95, "intent": "new"}}

Input: "ETC 5PM"
Output: {{"has_deadline": true, "deadline_text": "5 PM", "confidence": 0.95, "intent": "new"}}

Input: "will be done by 4:15 PM"
Output: {{"has_deadline": true, "deadline_text": "4:15 PM", "confidence": 0.95, "intent": "new"}}

Input: "ETC: 11 AM tomorrow"
Output: {{"has_deadline": true, "deadline_text": "11 AM tomorrow", "confidence": 0.95, "intent": "new"}}

DAY + TIME EXAMPLES:
Input: "ETC tomorrow 1PM"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 1PM", "confidence": 0.95, "intent": "new"}}

Input: "ETC by Friday 5PM"
Output: {{"has_deadline": true, "deadline_text": "Friday 5PM", "confidence": 0.95, "intent": "new"}}

Input: "Will complete by Monday morning"
Output: {{"has_deadline": true, "deadline_text": "Monday morning", "confidence": 0.95, "intent": "new"}}

TIME OF DAY EXAMPLES:
Input: "ETC evening"
Output: {{"has_deadline": true, "deadline_text": "evening", "confidence": 0.90, "intent": "new"}}

Input: "ETC by EOD"
Output: {{"has_deadline": true, "deadline_text": "EOD", "confidence": 0.90, "intent": "new"}}

Input: "ETC tomorrow afternoon"
Output: {{"has_deadline": true, "deadline_text": "tomorrow afternoon", "confidence": 0.95, "intent": "new"}}

CORPORATE STATUS UPDATES:
Input: "Facing some issues but ETC by 6 PM"
Output: {{"has_deadline": true, "deadline_text": "6 PM", "confidence": 0.95, "intent": "new"}}

Input: "Code review pending, ETC: Friday COB"
Output: {{"has_deadline": true, "deadline_text": "Friday COB", "confidence": 0.95, "intent": "new"}}

Input: "Testing in progress, ETC 2 hours"
Output: {{"has_deadline": true, "deadline_text": "2 hours", "confidence": 0.95, "intent": "new"}}

NO DEADLINE (REJECT):
Input: "What's the ETC?"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

Input: "ETC TBD"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

Input: "Working on it"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

Input: "Will update soon"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

═══════════════════════════════════════════════════════════════
FINAL CHECKLIST BEFORE RESPONDING
═══════════════════════════════════════════════════════════════
1. Did I extract the EXACT number from the message?
2. Did I preserve the time unit exactly (mins, minutes, hours, etc.)?
3. Did I correctly identify relative vs specific time?
4. Is my confidence score appropriate?
5. Is the JSON complete and valid?

RESPOND WITH JSON ONLY:"""
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
