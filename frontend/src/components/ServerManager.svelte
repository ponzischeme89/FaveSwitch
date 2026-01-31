<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../api.js';
  import { getServerTypesList, getServerType } from '../serverIcons';

  const dispatch = createEventDispatcher();

  export let editServer = null;

  let name = '';
  let serverType = 'emby';
  let url = '';
  let apiKey = '';
  let token = '';
  let loading = false;
  let testing = false;
  let message = '';
  let error = '';

  // Get server types from shared config
  const serverTypes = getServerTypesList();

  onMount(() => {
    if (editServer) {
      name = editServer.name || '';
      serverType = editServer.server_type || 'emby';
      url = editServer.url || '';
      // Don't populate credentials - user must re-enter to change
      apiKey = '';
      token = '';
    }
  });

  function getDefaultUrl(type) {
    return getServerType(type).defaultUrl;
  }

  function handleServerTypeChange() {
    if (!url || url.includes('localhost')) {
      url = getDefaultUrl(serverType);
    }
  }

  function needsToken(type) {
    return type === 'plex' || type === 'audiobookshelf' || type === 'stremio';
  }

  $: currentServerType = getServerType(serverType);

  async function saveServer() {
    if (!name.trim()) {
      error = 'Server name is required';
      return;
    }
    if (!url.trim()) {
      error = 'Server URL is required';
      return;
    }

    loading = true;
    error = '';
    message = '';

    try {
      const serverData = {
        name: name.trim(),
        server_type: serverType,
        url: url.trim()
      };

      // Only include credentials if user entered them
      if (needsToken(serverType)) {
        if (token.trim()) {
          serverData.token = token.trim();
        }
      } else {
        if (apiKey.trim()) {
          serverData.api_key = apiKey.trim();
        }
      }

      if (editServer) {
        await api.updateServer(editServer.id, serverData);
        message = 'Server updated!';
      } else {
        await api.createServer(serverData);
        message = 'Server added!';
      }

      setTimeout(() => dispatch('saved'), 500);
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function testConnection() {
    if (!name.trim() || !url.trim()) {
      error = 'Please fill in all required fields first';
      return;
    }

    // Check credentials
    if (needsToken(serverType) && !token.trim() && !editServer?.has_credentials) {
      error = 'Token is required for testing';
      return;
    }
    if (!needsToken(serverType) && !apiKey.trim() && !editServer?.has_credentials) {
      error = 'API key is required for testing';
      return;
    }

    testing = true;
    error = '';
    message = '';

    try {
      const serverData = {
        name: name.trim(),
        server_type: serverType,
        url: url.trim()
      };

      if (needsToken(serverType) && token.trim()) {
        serverData.token = token.trim();
      } else if (!needsToken(serverType) && apiKey.trim()) {
        serverData.api_key = apiKey.trim();
      }

      let serverId;
      if (editServer) {
        // Update existing server first
        await api.updateServer(editServer.id, serverData);
        serverId = editServer.id;
      } else {
        // Create new server
        const result = await api.createServer(serverData);
        serverId = result.id;
        // Update editServer so subsequent saves don't create duplicates
        editServer = { ...serverData, id: serverId, has_credentials: true };
      }

      // Test the connection
      const info = await api.getServerInfo(serverId);
      message = `Connected to ${info.ServerName || info.name || 'server'} successfully!`;
    } catch (e) {
      error = `Connection failed: ${e.message}`;
    } finally {
      testing = false;
    }
  }

  function cancel() {
    dispatch('cancel');
  }

</script>

<div class="server-form">
  <h2 class="text-lg font-bold mb-4">
    {editServer ? 'Edit Server' : 'Add New Server'}
  </h2>

  {#if error}
    <div class="alert alert-error mb-4">{error}</div>
  {/if}

  {#if message}
    <div class="alert alert-success mb-4">{message}</div>
  {/if}

  <form on:submit|preventDefault={saveServer}>
    <!-- Server Name -->
    <div class="mb-4">
      <label for="server-name" class="block text-sm font-medium text-[--text-secondary] mb-2">
        Server Name
      </label>
      <input
        id="server-name"
        type="text"
        class="input"
        bind:value={name}
        placeholder="My Emby Server"
      />
    </div>

    <!-- Server Type -->
    <fieldset class="mb-4">
      <legend class="block text-sm font-medium text-[--text-secondary] mb-3">Server Type</legend>
      <div class="grid grid-cols-4 gap-2">
        {#each serverTypes as server}
          <button
            type="button"
            class="server-type-btn"
            class:active={serverType === server.id}
            on:click={() => { serverType = server.id; handleServerTypeChange(); }}
          >
            <span class="server-icon-wrapper" class:native-color={server.useNativeColor} style="background: {server.gradient}">
              <img src={server.icon} alt={server.name} class="icon-img" />
            </span>
            <span class="server-type-name">{server.name}</span>
          </button>
        {/each}
      </div>
    </fieldset>

    <!-- Server URL -->
    <div class="mb-4">
      <label for="server-url" class="block text-sm font-medium text-[--text-secondary] mb-2">
        Server URL
      </label>
      <input
        id="server-url"
        type="url"
        class="input"
        bind:value={url}
        placeholder={getDefaultUrl(serverType)}
      />
    </div>

    <!-- API Key / Token -->
    {#if needsToken(serverType)}
      <div class="mb-4">
        <label for="token" class="block text-sm font-medium text-[--text-secondary] mb-2">
          {currentServerType.credentialLabel}
          {#if editServer?.has_credentials}
            <span class="text-xs text-[--text-tertiary]">(leave blank to keep existing)</span>
          {/if}
        </label>
        <input
          id="token"
          type="password"
          class="input"
          bind:value={token}
          placeholder={editServer?.has_credentials ? '••••••••' : 'Enter your token'}
        />
        <p class="text-xs text-[--text-tertiary] mt-2">
          {currentServerType.credentialHint}
        </p>
      </div>
    {:else}
      <div class="mb-4">
        <label for="api-key" class="block text-sm font-medium text-[--text-secondary] mb-2">
          {currentServerType.credentialLabel}
          {#if editServer?.has_credentials}
            <span class="text-xs text-[--text-tertiary]">(leave blank to keep existing)</span>
          {/if}
        </label>
        <input
          id="api-key"
          type="password"
          class="input"
          bind:value={apiKey}
          placeholder={editServer?.has_credentials ? '••••••••' : 'Enter your API key'}
        />
        <p class="text-xs text-[--text-tertiary] mt-2">
          {currentServerType.credentialHint}
        </p>
      </div>
    {/if}

    <div class="flex gap-3 mt-6">
      <button type="button" class="btn btn-ghost" on:click={cancel}>
        Cancel
      </button>
      <button type="button" class="btn btn-secondary flex-1" on:click={testConnection} disabled={loading || testing}>
        {testing ? 'Testing...' : 'Test Connection'}
      </button>
      <button type="submit" class="btn btn-primary flex-1" disabled={loading || testing}>
        {loading ? 'Saving...' : (editServer ? 'Update' : 'Add Server')}
      </button>
    </div>
  </form>
</div>

<style>
  .server-form {
    padding: 20px;
  }

  .server-type-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 12px 8px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .server-type-btn:hover {
    background: var(--bg-hover);
    border-color: rgba(139, 92, 246, 0.3);
  }

  .server-type-btn.active {
    background: rgba(139, 92, 246, 0.15);
    border-color: var(--accent);
  }

  .server-icon-wrapper {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 8px;
    color: white;
  }

  .server-icon-wrapper .icon-img {
    width: 18px;
    height: 18px;
    object-fit: contain;
    filter: brightness(0) invert(1);
  }

  .server-icon-wrapper.native-color .icon-img {
    filter: none;
  }

  .server-type-btn.active .server-icon-wrapper {
    box-shadow: 0 0 16px rgba(139, 92, 246, 0.4);
  }

  .server-type-name {
    font-size: 11px;
    font-weight: 500;
    color: var(--text-primary);
  }
</style>
