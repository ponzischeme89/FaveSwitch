const API_BASE = '/api';

async function fetchJson(url, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${url}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    });
  } catch (e) {
    // Network error - API completely unreachable
    const err = new Error('Failed to fetch');
    err.name = 'TypeError';
    throw err;
  }

  let data;
  try {
    data = await response.json();
  } catch (e) {
    // JSON parsing failed - server might be returning error page
    if (!response.ok) {
      const err = new Error('Failed to fetch');
      err.name = 'TypeError';
      throw err;
    }
    throw new Error('Invalid response from server');
  }

  if (!response.ok) {
    throw new Error(data.error || 'API request failed');
  }

  return data;
}

export const api = {
  // Health & Stats
  health: () => fetchJson('/health'),
  getLogs: (limit = 200) => fetchJson(`/logs?limit=${limit}`),
  getStats: () => fetchJson('/stats'),

  // Server Management (CRUD)
  getServers: () => fetchJson('/servers'),

  getServer: (serverId) => fetchJson(`/servers/${serverId}`),

  createServer: (server) => fetchJson('/servers', {
    method: 'POST',
    body: JSON.stringify(server)
  }),

  updateServer: (serverId, server) => fetchJson(`/servers/${serverId}`, {
    method: 'PUT',
    body: JSON.stringify(server)
  }),

  deleteServer: (serverId) => fetchJson(`/servers/${serverId}`, {
    method: 'DELETE'
  }),

  // Server-specific endpoints
  getServerInfo: (serverId) => fetchJson(`/servers/${serverId}/info`),

  testServer: (serverId) => fetchJson(`/servers/${serverId}/info`),

  getUsers: (serverId) => fetchJson(`/servers/${serverId}/users`),

  getLibraries: (serverId) => fetchJson(`/servers/${serverId}/libraries`),

  getItems: (serverId, params = {}) => {
    const query = new URLSearchParams(params).toString();
    return fetchJson(`/servers/${serverId}/items${query ? `?${query}` : ''}`);
  },

  getItem: (serverId, itemId) => fetchJson(`/servers/${serverId}/items/${itemId}`),

  getRecent: (serverId, limit = 20, parentId = '') => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (parentId) params.append('parent_id', parentId);
    return fetchJson(`/servers/${serverId}/recent?${params.toString()}`);
  },

  // Favorites
  getFavorites: (serverId, userId) => fetchJson(`/servers/${serverId}/users/${userId}/favorites`),

  addFavorite: (serverId, userId, itemId, userName = '') => {
    const query = userName ? `?user_name=${encodeURIComponent(userName)}` : '';
    return fetchJson(`/servers/${serverId}/users/${userId}/favorites/${itemId}${query}`, {
      method: 'POST'
    });
  },

  addAbsUserFavourite: (serverId, userName, libraryItemId) =>
    fetchJson(`/servers/${serverId}/abs/favourites`, {
      method: 'POST',
      body: JSON.stringify({ user_name: userName, item_id: libraryItemId })
    }),

  removeFavorite: (serverId, userId, itemId) => fetchJson(`/servers/${serverId}/users/${userId}/favorites/${itemId}`, {
    method: 'DELETE'
  }),

  // Audiobookshelf Collections
  getCollections: (serverId, userId) => fetchJson(`/servers/${serverId}/users/${userId}/collections`),

  createCollection: (serverId, userId, payload) => fetchJson(`/servers/${serverId}/users/${userId}/collections`, {
    method: 'POST',
    body: JSON.stringify(payload)
  }),

  getCollectionItems: (serverId, userId, collectionId) =>
    fetchJson(`/servers/${serverId}/users/${userId}/collections/${collectionId}/items`),

  addCollectionItem: (serverId, userId, collectionId, itemId) =>
    fetchJson(`/servers/${serverId}/users/${userId}/collections/${collectionId}/items/${itemId}`, {
      method: 'POST'
    }),

  removeCollectionItem: (serverId, userId, collectionId, itemId) =>
    fetchJson(`/servers/${serverId}/users/${userId}/collections/${collectionId}/items/${itemId}`, {
      method: 'DELETE'
    }),

  // Image URL helper
  getImageUrl: (serverId, itemId, type = 'Primary', maxWidth = 300, thumb = '') => {
    if (thumb && thumb.startsWith('http')) {
      return thumb;
    }
    let url = `${API_BASE}/servers/${serverId}/image/${itemId}?type=${type}&maxWidth=${maxWidth}`;
    if (thumb) {
      url += `&thumb=${encodeURIComponent(thumb)}`;
    }
    return url;
  },

  // Stats Collection & Scheduling
  collectStats: () => fetchJson('/stats/collect', { method: 'POST' }),

  getCollectionStatus: () => fetchJson('/stats/collect/status'),

  getSnapshots: (limit = 30) => fetchJson(`/stats/snapshots?limit=${limit}`)
};
