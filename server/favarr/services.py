import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


def get_server_headers(server):
    """Get headers based on server type."""
    if server.server_type == "plex":
        return {
            "X-Plex-Token": server.token or "",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    if server.server_type == "audiobookshelf":
        return {"Authorization": f'Bearer {server.token or ""}', "Content-Type": "application/json"}
    return {"X-Emby-Token": server.api_key or "", "Content-Type": "application/json"}


def server_request(server, endpoint: str, method: str = "GET", params: Optional[Dict] = None, data: Any = None):
    """Make a request to a specific server."""
    url = f"{server.url.rstrip('/')}{endpoint}"
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=get_server_headers(server),
            params=params,
            json=data,
            timeout=30,
        )
        response.raise_for_status()
        return response.json() if response.content else {}
    except requests.exceptions.RequestException as exc:
        raise Exception(f"Server API error: {exc}") from exc


def plex_item_played(item) -> bool:
    """Determine if a Plex item has been watched."""
    if not isinstance(item, dict):
        return False
    view_count = item.get("viewCount") or item.get("viewcount")
    if isinstance(view_count, (int, float)) and view_count > 0:
        return True
    if item.get("viewedAt") or item.get("lastViewedAt"):
        return True
    return False


# ---------- Audiobookshelf helpers ----------

def normalize_abs_collections(data) -> List[dict]:
    """Normalize Audiobookshelf collections response to a list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("collections", "results", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def abs_filter_collections_by_user(collections: Iterable[dict], user_id, strict: bool = False):
    """Filter collections by user, optionally requiring a match."""
    if not user_id:
        return collections
    user_keys = ("userId", "ownerId", "user")
    filtered = [c for c in collections if any(str(c.get(k)) == str(user_id) for k in user_keys)]
    if filtered or strict:
        return filtered
    return collections


def abs_find_favorites_collection(collections: Iterable[dict]):
    """Find a favorites collection by name."""
    for collection in collections:
        name = (collection.get("name") or "").strip().lower()
        if "favorite" in name or "favourite" in name:
            return collection
    return None


def abs_collection_id(collection: dict) -> Optional[str]:
    """Get a collection id from common Audiobookshelf fields."""
    if not isinstance(collection, dict):
        return None
    return collection.get("id") or collection.get("_id") or collection.get("collectionId")


def abs_find_collection_by_id(collections: Iterable[dict], collection_id) -> Optional[dict]:
    """Find a collection by id from a list."""
    for collection in collections:
        if str(abs_collection_id(collection)) == str(collection_id):
            return collection
    return None


def normalize_abs_users(data) -> List[dict]:
    """Normalize Audiobookshelf users response to a list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("users", "results", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def normalize_abs_items(data) -> List[dict]:
    """Normalize Audiobookshelf items response to a list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "results", "libraryItems"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def abs_collection_item_ids(collection: dict) -> Tuple[List[str], str]:
    """Extract item ids and the preferred update key from a collection."""
    if not isinstance(collection, dict):
        return [], None
    if isinstance(collection.get("books"), list):
        ids = []
        for book in collection.get("books"):
            if isinstance(book, dict):
                item_id = book.get("id") or book.get("libraryItemId")
                if item_id:
                    ids.append(str(item_id))
            else:
                ids.append(str(book))
        return ids, "books"
    for key in ("libraryItemIds", "itemIds"):
        ids = collection.get(key)
        if isinstance(ids, list):
            return [str(i) for i in ids], key
    items = collection.get("items")
    if isinstance(items, list):
        ids = []
        for item in items:
            if isinstance(item, dict):
                item_id = item.get("id") or item.get("libraryItemId")
                if item_id:
                    ids.append(str(item_id))
        return ids, "libraryItemIds"
    return [], "libraryItemIds"


def abs_progress_to_played(item: dict) -> bool:
    """Determine if an Audiobookshelf item is finished."""
    progress = None
    for key in ("progress", "mediaProgress", "userMediaProgress"):
        if isinstance(item.get(key), dict):
            progress = item.get(key)
            break
    if not progress and isinstance(item.get("media"), dict):
        for key in ("progress", "mediaProgress", "userMediaProgress"):
            if isinstance(item["media"].get(key), dict):
                progress = item["media"].get(key)
                break
    if not progress:
        return False
    if progress.get("isFinished") or progress.get("isComplete") or progress.get("completed") or progress.get("finished"):
        return True
    percent = progress.get("percentComplete")
    if isinstance(percent, (int, float)) and percent >= 1:
        return True
    ratio = progress.get("progress")
    if isinstance(ratio, (int, float)) and ratio >= 1:
        return True
    return False


def abs_map_item(item: dict) -> dict:
    """Map Audiobookshelf item to shared item shape."""
    return {
        "Id": item.get("id"),
        "Name": item.get("media", {}).get("metadata", {}).get("title", "Unknown"),
        "Type": "Audiobook" if item.get("mediaType") == "book" else "Podcast",
        "ProductionYear": item.get("media", {}).get("metadata", {}).get("publishedYear"),
        "Overview": item.get("media", {}).get("metadata", {}).get("description", ""),
        "ImageTags": {"Primary": True} if item.get("media", {}).get("coverPath") else {},
        "Tags": item.get("media", {}).get("tags", []),
        "UserData": {"Played": abs_progress_to_played(item)},
    }


def abs_fetch_items(server, item_ids: Iterable[str]) -> List[dict]:
    """Fetch Audiobookshelf items by id."""
    items = []
    for item_id in item_ids:
        try:
            item = server_request(server, f"/api/items/{item_id}")
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
        detail = server_request(server, f"/api/collections/{collection_id}")
        if isinstance(detail, dict):
            return detail
    except Exception:
        return None
    return None


def abs_get_default_library_id(server):
    """Get first library id as fallback."""
    try:
        libs = server_request(server, "/api/libraries").get("libraries", [])
        if libs:
            return libs[0].get("id")
    except Exception:
        return None
    return None


def abs_get_or_create_favorites_collection(server, user_id, create=False, user_name=None, library_id=None, item_id=None):
    """Get the user's favorites collection, optionally creating it. Optionally include item on creation."""
    collections = normalize_abs_collections(server_request(server, "/api/collections"))
    collections = abs_filter_collections_by_user(collections, user_id, strict=False)
    favorite = abs_find_favorites_collection(collections)
    if favorite or not create:
        return favorite
    desired_name = "Favourites"
    if user_name:
        desired_name = f"{user_name}'s Favourites"
    payload = {
        "name": desired_name,
        "description": f"Favourites for {user_name or user_id} from Favarr",
        "libraryItemIds": [],
    }
    if not library_id and item_id:
        item_detail = abs_get_item_detail(server, item_id)
        library_id = abs_item_library_id(item_detail)
    if not library_id:
        library_id = abs_get_default_library_id(server)
    if not library_id:
        raise Exception("Audiobookshelf libraryId required to create favourites collection")
    payload["libraryId"] = library_id
    if item_id:
        payload["libraryItemIds"] = [str(item_id)]
    return server_request(server, "/api/collections", method="POST", data=payload)


def abs_get_or_create_named_favourites(server, user_name, library_id=None, item_id=None):
    """Create or find a global ABS collection named 'Favourites – <user>'."""
    if not user_name:
        raise Exception("user_name is required for Audiobookshelf favourites")
    target_name = f"Favourites – {user_name}"
    collections = normalize_abs_collections(server_request(server, "/api/collections"))
    target_lower = target_name.lower()
    alt_lower = f"favourites - {user_name}".lower()
    for collection in collections:
        name = (collection.get("name") or "").strip().lower()
        if name == target_lower or name == alt_lower:
            return collection
    payload = {
        "name": target_name,
        "description": f"Favourites for {user_name} from Favarr",
        "libraryItemIds": [],
    }
    if not library_id and item_id:
        item_detail = abs_get_item_detail(server, item_id)
        library_id = abs_item_library_id(item_detail)
    if not library_id:
        library_id = abs_get_default_library_id(server)
    if not library_id:
        raise Exception("Audiobookshelf libraryId required to create favourites collection")
    payload["libraryId"] = library_id
    if item_id:
        payload["libraryItemIds"] = [str(item_id)]
    return server_request(server, "/api/collections", method="POST", data=payload)


def abs_get_item_detail(server, item_id):
    """Fetch a single ABS item detail."""
    return server_request(server, f"/api/items/{item_id}")


def abs_item_library_id(item_detail) -> Optional[str]:
    """Extract library id from an ABS item detail payload."""
    if not isinstance(item_detail, dict):
        return None
    return (
        item_detail.get("libraryId")
        or item_detail.get("library", {}).get("id")
        or item_detail.get("media", {}).get("libraryId")
    )


def abs_item_collections(item_detail) -> List[str]:
    """Extract collection ids from an ABS item."""
    if not isinstance(item_detail, dict):
        return []
    candidates = (
        item_detail.get("collections")
        or item_detail.get("collectionIds")
        or item_detail.get("collectionsIds")
        or item_detail.get("media", {}).get("collections")
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
    server_request(server, f"/api/items/{item_id}/meta", method="PATCH", data={"collections": merged})
    return True


def abs_update_collection_items(server, collection_id, item_ids, update_key="libraryItemIds", user_id=None):
    """Update an Audiobookshelf collection with a new item list."""
    payload = {update_key or "libraryItemIds": item_ids}
    return server_request(server, f"/api/collections/{collection_id}", method="PATCH", data=payload)
