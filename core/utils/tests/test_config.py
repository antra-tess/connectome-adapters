import os
import pytest
import yaml
import contextlib
from unittest.mock import patch, mock_open, MagicMock

from core.utils.config import Config

class TestConfig:
    """Tests for the Config class"""

    @pytest.fixture
    def default_config_data(self):
        """Default config data for testing"""
        return {
            "adapter": {
                "token": "test_token",
                "retry_delay": 5
            },
            "rate_limit": {
                "messages_per_second": 10
            },
            "caching": {
                "max_total_messages": 1000,
                "max_age_hours": 24
            },
            "logging": {
                "level": "INFO"
            },
            "socketio": {
                "url": "http://localhost:5000",
                "port": 8080
            }
        }

    @pytest.fixture
    def config_with_file(self, default_config_data):
        """Create a Config instance with a mocked config file"""
        config_yaml = yaml.dump(default_config_data)
        with patch("builtins.open", mock_open(read_data=config_yaml)):
            with patch("os.path.exists", return_value=True):
                yield Config()

    @pytest.fixture
    def config_missing_file(self):
        """Create a Config instance with a missing config file"""
        with patch("os.path.exists", return_value=False):
            with patch("logging.Logger.error") as mock_error:
                yield Config(), mock_error

    @pytest.fixture
    def config_with_exception(self):
        """Create a Config instance that raises an exception when loading"""
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", side_effect=Exception("Test exception")):
                with patch("logging.Logger.error") as mock_error:
                    yield Config(), mock_error

    class TestConfigLoading:
        """Tests for configuration loading functionality"""

        def test_load_config_with_existing_file(self, config_with_file, default_config_data):
            """Test loading configuration from an existing file"""
            config = config_with_file

            # Check that config categories were populated correctly
            for category in ["adapter", "rate_limit", "caching", "logging", "socketio"]:
                assert hasattr(config, category)
                assert getattr(config, category) == default_config_data[category]

        def test_load_config_with_nonexistent_file(self, config_missing_file):
            """Test loading configuration from a non-existent file"""
            _, mock_error = config_missing_file
            mock_error.assert_called_with("Config file not found")

        def test_load_config_with_exception(self, config_with_exception):
            """Test error handling when loading configuration"""
            _, mock_error = config_with_exception
            mock_error.assert_called_with("Error loading config: Test exception")

    class TestConfigAccess:
        """Tests for configuration access methods"""

        @pytest.mark.parametrize("category,key,expected", [
            ("adapter", "token", "test_token"),
            ("adapter", "retry_delay", 5),
            ("logging", "level", "INFO"),
            ("socketio", "port", 8080),
        ])
        def test_get_setting_existing_keys(self, config_with_file, category, key, expected):
            """Test getting settings with existing keys"""
            config = config_with_file
            assert config.get_setting(category, key) == expected

        @pytest.mark.parametrize("category,key,default_value,expected", [
            ("adapter", "non_existent", "default_value", "default_value"),
            ("non_existent_category", "key", 42, 42),
        ])
        def test_get_setting_with_defaults(self, config_with_file, category, key, default_value, expected):
            """Test getting settings with default values"""
            config = config_with_file
            assert config.get_setting(category, key, default_value) == expected

        def test_get_setting_raises_error(self, config_with_file):
            """Test get_setting raises exception when key not found and no default"""
            config = config_with_file
            with pytest.raises(ValueError):
                config.get_setting("non_existent_category", "key")

        @pytest.mark.parametrize("category,key,expected", [
            ("adapter", "token", True),
            ("socketio", "port", True),
            ("adapter", "non_existent", False),
            ("non_existent_category", "key", False),
        ])
        def test_has_setting(self, config_with_file, category, key, expected):
            """Test has_setting method"""
            config = config_with_file
            assert config.has_setting(category, key) is expected
