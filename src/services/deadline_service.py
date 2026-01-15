"""Deadline service for detecting and parsing deadline expressions.

Orchestrates pattern matching and parsing to extract deadlines from messages.
"""
from typing import Optional
from src.core.models import ReminderContext, ParsedDeadline
from src.parsers.pattern_matcher import PatternMatcher
from src.parsers.datetime_parser import DateTimeParser
from src.parsers.ai_parser import AIParser
from src.utils.logger import get_logger


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
        try:
            if not message:
                logger.debug('Empty message provided')
                return None

            logger.info(f'Detecting deadline in message from user {context.user_id}')
            logger.info(f'Full message text: "{message}"')

            # Check if message has ETC indicator
            has_etc = self.pattern_matcher.has_etc_indicator(message)
            logger.info(f'Pattern matcher ETC check: {has_etc}')

            if not has_etc:
                logger.info(f'No ETC indicator found in message: "{message}"')
                return None

            # Extract deadline text from message
            deadline_text = self.pattern_matcher.extract_deadline_text(message)
            logger.info(f'Extracted deadline text result: "{deadline_text}"')

            if not deadline_text:
                logger.warning('ETC indicator found but could not extract deadline text - trying full message for AI')
                # If extraction fails, still try AI with full message
                deadline_text = message

            logger.info(f'Using deadline text for parsing: "{deadline_text}"')

            # CRITICAL: Always try AI parsing first (user requirement: AI ALWAYS first, no exceptions)
            # Even if deadline_text extraction failed, try AI with full message
            if self.ai_parser and self.ai_parser.is_available():
                logger.info('=' * 60)
                logger.info('[AI] ⚡ ALWAYS USING AI FIRST (Gemini) - Attempting AI parsing...')
                logger.info(f'[AI] Full message: "{message}"')
                logger.info(f'[AI] Extracted text: "{deadline_text}"')
                logger.info(f'[AI] AI parser available: {self.ai_parser.is_available()}')
                logger.info('=' * 60)
                try:
                    # Always pass full message to AI - it's smarter at extraction
                    ai_result = self._try_ai_parsing(message, deadline_text)
                    if ai_result:
                        logger.success(f'[AI] ✅ AI parsing successful: {ai_result.deadline_datetime} (parsed_by: {ai_result.parsed_by})')
                        return ai_result
                    logger.warning('[AI] ⚠️ AI parsing returned None or timed out after 8 seconds, falling back to regex as last resort')
                except Exception as e:
                    logger.error(f'[AI] ❌ AI parsing error: {e}, falling back to regex as last resort', exc=e)
            else:
                logger.error('[AI] ❌ AI parser not available!')
                logger.error(f'[AI] AI parser object: {self.ai_parser}')
                logger.error(f'[AI] Is available check: {self.ai_parser.is_available() if self.ai_parser else "N/A"}')
                logger.error('[AI] Using regex as fallback')

            # Fallback to regex pattern matching + datetime parsing
            logger.info(f'Using regex pattern matching for: "{deadline_text}"')
            regex_result = self._try_regex_parsing(deadline_text, context)
            if regex_result:
                logger.success(f'Regex parsing successful: {regex_result.deadline_datetime}')
                return regex_result

            logger.warning(f'Failed to parse deadline from: "{deadline_text}"')
            return None

        except Exception as e:
            logger.error(f'Unexpected error in deadline detection: {e}', exc=e)
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
            logger.info('[AI] 🔍 Calling AI parser to extract deadline text...')
            logger.info(f'[AI] Input message: "{full_message}"')
            # Get deadline text from AI - always use full message for best results
            extracted_text = self.ai_parser.get_deadline_text(full_message)
            logger.info(f'[AI] AI returned: "{extracted_text}"')

            if not extracted_text:
                logger.info('AI did not extract deadline text (timeout or no result), returning None')
                return None

            logger.info(f'AI extracted deadline text: "{extracted_text}"')

            # Parse the extracted text into datetime
            logger.info(f'Parsing AI-extracted text with DateTimeParser: "{extracted_text}"')
            deadline_datetime = self.datetime_parser.parse(extracted_text)

            if not deadline_datetime:
                logger.warning('AI extracted text but datetime parsing failed')
                return None

            logger.info(f'DateTime parsed from AI text: {deadline_datetime}')

            # Calculate reminder time
            reminder_datetime = self.datetime_parser.calculate_reminder_time(deadline_datetime)

            # Create ParsedDeadline object
            # Store the AI-extracted deadline text (e.g., "2 mins") in original_text
            # This will be stored in reminder.deadline_text field
            logger.success(f'AI parsing complete: deadline={deadline_datetime}, reminder={reminder_datetime}')
            return ParsedDeadline(
                original_text=extracted_text,  # Store AI-extracted text, not full message
                deadline_datetime=deadline_datetime,
                reminder_datetime=reminder_datetime,
                confidence=0.9,  # High confidence for AI parsing
                parsed_by='ai'
            )

        except Exception as e:
            logger.error(f'AI parsing failed with exception: {e}', exc=e)
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

            text_to_parse = deadline_text
            if match_result:
                _pattern, matched_text = match_result
                logger.info(f'Pattern matched: "{matched_text}"')
                text_to_parse = matched_text
            else:
                logger.info(f'No regex pattern matched, trying direct datetime parsing for: "{deadline_text}"')
                # Even if no pattern matches, try parsing the text directly
                # DateTimeParser can handle simple relative times like "45mins", "2h", etc.
                text_to_parse = deadline_text

            # Parse text into datetime (works for both matched patterns and direct text)
            deadline_datetime = self.datetime_parser.parse(text_to_parse)

            if not deadline_datetime:
                logger.warning(f'DateTime parsing failed for: "{text_to_parse}"')
                return None

            logger.info(f'DateTime parsed successfully: {deadline_datetime}')

            # Calculate reminder time
            reminder_datetime = self.datetime_parser.calculate_reminder_time(deadline_datetime)

            # Create ParsedDeadline object
            # Store the extracted deadline text (e.g., "2 mins") in original_text
            # This will be stored in reminder.deadline_text field
            return ParsedDeadline(
                original_text=text_to_parse,  # Store extracted deadline text, not full message
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
