import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, event
from alembic import context

config = context.config

# Build DB URL from environment variables (same vars used by asyncpg in main.py)
user = os.getenv("POSTGRES_USER", "postgres")
password = os.getenv("POSTGRES_PASSWORD", "")
if not password:
    try:
        password = open("/run/secrets/db_password").read().strip()
    except FileNotFoundError:
        pass
database = os.getenv("POSTGRES_DB", "cdmx_crime")
host = os.getenv("POSTGRES_HOST", "postgres")
schema = os.getenv("POSTGRES_SCHEMA", user)

url = f"postgresql+psycopg2://{user}:{password}@{host}/{database}"
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # raw SQL migrations, no ORM


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    @event.listens_for(connectable, "connect")
    def set_search_path(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute(f"SET search_path TO {schema}, public")
        cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=schema,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
