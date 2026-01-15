"""Migration manager for database schema versioning."""
import os
import re
import importlib.util
from typing import List, Dict, Optional
from src.database.db_manager import DBManager
from src.utils.logger import get_logger

logger = get_logger('MigrationManager')


class Migration:
    """Represents a single database migration."""

    def __init__(self, version: str, description: str, file_path: str):
        self.version = version
        self.description = description
        self.file_path = file_path
        self.module = None

    def load(self):
        if self.module is None:
            spec = importlib.util.spec_from_file_location(
                f'migration_{self.version}',
                self.file_path
            )
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        return self.module

    def upgrade(self, db_manager: DBManager):
        module = self.load()
        if not hasattr(module, 'upgrade'):
            raise AttributeError(f'Migration {self.version} missing upgrade()')
        module.upgrade(db_manager)

    def downgrade(self, db_manager: DBManager):
        module = self.load()
        if not hasattr(module, 'downgrade'):
            raise AttributeError(f'Migration {self.version} missing downgrade()')
        module.downgrade(db_manager)


class MigrationManager:
    """Manages database migrations."""

    def __init__(self, db_manager: DBManager, migrations_dir: Optional[str] = None):
        self.db = db_manager

        if migrations_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.migrations_dir = os.path.join(current_dir, 'versions')
        else:
            self.migrations_dir = migrations_dir

        logger.info(f'Migration manager initialized: {self.migrations_dir}')
        self._ensure_migrations_table()

    def _ensure_migrations_table(self):
        """Create schema_migrations table if it doesn't exist (DB-safe)."""
        if self.db.database_type == 'postgresql':
            query = """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id SERIAL PRIMARY KEY,
                    version TEXT NOT NULL UNIQUE,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """
        else:
            query = """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL UNIQUE,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """
        self.db.execute(query)
        logger.debug('schema_migrations table ensured')

    def discover_migrations(self) -> List[Migration]:
        migrations = []

        if not os.path.exists(self.migrations_dir):
            return migrations

        pattern = re.compile(r'^(\d{3})_(.+)\.py$')

        for filename in os.listdir(self.migrations_dir):
            match = pattern.match(filename)
            if match:
                version = match.group(1)
                description = match.group(2).replace('_', ' ')
                file_path = os.path.join(self.migrations_dir, filename)
                migrations.append(Migration(version, description, file_path))

        migrations.sort(key=lambda m: m.version)
        return migrations

    def get_applied(self) -> List[Dict[str, str]]:
        query = """
            SELECT version, description, applied_at
            FROM schema_migrations
            ORDER BY version
        """
        return self.db.fetch_all(query)

    def is_applied(self, version: str) -> bool:
        query = "SELECT version FROM schema_migrations WHERE version = ?"
        return self.db.fetch_one(query, (version,)) is not None

    def mark_applied(self, version: str, description: str):
        query = "INSERT INTO schema_migrations (version, description) VALUES (?, ?)"
        self.db.execute(query, (version, description))

    def run_pending(self) -> int:
        applied_versions = {m['version'] for m in self.get_applied()}
        count = 0

        for migration in self.discover_migrations():
            if migration.version not in applied_versions:
                logger.info(f'Applying migration {migration.version}')
                migration.upgrade(self.db)
                self.mark_applied(migration.version, migration.description)
                count += 1

        return count

    def get_status(self) -> Dict[str, List[str]]:
        all_migrations = self.discover_migrations()
        applied_versions = {m['version'] for m in self.get_applied()}

        applied = []
        pending = []

        for m in all_migrations:
            label = f'{m.version}: {m.description}'
            if m.version in applied_versions:
                applied.append(label)
            else:
                pending.append(label)

        return {'applied': applied, 'pending': pending}

    def print_status(self):
        status = self.get_status()

        print('\n📊 Migration Status')
        print('=' * 50)

        print('\n✅ Applied:')
        for m in status['applied'] or ['(none)']:
            print(f'  - {m}')

        print('\n⏳ Pending:')
        for m in status['pending'] or ['(none)']:
            print(f'  - {m}')

        print('=' * 50)
