import redis
from config import REDIS_URL
import pickle


class Redis(object):
    """
    redis資料庫操作
    """

    @staticmethod
    def _get_r():
        r = redis.from_url(REDIS_URL)
        return r

    @classmethod
    def write_dict(self, key, value, expire=None):
        expire_in_seconds = expire or 60000

        r = self._get_r()
        r.set(key, pickle.dumps(value), ex=expire_in_seconds)

    @classmethod
    def read_dict(self, key):
        r = self._get_r()
        data = r.get(key)
        if data is None:
            return None
        return pickle.loads(data)

    @classmethod
    def delete(self, *names):

        r = self._get_r()
        r.delete(*names)

    @classmethod
    def expire(self, name, expire=None):
        expire_in_seconds = expire or 60000

        r = self._get_r()
        r.expire(name, expire_in_seconds)