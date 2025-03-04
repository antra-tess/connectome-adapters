import os
import pytest
import yaml
import contextlib
from unittest.mock import patch, mock_open, MagicMock
from config import Config

class TestConfig:

    @pytest.fixture(autouse=True)
    def reset_config_singleton(self):
        """Reset the Config singleton before and after each test"""
        Config._instance = None
        yield
        Config._instance = None

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
    def mock_config_file(self, default_config_data):
        """Mock the config file with default data"""
        config_yaml = yaml.dump(default_config_data)
        with patch("builtins.open", mock_open(read_data=config_yaml)):
            with patch("os.path.exists", return_value=True):
                yield

    @pytest.fixture
    def mock_missing_config_file(self):
        """Mock a missing config file"""
        with patch("os.path.exists", return_value=False):
            yield

    @pytest.fixture
    def mock_config_with_exception(self):
        """Mock a config file that raises an exception when opened"""
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", side_effect=Exception("Test exception")):
                yield

    class TestSingletonPattern:
        """Tests for the singleton pattern implementation"""

        def test_singleton_instances_are_same(self, mock_config_file):
            """Test that multiple Config instances reference the same object"""
            config1 = Config()
            config2 = Config()
            config3 = Config.get_instance()

            assert config1 is config2
            assert config1 is config3

        def test_get_instance_creates_if_none(self, mock_config_file):
            """Test get_instance creates a new instance if none exists"""
            config = Config.get_instance()

            assert config is not None
            assert isinstance(config, Config)

    class TestConfigLoading:
        """Tests for configuration loading functionality"""

        def test_load_config_with_existing_file(self, mock_config_file, default_config_data):
            """Test loading configuration from an existing file"""
            config = Config()

            # Check that config categories were populated correctly
            for category in ["adapter", "rate_limit", "caching", "logging", "socketio"]:
                assert getattr(config, category) == default_config_data[category]

        def test_load_config_with_nonexistent_file(self, mock_missing_config_file):
            """Test loading configuration from a non-existent file"""
            with patch("logging.Logger.error") as mock_error:
                _ = Config()
                mock_error.assert_called_with("Config file not found")

        def test_load_config_with_exception(self, mock_config_with_exception):
            """Test error handling when loading configuration"""
            with patch("logging.Logger.error") as mock_error:
                _ = Config()
                mock_error.assert_called_with("Error loading config: Test exception")

    class TestConfigAccess:
        """Tests for configuration access methods"""

        @pytest.mark.parametrize("category,key,expected", [
            ("adapter", "token", "test_token"),
            ("adapter", "retry_delay", 5),
            ("logging", "level", "INFO"),
            ("socketio", "port", 8080),
        ])
        def test_get_setting_existing_keys(self, mock_config_file, category, key, expected):
            """Test getting settings with existing keys"""
            config = Config()
            assert config.get_setting(category, key) == expected

        @pytest.mark.parametrize("category,key,default_value,expected", [
            ("adapter", "non_existent", "default_value", "default_value"),
            ("non_existent_category", "key", 42, 42),
        ])
        def test_get_setting_with_defaults(self, mock_config_file, category, key, default_value, expected):
            """Test getting settings with default values"""
            config = Config()
            assert config.get_setting(category, key, default_value) == expected

        def test_get_setting_raises_error(self, mock_config_file):
            """Test get_setting raises exception when key not found and no default"""
            config = Config()
            with pytest.raises(ValueError):
                config.get_setting("non_existent_category", "key")

        @pytest.mark.parametrize("category,key,expected", [
            ("adapter", "token", True),
            ("socketio", "port", True),
            ("adapter", "non_existent", False),
            ("non_existent_category", "key", False),
        ])
        def test_has_setting(self, mock_config_file, category, key, expected):
            """Test has_setting method"""
            config = Config()
            assert config.has_setting(category, key) is expected
