from typing import Dict, List, Optional

from config import Settings
from logger import AppLogger
from qdrant_client import QdrantClient as Client
from qdrant_client import models
from qdrant_client.http.exceptions import UnexpectedResponse

logger = AppLogger(__name__).get_logger()


class QdrantClient:
    def __init__(self, settings: Settings):
        self.settings = settings

        self.client = Client(
            url=settings.qdrant_url,
            timeout=60,
        )

    def create_collection(self):
        try:
            self.client.create_collection(
                collection_name=self.settings.collection_name,
                vectors_config=models.VectorParams(
                    size=768, distance=models.Distance.COSINE
                ),
            )
            logger.info(
                f"✅ Qdrant collection `{self.settings.collection_name}` created successfully."
            )
        except UnexpectedResponse as e:
            # 如果已存在就當作正常，不丟錯
            if "already exists" in str(e):
                logger.info(
                    f"ℹ️ Qdrant collection `{self.settings.collection_name}` already exists, skipping creation."
                )
            else:
                raise  # 其他 UnexpectedResponse 直接丟出

    def get_collections(self):
        return self.client.get_collections()

    def search_native(
        self,
        size: int = 10,
        query_vector: Optional[List[float]] = None,
    ):
        return self.client.search(
            collection_name=self.settings.collection_name,
            query_vector=query_vector,
            limit=size,
            with_payload=True,
        )

    def search(
        self,
        query: str,
        query_vector: Optional[List[float]] = None,
        size: int = 10,
        categories: Optional[List[str]] = None,
        min_score: float = 0.25,
    ) -> tuple[List[Dict], List[str], str, List[str], int]:
        # Implements Qdrant search logic
        return
