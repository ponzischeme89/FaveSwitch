<script>
  export let serverId = null;
  // user prop kept for API compatibility with parent component
  export let user = null;
  import { onMount, createEventDispatcher } from 'svelte';
  import { api } from '../api';
  import { getServerTypesList, getServerType, usesNativeColor } from '../serverIcons';

  // Suppress unused warning - user may be used in future
  void user;

  let currentTab = 'integrations';
  let logEntries = [];
  let logsLoading = false;
  let logError = '';
  let autoRefresh = true;
  let pollTimer = null;
  const logFilters = ['all', 'System', 'Favorites', 'Favourites', 'Integrations'];
  let selectedLogFilter = 'all';
  let integrations = [];
  let integrationsLoading = false;
  let integrationsError = '';
  let toast = '';
  let toastType = 'success';
  let toastTimer = null;
  let sortedIntegrations = [];

  // Statistics state
  let stats = null;
  let statsLoading = false;
  let statsError = '';

  // Stats collection state
  let collecting = false;
  let collectionProgress = 0;
  let collectionMessage = '';
  let collectionPollTimer = null;
  let snapshots = [];
  let snapshotsLoading = false;

  // Add integration state
  let showAddForm = false;
  let addStep = 1; // 1 = select type, 2 = enter details
  let editingId = null;
  let testing = false;
  let saving = false;
  let connectionStatus = {}; // { serverId: 'connected' | 'error' | 'unknown' }
  const dispatch = createEventDispatcher();

  let newIntegration = {
    name: '',
    server_type: '',
    url: '',
    credential: '',
    enabled: true
  };

  // Get server types from shared config
  const serverTypes = getServerTypesList();

  $: selectedServerType = newIntegration.server_type ? getServerType(newIntegration.server_type) : null;

  function parseLogLines(lines = []) {
    // Support both " [ts] LEVEL in module: msg" and " [ts] LEVEL: msg" shapes
    const patterns = [
      /^\[(?<ts>.+?)\]\s+(?<level>[A-Z]+)\s+in\s+(?<module>[^:]+):\s+(?<msg>.*)$/,
      /^\[(?<ts>.+?)\]\s+(?<level>[A-Z]+)\s*:?\s*(?<msg>.*)$/
    ];

    return lines.map((line) => {
      for (const regex of patterns) {
        const match = line.match(regex);
        if (match && match.groups) {
          const msg = match.groups.msg || '';
          // Derive service/module from "[Service]" prefix inside the message if present
          let derivedModule = match.groups.module || '';
          const serviceMatch = msg.match(/^\[(?<svc>[^\]]+)\]\s*(?<rest>.*)$/);
          let cleanedMsg = msg;
          if (serviceMatch && serviceMatch.groups) {
            derivedModule = derivedModule || serviceMatch.groups.svc;
            cleanedMsg = serviceMatch.groups.rest || '';
          }
          return {
            ts: match.groups.ts || '',
            level: match.groups.level || 'INFO',
            module: derivedModule,
            msg: cleanedMsg,
            raw: line
          };
        }
      }
      return { ts: '', level: 'INFO', module: '', msg: line, raw: line };
    });
  }

  async function loadLogs() {
    if (!serverId) {
      logEntries = [];
      return;
    }
    logsLoading = true;
    logError = '';
    try {
      const res = await api.getLogs(300);
      const lines = res.lines || [];
      logEntries = parseLogLines(lines);
    } catch (err) {
      logError = err.message || 'Failed to load logs';
    } finally {
      logsLoading = false;
    }
  }

  function refreshLogs() {
    loadLogs();
  }

  function goToTab(tab) {
    currentTab = tab;
    if (tab === 'logs') {
      loadLogs();
    } else if (tab === 'integrations') {
      loadIntegrations();
    } else if (tab === 'statistics') {
      loadStats();
      loadSnapshots();
    }
  }

  async function loadStats() {
    statsLoading = true;
    statsError = '';
    try {
      stats = await api.getStats();
    } catch (err) {
      statsError = err.message || 'Failed to load statistics';
    } finally {
      statsLoading = false;
    }
  }

  async function loadSnapshots() {
    snapshotsLoading = true;
    try {
      snapshots = await api.getSnapshots(10);
    } catch (err) {
      console.error('Failed to load snapshots:', err);
    } finally {
      snapshotsLoading = false;
    }
  }

  async function startCollection() {
    collecting = true;
    collectionProgress = 0;
    collectionMessage = 'Starting collection...';
    try {
      await api.collectStats();
      pollCollectionStatus();
    } catch (err) {
      showToast(err.message || 'Failed to start collection', 'error');
      collecting = false;
    }
  }

  async function pollCollectionStatus() {
    if (collectionPollTimer) clearTimeout(collectionPollTimer);
    try {
      const status = await api.getCollectionStatus();
      collectionProgress = status.progress || 0;
      collectionMessage = status.message || '';
      if (status.status === 'running') {
        collectionPollTimer = setTimeout(pollCollectionStatus, 1000);
      } else {
        collecting = false;
        if (status.status === 'completed') {
          showToast('Statistics collection completed', 'success');
          loadStats();
          loadSnapshots();
        } else if (status.status === 'failed') {
          showToast('Collection failed: ' + (status.message || 'Unknown error'), 'error');
        }
      }
    } catch (err) {
      console.error('Failed to poll status:', err);
      collectionPollTimer = setTimeout(pollCollectionStatus, 2000);
    }
  }

  function formatSnapshotDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString();
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(() => {
      if (currentTab === 'logs' && autoRefresh && !logsLoading) {
        loadLogs();
      }
    }, 5000);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  $: filteredLogEntries = selectedLogFilter === 'all'
    ? logEntries
    : logEntries.filter((entry) => {
        const mod = (entry.module || '').toLowerCase();
        const msg = (entry.msg || '').toLowerCase();
        const target = selectedLogFilter.toLowerCase();
        const aliases = target === 'favorites' ? ['favorites', 'favourites'] : [target];
        return aliases.some((t) =>
          mod === t || msg.startsWith(`[${t}]`) || msg.includes(`[${t}]`)
        );
      });

  onMount(() => {
    if (currentTab === 'logs') {
      loadLogs();
    }
    if (currentTab === 'integrations') {
      loadIntegrations();
    }
    startPolling();
    return () => stopPolling();
  });

  function showToast(message, type = 'success') {
    toast = message;
    toastType = type;
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast = '';
    }, 4000);
  }

  async function loadIntegrations() {
    integrationsLoading = true;
    integrationsError = '';
    try {
      integrations = await api.getServers();
      // Test connections in background
      integrations.forEach(async (integration) => {
        try {
          await api.getServerInfo(integration.id);
          connectionStatus[integration.id] = 'connected';
          connectionStatus = { ...connectionStatus };
        } catch {
          connectionStatus[integration.id] = 'error';
          connectionStatus = { ...connectionStatus };
        }
      });
    } catch (err) {
      integrationsError = err.message || 'Failed to load integrations';
    } finally {
      integrationsLoading = false;
    }
  }

  // Keep integrations sorted A–Z by integration type, then by name
  $: sortedIntegrations = [...integrations].sort((a, b) => {
    const typeA = getServerType(a.server_type).name;
    const typeB = getServerType(b.server_type).name;
    const typeCompare = typeA.localeCompare(typeB);
    if (typeCompare !== 0) return typeCompare;
    return (a.name || '').localeCompare(b.name || '');
  });

  function selectServerType(typeId) {
    const serverType = serverTypes.find(s => s.id === typeId);
    newIntegration.server_type = typeId;
    newIntegration.name = serverType.name;
    newIntegration.url = serverType.defaultUrl;
    addStep = 2;
  }

  function backToTypeSelection() {
    addStep = 1;
    newIntegration.server_type = '';
  }

  function cancelAdd() {
    showAddForm = false;
    addStep = 1;
    editingId = null;
    resetForm();
  }

  function resetForm() {
    newIntegration = {
      name: '',
      server_type: '',
      url: '',
      credential: '',
      enabled: true
    };
  }

  function startAdd() {
    showAddForm = true;
    addStep = 1;
    editingId = null;
    resetForm();
  }

  function startEdit(integration) {
    showAddForm = true;
    addStep = 2;
    editingId = integration.id;
    newIntegration = {
      name: integration.name,
      server_type: integration.server_type,
      url: integration.url,
      credential: '', // Don't populate credentials
      enabled: integration.enabled
    };
  }

  async function testConnection() {
    if (!newIntegration.url) {
      showToast('Please enter a server URL', 'error');
      return;
    }

    testing = true;
    try {
      // If editing, test existing server; otherwise create temp server and test
      let testServerId = editingId;

      if (!editingId) {
        // Create a temporary server to test
        const payload = buildPayload();
        const result = await api.createServer(payload);
        testServerId = result.id;
        editingId = testServerId; // Keep reference so we can update instead of create duplicate
      } else {
        // Update existing server with new values before testing
        const payload = buildPayload();
        await api.updateServer(editingId, payload);
      }

      const info = await api.getServerInfo(testServerId);
      showToast(`Connected to ${info.ServerName || info.name || 'server'} successfully!`, 'success');
      connectionStatus[testServerId] = 'connected';
      connectionStatus = { ...connectionStatus };
    } catch (err) {
      showToast(`Connection failed: ${err.message}`, 'error');
    } finally {
      testing = false;
    }
  }

  function buildPayload() {
    const payload = {
      name: newIntegration.name || selectedServerType?.name || 'New Server',
      server_type: newIntegration.server_type,
      url: newIntegration.url,
      enabled: true
    };

    if (newIntegration.credential) {
      if (newIntegration.server_type === 'plex' || newIntegration.server_type === 'audiobookshelf') {
        payload.token = newIntegration.credential;
      } else {
        payload.api_key = newIntegration.credential;
      }
    }

    return payload;
  }

  async function saveIntegration() {
    if (!newIntegration.server_type) {
      showToast('Please select a server type', 'error');
      return;
    }
    if (!newIntegration.url) {
      showToast('Please enter a server URL', 'error');
      return;
    }

    saving = true;
    try {
      const payload = buildPayload();

      if (editingId) {
        await api.updateServer(editingId, payload);
        showToast('Integration updated successfully', 'success');
        dispatch('updated');
      } else {
        await api.createServer(payload);
        showToast('Integration added successfully', 'success');
        dispatch('updated');
      }

      cancelAdd();
      loadIntegrations();
    } catch (err) {
      showToast(err.message || 'Failed to save integration', 'error');
    } finally {
      saving = false;
    }
  }

  async function removeIntegration(integration) {
    if (!confirm(`Delete "${integration.name}"?\n\nThis will remove the server connection from FaveSwitch.`)) return;
    try {
      await api.deleteServer(integration.id);
      showToast('Integration removed', 'success');
      loadIntegrations();
      dispatch('updated');
    } catch (err) {
      showToast(err.message || 'Failed to delete integration', 'error');
    }
  }

  async function refreshConnection(integration) {
    connectionStatus[integration.id] = 'testing';
    connectionStatus = { ...connectionStatus };
    try {
      await api.getServerInfo(integration.id);
      connectionStatus[integration.id] = 'connected';
      showToast(`${integration.name} is connected`, 'success');
    } catch {
      connectionStatus[integration.id] = 'error';
      showToast(`Cannot connect to ${integration.name}`, 'error');
    }
    connectionStatus = { ...connectionStatus };
  }

  function getServerTypeInfo(typeId) {
    return getServerType(typeId);
  }
</script>

<div class="settings-container">
  {#if toast}
    <div class="toast" class:error={toastType === 'error'} class:success={toastType === 'success'}>
      <span class="toast-icon">
        {#if toastType === 'success'}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
        {:else}
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        {/if}
      </span>
      {toast}
    </div>
  {/if}

  <div class="settings-header">
    <h2 class="settings-title">Settings</h2>
    <div class="tabs">
      <button class:active={currentTab === 'integrations'} on:click={() => goToTab('integrations')}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
          <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
          <line x1="6" y1="6" x2="6.01" y2="6"/>
          <line x1="6" y1="18" x2="6.01" y2="18"/>
        </svg>
        Integrations
      </button>
      <button class:active={currentTab === 'logs'} on:click={() => goToTab('logs')}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
        Logs
      </button>
      <button class:active={currentTab === 'statistics'} on:click={() => goToTab('statistics')}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="20" x2="18" y2="10"/>
          <line x1="12" y1="20" x2="12" y2="4"/>
          <line x1="6" y1="20" x2="6" y2="14"/>
        </svg>
        Statistics
      </button>
    </div>
  </div>

  {#if currentTab === 'integrations'}
    <div class="integrations-content">
      {#if integrationsError}
        <div class="alert alert-error">{integrationsError}</div>
      {/if}

      {#if showAddForm}
        <div class="add-form-container">
          <div class="add-form-header">
            <h3>{editingId ? 'Edit Integration' : 'Add Integration'}</h3>
            <button class="close-btn" on:click={cancelAdd}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>

          {#if addStep === 1}
            <div class="type-selection">
              <p class="step-description">Choose the type of media server you want to connect:</p>
              <div class="server-type-grid">
                {#each serverTypes as serverType}
                  <button
                    class="server-type-card"
                    on:click={() => selectServerType(serverType.id)}
                  >
                    <div class="server-type-icon" class:native-color={serverType.useNativeColor} style="background: {serverType.gradient}">
                      <img src={serverType.icon} alt={serverType.name} class="icon-img" />
                    </div>
                    <div class="server-type-info">
                      <span class="server-type-name">{serverType.name}</span>
                      <span class="server-type-desc">{serverType.description}</span>
                    </div>
                    <svg class="arrow-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <polyline points="9 18 15 12 9 6"/>
                    </svg>
                  </button>
                {/each}
              </div>
            </div>
          {:else}
            <div class="details-form">
              {#if !editingId}
                <button class="back-btn" on:click={backToTypeSelection}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="15 18 9 12 15 6"/>
                  </svg>
                  Back to server types
                </button>
              {/if}

              <div class="selected-type-banner" class:native-color={selectedServerType?.useNativeColor} style="background: {selectedServerType?.gradient}">
                <img src={selectedServerType?.icon} alt={selectedServerType?.name} class="banner-icon" />
                <span>{selectedServerType?.name}</span>
              </div>

              <div class="form-group">
                <label for="server-name">Display Name</label>
                <input
                  id="server-name"
                  type="text"
                  class="input"
                  bind:value={newIntegration.name}
                  placeholder={selectedServerType?.name || 'My Server'}
                />
              </div>

              <div class="form-group">
                <label for="server-url">Server URL</label>
                <input
                  id="server-url"
                  type="url"
                  class="input"
                  bind:value={newIntegration.url}
                  placeholder={selectedServerType?.defaultUrl || 'http://localhost:8096'}
                />
                <span class="hint">Include the port number (e.g., {selectedServerType?.defaultUrl})</span>
              </div>

              <div class="form-group">
                <label for="credential">
                  {selectedServerType?.credentialLabel || 'API Key'}
                  {#if editingId}
                    <span class="optional">(leave blank to keep existing)</span>
                  {/if}
                </label>
                <input
                  id="credential"
                  type="password"
                  class="input"
                  bind:value={newIntegration.credential}
                  placeholder={editingId ? '••••••••' : `Enter your ${selectedServerType?.credentialLabel?.toLowerCase() || 'API key'}`}
                />
                <div class="credential-help">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
                    <line x1="12" y1="17" x2="12.01" y2="17"/>
                  </svg>
                  <span>{selectedServerType?.credentialHint || 'Find in your server settings'}</span>
                </div>
              </div>

              <div class="form-actions">
                <button class="btn btn-secondary" on:click={testConnection} disabled={testing || saving}>
                  {#if testing}
                    <span class="spinner"></span>
                    Testing...
                  {:else}
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                      <polyline points="22 4 12 14.01 9 11.01"/>
                    </svg>
                    Test Connection
                  {/if}
                </button>
                <button class="btn btn-primary" on:click={saveIntegration} disabled={testing || saving}>
                  {#if saving}
                    <span class="spinner"></span>
                    Saving...
                  {:else}
                    {editingId ? 'Update' : 'Add'} Integration
                  {/if}
                </button>
              </div>
            </div>
          {/if}
        </div>
      {:else}
        <div class="integrations-header">
          <div>
            <h3>Your Integrations</h3>
            <p class="muted">Manage your connected media servers</p>
          </div>
          <button class="btn btn-primary" on:click={startAdd}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Add Integration
          </button>
        </div>

        {#if integrationsLoading}
          <div class="integrations-skeleton">
            {#each Array(3) as _}
              <div class="skeleton-card">
                <div class="skeleton icon"></div>
                <div class="skeleton lines">
                  <div class="skeleton line w-60"></div>
                  <div class="skeleton line w-40"></div>
                </div>
                <div class="skeleton pill"></div>
              </div>
            {/each}
          </div>
        {:else if integrations.length === 0}
          <div class="empty-state">
            <div class="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
                <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
                <line x1="6" y1="6" x2="6.01" y2="6"/>
                <line x1="6" y1="18" x2="6.01" y2="18"/>
              </svg>
            </div>
            <h4>No integrations yet</h4>
            <p>Connect your first media server to start managing favourites across all your libraries.</p>
            <button class="btn btn-primary" on:click={startAdd}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              Add Your First Integration
            </button>
          </div>
        {:else}
          <div class="integrations-list">
            {#each sortedIntegrations as integration (integration.id)}
              {@const typeInfo = getServerTypeInfo(integration.server_type)}
              {@const status = connectionStatus[integration.id] || 'unknown'}
              <div class="integration-card">
                <div class="integration-icon" class:native-color={typeInfo.useNativeColor} style="background: {typeInfo.gradient}">
                  <img src={typeInfo.icon} alt={typeInfo.name} class="icon-img" />
                </div>
                <div class="integration-details">
                  <div class="integration-header">
                    <span class="integration-name">{integration.name}</span>
                    <div class="status-indicator" class:connected={status === 'connected'} class:error={status === 'error'} class:testing={status === 'testing'}>
                      {#if status === 'testing'}
                        <span class="spinner small"></span>
                      {:else}
                        <span class="status-dot"></span>
                      {/if}
                      <span class="status-text">
                        {status === 'connected' ? 'Connected' : status === 'error' ? 'Disconnected' : status === 'testing' ? 'Testing...' : 'Unknown'}
                      </span>
                    </div>
                  </div>
                  <div class="integration-meta">
                    <span class="integration-type">{typeInfo.name}</span>
                    <span class="integration-url">{integration.url}</span>
                  </div>
                </div>
                <div class="integration-actions">
                  <button class="action-btn" title="Test connection" on:click={() => refreshConnection(integration)}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <polyline points="23 4 23 10 17 10"/>
                      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
                    </svg>
                  </button>
                  <button class="action-btn" title="Edit" on:click={() => startEdit(integration)}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                  </button>
                  <button class="action-btn delete" title="Delete" on:click={() => removeIntegration(integration)}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <polyline points="3 6 5 6 21 6"/>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                  </button>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </div>
  {:else if currentTab === 'logs'}
    <div class="logs-content">
      <div class="logs-header">
        <div>
          <h3>Backend Logs</h3>
          <p class="muted">View application logs for debugging</p>
        </div>
        <div class="log-controls">
          <label class="switch">
            <input type="checkbox" bind:checked={autoRefresh} />
            <span class="switch-slider"></span>
            <span class="switch-label">Auto refresh</span>
          </label>
          <button class="btn btn-secondary btn-sm" on:click={refreshLogs} disabled={logsLoading}>
            {#if logsLoading}
              <span class="spinner small"></span>
            {:else}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10"/>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
            {/if}
            Refresh
          </button>
        </div>
      </div>
      <div class="log-filters">
        {#each logFilters as filter}
          <button
            class="filter-btn"
            class:active={selectedLogFilter === filter}
            on:click={() => selectedLogFilter = filter}
          >
            {filter}
          </button>
        {/each}
      </div>
      {#if logError}
        <div class="alert alert-error">{logError}</div>
      {/if}
      <div class="log-viewer">
        {#if logEntries.length === 0}
          <div class="log-empty">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
            <span>No log entries yet</span>
          </div>
        {:else}
          {#each filteredLogEntries as entry, index (index)}
            <div class="log-entry">
              <span class="log-level" class:info={entry.level === 'INFO'} class:error={entry.level === 'ERROR'} class:warning={entry.level === 'WARNING' || entry.level === 'WARN'} class:debug={entry.level === 'DEBUG'}>
                {entry.level}
              </span>
              {#if entry.ts}<span class="log-ts">{entry.ts}</span>{/if}
              {#if entry.module}<span class="log-module">{entry.module}</span>{/if}
              <span class="log-msg">{entry.msg}</span>
            </div>
          {/each}
        {/if}
      </div>
    </div>
  {:else if currentTab === 'statistics'}
    <div class="stats-content">
      <div class="stats-header">
        <div>
          <h3>Library Stats</h3>
          <p class="muted">Overview of your media servers and favorites</p>
        </div>
        <div class="stats-actions">
          <button class="btn btn-primary btn-sm" on:click={startCollection} disabled={collecting || statsLoading}>
            {#if collecting}
              <span class="spinner small"></span>
              Collecting...
            {:else}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 12a9 9 0 11-6.219-8.56"/>
              </svg>
              Collect Now
            {/if}
          </button>
          <button class="btn btn-secondary btn-sm" on:click={loadStats} disabled={statsLoading || collecting}>
            {#if statsLoading}
              <span class="spinner small"></span>
            {:else}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10"/>
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
              </svg>
            {/if}
            Refresh
          </button>
        </div>
      </div>

      {#if collecting}
        <div class="collection-progress">
          <div class="progress-header">
            <span class="progress-label">Collecting statistics...</span>
            <span class="progress-percent">{collectionProgress}%</span>
          </div>
          <div class="progress-bar-container">
            <div class="progress-bar" style="width: {collectionProgress}%"></div>
          </div>
          <p class="progress-message">{collectionMessage}</p>
        </div>
      {/if}

      {#if statsError}
        <div class="alert alert-error">{statsError}</div>
      {/if}

      {#if statsLoading && !stats}
        <div class="stats-skeleton">
          {#each Array(3) as _}
            <div class="skeleton-stat">
              <div class="skeleton circle"></div>
              <div class="skeleton lines">
                <div class="skeleton line w-40"></div>
                <div class="skeleton line w-60"></div>
              </div>
            </div>
          {/each}
        </div>
      {:else if stats}
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-icon servers">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
                <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
                <line x1="6" y1="6" x2="6.01" y2="6"/>
                <line x1="6" y1="18" x2="6.01" y2="18"/>
              </svg>
            </div>
            <div class="stat-info">
              <span class="stat-value">{stats.servers?.total || 0}</span>
              <span class="stat-label">Connected Servers</span>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-icon users">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                <circle cx="9" cy="7" r="4"/>
                <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
              </svg>
            </div>
            <div class="stat-info">
              <span class="stat-value">{stats.users?.total || 0}</span>
              <span class="stat-label">Total Users</span>
            </div>
          </div>

          <div class="stat-card">
            <div class="stat-icon favorites">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
              </svg>
            </div>
            <div class="stat-info">
              <span class="stat-value">{stats.favorites?.total || 0}</span>
              <span class="stat-label">Total Favorites</span>
            </div>
          </div>
        </div>

        {#if stats.servers?.by_type && Object.keys(stats.servers.by_type).length > 0}
          <div class="stats-section">
            <h4>Servers by Type</h4>
            <div class="breakdown-list">
              {#each Object.entries(stats.servers.by_type) as [type, count]}
                <div class="breakdown-item">
                  <span class="breakdown-label">{type}</span>
                  <span class="breakdown-value">{count}</span>
                </div>
              {/each}
            </div>
          </div>
        {/if}

        {#if stats.favorites?.by_server && stats.favorites.by_server.length > 0}
          <div class="stats-section">
            <h4>Favorites by Server</h4>
            <div class="breakdown-list">
              {#each stats.favorites.by_server as server}
                <div class="breakdown-item">
                  <span class="breakdown-label">{server.name}</span>
                  <div class="breakdown-bar-container">
                    <div
                      class="breakdown-bar"
                      style="width: {stats.favorites.total > 0 ? (server.count / stats.favorites.total * 100) : 0}%"
                    ></div>
                  </div>
                  <span class="breakdown-value">{server.count}</span>
                </div>
              {/each}
            </div>
          </div>
        {/if}

        {#if stats.favorites?.by_type && Object.keys(stats.favorites.by_type).length > 0}
          <div class="stats-section">
            <h4>Favorites by Type</h4>
            <div class="type-chips">
              {#each Object.entries(stats.favorites.by_type) as [type, count]}
                <div class="type-chip">
                  <span class="type-name">{type}</span>
                  <span class="type-count">{count}</span>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      {/if}

      <!-- Snapshots History -->
      <div class="stats-section">
        <h4>Collection History</h4>
        {#if snapshotsLoading}
          <div class="snapshots-loading">
            <span class="spinner small"></span>
            Loading history...
          </div>
        {:else if snapshots.length === 0}
          <p class="snapshots-empty">No collection history yet. Click "Collect Now" to create your first snapshot.</p>
        {:else}
          <div class="snapshots-list">
            {#each snapshots as snapshot}
              <div class="snapshot-item">
                <div class="snapshot-date">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <polyline points="12 6 12 12 16 14"/>
                  </svg>
                  {formatSnapshotDate(snapshot.created_at)}
                </div>
                <div class="snapshot-stats">
                  <span class="snapshot-stat">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
                      <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
                    </svg>
                    {snapshot.servers_total} servers
                  </span>
                  <span class="snapshot-stat">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                      <circle cx="9" cy="7" r="4"/>
                    </svg>
                    {snapshot.users_total} users
                  </span>
                  <span class="snapshot-stat">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                    </svg>
                    {snapshot.favorites_total} favorites
                  </span>
                </div>
                {#if snapshot.collection_status === 'failed'}
                  <span class="snapshot-status failed">Failed</span>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>

    </div>
  {/if}
</div>

<style>
  .settings-container {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
  }

  .settings-header {
    padding: 20px 24px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }

  .settings-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .tabs {
    display: flex;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 4px;
    gap: 4px;
  }

  .tabs button {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    background: transparent;
    border: none;
    border-radius: 8px;
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }

  .tabs button:hover {
    color: var(--text-primary);
    background: var(--bg-hover);
  }

  .tabs button.active {
    background: var(--accent);
    color: white;
  }

  .toast {
    position: fixed;
    top: 24px;
    right: 24px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
    z-index: 100;
    animation: slideIn 0.3s ease;
  }

  .toast.success {
    border-color: rgba(16, 185, 129, 0.4);
  }

  .toast.success .toast-icon {
    color: #10b981;
  }

  .toast.error {
    border-color: rgba(239, 68, 68, 0.4);
  }

  .toast.error .toast-icon {
    color: #ef4444;
  }

  @keyframes slideIn {
    from {
      opacity: 0;
      transform: translateX(20px);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  /* Integrations Content */
  .integrations-content {
    padding: 24px;
  }

  .integrations-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
  }

  .integrations-header h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .muted {
    font-size: 13px;
    color: var(--text-tertiary);
  }

  /* Add Form */
  .add-form-container {
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }

  .add-form-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-secondary);
  }

  .add-form-header h3 {
    font-size: 15px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .close-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    border-radius: 8px;
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .close-btn:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  /* Type Selection */
  .type-selection {
    padding: 20px;
  }

  .step-description {
    font-size: 14px;
    color: var(--text-secondary);
    margin-bottom: 20px;
  }

  .server-type-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .server-type-card {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
  }

  .server-type-card:hover {
    background: var(--bg-hover);
    border-color: rgba(139, 92, 246, 0.3);
    transform: translateX(4px);
  }

  .server-type-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    flex-shrink: 0;
  }

  .server-type-icon .icon-img {
    width: 24px;
    height: 24px;
    object-fit: contain;
    filter: brightness(0) invert(1);
  }

  .server-type-icon.native-color .icon-img {
    filter: none;
  }

  .server-type-info {
    flex: 1;
    min-width: 0;
  }

  .server-type-name {
    display: block;
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 2px;
  }

  .server-type-desc {
    display: block;
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .arrow-icon {
    color: var(--text-tertiary);
    flex-shrink: 0;
  }

  /* Details Form */
  .details-form {
    padding: 20px;
  }

  .back-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    font-size: 13px;
    cursor: pointer;
    margin-bottom: 16px;
    border-radius: 8px;
    transition: all 0.2s;
  }

  .back-btn:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .selected-type-banner {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-radius: 10px;
    margin-bottom: 20px;
    color: white;
    font-weight: 500;
  }

  .selected-type-banner .banner-icon {
    width: 20px;
    height: 20px;
    object-fit: contain;
    filter: brightness(0) invert(1);
  }

  .selected-type-banner.native-color .banner-icon {
    filter: none;
  }

  .selected-type-banner.native-color {
    color: var(--text-primary);
  }

  .form-group {
    margin-bottom: 20px;
  }

  .form-group label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: var(--text-secondary);
    margin-bottom: 8px;
  }

  .form-group .optional {
    font-weight: 400;
    color: var(--text-tertiary);
    margin-left: 6px;
  }

  .hint {
    display: block;
    font-size: 12px;
    color: var(--text-tertiary);
    margin-top: 6px;
  }

  .credential-help {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin-top: 10px;
    padding: 12px;
    background: rgba(139, 92, 246, 0.08);
    border: 1px solid rgba(139, 92, 246, 0.15);
    border-radius: 8px;
    font-size: 12px;
    color: var(--text-secondary);
  }

  .credential-help svg {
    flex-shrink: 0;
    color: var(--accent);
    margin-top: 1px;
  }

  .form-actions {
    display: flex;
    gap: 12px;
    margin-top: 24px;
    padding-top: 20px;
    border-top: 1px solid var(--border);
  }

  .form-actions .btn {
    flex: 1;
  }

  /* Integrations Skeleton */
  .integrations-skeleton {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .skeleton-card {
    display: grid;
    grid-template-columns: 44px 1fr auto;
    align-items: center;
    gap: 12px;
    padding: 16px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 12px;
  }

  .skeleton {
    background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.12) 37%, rgba(255,255,255,0.04) 63%);
    background-size: 400% 100%;
    animation: shimmer 1.4s ease infinite;
    border-radius: 10px;
  }

  .skeleton.icon {
    width: 44px;
    height: 44px;
  }

  .skeleton.lines {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .skeleton.line {
    height: 10px;
    border-radius: 6px;
  }

  .skeleton.line.w-60 { width: 60%; }
  .skeleton.line.w-40 { width: 40%; }

  .skeleton.pill {
    width: 84px;
    height: 22px;
    border-radius: 999px;
  }

  @keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }

  /* Integrations List */
  .integrations-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .integration-card {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 12px;
    transition: all 0.2s;
  }

  .integration-card:hover {
    border-color: rgba(139, 92, 246, 0.25);
  }

  .integration-icon {
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 10px;
    flex-shrink: 0;
  }

  .integration-icon .icon-img {
    width: 22px;
    height: 22px;
    object-fit: contain;
    filter: brightness(0) invert(1);
  }

  .integration-icon.native-color .icon-img {
    filter: none;
  }

  .integration-details {
    flex: 1;
    min-width: 0;
  }

  .integration-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 4px;
  }

  .integration-name {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
  }

  .status-indicator {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 500;
    background: var(--bg-secondary);
  }

  .status-indicator.connected {
    color: #10b981;
    background: rgba(16, 185, 129, 0.1);
  }

  .status-indicator.connected .status-dot {
    background: #10b981;
    box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);
  }

  .status-indicator.error {
    color: #ef4444;
    background: rgba(239, 68, 68, 0.1);
  }

  .status-indicator.error .status-dot {
    background: #ef4444;
    box-shadow: 0 0 8px rgba(239, 68, 68, 0.5);
  }

  .status-indicator.testing {
    color: var(--text-secondary);
  }

  .status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--text-tertiary);
  }

  .integration-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .integration-type {
    color: var(--text-secondary);
  }

  .integration-url {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .integration-actions {
    display: flex;
    gap: 8px;
  }

  .action-btn {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .action-btn:hover {
    background: var(--bg-hover);
    color: var(--accent);
    border-color: rgba(139, 92, 246, 0.3);
  }

  .action-btn.delete:hover {
    color: #ef4444;
    border-color: rgba(239, 68, 68, 0.3);
    background: rgba(239, 68, 68, 0.1);
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    padding: 60px 20px;
  }

  .empty-icon {
    width: 80px;
    height: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 20px;
    color: var(--text-tertiary);
    margin-bottom: 20px;
  }

  .empty-state h4 {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 8px;
  }

  .empty-state p {
    font-size: 13px;
    color: var(--text-tertiary);
    max-width: 320px;
    margin-bottom: 20px;
  }

  /* Spinner */
  .spinner {
    width: 18px;
    height: 18px;
    border: 2px solid rgba(255, 255, 255, 0.2);
    border-top-color: currentColor;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .spinner.small {
    width: 14px;
    height: 14px;
    border-width: 2px;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Logs Content */
  .logs-content {
    padding: 24px;
  }

  .logs-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  .logs-header h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .log-controls {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .log-filters {
    display: flex;
    gap: 8px;
    margin: 4px 0 12px;
    flex-wrap: wrap;
  }

  .filter-btn {
    padding: 6px 10px;
    border: 1px solid var(--border);
    background: var(--bg-primary);
    color: var(--text-secondary);
    border-radius: 8px;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .filter-btn.active {
    color: var(--accent);
    border-color: var(--accent);
    background: rgba(139, 92, 246, 0.12);
  }

  .switch {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
  }

  .switch input {
    display: none;
  }

  .switch-slider {
    width: 36px;
    height: 20px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 10px;
    position: relative;
    transition: all 0.2s;
  }

  .switch-slider::after {
    content: '';
    position: absolute;
    top: 2px;
    left: 2px;
    width: 14px;
    height: 14px;
    background: var(--text-tertiary);
    border-radius: 50%;
    transition: all 0.2s;
  }

  .switch input:checked + .switch-slider {
    background: var(--accent);
    border-color: var(--accent);
  }

  .switch input:checked + .switch-slider::after {
    transform: translateX(16px);
    background: white;
  }

  .switch-label {
    font-size: 13px;
    color: var(--text-secondary);
  }

  .log-viewer {
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 12px;
    max-height: 400px;
    overflow-y: auto;
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 12px;
  }

  .log-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
    color: var(--text-tertiary);
    gap: 12px;
  }

  .log-entry {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }

  .log-entry:last-child {
    border-bottom: none;
  }

  .log-level {
    flex-shrink: 0;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
  }

  .log-level.info {
    background: rgba(59, 130, 246, 0.15);
    color: #3b82f6;
  }

  .log-level.error {
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
  }

  .log-level.warning {
    background: rgba(245, 158, 11, 0.15);
    color: #f59e0b;
  }

  .log-level.debug {
    background: rgba(139, 92, 246, 0.15);
    color: #8b5cf6;
  }

  .log-ts {
    color: var(--text-tertiary);
    white-space: nowrap;
  }

  .log-module {
    color: var(--text-secondary);
    white-space: nowrap;
  }

  .log-msg {
    color: var(--text-primary);
    word-break: break-word;
  }

  /* Statistics Content */
  .stats-content {
    padding: 24px;
  }

  .stats-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 24px;
  }

  .stats-header h3 {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 24px;
  }

  .stat-card {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 12px;
    transition: all 0.2s;
  }

  .stat-card:hover {
    border-color: rgba(139, 92, 246, 0.25);
  }

  .stat-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    flex-shrink: 0;
  }

  .stat-icon.servers {
    background: rgba(59, 130, 246, 0.15);
    color: #3b82f6;
  }

  .stat-icon.users {
    background: rgba(16, 185, 129, 0.15);
    color: #10b981;
  }

  .stat-icon.favorites {
    background: rgba(245, 158, 11, 0.15);
    color: #f59e0b;
  }

  .stat-info {
    display: flex;
    flex-direction: column;
  }

  .stat-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1;
  }

  .stat-label {
    font-size: 13px;
    color: var(--text-tertiary);
    margin-top: 4px;
  }

  .stats-section {
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
  }

  .stats-section h4 {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 16px;
  }

  .breakdown-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .breakdown-item {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .breakdown-label {
    font-size: 13px;
    color: var(--text-secondary);
    min-width: 100px;
    text-transform: capitalize;
  }

  .breakdown-bar-container {
    flex: 1;
    height: 8px;
    background: var(--bg-secondary);
    border-radius: 4px;
    overflow: hidden;
  }

  .breakdown-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), #c084fc);
    border-radius: 4px;
    transition: width 0.3s ease;
  }

  .breakdown-value {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    min-width: 40px;
    text-align: right;
  }

  .type-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .type-chip {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 20px;
  }

  .type-name {
    font-size: 13px;
    color: var(--text-secondary);
  }

  .type-count {
    font-size: 12px;
    font-weight: 600;
    color: var(--accent);
    background: rgba(139, 92, 246, 0.15);
    padding: 2px 8px;
    border-radius: 10px;
  }

  .stats-skeleton {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
  }

  .skeleton-stat {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 20px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 12px;
  }

  .skeleton.circle {
    width: 48px;
    height: 48px;
    border-radius: 12px;
  }

  /* Stats Actions */
  .stats-actions {
    display: flex;
    gap: 8px;
  }

  /* Collection Progress */
  .collection-progress {
    background: var(--bg-primary);
    border: 1px solid rgba(139, 92, 246, 0.3);
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 20px;
  }

  .progress-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }

  .progress-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .progress-percent {
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
  }

  .progress-bar-container {
    height: 8px;
    background: var(--bg-secondary);
    border-radius: 4px;
    overflow: hidden;
    margin-bottom: 8px;
  }

  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), #c084fc);
    border-radius: 4px;
    transition: width 0.3s ease;
  }

  .progress-message {
    font-size: 12px;
    color: var(--text-tertiary);
    margin: 0;
  }

  /* Snapshots */
  .snapshots-loading {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--text-tertiary);
    font-size: 13px;
    padding: 12px 0;
  }

  .snapshots-empty {
    font-size: 13px;
    color: var(--text-tertiary);
    margin: 0;
  }

  .snapshots-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .snapshot-item {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 10px;
    flex-wrap: wrap;
  }

  .snapshot-date {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--text-secondary);
    min-width: 180px;
  }

  .snapshot-date svg {
    color: var(--text-tertiary);
  }

  .snapshot-stats {
    display: flex;
    gap: 16px;
    flex: 1;
  }

  .snapshot-stat {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--text-tertiary);
  }

  .snapshot-stat svg {
    color: var(--text-tertiary);
  }

  .snapshot-status {
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 500;
  }

  .snapshot-status.failed {
    background: rgba(239, 68, 68, 0.15);
    color: #ef4444;
  }
</style>
