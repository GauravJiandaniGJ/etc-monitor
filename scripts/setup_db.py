#!/usr/bin/env python3
"""Database setup script.

Initializes the database and runs all pending migrations.
"""
import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import Settings
from src.database.db_manager import DBManager
from src.database.migrations.migration_manager import MigrationManager
from src.utils.logger import get_logger, init_logger


logger = get_logger('SetupDB')


def main():
    """Initialize database and run migrations."""
    try:
        # Load settings
        settings = Settings()

        # Initialize logger
        init_logger(settings.log_level)

        logger.info('Starting database setup')

        # Log database info correctly
        if settings.database_type == 'sqlite':
            logger.info(f'Database: SQLite ({settings.database_path})')
        else:
            logger.info(
                f'Database: {settings.database_type.upper()} '
                f'{settings.database_host}:{settings.database_port}/{settings.database_name}'
            )

        # Initialize database manager
        db_manager = DBManager(settings)
        logger.success('Database manager initialized')

        # Initialize migration manager
        migration_manager = MigrationManager(db_manager)
        logger.info('Migration manager initialized')

        # Get migration status
        status = migration_manager.get_status()
        applied_count = len(status['applied'])
        pending_count = len(status['pending'])

        logger.info(
            f'Migration status: {applied_count} applied, {pending_count} pending'
        )

        # Run pending migrations
        if pending_count > 0:
            logger.info('Running pending migrations...')
            migration_manager.run_pending()
            logger.success('All migrations completed successfully')
        else:
            logger.info('No pending migrations')

        # Print final status
        migration_manager.print_status()

        # Close database connections
        db_manager.close_all()

        logger.success('Database setup completed successfully')

    except Exception as e:
        logger.error('Database setup failed', exc=e)
        sys.exit(1)


if __name__ == '__main__':
    main()
