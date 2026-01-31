<script>
  import { createEventDispatcher, onMount, onDestroy } from 'svelte';
  import { api } from '../api.js';

  export let item = null; // The item triggering the popover (optional, for single-item add)
  export let serverId = null;
  export let serverType = null;
  export let users = []; // All available users for identity switching
  export let currentUser = null;
  export let position = { x: 0, y: 0 }; // Position for the popover
  export let isOpen = false;

  const dispatch = createEventDispatcher();

  // State
  let activeUser = currentUser;
  let libraries = [];
  let selectedLibrary = null;
  let tab = 'recent';
  let items = [];
  let loading = false;
  let searchTerm = '';
  let searching = false;
  let selectedIds = new Set();
  let favoritesSet = new Set();
  let toast = null;
  let toastTimer = null;
  let showUserSwitcher = false;
  let userSearch = '';
  let popoverEl = null;

  const RECENT_LIMIT = 12;

  $: filteredUsers = users.filter(u =>
    u.Name?.toLowerCase().includes(userSearch.toLowerCase())
  );

  $: isAudiobookshelf = serverType === 'audiobookshelf';

  // Initialize when popover opens
  $: if (isOpen && serverId && activeUser) {
    init();
  }

  // Sync activeUser with currentUser prop
  $: if (currentUser && !activeUser) {
    activeUser = currentUser;
  }

  onMount(() => {
    document.addEventListener('keydown', handleKeydown);
    document.addEventListener('click', handleClickOutside);
  });

  onDestroy(() => {
    document.removeEventListener('keydown', handleKeydown);
    document.removeEventListener('click', handleClickOutside);
    if (toastTimer) clearTimeout(toastTimer);
  });

  function handleKeydown(e) {
    if (!isOpen) return;

    // Escape to close
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
      return;
    }

    // Cmd/Ctrl + S to save selected
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
      e.preventDefault();
      if (selectedIds.size > 0) {
        addQueued();
      } else if (item) {
        addSingle(item);
      }
      return;
    }

    // Cmd/Ctrl + Enter for quick add
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      handleFabAction();
      return;
    }
  }

  function handleClickOutside(e) {
    if (isOpen && popoverEl && !popoverEl.contains(e.target)) {
      close();
    }
  }

  function close() {
    dispatch('close');
  }

  async function init() {
    await Promise.all([loadLibraries(), hydrateFavorites()]);
    await loadItems();
  }

  async function hydrateFavorites() {
    if (!activeUser) return;
    try {
      const favs = await api.getFavorites(serverId, activeUser.Id);
      favoritesSet = new Set((favs.Items || []).map((i) => String(i.Id)));
    } catch (e) {
      // non-blocking
    }
  }

  async function loadLibraries() {
    loading = true;
    try {
      libraries = await api.getLibraries(serverId);
      if (!selectedLibrary && libraries.length) {
        selectedLibrary = libraries[0];
      }
    } catch (e) {
      // Handle silently
    } finally {
      loading = false;
    }
  }

  async function loadItems() {
    if (!selectedLibrary || !serverId || !activeUser) return;
    loading = true;
    try {
      if (tab === 'recent') {
        const res = await api.getRecent(serverId, RECENT_LIMIT, selectedLibrary.ItemId);
        items = res.Items || [];
      } else {
        searching = true;
        const params = searchTerm
          ? { search: searchTerm, limit: 30 }
          : { parent_id: selectedLibrary.ItemId, limit: 30, sort_by: 'SortName' };
        const res = await api.getItems(serverId, params);
        items = res.Items || [];
      }
    } catch (e) {
      items = [];
    } finally {
      loading = false;
      searching = false;
    }
  }

  function selectLibrary(lib) {
    selectedLibrary = lib;
    selectedIds = new Set();
    loadItems();
  }

  function switchTab(next) {
    if (tab === next) return;
    tab = next;
    loadItems();
  }

  function switchUser(user) {
    activeUser = user;
    showUserSwitcher = false;
    userSearch = '';
    selectedIds = new Set();
    hydrateFavorites();
    dispatch('userSwitch', { user });
    showToast(`Switched to ${user.Name}'s library`, 'info');
  }

  function toggleSelect(itemToToggle) {
    const id = String(itemToToggle.Id);
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    selectedIds = next;
  }

  function clearSelection() {
    selectedIds = new Set();
  }

  async function addSingle(itemToAdd) {
    if (!activeUser || !serverId) return;
    try {
      if (isAudiobookshelf) {
        await api.addAbsUserFavourite(serverId, activeUser.Name, itemToAdd.Id);
      } else {
        await api.addFavorite(serverId, activeUser.Id, itemToAdd.Id, activeUser.Name);
      }
      favoritesSet = new Set([...favoritesSet, String(itemToAdd.Id)]);
      showToast(`Added "${itemToAdd.Name}" to ${activeUser.Name}'s favourites`, 'success');
      dispatch('added', { item: itemToAdd, user: activeUser });
    } catch (e) {
      showToast(e.message || 'Failed to add', 'error');
    }
  }

  async function addQueued() {
    if (!selectedIds.size || !activeUser) return;
    const ids = Array.from(selectedIds);
    let successCount = 0;

    for (const id of ids) {
      try {
        if (isAudiobookshelf) {
          await api.addAbsUserFavourite(serverId, activeUser.Name, id);
        } else {
          await api.addFavorite(serverId, activeUser.Id, id, activeUser.Name);
        }
        favoritesSet.add(String(id));
        successCount++;
      } catch (e) {
        // continue best-effort
      }
    }

    showToast(
      `Added ${successCount} item${successCount === 1 ? '' : 's'} to ${activeUser.Name}'s favourites`,
      'success'
    );
    dispatch('added', { count: successCount, user: activeUser });
    clearSelection();
  }

  function isAdded(id) {
    return favoritesSet.has(String(id));
  }

  function showToast(message, type = 'success') {
    toast = { message, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2500);
  }

  function handleFabAction() {
    if (selectedIds.size > 0) {
      addQueued();
    } else if (item) {
      addSingle(item);
    }
  }

  function handleItemClick(itemClicked, event) {
    if (event?.shiftKey) {
      addSingle(itemClicked);
      return;
    }
    toggleSelect(itemClicked);
  }

  function goToManageAll() {
    dispatch('manageAll', { user: activeUser });
    close();
  }

  // Computed
  $: fabVisible = selectedIds.size > 0 || !!item;
  $: fabLabel = selectedIds.size > 0
    ? `Add ${selectedIds.size} to ${activeUser?.Name || 'user'}`
    : item
      ? `Add to ${activeUser?.Name || 'user'}'s favourites`
      : 'Select items';

  // Position styles
  $: popoverStyle = `
    left: ${Math.min(position.x, window.innerWidth - 420)}px;
    top: ${Math.min(position.y, window.innerHeight - 500)}px;
  `;
</script>

{#if isOpen}
  <div class="popover-backdrop">
    <div
      class="popover"
      bind:this={popoverEl}
      style={popoverStyle}
      role="dialog"
      aria-modal="true"
    >
      <!-- Identity Switcher Header -->
      <div class="popover-header">
        <div class="identity-switcher" class:open={showUserSwitcher}>
          <button
            class="identity-trigger"
            on:click={() => showUserSwitcher = !showUserSwitcher}
          >
            <span class="avatar">{activeUser?.Name?.charAt(0) || '?'}</span>
            <span class="identity-name">{activeUser?.Name || 'Select user'}</span>
            <svg class="chevron" class:rotated={showUserSwitcher} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>

          {#if showUserSwitcher}
            <div class="user-dropdown">
              <input
                type="text"
                class="user-search"
                placeholder="Switch user..."
                bind:value={userSearch}
                on:click|stopPropagation
              />
              <div class="user-list">
                {#each filteredUsers as user (user.Id)}
                  <button
                    class="user-option"
                    class:active={activeUser?.Id === user.Id}
                    on:click|stopPropagation={() => switchUser(user)}
                  >
                    <span class="avatar small">{user.Name?.charAt(0) || '?'}</span>
                    <span>{user.Name}</span>
                    {#if activeUser?.Id === user.Id}
                      <span class="check">&#10003;</span>
                    {/if}
                  </button>
                {/each}
              </div>
            </div>
          {/if}
        </div>

        <div class="header-actions">
          <button class="btn-icon" on:click={goToManageAll} title="Manage All Favourites">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="7" height="7"/>
              <rect x="14" y="3" width="7" height="7"/>
              <rect x="14" y="14" width="7" height="7"/>
              <rect x="3" y="14" width="7" height="7"/>
            </svg>
          </button>
          <button class="btn-icon close" on:click={close} title="Close (Esc)">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- Library Chips -->
      <div class="library-selector">
        <div class="chips">
          {#each libraries as lib (lib.ItemId)}
            <button
              class="chip"
              class:active={selectedLibrary?.ItemId === lib.ItemId}
              on:click={() => selectLibrary(lib)}
            >
              {lib.Name}
            </button>
          {/each}
        </div>
      </div>

      <!-- Tabs + Search -->
      <div class="tabs-row">
        <div class="tabs">
          <button class:active={tab === 'recent'} on:click={() => switchTab('recent')}>
            Recent
          </button>
          <button class:active={tab === 'browse'} on:click={() => switchTab('browse')}>
            Browse
          </button>
        </div>
        {#if tab === 'browse'}
          <div class="search-inline">
            <input
              type="text"
              placeholder="Search..."
              bind:value={searchTerm}
              on:keyup={(e) => e.key === 'Enter' && loadItems()}
            />
            <button class="search-btn" on:click={loadItems} disabled={searching}>
              {#if searching}
                <span class="spinner"></span>
              {:else}
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="11" cy="11" r="8"/>
                  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
              {/if}
            </button>
          </div>
        {/if}
      </div>

      <!-- Items Grid -->
      <div class="items-container">
        {#if loading}
          <div class="loading-grid">
            {#each Array(6) as _}
              <div class="skeleton-item"></div>
            {/each}
          </div>
        {:else if items.length === 0}
          <div class="empty-state">
            <p>No items found</p>
          </div>
        {:else}
          <div class="items-grid">
            {#each items as itemEntry (itemEntry.Id)}
              <button
                class="item-card"
                class:selected={selectedIds.has(String(itemEntry.Id))}
                class:added={isAdded(itemEntry.Id)}
                on:click={(e) => handleItemClick(itemEntry, e)}
              >
                <div class="item-check">
                  {#if isAdded(itemEntry.Id)}
                    <span class="added-badge">&#10003;</span>
                  {:else if selectedIds.has(String(itemEntry.Id))}
                    <span class="selected-check">&#10003;</span>
                  {:else}
                    <span class="empty-check"></span>
                  {/if}
                </div>
                <div class="item-title" title={itemEntry.Name}>{itemEntry.Name}</div>
                <div class="item-meta">
                  {#if itemEntry.ProductionYear}<span>{itemEntry.ProductionYear}</span>{/if}
                  <span class="type-badge">{itemEntry.Type}</span>
                </div>
                {#if !isAdded(itemEntry.Id)}
                  <button
                    class="quick-add"
                    on:click|stopPropagation={() => addSingle(itemEntry)}
                    title="Quick add (Shift+Click)"
                  >
                    &#9733; Add
                  </button>
                {/if}
              </button>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Floating Action Button -->
      {#if fabVisible}
        <div class="fab-container">
          {#if selectedIds.size > 0}
            <button class="clear-btn" on:click={clearSelection}>Clear</button>
          {/if}
          <button class="fab" on:click={handleFabAction}>
            <span class="fab-icon">&#9733;</span>
            <span class="fab-label">{fabLabel}</span>
          </button>
        </div>
      {/if}

      <!-- Keyboard Hints -->
      <div class="keyboard-hints">
        <span><kbd>&#8984;S</kbd> Save</span>
        <span><kbd>Esc</kbd> Close</span>
        <span><kbd>&#8679;+Click</kbd> Quick Add</span>
      </div>

      <!-- Toast -->
        {#if toast}
          <div class="toast" class:success={toast.type === 'success'} class:error={toast.type === 'error'} class:info={toast.type === 'info'}>
            <span class="toast-icon">
              {#if toast.type === 'success'}✓{:else if toast.type === 'error'}!{:else}i{/if}
            </span>
            <span class="toast-message">{toast.message}</span>
          </div>
        {/if}
    </div>
  </div>
{/if}

<style>
  .popover-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 1200;
    backdrop-filter: blur(2px);
  }

  .popover {
    position: fixed;
    width: min(400px, 92vw);
    max-height: 520px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 1201;
  }

  .popover-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-card);
  }

  .identity-switcher {
    position: relative;
  }

  .identity-trigger {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 999px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .identity-trigger:hover {
    border-color: rgba(139, 92, 246, 0.4);
  }

  .identity-switcher.open .identity-trigger {
    border-color: var(--accent);
  }

  .avatar {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--accent);
    color: white;
    border-radius: 50%;
    font-size: 11px;
    font-weight: 600;
  }

  .avatar.small {
    width: 20px;
    height: 20px;
    font-size: 10px;
  }

  .identity-name {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
  }

  .chevron {
    color: var(--text-tertiary);
    transition: transform 0.2s;
  }

  .chevron.rotated {
    transform: rotate(180deg);
  }

  .user-dropdown {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    min-width: 180px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
    z-index: 10;
    overflow: hidden;
  }

  .user-search {
    width: 100%;
    padding: 10px 12px;
    background: var(--bg-primary);
    border: none;
    border-bottom: 1px solid var(--border);
    color: var(--text-primary);
    font-size: 13px;
  }

  .user-search::placeholder {
    color: var(--text-tertiary);
  }

  .user-list {
    max-height: 160px;
    overflow-y: auto;
  }

  .user-option {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    background: transparent;
    border: none;
    cursor: pointer;
    font-size: 13px;
    color: var(--text-primary);
    transition: background 0.15s;
    text-align: left;
  }

  .user-option:hover {
    background: var(--bg-hover);
  }

  .user-option.active {
    background: rgba(139, 92, 246, 0.15);
  }

  .check {
    margin-left: auto;
    color: var(--accent);
    font-weight: 600;
  }

  .header-actions {
    display: flex;
    gap: 6px;
  }

  .btn-icon {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .btn-icon:hover {
    color: var(--accent);
    border-color: rgba(139, 92, 246, 0.4);
  }

  .btn-icon.close:hover {
    color: #f87171;
    border-color: rgba(248, 113, 113, 0.4);
  }

  .library-selector {
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .chip {
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .chip:hover {
    border-color: rgba(139, 92, 246, 0.3);
    color: var(--text-primary);
  }

  .chip.active {
    background: rgba(139, 92, 246, 0.15);
    border-color: rgba(139, 92, 246, 0.4);
    color: var(--accent);
  }

  .tabs-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }

  .tabs {
    display: flex;
    gap: 4px;
  }

  .tabs button {
    padding: 6px 12px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .tabs button.active {
    background: rgba(139, 92, 246, 0.15);
    border-color: rgba(139, 92, 246, 0.4);
    color: var(--accent);
  }

  .search-inline {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .search-inline input {
    flex: 1;
    padding: 6px 10px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 12px;
  }

  .search-inline input::placeholder {
    color: var(--text-tertiary);
  }

  .search-btn {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--accent);
    border: none;
    border-radius: 6px;
    color: white;
    cursor: pointer;
  }

  .search-btn:disabled {
    opacity: 0.6;
  }

  .items-container {
    flex: 1;
    overflow-y: auto;
    padding: 10px 14px;
    min-height: 180px;
  }

  .loading-grid,
  .items-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }

  .skeleton-item {
    height: 70px;
    background: var(--bg-card);
    border-radius: 10px;
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 0.6; }
    50% { opacity: 1; }
  }

  .empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 120px;
    color: var(--text-tertiary);
    font-size: 13px;
  }

  .item-card {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 10px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
  }

  .item-card:hover {
    border-color: rgba(139, 92, 246, 0.3);
    transform: translateY(-1px);
  }

  .item-card.selected {
    background: rgba(139, 92, 246, 0.1);
    border-color: var(--accent);
  }

  .item-card.added {
    background: rgba(16, 185, 129, 0.08);
    border-color: rgba(16, 185, 129, 0.3);
  }

  .item-check {
    position: absolute;
    top: 8px;
    right: 8px;
  }

  .empty-check {
    display: block;
    width: 14px;
    height: 14px;
    border: 1px solid var(--border);
    border-radius: 3px;
  }

  .selected-check {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    background: var(--accent);
    border-radius: 3px;
    color: white;
    font-size: 10px;
  }

  .added-badge {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    background: #10b981;
    border-radius: 3px;
    color: white;
    font-size: 10px;
  }

  .item-title {
    font-weight: 600;
    font-size: 12px;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding-right: 20px;
  }

  .item-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    color: var(--text-secondary);
  }

  .type-badge {
    padding: 2px 5px;
    background: rgba(139, 92, 246, 0.15);
    border-radius: 4px;
    color: var(--accent);
    font-size: 9px;
    text-transform: uppercase;
  }

  .quick-add {
    position: absolute;
    bottom: 8px;
    right: 8px;
    padding: 4px 8px;
    background: rgba(255, 255, 255, 0.08);
    border: none;
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 10px;
    cursor: pointer;
    opacity: 0;
    transition: opacity 0.15s;
  }

  .item-card:hover .quick-add {
    opacity: 1;
  }

  .fab-container {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 8px;
    padding: 10px 14px;
    border-top: 1px solid var(--border);
    background: var(--bg-card);
  }

  .clear-btn {
    padding: 8px 12px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-secondary);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .clear-btn:hover {
    border-color: rgba(248, 113, 113, 0.4);
    color: #f87171;
  }

  .fab {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 10px 16px;
    background: var(--accent);
    border: none;
    border-radius: 999px;
    color: white;
    font-weight: 600;
    font-size: 13px;
    cursor: pointer;
    transition: all 0.2s;
    box-shadow: 0 4px 14px rgba(139, 92, 246, 0.3);
  }

  .fab:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(139, 92, 246, 0.4);
  }

  .fab-icon {
    font-size: 14px;
  }

  .keyboard-hints {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 8px 14px;
    background: var(--bg-primary);
    border-top: 1px solid var(--border);
    font-size: 11px;
    color: var(--text-tertiary);
  }

  .keyboard-hints kbd {
    padding: 2px 5px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-family: inherit;
    font-size: 10px;
  }

    .toast {
      position: absolute;
      bottom: 60px;
      left: 50%;
      transform: translateX(-50%);
      padding: 14px 18px;
      min-width: 240px;
      background: linear-gradient(135deg, var(--bg-card), rgba(255, 255, 255, 0.02));
      border: 1px solid var(--border);
      border-radius: 14px;
      box-shadow: 0 16px 36px rgba(0, 0, 0, 0.4);
      font-size: 14px;
      font-weight: 600;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: 12px;
      z-index: 10;
      animation: slideUp 0.25s ease, floatUp 4s ease-in-out infinite alternate;
      letter-spacing: 0.01em;
      backdrop-filter: blur(8px);
    }

    .toast::before {
      content: '';
      position: absolute;
      inset: 0;
      border-radius: 14px;
      pointer-events: none;
      opacity: 0.1;
    }

    .toast-icon {
      width: 32px;
      height: 32px;
      border-radius: 999px;
      display: grid;
      place-items: center;
      font-size: 16px;
      font-weight: 800;
      color: #fff;
      background: #64748b;
      flex-shrink: 0;
    }

    .toast-message {
      flex: 1;
      line-height: 1.35;
      text-align: left;
    }

    .toast.success {
      border-color: rgba(16, 185, 129, 0.5);
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(16, 185, 129, 0.05));
    }

    .toast.success .toast-icon {
      background: linear-gradient(135deg, #16c784, #0fa971);
    }

    .toast.error {
      border-color: rgba(248, 113, 113, 0.55);
      background: linear-gradient(135deg, rgba(248, 113, 113, 0.16), rgba(248, 113, 113, 0.07));
      color: #fee2e2;
    }

    .toast.error .toast-icon {
      background: linear-gradient(135deg, #f87171, #ef4444);
    }

    .toast.info {
      border-color: rgba(59, 130, 246, 0.5);
      background: linear-gradient(135deg, rgba(59, 130, 246, 0.14), rgba(59, 130, 246, 0.06));
      color: var(--text-primary);
    }

    .toast.info .toast-icon {
      background: linear-gradient(135deg, #3b82f6, #2563eb);
    }

    @keyframes slideUp {
      from {
        opacity: 0;
        transform: translateX(-50%) translateY(14px) scale(0.98);
      }
      to {
        opacity: 1;
        transform: translateX(-50%) translateY(0) scale(1);
      }
    }

    @keyframes floatUp {
      from {
        transform: translateX(-50%) translateY(0);
      }
      to {
        transform: translateX(-50%) translateY(-2px);
      }
    }

  .spinner {
    width: 12px;
    height: 12px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
