import os
import yaml
import logging

logger = logging.getLogger("Config")

class Config:
    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the singleton instance

        Args:
            config_path: Path to the configuration file
        """
        self.config_path = config_path
        self.categories = [
            "attachments",
            "caching",
            "logging",
            "rate_limit",
            "socketio",
            "adapter"
        ]
        for category in self.categories:
            setattr(self, category, {})

        self.config_path = config_path
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from YAML file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as file:
                    config = yaml.safe_load(file) or {}
                    for category in self.categories:
                        if category in config and isinstance(config[category], dict):
                            setattr(self, category, config[category])
                logger.info("Loaded configuration")
            else:
                logger.error("Config file not found")
        except Exception as e:
            logger.error(f"Error loading config: {str(e)}")

    def get_setting(self, category: str, key: str, default=None):
        """Get a specific setting with support for nested keys (e.g., "test.foo")

        Args:
            category: Configuration category
            key: Setting key
            default: Default value if key not found
        """
        try:
            return getattr(self, category).get(key, default)
        except (KeyError, AttributeError):
            if default is not None:
                return default
            raise ValueError(f"Setting '{key}' not found in configuration")

    def has_setting(self, category: str, key: str) -> bool:
        """Check if a setting exists, with support for nested keys

        Args:
            category: Configuration category
            key: Setting key
        """
        try:
            return key in getattr(self, category)
        except (KeyError, AttributeError):
            return False
