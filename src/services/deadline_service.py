"""Deadline service for detecting and parsing deadline expressions - Production Optimized.

Always uses AI first, falls back to regex only on AI failure/timeout.
Optimized for real-time responses.
"""
from typing import Optional
from src.core.models import ReminderContext, ParsedDeadline
from src.parsers.pattern_matcher import PatternMatcher
from src.parsers.datetime_parser import DateTimeParser
from src.parsers.ai_parser import AIParser
from src.utils.logger import get_logger


logger = get_logger('DeadlineService')


class DeadlineService:
    """Service for detecting deadlines in messages - Production Optimized.

    Design:
    - ALWAYS tries AI first (no exceptions)
    - Fast timeout (5 seconds)
    - Falls back to regex only if AI fails
    - Optimized for real-time responses
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
            logger.info('AI parsing enabled - ALWAYS used first')
        else:
            logger.warning('AI parsing disabled - using regex only')

    def detect(
        self,
        message: str,
        context: ReminderContext
    ) -> Optional[ParsedDeadline]:
        """Detect deadline in message - AI FIRST, always.

        Flow:
        1. Check for ETC indicator (quick regex check)
        2. ALWAYS try AI parsing first
        3. Fall back to regex only if AI fails

        Args:
            message: Message text to parse
            context: Message context

        Returns:
            ParsedDeadline object or None if no deadline detected
        """
        try:
            if not message or not message.strip():
                logger.debug('Empty message')
                return None

            logger.info(f'Detecting deadline from user {context.user_id}: "{message}"')

            # Quick ETC indicator check
            has_etc = self.pattern_matcher.has_etc_indicator(message)
            if not has_etc:
                logger.debug(f'No ETC indicator in message')
                return None

            logger.info('ETC indicator detected - proceeding to parsing')

            # CRITICAL: ALWAYS try AI first (user requirement)
            if self.ai_parser and self.ai_parser.is_available():
                logger.info('=' * 60)
                logger.info('[AI] ALWAYS USING AI FIRST - Attempting AI parsing...')
                logger.info('=' * 60)

                try:
                    ai_result = self._try_ai_parsing(message)
                    if ai_result:
                        logger.success(
                            f'[AI] Success: {ai_result.deadline_datetime} '
                            f'(confidence: {ai_result.confidence:.2f})'
                        )
                        return ai_result

                    logger.warning('[AI] AI parsing returned None - falling back to regex')
                except Exception as e:
                    logger.error(f'[AI] AI parsing error: {e} - falling back to regex', exc=e)
            else:
                logger.warning('[AI] AI parser not available - using regex only')

            # Fallback to regex pattern matching
            logger.info('Using regex pattern matching as fallback')
            regex_result = self._try_regex_parsing(message, context)
            if regex_result:
                logger.success(f'Regex parsing successful: {regex_result.deadline_datetime}')
                return regex_result

            logger.warning(f'Failed to parse deadline from message')
            return None

        except Exception as e:
            logger.error(f'Unexpected error in deadline detection: {e}', exc=e)
            return None

    def _try_ai_parsing(self, full_message: str) -> Optional[ParsedDeadline]:
        """Try parsing deadline using AI - optimized.

        Args:
            full_message: Full message text

        Returns:
            ParsedDeadline or None if parsing fails
        """
        try:
            logger.info(f'[AI] Calling AI parser for: "{full_message[:80]}..."')

            # Get deadline text from AI
            extracted_text = self.ai_parser.get_deadline_text(full_message)

            if not extracted_text:
                logger.debug('[AI] AI did not extract deadline text')
                return None

            logger.info(f'[AI] Extracted text: "{extracted_text}"')

            # Parse extracted text into datetime
            deadline_datetime = self.datetime_parser.parse(extracted_text)
            if not deadline_datetime:
                logger.warning(f'[AI] DateTime parsing failed for: "{extracted_text}"')
                return None

            logger.info(f'[AI] Parsed datetime: {deadline_datetime}')

            # Calculate reminder time (exactly at deadline)
            reminder_datetime = self.datetime_parser.calculate_reminder_time(deadline_datetime)

            logger.success(
                f'[AI] Complete: deadline={deadline_datetime}, reminder={reminder_datetime}'
            )

            return ParsedDeadline(
                original_text=extracted_text,
                deadline_datetime=deadline_datetime,
                reminder_datetime=reminder_datetime,
                confidence=0.9,  # High confidence for AI
                parsed_by='ai'
            )

        except Exception as e:
            logger.error(f'[AI] Parsing failed: {e}', exc=e)
            return None

    def _try_regex_parsing(
        self,
        message: str,
        context: ReminderContext
    ) -> Optional[ParsedDeadline]:
        """Try parsing deadline using regex pattern matching.

        Args:
            message: Message text
            context: Message context

        Returns:
            ParsedDeadline or None if parsing fails
        """
        try:
            # Extract deadline text
            deadline_text = self.pattern_matcher.extract_deadline_text(message)
            if not deadline_text:
                deadline_text = message

            # Find matching pattern
            match_result = self.pattern_matcher.find_first_match(deadline_text)
            text_to_parse = match_result[1] if match_result else deadline_text

            logger.info(f'Regex parsing: "{text_to_parse}"')

            # Parse into datetime
            deadline_datetime = self.datetime_parser.parse(text_to_parse)
            if not deadline_datetime:
                logger.warning(f'DateTime parsing failed for: "{text_to_parse}"')
                return None

            # Calculate reminder time
            reminder_datetime = self.datetime_parser.calculate_reminder_time(deadline_datetime)

            return ParsedDeadline(
                original_text=text_to_parse,
                deadline_datetime=deadline_datetime,
                reminder_datetime=reminder_datetime,
                confidence=0.85,  # Good confidence for regex
                parsed_by='regex'
            )

        except Exception as e:
            logger.error('Regex parsing failed', exc=e)
            return None

    def has_etc_indicator(self, message: str) -> bool:
        """Check if message has ETC indicator.

        Args:
            message: Message to check

        Returns:
            True if message has ETC indicator
        """
        return self.pattern_matcher.has_etc_indicator(message)

    def extract_deadline_text(self, message: str) -> Optional[str]:
        """Extract deadline text from message.

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
