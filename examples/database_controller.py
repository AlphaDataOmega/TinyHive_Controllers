"""TinyHive Database Controller - Multi-backend database integration.

A unified database controller supporting multiple backends:
- SQLite (built-in, no external dependencies)
- PostgreSQL (requires psycopg2)
- MySQL (requires mysql-connector-python)

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

SQLite profile:
{
    "db_type": "sqlite",
    "database": "/path/to/database.db",
    "readonly": false
}

PostgreSQL profile:
{
    "db_type": "postgresql",
    "connection_env": "DATABASE_URL",
    "pool_size": 5,
    "pool_timeout": 30,
    "readonly": false
}

MySQL profile:
{
    "db_type": "mysql",
    "connection_env": "MYSQL_URL",
    "pool_size": 5,
    "pool_timeout": 30,
    "readonly": false
}

Connection string formats:
- PostgreSQL: postgresql://user:password@host:port/database
- MySQL: mysql://user:password@host:port/database

Method IDs:
  controller.database.{profile}.execute_query
  controller.database.{profile}.execute_many
  controller.database.{profile}.fetch_one
  controller.database.{profile}.fetch_all
  controller.database.{profile}.list_tables
  controller.database.{profile}.describe_table

Security Features:
- Parameterized queries only (SQL injection prevention)
- Table name validation with regex
- Optional readonly mode (restricts to SELECT/SHOW/DESCRIBE)
- Connection pooling with thread-safety

Dependencies:
- SQLite: None (standard library)
- PostgreSQL: psycopg2 (pip install psycopg2-binary)
- MySQL: mysql-connector-python (pip install mysql-connector-python)
"""

import json
import logging
import os
import re
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from queue import Queue, Empty, Full
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("tinyhive.controller.database")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"

# Valid table/column name pattern (prevents injection in identifiers)
IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

# Read-only SQL commands
READONLY_COMMANDS = {'SELECT', 'SHOW', 'DESCRIBE', 'DESC', 'EXPLAIN'}


# =============================================================================
# Custom Exceptions
# =============================================================================

class DatabaseError(Exception):
    """Base exception for database operations."""
    pass


class ConnectionError(DatabaseError):
    """Raised when database connection fails."""
    pass


class PoolExhaustedError(DatabaseError):
    """Raised when connection pool is exhausted."""
    pass


class ValidationError(DatabaseError):
    """Raised when input validation fails."""
    pass


class ReadonlyViolationError(DatabaseError):
    """Raised when a write operation is attempted in readonly mode."""
    pass


# =============================================================================
# Connection Pool
# =============================================================================

class ConnectionPool:
    """Thread-safe connection pool for database connections."""

    def __init__(self, create_connection, pool_size: int = 5, timeout: float = 30.0):
        """
        Initialize connection pool.

        Args:
            create_connection: Callable that creates a new database connection
            pool_size: Maximum number of connections in the pool
            timeout: Timeout in seconds when waiting for a connection
        """
        self._create_connection = create_connection
        self._pool_size = pool_size
        self._timeout = timeout
        self._pool: Queue = Queue(maxsize=pool_size)
        self._size = 0
        self._lock = threading.Lock()
        self._closed = False

    def get_connection(self):
        """
        Get a connection from the pool.

        Returns a connection, creating a new one if necessary and pool isn't full.
        Raises PoolExhaustedError if no connection is available within timeout.
        """
        if self._closed:
            raise ConnectionError("Connection pool is closed")

        # Try to get an existing connection
        try:
            conn = self._pool.get(block=False)
            # Test if connection is still valid
            if self._is_connection_valid(conn):
                return conn
            else:
                # Connection is stale, close it and try again
                self._close_connection(conn)
                with self._lock:
                    self._size -= 1
        except Empty:
            pass

        # Try to create a new connection if pool isn't full
        with self._lock:
            if self._size < self._pool_size:
                try:
                    conn = self._create_connection()
                    self._size += 1
                    return conn
                except Exception as e:
                    raise ConnectionError(f"Failed to create connection: {e}")

        # Pool is full, wait for a connection
        try:
            conn = self._pool.get(block=True, timeout=self._timeout)
            if self._is_connection_valid(conn):
                return conn
            else:
                self._close_connection(conn)
                with self._lock:
                    self._size -= 1
                # Try to create a new one
                return self.get_connection()
        except Empty:
            raise PoolExhaustedError(
                f"Connection pool exhausted (size={self._pool_size}, timeout={self._timeout}s)"
            )

    def return_connection(self, conn):
        """Return a connection to the pool."""
        if self._closed:
            self._close_connection(conn)
            return

        try:
            self._pool.put(conn, block=False)
        except Full:
            # Pool is full, close the connection
            self._close_connection(conn)
            with self._lock:
                self._size -= 1

    def _is_connection_valid(self, conn) -> bool:
        """Check if a connection is still valid."""
        try:
            # Try a simple query to test the connection
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            return True
        except Exception:
            return False

    def _close_connection(self, conn):
        """Safely close a connection."""
        try:
            conn.close()
        except Exception:
            pass

    def close_all(self):
        """Close all connections in the pool."""
        self._closed = True
        while True:
            try:
                conn = self._pool.get(block=False)
                self._close_connection(conn)
            except Empty:
                break
        with self._lock:
            self._size = 0


# =============================================================================
# Database Backends
# =============================================================================

class DatabaseBackend(ABC):
    """Abstract base class for database backends."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.readonly = config.get("readonly", False)
        self._pool: Optional[ConnectionPool] = None

    @abstractmethod
    def connect(self):
        """Create a new database connection."""
        pass

    @abstractmethod
    def get_param_placeholder(self) -> str:
        """Get the parameter placeholder style (%s, ?, etc.)."""
        pass

    @abstractmethod
    def list_tables_query(self) -> str:
        """Get the query to list all tables."""
        pass

    @abstractmethod
    def describe_table_query(self, table: str) -> str:
        """Get the query to describe a table's columns."""
        pass

    @abstractmethod
    def format_row(self, cursor, row: tuple) -> Dict[str, Any]:
        """Convert a row tuple to a dictionary using cursor description."""
        pass

    def get_pool(self) -> ConnectionPool:
        """Get or create the connection pool."""
        if self._pool is None:
            pool_size = self.config.get("pool_size", 5)
            pool_timeout = self.config.get("pool_timeout", 30)
            self._pool = ConnectionPool(self.connect, pool_size, pool_timeout)
        return self._pool

    def validate_readonly(self, query: str):
        """Validate that query is allowed in readonly mode."""
        if not self.readonly:
            return

        # Extract the first word (command) from the query
        query_stripped = query.strip().upper()
        first_word = query_stripped.split()[0] if query_stripped else ""

        if first_word not in READONLY_COMMANDS:
            raise ReadonlyViolationError(
                f"Write operations not allowed in readonly mode. "
                f"Command '{first_word}' is not permitted."
            )

    def close(self):
        """Close the connection pool."""
        if self._pool:
            self._pool.close_all()
            self._pool = None


class SQLiteBackend(DatabaseBackend):
    """SQLite database backend."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.database = config.get("database", ":memory:")

    def connect(self):
        """Create a new SQLite connection."""
        conn = sqlite3.connect(
            self.database,
            check_same_thread=False,
            timeout=30.0
        )
        conn.row_factory = sqlite3.Row
        return conn

    def get_param_placeholder(self) -> str:
        return "?"

    def list_tables_query(self) -> str:
        return "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"

    def describe_table_query(self, table: str) -> str:
        # SQLite uses PRAGMA for table info
        return f"PRAGMA table_info({table})"

    def format_row(self, cursor, row: tuple) -> Dict[str, Any]:
        if row is None:
            return None
        if hasattr(row, "keys"):
            # sqlite3.Row object
            return dict(row)
        # Fallback for regular tuple
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def format_table_info(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format SQLite PRAGMA table_info output to standard format."""
        result = []
        for row in rows:
            result.append({
                "column_name": row.get("name"),
                "data_type": row.get("type"),
                "is_nullable": not row.get("notnull", 0),
                "default_value": row.get("dflt_value"),
                "is_primary_key": bool(row.get("pk", 0))
            })
        return result


class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQL database backend using psycopg2."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        try:
            import psycopg2
            import psycopg2.extras
            self.psycopg2 = psycopg2
            self.extras = psycopg2.extras
        except ImportError:
            raise ImportError(
                "PostgreSQL backend requires psycopg2: pip install psycopg2-binary"
            )

        # Get connection string from environment
        env_var = config.get("connection_env", "DATABASE_URL")
        self.connection_string = os.environ.get(env_var)
        if not self.connection_string:
            raise ConnectionError(f"Environment variable '{env_var}' not set")

    def connect(self):
        """Create a new PostgreSQL connection."""
        conn = self.psycopg2.connect(self.connection_string)
        conn.autocommit = False
        return conn

    def get_param_placeholder(self) -> str:
        return "%s"

    def list_tables_query(self) -> str:
        return """
            SELECT table_name as name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """

    def describe_table_query(self, table: str) -> str:
        return f"""
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                WHERE tc.table_name = '{table}'
                    AND tc.constraint_type = 'PRIMARY KEY'
            ) pk ON c.column_name = pk.column_name
            WHERE c.table_name = '{table}'
            ORDER BY c.ordinal_position
        """

    def format_row(self, cursor, row: tuple) -> Dict[str, Any]:
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def format_table_info(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format PostgreSQL column info to standard format."""
        result = []
        for row in rows:
            result.append({
                "column_name": row.get("column_name"),
                "data_type": row.get("data_type"),
                "is_nullable": row.get("is_nullable") == "YES",
                "default_value": row.get("column_default"),
                "is_primary_key": row.get("is_primary_key", False)
            })
        return result


class MySQLBackend(DatabaseBackend):
    """MySQL database backend using mysql-connector-python."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        try:
            import mysql.connector
            self.mysql = mysql.connector
        except ImportError:
            raise ImportError(
                "MySQL backend requires mysql-connector-python: "
                "pip install mysql-connector-python"
            )

        # Get connection string from environment
        env_var = config.get("connection_env", "MYSQL_URL")
        connection_string = os.environ.get(env_var)
        if not connection_string:
            raise ConnectionError(f"Environment variable '{env_var}' not set")

        # Parse connection string: mysql://user:password@host:port/database
        self.connection_params = self._parse_connection_string(connection_string)

    def _parse_connection_string(self, url: str) -> Dict[str, Any]:
        """Parse MySQL connection URL to connection parameters."""
        parsed = urlparse(url)
        params = {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 3306,
            "database": parsed.path.lstrip("/") if parsed.path else None,
        }
        if parsed.username:
            params["user"] = parsed.username
        if parsed.password:
            params["password"] = parsed.password
        return params

    def connect(self):
        """Create a new MySQL connection."""
        conn = self.mysql.connect(**self.connection_params)
        conn.autocommit = False
        return conn

    def get_param_placeholder(self) -> str:
        return "%s"

    def list_tables_query(self) -> str:
        return "SHOW TABLES"

    def describe_table_query(self, table: str) -> str:
        return f"DESCRIBE {table}"

    def format_row(self, cursor, row: tuple) -> Dict[str, Any]:
        if row is None:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

    def format_table_info(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format MySQL DESCRIBE output to standard format."""
        result = []
        for row in rows:
            result.append({
                "column_name": row.get("Field"),
                "data_type": row.get("Type"),
                "is_nullable": row.get("Null") == "YES",
                "default_value": row.get("Default"),
                "is_primary_key": row.get("Key") == "PRI"
            })
        return result


# =============================================================================
# Utility Functions
# =============================================================================

def validate_identifier(name: str) -> bool:
    """Validate a table or column name to prevent SQL injection."""
    if not name:
        return False
    return bool(IDENTIFIER_PATTERN.match(name))


def validate_table_name(table: str):
    """Validate table name and raise ValidationError if invalid."""
    if not validate_identifier(table):
        raise ValidationError(
            f"Invalid table name: '{table}'. "
            f"Table names must match pattern: {IDENTIFIER_PATTERN.pattern}"
        )


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from the profiles directory."""
    profile_path = PROFILES_DIR / f"{name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {name}")

    with open(profile_path) as f:
        return json.load(f)


# Backend cache to reuse connection pools
_backend_cache: Dict[str, DatabaseBackend] = {}
_backend_lock = threading.Lock()


def get_backend(profile_name: str) -> DatabaseBackend:
    """Get a database backend instance for the given profile."""
    with _backend_lock:
        if profile_name in _backend_cache:
            return _backend_cache[profile_name]

        config = load_profile(profile_name)
        db_type = config.get("db_type", "sqlite").lower()

        if db_type == "sqlite":
            backend = SQLiteBackend(config)
        elif db_type == "postgresql" or db_type == "postgres":
            backend = PostgreSQLBackend(config)
        elif db_type == "mysql":
            backend = MySQLBackend(config)
        else:
            raise ValueError(f"Unknown database type: {db_type}")

        _backend_cache[profile_name] = backend
        return backend


# =============================================================================
# Actions
# =============================================================================

def execute_query(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an INSERT, UPDATE, or DELETE query with parameterized values.

    Params:
        query (str): SQL query with parameter placeholders (required)
        values (list): Parameter values for the query (default: [])

    Returns:
        ok (bool): Success status
        rowcount (int): Number of affected rows
        lastrowid (int): Last inserted row ID (if applicable)
    """
    try:
        backend = get_backend(profile_name)
        query = params.get("query")
        values = params.get("values", [])

        if not query:
            return {"ok": False, "error": "query is required"}

        # Validate readonly mode
        backend.validate_readonly(query)

        pool = backend.get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(values))
            conn.commit()

            result = {
                "ok": True,
                "rowcount": cursor.rowcount,
            }

            # Include lastrowid if available
            if hasattr(cursor, "lastrowid") and cursor.lastrowid:
                result["lastrowid"] = cursor.lastrowid

            cursor.close()
            return result

        except Exception as e:
            conn.rollback()
            raise
        finally:
            pool.return_connection(conn)

    except (DatabaseError, ValidationError) as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("execute_query failed")
        return {"ok": False, "error": str(e)}


def execute_many(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a query with multiple parameter sets (batch operation).

    Params:
        query (str): SQL query with parameter placeholders (required)
        values_list (list): List of parameter tuples/lists (required)

    Returns:
        ok (bool): Success status
        rowcount (int): Total number of affected rows
    """
    try:
        backend = get_backend(profile_name)
        query = params.get("query")
        values_list = params.get("values_list", [])

        if not query:
            return {"ok": False, "error": "query is required"}
        if not values_list:
            return {"ok": False, "error": "values_list is required and cannot be empty"}

        # Validate readonly mode
        backend.validate_readonly(query)

        pool = backend.get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.executemany(query, [tuple(v) for v in values_list])
            conn.commit()

            result = {
                "ok": True,
                "rowcount": cursor.rowcount,
            }

            cursor.close()
            return result

        except Exception as e:
            conn.rollback()
            raise
        finally:
            pool.return_connection(conn)

    except (DatabaseError, ValidationError) as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("execute_many failed")
        return {"ok": False, "error": str(e)}


def fetch_one(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a SELECT query and return a single row as a dictionary.

    Params:
        query (str): SQL SELECT query with parameter placeholders (required)
        values (list): Parameter values for the query (default: [])

    Returns:
        ok (bool): Success status
        data (dict): The row as a dictionary, or None if no row found
    """
    try:
        backend = get_backend(profile_name)
        query = params.get("query")
        values = params.get("values", [])

        if not query:
            return {"ok": False, "error": "query is required"}

        # Validate readonly mode
        backend.validate_readonly(query)

        pool = backend.get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(values))
            row = cursor.fetchone()

            data = backend.format_row(cursor, row)
            cursor.close()

            return {"ok": True, "data": data}

        finally:
            pool.return_connection(conn)

    except (DatabaseError, ValidationError) as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("fetch_one failed")
        return {"ok": False, "error": str(e)}


def fetch_all(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a SELECT query and return all rows as a list of dictionaries.

    Params:
        query (str): SQL SELECT query with parameter placeholders (required)
        values (list): Parameter values for the query (default: [])
        limit (int): Maximum number of rows to return (optional)

    Returns:
        ok (bool): Success status
        data (list): List of rows as dictionaries
        count (int): Number of rows returned
    """
    try:
        backend = get_backend(profile_name)
        query = params.get("query")
        values = params.get("values", [])
        limit = params.get("limit")

        if not query:
            return {"ok": False, "error": "query is required"}

        # Validate readonly mode
        backend.validate_readonly(query)

        pool = backend.get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, tuple(values))

            if limit:
                rows = cursor.fetchmany(limit)
            else:
                rows = cursor.fetchall()

            data = [backend.format_row(cursor, row) for row in rows]
            cursor.close()

            return {"ok": True, "data": data, "count": len(data)}

        finally:
            pool.return_connection(conn)

    except (DatabaseError, ValidationError) as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("fetch_all failed")
        return {"ok": False, "error": str(e)}


def list_tables(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all tables in the database.

    Params:
        None required

    Returns:
        ok (bool): Success status
        tables (list): List of table names
        count (int): Number of tables
    """
    try:
        backend = get_backend(profile_name)
        query = backend.list_tables_query()

        pool = backend.get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            # Extract table names (first column of each row)
            tables = []
            for row in rows:
                if hasattr(row, "keys"):
                    # dict-like row
                    tables.append(list(dict(row).values())[0])
                else:
                    tables.append(row[0])

            cursor.close()
            return {"ok": True, "tables": tables, "count": len(tables)}

        finally:
            pool.return_connection(conn)

    except (DatabaseError, ValidationError) as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("list_tables failed")
        return {"ok": False, "error": str(e)}


def describe_table(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get column information for a table.

    Params:
        table (str): Table name to describe (required)

    Returns:
        ok (bool): Success status
        table (str): Table name
        columns (list): List of column info dictionaries containing:
            - column_name (str): Column name
            - data_type (str): Column data type
            - is_nullable (bool): Whether column allows NULL
            - default_value: Default value if any
            - is_primary_key (bool): Whether column is part of primary key
    """
    try:
        backend = get_backend(profile_name)
        table = params.get("table")

        if not table:
            return {"ok": False, "error": "table is required"}

        # Validate table name to prevent SQL injection
        validate_table_name(table)

        query = backend.describe_table_query(table)

        pool = backend.get_pool()
        conn = pool.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            # Convert to list of dicts
            raw_data = [backend.format_row(cursor, row) for row in rows]
            cursor.close()

            # Format to standard structure
            columns = backend.format_table_info(raw_data)

            return {
                "ok": True,
                "table": table,
                "columns": columns,
                "count": len(columns)
            }

        finally:
            pool.return_connection(conn)

    except (DatabaseError, ValidationError) as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("describe_table failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "execute_query": execute_query,
    "execute_many": execute_many,
    "fetch_one": fetch_one,
    "fetch_all": fetch_all,
    "list_tables": list_tables,
    "describe_table": describe_table,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """
    Main dispatch entry point.

    Called by ControllerDispatch with:
        - profile: The profile name from method_id
        - action: The action name from method_id
        - params: Action parameters

    Returns action result dict.
    """
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action: {action}"}

    logger.info(f"Executing database.{profile}.{action}")
    return ACTIONS[action](profile, params)
