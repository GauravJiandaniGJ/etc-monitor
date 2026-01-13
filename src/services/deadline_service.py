"""Deadline service for detecting and parsing deadline expressions.

Orchestrates pattern matching and parsing to extract deadlines from messages.
"""
from typing import Optional
from datetime import datetime
from src.core.models import ReminderContext, ParsedDeadline
from src.parsers.pattern_matcher import PatternMatcher
from src.parsers.datetime_parser import DateTimeParser
from src.parsers.ai_parser import AIParser
from src.utils.logger import get_logger
from src.utils.timezone import now_ist


logger = get_logger('DeadlineService')


class DeadlineService:
    """Service for detecting deadlines in messages.
    
    Orchestrates pattern matching, AI parsing, and datetime parsing
    to extract deadline information from natural language.
    """
    
    def __init__(
        self,
        pattern_matcher: PatternMatcher,
        datetime_parser: DateTimeParser,
        ai_parser: Optional[AIParser] = None
    ):
        """Initialize deadline service.
        
        Args:
            pattern_matcher: Pattern matcher instance
            datetime_parser: DateTime parser instance
            ai_parser: Optional AI parser instance
        """
        self.pattern_matcher = pattern_matcher
        self.datetime_parser = datetime_parser
        self.ai_parser = ai_parser
        
        logger.info('Deadline service initialized')
        if ai_parser and ai_parser.is_available():
            logger.info('AI parsing enabled')
        else:
            logger.info('AI parsing disabled - using regex only')
    
    def detect(
        self,
        message: str,
        context: ReminderContext
    ) -> Optional[ParsedDeadline]:
        """Detect deadline in message.
        
        Uses AI first if available, falls back to regex pattern matching.
        This follows the project requirement: AI first, regex fallback.
        
        Args:
            message: Message text to parse
            context: Message context (channel, thread, user info)
            
        Returns:
            ParsedDeadline object or None if no deadline detected
        """
        if not message:
            logger.debug('Empty message provided')
            return None
        
        logger.info(f'Detecting deadline in message from user {context.user_id}')
        
        # Check if message has ETC indicator
        if not self.pattern_matcher.has_etc_indicator(message):
            logger.debug('No ETC indicator found in message')
            return None
        
        # Extract deadline text from message
        deadline_text = self.pattern_matcher.extract_deadline_text(message)
        if not deadline_text:
            logger.warning('ETC indicator found but could not extract deadline text')
            return None
        
        logger.debug(f'Extracted deadline text: "{deadline_text}"')
        
        # Try AI parsing first (project requirement)
        if self.ai_parser and self.ai_parser.is_available():
            logger.debug('Attempting AI parsing')
            ai_result = self._try_ai_parsing(message, deadline_text)
            if ai_result:
                logger.success(f'AI parsing successful: {ai_result.deadline_datetime}')
                return ai_result
            logger.debug('AI parsing failed, falling back to regex')
        
        # Fallback to regex pattern matching + datetime parsing
        logger.debug('Using regex pattern matching')
        regex_result = self._try_regex_parsing(deadline_text, context)
        if regex_result:
            logger.success(f'Regex parsing successful: {regex_result.deadline_datetime}')
            return regex_result
        
        logger.warning(f'Failed to parse deadline from: "{deadline_text}"')
        return None
    
    def _try_ai_parsing(
        self,
        full_message: str,
        deadline_text: str
    ) -> Optional[ParsedDeadline]:
        """Try parsing deadline using AI.
        
        Args:
            full_message: Full message text
            deadline_text: Extracted deadline portion
            
        Returns:
            ParsedDeadline or None if parsing fails
        """
        try:
            # Get deadline text from AI
            extracted_text = self.ai_parser.get_deadline_text(full_message)
            
            if not extracted_text:
                logger.debug('AI did not extract deadline text')
                return None
            
            logger.debug(f'AI extracted: "{extracted_text}"')
            
            # Parse the extracted text into datetime
            deadline_datetime = self.datetime_parser.parse(extracted_text)
            
            if not deadline_datetime:
                logger.warning('AI extracted text but datetime parsing failed')
                return None
            
            # Calculate reminder time
            reminder_datetime = self.datetime_parser.calculate_reminder_time(deadline_datetime)
            
            # Create ParsedDeadline object
            return ParsedDeadline(
                original_text=full_message,
                deadline_datetime=deadline_datetime,
                reminder_datetime=reminder_datetime,
                confidence=0.9,  # High confidence for AI parsing
                parsed_by='ai'
            )
            
        except Exception as e:
            logger.error('AI parsing failed with exception', exc=e)
            return None
    
    def _try_regex_parsing(
        self,
        deadline_text: str,
        context: ReminderContext
    ) -> Optional[ParsedDeadline]:
        """Try parsing deadline using regex pattern matching.
        
        Args:
            deadline_text: Deadline text to parse
            context: Message context
            
        Returns:
            ParsedDeadline or None if parsing fails
        """
        try:
            # Find first matching pattern
            match_result = self.pattern_matcher.find_first_match(deadline_text)
            
            if not match_result:
                logger.debug('No regex pattern matched')
                return None
            
            pattern, matched_text = match_result
            logger.debug(f'Pattern matched: "{matched_text}"')
            
            # Parse matched text into datetime
            deadline_datetime = self.datetime_parser.parse(matched_text)
            
            if not deadline_datetime:
                logger.warning('Pattern matched but datetime parsing failed')
                return None
            
            # Calculate reminder time
            reminder_datetime = self.datetime_parser.calculate_reminder_time(deadline_datetime)
            
            # Create ParsedDeadline object
            return ParsedDeadline(
                original_text=context.message_text,
                deadline_datetime=deadline_datetime,
                reminder_datetime=reminder_datetime,
                confidence=0.85,  # Good confidence for regex parsing
                parsed_by='regex'
            )
            
        except Exception as e:
            logger.error('Regex parsing failed with exception', exc=e)
            return None
    
    def has_etc_indicator(self, message: str) -> bool:
        """Check if message has ETC indicator.
        
        Convenience method that delegates to pattern matcher.
        
        Args:
            message: Message to check
            
        Returns:
            True if message has ETC indicator
        """
        return self.pattern_matcher.has_etc_indicator(message)
    
    def extract_deadline_text(self, message: str) -> Optional[str]:
        """Extract deadline text from message.
        
        Convenience method that delegates to pattern matcher.
        
        Args:
            message: Message to parse
            
        Returns:
            Extracted deadline text or None
        """
        return self.pattern_matcher.extract_deadline_text(message)
    
    def get_parsing_stats(self) -> dict:
        """Get statistics about parsing capabilities.
        
        Returns:
            Dictionary with parsing configuration info
        """
        return {
            'ai_enabled': self.ai_parser is not None and self.ai_parser.is_available(),
            'regex_enabled': True,
            'pattern_count': len(self.pattern_matcher.deadline_patterns),
            'ai_model': self.ai_parser.model if self.ai_parser else None
        }
