import re
import uuid
import sqlite3
import json
import os
import requests
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import pytz
import dateparser

# Optional Gemini AI import - bot works without it
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️  google-generativeai not installed. Install with: pip install google-generativeai")
    print("   Bot will work with regex-based parsing only.")


@dataclass
class Reminder:
    """Data structure for storing deadline reminders"""
    id: str
    user_id: str
    channel_id: str
    message_ts: str
    thread_ts: Optional[str] = None
    original_text: str = ""
    matched_text: str = ""
    due_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class DeadlineAgent:
    """AI agent that detects deadlines in user messages and triggers reminders"""

    def __init__(self, timezone: str = 'UTC', db_path: str = 'reminders.db'):
        self.timezone = pytz.timezone(timezone)
        self.db_path = db_path
        self.reminders: Dict[str, Reminder] = {}
        self.user_history: Dict[str, List[Dict]] = {}  # Track user's last ETC for context
        self._last_suggested_response: Optional[str] = None  # Store last Gemini response

        # Gemini API configuration
        self.gemini_api_key = os.getenv('GEMINI_API_KEY')
        self.gemini_model = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')
        self.gemini_temperature = float(os.getenv('GEMINI_TEMPERATURE', '0.2'))

        # Initialize Gemini if API key is provided and package is available
        if not GEMINI_AVAILABLE:
            print("ℹ️  Gemini package not installed - using regex fallback only")
            print("   To enable Gemini: pip install google-generativeai")
            self.gemini_client = None
        elif self.gemini_api_key:
            try:
                genai.configure(api_key=self.gemini_api_key)
                self.gemini_client = genai.GenerativeModel(
                    model_name=self.gemini_model,
                    generation_config={
                        'temperature': self.gemini_temperature,
                        'max_output_tokens': 2048,
                    }
                )
                print(f"✅ Gemini API initialized with model: {self.gemini_model}")
            except Exception as e:
                print(f"⚠️  Error initializing Gemini API: {e}")
                print("   Falling back to regex-based parsing")
                self.gemini_client = None
        else:
            print("ℹ️  Gemini API key not configured - using regex fallback only")
            self.gemini_client = None

        self._init_database()
        self._load_reminders_from_db()

        # Contextual patterns for professional intelligence - highest priority
        self.contextual_patterns = [
            # Repeat/Again patterns
            r"^(again|repeat|same|re-schedule|reschedule|do\s+it\s+again|once\s+more|one\s+more\s+time)$",
            r"^(again|repeat|same|re-schedule|reschedule|do\s+it\s+again|once\s+more|one\s+more\s+time)\s+(for|in|at|on)\s+(.+)$",
            r"^(again|repeat|same|re-schedule|reschedule|do\s+it\s+again|once\s+more|one\s+more\s+time)\s+(.+)$",

            # Professional expressions
            r"^(schedule|set|create|add|make)\s+(another|one\s+more|additional)\s+(etc|reminder|deadline|meeting|call|task)$",
            r"^(schedule|set|create|add|make)\s+(another|one\s+more|additional)\s+(etc|reminder|deadline|meeting|call|task)\s+(for|in|at|on)\s+(.+)$",

            # Time-based repeats
            r"^(every|each|recurring|recur)\s+(.+)$",
            r"^(every|each|recurring|recur)\s+(.+)\s+(for|in|at|on)\s+(.+)$",
        ]

        # Comprehensive patterns that work with long messages and natural language
        # Order matters - more specific patterns first
        self.deadline_patterns = [
            # Till expressions with specific dates - highest priority
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))\s+(\d{1,2}(?::\d{2})?)",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",

            # Standalone times - high priority
            r"^(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))$",
            r"^(\d{1,2}(?::\d{2})?)$",

            # Days with times (most specific first)
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",
            r"on\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",

            # Professional expressions - highest priority (most flexible patterns first)
            r".*?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r".*?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r".*?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",

            # Advanced professional expressions
            r"(schedule|set|create|add|make)\s+(meeting|call|task|reminder|etc|deadline)\s+(for|in|at|on)\s+(.+)$",
            r"(need|want|require|must)\s+(meeting|call|task|reminder|etc|deadline)\s+(for|in|at|on)\s+(.+)$",
            r"(remind|notify|alert)\s+(me|us)\s+(for|in|at|on)\s+(.+)$",
            r"(follow\s+up|followup|follow-up)\s+(meeting|call|task|reminder)\s+(for|in|at|on)\s+(.+)$",
            r"(book|arrange|organize)\s+(meeting|call|task|reminder|etc|deadline)\s+(for|in|at|on)\s+(.+)$",

            # Specific date with time patterns (most specific first)
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(?:morning|evening|night))",

            # Short month format with time patterns
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\s+(?:morning|evening|night))",
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}\s+at\s+\d{1,2}(?::\d{2})?)",

            # Days of the week patterns with natural language
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(next-to-next|next\s+to\s+next|after\s+next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(next-to-next|next\s+to\s+next|after\s+next)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+morning",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+evening",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+night",
            r"on\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"on\s+a\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"on\s+the\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"by\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"until\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"until\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"until\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"till\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?)",
            r"till\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"till\s+(tomorrow|today|tonight)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(tomorrow|today|tonight)\s+(\d{1,2}(?::\d{2})?)",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))\s+(\d{1,2}(?::\d{2})?)",
            r"this\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",

            # Enhanced natural language patterns
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",

            # Week patterns
            r"(this\s+week|next\s+week|coming\s+week)",
            r"(this\s+week|next\s+week|coming\s+week)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            r"(this\s+week|next\s+week|coming\s+week)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+at\s+(\d{1,2}(?::\d{2})?)",

            # Time expressions with natural language
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(morning|evening|night|noon|midnight)",

            # Date patterns with natural language
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2})",
            r"(before|after|on|in|at|particular|on\s+that\s+day|after\s+that)\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+at\s+\d{1,2}(?::\d{2})?)",

            # Flexible time expressions
            r"(in\s+)?(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)\s+(before|after|from\s+now|later)",
            r"(in\s+)?(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)\s+(before|after|from\s+now|later)\s+(morning|evening|night)",


            # Time + day expressions (highest priority)
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))\s+(tomorrow|today|tonight)",
            r"(\d{1,2}(?::\d{2})?)\s+(tomorrow|today|tonight)",

            # Common informal expressions with time (higher priority)
            r"(tonight|today|tomorrow|day\s+after\s+tomorrow|yesterday)\s+at\s+(\d{1,2}(?::\d{2})?)",
            r"(tonight|today|tomorrow|day\s+after\s+tomorrow|yesterday)\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"(tonight|today|tomorrow|day\s+after\s+tomorrow|yesterday)\s+(morning|evening|night|noon|midnight)",
            # Common informal expressions without time (lower priority)
            r"(tonight|today|tomorrow|day\s+after\s+tomorrow|yesterday)",

            # EOD and time of day variations (comprehensive)
            r"(by\s+tomorrow\s+eod|tomorrow\s+eod|by\s+eod|till\s+eod|until\s+eod|before\s+eod)",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(eod|end\s+of\s+day)",
            r"(today\s+eod|tonight\s+eod|this\s+week\s+eod|next\s+week\s+eod)",
            r"(eod|end\s+of\s+day|end\s+of\s+work|close\s+of\s+business|cob|end\s+of\s+business|eob)",
            r"(morning|evening|night|noon|midnight|dawn|dusk)",
            r"(early\s+morning|late\s+evening|late\s+night|early\s+evening)",

            # Relative time patterns (most specific first)
            r"in\s+(\d+\s+(?:seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?))",

            # "at" time patterns
            r"at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"at\s+(evening|morning|noon|midnight)",

            # "by" patterns
            r"by\s+(EOD|eod|end of day)",
            r"by\s+(evening|night|morning|noon|midnight)",
            r"by\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"by\s+(.+?)(?:\s|$|\.|\,|\!|\?)",

            # "till" patterns
            r"till\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))",
            r"till\s+(evening|night|morning|noon|midnight)",

            # Date patterns (without time)
            r"in\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"on\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"till\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"by\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))",

            # Short month format without time
            r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2})(?:\s|$)",

            # Single word time references
            r"^(evening|morning|noon|midnight|tonight|today|tomorrow|eod|monday|tuesday|wednesday|thursday|friday|saturday|sunday)$",

            # "deadline" patterns
            r"deadline[:\s]+(.+?)(?:\s|$|\.|\,|\!|\?)",

            # "due" patterns
            r"due[:\s]+(.+?)(?:\s|$|\.|\,|\!|\?)",

            # "will [action] by/in" patterns (flexible)
            r"will\s+\w+.*?(?:by|in)\s+(.+?)(?:\s|$|\.|\,|\!|\?)",

            # "i will [action] by/in" patterns
            r"i\s+will\s+\w+.*?(?:by|in)\s+(.+?)(?:\s|$|\.|\,|\!|\?)",

            # "before" patterns
            r"before\s+(.+?)(?:\s|$|\.|\,|\!|\?)",
        ]

    def _is_etc_format(self, message: str) -> bool:
        """Check if message follows ETC format - comprehensive detection"""
        message_upper = message.upper().strip()

        # Comprehensive ETC patterns - catch ETC anywhere in message
        etc_patterns = [
            r'^ETC:\s*(.+)$',                    # ETC: [time/date]
            r'^ETC\s+(.+)$',                     # ETC [time/date]
            r'.*ETC:\s*(.+)$',                   # [text] ETC: [time/date]
            r'.*ETC\s+(.+)$',                    # [text] ETC [time/date]
            r'ETC\s*[:]\s*(.+)',                 # ETC: with flexible spacing
            r'ETC\s+(.+)',                       # ETC followed by anything
            r'ETC\s*-\s*(.+)',                   # ETC- [time/date]
            r'ETC\s*=\s*(.+)',                   # ETC= [time/date]
            r'ETC\s*\((.+)\)',                   # ETC([time/date])
        ]

        # Also check for common variations
        etc_keywords = ['ETC:', 'ETC ', 'ETC-', 'ETC=', 'ETC(']
        has_etc_keyword = any(keyword in message_upper for keyword in etc_keywords)

        # Check if message contains ETC followed by time/date indicators
        if has_etc_keyword:
            # Look for time/date patterns after ETC
            time_indicators = [
                r'\d+\s*(min|mins|minute|minutes|hour|hours|day|days|week|weeks)',
                r'(today|tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
                r'\d{1,2}(:\d{2})?\s*(am|pm|AM|PM)',
                r'(EOD|eod|end of day|morning|evening|night|noon)',
                r'\d{1,2}(st|nd|rd|th)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
            ]

            # Extract text after ETC
            etc_match = re.search(r'ETC[:\s\-=\(]*(.+)', message, re.IGNORECASE)
            if etc_match:
                etc_content = etc_match.group(1).strip()
                # Check if content has time/date indicators
                for indicator in time_indicators:
                    if re.search(indicator, etc_content, re.IGNORECASE):
                        return True
                # If ETC is followed by something, consider it valid
                if etc_content:
                    return True

        # Check regex patterns
        for pattern in etc_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        return False

    def _extract_etc_content(self, message: str) -> Optional[str]:
        """Extract the deadline part from ETC format - comprehensive extraction"""
        # IMPORTANT: Extract EVERYTHING after ETC, not just until first space
        # "etc 1 min" should extract "1 min", not just "1"

        # First, try to get everything after ETC (greedy patterns first)
        etc_patterns = [
            r'ETC:\s*(.+)$',                         # ETC: [rest of message] - GREEDY
            r'ETC\s+(.+)$',                          # ETC [rest of message] - GREEDY
            r'ETC\s*-\s*(.+)$',                      # ETC- [rest of message] - GREEDY
            r'ETC\s*=\s*(.+)$',                      # ETC= [rest of message] - GREEDY
            r'ETC\s*\(\s*(.+?)\s*\)',                # ETC([time/date])
        ]

        for pattern in etc_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                content = match.group(1).strip()
                # Clean up common trailing punctuation
                content = re.sub(r'[.,;!?]+$', '', content).strip()
                if content:
                    print(f"📝 Extracted ETC content: '{content}' from '{message}'")
                    return content

        # Fallback: extract everything after ETC
        etc_match = re.search(r'ETC[:\s\-=\(]*(.+)', message, re.IGNORECASE)
        if etc_match:
            content = etc_match.group(1).strip()
            # Remove trailing punctuation
            content = re.sub(r'[.,;!?]+$', '', content).strip()
            if content:
                return content

        return None

    def _call_gemini_api(self, message: str, user_history: Optional[Dict] = None) -> Optional[Dict]:
        """Call Gemini API to intelligently analyze ETC message and extract deadline information"""
        if not self.gemini_client:
            print("Gemini API not configured")
            return None

        try:
            current_time = datetime.now(self.timezone)
            current_date = current_time.strftime('%Y-%m-%d')
            current_day = current_time.strftime('%A')
            current_time_str = current_time.strftime('%H:%M:%S')
            current_datetime_iso = current_time.isoformat()

            # Build context from user history if available
            history_context = ""
            if user_history:
                last_etc = user_history.get('matched_text', '')
                last_due = user_history.get('due_at', '')
                if last_etc:
                    history_context = f"\nUser's last ETC was: '{last_etc}' (was due: {last_due})"

            prompt = f"""You are an EXPERT AI deadline parser for an ETC (Estimated Time of Completion) reminder system. Your job is to be COMPREHENSIVE and catch EVERY possible time/date expression - nothing should be missed.

CURRENT CONTEXT:
- Current date: {current_date} ({current_day})
- Current time: {current_time_str}
- Current datetime (ISO): {current_datetime_iso}
- Timezone: {self.timezone}{history_context}

USER MESSAGE: "{message}"

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
    "reason": "brief expert explanation",
    "suggested_response": "expert, friendly, contextual confirmation message"
}}

COMPREHENSIVE EXAMPLES (LEARN FROM ALL THESE - BE EXPERT):

=== RELATIVE TIME EXAMPLES (CRITICAL - PRESERVE THE UNIT!) ===
Input: "ETC: 2min"
Output: {{"has_deadline": true, "deadline_text": "2 min", "confidence": 0.99, "reason": "Relative time - 2 minutes from now", "suggested_response": "Got it! I'll remind you in 2 minutes."}}

Input: "ETC: 1 min"
Output: {{"has_deadline": true, "deadline_text": "1 min", "confidence": 0.99, "reason": "Relative time - 1 minute from now", "suggested_response": "Got it! I'll remind you in 1 minute."}}

Input: "ETC: 3 mins"
Output: {{"has_deadline": true, "deadline_text": "3 mins", "confidence": 0.99, "reason": "Relative time - 3 minutes from now", "suggested_response": "Perfect! I'll remind you in 3 minutes."}}

Input: "etc 1 min"
Output: {{"has_deadline": true, "deadline_text": "1 min", "confidence": 0.99, "reason": "Relative time - 1 minute from now", "suggested_response": "Got it! I'll remind you in 1 minute."}}

Input: "etc 5 min"
Output: {{"has_deadline": true, "deadline_text": "5 min", "confidence": 0.99, "reason": "Relative time - 5 minutes from now", "suggested_response": "Got it! I'll remind you in 5 minutes."}}

Input: "ETC: 30 mins"
Output: {{"has_deadline": true, "deadline_text": "30 mins", "confidence": 0.99, "reason": "Relative time - 30 minutes from now", "suggested_response": "Perfect! I'll remind you in 30 minutes."}}

Input: "ETC: 5 hours"
Output: {{"has_deadline": true, "deadline_text": "5 hours", "confidence": 0.99, "reason": "Relative time - 5 hours from now", "suggested_response": "Understood! I'll check back with you in 5 hours."}}

Input: "ETC: in 2 hours"
Output: {{"has_deadline": true, "deadline_text": "2 hours", "confidence": 0.99, "reason": "Relative time with 'in' prefix", "suggested_response": "Got it! I'll remind you in 2 hours."}}

Input: "ETC: 2 days"
Output: {{"has_deadline": true, "deadline_text": "2 days", "confidence": 0.99, "reason": "Relative time - 2 days from now", "suggested_response": "Understood! I'll remind you in 2 days."}}

Input: "ETC: half hour"
Output: {{"has_deadline": true, "deadline_text": "half hour", "confidence": 0.98, "reason": "Half hour = 30 minutes", "suggested_response": "Got it! I'll remind you in 30 minutes."}}

=== EOD EXAMPLES (END OF DAY = 7:00 PM) ===
Input: "ETC: EOD"
Output: {{"has_deadline": true, "deadline_text": "EOD", "confidence": 0.99, "reason": "End of day - today at 7:00 PM", "suggested_response": "Noted! I'll remind you at end of day (7:00 PM)."}}

Input: "ETC: by EOD"
Output: {{"has_deadline": true, "deadline_text": "EOD", "confidence": 0.99, "reason": "By end of day - today at 7:00 PM", "suggested_response": "Got it! I'll remind you by end of day (7:00 PM)."}}

Input: "ETC: tomorrow EOD"
Output: {{"has_deadline": true, "deadline_text": "tomorrow EOD", "confidence": 0.99, "reason": "Tomorrow end of day - 7:00 PM", "suggested_response": "Perfect! I'll remind you tomorrow at end of day (7:00 PM)."}}

Input: "ETC: by tomorrow EOD"
Output: {{"has_deadline": true, "deadline_text": "tomorrow EOD", "confidence": 0.99, "reason": "By tomorrow end of day - 7:00 PM", "suggested_response": "Noted! I'll remind you by tomorrow end of day (7:00 PM)."}}

Input: "ETC: friday EOD"
Output: {{"has_deadline": true, "deadline_text": "friday EOD", "confidence": 0.99, "reason": "Friday end of day - 7:00 PM", "suggested_response": "Got it! I'll remind you Friday at end of day (7:00 PM)."}}

Input: "ETC: monday EOD"
Output: {{"has_deadline": true, "deadline_text": "monday EOD", "confidence": 0.99, "reason": "Monday end of day - 7:00 PM", "suggested_response": "Noted! I'll remind you Monday at end of day (7:00 PM)."}}

Input: "ETC: end of day"
Output: {{"has_deadline": true, "deadline_text": "EOD", "confidence": 0.99, "reason": "End of day - today at 7:00 PM", "suggested_response": "Got it! I'll remind you at end of day (7:00 PM)."}}

Input: "ETC: till EOD"
Output: {{"has_deadline": true, "deadline_text": "EOD", "confidence": 0.99, "reason": "Till end of day - 7:00 PM", "suggested_response": "Understood! I'll remind you at end of day (7:00 PM)."}}

=== TODAY/TOMORROW EXAMPLES ===
Input: "ETC: today 5pm"
Output: {{"has_deadline": true, "deadline_text": "today 5pm", "confidence": 0.99, "reason": "Today at specific time", "suggested_response": "Got it! I'll remind you today at 5:00 PM."}}

Input: "ETC: today evening"
Output: {{"has_deadline": true, "deadline_text": "today evening", "confidence": 0.98, "reason": "Today evening - 7:00 PM", "suggested_response": "Understood! I'll remind you today evening (7:00 PM)."}}

Input: "ETC: tomorrow 3pm"
Output: {{"has_deadline": true, "deadline_text": "tomorrow 3pm", "confidence": 0.99, "reason": "Tomorrow at specific time", "suggested_response": "Perfect! I'll remind you tomorrow at 3:00 PM."}}

Input: "ETC: tomorrow morning"
Output: {{"has_deadline": true, "deadline_text": "tomorrow morning", "confidence": 0.99, "reason": "Tomorrow morning - 9:00 AM", "suggested_response": "Got it! I'll remind you tomorrow morning (9:00 AM)."}}

Input: "ETC: tomorrow afternoon"
Output: {{"has_deadline": true, "deadline_text": "tomorrow afternoon", "confidence": 0.99, "reason": "Tomorrow afternoon - 2:00 PM", "suggested_response": "Noted! I'll remind you tomorrow afternoon (2:00 PM)."}}

Input: "ETC: tonight"
Output: {{"has_deadline": true, "deadline_text": "tonight", "confidence": 0.99, "reason": "Tonight - 9:00 PM", "suggested_response": "Got it! I'll remind you tonight (9:00 PM)."}}

=== DAY OF WEEK EXAMPLES ===
Input: "ETC: friday 3pm"
Output: {{"has_deadline": true, "deadline_text": "friday 3pm", "confidence": 0.99, "reason": "Friday at specific time", "suggested_response": "Perfect! I'll remind you Friday at 3:00 PM."}}

Input: "ETC: next monday 10am"
Output: {{"has_deadline": true, "deadline_text": "next monday 10am", "confidence": 0.99, "reason": "Next Monday at specific time", "suggested_response": "Excellent! I'll remind you next Monday at 10:00 AM."}}

Input: "ETC: this friday afternoon"
Output: {{"has_deadline": true, "deadline_text": "this friday afternoon", "confidence": 0.98, "reason": "This Friday afternoon - 2:00 PM", "suggested_response": "Noted! I'll remind you this Friday afternoon (2:00 PM)."}}

Input: "ETC: wednesday morning"
Output: {{"has_deadline": true, "deadline_text": "wednesday morning", "confidence": 0.99, "reason": "Wednesday morning - 9:00 AM", "suggested_response": "Got it! I'll remind you Wednesday morning (9:00 AM)."}}

Input: "ETC: next week monday"
Output: {{"has_deadline": true, "deadline_text": "next week monday", "confidence": 0.99, "reason": "Next week Monday - 9:00 AM", "suggested_response": "Perfect! I'll remind you next Monday (9:00 AM)."}}

=== DATE EXAMPLES ===
Input: "ETC: Dec 25 10am"
Output: {{"has_deadline": true, "deadline_text": "Dec 25 10am", "confidence": 0.99, "reason": "Specific date with time", "suggested_response": "Perfect! I'll remind you December 25th at 10:00 AM."}}

Input: "ETC: jan 15"
Output: {{"has_deadline": true, "deadline_text": "jan 15", "confidence": 0.99, "reason": "Specific date", "suggested_response": "Noted! I'll remind you January 15th."}}

Input: "ETC: 20th jan 5pm"
Output: {{"has_deadline": true, "deadline_text": "20th jan 5pm", "confidence": 0.99, "reason": "Date with time", "suggested_response": "Got it! I'll remind you January 20th at 5:00 PM."}}

=== BY/TILL/UNTIL EXAMPLES ===
Input: "ETC: by 5pm"
Output: {{"has_deadline": true, "deadline_text": "5pm", "confidence": 0.99, "reason": "By specific time today", "suggested_response": "Got it! I'll remind you by 5:00 PM."}}

Input: "ETC: till friday"
Output: {{"has_deadline": true, "deadline_text": "friday", "confidence": 0.99, "reason": "Till Friday", "suggested_response": "Noted! I'll remind you on Friday."}}

Input: "ETC: until tomorrow"
Output: {{"has_deadline": true, "deadline_text": "tomorrow", "confidence": 0.99, "reason": "Until tomorrow", "suggested_response": "Got it! I'll remind you tomorrow."}}

=== NOT ETC EXAMPLES ===
Input: "can we meet today?"
Output: {{"has_deadline": false, "deadline_text": "", "confidence": 0.95, "reason": "Question without ETC format", "suggested_response": ""}}

Input: "I'll finish this by tomorrow"
Output: {{"has_deadline": false, "deadline_text": "", "confidence": 0.95, "reason": "Statement without ETC format", "suggested_response": ""}}

Input: "Let's discuss EOD plans"
Output: {{"has_deadline": false, "deadline_text": "", "confidence": 0.95, "reason": "Discussion without ETC format", "suggested_response": ""}}

CRITICAL INSTRUCTIONS:
- Be AGGRESSIVE in detection - if ETC is mentioned, extract EVERYTHING
- Include ALL parts: if both day AND time mentioned, extract BOTH
- For RELATIVE TIMES: ALWAYS preserve the time unit! "1 min" → "1 min", "3 mins" → "3 mins", "5 hours" → "5 hours"
- DO NOT convert "1 min" to just "1" or "3 mins" to just "3" - this will cause errors!
- Normalize but preserve meaning: "2min" → "2 min", "tomorrow 3pm" → "tomorrow 3pm"
- Confidence should be HIGH (0.95+) for clear ETC requests
- Only return has_deadline=false if absolutely certain it's NOT an ETC request
- Return ONLY valid JSON, no markdown, no code blocks, no explanations outside JSON"""

            # Call Gemini API with error handling
            try:
                response = self.gemini_client.generate_content(
                    prompt,
                    generation_config={
                        'temperature': self.gemini_temperature,
                        'max_output_tokens': 2048,
                    }
                )

                if not response or not response.text:
                    print("Gemini API returned empty response")
                    return None

                content = response.text.strip()
            except Exception as api_error:
                print(f"Error calling Gemini API: {api_error}")
                return None

            # Try to parse JSON from response
            try:
                # Remove any markdown formatting
                if '```json' in content:
                    content = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    content = content.split('```')[1].split('```')[0].strip()

                # Try to extract JSON if there's extra text
                json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
                if json_match:
                    content = json_match.group(0)

                parsed_result = json.loads(content)
                print(f"Gemini API response: {parsed_result}")
                return parsed_result

            except json.JSONDecodeError as e:
                print(f"Failed to parse Gemini JSON response: {e}")
                print(f"Raw content: {content}")
                # Try to extract just the JSON part
                try:
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        parsed_result = json.loads(json_match.group(0))
                        print(f"Extracted JSON: {parsed_result}")
                        return parsed_result
                except:
                    pass
                return None

        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _detect_deadline_text(self, message: str) -> Optional[str]:
        """
        Detect deadline text using regex patterns.
        Returns the first matched deadline text or None.
        """
        print(f"Analyzing message: '{message}'")

        for i, pattern in enumerate(self.deadline_patterns):
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                # Always try to return the full match first
                full_match = match.group(0).strip()
                print(f"Pattern {i+1} matched: '{pattern}' -> '{full_match}'")

                # For patterns that match the full message, return the full message
                if full_match == message.strip():
                    print(f"Full message match: '{message}'")
                    return message.strip()

                # For patterns with multiple groups, try to get meaningful text
                # Always return the full match to preserve context
                return full_match

        print("No pattern matched")
        return None

    def _is_contextual_request(self, message: str) -> bool:
        """Check if message is a contextual request like 'again', 'same', etc."""
        message_lower = message.lower().strip()

        contextual_keywords = [
            'again', 'repeat', 'same', 're-schedule', 'reschedule',
            'do it again', 'once more', 'one more time', 'another',
            'schedule another', 'set another', 'create another',
            'every', 'each', 'recurring', 'recur'
        ]

        for keyword in contextual_keywords:
            if keyword in message_lower:
                return True
        return False

    def _get_user_last_etc(self, user_id: str) -> Optional[Dict]:
        """Get user's last ETC for contextual understanding"""
        if user_id not in self.user_history or not self.user_history[user_id]:
            return None

        # Get the most recent ETC
        return self.user_history[user_id][-1]

    def _save_user_etc(self, user_id: str, etc_data: Dict):
        """Save user's ETC to history for contextual understanding"""
        if user_id not in self.user_history:
            self.user_history[user_id] = []

        # Keep only last 5 ETCs per user
        self.user_history[user_id].append(etc_data)
        if len(self.user_history[user_id]) > 5:
            self.user_history[user_id] = self.user_history[user_id][-5:]

    def _parse_datetime(self, date_text: str) -> Optional[datetime]:
        """
        Parse datetime from text, supporting both absolute and relative formats.
        """
        print(f"Parsing datetime from: '{date_text}'")

        now = datetime.now(self.timezone)

        # Handle common time expressions first
        date_text_lower = date_text.lower().strip()

        # ============================================================
        # PRIORITY 1: RELATIVE TIME EXPRESSIONS (minutes, hours, days)
        # Must be checked FIRST before any other parsing
        # ============================================================

        # Comprehensive relative time patterns - check these FIRST
        relative_patterns = [
            # Pattern: "X min", "X mins", "X minute", "X minutes", "Xm" (with or without space)
            (r'^(\d+)\s*(?:m|min|mins|minute|minutes)$', 'minutes'),
            (r'^in\s+(\d+)\s*(?:m|min|mins|minute|minutes)$', 'minutes'),
            (r'^(\d+)\s*(?:m|min|mins|minute|minutes)\s+(?:from\s+now|later)?$', 'minutes'),

            # Pattern: "X hr", "X hrs", "X hour", "X hours", "Xh"
            (r'^(\d+)\s*(?:h|hr|hrs|hour|hours)$', 'hours'),
            (r'^in\s+(\d+)\s*(?:h|hr|hrs|hour|hours)$', 'hours'),
            (r'^(\d+)\s*(?:h|hr|hrs|hour|hours)\s+(?:from\s+now|later)?$', 'hours'),

            # Pattern: "X day", "X days", "Xd"
            (r'^(\d+)\s*(?:d|day|days)$', 'days'),
            (r'^in\s+(\d+)\s*(?:d|day|days)$', 'days'),
            (r'^(\d+)\s*(?:d|day|days)\s+(?:from\s+now|later)?$', 'days'),

            # Pattern: "X week", "X weeks", "Xw"
            (r'^(\d+)\s*(?:w|week|weeks)$', 'weeks'),
            (r'^in\s+(\d+)\s*(?:w|week|weeks)$', 'weeks'),

            # Pattern: "X sec", "X secs", "X second", "X seconds", "Xs"
            (r'^(\d+)\s*(?:s|sec|secs|second|seconds)$', 'seconds'),
            (r'^in\s+(\d+)\s*(?:s|sec|secs|second|seconds)$', 'seconds'),

            # Pattern: "half hour", "quarter hour"
            (r'^half\s+(?:an?\s+)?hour$', 'half_hour'),
            (r'^quarter\s+(?:an?\s+)?hour$', 'quarter_hour'),
        ]

        for pattern, unit in relative_patterns:
            match = re.search(pattern, date_text_lower)
            if match:
                if unit == 'half_hour':
                    future_time = now + timedelta(minutes=30)
                    print(f"✅ Relative time (half hour) parsed: {future_time}")
                    return future_time
                elif unit == 'quarter_hour':
                    future_time = now + timedelta(minutes=15)
                    print(f"✅ Relative time (quarter hour) parsed: {future_time}")
                    return future_time
                else:
                    amount = int(match.group(1))
                    if unit == 'seconds':
                        future_time = now + timedelta(seconds=amount)
                    elif unit == 'minutes':
                        future_time = now + timedelta(minutes=amount)
                    elif unit == 'hours':
                        future_time = now + timedelta(hours=amount)
                    elif unit == 'days':
                        future_time = now + timedelta(days=amount)
                    elif unit == 'weeks':
                        future_time = now + timedelta(weeks=amount)
                    else:
                        continue

                    print(f"✅ Relative time ({amount} {unit}) parsed: {future_time}")
                    return future_time

        # Also check for flexible relative patterns (not at start of string)
        # Priority: check for time units in order (min before m, hour before h, etc.)
        flexible_patterns = [
            (r'(\d+)\s*(minutes?|mins?)', 'minutes'),
            (r'(\d+)\s*(hours?|hrs?)', 'hours'),
            (r'(\d+)\s*(days?)', 'days'),
            (r'(\d+)\s*(weeks?)', 'weeks'),
            (r'(\d+)\s*(seconds?|secs?)', 'seconds'),
            (r'(\d+)\s*m\b', 'minutes'),  # "5m" at word boundary
            (r'(\d+)\s*h\b', 'hours'),    # "2h" at word boundary
            (r'(\d+)\s*d\b', 'days'),     # "3d" at word boundary
            (r'(\d+)\s*w\b', 'weeks'),    # "1w" at word boundary
            (r'(\d+)\s*s\b', 'seconds'),  # "30s" at word boundary
        ]

        for pattern, unit in flexible_patterns:
            match = re.search(pattern, date_text_lower)
            if match:
                amount = int(match.group(1))

                if unit == 'seconds':
                    future_time = now + timedelta(seconds=amount)
                elif unit == 'minutes':
                    future_time = now + timedelta(minutes=amount)
                elif unit == 'hours':
                    future_time = now + timedelta(hours=amount)
                elif unit == 'days':
                    future_time = now + timedelta(days=amount)
                elif unit == 'weeks':
                    future_time = now + timedelta(weeks=amount)
                else:
                    continue

                print(f"✅ Flexible relative time ({amount} {unit}) parsed: {future_time}")
                return future_time

        # ============================================================
        # PRIORITY 2: EOD and other expressions
        # ============================================================

        # EOD and work-related expressions - 7 PM (office hours)
        eod_expressions = [
            'eod', 'end of day', 'end of work', 'close of business', 'cob',
            'by eod', 'till eod', 'until eod', 'before eod',
            'end of business', 'eob', 'close of day', 'cod'
        ]

        # Check if message contains EOD expression
        has_eod = any(expr in date_text_lower for expr in eod_expressions)

        if has_eod:
            # Check if there's a day mentioned with EOD (e.g., "tomorrow EOD", "friday EOD")
            day_with_eod = None

            # Check for "tomorrow EOD" or "by tomorrow EOD"
            if 'tomorrow' in date_text_lower:
                day_with_eod = now + timedelta(days=1)
            # Check for "today EOD"
            elif 'today' in date_text_lower:
                day_with_eod = now
            # Check for day of week with EOD (e.g., "friday EOD", "monday EOD")
            else:
                day_mappings = {
                    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                    'friday': 4, 'saturday': 5, 'sunday': 6
                }
                for day_name, day_num in day_mappings.items():
                    if day_name in date_text_lower:
                        current_weekday = now.weekday()
                        days_ahead = (day_num - current_weekday) % 7
                        if days_ahead == 0:  # Same day
                            # If it's already past 7PM, go to next week
                            if now.hour >= 19:
                                days_ahead = 7
                        day_with_eod = now + timedelta(days=days_ahead)
                        break

            if day_with_eod:
                target_date = day_with_eod.replace(hour=19, minute=0, second=0, microsecond=0)
            else:
                # Just "EOD" means today at 7PM
                target_date = now.replace(hour=19, minute=0, second=0, microsecond=0)

            if target_date <= now:
                target_date += timedelta(days=1)

            print(f"EOD parsed: {target_date}")
            return target_date

        # Handle days of the week
        day_mappings = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }

        # Handle time + day expressions first (highest priority)
        time_day_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s+(tomorrow|today|tonight)', date_text_lower)
        if time_day_match:
            hour = int(time_day_match.group(1))
            minute = int(time_day_match.group(2)) if time_day_match.group(2) else 0
            period = time_day_match.group(3)
            day_expr = time_day_match.group(4)

            # Convert to 24-hour format
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            if day_expr == 'tomorrow':
                target_date = now + timedelta(days=1)
            elif day_expr == 'today':
                target_date = now
            elif day_expr == 'tonight':
                target_date = now

            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_date <= now and day_expr in ['today', 'tonight']:
                target_date += timedelta(days=1)
            print(f"Time + day parsed: {target_date}")
            return target_date

        # Handle time + day expressions without AM/PM
        time_day_24_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s+(tomorrow|today|tonight)', date_text_lower)
        if time_day_24_match:
            hour = int(time_day_24_match.group(1))
            minute = int(time_day_24_match.group(2)) if time_day_24_match.group(2) else 0
            day_expr = time_day_24_match.group(3)

            # Apply smart AM/PM inference
            if hour == 12:
                hour = 12  # 12 PM
            elif hour == 0:
                hour = 0
            elif 1 <= hour <= 11:
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                pass  # Keep as is
            else:
                hour = 9

            if day_expr == 'tomorrow':
                target_date = now + timedelta(days=1)
            elif day_expr == 'today':
                target_date = now
            elif day_expr == 'tonight':
                target_date = now

            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_date <= now and day_expr in ['today', 'tonight']:
                target_date += timedelta(days=1)
            print(f"Time + day 24h parsed: {target_date}")
            return target_date

        # Handle standalone times first (highest priority)
        standalone_time_match = re.search(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$', date_text_lower)
        if standalone_time_match:
            hour = int(standalone_time_match.group(1))
            minute = int(standalone_time_match.group(2)) if standalone_time_match.group(2) else 0
            period = standalone_time_match.group(3)

            # Convert to 24-hour format
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            print(f"Standalone time parsed: {target_time}")
            return target_time

        # Handle standalone times without AM/PM
        standalone_time_24_match = re.search(r'^(\d{1,2})(?::(\d{2}))?$', date_text_lower)
        if standalone_time_24_match:
            hour = int(standalone_time_24_match.group(1))
            minute = int(standalone_time_24_match.group(2)) if standalone_time_24_match.group(2) else 0

            # Apply smart AM/PM inference
            if hour == 12:
                hour = 12  # 12 PM
            elif hour == 0:
                hour = 0
            elif 1 <= hour <= 11:
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                pass  # Keep as is
            else:
                hour = 9

            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            print(f"Standalone time 24h parsed: {target_time}")
            return target_time

        # Handle days with times (e.g., "friday 2pm", "monday 9am")
        day_time_match = re.search(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
        if day_time_match:
            day_name = day_time_match.group(1)
            hour = int(day_time_match.group(2))
            minute = int(day_time_match.group(3)) if day_time_match.group(3) else 0
            period = day_time_match.group(4)

            # Convert to 24-hour format
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            # Calculate target date
            day_mappings = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6
            }
            target_day = day_mappings[day_name]
            current_day = now.weekday()
            days_ahead = target_day - current_day
            if days_ahead <= 0:  # Target day already passed this week
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)
            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            print(f"Day with time parsed: {target_date}")
            return target_date

        # Handle days with times without AM/PM (e.g., "friday 2", "monday 9")
        day_time_24_match = re.search(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(\d{1,2})(?::(\d{2}))?', date_text_lower)
        if day_time_24_match:
            day_name = day_time_24_match.group(1)
            hour = int(day_time_24_match.group(2))
            minute = int(day_time_24_match.group(3)) if day_time_24_match.group(3) else 0

            # Apply smart AM/PM inference
            if hour == 12:
                hour = 12  # 12 PM
            elif hour == 0:
                hour = 0
            elif 1 <= hour <= 11:
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                pass  # Keep as is
            else:
                hour = 9

            # Calculate target date
            day_mappings = {
                'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                'friday': 4, 'saturday': 5, 'sunday': 6
            }
            target_day = day_mappings[day_name]
            current_day = now.weekday()
            days_ahead = target_day - current_day
            if days_ahead <= 0:  # Target day already passed this week
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)
            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            print(f"Day with time 24h parsed: {target_date}")
            return target_date

        # Handle "till" expressions with specific dates first (most specific)
        till_date_match = re.search(r'till\s+(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
        if till_date_match:
            day = int(till_date_match.group(1))
            month_name = till_date_match.group(2)
            hour = int(till_date_match.group(3))
            minute = int(till_date_match.group(4)) if till_date_match.group(4) else 0
            period = till_date_match.group(5)

            month_mapping = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            month = month_mapping[month_name]

            # Convert to 24-hour format
            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            # Use current year, or next year if date has passed
            year = now.year
            target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
            # Only go to next year if the date has completely passed (not just the time)
            if target_date.date() < now.date():
                target_date = target_date.replace(year=year + 1)

            print(f"Till specific date parsed: {target_date}")
            return target_date

        # Handle "till" expressions with specific dates without AM/PM
        till_date_match_24 = re.search(r'till\s+(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?::(\d{2}))?', date_text_lower)
        if till_date_match_24:
            day = int(till_date_match_24.group(1))
            month_name = till_date_match_24.group(2)
            hour = int(till_date_match_24.group(3))
            minute = int(till_date_match_24.group(4)) if till_date_match_24.group(4) else 0

            month_mapping = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }
            month = month_mapping[month_name]

            # Apply smart AM/PM inference
            if hour == 12:
                hour = 12  # 12 PM
            elif hour == 0:
                hour = 0
            elif 1 <= hour <= 11:
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                pass  # Keep as is
            else:
                hour = 9

            # Use current year, or next year if date has passed
            year = now.year
            target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
            # Only go to next year if the date has completely passed (not just the time)
            if target_date.date() < now.date():
                target_date = target_date.replace(year=year + 1)

            print(f"Till specific date parsed: {target_date}")
            return target_date

        # Handle "till" expressions first (most specific)
        if 'till' in date_text_lower:
            # Handle "till tomorrow 5 am" or "till tomorrow 5"
            if 'tomorrow' in date_text_lower:
                target_date = now + timedelta(days=1)
                # Extract time from the text
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    # Check for time without AM/PM
                    time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                    if time_match_24:
                        hour = int(time_match_24.group(1))
                        minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        # Default to 9 AM for tomorrow
                        target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

                print(f"Till tomorrow parsed: {target_date}")
                return target_date

            # Handle "till friday" or "till saturday 2 pm"
            for day_name, day_num in day_mappings.items():
                if day_name in date_text_lower:
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7
                    if days_ahead == 0:  # If it's the same day, use today
                        days_ahead = 0
                    target_date = now + timedelta(days=days_ahead)

                    # Extract time from the text
                    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                    if time_match:
                        hour = int(time_match.group(1))
                        minute = int(time_match.group(2)) if time_match.group(2) else 0
                        period = time_match.group(3)

                        if period == 'pm' and hour != 12:
                            hour += 12
                        elif period == 'am' and hour == 12:
                            hour = 0

                        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        # Check for time without AM/PM
                        time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                        if time_match_24:
                            hour = int(time_match_24.group(1))
                            minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                            target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        else:
                            # Default to 9 AM for day
                            target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

                    print(f"Till {day_name} parsed: {target_date}")
                    return target_date

            # Handle "till 4th Oct 5 pm" or "till 4th Oct 5"
            date_match = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', date_text_lower)
            if date_match:
                day = int(date_match.group(1))
                month_name = date_match.group(2)
                month_mapping = {
                    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
                }
                month = month_mapping[month_name]

                # Use current year, or next year if date has passed
                year = now.year
                target_date = now.replace(month=month, day=day, hour=0, minute=0, second=0, microsecond=0)
                # Only go to next year if the date has completely passed (not just the time)
                if target_date.date() < now.date():
                    target_date = target_date.replace(year=year + 1)

                # Extract time from the text
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    # Check for time without AM/PM
                    time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                    if time_match_24:
                        hour = int(time_match_24.group(1))
                        minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        # Default to 7 PM for specific dates (office hours)
                        target_date = target_date.replace(hour=19, minute=0, second=0, microsecond=0)

                print(f"Till {day} {month_name} parsed: {target_date}")
                return target_date

        # Handle week expressions - comprehensive patterns
        week_expressions = {
            'this week': 0,
            'coming week': 0,
            'next week': 7,
            'week after next': 14,
            'next to next week': 14,
            'next-to-next week': 14,
            'after next week': 14,
        }

        week_found = False
        week_offset = 0

        for week_expr, offset in week_expressions.items():
            if week_expr in date_text_lower:
                week_offset = offset
                week_found = True
                print(f"Found week expression: {week_expr} (offset: {offset} days)")
                break

        if week_found:
            # Find day of week in the text
            for day_name, day_num in day_mappings.items():
                if day_name in date_text_lower:
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7

                    # If same day and we're in "this week", use today if time hasn't passed
                    if days_ahead == 0 and week_offset == 0:
                        # Check if there's a time specified
                        time_in_text = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                        if time_in_text or 'morning' in date_text_lower or 'evening' in date_text_lower or 'afternoon' in date_text_lower:
                            days_ahead = 0  # Use today
                        else:
                            days_ahead = 7  # If no time, assume next week
                    elif days_ahead == 0:
                        days_ahead = 7  # If same day but "next week", go to next week

                    target_date = now + timedelta(days=days_ahead + week_offset)
                    print(f"Week expression parsed: {day_name} in {week_offset} days = {target_date}")
                    break
        else:
            # Check for day of week patterns
            for day_name, day_num in day_mappings.items():
                if day_name in date_text_lower:
                    # Check for various modifiers
                    is_next = 'next' in date_text_lower
                    is_this = 'this' in date_text_lower
                    is_before = 'before' in date_text_lower
                    is_after = 'after' in date_text_lower
                    is_particular = 'particular' in date_text_lower
                    is_on_that_day = 'on that day' in date_text_lower
                    is_after_that = 'after that' in date_text_lower

                    # Calculate target day
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7

                    if is_next:
                        days_ahead = (day_num - current_weekday) % 7
                        if days_ahead == 0:  # If it's the same day, go to next week
                            days_ahead = 7
                    elif is_this:
                        days_ahead = (day_num - current_weekday) % 7
                        if days_ahead == 0:  # If it's the same day, use today
                            days_ahead = 0
                    elif is_before:
                        # If it's before a day, go to previous week
                        days_ahead = (day_num - current_weekday) % 7 - 7
                        if days_ahead >= 0:
                            days_ahead -= 7
                    elif is_after or is_particular or is_on_that_day or is_after_that:
                        # Default behavior for these
                        if days_ahead == 0 and now.hour >= 18:  # If it's evening, assume next week
                            days_ahead = 7
                        elif days_ahead == 0:  # If it's the same day but not evening, use today
                            days_ahead = 0
                    else:
                        # Default behavior: if it's the same day or past, go to next week
                        if days_ahead == 0 and now.hour >= 18:  # If it's evening, assume next week
                            days_ahead = 7
                        elif days_ahead == 0:  # If it's the same day but not evening, use today
                            days_ahead = 0

                    target_date = now + timedelta(days=days_ahead)
                    break

        # If we found a target_date, now handle time parsing
        if 'target_date' in locals():
            # Check for specific time with day (AM/PM format)
            time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
            if time_match:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2)) if time_match.group(2) else 0
                period = time_match.group(3)

                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0

                target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            else:
                # Check for time without AM/PM (e.g., "Friday at 12:00" or "Saturday at 2:00")
                time_match_24 = re.search(r'at\s+(\d{1,2})(?::(\d{2}))?', date_text_lower)
                if time_match_24:
                    hour = int(time_match_24.group(1))
                    minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0

                    # Smart AM/PM inference
                    if hour == 12:
                        # 12:00 is ambiguous, default to PM for most cases
                        hour = 12  # 12 PM
                    elif hour == 0:
                        # 0:00 should be 12 AM
                        hour = 0
                    elif 1 <= hour <= 11:
                        # 1-11 could be AM or PM, use smart inference
                        current_hour = now.hour
                        if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                            hour = hour  # Keep as AM
                        else:  # 2, 6-11 are more likely to be PM
                            # For common afternoon times like 2:00, 3:00, etc., default to PM
                            hour = hour + 12  # Convert to PM
                    elif 13 <= hour <= 23:
                        # 13-23 are clearly 24-hour format
                        pass  # Keep as is
                    else:
                        # Invalid hour, default to 9 AM
                        hour = 9

                    # Convert to 24-hour format if needed
                    if hour > 23:
                        hour = hour % 24
                    if minute > 59:
                        minute = 59

                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    # Check for time of day expressions with day
                    if 'morning' in date_text_lower:
                        target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
                    elif 'night' in date_text_lower:
                        target_date = target_date.replace(hour=21, minute=0, second=0, microsecond=0)
                    else:
                        # Default to 9 AM for day of week
                        target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

            print(f"Day of week parsed: {target_date}")
            return target_date

        # Handle professional expressions with flexible patterns
        # Check for any day of week in the text (for professional expressions)
        day_mappings = {
            'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
            'friday': 4, 'saturday': 5, 'sunday': 6
        }

        for day_name, day_num in day_mappings.items():
            if day_name in date_text_lower:
                # Check for time with day (AM/PM format)
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    # Calculate target day
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7
                    if days_ahead == 0:  # If it's the same day, use today
                        days_ahead = 0
                    target_date = now + timedelta(days=days_ahead)
                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                    print(f"Professional expression parsed: {target_date}")
                    return target_date

                # Check for time without AM/PM
                time_match_24 = re.search(r'at\s+(\d{1,2})(?::(\d{2}))?', date_text_lower)
                if time_match_24:
                    hour = int(time_match_24.group(1))
                    minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0

                    # Apply smart AM/PM inference
                    if hour == 12:
                        hour = 12  # 12 PM
                    elif hour == 0:
                        hour = 0
                    elif 1 <= hour <= 11:
                        if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                            hour = hour  # Keep as AM
                        else:  # 2, 6-11 are more likely to be PM
                            hour = hour + 12  # Convert to PM
                    elif 13 <= hour <= 23:
                        pass  # Keep as is
                    else:
                        hour = 9

                    # Calculate target day
                    current_weekday = now.weekday()
                    days_ahead = (day_num - current_weekday) % 7
                    if days_ahead == 0:  # If it's the same day, use today
                        days_ahead = 0
                    target_date = now + timedelta(days=days_ahead)
                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                    print(f"Professional expression parsed: {target_date}")
                    return target_date

                # No specific time, use default
                current_weekday = now.weekday()
                days_ahead = (day_num - current_weekday) % 7
                if days_ahead == 0:  # If it's the same day, use today
                    days_ahead = 0
                target_date = now + timedelta(days=days_ahead)
                target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

                print(f"Professional expression parsed: {target_date}")
                return target_date

        # Handle common informal expressions
        if 'tonight' in date_text_lower:
            target_date = now.replace(hour=21, minute=0, second=0, microsecond=0)
            if target_date <= now:
                target_date += timedelta(days=1)
            print(f"Tonight parsed: {target_date}")
            return target_date

        if 'today' in date_text_lower:
            target_date = now

            # Check for time of day expressions (office hours: evening/EOD = 7PM)
            time_mappings = {
                'early morning': 7,
                'morning': 9,
                'late morning': 11,
                'noon': 12,
                'lunch': 12,
                'afternoon': 14,
                'late afternoon': 16,
                'evening': 19,        # 7 PM - office hours
                'late evening': 20,
                'dinner': 19,
                'night': 21,
                'late night': 23,
                'midnight': 0,
            }

            time_found = False
            for time_expr in sorted(time_mappings.keys(), key=len, reverse=True):
                if time_expr in date_text_lower:
                    target_date = target_date.replace(hour=time_mappings[time_expr], minute=0, second=0, microsecond=0)
                    time_found = True
                    if target_date <= now:
                        target_date += timedelta(days=1)
                    break

            if not time_found:
                # Extract time from the text if present
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    # Convert to 24-hour format
                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        target_date += timedelta(days=1)
                else:
                    # Check for time without AM/PM
                    time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                    if time_match_24:
                        hour = int(time_match_24.group(1))
                        minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                        # Smart AM/PM inference
                        if 1 <= hour <= 11:
                            hour = hour + 12  # Assume PM
                        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        if target_date <= now:
                            target_date += timedelta(days=1)
                    else:
                        # Default to 7 PM today (office hours)
                        target_date = target_date.replace(hour=19, minute=0, second=0, microsecond=0)
                        if target_date <= now:
                            target_date += timedelta(days=1)

            print(f"Today parsed: {target_date}")
            return target_date

        if 'tomorrow' in date_text_lower:
            target_date = now + timedelta(days=1)

            # Comprehensive time of day mappings (office hours: evening/EOD = 7PM)
            time_mappings = {
                'early morning': 7,
                'morning': 9,
                'late morning': 11,
                'noon': 12,
                'lunch': 12,
                'afternoon': 14,
                'late afternoon': 16,
                'evening': 19,        # 7 PM - office hours
                'late evening': 20,
                'dinner': 19,
                'night': 21,
                'late night': 23,
                'midnight': 0,
            }

            time_found = False
            # Check for time expressions (longer first to match "late evening" before "evening")
            for time_expr in sorted(time_mappings.keys(), key=len, reverse=True):
                if time_expr in date_text_lower:
                    target_date = target_date.replace(hour=time_mappings[time_expr], minute=0, second=0, microsecond=0)
                    time_found = True
                    print(f"Found time expression: {time_expr}")
                    break

            if not time_found:
                # Extract time from the text if present
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3)

                    # Convert to 24-hour format
                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0

                    target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                else:
                    # Check for time without AM/PM
                    time_match_24 = re.search(r'(\d{1,2})(?::(\d{2}))?', date_text_lower)
                    if time_match_24:
                        hour = int(time_match_24.group(1))
                        minute = int(time_match_24.group(2)) if time_match_24.group(2) else 0
                        # Smart AM/PM inference
                        if 1 <= hour <= 11:
                            hour = hour + 12  # Assume PM for afternoon times
                        target_date = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    else:
                        # Default to 9 AM tomorrow
                        target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)

            print(f"Tomorrow parsed: {target_date}")
            return target_date

        if 'day after tomorrow' in date_text_lower:
            target_date = now + timedelta(days=2)
            # Default to 9 AM day after tomorrow
            target_date = target_date.replace(hour=9, minute=0, second=0, microsecond=0)
            print(f"Day after tomorrow parsed: {target_date}")
            return target_date

        # Handle specific time patterns (AM/PM)
        time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text_lower)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(3)

            if period == 'pm' and hour != 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0

            target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            print(f"Specific time parsed: {target_time}")
            return target_time

        # Time of day expressions
        time_mappings = {
            'morning': 9,
            'noon': 12,
            'evening': 18,
            'night': 21,
            'midnight': 0
        }

        if date_text_lower in time_mappings:
            hour = time_mappings[date_text_lower]
            target_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if target_time <= now:
                target_time += timedelta(days=1)
            print(f"Time expression parsed: {target_time}")
            return target_time

        # Handle relative time expressions - comprehensive patterns
        relative_patterns = [
            r'(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)',
            r'in\s+(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)',
            r'(\d+)\s+(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|months?)\s+(from\s+now|later)',
            r'(\d+)(min|mins|hour|hours|hr|hrs|day|days|week|weeks)',  # No space: "2min", "5hours"
        ]

        for pattern in relative_patterns:
            relative_match = re.search(pattern, date_text, re.IGNORECASE)
            if relative_match:
                amount = int(relative_match.group(1))
                unit = relative_match.group(2).lower() if len(relative_match.groups()) >= 2 else relative_match.group(2).lower()

                if 'second' in unit or 'sec' in unit:
                    future_time = now + timedelta(seconds=amount)
                elif 'minute' in unit or 'min' in unit:
                    future_time = now + timedelta(minutes=amount)
                elif 'hour' in unit or 'hr' in unit:
                    future_time = now + timedelta(hours=amount)
                elif 'day' in unit:
                    future_time = now + timedelta(days=amount)
                elif 'week' in unit:
                    future_time = now + timedelta(weeks=amount)
                elif 'month' in unit:
                    future_time = now + timedelta(days=amount * 30)
                else:
                    continue

                print(f"Relative time parsed: {future_time}")
                return future_time

        # Handle specific date patterns (e.g., "2nd Oct", "15th Dec", "Oct 2")
        # Pattern 1: "2nd Oct" format
        date_pattern = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', date_text, re.IGNORECASE)
        if date_pattern:
            day = int(date_pattern.group(1))
            month_name = date_pattern.group(2).lower()

            # Map month names to numbers
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }

            if month_name in month_map:
                month = month_map[month_name]
                year = now.year

                # Check for specific time with date
                time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text, re.IGNORECASE)
                if time_match:
                    hour = int(time_match.group(1))
                    minute = int(time_match.group(2)) if time_match.group(2) else 0
                    period = time_match.group(3).lower()

                    if period == 'pm' and hour != 12:
                        hour += 12
                    elif period == 'am' and hour == 12:
                        hour = 0
                else:
                    # Default to 6 PM for dates without specific time
                    hour = 18
                    minute = 0

                # If the date is in the past this year, assume next year
                try:
                    target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        target_date = target_date.replace(year=year + 1)
                    print(f"Specific date parsed: {target_date}")
                    return target_date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass

        # Pattern 2: "Oct 2" format (only if no time is specified)
        short_date_pattern = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})(?:\s|$)', date_text, re.IGNORECASE)
        if short_date_pattern and not re.search(r'at\s+\d{1,2}(?::\d{2})?', date_text):
            month_name = short_date_pattern.group(1).lower()
            day = int(short_date_pattern.group(2))

            # Map month names to numbers
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }

            if month_name in month_map:
                month = month_map[month_name]
                year = now.year

                # Default to 6 PM for dates without specific time
                hour = 18
                minute = 0

                # If the date is in the past this year, assume next year
                try:
                    target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        target_date = target_date.replace(year=year + 1)
                    print(f"Short date format parsed: {target_date}")
                    return target_date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass

        # Pattern 3: "Oct 2 at 10:48" format (without AM/PM)
        short_date_time_pattern = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})\s+at\s+(\d{1,2})(?::(\d{2}))?', date_text, re.IGNORECASE)
        if short_date_time_pattern:
            month_name = short_date_time_pattern.group(1).lower()
            day = int(short_date_time_pattern.group(2))
            hour = int(short_date_time_pattern.group(3))
            minute = int(short_date_time_pattern.group(4)) if short_date_time_pattern.group(4) else 0

            # Apply smart AM/PM inference
            if hour == 12:
                # 12:00 is ambiguous, default to PM for most cases
                hour = 12  # 12 PM
            elif hour == 0:
                # 0:00 should be 12 AM
                hour = 0
            elif 1 <= hour <= 11:
                # 1-11 could be AM or PM, use smart inference
                if hour in [1, 3, 4, 5]:  # 1, 3-5 AM are very early morning
                    hour = hour  # Keep as AM
                else:  # 2, 6-11 are more likely to be PM
                    hour = hour + 12  # Convert to PM
            elif 13 <= hour <= 23:
                # 13-23 are clearly 24-hour format
                pass  # Keep as is
            else:
                # Invalid hour, default to 9 AM
                hour = 9

            # Map month names to numbers
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }

            if month_name in month_map:
                month = month_map[month_name]
                year = now.year

                # If the date is in the past this year, assume next year
                # But if it's the same day and time has passed, assume tomorrow
                try:
                    target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        # If it's the same day but time has passed, schedule for tomorrow
                        if target_date.date() == now.date():
                            target_date = target_date + timedelta(days=1)
                        else:
                            # If it's a different day, schedule for next year
                            target_date = target_date.replace(year=year + 1)
                    print(f"Short date with time parsed: {target_date}")
                    return target_date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass

        # Pattern 4: Full date+time combinations (e.g., "2nd October 2025 10:47 AM")
        full_date_time_pattern = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{4})?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)', date_text, re.IGNORECASE)
        if full_date_time_pattern:
            day = int(full_date_time_pattern.group(1))
            month_name = full_date_time_pattern.group(2).lower()
            year = int(full_date_time_pattern.group(3)) if full_date_time_pattern.group(3) else now.year
            hour = int(full_date_time_pattern.group(4))
            minute = int(full_date_time_pattern.group(5)) if full_date_time_pattern.group(5) else 0
            period = full_date_time_pattern.group(6).lower()

            # Map month names to numbers
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
            }

            if month_name in month_map:
                month = month_map[month_name]

                # Convert to 24-hour format
                if period == 'pm' and hour != 12:
                    hour += 12
                elif period == 'am' and hour == 12:
                    hour = 0

                try:
                    target_date = now.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
                    if target_date <= now:
                        target_date = target_date.replace(year=year + 1)
                    print(f"Full date+time parsed: {target_date}")
                    return target_date
                except ValueError:
                    # Invalid date (e.g., Feb 30th)
                    pass

        # Pattern 5: Handle the case where the pattern matches but parsing fails
        # This is a fallback to use dateparser for complex patterns
        if any(keyword in date_text_lower for keyword in ['october', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'november', 'december']):
            # Use dateparser for full month names with time
            parsed_date = dateparser.parse(date_text, settings={
                'TIMEZONE': str(self.timezone),
                'RETURN_AS_TIMEZONE_AWARE': True,
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': now
            })

            if parsed_date:
                if parsed_date.tzinfo is None:
                    parsed_date = self.timezone.localize(parsed_date)

                now = datetime.now(self.timezone)
                if parsed_date > now:
                    print(f"Dateparser fallback parsed: {parsed_date}")
                    return parsed_date

        # Use dateparser for absolute dates and complex patterns
        parsed_date = dateparser.parse(date_text, settings={
            'TIMEZONE': str(self.timezone),
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': now
        })

        if parsed_date:
            if parsed_date.tzinfo is None:
                parsed_date = self.timezone.localize(parsed_date)

            now = datetime.now(self.timezone)
            if parsed_date > now:
                print(f"Absolute date parsed: {parsed_date}")
                return parsed_date

        print("Failed to parse datetime")
        return None

    def handle_message(self, message: str, user_id: str, channel_id: Optional[str] = None, message_ts: Optional[str] = None, thread_ts: Optional[str] = None) -> Optional[Reminder]:
        """
        Main function to process a message and detect deadlines with improved contextual understanding.
        Returns a Reminder object if deadline is found, None otherwise.
        """
        print(f"Processing message: '{message}' from user: {user_id}")

        # First check if message has ETC format
        if not self._is_etc_format(message):
            print("Message does not contain ETC format - skipping")
            return None

        print("ETC format detected - proceeding with deadline analysis")

        # Check if this is a contextual request (again, same, repeat, etc.)
        if self._is_contextual_request(message):
            print("Contextual request detected - checking user history")
            last_etc = self._get_user_last_etc(user_id)

            if last_etc:
                print(f"Found last ETC: {last_etc}")
                # Use the last ETC's time pattern
                deadline_text = last_etc.get('matched_text', '')
                if deadline_text:
                    print(f"Using contextual deadline: {deadline_text}")
                else:
                    print("No contextual deadline found, extracting from current message")
                    deadline_text = self._extract_etc_content(message)
            else:
                print("No user history found, extracting from current message")
                deadline_text = self._extract_etc_content(message)
        else:
            # Use Gemini API for intelligent deadline detection (if available)
            user_history = self._get_user_last_etc(user_id)
            gemini_result = None

            if self.gemini_client:
                gemini_result = self._call_gemini_api(message, user_history)

            # Multi-strategy approach: Try Gemini first, then fallback to regex
            deadline_text = None

            if gemini_result and gemini_result.get('has_deadline', False):
                confidence = gemini_result.get('confidence', 0.0)
                if confidence >= 0.6:  # Lower threshold for more aggressive detection
                    deadline_text = gemini_result.get('deadline_text', '')
                    suggested_response = gemini_result.get('suggested_response', '')
                    print(f"✅ Gemini detected deadline: '{deadline_text}' (confidence: {confidence})")

                    # Store suggested response for later use
                    if suggested_response:
                        self._last_suggested_response = suggested_response
                else:
                    print(f"⚠️  Gemini confidence too low: {confidence}, trying fallback")

            # Fallback to manual extraction if Gemini didn't work
            if not deadline_text:
                print("🔄 Using regex-based extraction as fallback")
                deadline_text = self._extract_etc_content(message)

                # If still no text, try more aggressive extraction
                if not deadline_text:
                    # Try to extract anything after ETC
                    aggressive_match = re.search(r'ETC[:\s\-=\(]*(.+)', message, re.IGNORECASE)
                    if aggressive_match:
                        deadline_text = aggressive_match.group(1).strip()
                        # Clean up
                        deadline_text = re.sub(r'[.,;!?]+$', '', deadline_text).strip()
                        print(f"🔄 Aggressive extraction found: '{deadline_text}'")

                if not deadline_text:
                    print("❌ No deadline text found in any extraction method")
                    return None

        if not deadline_text:
            print("❌ No ETC text detected")
            return None

        print(f"📅 Parsing deadline text: '{deadline_text}' (length: {len(deadline_text)})")

        # Multi-strategy datetime parsing
        due_at = None

        # Strategy 1: Try comprehensive regex parsing
        due_at = self._parse_datetime(deadline_text)

        # Strategy 2: If regex fails, try dateparser
        if not due_at:
            print("🔄 Regex parsing failed, trying dateparser...")
            try:
                parsed_date = dateparser.parse(deadline_text, settings={
                    'TIMEZONE': str(self.timezone),
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': datetime.now(self.timezone)
                })

                if parsed_date:
                    if parsed_date.tzinfo is None:
                        parsed_date = self.timezone.localize(parsed_date)

                    now = datetime.now(self.timezone)
                    if parsed_date > now:
                        due_at = parsed_date
                        print(f"✅ Dateparser parsed: {due_at}")
            except Exception as e:
                print(f"⚠️  Dateparser error: {e}")

        # Strategy 3: If still no date, try to extract just the time/relative part
        if not due_at:
            print("🔄 Trying to extract time/relative component...")
            # Try to find just time or relative expression
            time_match = re.search(r'(\d+)\s*(min|mins|minute|minutes|hour|hours|day|days)', deadline_text, re.IGNORECASE)
            if time_match:
                amount = int(time_match.group(1))
                unit = time_match.group(2).lower()
                now = datetime.now(self.timezone)

                if 'min' in unit:
                    due_at = now + timedelta(minutes=amount)
                elif 'hour' in unit:
                    due_at = now + timedelta(hours=amount)
                elif 'day' in unit:
                    due_at = now + timedelta(days=amount)

                if due_at:
                    print(f"✅ Relative time parsed: {due_at}")

        if not due_at:
            print(f"❌ Failed to parse datetime from: '{deadline_text}'")
            print("   Tried: regex patterns, dateparser, relative time extraction")
            return None

        print(f"✅ Successfully parsed deadline: {deadline_text} → {due_at}")

        # Create reminder
        reminder_id = str(uuid.uuid4())
        created_at = datetime.now(self.timezone)

        reminder = Reminder(
            id=reminder_id,
            user_id=user_id,
            channel_id=channel_id or 'unknown',
            message_ts=message_ts or 'unknown',
            thread_ts=thread_ts,
            original_text=message,
            matched_text=deadline_text,
            due_at=due_at,
            created_at=created_at
        )

        # Store reminder
        self.reminders[reminder_id] = reminder

        # Persist to database
        self._save_reminder_to_db(reminder)

        # Save to user history for contextual understanding
        self._save_user_etc(user_id, {
            'matched_text': deadline_text,
            'due_at': due_at.isoformat(),
            'original_text': message,
            'created_at': created_at.isoformat()
        })

        print(f"ETC reminder created: {deadline_text} -> {due_at}")
        return reminder

    def get_suggested_response(self) -> Optional[str]:
        """Get the last suggested response from Gemini API"""
        response = self._last_suggested_response
        self._last_suggested_response = None  # Clear after use
        return response

    def get_reminder(self, reminder_id: str) -> Optional[Reminder]:
        """Retrieve a specific reminder by ID"""
        return self.reminders.get(reminder_id)

    def get_all_reminders(self) -> Dict[str, Reminder]:
        """Get all stored reminders"""
        return self.reminders.copy()

    def remove_reminder(self, reminder_id: str) -> bool:
        """Remove a reminder from storage"""
        if reminder_id in self.reminders:
            # Mark as inactive in database
            self._deactivate_reminder_in_db(reminder_id)

            # Remove from memory
            del self.reminders[reminder_id]
            return True
        return False

    def _init_database(self):
        """Initialize SQLite database for persistent storage"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create reminders table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    message_ts TEXT NOT NULL,
                    thread_ts TEXT,
                    due_at TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
            ''')

            conn.commit()
            conn.close()
            print(f"Database initialized: {self.db_path}")

        except Exception as e:
            print(f"Error initializing database: {e}")

    def _save_reminder_to_db(self, reminder: Reminder):
        """Save reminder to database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO reminders
                (id, user_id, channel_id, message_ts, thread_ts, due_at, original_text, created_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                reminder.id,
                reminder.user_id,
                reminder.channel_id,
                reminder.message_ts,
                reminder.thread_ts,
                reminder.due_at.isoformat(),
                reminder.original_text,
                reminder.created_at.isoformat(),
                1
            ))

            conn.commit()
            conn.close()
            print(f"ETC reminder saved to database: {reminder.id}")

        except Exception as e:
            print(f"Error saving reminder to database: {e}")

    def _load_reminders_from_db(self):
        """Load existing reminders from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Load active reminders
            cursor.execute('''
                SELECT id, user_id, channel_id, message_ts, thread_ts, due_at, original_text, created_at
                FROM reminders
                WHERE is_active = 1 AND due_at > datetime('now')
                ORDER BY due_at ASC
            ''')

            rows = cursor.fetchall()
            loaded_count = 0

            for row in rows:
                reminder_id, user_id, channel_id, message_ts, thread_ts, due_at_str, original_text, created_at_str = row

                # Parse datetime strings
                due_at = datetime.fromisoformat(due_at_str)
                created_at = datetime.fromisoformat(created_at_str)

                # Create reminder object
                reminder = Reminder(
                    id=reminder_id,
                    user_id=user_id,
                    channel_id=channel_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    due_at=due_at,
                    original_text=original_text,
                    created_at=created_at
                )

                self.reminders[reminder_id] = reminder
                loaded_count += 1

            conn.close()
            print(f"Loaded {loaded_count} active ETC reminders from database")

        except Exception as e:
            print(f"Error loading reminders from database: {e}")

    def _deactivate_reminder_in_db(self, reminder_id: str):
        """Mark reminder as inactive in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                UPDATE reminders
                SET is_active = 0
                WHERE id = ?
            ''', (reminder_id,))

            conn.commit()
            conn.close()
            print(f"ETC reminder deactivated in database: {reminder_id}")

        except Exception as e:
            print(f"Error deactivating reminder in database: {e}")

    def get_active_reminders(self) -> List[Reminder]:
        """Get all active reminders"""
        now = datetime.now(self.timezone)
        active_reminders = []

        for reminder in self.reminders.values():
            if reminder.due_at and reminder.due_at > now:
                active_reminders.append(reminder)

        return sorted(active_reminders, key=lambda r: r.due_at)

    def cancel_reminder(self, reminder_id: str) -> bool:
        """Cancel a specific reminder"""
        if reminder_id in self.reminders:
            # Mark as inactive in database
            self._deactivate_reminder_in_db(reminder_id)

            # Remove from memory
            del self.reminders[reminder_id]
            print(f"ETC reminder cancelled: {reminder_id}")
            return True

        return False

    def cancel_reminders_for_message(self, message_ts: str, channel_id: str) -> int:
        """Cancel all reminders for a specific message"""
        cancelled_count = 0

        # Find reminders for this message
        reminders_to_cancel = []
        for reminder_id, reminder in self.reminders.items():
            if reminder.message_ts == message_ts and reminder.channel_id == channel_id:
                reminders_to_cancel.append(reminder_id)

        # Cancel each reminder
        for reminder_id in reminders_to_cancel:
            if self.cancel_reminder(reminder_id):
                cancelled_count += 1

        print(f"Cancelled {cancelled_count} ETC reminders for message {message_ts}")
        return cancelled_count
