"""AI-based parser for ETC deadline detection using Gemini AI."""
import json
import re
from datetime import datetime
from typing import Optional, Dict
from src.core.models import ParsedDeadline
from src.utils.logger import get_logger
from src.utils.timezone import now_ist


logger = get_logger('AIParser')


# Check if Gemini is available
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning('google-generativeai not installed. AI parsing will not be available.')


class AIParser:
    """AI-based deadline parser using Gemini.
    
    Uses Gemini AI to intelligently parse deadline expressions from
    natural language text. Falls back gracefully if API is not available.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = 'gemini-1.5-flash',
        temperature: float = 0.2
    ):
        """Initialize AI parser.
        
        Args:
            api_key: Gemini API key
            model: Gemini model name
            temperature: Generation temperature (0.0-2.0)
        """
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.client = None
        
        if not GEMINI_AVAILABLE:
            logger.info('Gemini package not available')
            return
        
        if not api_key:
            logger.info('Gemini API key not configured')
            return
        
        try:
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(
                model_name=model,
                generation_config={
                    'temperature': temperature,
                    'max_output_tokens': 2048,
                }
            )
            logger.success(f'Gemini AI initialized with model: {model}')
        except Exception as e:
            logger.error('Failed to initialize Gemini AI', exc=e)
            self.client = None
    
    def is_available(self) -> bool:
        """Check if AI parser is available.
        
        Returns:
            True if Gemini client is configured
        """
        return self.client is not None
    
    def parse_deadline(
        self,
        text: str,
        reference_time: Optional[datetime] = None
    ) -> Optional[ParsedDeadline]:
        """Parse deadline using Gemini AI.
        
        Args:
            text: Text to parse
            reference_time: Reference datetime (defaults to now in IST)
            
        Returns:
            ParsedDeadline object or None if parsing fails
        """
        if not self.is_available():
            logger.debug('AI parser not available')
            return None
        
        if not text:
            return None
        
        now = reference_time if reference_time else now_ist()
        
        try:
            # Build prompt for Gemini
            prompt = self._build_prompt(text, now)
            
            # Call Gemini API
            response = self.client.generate_content(
                prompt,
                generation_config={
                    'temperature': self.temperature,
                    'max_output_tokens': 2048,
                }
            )
            
            if not response or not response.text:
                logger.warning('Gemini returned empty response')
                return None
            
            # Parse response
            result = self._parse_response(response.text)
            
            if result and result.get('has_deadline'):
                deadline_text = result.get('deadline_text', '')
                confidence = result.get('confidence', 0.5)
                
                if deadline_text:
                    logger.success(f'AI parsed deadline: "{deadline_text}" (confidence: {confidence})')
                    # Note: We return the text, not the datetime
                    # The datetime parsing will be done by DateTimeParser
                    return ParsedDeadline(
                        original_text=text,
                        deadline_datetime=now,  # Placeholder - will be parsed later
                        reminder_datetime=now,  # Placeholder - will be calculated later
                        confidence=confidence,
                        parsed_by='ai'
                    )
            
            return None
            
        except Exception as e:
            logger.error('Gemini API call failed', exc=e)
            return None
    
    def _build_prompt(self, text: str, now: datetime) -> str:
        """Build Gemini prompt for deadline parsing.
        
        Args:
            text: Text to parse
            now: Current datetime
            
        Returns:
            Formatted prompt string
        """
        current_date = now.strftime('%Y-%m-%d')
        current_day = now.strftime('%A')
        current_time_str = now.strftime('%H:%M:%S')
        current_datetime_iso = now.isoformat()
        
        prompt = f"""You are an EXPERT AI deadline parser for an ETC (Estimated Time of Completion) reminder system. Your job is to be COMPREHENSIVE and catch EVERY possible time/date expression - nothing should be missed.

CURRENT CONTEXT:
- Current date: {current_date} ({current_day})
- Current time: {current_time_str}
- Current datetime (ISO): {current_datetime_iso}
- Timezone: Asia/Kolkata

USER MESSAGE: "{text}"

YOUR EXPERT TASK:
1. ACTIVELY search for ANY ETC deadline in the message - be aggressive, don't miss anything
2. Extract the COMPLETE time/date portion - include everything mentioned (day, date, time)
3. Normalize it for parsing (e.g., "2min" → "2 minutes", "tomorrow 3pm" → "tomorrow 3pm")
4. Provide intelligent, expert-level understanding

COMPREHENSIVE ANALYSIS RULES (MISS NOTHING - BE AN EXPERT):
- ETC can appear as: "ETC:", "ETC ", "ETC-", "ETC=", "ETC(", "etc:", "etc ", "Etc:"
- Extract EVERYTHING after ETC until end of message or punctuation
- Handle ALL relative times: "2min", "2 min", "2mins", "2minutes", "in 2 min", "2 min from now", "2m", "2h", "2hrs", "half hour", "quarter hour"
- Handle ALL absolute times: "today 5 PM", "today at 5pm", "tomorrow 3pm", "tomorrow at 3:00 PM", "tomorrow morning", "tomorrow evening"
- Handle ALL days: "today", "tomorrow", "tonight", "day after tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
- Handle ALL day variations: "next monday", "this friday", "coming monday", "next week monday", "monday next week", "upcoming friday"
- Handle ALL date formats: "Dec 25", "25th Dec", "25 Dec", "December 25", "25/12", "12/25", "2024-12-25", "jan 15", "15 jan"
- Handle ALL time formats: "5pm", "5 PM", "5:00pm", "17:00", "17:00:00", "5 o'clock", "five pm", "5p", "5 p.m."
- Handle ALL EOD expressions (EOD = End of Day = 7:00 PM office hours):
  * "EOD", "eod", "end of day", "end of business", "close of business", "COB", "cob"
  * "by EOD", "till EOD", "until EOD", "before EOD"
  * "tomorrow EOD", "by tomorrow EOD", "friday EOD", "monday EOD"
  * "this week EOD", "next week EOD"
- Handle ALL time of day expressions:
  * "morning" = 9:00 AM, "early morning" = 7:00 AM, "late morning" = 11:00 AM
  * "noon" = 12:00 PM, "lunch" = 12:30 PM, "afternoon" = 2:00 PM, "late afternoon" = 4:00 PM
  * "evening" = 7:00 PM, "late evening" = 8:00 PM, "dinner" = 7:30 PM
  * "night" = 9:00 PM, "late night" = 11:00 PM, "midnight" = 12:00 AM
- Handle ALL combinations: "friday EOD", "tomorrow 3pm", "next monday morning", "Dec 25 10am", "today evening", "by tomorrow EOD"
- Handle ALL relative expressions: "in 2 hours", "2 hours later", "after 2 hours", "2 hours from now", "within 2 hours"
- Handle ALL week expressions: "this week", "next week", "week after next", "in 2 weeks", "end of week", "start of week"
- Handle ALL month expressions: "next month", "end of month", "beginning of month", "month end", "EOM"
- Handle ALL "by/till/until" patterns: "by 5pm", "till friday", "until tomorrow", "before EOD", "by tomorrow EOD"
- Handle informal expressions: "asap", "soon", "later today", "shortly", "in a bit", "in a while"
- Be SMART about context: "ETC: 2min" = 2 minutes from now, "ETC: today 5pm" = today at 5pm
- If multiple times mentioned, extract the PRIMARY/MOST SPECIFIC one
- If day AND time mentioned, extract BOTH: "friday 3pm" → "friday 3pm" (not just "friday" or just "3pm")
- If date AND time mentioned, extract BOTH: "Dec 25 10am" → "Dec 25 10am"
- PRESERVE EOD in deadline_text: "tomorrow EOD" should stay as "tomorrow EOD" not converted

RESPONSE FORMAT (JSON only):
{{
    "has_deadline": true/false,
    "deadline_text": "COMPLETE extracted time/date (include day+date+time if all mentioned)",
    "confidence": 0.0-1.0,
    "reason": "brief expert explanation"
}}

CRITICAL INSTRUCTIONS:
- Be AGGRESSIVE in detection - if ETC is mentioned, extract EVERYTHING
- Include ALL parts: if both day AND time mentioned, extract BOTH
- For RELATIVE TIMES: ALWAYS preserve the time unit! "1 min" → "1 min", "3 mins" → "3 mins", "5 hours" → "5 hours"
- DO NOT convert "1 min" to just "1" or "3 mins" to just "3" - this will cause errors!
- Normalize but preserve meaning: "2min" → "2 min", "tomorrow 3pm" → "tomorrow 3pm"
- Confidence should be HIGH (0.95+) for clear ETC requests
- Only return has_deadline=false if absolutely certain it's NOT an ETC request
- Return ONLY valid JSON, no markdown, no code blocks, no explanations outside JSON"""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> Optional[Dict]:
        """Parse Gemini response and extract JSON.
        
        Args:
            response_text: Raw response from Gemini
            
        Returns:
            Parsed JSON dict or None
        """
        try:
            content = response_text.strip()
            
            # Remove markdown formatting if present
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            # Try to extract JSON if there's extra text
            json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            
            # Parse JSON
            result = json.loads(content)
            logger.debug(f'Parsed Gemini response: {result}')
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f'Failed to parse Gemini JSON: {e}')
            logger.debug(f'Raw content: {response_text}')
            
            # Try harder to extract JSON
            try:
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                    logger.debug(f'Extracted JSON: {result}')
                    return result
            except Exception:
                pass
            
            return None
        except Exception as e:
            logger.error('Unexpected error parsing Gemini response', exc=e)
            return None
    
    def get_deadline_text(self, text: str) -> Optional[str]:
        """Extract deadline text from message using Gemini.
        
        This is a convenience method that returns just the deadline text
        instead of a full ParsedDeadline object.
        
        Args:
            text: Text to parse
            
        Returns:
            Extracted deadline text or None
        """
        if not self.is_available():
            return None
        
        try:
            prompt = self._build_prompt(text, now_ist())
            response = self.client.generate_content(
                prompt,
                generation_config={
                    'temperature': self.temperature,
                    'max_output_tokens': 2048,
                }
            )
            
            if response and response.text:
                result = self._parse_response(response.text)
                if result and result.get('has_deadline'):
                    return result.get('deadline_text')
            
        except Exception as e:
            logger.error('Failed to extract deadline text with AI', exc=e)
        
        return None
