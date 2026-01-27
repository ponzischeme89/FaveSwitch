from flask import Flask, jsonify, request, Response, send_from_directory
from flask_cors import CORS
import requests
import os
import logging
from logging.handlers import RotatingFileHandler
import sys
from functools import wraps
from collections import deque
import json
import platform

from favarr.extensions import db
from favarr.models import AppSettings, Server, StatsSnapshot
from favarr.services import (
    abs_add_item_to_collection,
    abs_collection_id,
    abs_collection_item_ids,
    abs_fetch_collection,
    abs_fetch_items,
    abs_filter_collections_by_user,
    abs_find_collection_by_id,
    abs_find_favorites_collection,
    abs_get_default_library_id,
    abs_get_item_detail,
    abs_get_or_create_favorites_collection,
    abs_get_or_create_named_favourites,
    abs_item_collections,
    abs_item_library_id,
    abs_map_item,
    abs_progress_to_played,
    get_server_headers,
    normalize_abs_collections,
    normalize_abs_items,
    normalize_abs_users,
    plex_item_played,
    server_request,
)

VERSION = '1.1.0'

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

db.init_app(app)

# Suppress noisy HTTP access logs from werkzeug and gunicorn
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('gunicorn.access').setLevel(logging.WARNING)

# Logging configuration (file + stdout for Docker)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

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


# Helper for structured logging
def log_service(service, message, level='info'):
    """Log with service prefix for better filtering."""
    full_msg = f'[{service}] {message}'
    getattr(app.logger, level)(full_msg)

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
    try:
        print(banner, flush=True)
    except UnicodeEncodeError:
        # Windows consoles can choke on box-drawing chars; fall back to ASCII-safe.
        print(banner.encode('ascii', 'ignore').decode(), flush=True)

print_startup_banner()

# Log startup to file
log_service('System', f'Favarr started - Data directory: {data_dir}')


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


def check_integrations_on_startup():
    """Log connectivity status for all configured servers on startup."""
    with app.app_context():
        servers = Server.query.filter_by(enabled=True).all()
        if not servers:
            log_service('Integrations', 'No servers configured; skipping connectivity check')
            return

        for server in servers:
            try:
                info = get_server_info_internal(server)
                version = info.get('Version') or info.get('ServerName') or 'unknown'
                log_service(
                    'Integrations',
                    f'Connected to "{server.name}" ({server.server_type}) - {version}'
                )
            except Exception as e:
                log_service(
                    'Integrations',
                    f'Failed to connect to "{server.name}" ({server.server_type}): {e}',
                    level='warning'
                )


# Run an initial connectivity check when the app starts
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

    log_service('Server', f'Created {server.server_type} server "{server.name}" (id={server.id})')
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
    log_service('Server', f'Updated server "{server.name}" (id={server_id})')
    return jsonify(server.to_dict())


@app.route('/api/servers/<int:server_id>', methods=['DELETE'])
def delete_server(server_id):
    """Delete a server connection."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    server_name = server.name
    db.session.delete(server)
    db.session.commit()
    log_service('Server', f'Deleted server "{server_name}" (id={server_id})')
    return jsonify({'message': 'Server deleted'})


@app.route('/api/servers/<int:server_id>/test', methods=['POST'])
def test_server(server_id):
    """Test connection to a server."""
    server = get_server_or_404(server_id)
    if not server:
        return jsonify({'error': 'Server not found'}), 404

    log_service('Server', f'Testing connection to "{server.name}" ({server.server_type})')

    try:
        info = get_server_info_internal(server)
        log_service('Server', f'Connection test passed for "{server.name}"')
        return jsonify({'success': True, 'info': info})
    except Exception as e:
        log_service('Server', f'Connection test failed for "{server.name}": {e}', level='warning')
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
        # Use /api/libraries to verify API key works (authenticated endpoint)
        libs = server_request(server, '/api/libraries')
        lib_count = len(libs.get('libraries', []))
        return {
            'ServerName': 'Audiobookshelf',
            'Version': f'{lib_count} libraries',
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


# Run an initial connectivity check when the app starts (after helpers are defined)
check_integrations_on_startup()


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

    if search:
        log_service('Search', f'Query "{search}" on {server.server_type} (server_id={server_id})')

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
            if search:
                log_service('Search', f'Found {len(items)} results for "{search}" on plex')
            return jsonify({'Items': items, 'TotalRecordCount': len(items)})

        elif server.server_type == 'audiobookshelf':
            libs = server_request(server, '/api/libraries').get('libraries', [])
            abs_items = []

            if search:
                # Use native search endpoint for each library
                for lib in libs:
                    try:
                        search_result = server_request(
                            server,
                            f'/api/libraries/{lib["id"]}/search',
                            params={'q': search, 'limit': limit}
                        )
                        # Search returns different structure: book/podcast results
                        for key in ('book', 'podcast', 'audiobook', 'libraryItems'):
                            if key in search_result and isinstance(search_result[key], list):
                                abs_items.extend(search_result[key])
                        # Also check for direct results array
                        if isinstance(search_result, list):
                            abs_items.extend(search_result)
                    except Exception as e:
                        log_service('Search', f'ABS library {lib.get("id")} search failed: {e}', level='warning')
            elif parent_id:
                result = server_request(
                    server,
                    f'/api/libraries/{parent_id}/items',
                    params={'limit': limit}
                )
                abs_items = result.get('results', [])
            else:
                # Get items from all libraries
                for lib in libs:
                    lib_items = server_request(
                        server,
                        f'/api/libraries/{lib["id"]}/items',
                        params={'limit': limit}
                    )
                    abs_items.extend(lib_items.get('results', []))

            # Handle search results which may have nested libraryItem
            normalized_items = []
            for item in abs_items[:limit]:
                if 'libraryItem' in item:
                    normalized_items.append(item['libraryItem'])
                else:
                    normalized_items.append(item)

            items = [abs_map_item(item) for item in normalized_items]
            if search:
                log_service('Search', f'Found {len(items)} results for "{search}" on audiobookshelf')
            return jsonify({'Items': items, 'TotalRecordCount': len(items)})

        else:  # emby or jellyfin
            include_types = request.args.get('types', 'Movie,Series,AudioBook')
            params = {
                'Recursive': request.args.get('recursive', 'true'),
                'IncludeItemTypes': include_types,
                'StartIndex': request.args.get('start', 0),
                'Limit': limit * 3 if search else limit,  # Fetch more to filter
                'SortBy': request.args.get('sort_by', 'SortName'),
                'SortOrder': request.args.get('sort_order', 'Ascending'),
                'Fields': 'Overview,Path,MediaSources,UserData'
            }
            if parent_id:
                params['ParentId'] = parent_id
            if search:
                params['SearchTerm'] = search

            result = server_request(server, '/Items', params=params)

            # Emby/Jellyfin does fuzzy word matching - filter to items containing search term
            if search and 'Items' in result:
                search_lower = search.lower()
                filtered_items = [
                    item for item in result['Items']
                    if search_lower in (item.get('Name', '') or '').lower()
                ]
                result['Items'] = filtered_items[:limit]
                result['TotalRecordCount'] = len(filtered_items)
                log_service('Search', f'Found {len(filtered_items)} results for "{search}" on {server.server_type}')

            return jsonify(result)

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

    log_service('Favorites', f'Adding item {item_id} for user {user_id} on {server.server_type}')

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

    log_service('Favorites', f'Removing item {item_id} for user {user_id} on {server.server_type}')

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
