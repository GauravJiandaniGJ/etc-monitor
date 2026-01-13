"""Centralized logging utility for ETC Monitor application.

Uses print-based logging with emoji prefixes for visibility.
This follows the project requirement to keep logging simple.
"""
from datetime import datetime
from typing import Optional


class Logger:
    """Simple logger with emoji prefixes and timestamps.
    
    Provides consistent logging across the application using print()
    statements with visual emoji indicators and timestamps.
    """
    
    def __init__(self, name: Optional[str] = None, log_level: str = 'INFO'):
        """Initialize logger.
        
        Args:
            name: Optional name/prefix for the logger (e.g., module name)
            log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.name = name
        self.log_level = log_level.upper()
        self._level_priority = {
            'DEBUG': 0,
            'INFO': 1,
            'WARNING': 2,
            'ERROR': 3,
            'CRITICAL': 4
        }
    
    def _should_log(self, level: str) -> bool:
        """Check if message should be logged based on log level.
        
        Args:
            level: Log level of the message
            
        Returns:
            True if message should be logged
        """
        return self._level_priority.get(level, 0) >= self._level_priority.get(self.log_level, 0)
    
    def _format_message(self, emoji: str, level: str, message: str) -> str:
        """Format log message with timestamp, emoji, and optional name.
        
        Args:
            emoji: Emoji prefix
            level: Log level
            message: Log message
            
        Returns:
            Formatted log message
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        prefix = f'[{self.name}]' if self.name else ''
        return f'{emoji} [{timestamp}] {prefix} {message}'
    
    def debug(self, message: str):
        """Log debug message.
        
        Args:
            message: Debug message to log
        """
        if self._should_log('DEBUG'):
            formatted = self._format_message('🔍', 'DEBUG', message)
            print(formatted)
    
    def info(self, message: str):
        """Log info message.
        
        Args:
            message: Info message to log
        """
        if self._should_log('INFO'):
            formatted = self._format_message('📝', 'INFO', message)
            print(formatted)
    
    def success(self, message: str):
        """Log success message.
        
        Args:
            message: Success message to log
        """
        if self._should_log('INFO'):
            formatted = self._format_message('✅', 'SUCCESS', message)
            print(formatted)
    
    def warning(self, message: str):
        """Log warning message.
        
        Args:
            message: Warning message to log
        """
        if self._should_log('WARNING'):
            formatted = self._format_message('⚠️', 'WARNING', message)
            print(formatted)
    
    def error(self, message: str, exc: Optional[Exception] = None):
        """Log error message.
        
        Args:
            message: Error message to log
            exc: Optional exception to include
        """
        if self._should_log('ERROR'):
            if exc:
                formatted = self._format_message('❌', 'ERROR', f'{message}: {exc}')
            else:
                formatted = self._format_message('❌', 'ERROR', message)
            print(formatted)
    
    def critical(self, message: str, exc: Optional[Exception] = None):
        """Log critical message.
        
        Args:
            message: Critical message to log
            exc: Optional exception to include
        """
        if self._should_log('CRITICAL'):
            if exc:
                formatted = self._format_message('🚨', 'CRITICAL', f'{message}: {exc}')
            else:
                formatted = self._format_message('🚨', 'CRITICAL', message)
            print(formatted)
    
    def set_level(self, level: str):
        """Change log level.
        
        Args:
            level: New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.log_level = level.upper()


# Global logger instance
_global_logger: Optional[Logger] = None


def get_logger(name: Optional[str] = None, log_level: Optional[str] = None) -> Logger:
    """Get logger instance.
    
    If log_level is not provided, uses the global logger if available,
    or creates a new logger with INFO level.
    
    Args:
        name: Optional name for the logger
        log_level: Optional log level
        
    Returns:
        Logger instance
    """
    global _global_logger
    
    if log_level:
        return Logger(name=name, log_level=log_level)
    
    if _global_logger and not name:
        return _global_logger
    
    return Logger(name=name, log_level='INFO')


def init_logger(log_level: str = 'INFO'):
    """Initialize global logger with specified log level.
    
    Args:
        log_level: Log level for global logger
    """
    global _global_logger
    _global_logger = Logger(log_level=log_level)
