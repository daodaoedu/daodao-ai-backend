from config import get_settings
from db.interface_db import BaseDatabase
from db.postgresql import PostgreSQLDatabase


def make_database() -> BaseDatabase:
    """Factory function to create a database instance.

    :returns: An instance of the database
    :rtype: BaseDatabase
    """
    # Get settings from centralized config
    settings = get_settings()

 
    database = PostgreSQLDatabase(config=settings.postgresql)
    database.startup()
    return database