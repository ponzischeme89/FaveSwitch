<div align="center">
  <img src="docs/logo_faveswitch.png" alt="FaveSwitch logo" width="60%">
  <p><em>A favorites (favourites if your American) manager for Jellyfin, Emby, PleX and Audiobookshelf)</em></p>
</div>

FaveSwitch is a self-hosted favourites manager for Plex, Jellyfin, Emby, and Audiobookshelf that lets you edit any user's favorites from a single interface. It eliminates the need to log into multiple apps or remote-into family members' devices just to curate their libraries.

## Features
- God-mode Access: Switch between any user on your servers to prune or add favorites instantly.
- Cross-Platform: One interface for your entire media stack (Plex, Jellyfin, Emby, and ABS).
- Fix Messy Libraries: Bulk-manage users who "heart" everything or help less tech-savvy users curate their collections.
- ABS Collections: Basic support for Audiobookshelf user-named collections with tag fallback (e.g. Matt's Favourites)
- Stats: Total user favourite counts, favourites by media type, and server breakdowns.

> [!TIP]
> **Help support FaveSwitch and give our repo a star!**  
> If you enjoy FaveSwitch and want to help support me, please consider starring my repo. Thank you so much
> Discord support here:   
> 👉 https://discord.gg/jycHt7jDJF

## Screenshots

<p align="center">
  <img src="docs/screenshots/FaveSwitch_screen1.png" alt="FaveSwitch screenshot 1" width="80%"> <br>
  <i>
  Favourites screen: Quickly switch between users</i>
</p>
<p align="center">
  <img src="docs/screenshots/FaveSwitch_screen2.png" alt="FaveSwitch screenshot 2" width="80%">
  <br> <i>
  Audiobookshelf support</i>
</p>
<p align="center">
  <img src="docs/screenshots/FaveSwitch_screen3.png" alt="FaveSwitch screenshot 3" width="80%"><br>
  </i>
  Settings page</i>
</p>

## Why FaveSwitch?

Most media servers make it impossible to manage things from the user's perspective without actually being them. FaveSwitch fixes the administrative gaps that Plex, Jellyfin, and Emby ignore:

- Remote Curation: Stop walking your parents through "how to heart a movie" over the phone. Just do it for them from your own dashboard.
- The "Clean Up" Tool: Fix the user who accidentally favorites 400 items, or prep a "Must Watch" list for a friend without needing their password.
- Platform Agnostic: If you run a split stack (e.g., Plex for movies, JF for anime), you can manage everything in one tab instead of flipping between three different web UIs.
- Zero Overhead: It’s a tiny tool that does one thing: it lets you act as a "Favorites Admin" across your entire server list.

## Intergrations
| Server | Auth expected | Notes |
| --- | --- | --- |
| Emby | API key | Standard favourites endpoints |
| Jellyfin | API key | Standard favourites endpoints |
| Plex | X-Plex Token | Uses ratings API to flag favourites |
| Audiobookshelf | JWT token | Creates/updates a per-user favourites collection; falls back to tags if needed |

## Quick start (Docker / Compose)
Single image published to GHCR: `ghcr.io/ponzischeme89/FaveSwitch:latest`

```bash
docker run -d \
  --name FaveSwitch \
  -p 5050:5000 \
  -e TZ=Etc/UTC \
  ghcr.io/ponzischeme89/FaveSwitch:latest
```

Or with Compose:

```yaml
version: "3.9"
services:
  FaveSwitch:
    image: ghcr.io/ponzischeme89/FaveSwitch:latest
    container_name: FaveSwitch
    restart: unless-stopped
    environment:
      - TZ=Etc/UTC
    ports:
      - "5050:5000"
    # volumes:
    #   - ./data:/config   # optional: when persistence is wired up
```

## Using FaveSwitch
- Go to Settings → “Add Integration” and choose your server type. Supply URL + API key/token. Use “Test Connection” to verify.
- Pick a server from the sidebar, then select a user from the header dropdown.
- Browse Libraries or Recent to add/remove favourites, or use the Favourites view to prune quickly.
- Unified Search searches every integration and can warm its cache for faster suggestions.
- Logs tab shows the tail of `server/logs/app.log` for quick debugging.

## Limitations
- Audiobookshelf collections are global, not user-scoped, so “per-user favourites” are simulated by naming conventions and best-effort filtering; collisions are possible on shared servers.
- ABS collection APIs lack atomic add/remove; updates replace the whole item list, so concurrent edits can race. FaveSwitch mitigates but can’t fully prevent this.
- ABS metadata is inconsistent across versions; fallback to tag-based favourites is used when collections break, which means favourites may appear as tags instead of lists.

## Roadmap
- Auth
- API - so you can see stats inside Homepage, other external services
- Export/import server integrations.

## Support
- Give our project a star! This really helps
- Check out my other projects (Sublogue, Shelfarr)