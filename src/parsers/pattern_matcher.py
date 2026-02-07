"""Pattern matcher for ETC deadline detection.

Contains regex patterns for matching deadline expressions in text.
"""
import re
from typing import Optional, List, Tuple
from src.utils.logger import get_logger


logger = get_logger('PatternMatcher')


class PatternMatcher:
    """Matches deadline patterns in text using regex.

    Patterns are ordered from most specific to most general to ensure
    accurate matching.
    """

    def __init__(self):
        """Initialize pattern matcher with comprehensive regex patterns."""
        # Patterns ordered: specific first, general last
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

        logger.info(f'Pattern matcher initialized with {len(self.deadline_patterns)} patterns')

    def has_etc_indicator(self, text: str) -> bool:
        """Check if text contains ETC (Estimated Time of Completion) indicator.

        ONLY returns True if BOTH conditions are met:
        1. Message contains "ETC" or "etc" in deadline context (not "et cetera")
        2. Message contains actual time/date information (today, tomorrow, EOD, 5pm, etc.)

        Excludes "etc" when used as "et cetera" abbreviation.

        Args:
            text: Text to check

        Returns:
            True if text contains BOTH ETC keyword AND time/date information
        """
        message_upper = text.upper().strip()

        # EXCLUSION: Check if "etc" is being used as "et cetera" (abbreviation)
        # Common patterns: "add etc", "like etc", "etc.", ", etc", "etc here"
        et_cetera_patterns = [
            r'\bADD\s+ETC\b',           # "add etc"
            r'\bLIKE\s+ETC\b',          # "like etc"
            r'\bETC\.',                 # "etc."
            r',\s*ETC\b',               # ", etc"
            r'\bETC\s+HERE\b',          # "etc here"
            r'\bAND\s+ETC\b',           # "and etc"
            r'\bOR\s+ETC\b',            # "or etc"
            r'\bETCETERA\b',            # "etcetera"
        ]

        # If message matches et cetera pattern, it's NOT a deadline
        if any(re.search(pattern, message_upper) for pattern in et_cetera_patterns):
            logger.debug(f'Rejected: "etc" used as et cetera in: {text[:50]}...')
            return False

        # Check for direct ETC keywords
        etc_keywords = ['ETC:', 'ETC ', 'ETC-', 'ETC=', 'ETC(', 'ETC\n', 'ETC\t']
        has_etc_keyword = any(keyword in message_upper for keyword in etc_keywords)

        # Check for natural language ETC patterns (deadline-specific)
        natural_etc_patterns = [
            r'\bETC\s+(FOR|IS|OF|AT|TILL|BY|UNTIL)\b',  # "etc for/is/of/at/till/by/until"
            r'\bMY\s+ETC\b',   # "my etc"
            r'\bTHE\s+ETC\b',  # "the etc"
        ]

        has_natural_etc = any(re.search(pattern, message_upper) for pattern in natural_etc_patterns)

        # If no ETC keyword found, return False immediately
        if not (has_etc_keyword or has_natural_etc):
            return False

        # CRITICAL: Now check if message has actual time/date information
        # ONLY proceed if we find deadline indicators
        time_indicators = [
            # Relative time
            r'\d+\s*(min|mins|minute|minutes|hour|hours|hr|hrs)',
            r'\d+\s*(day|days|week|weeks|month|months)',
            r'(within|in)\s+\d+\s*(min|mins|minute|minutes|hour|hours|day|days|week|weeks)',

            # Absolute dates
            r'\b(today|tomorrow|tonight|yesterday)\b',
            r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',

            # Times
            r'\d{1,2}(:\d{2})?\s*(am|pm|AM|PM)',
            r'\bat\s+\d{1,2}(:\d{2})?\b',

            # EOD and time of day
            r'\b(EOD|eod|end of day|morning|evening|night|noon|midnight)\b',

            # Dates
            r'\d{1,2}(st|nd|rd|th)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)',
            r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2}',
        ]

        # Check if message has ANY time/date indicator
        has_time_info = any(re.search(indicator, text, re.IGNORECASE) for indicator in time_indicators)

        if has_time_info:
            logger.debug(f'Valid ETC found with time/date in: {text[:50]}...')
            return True
        else:
            logger.debug(f'Rejected: ETC found but NO time/date info in: {text[:50]}...')
            return False

    def extract_deadline_text(self, text: str) -> Optional[str]:
        """Extract deadline text from message.

        Handles both direct ETC patterns and natural language ETC sentences.
        Normalizes typos like "with in" to "within".

        Args:
            text: Full message text

        Returns:
            Extracted deadline text or None
        """
        # Normalize common typos: "with in" -> "within", "withing" -> "within"
        normalized_text = re.sub(r'\bwith\s+in\b', 'within', text, flags=re.IGNORECASE)
        normalized_text = re.sub(r'\bwithing\b', 'within', normalized_text, flags=re.IGNORECASE)

        # First try to extract from direct ETC format: "ETC: 2 hours", "ETC 5 mins"
        etc_match = re.search(r'ETC[:\s\-=\(]*(.+?)(?:\)|$)', normalized_text, re.IGNORECASE)
        if etc_match:
            extracted = etc_match.group(1).strip()
            # If extracted text is meaningful (not empty, has content), return it
            if extracted and len(extracted) > 0:
                return extracted

        # Try natural language patterns: "my etc for this project is of 2 hours"
        # Also handle "is with in", "is within", "is of", "is"
        natural_patterns = [
            r'ETC\s+FOR\s+(?:THIS|THE|A|AN)?\s*(?:PROJECT|TASK|WORK|ITEM)?\s+(?:IS\s+(?:WITH\s+IN|WITHIN|OF)|IS|OF)\s+(.+)',
            r'ETC\s+IS\s+(?:WITH\s+IN|WITHIN|OF\s+)?(.+)',
            r'ETC\s+OF\s+(.+)',
            r'MY\s+ETC\s+(?:FOR\s+(?:THIS|THE|A|AN)?\s*(?:PROJECT|TASK|WORK|ITEM)?\s+)?(?:IS\s+(?:WITH\s+IN|WITHIN|OF)|IS|OF)\s+(.+)',
            r'THE\s+ETC\s+(?:FOR\s+(?:THIS|THE|A|AN)?\s*(?:PROJECT|TASK|WORK|ITEM)?\s+)?(?:IS\s+(?:WITH\s+IN|WITHIN|OF)|IS|OF)\s+(.+)',
        ]

        for pattern in natural_patterns:
            match = re.search(pattern, normalized_text, re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()
                if extracted and len(extracted) > 0:
                    return extracted

        # If no specific pattern matched, return the full text for AI to parse
        # AI is better at extracting from natural language and handling typos
        return normalized_text.strip()

    def get_matching_patterns(self, text: str) -> List[Tuple[str, str]]:
        """Get all patterns that match the text.

        Args:
            text: Text to match against

        Returns:
            List of tuples (pattern, matched_text)
        """
        matches = []
        text_lower = text.lower().strip()

        for pattern in self.deadline_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                matched_text = match.group(0)
                matches.append((pattern, matched_text))

        if matches:
            logger.debug(f'Found {len(matches)} matching patterns for text: {text[:50]}...')

        return matches

    def find_first_match(self, text: str) -> Optional[Tuple[str, str]]:
        """Find first matching pattern.

        Args:
            text: Text to match against

        Returns:
            Tuple of (pattern, matched_text) or None
        """
        text_lower = text.lower().strip()

        for pattern in self.deadline_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                matched_text = match.group(0)
                logger.debug(f'Matched pattern: {pattern[:50]}... -> {matched_text}')
                return (pattern, matched_text)

        return None
