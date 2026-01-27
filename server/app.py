from flask import Flask, jsonify, request, Response, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import requests
import os
import logging
from logging.handlers import RotatingFileHandler
import sys
from functools import wraps
from collections import deque
import json
import platform

VERSION = '1.0.7'

# ANSI color codes for terminal output
class Colors:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

basedir = os.path.abspath(os.path.dirname(__file__))

# Determine data directory: use /config for Docker, basedir for local development
_docker_config = '/config'
if os.path.isdir(_docker_config):
    data_dir = _docker_config
else:
    data_dir = basedir

# Check Docker path first (/app/frontend_dist), then local dev path (../frontend/dist)
_docker_static = os.path.join(basedir, 'frontend_dist')
_local_static = os.path.join(basedir, '..', 'frontend', 'dist')
if os.path.isdir(_docker_static):
    static_dir = _docker_static
elif os.path.isdir(_local_static):
    static_dir = os.path.abspath(_local_static)
else:
    static_dir = _docker_static  # Fallback, will show clear error if missing

app = Flask(__name__, static_folder=static_dir, static_url_path='')
CORS(app)

# Database configuration - store in data_dir for persistence
db_path = os.path.join(data_dir, 'favarr.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Log directory - store in data_dir for persistence
log_dir = os.path.join(data_dir, 'logs')
log_file = os.path.join(log_dir, 'app.log')
os.makedirs(log_dir, exist_ok=True)

db = SQLAlchemy(app)

# Logging configuration (file + stdout for Docker)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')

if not any(isinstance(h, RotatingFileHandler) for h in app.logger.handlers):
    file_handler = RotatingFileHandler(log_file, maxBytes=2 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

if not any(isinstance(h, logging.StreamHandler) and h.stream == sys.stdout for h in app.logger.handlers):
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(logging.INFO)
    app.logger.addHandler(stdout_handler)

app.logger.setLevel(logging.INFO)

# Startup banner with colors
def print_startup_banner():
    c = Colors
    is_docker = os.path.isdir('/config')
    env_mode = 'Docker' if is_docker else 'Local Development'
    py_version = platform.python_version()

    banner = f"""
{c.CYAN}{c.BOLD}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {c.MAGENTA}███████╗ █████╗ ██╗   ██╗ █████╗ ██████╗ ██████╗ {c.CYAN}        ║
║   {c.MAGENTA}██╔════╝██╔══██╗██║   ██║██╔══██╗██╔══██╗██╔══██╗{c.CYAN}        ║
║   {c.MAGENTA}█████╗  ███████║██║   ██║███████║██████╔╝██████╔╝{c.CYAN}        ║
║   {c.MAGENTA}██╔══╝  ██╔══██║╚██╗ ██╔╝██╔══██║██╔══██╗██╔══██╗{c.CYAN}        ║
║   {c.MAGENTA}██║     ██║  ██║ ╚████╔╝ ██║  ██║██║  ██║██║  ██║{c.CYAN}        ║
║   {c.MAGENTA}╚═╝     ╚═╝  ╚═╝  ╚═══╝  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝{c.CYAN}        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{c.RESET}

{c.GREEN}{c.BOLD}  ▶ Server Starting...{c.RESET}

{c.WHITE}{c.BOLD}  ┌─ Configuration ─────────────────────────────────────────────┐{c.RESET}
{c.WHITE}  │{c.RESET}  {c.YELLOW}Version:{c.RESET}      {c.WHITE}{VERSION}{c.RESET}
{c.WHITE}  │{c.RESET}  {c.YELLOW}Environment:{c.RESET}  {c.WHITE}{env_mode}{c.RESET}
{c.WHITE}  │{c.RESET}  {c.YELLOW}Python:{c.RESET}       {c.WHITE}{py_version}{c.RESET}
{c.WHITE}  └────────────────────────────────────────────────────────────┘{c.RESET}

{c.WHITE}{c.BOLD}  ┌─ Storage ────────────────────────────────────────────────────┐{c.RESET}
{c.WHITE}  │{c.RESET}  {c.BLUE}Data Dir:{c.RESET}    {c.DIM}{data_dir}{c.RESET}
{c.WHITE}  │{c.RESET}  {c.BLUE}Database:{c.RESET}     {c.DIM}{db_path}{c.RESET}
{c.WHITE}  │{c.RESET}  {c.BLUE}Log File:{c.RESET}     {c.DIM}{log_file}{c.RESET}
{c.WHITE}  └────────────────────────────────────────────────────────────┘{c.RESET}
"""
    print(banner, flush=True)

print_startup_banner()


# Database Models
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
            'id': self.id,
            'name': self.name,
            'server_type': self.server_type,
            'url': self.url,
            'enabled': self.enabled,
            'has_credentials': bool(self.api_key or self.token)
        }
        if include_sensitive:
            data['api_key'] = self.api_key
            data['token'] = self.token
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
    servers_by_type = db.Column(db.Text, default='{}')  # JSON string
    users_total = db.Column(db.Integer, default=0)
    users_by_server = db.Column(db.Text, default='[]')  # JSON string
    favorites_total = db.Column(db.Integer, default=0)
    favorites_by_server = db.Column(db.Text, default='[]')  # JSON string
    favorites_by_type = db.Column(db.Text, default='{}')  # JSON string
    collection_status = db.Column(db.String(20), default='completed')  # pending, running, completed, failed
    collection_progress = db.Column(db.Integer, default=0)  # 0-100
    collection_message = db.Column(db.Text, default='')
    duration_seconds = db.Column(db.Float, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'servers_total': self.servers_total,
            'servers_by_type': json.loads(self.servers_by_type) if self.servers_by_type else {},
            'users_total': self.users_total,
            'users_by_server': json.loads(self.users_by_server) if self.users_by_server else [],
            'favorites_total': self.favorites_total,
            'favorites_by_server': json.loads(self.favorites_by_server) if self.favorites_by_server else [],
            'favorites_by_type': json.loads(self.favorites_by_type) if self.favorites_by_type else {},
            'collection_status': self.collection_status,
            'collection_progress': self.collection_progress,
            'collection_message': self.collection_message,
            'duration_seconds': self.duration_seconds
        }


# Global state for tracking running collection task
_stats_collection_task = {
    'running': False,
    'snapshot_id': None
}


# Create tables (wrapped to handle race conditions with multiple workers)
with app.app_context():
    try:
        db.create_all()
        app.logger.info('Database initialized')
    except Exception:
        pass  # Table already exists from another worker


# Server-specific request helpers
def get_server_headers(server):
    """Get headers based on server type."""
    if server.server_type == 'plex':
        return {
            'X-Plex-Token': server.token or '',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    elif server.server_type == 'audiobookshelf':
        return {
            'Authorization': f'Bearer {server.token or ""}',
            'Content-Type': 'application/json'
        }
    else:  # emby or jellyfin
        return {
            'X-Emby-Token': server.api_key or '',
            'Content-Type': 'application/json'
        }


def server_request(server, endpoint, method='GET', params=None, data=None):
    """Make a request to a specific server."""
    url = f"{server.url.rstrip('/')}{endpoint}"
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=get_server_headers(server),
            params=params,
            json=data,
            timeout=30
        )
        response.raise_for_status()
        return response.json() if response.content else {}
    except requests.exceptions.RequestException as e:
        raise Exception(f"Server API error: {str(e)}")


def plex_item_played(item):
    """Determine if a Plex item has been watched."""
    if not isinstance(item, dict):
        return False
    view_count = item.get('viewCount') or item.get('viewcount')
    if isinstance(view_count, (int, float)) and view_count > 0:
        return True
    if item.get('viewedAt') or item.get('lastViewedAt'):
        return True
    return False


def normalize_abs_collections(data):
    """Normalize Audiobookshelf collections response to a list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('collections', 'results', 'items'):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def abs_filter_collections_by_user(collections, user_id, strict=False):
    """Filter collections by user, optionally requiring a match."""
    if not user_id:
        return collections
    user_keys = ('userId', 'ownerId', 'user')
    filtered = [
        c for c in collections
        if any(str(c.get(k)) == str(user_id) for k in user_keys)
    ]
    if filtered or strict:
        return filtered
    return collections


def abs_find_favorites_collection(collections):
    """Find a favorites collection by name."""
    for collection in collections:
        name = (collection.get('name') or '').strip().lower()
        if 'favorite' in name or 'favourite' in name:
            return collection
    return None


def abs_collection_id(collection):
    """Get a collection id from common Audiobookshelf fields."""
    if not isinstance(collection, dict):
        return None
    return collection.get('id') or collection.get('_id') or collection.get('collectionId')


def abs_find_collection_by_id(collections, collection_id):
    """Find a collection by id from a list."""
    for collection in collections:
        if str(abs_collection_id(collection)) == str(collection_id):
            return collection
    return None


def normalize_abs_users(data):
    """Normalize Audiobookshelf users response to a list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('users', 'results', 'items'):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def normalize_abs_items(data):
    """Normalize Audiobookshelf items response to a list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ('items', 'results', 'libraryItems'):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def abs_collection_item_ids(collection):
    """Extract item ids and the preferred update key from a collection."""
    if not isinstance(collection, dict):
        return [], None
    # Audiobookshelf newer API returns "books" array
    if isinstance(collection.get('books'), list):
        books = collection.get('books')
        ids = []
        for book in books:
            if isinstance(book, dict):
                item_id = book.get('id') or book.get('libraryItemId')
                if item_id:
                    ids.append(str(item_id))
            else:
                ids.append(str(book))
        return ids, 'books'
    for key in ('libraryItemIds', 'itemIds'):
        ids = collection.get(key)
        if isinstance(ids, list):
            return [str(i) for i in ids], key
    items = collection.get('items')
    if isinstance(items, list):
        ids = []
        for item in items:
            if isinstance(item, dict):
                item_id = item.get('id') or item.get('libraryItemId')
                if item_id:
                    ids.append(str(item_id))
        return ids, 'libraryItemIds'
    return [], 'libraryItemIds'


def abs_progress_to_played(item):
    """Determine if an Audiobookshelf item is finished."""
    progress = None
    for key in ('progress', 'mediaProgress', 'userMediaProgress'):
        if isinstance(item.get(key), dict):
            progress = item.get(key)
            break
    if not progress and isinstance(item.get('media'), dict):
        for key in ('progress', 'mediaProgress', 'userMediaProgress'):
            if isinstance(item['media'].get(key), dict):
                progress = item['media'].get(key)
                break
    if not progress:
        return False
    if progress.get('isFinished') or progress.get('isComplete') or progress.get('completed') or progress.get('finished'):
        return True
    percent = progress.get('percentComplete')
    if isinstance(percent, (int, float)) and percent >= 1:
        return True
    ratio = progress.get('progress')
    if isinstance(ratio, (int, float)) and ratio >= 1:
        return True
    return False


def abs_map_item(item):
    """Map Audiobookshelf item to shared item shape."""
    return {
        'Id': item.get('id'),
        'Name': item.get('media', {}).get('metadata', {}).get('title', 'Unknown'),
        'Type': 'Audiobook' if item.get('mediaType') == 'book' else 'Podcast',
        'ProductionYear': item.get('media', {}).get('metadata', {}).get('publishedYear'),
        'Overview': item.get('media', {}).get('metadata', {}).get('description', ''),
        'ImageTags': {'Primary': True} if item.get('media', {}).get('coverPath') else {},
        'Tags': item.get('media', {}).get('tags', []),
        'UserData': {
            'Played': abs_progress_to_played(item)
        }
    }


def abs_fetch_items(server, item_ids):
    """Fetch Audiobookshelf items by id."""
    items = []
    for item_id in item_ids:
        try:
            item = server_request(server, f'/api/items/{item_id}')
            if item:
                items.append(abs_map_item(item))
        except Exception:
            continue
    return items


def abs_fetch_collection(server, collection_id):
    """Fetch an Audiobookshelf collection by id."""
    if not collection_id:
        return None
    try:
        detail = server_request(server, f'/api/collections/{collection_id}')
        if isinstance(detail, dict):
            return detail
    except Exception:
        return None
    return None


def abs_get_default_library_id(server):
    """Get first library id as fallback."""
    try:
        libs = server_request(server, '/api/libraries').get('libraries', [])
        if libs:
            return libs[0].get('id')
    except Exception:
        return None
    return None


def abs_get_or_create_favorites_collection(server, user_id, create=False, user_name=None, library_id=None, item_id=None):
    """Get the user's favorites collection, optionally creating it. Optionally include item on creation."""
    collections = normalize_abs_collections(server_request(server, '/api/collections'))
    # Collections are global in ABS; filter softly by user but allow shared matches
    collections = abs_filter_collections_by_user(collections, user_id, strict=False)
    favorite = abs_find_favorites_collection(collections)
    if favorite or not create:
        return favorite
    desired_name = 'Favourites'
    if user_name:
        desired_name = f"{user_name}'s Favourites"
    payload = {
        'name': desired_name,
        'description': f'Favourites for {user_name or user_id} from Favarr',
        'libraryItemIds': []
    }
    # resolve library id
    if not library_id and item_id:
        item_detail = abs_get_item_detail(server, item_id)
        library_id = abs_item_library_id(item_detail)
    if not library_id:
        library_id = abs_get_default_library_id(server)
    if not library_id:
        raise Exception('Audiobookshelf libraryId required to create favourites collection')
    payload['libraryId'] = library_id
    if item_id:
        payload['libraryItemIds'] = [str(item_id)]
    return server_request(server, '/api/collections', method='POST', data=payload)


def abs_get_or_create_named_favourites(server, user_name, library_id=None, item_id=None):
    """Create or find a global ABS collection named 'Favourites – <user>'."""
    if not user_name:
        raise Exception('user_name is required for Audiobookshelf favourites')
    target_name = f"Favourites – {user_name}"
    collections = normalize_abs_collections(server_request(server, '/api/collections'))
    # Try both en dash and hyphen variants
    target_lower = target_name.lower()
    alt_lower = f"favourites - {user_name}".lower()
    for collection in collections:
        name = (collection.get('name') or '').strip().lower()
        if name == target_lower or name == alt_lower:
            return collection
    payload = {
        'name': target_name,
        'description': f'Favourites for {user_name} from Favarr',
        'libraryItemIds': []
    }
    if not library_id and item_id:
        item_detail = abs_get_item_detail(server, item_id)
        library_id = abs_item_library_id(item_detail)
    if not library_id:
        library_id = abs_get_default_library_id(server)
    if not library_id:
        raise Exception('Audiobookshelf libraryId required to create favourites collection')
    payload['libraryId'] = library_id
    if item_id:
        payload['libraryItemIds'] = [str(item_id)]
    return server_request(server, '/api/collections', method='POST', data=payload)


def abs_get_item_detail(server, item_id):
    """Fetch a single ABS item detail."""
    return server_request(server, f'/api/items/{item_id}')


def abs_item_library_id(item_detail):
    """Extract library id from an ABS item detail payload."""
    if not isinstance(item_detail, dict):
        return None
    return (
        item_detail.get('libraryId')
        or item_detail.get('library', {}).get('id')
        or item_detail.get('media', {}).get('libraryId')
    )


def abs_item_collections(item_detail):
    """Extract collection ids from an ABS item."""
    if not isinstance(item_detail, dict):
        return []
    candidates = (
        item_detail.get('collections')
        or item_detail.get('collectionIds')
        or item_detail.get('collectionsIds')
        or item_detail.get('media', {}).get('collections')
    )
    if isinstance(candidates, list):
        return [str(c) for c in candidates if c is not None]
    return []


def abs_add_item_to_collection(server, item_id, collection_id):
    """PATCH item metadata to include a collection (ABS expected way)."""
    detail = abs_get_item_detail(server, item_id)
    existing = abs_item_collections(detail)
    if str(collection_id) in existing:
        return False
    merged = existing + [str(collection_id)]
    server_request(
        server,
        f'/api/items/{item_id}/meta',
        method='PATCH',
        data={'collections': merged}
    )
    return True


def abs_update_collection_items(server, collection_id, item_ids, update_key='libraryItemIds', user_id=None):
    """Update an Audiobookshelf collection with a new item list."""
    payload = {update_key or 'libraryItemIds': item_ids}
    return server_request(server, f'/api/collections/{collection_id}', method='PATCH', data=payload)


def read_log_lines(limit=200):
    """Return the last N log lines from the app log file."""
    if not os.path.exists(log_file):
        return []
    lines = deque(maxlen=limit)
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            lines.append(line.rstrip('\n'))
    return list(lines)


def get_server_or_404(server_id):
    """Get server by ID or return 404."""
    server = Server.query.get(server_id)
    if not server:
        return None
    return server


@app.after_request
def log_request(response):
    """Basic request logging to file for the log viewer."""
    try:
        app.logger.info('%s %s %s', request.method, request.path, response.status_code)
    except Exception:
        pass
    return response


# Health check
@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Return tail of backend logs."""
    limit = int(request.args.get('limit', 200))
    try:
        return jsonify({
            'lines': read_log_lines(limit),
            'limit': limit,
            'path': os.path.basename(log_file)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics across all servers."""
    try:
        servers = Server.query.filter_by(enabled=True).all()
        stats = {
            'servers': {
                'total': len(servers),
                'by_type': {}
            },
            'users': {
                'total': 0,
                'by_server': []
            },
            'favorites': {
                'total': 0,
                'by_server': [],
                'by_type': {}
            }
        }

        # Count servers by type
        for server in servers:
            stype = server.server_type
            stats['servers']['by_type'][stype] = stats['servers']['by_type'].get(stype, 0) + 1

        # Gather user and favorites stats per server
        for server in servers:
            server_stats = {
                'id': server.id,
                'name': server.name,
                'server_type': server.server_type,
                'users': 0,
                'favorites': 0
            }

            try:
                # Get users
                if server.server_type == 'plex':
                    info = server_request(server, '/accounts')
                    accounts = info.get('MediaContainer', {}).get('Account', [])
                    users = [{'Id': str(a.get('id')), 'Name': a.get('name', 'Unknown')} for a in accounts]
                    if not users:
                        users = [{'Id': '1', 'Name': 'Owner'}]
                elif server.server_type == 'audiobookshelf':
                    users = normalize_abs_users(server_request(server, '/api/users'))
                    users = [{'Id': u.get('id'), 'Name': u.get('username', 'Unknown')} for u in users]
                else:
                    users = server_request(server, '/Users')
                    users = [{'Id': u.get('Id'), 'Name': u.get('Name', 'Unknown')} for u in users]

                server_stats['users'] = len(users)
                stats['users']['total'] += len(users)

                # Get favorites count for ALL users on this server
                server_fav_count = 0
                for user in users:
                    user_id = user.get('Id')
                    try:
                        if server.server_type == 'plex':
                            # Plex ratings are per-account, query with user context
                            result = server_request(server, '/library/all', params={'userRating>>': '7'})
                            metadata = result.get('MediaContainer', {}).get('Metadata', [])
                            fav_count = len(metadata)
                        elif server.server_type == 'audiobookshelf':
                            # ABS: look for user's named favorites collection
                            user_name = user.get('Name')
                            collections = normalize_abs_collections(server_request(server, '/api/collections'))
                            fav_count = 0
                            for collection in collections:
                                name = (collection.get('name') or '').lower()
                                if user_name and user_name.lower() in name and ('favorite' in name or 'favourite' in name):
                                    item_ids, _ = abs_collection_item_ids(collection)
                                    fav_count += len(item_ids)
                                    break
                        else:
                            # Emby/Jellyfin: query user's favorites
                            params = {'Filters': 'IsFavorite', 'Recursive': 'true'}
                            favorites = server_request(server, f'/Users/{user_id}/Items', params=params)
                            items = favorites.get('Items', [])
                            fav_count = len(items)

                            # Count by type
                            for item in items:
                                item_type = item.get('Type', 'Other')
                                stats['favorites']['by_type'][item_type] = stats['favorites']['by_type'].get(item_type, 0) + 1

                        server_fav_count += fav_count
                    except Exception:
                        continue

                server_stats['favorites'] = server_fav_count
                stats['favorites']['total'] += server_fav_count

            except Exception as e:
                server_stats['error'] = str(e)

            stats['users']['by_server'].append({
                'id': server.id,
                'name': server.name,
                'count': server_stats['users']
            })
            stats['favorites']['by_server'].append({
                'id': server.id,
                'name': server.name,
                'count': server_stats['favorites']
            })

        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def collect_stats_task(snapshot_id):
    """Background task to collect statistics and update snapshot."""
    import time
    start_time = time.time()

    with app.app_context():
        snapshot = StatsSnapshot.query.get(snapshot_id)
        if not snapshot:
            return

        try:
            snapshot.collection_status = 'running'
            snapshot.collection_progress = 0
            snapshot.collection_message = 'Starting collection...'
            db.session.commit()

            servers = Server.query.filter_by(enabled=True).all()
            total_steps = len(servers) + 1  # +1 for final processing

            stats = {
                'servers': {'total': len(servers), 'by_type': {}},
                'users': {'total': 0, 'by_server': []},
                'favorites': {'total': 0, 'by_server': [], 'by_type': {}}
            }

            # Count servers by type
            for server in servers:
                stype = server.server_type
                stats['servers']['by_type'][stype] = stats['servers']['by_type'].get(stype, 0) + 1

            # Process each server
            for idx, server in enumerate(servers):
                snapshot.collection_message = f'Processing {server.name}...'
                snapshot.collection_progress = int((idx / total_steps) * 100)
                db.session.commit()

                server_users = 0
                server_fav_count = 0

                try:
                    # Get users
                    if server.server_type == 'plex':
                        info = server_request(server, '/accounts')
                        accounts = info.get('MediaContainer', {}).get('Account', [])
                        users = [{'Id': str(a.get('id')), 'Name': a.get('name', 'Unknown')} for a in accounts]
                        if not users:
                            users = [{'Id': '1', 'Name': 'Owner'}]
                    elif server.server_type == 'audiobookshelf':
                        users = normalize_abs_users(server_request(server, '/api/users'))
                        users = [{'Id': u.get('id'), 'Name': u.get('username', 'Unknown')} for u in users]
                    else:
                        users = server_request(server, '/Users')
                        users = [{'Id': u.get('Id'), 'Name': u.get('Name', 'Unknown')} for u in users]

                    server_users = len(users)
                    stats['users']['total'] += server_users

                    # Get favorites for all users
                    for user in users:
                        user_id = user.get('Id')
                        try:
                            if server.server_type == 'plex':
                                result = server_request(server, '/library/all', params={'userRating>>': '7'})
                                metadata = result.get('MediaContainer', {}).get('Metadata', [])
                                fav_count = len(metadata)
                            elif server.server_type == 'audiobookshelf':
                                user_name = user.get('Name')
                                collections = normalize_abs_collections(server_request(server, '/api/collections'))
                                fav_count = 0
                                for collection in collections:
                                    name = (collection.get('name') or '').lower()
                                    if user_name and user_name.lower() in name and ('favorite' in name or 'favourite' in name):
                                        item_ids, _ = abs_collection_item_ids(collection)
                                        fav_count += len(item_ids)
                                        break
                            else:
                                params = {'Filters': 'IsFavorite', 'Recursive': 'true'}
                                favorites = server_request(server, f'/Users/{user_id}/Items', params=params)
                                items = favorites.get('Items', [])
                                fav_count = len(items)
                                for item in items:
                                    item_type = item.get('Type', 'Other')
                                    stats['favorites']['by_type'][item_type] = stats['favorites']['by_type'].get(item_type, 0) + 1

                            server_fav_count += fav_count
                        except Exception:
                            continue

                except Exception as e:
                    app.logger.warning(f'Stats collection error for {server.name}: {e}')

                stats['users']['by_server'].append({'id': server.id, 'name': server.name, 'count': server_users})
                stats['favorites']['by_server'].append({'id': server.id, 'name': server.name, 'count': server_fav_count})
                stats['favorites']['total'] += server_fav_count

            # Save final stats
            snapshot.collection_message = 'Saving results...'
            snapshot.collection_progress = 95
            db.session.commit()

            snapshot.servers_total = stats['servers']['total']
            snapshot.servers_by_type = json.dumps(stats['servers']['by_type'])
            snapshot.users_total = stats['users']['total']
            snapshot.users_by_server = json.dumps(stats['users']['by_server'])
            snapshot.favorites_total = stats['favorites']['total']
            snapshot.favorites_by_server = json.dumps(stats['favorites']['by_server'])
            snapshot.favorites_by_type = json.dumps(stats['favorites']['by_type'])
            snapshot.collection_status = 'completed'
            snapshot.collection_progress = 100
            snapshot.collection_message = 'Collection completed'
            snapshot.duration_seconds = time.time() - start_time
            db.session.commit()

            app.logger.info(f'Stats collection completed in {snapshot.duration_seconds:.1f}s')

        except Exception as e:
            snapshot.collection_status = 'failed'
            snapshot.collection_message = str(e)
            snapshot.duration_seconds = time.time() - start_time
            db.session.commit()
            app.logger.error(f'Stats collection failed: {e}')

        finally:
            _stats_collection_task['running'] = False
            _stats_collection_task['snapshot_id'] = None


@app.route('/api/stats/collect', methods=['POST'])
def start_stats_collection():
    """Start a new statistics collection task."""
    if _stats_collection_task['running']:
        snapshot = StatsSnapshot.query.get(_stats_collection_task['snapshot_id'])
        if snapshot:
            return jsonify({
                'message': 'Collection already in progress',
                'snapshot': snapshot.to_dict()
            }), 409

    # Create new snapshot
    snapshot = StatsSnapshot(
        collection_status='pending',
        collection_progress=0,
        collection_message='Queued for collection'
    )
    db.session.add(snapshot)
    db.session.commit()

    _stats_collection_task['running'] = True
    _stats_collection_task['snapshot_id'] = snapshot.id

    # Start background thread
    import threading
    thread = threading.Thread(target=collect_stats_task, args=(snapshot.id,))
    thread.daemon = True
    thread.start()

    return jsonify({
        'message': 'Collection started',
        'snapshot': snapshot.to_dict()
    }), 202


@app.route('/api/stats/collect/status', methods=['GET'])
def get_collection_status():
    """Get the status of the current or most recent collection."""
    if _stats_collection_task['running'] and _stats_collection_task['snapshot_id']:
        snapshot = StatsSnapshot.query.get(_stats_collection_task['snapshot_id'])
        if snapshot:
            return jsonify({'running': True, 'snapshot': snapshot.to_dict()})

    # Get most recent snapshot
    snapshot = StatsSnapshot.query.order_by(StatsSnapshot.created_at.desc()).first()
    return jsonify({
        'running': False,
        'snapshot': snapshot.to_dict() if snapshot else None
    })


@app.route('/api/stats/snapshots', methods=['GET'])
def list_snapshots():
    """List historical statistics snapshots."""
    limit = int(request.args.get('limit', 30))
    snapshots = StatsSnapshot.query.order_by(StatsSnapshot.created_at.desc()).limit(limit).all()
    return jsonify([s.to_dict() for s in snapshots])


@app.route('/api/stats/snapshots/<int:snapshot_id>', methods=['GET'])
def get_snapshot(snapshot_id):
    """Get a specific snapshot."""
    snapshot = StatsSnapshot.query.get(snapshot_id)
    if not snapshot:
        return jsonify({'error': 'Snapshot not found'}), 404
    return jsonify(snapshot.to_dict())


@app.route('/api/stats/snapshots/<int:snapshot_id>', methods=['DELETE'])
def delete_snapshot(snapshot_id):
    """Delete a snapshot."""
    snapshot = StatsSnapshot.query.get(snapshot_id)
    if not snapshot:
        return jsonify({'error': 'Snapshot not found'}), 404
    db.session.delete(snapshot)
    db.session.commit()
    return jsonify({'message': 'Snapshot deleted'})


# ============ Server Management ============

@app.route('/api/servers', methods=['GET'])
def list_servers():
    """List all configured servers."""
    servers = Server.query.all()
    return jsonify([s.to_dict() for s in servers])


@app.route('/api/servers', methods=['POST'])
def create_server():
    """Add a new server connection."""
    data = request.get_json()

    server = Server(
        name=data.get('name', 'New Server'),
        server_type=data.get('server_type', 'emby'),
        url=data.get('url', ''),
        api_key=data.get('api_key'),
        token=data.get('token'),
        enabled=data.get('enabled', True)
    )

    db.session.add(server)
    db.session.commit()

    return jsonify(server.to_dict()), 201


@app.route('/api/servers/<int:server_id>', methods=['GET'])
def get_server(server_id):
    """Get a specific server."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404
    return jsonify(server.to_dict())


@app.route('/api/servers/<int:server_id>', methods=['PUT'])
def update_server(server_id):
    """Update a server connection."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    data = request.get_json()

    if 'name' in data:
        server.name = data['name']
    if 'server_type' in data:
        server.server_type = data['server_type']
    if 'url' in data:
        server.url = data['url']
    if 'api_key' in data:
        server.api_key = data['api_key']
    if 'token' in data:
        server.token = data['token']
    if 'enabled' in data:
        server.enabled = data['enabled']

    db.session.commit()
    return jsonify(server.to_dict())


@app.route('/api/servers/<int:server_id>', methods=['DELETE'])
def delete_server(server_id):
    """Delete a server connection."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    db.session.delete(server)
    db.session.commit()
    return jsonify({'message': 'Server deleted'})


@app.route('/api/servers/<int:server_id>/test', methods=['POST'])
def test_server(server_id):
    """Test connection to a server."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        info = get_server_info_internal(server)
        return jsonify({'success': True, 'info': info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ============ Server Info ============

def get_server_info_internal(server):
    """Internal function to get server info."""
    if server.server_type == 'plex':
        info = server_request(server, '/')
        return {
            'ServerName': info.get('MediaContainer', {}).get('friendlyName', 'Plex Server'),
            'Version': info.get('MediaContainer', {}).get('version', ''),
            'ServerType': 'plex'
        }
    elif server.server_type == 'audiobookshelf':
        info = server_request(server, '/api/status')
        return {
            'ServerName': info.get('serverSettings', {}).get('name', 'Audiobookshelf'),
            'Version': info.get('version', ''),
            'ServerType': 'audiobookshelf'
        }
    else:  # emby or jellyfin
        info = server_request(server, '/System/Info')
        return {
            'ServerName': info.get('ServerName', server.server_type.title()),
            'Version': info.get('Version', ''),
            'ServerType': server.server_type
        }


@app.route('/api/servers/<int:server_id>/info', methods=['GET'])
def get_server_info(server_id):
    """Get server information."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        info = get_server_info_internal(server)
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ Users ============

@app.route('/api/servers/<int:server_id>/users', methods=['GET'])
def get_users(server_id):
    """Get list of users from a server."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        if server.server_type == 'plex':
            info = server_request(server, '/accounts')
            accounts = info.get('MediaContainer', {}).get('Account', [])
            users = [{'Id': str(a.get('id')), 'Name': a.get('name', 'Unknown')} for a in accounts]
            if not users:
                users = [{'Id': '1', 'Name': 'Owner'}]
            return jsonify(users)
        elif server.server_type == 'audiobookshelf':
            users = normalize_abs_users(server_request(server, '/api/users'))
            return jsonify([{'Id': u.get('id'), 'Name': u.get('username', 'Unknown')} for u in users])
        else:  # emby or jellyfin
            users = server_request(server, '/Users')
            return jsonify(users)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ Audiobookshelf Collections ============

@app.route('/api/servers/<int:server_id>/users/<user_id>/collections', methods=['GET', 'POST'])
def abs_collections(server_id, user_id):
    """List or create Audiobookshelf collections for a user."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404
    if server.server_type != 'audiobookshelf':
        return jsonify({'error': 'Collections are only supported for Audiobookshelf'}), 400

    try:
        if request.method == 'GET':
            collections = normalize_abs_collections(server_request(server, '/api/collections'))
            collections = abs_filter_collections_by_user(collections, user_id, strict=False)
            if not collections:
                try:
                    collections = normalize_abs_collections(
                        server_request(server, f'/api/users/{user_id}/collections')
                    )
                except Exception:
                    collections = []
            result = []
            for collection in collections:
                collection_id = abs_collection_id(collection)
                item_ids, _ = abs_collection_item_ids(collection)
                if collection_id and not item_ids:
                    try:
                        detail = server_request(server, f'/api/collections/{collection_id}')
                        if isinstance(detail, dict):
                            item_ids, _ = abs_collection_item_ids(detail)
                    except Exception:
                        pass
                result.append({
                    'Id': collection_id,
                    'Name': collection.get('name', 'Unknown'),
                    'Description': collection.get('description', ''),
                    'ItemCount': len(item_ids),
                    'UserId': collection.get('userId') or collection.get('ownerId') or collection.get('user')
                })
            return jsonify(result)

        data = request.get_json() or {}
        payload = {
            'name': data.get('name', 'Favourites'),
            'description': data.get('description', ''),
            'libraryItemIds': data.get('libraryItemIds', [])
        }
        if user_id:
            payload['userId'] = user_id
        collection = server_request(server, '/api/collections', method='POST', data=payload)
        return jsonify({
            'Id': abs_collection_id(collection),
            'Name': collection.get('name', payload['name']),
            'Description': collection.get('description', payload.get('description', '')),
            'ItemCount': len(payload.get('libraryItemIds', [])),
            'UserId': collection.get('userId') or payload.get('userId')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/servers/<int:server_id>/users/<user_id>/collections/<collection_id>/items', methods=['GET'])
def abs_collection_items(server_id, user_id, collection_id):
    """Get items for an Audiobookshelf collection."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404
    if server.server_type != 'audiobookshelf':
        return jsonify({'error': 'Collections are only supported for Audiobookshelf'}), 400

    try:
        collections = normalize_abs_collections(server_request(server, '/api/collections'))
        collection = abs_find_collection_by_id(collections, collection_id)
        if not collection:
            collection = abs_fetch_collection(server, collection_id)
        if not collection:
            return jsonify({'error': 'Collection not found'}), 404
        if user_id:
            filtered = abs_filter_collections_by_user([collection], user_id, strict=False)
            if filtered:
                collection = filtered[0]
        item_ids, _ = abs_collection_item_ids(collection)
        if not item_ids:
            detail = abs_fetch_collection(server, collection_id)
            if detail:
                item_ids, _ = abs_collection_item_ids(detail)
        items = []
        if not item_ids:
            try:
                payload = normalize_abs_items(server_request(server, f'/api/collections/{collection_id}/items'))
                if payload:
                    if isinstance(payload[0], dict) and payload[0].get('media'):
                        items = [abs_map_item(i) for i in payload]
                    else:
                        ids = [
                            str(i.get('id') or i.get('libraryItemId'))
                            for i in payload if isinstance(i, dict)
                        ]
                        item_ids = [i for i in ids if i]
            except Exception:
                pass
        if not items:
            items = abs_fetch_items(server, item_ids)
        return jsonify({'Items': items, 'TotalRecordCount': len(items)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/servers/<int:server_id>/users/<user_id>/collections/<collection_id>/items/<item_id>', methods=['POST', 'DELETE'])
def abs_collection_item_update(server_id, user_id, collection_id, item_id):
    """Add or remove an item from an Audiobookshelf collection."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404
    if server.server_type != 'audiobookshelf':
        return jsonify({'error': 'Collections are only supported for Audiobookshelf'}), 400

    try:
        collections = normalize_abs_collections(server_request(server, '/api/collections'))
        collection = abs_find_collection_by_id(collections, collection_id)
        if not collection:
            collection = abs_fetch_collection(server, collection_id)
        if not collection:
            return jsonify({'error': 'Collection not found'}), 404
        if user_id:
            filtered = abs_filter_collections_by_user([collection], user_id, strict=False)
            if filtered:
                collection = filtered[0]
        item_ids, update_key = abs_collection_item_ids(collection)
        if request.method == 'POST':
            if str(item_id) not in item_ids:
                item_ids.append(str(item_id))
        else:
            item_ids = [i for i in item_ids if str(i) != str(item_id)]
        abs_update_collection_items(
            server,
            abs_collection_id(collection),
            item_ids,
            update_key=update_key,
            user_id=user_id
        )
        return jsonify({'message': 'Collection updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ Libraries ============

@app.route('/api/servers/<int:server_id>/libraries', methods=['GET'])
def get_libraries(server_id):
    """Get media libraries from a server."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        if server.server_type == 'plex':
            result = server_request(server, '/library/sections')
            sections = result.get('MediaContainer', {}).get('Directory', [])
            libraries = [{
                'ItemId': str(s.get('key')),
                'Name': s.get('title', 'Unknown'),
                'CollectionType': s.get('type', '')
            } for s in sections]
            return jsonify(libraries)
        elif server.server_type == 'audiobookshelf':
            result = server_request(server, '/api/libraries')
            libraries = result.get('libraries', [])
            return jsonify([{
                'ItemId': lib.get('id'),
                'Name': lib.get('name', 'Unknown'),
                'CollectionType': lib.get('mediaType', 'book')
            } for lib in libraries])
        else:  # emby or jellyfin
            libraries = server_request(server, '/Library/VirtualFolders')
            return jsonify(libraries)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ Items ============

@app.route('/api/servers/<int:server_id>/items', methods=['GET'])
def get_items(server_id):
    """Get media items from a server."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    parent_id = request.args.get('parent_id')
    search = request.args.get('search')
    limit_param = request.args.get('limit')
    default_limit = 3500 if server.server_type == 'audiobookshelf' else 50
    limit = int(limit_param) if limit_param is not None else default_limit

    try:
        if server.server_type == 'plex':
            disallowed_types = {'episode', 'program', 'person'}
            if search:
                # Limit to movies and shows only
                result = server_request(
                    server,
                    '/search',
                    params={'query': search, 'type': '1,2'}  # 1=movie, 2=show
                )
                metadata = result.get('MediaContainer', {}).get('Metadata', [])
            elif parent_id:
                result = server_request(server, f'/library/sections/{parent_id}/all')
                metadata = result.get('MediaContainer', {}).get('Metadata', [])
            else:
                result = server_request(server, '/library/recentlyAdded')
                metadata = result.get('MediaContainer', {}).get('Metadata', [])

            filtered = [m for m in metadata if (m.get('type') or '').lower() not in disallowed_types]

            items = [{
                'Id': str(item.get('ratingKey')),
                'Name': item.get('title', 'Unknown'),
                'Type': item.get('type', '').title(),
                'ProductionYear': item.get('year'),
                'Overview': item.get('summary', ''),
                'ImageTags': {'Primary': item.get('thumb')} if item.get('thumb') else {},
                'UserData': {
                    'Played': plex_item_played(item)
                }
            } for item in filtered[:limit]]
            return jsonify({'Items': items, 'TotalRecordCount': len(items)})

        elif server.server_type == 'audiobookshelf':
            if search:
                # For search, scan all libraries to avoid missing items
                libs = server_request(server, '/api/libraries').get('libraries', [])
                abs_items = []
                for lib in libs:
                    lib_items = server_request(
                        server,
                        f'/api/libraries/{lib["id"]}/items',
                        params={'limit': limit}
                    )
                    abs_items.extend(lib_items.get('results', []))
                abs_items = [
                    i for i in abs_items
                    if search.lower() in i.get('media', {}).get('metadata', {}).get('title', '').lower()
                ]
            elif parent_id:
                result = server_request(
                    server,
                    f'/api/libraries/{parent_id}/items',
                    params={'limit': limit}
                )
                abs_items = result.get('results', [])
            else:
                # Get items from all libraries
                libs = server_request(server, '/api/libraries').get('libraries', [])
                abs_items = []
                for lib in libs:
                    lib_items = server_request(
                        server,
                        f'/api/libraries/{lib["id"]}/items',
                        params={'limit': limit}
                    )
                    abs_items.extend(lib_items.get('results', []))

            if search:
                abs_items = [i for i in abs_items if search.lower() in i.get('media', {}).get('metadata', {}).get('title', '').lower()]

            items = [abs_map_item(item) for item in abs_items[:limit]]
            return jsonify({'Items': items, 'TotalRecordCount': len(items)})

        else:  # emby or jellyfin
            include_types = request.args.get('types', 'Movie,Series,AudioBook')
            params = {
                'Recursive': request.args.get('recursive', 'true'),
                'IncludeItemTypes': include_types,
                'StartIndex': request.args.get('start', 0),
                'Limit': limit,
                'SortBy': request.args.get('sort_by', 'SortName'),
                'SortOrder': request.args.get('sort_order', 'Ascending'),
                'Fields': 'Overview,Path,MediaSources,UserData'
            }
            if parent_id:
                params['ParentId'] = parent_id
            if search:
                params['SearchTerm'] = search

            items = server_request(server, '/Items', params=params)
            return jsonify(items)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ Favorites ============

@app.route('/api/servers/<int:server_id>/users/<user_id>/favorites', methods=['GET'])
def get_favorites(server_id, user_id):
    """Get user's favorites from a server."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        if server.server_type == 'plex':
            # Plex uses ratings for favorites
            result = server_request(server, '/library/all', params={'userRating>>': '7'})
            metadata = result.get('MediaContainer', {}).get('Metadata', [])
            items = [{
                'Id': str(item.get('ratingKey')),
                'Name': item.get('title', 'Unknown'),
                'Type': item.get('type', '').title(),
                'ProductionYear': item.get('year'),
                'ImageTags': {'Primary': item.get('thumb')} if item.get('thumb') else {},
                'UserData': {
                    'Played': plex_item_played(item)
                }
            } for item in metadata]
            return jsonify({'Items': items, 'TotalRecordCount': len(items)})

        elif server.server_type == 'audiobookshelf':
            # Use favorites collection per user (fallback to tag-based if needed)
            try:
                favorite = abs_get_or_create_favorites_collection(server, user_id, create=False)
                if not favorite:
                    return jsonify({'Items': [], 'TotalRecordCount': 0})
                item_ids, _ = abs_collection_item_ids(favorite)
                items = abs_fetch_items(server, item_ids)
                return jsonify({'Items': items, 'TotalRecordCount': len(items)})
            except Exception:
                libs = server_request(server, '/api/libraries').get('libraries', [])
                items = []
                for lib in libs:
                    lib_items = server_request(server, f'/api/libraries/{lib["id"]}/items')
                    for item in lib_items.get('results', []):
                        tags = item.get('media', {}).get('tags', [])
                        if 'Favorite' in tags or 'favorite' in tags:
                            items.append(abs_map_item(item))
                return jsonify({'Items': items, 'TotalRecordCount': len(items)})

        else:  # emby or jellyfin
            params = {
                'Filters': 'IsFavorite',
                'Recursive': 'true',
                'Fields': 'Overview,Path,UserData'
            }
            favorites = server_request(server, f'/Users/{user_id}/Items', params=params)
            return jsonify(favorites)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/servers/<int:server_id>/users/<user_id>/favorites/<item_id>', methods=['POST'])
def add_favorite(server_id, user_id, item_id):
    """Add item to favorites."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        if server.server_type == 'plex':
            server_request(server, '/:/rate', method='PUT',
                          params={'key': item_id, 'identifier': 'com.plexapp.plugins.library', 'rating': 10})
            return jsonify({'message': 'Added to favorites'})

        elif server.server_type == 'audiobookshelf':
            # Add item to user's favorites collection (fallback to tag-based if needed)
            try:
                payload = request.get_json(silent=True) or {}
                user_name = request.args.get('user_name') or payload.get('user_name')
                favorite = abs_get_or_create_favorites_collection(
                    server,
                    user_id,
                    create=True,
                    user_name=user_name,
                    item_id=item_id
                )
                if not favorite:
                    raise Exception('Favorites collection not available')
                collection_id = abs_collection_id(favorite)
                if not collection_id:
                    raise Exception('Favorites collection id missing')
                added = abs_add_item_to_collection(server, item_id, collection_id)
                return jsonify({'message': 'Added to favorites', 'added': added})
            except Exception:
                item = server_request(server, f'/api/items/{item_id}')
                current_tags = item.get('media', {}).get('tags', [])
                if 'Favorite' not in current_tags:
                    current_tags.append('Favorite')
                    server_request(server, f'/api/items/{item_id}/media', method='PATCH',
                                  data={'tags': current_tags})
                return jsonify({'message': 'Added to favorites'})

        else:  # emby or jellyfin
            server_request(server, f'/Users/{user_id}/FavoriteItems/{item_id}', method='POST')
            return jsonify({'message': 'Added to favorites'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/servers/<int:server_id>/abs/favourites', methods=['POST'])
def abs_add_favourite(server_id):
    """Add an Audiobookshelf item to a user-named favourites collection, creating it if missing."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404
    if server.server_type != 'audiobookshelf':
        return jsonify({'error': 'This endpoint is only for Audiobookshelf'}), 400

    payload = request.get_json(silent=True) or {}
    user_name = payload.get('user_name')
    item_id = payload.get('item_id') or payload.get('libraryItemId') or payload.get('Id')
    if not user_name or not item_id:
        return jsonify({'error': 'user_name and item_id are required'}), 400

    try:
        # Fetch item to determine its library for ABS
        collection = abs_get_or_create_named_favourites(server, user_name, item_id=item_id)
        if not collection:
            return jsonify({'error': 'Unable to create favourites collection'}), 500
        collection_id = abs_collection_id(collection)
        if not collection_id:
            return jsonify({'error': 'Unable to determine favourites collection id'}), 500
        added = abs_add_item_to_collection(server, item_id, collection_id)
        return jsonify({
            'success': True,
            'collectionId': collection_id,
            'added': added
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/servers/<int:server_id>/users/<user_id>/favorites/<item_id>', methods=['DELETE'])
def remove_favorite(server_id, user_id, item_id):
    """Remove item from favorites."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    try:
        if server.server_type == 'plex':
            server_request(server, '/:/rate', method='PUT',
                          params={'key': item_id, 'identifier': 'com.plexapp.plugins.library', 'rating': -1})
            return jsonify({'message': 'Removed from favorites'})

        elif server.server_type == 'audiobookshelf':
            # Remove item from user's favorites collection (fallback to tag-based if needed)
            try:
                favorite = abs_get_or_create_favorites_collection(server, user_id, create=False)
                if not favorite:
                    return jsonify({'message': 'Removed from favorites'})
                item_ids, update_key = abs_collection_item_ids(favorite)
                next_ids = [i for i in item_ids if str(i) != str(item_id)]
                collection_id = abs_collection_id(favorite)
                if not collection_id:
                    raise Exception('Favorites collection id missing')
                abs_update_collection_items(
                    server,
                    collection_id,
                    next_ids,
                    update_key=update_key,
                    user_id=user_id
                )
                return jsonify({'message': 'Removed from favorites'})
            except Exception:
                item = server_request(server, f'/api/items/{item_id}')
                current_tags = item.get('media', {}).get('tags', [])
                current_tags = [t for t in current_tags if t.lower() != 'favorite']
                server_request(server, f'/api/items/{item_id}/media', method='PATCH',
                              data={'tags': current_tags})
                return jsonify({'message': 'Removed from favorites'})

        else:  # emby or jellyfin
            server_request(server, f'/Users/{user_id}/FavoriteItems/{item_id}', method='DELETE')
            return jsonify({'message': 'Removed from favorites'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ Recent Items ============

@app.route('/api/servers/<int:server_id>/recent', methods=['GET'])
def get_recent(server_id):
    """Get recently added items from a server."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    limit = int(request.args.get('limit', 20))
    parent_id = request.args.get('parent_id')

    try:
        if server.server_type == 'plex':
            if parent_id:
                result = server_request(
                    server,
                    f'/library/sections/{parent_id}/recentlyAdded',
                    params={'X-Plex-Container-Size': limit}
                )
            else:
                result = server_request(server, '/library/recentlyAdded',
                                       params={'X-Plex-Container-Size': limit})
            metadata = result.get('MediaContainer', {}).get('Metadata', [])
            items = [{
                'Id': str(item.get('ratingKey')),
                'Name': item.get('title', 'Unknown'),
                'Type': item.get('type', '').title(),
                'ProductionYear': item.get('year'),
                'ImageTags': {'Primary': item.get('thumb')} if item.get('thumb') else {},
                'UserData': {
                    'Played': plex_item_played(item)
                }
            } for item in metadata]
            return jsonify({'Items': items, 'TotalRecordCount': len(items)})

        elif server.server_type == 'audiobookshelf':
            libs = server_request(server, '/api/libraries').get('libraries', [])
            if parent_id:
                libs = [lib for lib in libs if str(lib.get('id')) == str(parent_id)]
            items = []
            for lib in libs:
                lib_items = server_request(server, f'/api/libraries/{lib["id"]}/items',
                                          params={'sort': 'addedAt', 'desc': 1, 'limit': limit})
                for item in lib_items.get('results', []):
                    items.append(abs_map_item(item))
            return jsonify({'Items': items[:limit], 'TotalRecordCount': len(items)})

        else:  # emby or jellyfin
            params = {
                'Limit': limit,
                'Recursive': 'true',
                'SortBy': 'DateCreated',
                'SortOrder': 'Descending',
                'Fields': 'Overview,Path,UserData'
            }
            if parent_id:
                params['ParentId'] = parent_id
            recent = server_request(server, '/Items', params=params)
            return jsonify(recent)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ Image Proxy ============

@app.route('/api/servers/<int:server_id>/image/<item_id>', methods=['GET'])
def get_image(server_id, item_id):
    """Proxy for item images."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    image_type = request.args.get('type', 'Primary')
    max_width = request.args.get('maxWidth', 300)

    try:
        if server.server_type == 'plex':
            thumb_path = request.args.get('thumb', '')
            if thumb_path:
                url = f"{server.url.rstrip('/')}{thumb_path}"
            else:
                url = f"{server.url.rstrip('/')}/library/metadata/{item_id}/thumb"
            params = {'X-Plex-Token': server.token, 'width': max_width}

        elif server.server_type == 'audiobookshelf':
            url = f"{server.url.rstrip('/')}/api/items/{item_id}/cover"
            params = {'width': max_width}

        else:  # emby or jellyfin
            url = f"{server.url.rstrip('/')}/Items/{item_id}/Images/{image_type}"
            params = {'maxWidth': max_width, 'api_key': server.api_key}

        response = requests.get(url, params=params, headers=get_server_headers(server), timeout=30)
        response.raise_for_status()

        return Response(
            response.content,
            mimetype=response.headers.get('Content-Type', 'image/jpeg')
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============ Frontend SPA ============
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if static_dir and os.path.exists(os.path.join(static_dir, path)) and path != '':
        return send_from_directory(static_dir, path)
    return send_from_directory(static_dir, 'index.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
