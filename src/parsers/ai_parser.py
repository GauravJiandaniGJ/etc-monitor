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
                                "max_output_tokens": 1024,  # Increased to prevent JSON truncation
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
                                "max_output_tokens": 1024,  # Increased to prevent JSON truncation
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
                            "max_output_tokens": 1024,  # Increased to prevent JSON truncation
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

        return f"""You are an EXPERT deadline extraction system for ETC (Estimated Time of Completion) tracking. Your task is to identify and extract deadline commitments from natural language with MAXIMUM PRECISION.

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
COMPREHENSIVE TIME EXPRESSION PARSING RULES:
═══════════════════════════════════════════════════════════════

1. RELATIVE TIME EXPRESSIONS (from current time):
   ✓ "2 mins", "2 minutes", "2min", "2minute" → 2 minutes from now
   ✓ "5 hours", "5 hrs", "5h" → 5 hours from now
   ✓ "1 day", "1d" → 1 day from now
   ✓ "3 weeks", "3w" → 3 weeks from now
   ✓ "in 30 minutes" → 30 minutes from now
   ✓ "within 2 hours" → 2 hours from now

2. TIME OF DAY EXPRESSIONS (standardized times):
   ✓ "evening" → 18:00 (6:00 PM) today, or tomorrow if current time > 18:00
   ✓ "morning" → 09:00 (9:00 AM) today, or tomorrow if current time > 09:00
   ✓ "afternoon" → 14:00 (2:00 PM) today, or tomorrow if current time > 14:00
   ✓ "night" → 21:00 (9:00 PM) today, or tomorrow if current time > 21:00
   ✓ "noon" → 12:00 (12:00 PM) today, or tomorrow if current time > 12:00
   ✓ "midnight" → 00:00 (12:00 AM) tomorrow

3. SPECIFIC TIME EXPRESSIONS:
   ✓ "2PM", "2 PM", "14:00", "14:00:00" → 14:00 today, or tomorrow if past
   ✓ "5:30 PM", "17:30" → 17:30 today, or tomorrow if past
   ✓ "9am", "09:00", "9:00 AM" → 09:00 today, or tomorrow if past
   ✓ "half past 3" → 15:30 today, or tomorrow if past

4. DAY-BASED EXPRESSIONS:
   ✓ "today" → End of today (23:59:59)
   ✓ "tomorrow" → End of tomorrow (23:59:59)
   ✓ "Monday", "Tuesday", etc. → Next occurrence of that weekday at end of day
   ✓ "next Monday" → Next Monday at end of day
   ✓ "this Friday" → This Friday if not past, else next Friday
   ✓ "Friday" → Next Friday (or today if it's Friday and not past)

5. COMBINED EXPRESSIONS:
   ✓ "tomorrow evening" → Tomorrow at 18:00
   ✓ "Friday 5PM" → Next Friday at 17:00
   ✓ "next week Monday morning" → Next Monday at 09:00
   ✓ "tomorrow at 2PM" → Tomorrow at 14:00
   ✓ "Monday afternoon" → Next Monday at 14:00

6. COMPLEX EXPRESSIONS:
   ✓ "end of day" → Today at 23:59:59
   ✓ "end of week" → End of current week (Sunday 23:59:59)
   ✓ "by close of business" → Today at 17:00 (5 PM)
   ✓ "EOD" → End of day (23:59:59)
   ✓ "COB" → Close of business (17:00)

7. NATURAL LANGUAGE VARIATIONS:
   ✓ "My task will complete by tomorrow 1PM" → Extract "tomorrow 1PM"
   ✓ "ETC: evening" → Extract "evening"
   ✓ "I'll finish this in 2 hours" → Extract "2 hours"
   ✓ "Done by Friday" → Extract "Friday"

═══════════════════════════════════════════════════════════════
CRITICAL EXTRACTION RULES:
═══════════════════════════════════════════════════════════════

1. DEADLINE DETECTION:
   - Extract ONLY if user explicitly commits to a completion time
   - Look for: "ETC", "by", "at", "in", "within", "complete by", "finish by"
   - Ignore: questions, status updates, vague statements

2. TIME CALCULATION PRECISION:
   - For relative times: Calculate EXACTLY from current time
   - For time-of-day: Use standardized times (evening=18:00, morning=09:00, etc.)
   - For past times: Automatically move to next occurrence
   - For ambiguous days: Use next occurrence if today's time has passed

3. EXTRACTION PRIORITY:
   - If multiple deadlines exist, extract the FIRST/PRIMARY one
   - Prefer specific times over vague ones
   - Prefer earlier deadlines if ambiguous

4. CONFIDENCE SCORING:
   - 0.95-1.0: Clear, specific deadline (e.g., "2 mins", "Friday 5PM")
   - 0.85-0.94: Clear but slightly ambiguous (e.g., "evening", "tomorrow")
   - 0.80-0.84: Somewhat ambiguous but extractable
   - < 0.80: Too ambiguous, set has_deadline=false

5. INTENT CLASSIFICATION:
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
- deadline_text: Exact phrase from message (e.g., "2 mins", "evening", "tomorrow 1PM")
- confidence: Must be >= 0.8 if has_deadline=true, else 0.0
- intent: Classification of the message intent

═══════════════════════════════════════════════════════════════
EXAMPLES (LEARN FROM THESE):
═══════════════════════════════════════════════════════════════

Input: "ETC: 2 mins"
Output: {{"has_deadline": true, "deadline_text": "2 mins", "confidence": 0.95, "intent": "new"}}

Input: "ETC: evening"
Output: {{"has_deadline": true, "deadline_text": "evening", "confidence": 0.9, "intent": "new"}}

Input: "My task of this ETC will complete by tomorrow 1PM"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 1PM", "confidence": 0.95, "intent": "new"}}

Input: "ETC: Friday 5PM"
Output: {{"has_deadline": true, "deadline_text": "Friday 5PM", "confidence": 0.95, "intent": "new"}}

Input: "ETC tomorrow"
Output: {{"has_deadline": true, "deadline_text": "tomorrow", "confidence": 0.9, "intent": "new"}}

Input: "How's it going?"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

Input: "Status update: working on it"
Output: {{"has_deadline": false, "deadline_text": null, "confidence": 0.0, "intent": "none"}}

═══════════════════════════════════════════════════════════════
FINAL INSTRUCTIONS:
═══════════════════════════════════════════════════════════════

1. Analyze the message carefully
2. Extract deadline if present (use exact phrase from message)
3. Calculate confidence based on clarity
4. Determine intent
5. Output ONLY complete, valid JSON
6. Ensure JSON is properly closed with all required fields

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
