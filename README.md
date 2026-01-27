# Favarr

<div align="center">
  <img src="docs/images/favarr_logo_v7.png" alt="Favarr logo" height="350">
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

## Quick start (Docker Compose)
Images are expected to be published to GHCR via the release workflow under:
- Frontend: `ghcr.io/ponzischeme89/favarr-frontend:latest`
- API: `ghcr.io/ponzischeme89/favarr-api:latest`

```yaml
version: "3.9"
services:
  api:
    image: ghcr.io/ponzischeme89/favarr-api:latest   # built from /server
    container_name: favarr-api
    restart: unless-stopped
    environment:
      - TZ=Etc/UTC
    ports:
      - "5050:5000"        # host:container

  frontend:
    image: ghcr.io/ponzischeme89/favarr-frontend:latest   # built from /frontend
    container_name: favarr-frontend
    restart: unless-stopped
    depends_on:
      - api
    environment:
      - API_PROXY_TARGET=http://api:5000   # nginx forwards /api to backend
      - PORT=4173
    ports:
      - "4173:4173"        # host:container
```

Notes
- If you’re iterating locally, you can swap `image:` for `build:` using the same service names to build from your working copy.
- Backend SQLite DB and logs currently live inside the container; add a volume to persist them once a `/config` path is wired up in the image.

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
