"""
測試 config.py 環境變數載入行為

注意：get_settings() 使用 @lru_cache，測試若需要不同 env 設定，
須在 fixture 或測試結尾呼叫 get_settings.cache_clear() 清除快取。
"""

import pytest
from unittest.mock import patch


class TestRedisSettingsTTL:
    def test_ttl_hours_with_valid_int(self):
        """REDIS_TTL_HOURS=3 應被正確解析為整數 3"""
        with patch.dict("os.environ", {"REDIS_TTL_HOURS": "3"}, clear=False):
            from importlib import reload
            import src.config as config_module

            reload(config_module)
            settings = config_module.RedisSettings()
            assert settings.ttl_hours == 3

    def test_ttl_hours_fallback_when_old_key_used(self):
        """舊鍵名 REDIS_TTL_HOUR（無 S）不被辨識，應回傳預設值 6"""
        env = {"REDIS_TTL_HOURS": ""}  # 清空正確鍵
        with patch.dict("os.environ", env, clear=False):
            from importlib import reload
            import src.config as config_module

            reload(config_module)
            settings = config_module.RedisSettings()
            assert settings.ttl_hours == 6

    def test_ttl_hours_default_is_int(self):
        """預設值應為整數型別"""
        from src.config import RedisSettings

        settings = RedisSettings()
        assert isinstance(settings.ttl_hours, int)
