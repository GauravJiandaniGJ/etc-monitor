"""Database manager for ETC Monitor application.

Supports SQLite, PostgreSQL, and MySQL databases.
"""
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple, Union
from src.utils.logger import get_logger

# Try importing database drivers (optional)
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
    MYSQL_AVAILABLE = True
    MYSQL_DRIVER = 'mysql.connector'
except ImportError:
    try:
        import pymysql
        MYSQL_AVAILABLE = True
        MYSQL_DRIVER = 'pymysql'
    except ImportError:
        MYSQL_AVAILABLE = False
        MYSQL_DRIVER = None

logger = get_logger('DBManager')


class DBManager:
    """Database manager with connection pooling and error handling.

    Supports SQLite, PostgreSQL, and MySQL databases based on configuration.
    """

    def __init__(self, settings):
        """Initialize database manager.

        Args:
            settings: Settings object with database configuration
        """
        self.settings = settings
        self.database_type = settings.database_type
        self._local = threading.local()

        if self.database_type == 'sqlite':
            self.database_path = settings.database_path
            logger.info(f'Database manager initialized: SQLite at {self.database_path}')
        elif self.database_type == 'postgresql':
            if not PSYCOPG2_AVAILABLE:
                raise ImportError('psycopg2 is required for PostgreSQL. Install with: pip install psycopg2-binary')
            self._init_postgresql()
        elif self.database_type == 'mysql':
            if not MYSQL_AVAILABLE:
                raise ImportError('mysql-connector-python or pymysql is required for MySQL. Install with: pip install mysql-connector-python')
            self._init_mysql()
        else:
            raise ValueError(f'Unsupported database type: {self.database_type}')

    def _init_postgresql(self):
        """Initialize PostgreSQL connection parameters."""
        if self.settings.database_url:
            self.connection_string = self.settings.database_url
        else:
            if not all([self.settings.database_host, self.settings.database_name,
                       self.settings.database_user, self.settings.database_password]):
                raise ValueError('PostgreSQL requires DATABASE_HOST, DATABASE_NAME, DATABASE_USER, and DATABASE_PASSWORD')

            # Add connection timeout and statement timeout to prevent hanging
            self.connection_string = (
                f"host={self.settings.database_host} "
                f"port={self.settings.database_port} "
                f"dbname={self.settings.database_name} "
                f"user={self.settings.database_user} "
                f"password={self.settings.database_password} "
                f"connect_timeout=10 "
                f"options='-c statement_timeout=30s'"
            )
        logger.info(f'Database manager initialized: PostgreSQL at {self.settings.database_host}:{self.settings.database_port}/{self.settings.database_name}')

    def _init_mysql(self):
        """Initialize MySQL connection parameters."""
        if self.settings.database_url:
            # Parse URL if provided
            self.connection_params = self._parse_mysql_url(self.settings.database_url)
        else:
            if not all([self.settings.database_host, self.settings.database_name,
                       self.settings.database_user, self.settings.database_password]):
                raise ValueError('MySQL requires DATABASE_HOST, DATABASE_NAME, DATABASE_USER, and DATABASE_PASSWORD')

            self.connection_params = {
                'host': self.settings.database_host,
                'port': self.settings.database_port,
                'database': self.settings.database_name,
                'user': self.settings.database_user,
                'password': self.settings.database_password
            }
        logger.info(f'Database manager initialized: MySQL at {self.settings.database_host}:{self.settings.database_port}/{self.settings.database_name}')

    def _parse_mysql_url(self, url: str) -> dict:
        """Parse MySQL connection URL."""
        # Simple URL parser: mysql://user:pass@host:port/db
        import re
        match = re.match(r'mysql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', url)
        if match:
            return {
                'user': match.group(1),
                'password': match.group(2),
                'host': match.group(3),
                'port': int(match.group(4)),
                'database': match.group(5)
            }
        raise ValueError(f'Invalid MySQL URL format: {url}')

    def _get_connection(self):
        """Get thread-local database connection.

        Returns:
            Database connection object (SQLite, PostgreSQL, or MySQL)
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            try:
                if self.database_type == 'sqlite':
                    self._local.connection = sqlite3.connect(
                        self.database_path,
                        check_same_thread=False,
                        timeout=30.0
                    )
                    self._local.connection.execute('PRAGMA foreign_keys = ON')
                    self._local.connection.row_factory = sqlite3.Row

                elif self.database_type == 'postgresql':
                    self._local.connection = psycopg2.connect(self.connection_string)
                    # Enable autocommit for PostgreSQL to avoid blocking on read queries
                    # Explicit transactions can still be used when needed
                    self._local.connection.autocommit = True
                    # Set statement timeout to prevent queries from hanging indefinitely
                    with self._local.connection.cursor() as cursor:
                        cursor.execute("SET statement_timeout = '30s'")

                elif self.database_type == 'mysql':
                    if MYSQL_DRIVER == 'pymysql':
                        import pymysql
                        self._local.connection = pymysql.connect(**self.connection_params)
                    else:
                        import mysql.connector
                        self._local.connection = mysql.connector.connect(**self.connection_params)
                    self._local.connection.autocommit = False

                logger.debug(f'Created new database connection for thread {threading.get_ident()}')
            except Exception as e:
                logger.error(f'Failed to connect to database', exc=e)
                raise

        return self._local.connection

    @contextmanager
    def get_connection(self):
        """Context manager for database connection.

        Usage:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(...)

        Yields:
            Database connection object
        """
        conn = self._get_connection()
        # For PostgreSQL with autocommit=True, we don't need commit/rollback
        # For other databases or when autocommit=False, handle transactions
        needs_transaction = (
            self.database_type != 'postgresql' or
            (hasattr(conn, 'autocommit') and not conn.autocommit)
        )

        try:
            yield conn
        except Exception as e:
            if needs_transaction:
                conn.rollback()
            logger.error(f'Database operation failed, rolled back', exc=e)
            raise
        else:
            if needs_transaction:
                conn.commit()

    def _get_cursor(self, conn):
        """Get appropriate cursor for database type.

        Args:
            conn: Database connection

        Returns:
            Cursor object
        """
        if self.database_type == 'postgresql':
            return conn.cursor(cursor_factory=RealDictCursor)
        elif self.database_type == 'mysql':
            return conn.cursor(dictionary=True)
        else:  # SQLite
            return conn.cursor()

    def _row_to_dict(self, row, cursor=None):
        """Convert database row to dictionary.

        Args:
            row: Database row
            cursor: Optional cursor (for column names)

        Returns:
            Dictionary representation of row
        """
        if self.database_type == 'postgresql':
            return dict(row)  # RealDictCursor already returns dict
        elif self.database_type == 'mysql':
            return dict(row)  # dictionary=True already returns dict
        else:  # SQLite
            return dict(row)  # Row factory already returns dict-like

    def execute(
        self,
        query: str,
        params: Optional[Tuple] = None,
        fetch_one: bool = False,
        fetch_all: bool = False
    ) -> Optional[Any]:
        """Execute a single query.

        Args:
            query: SQL query to execute
            params: Optional query parameters
            fetch_one: If True, return single row
            fetch_all: If True, return all rows

        Returns:
            Query results if fetch_one or fetch_all is True, otherwise lastrowid
        """
        try:
            with self.get_connection() as conn:
                cursor = self._get_cursor(conn)

                # Convert SQLite ? placeholders to %s for PostgreSQL/MySQL
                if self.database_type != 'sqlite' and params:
                    query = query.replace('?', '%s')

                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)

                if fetch_one:
                    result = cursor.fetchone()
                    return self._row_to_dict(result) if result else None
                elif fetch_all:
                    results = cursor.fetchall()
                    return [self._row_to_dict(row) for row in results]
                else:
                    return cursor.lastrowid
        except Exception as e:
            logger.error(f'Query execution failed: {query[:100]}...', exc=e)
            raise

    def execute_many(
        self,
        query: str,
        params_list: List[Tuple]
    ) -> int:
        """Execute query with multiple parameter sets.

        Args:
            query: SQL query to execute
            params_list: List of parameter tuples

        Returns:
            Number of rows affected
        """
        try:
            with self.get_connection() as conn:
                cursor = self._get_cursor(conn)

                # Convert placeholders
                if self.database_type != 'sqlite':
                    query = query.replace('?', '%s')

                cursor.executemany(query, params_list)
                return cursor.rowcount
        except Exception as e:
            logger.error(f'Batch query execution failed: {query[:100]}...', exc=e)
            raise

    def execute_script(self, script: str) -> None:
        """Execute SQL script (multiple statements).

        Args:
            script: SQL script to execute
        """
        try:
            with self.get_connection() as conn:
                cursor = self._get_cursor(conn)

                # Split by semicolon and execute each statement
                statements = [s.strip() for s in script.split(';') if s.strip()]
                for statement in statements:
                    if statement:
                        try:
                            cursor.execute(statement)
                        except Exception as e:
                            # Some statements might fail (like IF NOT EXISTS on existing tables)
                            # Log but continue
                            if 'already exists' in str(e).lower() or 'duplicate' in str(e).lower():
                                logger.debug(f'Statement skipped (already exists): {statement[:50]}...')
                            else:
                                raise

            logger.success('SQL script executed successfully')
        except Exception as e:
            logger.error(f'Script execution failed', exc=e)
            raise

    def fetch_one(self, query: str, params: Optional[Tuple] = None) -> Optional[Dict[str, Any]]:
        """Execute query and fetch single row.

        Args:
            query: SQL query to execute
            params: Optional query parameters

        Returns:
            Single row as dictionary, or None if no results
        """
        return self.execute(query, params, fetch_one=True)

    def fetch_all(self, query: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        """Execute query and fetch all rows.

        Args:
            query: SQL query to execute
            params: Optional query parameters

        Returns:
            List of rows as dictionaries
        """
        return self.execute(query, params, fetch_all=True)

    def table_exists(self, table_name: str) -> bool:
        """Check if table exists in database.

        Args:
            table_name: Name of table to check

        Returns:
            True if table exists
        """
        if self.database_type == 'sqlite':
            query = "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
            result = self.fetch_one(query, (table_name,))
        elif self.database_type == 'postgresql':
            query = "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = %s"
            result = self.fetch_one(query, (table_name,))
        else:  # MySQL
            query = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s"
            result = self.fetch_one(query, (self.settings.database_name, table_name))

        return result is not None

    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """Get schema information for a table.

        Args:
            table_name: Name of table

        Returns:
            List of column definitions
        """
        if self.database_type == 'sqlite':
            query = f'PRAGMA table_info({table_name})'
            return self.fetch_all(query)
        elif self.database_type == 'postgresql':
            query = """
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """
            return self.fetch_all(query, (table_name,))
        else:  # MySQL
            query = f'DESCRIBE {table_name}'
            return self.fetch_all(query)

    def vacuum(self) -> None:
        """Vacuum database to reclaim space and optimize.

        Only works for SQLite. For PostgreSQL/MySQL, use VACUUM/OPTIMIZE TABLE commands.
        """
        if self.database_type == 'sqlite':
            try:
                with self.get_connection() as conn:
                    conn.execute('VACUUM')
                logger.success('Database vacuumed successfully')
            except Exception as e:
                logger.error('Database vacuum failed', exc=e)
                raise
        else:
            logger.warning('VACUUM is SQLite-specific. Use database-specific optimization commands.')

    def close(self) -> None:
        """Close database connection for current thread."""
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
                self._local.connection = None
                logger.debug(f'Closed database connection for thread {threading.get_ident()}')
            except Exception as e:
                logger.error('Failed to close database connection', exc=e)

    def close_all(self) -> None:
        """Close all database connections."""
        self.close()
        logger.info('All database connections closed')

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
