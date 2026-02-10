"""
AI-based ETC (Estimated Time of Completion) deadline parser using Gemini AI.

Production-grade implementation with:
- Fast async processing with proper timeout handling
- Always-on AI parsing (no skipping)
- Robust error handling and fallback
- Optimized for real-time responses
- Uses GeminiService for API communication (no duplication)
"""

import json
import re
from datetime import datetime
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import threading

from src.core.models import ParsedDeadline
from src.services.ai_service import GeminiService
from src.utils.logger import get_logger
from src.utils.timezone import now_ist

logger = get_logger("AIParser")


class AIParser:
    """
    Production-grade AI-based ETC parser.

    Delegates Gemini API communication to GeminiService, keeping this class
    focused on prompt engineering, response validation, and deadline extraction.

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
        self.timeout_seconds = timeout_seconds
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ai-parser")
        self._lock = threading.Lock()

        # Delegate all Gemini setup to GeminiService
        self._gemini = GeminiService(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_retries=1,  # Single attempt — we handle timeout ourselves
            retry_delay=0.5,
        )

        if self._gemini.is_configured():
            logger.success(f"AIParser initialized via GeminiService (timeout: {timeout_seconds}s)")
        else:
            logger.warning("AIParser: GeminiService not configured — AI parsing disabled")

    def is_available(self) -> bool:
        """Check if AI parser is available."""
        return self._gemini.is_configured()

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
        Call Gemini AI with timeout protection.

        Uses GeminiService for the actual API call, adding thread-pool
        timeout and response validation on top.

        Args:
            text: Message text
            now: Current time

        Returns:
            Parsed result dict or None
        """
        logger.info(f'[AI] Processing: "{text[:80]}..."')

        prompt = self._build_prompt(text, now)

        try:
            # Run GeminiService.generate() inside thread pool for timeout control
            def run_ai():
                return self._gemini.generate(prompt)

            future = self._executor.submit(run_ai)
            response_text = future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError:
            logger.warning(f'[AI] Timeout after {self.timeout_seconds}s')
            return None
        except Exception as e:
            logger.error(f'[AI] Generation failed: {e}')
            return None

        if not response_text:
            logger.warning('[AI] Empty response from Gemini')
            return None

        logger.debug(f'[AI] Raw response: {response_text[:500]}')

        result = self._parse_response(response_text)
        if result and result.get("has_deadline"):
            deadline_text = result.get("deadline_text", "")
            confidence = result.get("confidence", 0.0)

            # --- CRITICAL VALIDATION ---
            if not self._validate_extraction(text, deadline_text):
                return None

            logger.success(f'[AI] Extracted: "{deadline_text}" (confidence: {confidence:.2f})')
        else:
            logger.debug('[AI] No deadline found in response')

        return result

    def _validate_extraction(self, original: str, extracted: str) -> bool:
        """Validate that the AI extraction is consistent with the original text.

        Runs multiple sanity checks to catch hallucinated or incorrect extractions.

        Args:
            original: Original message text
            extracted: Extracted deadline text from AI

        Returns:
            True if extraction passes all checks
        """
        if not extracted:
            return True  # No extraction to validate

        original_upper = original.upper()
        extracted_upper = extracted.upper()
        original_has_pm_am = 'PM' in original_upper or 'AM' in original_upper
        extracted_has_pm_am = 'PM' in extracted_upper or 'AM' in extracted_upper

        original_has_colon_time = bool(re.search(r'\d{1,2}:\d{2}', original))
        extracted_has_relative = any(
            ind in extracted_upper
            for ind in ['MIN', 'MINS', 'MINUTE', 'MINUTES', 'HOUR', 'HOURS',
                        'HR', 'HRS', 'DAY', 'DAYS', 'WEEK', 'WEEKS']
        )

        # CHECK 1: Original has PM/AM but extracted doesn't
        if original_has_pm_am and not extracted_has_pm_am:
            logger.error(f'[AI] CRITICAL: Original "{original}" has PM/AM but extracted "{extracted}" does not — rejecting')
            return False

        # CHECK 2: Original has specific time but extracted is relative
        if original_has_colon_time and extracted_has_relative:
            logger.error(f'[AI] CRITICAL: Original "{original}" has specific time but extracted "{extracted}" is relative — rejecting')
            return False

        # CHECK 3: Original has "X:XX PM/AM" but extracted doesn't preserve time
        if original_has_pm_am and original_has_colon_time:
            match = re.search(r'(\d{1,2}):(\d{2})\s*(?:AM|PM)', original, re.IGNORECASE)
            if match:
                hour, minute = match.group(1), match.group(2)
                if not (hour in extracted and minute in extracted):
                    logger.error(f'[AI] CRITICAL: Original time "{match.group(0)}" not preserved in "{extracted}" — rejecting')
                    return False

        # CHECK 4: Validate key numbers preserved for relative time
        original_numbers = re.findall(r'\d+', original)
        extracted_numbers = re.findall(r'\d+', extracted)
        relative_words_in_original = any(word in original.lower() for word in ['min', 'minute', 'hour', 'hr', 'day', 'week'])

        if relative_words_in_original and original_numbers:
            if extracted_has_pm_am:
                logger.error(f'[AI] CRITICAL: Original "{original}" has relative time but extracted "{extracted}" has PM/AM — rejecting')
                return False

            main_number = original_numbers[0]
            for num in original_numbers:
                if re.search(rf'{num}\s*(?:min|minute|hour|hr|day|week)', original.lower()):
                    main_number = num
                    break

            if main_number not in extracted_numbers:
                logger.error(f'[AI] CRITICAL: Number "{main_number}" from "{original}" not in "{extracted}" — rejecting')
                return False

        # Warn (but don't reject) if extracted adds PM/AM that wasn't in original
        if extracted_has_pm_am and not original_has_pm_am:
            if '12' in original_upper and ('12 AM' in extracted_upper or '12 PM' in extracted_upper):
                logger.debug(f'[AI] Context-aware AM/PM addition for "{original}" → "{extracted}"')
            else:
                logger.warning(f'[AI] Extracted "{extracted}" has PM/AM but original "{original}" does not')

        return True

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

    def rephrase_task(self, task_text: str) -> Optional[str]:
        """Rephrase a task message into a concise single sentence.

        Delegates to GeminiService.rephrase_task().

        Args:
            task_text: Original task message text

        Returns:
            Rephrased task as single sentence, or original text if rephrasing fails
        """
        return self._gemini.rephrase_task(task_text)

    def __del__(self):
        """Cleanup executor on destruction."""
        if hasattr(self, '_executor'):
            self._executor.shutdown(wait=False)
