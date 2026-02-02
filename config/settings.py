"""Configuration management for ETC Monitor application."""
import os
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class Settings:
    """Application configuration settings.

    Loads configuration from environment variables with validation
    for required settings and defaults for optional ones.
    """

    # Slack Configuration (Required)
    slack_bot_token: str = field(init=False)
    slack_signing_secret: str = field(init=False)
    slack_app_token: str = field(init=False)

    # Gemini AI Configuration (Optional)
    gemini_api_key: Optional[str] = field(init=False, default=None)
    gemini_model: str = field(init=False, default='gemini-1.5-flash')
    gemini_temperature: float = field(init=False, default=0.2)

    # Database Configuration
    database_type: str = field(init=False, default='sqlite')  # 'sqlite', 'postgresql', 'mysql'
    database_path: str = field(init=False, default='reminders.db')  # For SQLite
    database_host: Optional[str] = field(init=False, default=None)  # For PostgreSQL/MySQL
    database_port: Optional[int] = field(init=False, default=None)  # For PostgreSQL/MySQL
    database_name: Optional[str] = field(init=False, default=None)  # For PostgreSQL/MySQL
    database_user: Optional[str] = field(init=False, default=None)  # For PostgreSQL/MySQL
    database_password: Optional[str] = field(init=False, default=None)  # For PostgreSQL/MySQL
    database_url: Optional[str] = field(init=False, default=None)  # Full connection URL (optional)

    # Admin Panel Configuration
    flask_secret_key: str = field(init=False)
    admin_username: str = field(init=False, default='admin')
    admin_password: str = field(init=False, default='changeme')

    # Application Configuration
    timezone: str = field(init=False, default='Asia/Kolkata')
    debug: bool = field(init=False, default=False)
    log_level: str = field(init=False, default='INFO')
    
    # Daily Summary Configuration
    daily_summary_enabled: bool = field(init=False, default=True)
    daily_summary_hour: int = field(init=False, default=9)
    daily_summary_minute: int = field(init=False, default=0)
    
    # DM Support Configuration
    enable_dm_support: bool = field(init=False, default=True)

    def __post_init__(self):
        """Load and validate environment variables after initialization."""
        # Load Slack configuration (required)
        self.slack_bot_token = self._get_required_env('SLACK_BOT_TOKEN')
        self.slack_signing_secret = self._get_required_env('SLACK_SIGNING_SECRET')
        self.slack_app_token = self._get_required_env('SLACK_APP_TOKEN')

        # Load Gemini AI configuration (optional)
        self.gemini_api_key = os.environ.get('GEMINI_API_KEY')
        self.gemini_model = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')
        self.gemini_temperature = float(os.environ.get('GEMINI_TEMPERATURE', '0.2'))

        # Load database configuration
        self.database_type = os.environ.get('DATABASE_TYPE', 'sqlite').lower()

        if self.database_type == 'sqlite':
            # SQLite configuration
                self.database_path = os.environ.get('DATABASE_PATH', 'reminders.db')
        else:
            # PostgreSQL/MySQL configuration
            self.database_host = os.environ.get('DATABASE_HOST')
            self.database_port = int(os.environ.get('DATABASE_PORT', '5432' if self.database_type == 'postgresql' else '3306'))
            self.database_name = os.environ.get('DATABASE_NAME', 'etc_monitor')
            self.database_user = os.environ.get('DATABASE_USER')
            self.database_password = os.environ.get('DATABASE_PASSWORD')
            self.database_url = os.environ.get('DATABASE_URL')  # Optional full URL

        # Load admin panel configuration
        self.flask_secret_key = self._get_required_env('FLASK_SECRET_KEY')
        self.admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        self.admin_password = os.environ.get('ADMIN_PASSWORD', 'changeme')

        # Load application configuration
        self.timezone = os.environ.get('TIMEZONE', 'Asia/Kolkata')
        self.debug = os.environ.get('DEBUG', 'false').lower() in ('true', '1', 'yes')
        self.log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
        
        # Load daily summary configuration
        self.daily_summary_enabled = os.environ.get('DAILY_SUMMARY_ENABLED', 'true').lower() in ('true', '1', 'yes')
        self.daily_summary_hour = int(os.environ.get('DAILY_SUMMARY_HOUR', '9'))
        self.daily_summary_minute = int(os.environ.get('DAILY_SUMMARY_MINUTE', '0'))
        
        # Load DM support configuration
        self.enable_dm_support = os.environ.get('ENABLE_DM_SUPPORT', 'true').lower() in ('true', '1', 'yes')

        # Validate configuration
        self._validate()

        # Print loaded configuration (mask sensitive values)
        self._print_config()

    def _get_required_env(self, key: str) -> str:
        """Get required environment variable or raise error.

        Args:
            key: Environment variable name

        Returns:
            Environment variable value

        Raises:
            ValueError: If environment variable is not set
        """
        value = os.environ.get(key)
        if not value:
            raise ValueError(f'Missing required environment variable: {key}')
        return value

    def _validate(self):
        """Validate configuration values."""
        # Validate timezone
        try:
            import pytz
            pytz.timezone(self.timezone)
        except Exception as e:
            raise ValueError(f'Invalid timezone: {self.timezone}. Error: {e}')

        # Validate log level
        valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if self.log_level not in valid_log_levels:
            raise ValueError(f'Invalid log level: {self.log_level}. Must be one of {valid_log_levels}')

        # Validate Gemini temperature
        if not 0.0 <= self.gemini_temperature <= 2.0:
            raise ValueError(f'Invalid Gemini temperature: {self.gemini_temperature}. Must be between 0.0 and 2.0')

        # Warn about insecure defaults
        if self.admin_password == 'changeme':
            print('[WARNING] Using default admin password. Change ADMIN_PASSWORD in .env for production!')

        if self.flask_secret_key == 'generate-secure-key-here':
            print('[WARNING] Using default Flask secret key. Change FLASK_SECRET_KEY in .env for production!')

    def _print_config(self):
        """Print loaded configuration with sensitive values masked."""
        print('[INFO] Configuration loaded:')
        print(f'  - Slack Bot Token: {self._mask_token(self.slack_bot_token)}')
        print(f'  - Slack App Token: {self._mask_token(self.slack_app_token)}')
        print(f'  - Gemini API Key: {self._mask_token(self.gemini_api_key) if self.gemini_api_key else "Not configured"}')
        print(f'  - Gemini Model: {self.gemini_model}')
        if self.database_type == 'sqlite':
            print(f'  - Database Type: SQLite')
            print(f'  - Database Path: {self.database_path}')
        else:
            print(f'  - Database Type: {self.database_type.upper()}')
            print(f'  - Database Host: {self.database_host}:{self.database_port}')
            print(f'  - Database Name: {self.database_name}')
            print(f'  - Database User: {self.database_user}')
        print(f'  - Timezone: {self.timezone}')
        print(f'  - Debug Mode: {self.debug}')
        print(f'  - Log Level: {self.log_level}')

    @staticmethod
    def _mask_token(token: Optional[str]) -> str:
        """Mask token for safe display.

        Args:
            token: Token to mask

        Returns:
            Masked token showing only first/last few characters
        """
        if not token:
            return 'None'
        if len(token) <= 8:
            return '***'
        return f'{token[:4]}...{token[-4:]}'

    @property
    def is_gemini_configured(self) -> bool:
        """Check if Gemini AI is configured.

        Returns:
            True if Gemini API key is set
        """
        return self.gemini_api_key is not None and len(self.gemini_api_key) > 0
