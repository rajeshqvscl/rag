"""
Config Version Control System
Manages versioning for prompts, analysis configs, and system settings
"""
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class ConfigVersion:
    """Single version of a configuration"""
    version: str
    created_at: datetime
    created_by: str = "system"
    config_data: Dict = None
    changelog: str = ""

    def to_dict(self) -> Dict:
        return {
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "config_data": self.config_data or {},
            "changelog": self.changelog
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ConfigVersion':
        return cls(
            version=data["version"],
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data.get("created_by", "system"),
            config_data=data.get("config_data", {}),
            changelog=data.get("changelog", "")
        )


class ConfigRegistry:
    """
    Manages versioned configurations for prompts and system settings
    """

    def __init__(self, config_dir: str = None):
        self.config_dir = Path(config_dir or "app/config")
        self.versions: Dict[str, Dict[str, ConfigVersion]] = {}
        self._load_configs()

    def _load_configs(self):
        """Load all configurations from disk"""
        if not self.config_dir.exists():
            return

        for category_dir in self.config_dir.iterdir():
            if category_dir.is_dir():
                category = category_dir.name
                self.versions[category] = {}

                for version_file in category_dir.glob("v*.json"):
                    try:
                        with open(version_file, 'r') as f:
                            data = json.load(f)
                            version = ConfigVersion.from_dict(data)
                            self.versions[category][version.version] = version
                    except Exception:
                        continue

    def register(self, category: str, version: str, config_data: Dict,
                 changelog: str = "", created_by: str = "system") -> ConfigVersion:
        """Register a new configuration version"""

        if category not in self.versions:
            self.versions[category] = {}

        new_version = ConfigVersion(
            version=version,
            created_at=datetime.now(),
            created_by=created_by,
            config_data=config_data,
            changelog=changelog
        )

        self.versions[category][version] = new_version

        category_dir = self.config_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)

        with open(category_dir / f"{version}.json", 'w') as f:
            json.dump(new_version.to_dict(), f, indent=2)

        return new_version

    def get(self, category: str, version: str = None) -> Optional[ConfigVersion]:
        """Get a specific version or current version"""

        if category not in self.versions:
            return None

        if version is None:
            versions = self.versions[category]
            if not versions:
                return None
            return list(versions.values())[-1]

        return self.versions[category].get(version)

    def get_current(self, category: str) -> Optional[ConfigVersion]:
        """Get current (latest) version of a category"""
        return self.get(category)

    def list_versions(self, category: str) -> List[str]:
        """List all versions for a category"""
        if category not in self.versions:
            return []
        return list(self.versions[category].keys())

    def rollback(self, category: str, version: str) -> bool:
        """Rollback to a previous version"""
        target = self.get(category, version)
        if not target:
            return False

        current = self.get_current(category)
        if current:
            current.config_data = target.config_data.copy()

        return True


class PromptRegistry:
    """Specialized registry for LLM prompts"""

    DEFAULT_PROMPTS = {
        "extraction": {
            "v1": {
                "system": "You are an institutional-grade investment analyst.",
                "user_template": "Extract data from: {context}",
                "schema": {}
            },
            "v2": {
                "system": "You are an expert investment analyst analyzing pitch decks.",
                "user_template": "Extract structured data from the following context:\n\n{context}\n\nProvide JSON output.",
                "schema": {}
            }
        },
        "email": {
            "v1": {
                "template": "Hi,\n\n{intro}\n\n{body}\n\n{cta}\n\nBest regards",
                "tone": "professional"
            },
            "v2": {
                "template": "Hi {name},\n\n{intro}\n\n{body}\n\n{cta}\n\nBest regards",
                "tone": "investor-focused"
            }
        },
        "analysis": {
            "v1": {
                "sections": ["financials", "market", "team", "competition"],
                "weights": {"revenue": 30, "growth": 25, "team": 20, "market": 25}
            },
            "v2": {
                "sections": ["financials", "market", "team", "competition", "funding"],
                "weights": {"revenue": 25, "growth": 25, "team": 20, "market": 15, "funding": 15}
            }
        }
    }

    def __init__(self):
        self.prompts = self.DEFAULT_PROMPTS.copy()
        self.current_versions = {cat: list(versions.keys())[-1] for cat, versions in self.prompts.items()}

    def get_prompt(self, category: str, version: str = None) -> Optional[Dict]:
        """Get prompt configuration"""
        if category not in self.prompts:
            return None

        if version is None:
            version = self.current_versions.get(category, "v1")

        return self.prompts[category].get(version)

    def update_prompt(self, category: str, version: str, prompt_data: Dict) -> bool:
        """Update or add a prompt version"""
        if category not in self.prompts:
            self.prompts[category] = {}

        self.prompts[category][version] = prompt_data
        self.current_versions[category] = version
        return True

    def list_prompt_versions(self, category: str) -> List[str]:
        """List available versions for a prompt category"""
        if category not in self.prompts:
            return []
        return list(self.prompts[category].keys())


class ConfigAuditLog:
    """Tracks changes to configurations"""

    def __init__(self):
        self.log: List[Dict] = []

    def log_change(self, category: str, version: str, action: str,
                   user: str = "system", details: str = ""):
        """Log a configuration change"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "version": version,
            "action": action,
            "user": user,
            "details": details
        }
        self.log.append(entry)

    def get_recent(self, limit: int = 10) -> List[Dict]:
        """Get recent changes"""
        return self.log[-limit:]

    def get_by_category(self, category: str) -> List[Dict]:
        """Get changes for a specific category"""
        return [e for e in self.log if e["category"] == category]


# Global instances
CONFIG_REGISTRY = ConfigRegistry()
PROMPT_REGISTRY = PromptRegistry()
AUDIT_LOG = ConfigAuditLog()


def get_config(category: str, version: str = None) -> Optional[Dict]:
    """Get configuration"""
    cfg = CONFIG_REGISTRY.get(category, version)
    return cfg.config_data if cfg else None


def update_config(category: str, version: str, config_data: Dict,
                  changelog: str = "", user: str = "system") -> Dict:
    """Update configuration and log the change"""
    CONFIG_REGISTRY.register(category, version, config_data, changelog, user)
    AUDIT_LOG.log_change(category, version, "update", user, changelog)
    return {"success": True, "category": category, "version": version}


def get_prompt(category: str, version: str = None) -> Optional[Dict]:
    """Get prompt configuration"""
    return PROMPT_REGISTRY.get_prompt(category, version)


def update_prompt(category: str, version: str, prompt_data: Dict,
                 user: str = "system") -> Dict:
    """Update prompt and log the change"""
    PROMPT_REGISTRY.update_prompt(category, version, prompt_data)
    AUDIT_LOG.log_change(f"prompt_{category}", version, "update", user)
    return {"success": True, "category": category, "version": version}


def get_system_config() -> Dict:
    """Get current system configuration summary"""
    return {
        "prompt_versions": PROMPT_REGISTRY.current_versions,
        "config_categories": list(CONFIG_REGISTRY.versions.keys()),
        "recent_changes": AUDIT_LOG.get_recent(5),
        "system_info": {
            "version": "1.0",
            "environment": os.getenv("ENVIRONMENT", "production")
        }
    }