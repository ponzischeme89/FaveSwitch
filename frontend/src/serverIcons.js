// Shared server type configuration with official icons from homarr-labs/dashboard-icons
// https://github.com/homarr-labs/dashboard-icons

const ICON_BASE_URL = 'https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/svg';

export const serverTypes = {
  audiobookshelf: {
    name: 'Audiobookshelf',
    description: 'Self-hosted audiobook and podcast server',
    color: '#8250df',
    gradient: 'rgba(15, 10, 26, 0.9)',
    useNativeColor: true,
    defaultPort: '13378',
    defaultUrl: 'http://localhost:13378',
    credentialLabel: 'API Token',
    credentialHint: 'Settings → Users → Select user → Copy API Token',
    icon: `${ICON_BASE_URL}/audiobookshelf.svg`
  },
  plex: {
    name: 'Plex',
    description: 'Stream movies, TV shows, and music',
    color: '#e5a00d',
    gradient: 'rgba(15, 10, 26, 0.9)',
    useNativeColor: true,
    defaultPort: '32400',
    defaultUrl: 'http://localhost:32400',
    credentialLabel: 'Plex Token',
    credentialHint: 'Get from app.plex.tv → Settings → Account → Authorized Devices',
    icon: `${ICON_BASE_URL}/plex.svg`
  },
  stremio: {
    name: 'Stremio',
    description: 'Cloud streaming library & addons',
    color: '#6c5ce7',
    gradient: 'linear-gradient(135deg, #6c5ce7 0%, #4834d4 100%)',
    useNativeColor: true,
    defaultPort: '',
    defaultUrl: 'https://api.strem.io/api',
    credentialLabel: 'Auth Key',
    credentialHint: 'Copy authKey from Stremio account (settings.json or profile)',
    icon: `${ICON_BASE_URL}/stremio.svg`
  },
  emby: {
    name: 'Emby',
    description: 'Personal media server for your content',
    color: '#52b54b',
    gradient: 'linear-gradient(135deg, #52b54b 0%, #3d8c37 100%)',
    defaultPort: '8096',
    defaultUrl: 'http://localhost:8096',
    credentialLabel: 'API Key',
    credentialHint: 'Dashboard → Advanced → API Keys → New API Key',
    icon: `${ICON_BASE_URL}/emby.svg`
  },
  jellyfin: {
    name: 'Jellyfin',
    description: 'Free and open-source media system',
    color: '#00a4dc',
    gradient: 'linear-gradient(135deg, #00a4dc 0%, #0088b9 100%)',
    defaultPort: '8096',
    defaultUrl: 'http://localhost:8096',
    credentialLabel: 'API Key',
    credentialHint: 'Dashboard → Advanced → API Keys → Add API Key',
    icon: `${ICON_BASE_URL}/jellyfin.svg`
  }
};

// Get server type info with fallback
export function getServerType(typeId) {
  return serverTypes[typeId] || serverTypes.emby;
}

// Get all server types as array for iteration
export function getServerTypesList() {
  const order = ['audiobookshelf', 'emby', 'jellyfin', 'plex', 'stremio'];
  return order
    .filter((id) => serverTypes[id])
    .map((id) => ({
      id,
      ...serverTypes[id]
    }));
}

// Get just the color for a server type
export function getServerColor(typeId) {
  return getServerType(typeId).color;
}

// Get the gradient for a server type
export function getServerGradient(typeId) {
  return getServerType(typeId).gradient;
}

// Get the icon URL for a server type
export function getServerIcon(typeId) {
  return getServerType(typeId).icon;
}

// Check if a server type uses native icon colors (no white filter)
export function usesNativeColor(typeId) {
  return getServerType(typeId).useNativeColor === true;
}
