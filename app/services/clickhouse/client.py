from clickhouse_driver import Client
from config import ClickHouseSettings


class ClickHouseClient:
    def __init__(self, settings: ClickHouseSettings):
        self.settings = settings
        self.client = Client(
            host=self.settings.host,
            port=settings.port,
            user=settings.user,
            password=settings.password,
            database=settings.database,
        )
