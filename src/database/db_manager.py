"""Database manager for ETC Monitor application.

Provides database connection management and query execution using sqlite3.
"""
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple
from src.utils.logger import get_logger


logger = get_logger('DBManager')


class DBManager:
    """Database manager with connection pooling and error handling.
    
    Uses sqlite3 directly for database operations. Provides context manager
    pattern for safe connection handling.
    """
    
    def __init__(self, database_path: str):
        """Initialize database manager.
        
        Args:
            database_path: Path to SQLite database file
        """
        self.database_path = database_path
        self._local = threading.local()
        logger.info(f'Database manager initialized with path: {database_path}')
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection.
        
        Creates a new connection if one doesn't exist for this thread.
        
        Returns:
            SQLite connection object
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            try:
                self._local.connection = sqlite3.connect(
                    self.database_path,
                    check_same_thread=False,
                    timeout=30.0
                )
                # Enable foreign key constraints
                self._local.connection.execute('PRAGMA foreign_keys = ON')
                # Return rows as dictionaries
                self._local.connection.row_factory = sqlite3.Row
                logger.debug(f'Created new database connection for thread {threading.get_ident()}')
            except sqlite3.Error as e:
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
            SQLite connection object
        """
        conn = self._get_connection()
        try:
            yield conn
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f'Database operation failed, rolled back', exc=e)
            raise
        else:
            conn.commit()
    
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
            Query results if fetch_one or fetch_all is True, otherwise None
            
        Raises:
            sqlite3.Error: If query execution fails
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if fetch_one:
                    result = cursor.fetchone()
                    return dict(result) if result else None
                elif fetch_all:
                    results = cursor.fetchall()
                    return [dict(row) for row in results]
                else:
                    return cursor.lastrowid
        except sqlite3.Error as e:
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
            
        Raises:
            sqlite3.Error: If query execution fails
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, params_list)
                return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f'Batch query execution failed: {query[:100]}...', exc=e)
            raise
    
    def execute_script(self, script: str) -> None:
        """Execute SQL script (multiple statements).
        
        Args:
            script: SQL script to execute
            
        Raises:
            sqlite3.Error: If script execution fails
        """
        try:
            with self.get_connection() as conn:
                conn.executescript(script)
            logger.success('SQL script executed successfully')
        except sqlite3.Error as e:
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
        query = '''
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        '''
        result = self.fetch_one(query, (table_name,))
        return result is not None
    
    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """Get schema information for a table.
        
        Args:
            table_name: Name of table
            
        Returns:
            List of column definitions
        """
        query = f'PRAGMA table_info({table_name})'
        return self.fetch_all(query)
    
    def vacuum(self) -> None:
        """Vacuum database to reclaim space and optimize.
        
        Should be called periodically for maintenance.
        """
        try:
            with self.get_connection() as conn:
                conn.execute('VACUUM')
            logger.success('Database vacuumed successfully')
        except sqlite3.Error as e:
            logger.error('Database vacuum failed', exc=e)
            raise
    
    def close(self) -> None:
        """Close database connection for current thread.
        
        Should be called when thread is done with database operations.
        """
        if hasattr(self._local, 'connection') and self._local.connection:
            try:
                self._local.connection.close()
                self._local.connection = None
                logger.debug(f'Closed database connection for thread {threading.get_ident()}')
            except sqlite3.Error as e:
                logger.error('Failed to close database connection', exc=e)
    
    def close_all(self) -> None:
        """Close all database connections.
        
        Should be called on application shutdown.
        """
        self.close()
        logger.info('All database connections closed')
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
