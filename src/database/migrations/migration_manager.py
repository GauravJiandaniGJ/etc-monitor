"""Migration manager for database schema versioning."""
import os
import re
import importlib.util
from typing import List, Dict, Optional
from datetime import datetime
from src.database.db_manager import DBManager
from src.utils.logger import get_logger


logger = get_logger('MigrationManager')


class Migration:
    """Represents a single database migration."""
    
    def __init__(self, version: str, description: str, file_path: str):
        """Initialize migration.
        
        Args:
            version: Migration version (e.g., '001')
            description: Migration description
            file_path: Path to migration file
        """
        self.version = version
        self.description = description
        self.file_path = file_path
        self.module = None
    
    def load(self):
        """Load migration module dynamically."""
        if self.module is None:
            spec = importlib.util.spec_from_file_location(
                f'migration_{self.version}',
                self.file_path
            )
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        return self.module
    
    def upgrade(self, db_manager: DBManager):
        """Execute migration upgrade.
        
        Args:
            db_manager: Database manager instance
        """
        module = self.load()
        if hasattr(module, 'upgrade'):
            module.upgrade(db_manager)
        else:
            raise AttributeError(f'Migration {self.version} missing upgrade() function')
    
    def downgrade(self, db_manager: DBManager):
        """Execute migration downgrade (rollback).
        
        Args:
            db_manager: Database manager instance
        """
        module = self.load()
        if hasattr(module, 'downgrade'):
            module.downgrade(db_manager)
        else:
            raise AttributeError(f'Migration {self.version} missing downgrade() function')


class MigrationManager:
    """Manages database migrations.
    
    Auto-discovers migrations in versions/ folder and tracks applied migrations.
    """
    
    def __init__(self, db_manager: DBManager, migrations_dir: Optional[str] = None):
        """Initialize migration manager.
        
        Args:
            db_manager: Database manager instance
            migrations_dir: Path to migrations directory (auto-detected if None)
        """
        self.db = db_manager
        
        # Auto-detect migrations directory if not provided
        if migrations_dir is None:
            current_file = os.path.abspath(__file__)
            current_dir = os.path.dirname(current_file)
            self.migrations_dir = os.path.join(current_dir, 'versions')
        else:
            self.migrations_dir = migrations_dir
        
        logger.info(f'Migration manager initialized with directory: {self.migrations_dir}')
        self._ensure_migrations_table()
    
    def _ensure_migrations_table(self):
        """Create schema_migrations table if it doesn't exist."""
        query = '''
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL UNIQUE,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        '''
        self.db.execute(query)
        logger.debug('Ensured schema_migrations table exists')
    
    def discover_migrations(self) -> List[Migration]:
        """Discover all migration files in versions directory.
        
        Migration files should be named: NNN_description.py (e.g., 001_initial_schema.py)
        
        Returns:
            List of Migration objects sorted by version
        """
        migrations = []
        
        if not os.path.exists(self.migrations_dir):
            logger.warning(f'Migrations directory not found: {self.migrations_dir}')
            return migrations
        
        # Pattern: 001_initial_schema.py
        pattern = re.compile(r'^(\d{3})_(.+)\.py$')
        
        for filename in os.listdir(self.migrations_dir):
            match = pattern.match(filename)
            if match:
                version = match.group(1)
                description = match.group(2).replace('_', ' ')
                file_path = os.path.join(self.migrations_dir, filename)
                
                migration = Migration(version, description, file_path)
                migrations.append(migration)
        
        # Sort by version
        migrations.sort(key=lambda m: m.version)
        
        logger.info(f'Discovered {len(migrations)} migrations')
        return migrations
    
    def get_applied(self) -> List[Dict[str, str]]:
        """Get list of applied migrations.
        
        Returns:
            List of applied migration records
        """
        query = '''
            SELECT version, description, applied_at 
            FROM schema_migrations 
            ORDER BY version ASC
        '''
        return self.db.fetch_all(query)
    
    def is_applied(self, version: str) -> bool:
        """Check if migration version is already applied.
        
        Args:
            version: Migration version
            
        Returns:
            True if migration is applied
        """
        query = 'SELECT version FROM schema_migrations WHERE version = ?'
        result = self.db.fetch_one(query, (version,))
        return result is not None
    
    def mark_applied(self, version: str, description: str):
        """Mark migration as applied.
        
        Args:
            version: Migration version
            description: Migration description
        """
        query = '''
            INSERT INTO schema_migrations (version, description)
            VALUES (?, ?)
        '''
        self.db.execute(query, (version, description))
        logger.success(f'Marked migration {version} as applied')
    
    def mark_reverted(self, version: str):
        """Mark migration as reverted (remove from applied).
        
        Args:
            version: Migration version
        """
        query = 'DELETE FROM schema_migrations WHERE version = ?'
        self.db.execute(query, (version,))
        logger.success(f'Marked migration {version} as reverted')
    
    def run_pending(self) -> int:
        """Run all pending migrations.
        
        Returns:
            Number of migrations applied
        """
        all_migrations = self.discover_migrations()
        applied_count = 0
        
        for migration in all_migrations:
            if not self.is_applied(migration.version):
                logger.info(f'Running migration {migration.version}: {migration.description}')
                
                try:
                    migration.upgrade(self.db)
                    self.mark_applied(migration.version, migration.description)
                    applied_count += 1
                    logger.success(f'Migration {migration.version} applied successfully')
                except Exception as e:
                    logger.error(f'Migration {migration.version} failed', exc=e)
                    raise
        
        if applied_count == 0:
            logger.info('No pending migrations to run')
        else:
            logger.success(f'Applied {applied_count} migrations')
        
        return applied_count
    
    def rollback(self, version: str) -> bool:
        """Rollback a specific migration.
        
        Args:
            version: Migration version to rollback
            
        Returns:
            True if rollback successful
        """
        if not self.is_applied(version):
            logger.warning(f'Migration {version} is not applied, cannot rollback')
            return False
        
        # Find migration
        all_migrations = self.discover_migrations()
        migration = None
        for m in all_migrations:
            if m.version == version:
                migration = m
                break
        
        if not migration:
            logger.error(f'Migration {version} not found')
            return False
        
        logger.info(f'Rolling back migration {version}: {migration.description}')
        
        try:
            migration.downgrade(self.db)
            self.mark_reverted(version)
            logger.success(f'Migration {version} rolled back successfully')
            return True
        except Exception as e:
            logger.error(f'Rollback of migration {version} failed', exc=e)
            raise
    
    def rollback_last(self) -> bool:
        """Rollback the last applied migration.
        
        Returns:
            True if rollback successful
        """
        applied = self.get_applied()
        if not applied:
            logger.warning('No migrations to rollback')
            return False
        
        last_migration = applied[-1]
        return self.rollback(last_migration['version'])
    
    def get_status(self) -> Dict[str, List[str]]:
        """Get migration status summary.
        
        Returns:
            Dictionary with 'applied' and 'pending' migration lists
        """
        all_migrations = self.discover_migrations()
        applied_versions = set(m['version'] for m in self.get_applied())
        
        applied = []
        pending = []
        
        for migration in all_migrations:
            if migration.version in applied_versions:
                applied.append(f'{migration.version}: {migration.description}')
            else:
                pending.append(f'{migration.version}: {migration.description}')
        
        return {
            'applied': applied,
            'pending': pending
        }
    
    def print_status(self):
        """Print migration status to console."""
        status = self.get_status()
        
        print('\n📊 Migration Status')
        print('=' * 60)
        
        print(f'\n✅ Applied Migrations ({len(status["applied"])}):')
        if status['applied']:
            for migration in status['applied']:
                print(f'  - {migration}')
        else:
            print('  (none)')
        
        print(f'\n⏳ Pending Migrations ({len(status["pending"])}):')
        if status['pending']:
            for migration in status['pending']:
                print(f'  - {migration}')
        else:
            print('  (none)')
        
        print('\n' + '=' * 60)
