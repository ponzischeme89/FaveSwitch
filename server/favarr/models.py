import json

from .extensions import db


class Server(db.Model):
    """Model for storing multiple server connections."""

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server_type = db.Column(db.String(20), nullable=False)  # emby, jellyfin, plex, audiobookshelf
    url = db.Column(db.String(500), nullable=False)
    api_key = db.Column(db.String(500), nullable=True)  # For Emby/Jellyfin/Audiobookshelf
    token = db.Column(db.String(500), nullable=True)  # For Plex
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    def to_dict(self, include_sensitive=False):
        data = {
            "id": self.id,
            "name": self.name,
            "server_type": self.server_type,
            "url": self.url,
            "enabled": self.enabled,
            "has_credentials": bool(self.api_key or self.token),
        }
        if include_sensitive:
            data["api_key"] = self.api_key
            data["token"] = self.token
        return data


class AppSettings(db.Model):
    """Model for storing application settings."""

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

    @staticmethod
    def get(key, default=None):
        setting = AppSettings.query.filter_by(key=key).first()
        return setting.value if setting else default

    @staticmethod
    def set(key, value):
        setting = AppSettings.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = AppSettings(key=key, value=value)
            db.session.add(setting)
        db.session.commit()
        return setting


class StatsSnapshot(db.Model):
    """Model for storing historical statistics snapshots."""

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    servers_total = db.Column(db.Integer, default=0)
    servers_by_type = db.Column(db.Text, default="{}")  # JSON string
    users_total = db.Column(db.Integer, default=0)
    users_by_server = db.Column(db.Text, default="[]")  # JSON string
    favorites_total = db.Column(db.Integer, default=0)
    favorites_by_server = db.Column(db.Text, default="[]")  # JSON string
    favorites_by_type = db.Column(db.Text, default="{}")  # JSON string
    collection_status = db.Column(db.String(20), default="completed")  # pending, running, completed, failed
    collection_progress = db.Column(db.Integer, default=0)  # 0-100
    collection_message = db.Column(db.Text, default="")
    duration_seconds = db.Column(db.Float, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "servers_total": self.servers_total,
            "servers_by_type": json.loads(self.servers_by_type) if self.servers_by_type else {},
            "users_total": self.users_total,
            "users_by_server": json.loads(self.users_by_server) if self.users_by_server else [],
            "favorites_total": self.favorites_total,
            "favorites_by_server": json.loads(self.favorites_by_server) if self.favorites_by_server else [],
            "favorites_by_type": json.loads(self.favorites_by_type) if self.favorites_by_type else {},
            "collection_status": self.collection_status,
            "collection_progress": self.collection_progress,
            "collection_message": self.collection_message,
            "duration_seconds": self.duration_seconds,
        }
