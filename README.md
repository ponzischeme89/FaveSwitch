# Favarr

<div align="center">
  <img src="docs/images/favarr_logo_v7.png" alt="Favarr logo">
  <p><em>Multi-server favourites wrangler for Emby, Jellyfin, Plex, and Audiobookshelf — because Dad still can’t find the star button.</em></p>
</div>

Favarr is a tiny multi-server favourite-fixer that lets you edit anyone’s favourites across Emby/Jellyfin/Plex/Audiobookshelf from one place. No juggling apps, no remote-controlling your dad’s TV, no sighing dramatically.

Use it to clean up messy libraries, curate playlists for the olds, or fix that one user who somehow hearts every item they scroll past.

## Features
- Connect multiple servers and store credentials locally (SQLite).
- Switch between users on a server and manage their favourites with one click.
- Unified search with fast suggestions across every connected server.
- Library, Recent and Favourites views share the same lightweight grid UI.
- Audiobookshelf support with user‑named “Favourites” collections (with tag fallback).

## Intergrations
| Server | Auth expected | Notes |
| --- | --- | --- |
| Emby | API key | Standard favourites endpoints |
| Jellyfin | API key | Standard favourites endpoints |
| Plex | X-Plex Token | Uses ratings API to flag favourites |
| Audiobookshelf | JWT token | Creates/updates a per-user favourites collection; falls back to tags if needed |

## Quick start (local dev)
Prereqs: Python 3.10+, Node 18+, npm.

1) Backend (Flask, port 5000)  
```
cd server
python -m venv .venv
. .venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
python app.py
```

2) Frontend (Svelte + Vite, port 3000 with `/api` proxy to 5000)  
```
cd frontend
npm install
npm run dev
```
Open http://localhost:3000. The proxy sends API calls to the Flask server, so both processes need to be running.

## Quick start (Docker)
Docker image name is `ghcr.io/ponzischeme89/favarr:latest` (placeholder tag; update if renamed).

```
docker run -d \
  --name favarr \
  -p 5050:5000 \
  -e TZ=Etc/UTC \
  -v /path/to/config:/config \   # optional future bind for sqlite/logs
  ghcr.io/ponzischeme89/favarr:latest
```

### Docker Compose
```yaml
version: "3.9"
services:
  favarr:
    image: ghcr.io/ponzischeme89/favarr:latest
    container_name: favarr
    restart: unless-stopped
    ports:
      - "5050:5000"
    environment:
      - TZ=Etc/UTC
    volumes:
      - ./data:/config   # future: sqlite db + logs
```

## Using Favarr
- Go to Settings → “Add Integration” and choose your server type. Supply URL + API key/token. Use “Test Connection” to verify.
- Pick a server from the sidebar, then select a user from the header dropdown.
- Browse Libraries or Recent to add/remove favourites, or use the Favourites view to prune quickly.
- Unified Search searches every integration and can warm its cache for faster suggestions.
- Logs tab shows the tail of `server/logs/app.log` for quick debugging.

## Limitations
- Audiobookshelf collections are global, not user-scoped, so “per-user favourites” are simulated by naming conventions and best-effort filtering; collisions are possible on shared servers.
- ABS collection APIs lack atomic add/remove; updates replace the whole item list, so concurrent edits can race. Favarr mitigates but can’t fully prevent this.
- ABS metadata is inconsistent across versions; fallback to tag-based favourites is used when collections break, which means favourites may appear as tags instead of lists.
- No offline mode—server APIs must be reachable to read or change favourites.

## Production notes
- `frontend/npm run build` outputs static assets to `frontend/dist`. Serve them with any web server and reverse‑proxy `/api` to the Flask app on port 5000.
- Flask stores data in `server/favarr.db` (SQLite) alongside log files in `server/logs/`.
- Docker volumes above assume `/config` will be used for persistent db/logs once the container packaging is wired up.

## Roadmap (short list)
- Optional auth for the web UI.
- Docker image + compose example.
- Export/import server integrations.
