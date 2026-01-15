"""
AI-based ETC (Estimated Time of Completion) deadline parser using Gemini AI.

This module is production-hardened for real-world human messages:
- Slack / WhatsApp / Jira / Comments / Threads
- Handles new ETCs, updates, cancellations
- Aggressive detection with strict false-positive control
- Deterministic JSON-only AI responses
"""

import json
import re
from datetime import datetime
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

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
    Senior-grade AI-based ETC parser.

    Design goals:
    - Precision > Recall
    - Zero hallucinations
    - Safe for threaded updates
    - Day-2 operations ready
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.15,
        timeout_seconds: int = 5,
    ):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = 8  # Increased to 8 seconds for reliable AI processing
        self.client = None

        if not GEMINI_AVAILABLE:
            return

        if not api_key:
            logger.info("Gemini API key not configured")
            return

        try:
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(
                model_name=model,
                generation_config={
                    "temperature": temperature,
                    "max_output_tokens": 1024,
                },
            )
            logger.success(f"Gemini initialized: {model}")
        except Exception as e:
            logger.error("Failed to initialize Gemini", exc=e)
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def parse_deadline(
        self, text: str, reference_time: Optional[datetime] = None
    ) -> Optional[ParsedDeadline]:
        """
        Full ETC parsing entry point.
        Returns ParsedDeadline or None.
        """
        if not self.is_available() or not text:
            return None

        now = reference_time or now_ist()

        result = self._call_ai(text, now)
        if not result or not result.get("has_deadline"):
            return None

        confidence = float(result.get("confidence", 0.0))

        if confidence < 0.6:
            return None

        # Extract deadline text from AI response
        deadline_text = result.get("deadline_text", text)

        return ParsedDeadline(
            original_text=deadline_text,  # Store AI-extracted text
            deadline_datetime=now,     # resolved later by datetime parser
            reminder_datetime=now,     # calculated later
            confidence=confidence,
            parsed_by="ai"
        )

    def get_deadline_text(self, text: str) -> Optional[str]:
        """
        Lightweight helper: extract only deadline text.
        """
        if not self.is_available() or not text:
            return None

        result = self._call_ai(text, now_ist())
        if result and result.get("has_deadline"):
            return result.get("deadline_text")

        return None

    # ------------------------------------------------------------------
    # AI EXECUTION
    # ------------------------------------------------------------------

    def _call_ai(self, text: str, now: datetime) -> Optional[Dict]:
        logger.info(f'[AI] Calling Gemini API for text: "{text[:100]}..."')
        logger.info(f'[AI] Full message length: {len(text)} characters')
        prompt = self._build_prompt(text, now)

        def run():
            return self.client.generate_content(prompt)

        executor = ThreadPoolExecutor(max_workers=1)

        try:
            future = executor.submit(run)
            response = future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError:
            logger.warning(f'[AI] Gemini timeout after {self.timeout_seconds} seconds')
            return None
        except Exception as e:
            logger.error(f'[AI] Gemini execution failed: {e}', exc=e)
            return None
        finally:
            executor.shutdown(wait=False)

        if not response or not response.text:
            logger.warning('[AI] Gemini returned empty response')
            return None

        logger.info(f'[AI] Received response from Gemini: {len(response.text)} characters')
        result = self._parse_response(response.text)
        if result and result.get("has_deadline"):
            deadline_text = result.get("deadline_text")
            confidence = result.get("confidence", 0.0)
            logger.success(f'[AI] Successfully extracted deadline: "{deadline_text}" (confidence: {confidence})')
        else:
            logger.warning(f'[AI] Did not find deadline in response. Result: {result}')
        return result

    # ------------------------------------------------------------------
    # PROMPT (MAX-STRENGTH)
    # ------------------------------------------------------------------

    def _build_prompt(self, text: str, now: datetime) -> str:
        return f"""
You are a SENIOR ETC (Estimated Time of Completion) INTENT PARSER with 15+ years of experience building production-grade systems.

Your responsibility is STRICT detection of deadline commitments.
False positives are worse than misses.

────────────────────────────────
SYSTEM CONTEXT (AUTHORITATIVE)
────────────────────────────────
Current date: {now.strftime('%Y-%m-%d')}
Current day: {now.strftime('%A')}
Current time: {now.strftime('%H:%M:%S')}
Timezone: Asia/Kolkata (IST)

────────────────────────────────
USER MESSAGE (RAW)
────────────────────────────────
{text}

────────────────────────────────
WHAT QUALIFIES AS ETC
────────────────────────────────
A message qualifies ONLY if the user is:
• Committing to a completion time
• Updating a previous commitment
• Explicitly cancelling an earlier ETC

DO NOT extract if:
• The message is a question
• The message is speculative
• The message is historical
• The message is conditional

────────────────────────────────
VALID ETC SIGNALS
────────────────────────────────
Explicit:
ETC:, ETA:, etc is, etc of, etc for, delivery by, will finish by

Natural Language (CRITICAL - DETECT THESE):
"My etc for this project is of 2 hours" → extract "2 hours"
"My etc for this project is with in 5 hours" → extract "5 hours" (handle "with in" typo)
"My etc for this project is within 5 hours" → extract "5 hours"
"The etc for this task is 5 mins" → extract "5 mins"
"My etc is of 3 hours" → extract "3 hours"
"etc for this project is of 1 hour" → extract "1 hour"
"etc is 2 hours" → extract "2 hours"
"etc of 30 mins" → extract "30 mins"
"my etc for project is 2 hours" → extract "2 hours"

Implicit:
"I'll take 30 mins"
"Wrapping up in an hour"
"Should be done by evening"
"Need 2 hours"

Updates:
"Updated ETC"
"Revised ETA"
"Change it to tomorrow"
"Actually make it 45 mins"

Cancellations:
"Ignore previous ETC"
"No ETC now"
"Cancel the deadline"
"Removing ETA"

────────────────────────────────
TIME EXPRESSIONS TO SUPPORT
────────────────────────────────
Relative:
2 min, 2 mins, 2m, half hour, in 30 mins, within 1 hour, with in 5 hours (typo for "within")

Absolute:
today 5pm, tomorrow 3pm, friday EOD, next monday morning,
25 Dec 10am, 2025-01-15 17:00

Business terms:
EOD / COB = preserve as text (DO NOT convert)

Time-of-day:
morning=9am, afternoon=2pm, evening=7pm, night=9pm

────────────────────────────────
MULTIPLE TIMES RULE
────────────────────────────────
If multiple times exist:
• Prefer explicit over vague
• Prefer updated over original
• Prefer later correction

────────────────────────────────
NORMALIZATION
────────────────────────────────
Allowed:
"2min" → "2 min"
"5pm" → "5 pm"

Forbidden:
• Datetime conversion
• Unit removal
• Guessing missing info

────────────────────────────────
CONFIDENCE SCORING
────────────────────────────────
0.95+ → explicit ETC
0.80 → clear but informal
0.60 → weak but actionable
<0.60 → do NOT extract

────────────────────────────────
OUTPUT FORMAT (JSON ONLY)
────────────────────────────────
{{
  "has_deadline": true | false,
  "deadline_text": "exact phrase or null",
  "confidence": 0.0-1.0,
  "intent": "new | update | cancel | none",
  "reason": "short factual explanation"
}}

ABSOLUTE RULES:
• JSON only
• No markdown
• No extra text
• If unsure → has_deadline=false
"""

    # ------------------------------------------------------------------
    # RESPONSE PARSING
    # ------------------------------------------------------------------

    def _parse_response(self, response_text: str) -> Optional[Dict]:
        try:
            content = response_text.strip()

            if "```" in content:
                content = re.sub(r"```.*?```", "", content, flags=re.S).strip()

            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                return None

            data = json.loads(match.group(0))

            if not isinstance(data, dict):
                return None

            return data

        except Exception as e:
            logger.warning(f"Failed to parse Gemini JSON: {e}")
            return None
