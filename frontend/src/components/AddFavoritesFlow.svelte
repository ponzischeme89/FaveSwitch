<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { api } from '../api.js';

  export let serverId = null;
  export let serverType = null;
  export let user = null;
  export let users = []; // All available users for identity switching
  export let onUserSwitch = null; // Callback when user switches

  const dispatch = createEventDispatcher();
  const RECENT_LIMIT = 20;

  // Active user (can be switched mid-workflow)
  let activeUser = user;
  let showUserSwitcher = false;
  let userSearch = '';

  let libraries = [];
  let selectedLibrary = null;
  let tab = 'recent'; // recent | browse
  let items = [];
  let loading = false;
  let error = null;
  let searchTerm = '';
  let searching = false;
  let selectedIds = new Set();
  let queue = [];
  let favoritesSet = new Set();
  let toast = null;
  let toastTimer = null;
  let quickViewItem = null;

  // Keyboard shortcuts handling
  let panelEl = null;

  const isAudiobookshelf = () => serverType === 'audiobookshelf';

  // Filtered users for switcher
  $: filteredUsers = users.filter(u =>
    u.Name?.toLowerCase().includes(userSearch.toLowerCase())
  );

  // Sync activeUser when user prop changes
  $: if (user && (!activeUser || user.Id !== activeUser.Id)) {
    activeUser = user;
  }

  onMount(() => {
    init();
    document.addEventListener('keydown', handleKeydown);
  });

  onDestroy(() => {
    document.removeEventListener('keydown', handleKeydown);
    if (toastTimer) clearTimeout(toastTimer);
  });

  function handleKeydown(e) {
    // Only handle if panel is focused or no other input is focused
    const activeEl = document.activeElement;
    const isInputFocused = activeEl?.tagName === 'INPUT' || activeEl?.tagName === 'TEXTAREA';

    // Escape to close quick view
    if (e.key === 'Escape' && quickViewItem) {
      e.preventDefault();
      quickViewItem = null;
      return;
    }

    // Cmd/Ctrl + S to save selected items
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
      e.preventDefault();
      if (selectedIds.size > 0) {
        addQueued();
      } else if (quickViewItem) {
        addSingle(quickViewItem);
      }
      return;
    }

    // Cmd/Ctrl + K to focus search (when in browse mode)
    if ((e.metaKey || e.ctrlKey) && e.key === 'k' && !isInputFocused) {
      e.preventDefault();
      tab = 'browse';
      // Focus search input after switching
      setTimeout(() => {
        const searchInput = panelEl?.querySelector('.filters input');
        searchInput?.focus();
      }, 50);
      return;
    }
  }

  $: if (serverId && activeUser) {
    init();
  }

  async function init() {
    if (!serverId || !activeUser) return;
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

  function switchUser(newUser) {
    activeUser = newUser;
    showUserSwitcher = false;
    userSearch = '';
    selectedIds = new Set();
    queue = [];
    hydrateFavorites();

    // Notify parent of user switch
    if (onUserSwitch) {
      onUserSwitch(newUser);
    }
    dispatch('userSwitch', { user: newUser });
    showToast(`Switched to ${newUser.Name}'s library`, 'info');
  }

  function closeUserSwitcher() {
    showUserSwitcher = false;
    userSearch = '';
  }

  async function loadLibraries() {
    loading = true;
    error = null;
    try {
      libraries = await api.getLibraries(serverId);
      if (!selectedLibrary && libraries.length) {
        selectedLibrary = libraries[0];
      }
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function loadItems() {
    if (!selectedLibrary || !serverId || !activeUser) return;
    loading = true;
    error = null;
    try {
      if (tab === 'recent') {
        const res = await api.getRecent(serverId, RECENT_LIMIT, selectedLibrary.ItemId);
        items = res.Items || [];
      } else {
        searching = true;
        const params = searchTerm
          ? { search: searchTerm, limit: 60 }
          : { parent_id: selectedLibrary.ItemId, limit: 60, sort_by: 'SortName' };
        const res = await api.getItems(serverId, params);
        items = res.Items || [];
      }
    } catch (e) {
      error = e.message;
      items = [];
    } finally {
      loading = false;
      searching = false;
    }
  }

  function selectLibrary(lib) {
    selectedLibrary = lib;
    selectedIds = new Set();
    queue = [];
    loadItems();
  }

  function switchTab(next) {
    if (tab === next) return;
    tab = next;
    loadItems();
  }

  function toggleSelect(item) {
    const id = String(item.Id);
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
      queue = queue.filter((q) => q.Id !== item.Id);
    } else {
      next.add(id);
      queue = [...queue, item];
    }
    selectedIds = next;
  }

  function clearQueue() {
    selectedIds = new Set();
    queue = [];
  }

  async function addSingle(item) {
    if (!activeUser || !serverId) return;
    try {
      if (isAudiobookshelf()) {
        await api.addAbsUserFavourite(serverId, activeUser.Name, item.Id);
      } else {
        await api.addFavorite(serverId, activeUser.Id, item.Id, activeUser.Name);
      }
      favoritesSet = new Set([...favoritesSet, String(item.Id)]);
      showToast(`Added "${item.Name}" to ${activeUser?.Name || 'user'}'s favourites`, 'success');
      quickViewItem = null;
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
        if (isAudiobookshelf()) {
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
    showToast(`Added ${successCount} item${successCount === 1 ? '' : 's'} to ${activeUser?.Name || 'user'}'s favourites`, 'success');
    clearQueue();
  }

  function isAdded(id) {
    return favoritesSet.has(String(id));
  }

  function showToast(message, type = 'success') {
    toast = { message, type };
    if (toastTimer) {
      clearTimeout(toastTimer);
    }
    toastTimer = setTimeout(() => (toast = null), 2500);
  }

  // Compute FAB state dynamically
  $: fabVisible = selectedIds.size > 0 || !!quickViewItem;
  $: fabLabel = selectedIds.size > 0
    ? `Add ${selectedIds.size} to ${activeUser?.Name || 'user'}`
    : quickViewItem
      ? `Favourite for ${activeUser?.Name || 'user'}`
      : 'Add to favourites';

  function handleFabAction() {
    // Basket button routes to bulk add or single quick-view add
    if (selectedIds.size > 0) {
      addQueued();
    } else if (quickViewItem) {
      addSingle(quickViewItem);
    }
  }

  function handleItemClick(item, event) {
    // Shift-click to favourite immediately; regular click opens preview
    if (event?.shiftKey) {
      addSingle(item);
      return;
    }
    quickViewItem = item;
  }
</script>

{#if !activeUser}
  <div class="card text-center py-8">
    <p class="text-[--text-secondary]">Select a user to add favourites.</p>
  </div>
{:else}
  <div class="flow" bind:this={panelEl}>
    <!-- Identity Switcher -->
    <div class="identity-section">
      <div class="identity-switcher" class:open={showUserSwitcher}>
        <button
          class="identity-trigger"
          on:click={() => showUserSwitcher = !showUserSwitcher}
          aria-expanded={showUserSwitcher}
          aria-haspopup="listbox"
        >
          <span class="avatar">{activeUser?.Name?.charAt(0) || '?'}</span>
          <div class="identity-info">
            <span class="identity-label">Adding to</span>
            <span class="identity-name">{activeUser?.Name || 'Select user'}</span>
          </div>
          <svg class="chevron" class:rotated={showUserSwitcher} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>

        {#if showUserSwitcher && users.length > 1}
          <div class="user-dropdown" role="listbox">
            <input
              type="text"
              class="user-search"
              placeholder="Switch user..."
              bind:value={userSearch}
              on:click|stopPropagation
              on:keydown={(e) => e.key === 'Escape' && closeUserSwitcher()}
            />
            <div class="user-list">
              {#each filteredUsers as u (u.Id)}
                <button
                  class="user-option"
                  class:active={activeUser?.Id === u.Id}
                  on:click|stopPropagation={() => switchUser(u)}
                  role="option"
                  aria-selected={activeUser?.Id === u.Id}
                >
                  <span class="avatar small">{u.Name?.charAt(0) || '?'}</span>
                  <span class="user-name">{u.Name}</span>
                  {#if activeUser?.Id === u.Id}
                    <span class="check-icon">✓</span>
                  {/if}
                </button>
              {/each}
            </div>
          </div>
        {/if}
      </div>

      <div class="keyboard-hint">
        <kbd>⌘S</kbd> Save · <kbd>⌘K</kbd> Search · <kbd>Esc</kbd> Close
      </div>
    </div>

    <div class="flow-header">
      <div class="header-block">
        <div class="label">Libraries</div>
        <div class="chips">
          {#each libraries as lib (lib.ItemId)}
            <button
              class="chip"
              class:active={selectedLibrary?.ItemId === lib.ItemId}
              on:click={() => selectLibrary(lib)}
            >
              <span class="chip-icon">📚</span>
              <span>{lib.Name}</span>
            </button>
          {/each}
        </div>
      </div>
      <div class="header-block tabs">
        <button class:active={tab === 'recent'} on:click={() => switchTab('recent')}>Recent (20)</button>
        <button class:active={tab === 'browse'} on:click={() => switchTab('browse')}>Browse</button>
      </div>
    </div>

    {#if tab === 'browse'}
      <div class="filters">
        <input
          class="input"
          type="text"
          placeholder="Search this library..."
          bind:value={searchTerm}
          on:keyup={(e) => e.key === 'Enter' && loadItems()}
        />
        <button class="btn btn-secondary" on:click={loadItems} disabled={searching}>
          {searching ? 'Searching...' : 'Search'}
        </button>
      </div>
    {/if}

    {#if loading}
      <div class="grid skeleton">
        {#each Array(8) as _, idx}
          <div class="card skeleton-card" aria-hidden="true">
            <div class="thumb"></div>
            <div class="lines">
              <div class="line w-70"></div>
              <div class="line w-40"></div>
            </div>
          </div>
        {/each}
      </div>
    {:else if error}
      <div class="alert alert-error">{error}</div>
    {:else if !items.length}
      <div class="card text-center py-10">
        <p class="text-[--text-secondary]">No items found.</p>
      </div>
    {:else}
      <div class="grid">
            {#each items as item (item.Id)}
          <button
            type="button"
            class="card media-card"
            on:click={(e) => handleItemClick(item, e)}
          >
            <div class="media-top">
              <label class="checkbox">
                <input
                  type="checkbox"
                  checked={selectedIds.has(String(item.Id))}
                  on:change={() => toggleSelect(item)}
                  on:click|stopPropagation
                />
                <span></span>
              </label>
              {#if isAdded(item.Id)}
                <span class="badge badge-success">Added</span>
              {:else}
                <button class="inline-add" on:click|stopPropagation={() => addSingle(item)}>⭐ Add</button>
              {/if}
            </div>
            <div class="title" title={item.Name}>{item.Name}</div>
            <div class="meta">
              {#if item.ProductionYear}<span>{item.ProductionYear}</span>{/if}
              {#if item.UserData?.Played}<span class="pill">Played</span>{/if}
            </div>
          </button>
        {/each}
      </div>
    {/if}

        {#if toast}
          <div class="toast" class:success={toast.type === 'success'} class:error={toast.type === 'error'} class:info={toast.type === 'info'}>
            <span class="toast-icon">
              {#if toast.type === 'success'}✓{:else if toast.type === 'error'}!{:else}i{/if}
            </span>
            <span class="toast-message">{toast.message}</span>
          </div>
        {/if}

    {#if quickViewItem}
      <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
      <div
        class="quickview-backdrop"
        on:click={() => quickViewItem = null}
        on:keydown={(e) => e.key === 'Escape' && (quickViewItem = null)}
        role="dialog"
        aria-modal="true"
        tabindex="-1"
      >
        <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
        <div class="quickview" on:click|stopPropagation on:keydown|stopPropagation role="document" tabindex="-1">
          <div class="qv-header">
            <div class="qv-title">{quickViewItem.Name}</div>
            <button class="qv-close" on:click={() => quickViewItem = null} title="Close (Esc)">✕</button>
          </div>
          <div class="qv-meta">
            <span class="qv-type">{quickViewItem.Type}</span>
            {#if quickViewItem.ProductionYear}<span>• {quickViewItem.ProductionYear}</span>{/if}
          </div>
          <p class="qv-overview">{quickViewItem.Overview || 'No description available.'}</p>
          <div class="qv-actions">
            <button class="btn btn-ghost" on:click={() => quickViewItem = null}>Cancel</button>
            <button class="btn btn-primary" on:click={() => addSingle(quickViewItem)}>
              ⭐ Add to {activeUser?.Name || 'user'}'s Favourites
            </button>
          </div>
          <div class="qv-hint">Press <kbd>⌘S</kbd> to save or <kbd>Esc</kbd> to close</div>
        </div>
      </div>
    {/if}

    <div class="basket" class:hidden={!fabVisible}>
      <div class="basket-info">
        <span class="basket-icon">⭐</span>
        <span class="basket-count">{selectedIds.size || 0} selected</span>
      </div>
      <button class="basket-btn" on:click={handleFabAction}>
        {fabLabel}
      </button>
    </div>
  </div>
{/if}

<style>
  .flow {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  /* Identity Switcher Styles */
  .identity-section {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 4px;
  }

  .identity-switcher {
    position: relative;
  }

  .identity-trigger {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .identity-trigger:hover {
    border-color: rgba(139, 92, 246, 0.4);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  }

  .identity-switcher.open .identity-trigger {
    border-color: var(--accent);
    background: rgba(139, 92, 246, 0.08);
  }

  .avatar {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--accent);
    color: white;
    border-radius: 50%;
    font-size: 12px;
    font-weight: 600;
    flex-shrink: 0;
  }

  .avatar.small {
    width: 22px;
    height: 22px;
    font-size: 10px;
  }

  .identity-info {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 1px;
  }

  .identity-label {
    font-size: 10px;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .identity-name {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
  }

  .chevron {
    color: var(--text-tertiary);
    transition: transform 0.2s;
    margin-left: 4px;
  }

  .chevron.rotated {
    transform: rotate(180deg);
  }

  .user-dropdown {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    min-width: 200px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
    z-index: 100;
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
    max-height: 180px;
    overflow-y: auto;
  }

  .user-option {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 10px;
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

  .user-name {
    flex: 1;
  }

  .check-icon {
    color: var(--accent);
    font-weight: 600;
    font-size: 14px;
  }

  .keyboard-hint {
    font-size: 10px;
    color: var(--text-tertiary);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .keyboard-hint kbd {
    padding: 2px 5px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-family: inherit;
    font-size: 9px;
  }

  .flow-header {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .header-block {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .label {
    font-size: 12px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--text-tertiary);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-primary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .chip-icon {
    font-size: 14px;
  }

  .chip.active {
    border-color: rgba(139, 92, 246, 0.4);
    background: rgba(139, 92, 246, 0.15);
    color: var(--accent);
  }

  .tabs {
    display: inline-flex;
    gap: 8px;
  }

  .tabs button {
    border: 1px solid var(--border);
    background: var(--bg-card);
    padding: 8px 12px;
    border-radius: 10px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
  }

  .tabs button.active {
    background: rgba(139, 92, 246, 0.15);
    border-color: rgba(139, 92, 246, 0.4);
    color: var(--accent);
  }

  .filters {
    display: flex;
    gap: 8px;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
  }

  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px;
  }

  .media-card {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 130px;
    position: relative;
    text-align: left;
    cursor: pointer;
    transition: all 0.2s;
  }

  .media-card:hover {
    border-color: rgba(139, 92, 246, 0.4);
    transform: translateY(-2px);
  }

  .media-card:focus {
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.2);
  }

  .media-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .title {
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.3;
  }

  .meta {
    display: flex;
    gap: 10px;
    align-items: center;
    color: var(--text-secondary);
    font-size: 12px;
  }

  .pill {
    background: rgba(255, 255, 255, 0.08);
    padding: 2px 8px;
    border-radius: 999px;
    border: 1px solid var(--border);
  }

  .inline-add {
    opacity: 0;
    transition: opacity 0.15s ease;
    font-size: 12px;
    border: none;
    background: rgba(255,255,255,0.08);
    color: var(--text-primary);
    padding: 4px 8px;
    border-radius: 20px;
    cursor: pointer;
  }

  .media-card:hover .inline-add {
    opacity: 1;
  }

  .checkbox {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
  }

  .checkbox input {
    display: none;
  }

  .checkbox span {
    width: 16px;
    height: 16px;
    border: 1px solid var(--border);
    border-radius: 4px;
    display: inline-block;
    position: relative;
  }

  .checkbox input:checked + span {
    background: var(--accent);
    border-color: var(--accent);
  }

  .checkbox input:checked + span::after {
    content: '';
    position: absolute;
    left: 4px;
    top: 1px;
    width: 6px;
    height: 10px;
    border: 2px solid white;
    border-left: 0;
    border-top: 0;
    transform: rotate(45deg);
  }

  .skeleton {
    opacity: 0.7;
  }

  .skeleton-card {
    display: grid;
    grid-template-columns: 80px 1fr;
    gap: 12px;
  }

  .thumb {
    background: var(--bg-primary);
    border-radius: 10px;
    height: 80px;
  }

  .lines {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .line {
    height: 10px;
    background: var(--bg-primary);
    border-radius: 6px;
  }

  .w-70 { width: 70%; }
  .w-40 { width: 40%; }


    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      padding: 14px 18px;
      min-width: 260px;
      background: linear-gradient(135deg, var(--bg-card), rgba(255, 255, 255, 0.02));
      border: 1px solid var(--border);
      border-radius: 14px;
      box-shadow: 0 18px 46px rgba(0, 0, 0, 0.35);
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 14px;
      font-weight: 600;
      color: var(--text-primary);
      letter-spacing: 0.01em;
      animation: slideIn 0.25s ease, floatUp 4s ease-in-out infinite alternate;
      z-index: 1100;
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

    @keyframes slideIn {
      from {
        opacity: 0;
        transform: translateY(14px) scale(0.98);
      }
      to {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
    }

    @keyframes floatUp {
      from {
        transform: translateY(0);
      }
      to {
        transform: translateY(-2px);
      }
    }

  @media (max-width: 900px) {
    .chips {
      gap: 6px;
    }
    .grid {
      grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    }
    .tabs {
      width: 100%;
      justify-content: space-between;
    }
    .identity-section {
      flex-direction: column;
      gap: 8px;
      align-items: stretch;
    }
    .keyboard-hint {
      justify-content: center;
    }
  }

  .quickview-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1200;
  }

  .quickview {
    width: min(520px, 92vw);
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.45);
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .qv-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
  }

  .qv-title {
    font-size: 18px;
    font-weight: 700;
    flex: 1;
  }

  .qv-close {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s;
    flex-shrink: 0;
  }

  .qv-close:hover {
    color: #f87171;
    border-color: rgba(248, 113, 113, 0.4);
  }

  .qv-meta {
    color: var(--text-secondary);
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 13px;
  }

  .qv-type {
    padding: 3px 8px;
    background: rgba(139, 92, 246, 0.15);
    border-radius: 6px;
    color: var(--accent);
    font-size: 11px;
    text-transform: uppercase;
    font-weight: 500;
  }

  .qv-overview {
    color: var(--text-primary);
    font-size: 14px;
    line-height: 1.5;
    max-height: 160px;
    overflow-y: auto;
  }

  .qv-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    margin-top: 6px;
  }

  .qv-hint {
    text-align: center;
    font-size: 11px;
    color: var(--text-tertiary);
    padding-top: 6px;
    border-top: 1px solid var(--border);
  }

  .qv-hint kbd {
    padding: 2px 5px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-family: inherit;
    font-size: 10px;
  }

  .basket {
    position: fixed;
    right: 18px;
    bottom: 18px;
    display: inline-flex;
    gap: 12px;
    align-items: center;
    background: rgba(20, 20, 26, 0.92);
    color: white;
    padding: 10px 14px;
    border-radius: 999px;
    box-shadow: 0 14px 38px rgba(0,0,0,0.4);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    transition: all 0.2s ease;
    z-index: 1100;
  }

  .basket:hover {
    transform: translateY(-2px);
    box-shadow: 0 18px 44px rgba(0,0,0,0.5);
  }

  .basket-info {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .basket-icon {
    font-size: 14px;
  }

  .basket-count {
    font-weight: 600;
    font-size: 13px;
    color: rgba(255,255,255,0.85);
  }

  .basket-btn {
    border: none;
    background: var(--accent);
    color: white;
    padding: 8px 14px;
    border-radius: 999px;
    font-weight: 600;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .basket-btn:hover {
    background: #9b6dfa;
    transform: scale(1.02);
  }

  .hidden {
    display: none;
  }
</style>
