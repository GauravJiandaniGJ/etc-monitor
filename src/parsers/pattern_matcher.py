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
        """Check if text contains ETC indicator.
        
        Args:
            text: Text to check
            
        Returns:
            True if text contains ETC indicator
        """
        message_upper = text.upper().strip()
        
        # Check for ETC keywords
        etc_keywords = ['ETC:', 'ETC ', 'ETC-', 'ETC=', 'ETC(']
        has_etc_keyword = any(keyword in message_upper for keyword in etc_keywords)
        
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
            etc_match = re.search(r'ETC[:\s\-=\(]*(.+)', text, re.IGNORECASE)
            if etc_match:
                etc_content = etc_match.group(1).strip()
                # Check if content has time/date indicators
                for indicator in time_indicators:
                    if re.search(indicator, etc_content, re.IGNORECASE):
                        return True
        
        return has_etc_keyword
    
    def extract_deadline_text(self, text: str) -> Optional[str]:
        """Extract deadline text from message.
        
        Args:
            text: Full message text
            
        Returns:
            Extracted deadline text or None
        """
        # First try to extract from ETC format
        etc_match = re.search(r'ETC[:\s\-=\(]*(.+?)(?:\)|$)', text, re.IGNORECASE)
        if etc_match:
            return etc_match.group(1).strip()
        
        # Otherwise return the full text
        return text.strip()
    
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
