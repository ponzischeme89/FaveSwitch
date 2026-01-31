<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import { api } from '../api.js';
  import DetailPlaceholder from './DetailPlaceholder.svelte';

  export let serverId = null;
  export let user = null;
  export let users = []; // All available users
  export let usersLoading = false;
  export let serverType = null;
  export let onUserSwitch = null;

  const dispatch = createEventDispatcher();

  let favorites = [];
  let searchResults = [];
  let collections = [];
  let selectedCollection = null;
  let collectionsLoading = false;
  let loading = true;
  let searchLoading = false;
  let error = null;
  let searchTerm = '';
  let fabSearchTerm = '';
  let showSearch = false;
  let lastUserId = null;
  let lastServerId = null;
  let lastFavoritesKey = null;

  // Master-Detail state
  let selectedItem = null;
  let bulkSelectMode = false;
  let selectedIds = new Set();

  // View mode: 'list' or 'card'
  let viewMode = 'list';

  // FAB state - now with modes: closed, menu, search, add
  let fabMode = 'closed'; // closed | menu | search | bulk
  let fabSearchResults = [];
  let fabSearching = false;

  // User switcher
  let showUserSwitcher = false;
  let userSearchTerm = '';
  let filteredUsers = [];

  // Pagination
  let pageSize = 20;
  let showAll = false;
  let currentPage = 1;
  let paginatedFavorites = [];
  let totalPages = 1;
  let pageRangeStart = 0;
  let pageRangeEnd = 0;
  let resultPickerOpenFor = null;

  // Copy-to-user popover
  let copyPickerFor = null;
  let copySearchTerm = '';

  // Toast notification
  let toast = null;
  let toastTimer = null;

  onMount(() => {
    document.addEventListener('keydown', handleKeydown);
    document.addEventListener('click', handleGlobalClick);
  });

  onDestroy(() => {
    document.removeEventListener('keydown', handleKeydown);
    document.removeEventListener('click', handleGlobalClick);
    if (toastTimer) clearTimeout(toastTimer);
  });

  function handleKeydown(e) {
    // Escape to close things
    if (e.key === 'Escape') {
      if (fabMode !== 'closed') {
        e.preventDefault();
        closeFab();
        return;
      }
      if (showUserSwitcher) {
        e.preventDefault();
        showUserSwitcher = false;
        return;
      }
      if (selectedItem) {
        e.preventDefault();
        selectedItem = null;
        return;
      }
      if (bulkSelectMode) {
        e.preventDefault();
        exitBulkMode();
        return;
      }
      return;
    }

    // Delete key to remove selected
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (selectedItem && !document.activeElement?.matches('input, textarea')) {
        e.preventDefault();
        removeFromFavorites(selectedItem);
      }
    }
  }

  function showToast(message, type = 'success') {
    toast = { message, type };
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = null), 2500);
  }

  function changePage(delta) {
    if (showAll) return;
    const next = Math.min(Math.max(1, currentPage + delta), totalPages);
    if (next !== currentPage) {
      const nextPageItems = favorites.slice((next - 1) * pageSize, next * pageSize);
      currentPage = next;
      // Avoid showing stale details from another page
      if (selectedItem && !nextPageItems.some(i => i.Id === selectedItem.Id)) {
        selectedItem = null;
      }
    }
  }

  function toggleCopyPicker(item) {
    copyPickerFor = copyPickerFor?.Id === item.Id ? null : item;
    copySearchTerm = '';
  }

  async function copyFavoriteToUser(item, targetUser) {
    if (!targetUser || !item) return;
    try {
      await api.addFavorite(serverId, targetUser.Id, item.Id, targetUser.Name || '');
      showToast(`Copied "${item.Name}" to ${targetUser.Name}'s favorites`, 'success');
    } catch (e) {
      showToast(e.message || 'Failed to copy favorite', 'error');
    } finally {
      copyPickerFor = null;
    }
  }

  function selectItem(item) {
    if (bulkSelectMode) {
      toggleBulkSelect(item);
    } else {
      selectedItem = selectedItem?.Id === item.Id ? null : item;
    }
  }

  function toggleBulkSelect(item) {
    const id = String(item.Id);
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    selectedIds = next;
  }

  function enterBulkMode() {
    bulkSelectMode = true;
    selectedItem = null;
    selectedIds = new Set();
  }

  function exitBulkMode() {
    bulkSelectMode = false;
    selectedIds = new Set();
  }

  function selectAll() {
    selectedIds = new Set(favorites.map(f => String(f.Id)));
  }

  function handleGlobalClick(event) {
    if (copyPickerFor && !event.target.closest('.copy-menu') && !event.target.closest('.inline-copy') && !event.target.closest('.card-copy')) {
      copyPickerFor = null;
    }
  }

  async function removeSelected() {
    if (!selectedIds.size) return;
    const ids = Array.from(selectedIds);
    let successCount = 0;

    for (const id of ids) {
      const item = favorites.find(f => String(f.Id) === id);
      if (item) {
        try {
          if (isAudiobookshelf && selectedCollection) {
            await api.removeCollectionItem(serverId, user.Id, selectedCollection.Id, item.Id);
          } else {
            await api.removeFavorite(serverId, user.Id, item.Id);
          }
          successCount++;
        } catch (e) {
          // continue
        }
      }
    }

    favorites = favorites.filter(f => !selectedIds.has(String(f.Id)));
    if (!showAll && (currentPage - 1) * pageSize >= favorites.length && currentPage > 1) {
      currentPage = Math.max(1, Math.ceil(favorites.length / pageSize));
    }
    showToast(`Removed ${successCount} item${successCount === 1 ? '' : 's'}`, 'success');
    exitBulkMode();
  }

  async function removeWatched() {
    if (!favorites.length) return;
    const watched = favorites.filter(f => f?.UserData?.Played);
    if (!watched.length) {
      showToast('No watched items to remove', 'info');
      return;
    }

    let removed = 0;
    for (const item of watched) {
      try {
        if (isAudiobookshelf && selectedCollection) {
          await api.removeCollectionItem(serverId, user.Id, selectedCollection.Id, item.Id);
        } else {
          await api.removeFavorite(serverId, user.Id, item.Id);
        }
        removed++;
      } catch (e) {
        // keep going
      }
    }

    favorites = favorites.filter(f => !f?.UserData?.Played);
    if (!showAll && (currentPage - 1) * pageSize >= favorites.length && currentPage > 1) {
      currentPage = Math.max(1, Math.ceil(favorites.length / pageSize));
    }
    selectedItem = null;
    showToast(`Removed ${removed} watched item${removed === 1 ? '' : 's'}`, 'success');
  }

  // User switching
  function switchUser(newUser) {
    if (user?.Id === newUser?.Id) {
      showUserSwitcher = false;
      return;
    }
    const fromName = user?.Name || 'Current user';
    const toName = newUser?.Name || 'User';
    showUserSwitcher = false;
    if (onUserSwitch) onUserSwitch(newUser);
    dispatch('userSwitch', { user: newUser });
    showToast(`Switched from ${fromName} to ${toName}`, 'info');
  }

  // FAB functions
  function openFabSearch() {
    fabMode = 'search';
    fabSearchTerm = '';
    fabSearchResults = [];
    setTimeout(() => {
      const el = document.querySelector('.fab-search-input');
      if (el && typeof el === 'object' && 'focus' in el && typeof el.focus === 'function') {
        el.focus();
      }
    }, 100);
  }

  function closeFab() {
    fabMode = 'closed';
    fabSearchTerm = '';
    fabSearchResults = [];
  }

  async function fabSearch() {
    if (!fabSearchTerm.trim() || !serverId) return;
    fabSearching = true;
    try {
      const result = await api.getItems(serverId, { search: fabSearchTerm, limit: 8 });
      fabSearchResults = result.Items || [];
    } catch (e) {
      fabSearchResults = [];
    } finally {
      fabSearching = false;
    }
  }

  async function quickAddFromFab(item) {
    if (!user || !serverId) return;
    try {
      if (isAudiobookshelf) {
        await api.addAbsUserFavourite(serverId, user.Name || '', item.Id);
      } else {
        await api.addFavorite(serverId, user.Id, item.Id, user.Name || '');
      }
      showToast(`Added "${item.Name}" to ${user.Name}'s favorites`, 'success');
      // Refresh favorites list
      if (!isAudiobookshelf) loadFavorites();
      else if (selectedCollection) loadCollectionItems();
    } catch (e) {
      showToast(e.message || 'Failed to add', 'error');
    }
  }

  $: isAudiobookshelf = serverType === 'audiobookshelf';

  $: filteredUsers = userSearchTerm
    ? users.filter(u => (u.Name || '').toLowerCase().includes(userSearchTerm.toLowerCase()))
    : users;

  $: totalPages = showAll ? 1 : Math.max(1, Math.ceil((favorites?.length || 0) / pageSize) || 1);

  $: {
    if (showAll) {
      currentPage = 1;
    } else if (!favorites.length) {
      currentPage = 1;
    } else {
      const lastPage = Math.max(1, Math.ceil(favorites.length / pageSize));
      if (currentPage > lastPage) currentPage = lastPage;
    }
  }

  $: paginatedFavorites = showAll
    ? favorites
    : favorites.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  $: pageRangeStart = favorites.length
    ? (showAll ? 1 : (currentPage - 1) * pageSize + 1)
    : 0;
  $: pageRangeEnd = favorites.length
    ? (showAll ? favorites.length : Math.min(currentPage * pageSize, favorites.length))
    : 0;

  $: if (isAudiobookshelf && user && serverId) {
    if (user.Id !== lastUserId || serverId !== lastServerId) {
      lastUserId = user.Id;
      lastServerId = serverId;
      selectedCollection = null;
      collections = [];
      loadCollections();
    }
  }

  $: if (!isAudiobookshelf && user && serverId) {
    const key = `${serverId}-${user.Id}-favorites`;
    if (key !== lastFavoritesKey) {
      // Clear stale results from other servers/users to avoid cross-contamination
      favorites = [];
      selectedItem = null;
      currentPage = 1;
      lastFavoritesKey = key;
    }
    loadFavorites();
  }

  $: if (isAudiobookshelf && user && serverId && selectedCollection) {
    loadCollectionItems();
  }

  async function loadFavorites() {
    if (!user || !serverId) return;

    loading = true;
    error = null;
    // Prevent showing stale ABS items when switching servers/users
    favorites = [];
    selectedItem = null;

    try {
      const result = await api.getFavorites(serverId, user.Id);
      favorites = result.Items || [];
      currentPage = 1;
      selectedItem = null;
    } catch (e) {
      error = e.message;
      favorites = [];
    } finally {
      loading = false;
    }
  }

  async function loadCollections() {
    if (!user || !serverId) return;

    collectionsLoading = true;
    error = null;

    try {
      console.log('[FaveSwitch] ABS collections request', { serverId, userId: user.Id });
      const result = await api.getCollections(serverId, user.Id);
      console.log('[FaveSwitch] ABS collections response', result);
      collections = result || [];
      if (!selectedCollection && collections.length > 0) {
        const favourites = collections.find(isFavouritesCollection);
        selectedCollection = favourites || collections[0];
      } else if (collections.length === 0) {
        favorites = [];
      }
    } catch (e) {
      error = e.message;
      collections = [];
      selectedCollection = null;
    } finally {
      collectionsLoading = false;
    }
  }

  async function loadCollectionItems() {
    if (!user || !serverId || !selectedCollection) return;

    loading = true;
    error = null;

    try {
      console.log('[FaveSwitch] ABS collection items request', {
        serverId,
        userId: user.Id,
        collectionId: selectedCollection.Id
      });
      const result = await api.getCollectionItems(serverId, user.Id, selectedCollection.Id);
      console.log('[FaveSwitch] ABS collection items response', result);
      favorites = result.Items || [];
      currentPage = 1;
      selectedItem = null;
    } catch (e) {
      error = e.message;
      favorites = [];
    } finally {
      loading = false;
    }
  }

  async function searchItems() {
    if (!serverId) return;

    if (!searchTerm.trim()) {
      searchResults = [];
      return;
    }

    searchLoading = true;
    try {
      const result = await api.getItems(serverId, {
        search: searchTerm,
        limit: 20
      });
      searchResults = result.Items || [];
    } catch (e) {
      error = e.message;
    } finally {
      searchLoading = false;
    }
  }

  async function addToFavorites(item) {
    if (!user || !serverId) return;

    try {
      if (isAudiobookshelf) {
        const collection = selectedCollection || await ensureFavouritesCollection();
        if (!collection) {
          throw new Error('Please select a collection');
        }
        console.log('[FaveSwitch] ABS add collection item', {
          serverId,
          userId: user.Id,
          collectionId: collection.Id,
          itemId: item.Id
        });
        await api.addCollectionItem(serverId, user.Id, collection.Id, item.Id);
        await loadCollectionItems();
      } else {
        await api.addFavorite(serverId, user.Id, item.Id);
        await loadFavorites();
      }
      searchResults = searchResults.map(r =>
        r.Id === item.Id ? { ...r, isAdded: true } : r
      );
    } catch (e) {
      error = e.message;
    }
  }

  async function removeFromFavorites(item) {
    if (!user || !serverId) return;

    try {
      if (isAudiobookshelf && selectedCollection) {
        console.log('[FaveSwitch] ABS remove collection item', {
          serverId,
          userId: user.Id,
          collectionId: selectedCollection.Id,
          itemId: item.Id
        });
        await api.removeCollectionItem(serverId, user.Id, selectedCollection.Id, item.Id);
      } else {
        await api.removeFavorite(serverId, user.Id, item.Id);
      }
    favorites = favorites.filter(f => f.Id !== item.Id);
      if (!showAll && (currentPage - 1) * pageSize >= favorites.length && currentPage > 1) {
        currentPage = currentPage - 1;
      }

      // Clear selection if removed item was selected
      if (selectedItem?.Id === item.Id) {
        selectedItem = null;
      }

      showToast(`Removed "${item.Name}" from favorites`, 'success');
    } catch (e) {
      error = e.message;
      showToast(e.message || 'Failed to remove', 'error');
    }
  }

  function toggleSearch() {
    showSearch = !showSearch;
    if (!showSearch) {
      searchTerm = '';
      searchResults = [];
    }
  }

  function isInFavorites(itemId) {
    return favorites.some(f => f.Id === itemId);
  }

  function isFavouritesCollection(collection) {
    const name = collection?.Name?.toLowerCase();
    return name === 'favourites' || name === 'favorites';
  }

  async function ensureFavouritesCollection() {
    const existing = collections.find(isFavouritesCollection);
    if (existing) {
      selectedCollection = existing;
      return existing;
    }
    console.log('[FaveSwitch] ABS create favourites collection', { serverId, userId: user.Id });
    await api.createCollection(serverId, user.Id, {
      name: 'Favourites',
      description: 'Favourites from FaveSwitch'
    });
    await loadCollections();
    const created = collections.find(isFavouritesCollection);
    if (created) {
      selectedCollection = created;
      return created;
    }
    return null;
  }

  function selectCollection(collection) {
    selectedCollection = collection;
  }

  function getStatusLabel(item) {
    if (!item?.UserData?.Played) return null;
    const type = (item.Type || '').toLowerCase();
    if (type.includes('audio') || type.includes('book') || type.includes('podcast')) {
      return 'Read';
    }
    return 'Watched';
  }

  function getImageUrl(item) {
    if (!serverId) return null;
    if (item.ImageTags?.Primary) {
      if (typeof item.ImageTags.Primary === 'string' && item.ImageTags.Primary.startsWith('http')) {
        return item.ImageTags.Primary;
      }
      if (typeof item.ImageTags.Primary === 'string' && item.ImageTags.Primary.startsWith('/')) {
        return api.getImageUrl(serverId, item.Id, 'Primary', 150, item.ImageTags.Primary);
      }
      return api.getImageUrl(serverId, item.Id, 'Primary', 150);
    }
    return null;
  }
</script>

{#if !user}
  {#if usersLoading}
    <div class="card">
      <div class="favorites-skeleton">
        {#each Array(6) as _}
          <div class="skeleton-row" aria-hidden="true">
            <div class="skeleton thumb"></div>
            <div class="skeleton text w-60"></div>
            <div class="skeleton text w-40"></div>
          </div>
        {/each}
      </div>
    </div>
  {:else}
    <div class="card text-center py-8">
      <p class="text-[--text-secondary]">Please select a user to manage favorites.</p>
    </div>
  {/if}
{:else}
  {#if error || isAudiobookshelf || showSearch}
    <div class="card">
      {#if error}
        <div class="alert alert-error">{error}</div>
      {/if}

      {#if isAudiobookshelf}
        <div class="collections-panel">
          <div class="collections-header">
            <h3 class="text-sm font-medium text-[--accent]">Collections</h3>
            {#if !collectionsLoading && !collections.some(isFavouritesCollection)}
              <button class="btn btn-secondary btn-sm" on:click={ensureFavouritesCollection}>
                + Favourites
              </button>
            {/if}
          </div>
          {#if collectionsLoading}
            <div class="collections-skeleton">
              {#each Array(4) as _}
                <div class="collection-skel-row">
                  <div class="skeleton circle"></div>
                  <div class="skeleton text w-70"></div>
                  <div class="skeleton pill w-20"></div>
                </div>
              {/each}
            </div>
          {:else if collections.length === 0}
            <p class="text-sm text-[--text-secondary]">No collections found.</p>
          {:else}
            <div class="collection-list">
              {#each collections as collection (collection.Id)}
                <button
                  class="collection-btn"
                  class:active={selectedCollection?.Id === collection.Id}
                  on:click={() => selectCollection(collection)}
                >
                  <span class="collection-name">{collection.Name}</span>
                  <span class="badge badge-success">{collection.ItemCount}</span>
                </button>
              {/each}
            </div>
          {/if}
        </div>
      {/if}

      {#if showSearch}
        <div class="search-section">
          <h3 class="text-sm font-medium text-[--accent] mb-3">
            {isAudiobookshelf
              ? `Search Items to Add to ${selectedCollection?.Name || 'Favourites'}`
              : 'Search Items to Add'}
          </h3>
          <form class="flex gap-3" on:submit|preventDefault={searchItems}>
            <input
              type="text"
              class="input flex-1"
              placeholder={isAudiobookshelf ? 'Search for audiobooks, podcasts...' : 'Search for movies, shows...'}
              bind:value={searchTerm}
            />
            <button type="submit" class="btn btn-secondary" disabled={searchLoading}>
              {searchLoading ? 'Searching...' : 'Search'}
            </button>
          </form>

          {#if searchResults.length > 0}
            <div class="search-results">
              {#each searchResults as item (item.Id)}
                <div class="result-item">
                  {#if getImageUrl(item)}
                    <img src={getImageUrl(item)} alt={item.Name} />
                  {:else}
                    <div class="no-img">
                      <span class="text-xs text-[--text-tertiary]">No Image</span>
                    </div>
                  {/if}
              <div class="result-info">
                <div class="result-title">{item.Name}</div>
                <div class="result-meta">
                  <span class="badge badge-success">{item.Type}</span>
                  {#if item.ProductionYear}
                    <span class="text-[--text-secondary]">{item.ProductionYear}</span>
                  {/if}
                  {#if getStatusLabel(item)}
                    <span class="badge badge-warning">{getStatusLabel(item)}</span>
                  {/if}
                </div>
              </div>
              <div class="add-with-user">
                <button
                  class="btn"
                  class:btn-primary={!isInFavorites(item.Id) && !item.isAdded}
                  class:btn-secondary={isInFavorites(item.Id) || item.isAdded}
                  on:click={() => addToFavorites(item)}
                  disabled={isInFavorites(item.Id) || item.isAdded}
                >
                  {isInFavorites(item.Id) || item.isAdded ? 'Added' : 'Add'}
                </button>
                {#if users?.length > 1}
                  <button
                    type="button"
                    class="mini-user"
                    aria-expanded={resultPickerOpenFor === item.Id}
                    on:click={() => resultPickerOpenFor = resultPickerOpenFor === item.Id ? null : item.Id}
                  >
                    <span class="user-avatar tiny">{user?.Name?.charAt(0) || '?'}</span>
                    <span class="mini-name">{user?.Name || 'User'}</span>
                    <svg class="chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <polyline points="6 9 12 15 18 9"/>
                    </svg>
                  </button>
                  {#if resultPickerOpenFor === item.Id}
                    <div class="mini-user-dropdown">
                      {#each users as u (u.Id)}
                        <button
                          class="mini-user-option"
                          class:active={user?.Id === u.Id}
                          on:click|stopPropagation={() => { switchUser(u); resultPickerOpenFor = null; }}
                        >
                          <span class="user-avatar tiny">{u.Name?.charAt(0) || '?'}</span>
                          <span>{u.Name}</span>
                        </button>
                      {/each}
                    </div>
                  {/if}
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}
        </div>
      {/if}
    </div>
  {/if}

  <!-- Master-Detail Layout -->
  <div class="master-detail-container">
    <!-- Master Panel (List) -->
    <div class="master-panel">
      <div class="master-header">
        <div class="title-with-user">
          <h2 class="master-title">
            {isAudiobookshelf ? (selectedCollection?.Name || 'Collection') : 'Favorites'}
            <span class="count-badge">{favorites.length}</span>
          </h2>

          <!-- User Switcher -->
          <div class="user-switcher" class:open={showUserSwitcher}>
            <button
              class="user-trigger"
              on:click={() => {
                showUserSwitcher = !showUserSwitcher;
                if (showUserSwitcher) userSearchTerm = '';
              }}
              title="Switch user"
            >
              <span class="user-avatar">{user?.Name?.charAt(0) || '?'}</span>
              <span class="user-name">{user?.Name || 'User'}</span>
              <svg class="user-chevron" class:rotated={showUserSwitcher} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>

            {#if showUserSwitcher && users.length > 1}
              <div class="user-dropdown">
                <div class="user-search">
                  <input
                    class="user-search-input"
                    type="text"
                    placeholder="Search users..."
                    bind:value={userSearchTerm}
                    on:click|stopPropagation
                  />
                </div>
                <div class="user-options">
                  {#if filteredUsers.length === 0}
                    <div class="user-empty">No matches</div>
                  {:else}
                    {#each filteredUsers as u (u.Id)}
                      <button
                        class="user-option"
                        class:active={user?.Id === u.Id}
                        on:click|stopPropagation={() => switchUser(u)}
                      >
                        <span class="option-avatar">{u.Name?.charAt(0) || '?'}</span>
                        <span class="option-name">{u.Name}</span>
                        {#if user?.Id === u.Id}
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                            <polyline points="20 6 9 17 4 12"/>
                          </svg>
                        {/if}
                      </button>
                    {/each}
                  {/if}
                </div>
              </div>
            {/if}
          </div>
        </div>

        <div class="master-actions">
          <div class="view-toggle">
            <button class="view-btn has-tooltip" data-tooltip="List view" class:active={viewMode === 'list'} on:click={() => viewMode = 'list'}>
              <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
                <line x1="3" y1="6" x2="3" y2="6"/><line x1="3" y1="12" x2="3" y2="12"/><line x1="3" y1="18" x2="3" y2="18"/>
              </svg>
            </button>
            <button class="view-btn has-tooltip" data-tooltip="Card view" class:active={viewMode === 'card'} on:click={() => viewMode = 'card'}>
              <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
                <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
              </svg>
            </button>
          </div>
          {#if !bulkSelectMode}
            <button class="action-btn has-tooltip" data-tooltip="Select multiple" on:click={enterBulkMode}>
              <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
              </svg>
            </button>
            <button class="action-btn has-tooltip" data-tooltip="Remove watched items" on:click={removeWatched}>
              <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <!-- Heroicons outline sparkles (clean up) -->
                <path d="M7.5 4.5l.53 1.6a2 2 0 001.27 1.27l1.7.57-1.7.57a2 2 0 00-1.27 1.27L7.5 11.5l-.53-1.6a2 2 0 00-1.27-1.27L4 7.94l1.7-.57a2 2 0 001.27-1.27L7.5 4.5z"/>
                <path d="M16.5 3l.42 1.28c.18.57.62 1.02 1.19 1.19L19.5 5.9l-1.39.44a1.67 1.67 0 00-1.19 1.19L16.5 8.3l-.42-1.28a1.67 1.67 0 00-1.19-1.19L13.5 5.9l1.39-.44c.57-.18 1.02-.62 1.19-1.19L16.5 3z"/>
                <path d="M15 12l.6 1.83c.16.5.55.9 1.05 1.05L18.5 15l-1.85.6c-.5.16-.89.55-1.05 1.05L15 18.5l-.6-1.85c-.16-.5-.55-.9-1.05-1.05L11.5 15l1.85-.6c.5-.16.89-.55 1.05-1.05L15 12z"/>
              </svg>
            </button>
          {:else}
            <button class="action-btn text-btn" on:click={selectAll}>All</button>
            <button class="action-btn text-btn cancel" on:click={exitBulkMode}>Done</button>
          {/if}
        </div>
      </div>

      {#if loading}
        <div class="favorites-skeleton">
          {#each Array(8) as _}
            <div class="skeleton-row" aria-hidden="true">
              <div class="skeleton thumb"></div>
              <div class="skeleton text w-60"></div>
              <div class="skeleton text w-40"></div>
            </div>
          {/each}
        </div>
      {:else if favorites.length === 0}
        <div class="empty-state">
          <p>
            {isAudiobookshelf
              ? 'No collection items yet.'
              : 'No favorites yet.'}
          </p>
          <button class="btn btn-primary btn-sm" on:click={toggleSearch}>
            + Add Items
          </button>
        </div>
      {:else if viewMode === 'list'}
        <div class="favorites-list">
          {#each paginatedFavorites as item (item.Id)}
            <button
              type="button"
              class="favorite-row"
              class:selected={selectedItem?.Id === item.Id}
              class:bulk-selected={selectedIds.has(String(item.Id))}
              on:click={() => selectItem(item)}
            >
              {#if bulkSelectMode}
                <span class="bulk-check" class:checked={selectedIds.has(String(item.Id))}>
                  {#if selectedIds.has(String(item.Id))}✓{/if}
                </span>
              {/if}
              {#if getImageUrl(item)}
                <img src={getImageUrl(item)} alt={item.Name} class="row-thumb" />
              {:else}
                <div class="row-thumb no-img">
                  <span>?</span>
                </div>
              {/if}
              <div class="row-info">
                <div class="row-title">{item.Name}</div>
                <div class="row-meta">
                  <span class="type-tag">{item.Type}</span>
                  {#if item.ProductionYear}
                    <span>{item.ProductionYear}</span>
                  {/if}
                </div>
              </div>
                {#if !bulkSelectMode}
                  <div class="inline-actions">
                    <button
                      class="inline-copy"
                      on:click|stopPropagation={() => toggleCopyPicker(item)}
                      title="Copy to another user"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="3" y="5" width="12" height="14" rx="2" />
                        <path d="M9 5V3a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-2" />
                      </svg>
                    </button>
                    {#if copyPickerFor?.Id === item.Id}
                      <div class="copy-menu" on:click|stopPropagation>
                        {#if users && users.length > 1}
                          <div class="copy-search">
                            <input
                              type="text"
                              placeholder="Search users..."
                              bind:value={copySearchTerm}
                              autocomplete="off"
                            />
                          </div>
                          <div class="copy-list">
                            {#each users.filter(u => u.Id !== user?.Id && (u.Name || '').toLowerCase().includes(copySearchTerm.toLowerCase())) as u (u.Id)}
                              <button class="copy-option" on:click={() => copyFavoriteToUser(item, u)}>
                                <span class="copy-avatar">{u.Name?.charAt(0) || '?'}</span>
                                <span class="copy-name">{u.Name}</span>
                                <span class="copy-check">↗</span>
                              </button>
                            {/each}
                            {#if users.filter(u => u.Id !== user?.Id && (u.Name || '').toLowerCase().includes(copySearchTerm.toLowerCase())).length === 0}
                              <div class="copy-empty">No matches</div>
                            {/if}
                          </div>
                        {:else}
                          <div class="copy-empty">No other users</div>
                        {/if}
                      </div>
                    {/if}
                    <button
                      class="inline-remove"
                      on:click|stopPropagation={() => removeFromFavorites(item)}
                      title="Remove from favorites"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                      </svg>
                    </button>
                  </div>
                {/if}
            </button>
          {/each}
        </div>
      {:else}
        <!-- Card Grid View -->
        <div class="favorites-grid">
          {#each paginatedFavorites as item (item.Id)}
            <button
              type="button"
              class="favorite-card"
              class:selected={selectedItem?.Id === item.Id}
              class:bulk-selected={selectedIds.has(String(item.Id))}
              on:click={() => selectItem(item)}
            >
              {#if bulkSelectMode}
                <span class="card-check" class:checked={selectedIds.has(String(item.Id))}>
                  {#if selectedIds.has(String(item.Id))}✓{/if}
                </span>
              {/if}
              <div class="card-image">
                {#if getImageUrl(item)}
                  <img src={getImageUrl(item)} alt={item.Name} />
                {:else}
                  <div class="no-img">
                    <span>?</span>
                  </div>
                {/if}
                  <div class="card-overlay">
                    <span class="card-overlay-title">{item.Name}</span>
                  </div>
                  {#if !bulkSelectMode}
                    <div class="card-actions">
                      <button
                        class="card-copy"
                        on:click|stopPropagation={() => toggleCopyPicker(item)}
                        title="Copy to another user"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <rect x="3" y="5" width="12" height="14" rx="2" />
                          <path d="M9 5V3a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-2" />
                        </svg>
                      </button>
                      <button
                        class="card-remove"
                        on:click|stopPropagation={() => removeFromFavorites(item)}
                        title="Remove from favorites"
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                          <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                      </button>
                    </div>
                  {/if}
                </div>
                <div class="card-info">
                  <div class="card-title" title={item.Name}>{item.Name}</div>
                  <div class="card-meta">
                    <span class="type-tag">{item.Type}</span>
                    {#if item.ProductionYear}
                      <span class="year">{item.ProductionYear}</span>
                    {/if}
                  </div>
                </div>
                {#if copyPickerFor?.Id === item.Id}
                  <div class="copy-menu card-menu" on:click|stopPropagation>
                    {#if users && users.length > 1}
                      <div class="copy-search">
                        <input
                          type="text"
                          placeholder="Search users..."
                          bind:value={copySearchTerm}
                          autocomplete="off"
                        />
                      </div>
                      <div class="copy-list">
                        {#each users.filter(u => u.Id !== user?.Id && (u.Name || '').toLowerCase().includes(copySearchTerm.toLowerCase())) as u (u.Id)}
                          <button class="copy-option" on:click={() => copyFavoriteToUser(item, u)}>
                            <span class="copy-avatar">{u.Name?.charAt(0) || '?'}</span>
                            <span class="copy-name">{u.Name}</span>
                            <span class="copy-check">↗</span>
                          </button>
                        {/each}
                        {#if users.filter(u => u.Id !== user?.Id && (u.Name || '').toLowerCase().includes(copySearchTerm.toLowerCase())).length === 0}
                          <div class="copy-empty">No matches</div>
                        {/if}
                      </div>
                    {:else}
                      <div class="copy-empty">No other users</div>
                    {/if}
                  </div>
                {/if}
              </button>
            {/each}
          </div>
      {/if}

      {#if favorites.length > pageSize || showAll}
        <div class="pagination">
          <button class="page-btn" on:click={() => changePage(-1)} disabled={currentPage === 1}>
            ‹ Prev
          </button>
          <span class="page-info">
            {pageRangeStart}-{pageRangeEnd} of {favorites.length}
          </span>
          <button class="page-btn" on:click={() => changePage(1)} disabled={currentPage >= totalPages}>
            Next ›
          </button>
          <button class="page-btn secondary has-tooltip" data-tooltip={showAll ? 'Return to paged view' : 'Show every item'} on:click={() => showAll = !showAll}>
            {showAll ? 'Paged view' : 'Show all'}
          </button>
        </div>
      {/if}

      {#if bulkSelectMode && selectedIds.size > 0}
        <div class="bulk-actions">
          <span class="bulk-count">{selectedIds.size} selected</span>
          <button class="btn btn-danger btn-sm" on:click={removeSelected}>
            Remove Selected
          </button>
        </div>
      {/if}
    </div>

    <!-- Detail Panel -->
    <div class="detail-panel" class:has-selection={selectedItem}>
      {#if selectedItem}
        <div class="detail-header">
          <h3 class="detail-title">{selectedItem.Name}</h3>
          <button class="close-detail" on:click={() => selectedItem = null} title="Close (Esc)">✕</button>
        </div>

        <div class="detail-image">
          {#if getImageUrl(selectedItem)}
            <img src={getImageUrl(selectedItem)} alt={selectedItem.Name} />
          {:else}
            <div class="no-image-placeholder">
              <span>No Image</span>
            </div>
          {/if}
        </div>

        <div class="detail-meta">
          <div class="meta-row">
            <span class="meta-label">Type</span>
            <span class="meta-value type-tag">{selectedItem.Type}</span>
          </div>
          {#if selectedItem.ProductionYear}
            <div class="meta-row">
              <span class="meta-label">Year</span>
              <span class="meta-value">{selectedItem.ProductionYear}</span>
            </div>
          {/if}
          {#if getStatusLabel(selectedItem)}
            <div class="meta-row">
              <span class="meta-label">Status</span>
              <span class="meta-value status-tag">{getStatusLabel(selectedItem)}</span>
            </div>
          {/if}
        </div>

        {#if selectedItem.Overview}
          <div class="detail-overview">
            <span class="meta-label">Overview</span>
            <p>{selectedItem.Overview}</p>
          </div>
        {/if}

        <div class="detail-actions">
          <button class="btn btn-danger" on:click={() => removeFromFavorites(selectedItem)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
            </svg>
            Remove from Favorites
          </button>
        </div>

        <div class="detail-hint">
          Press <kbd>Del</kbd> to remove · <kbd>Esc</kbd> to close
        </div>
      {:else}
        <DetailPlaceholder />
      {/if}
    </div>
  </div>

  <!-- Toast Notification -->
  {#if toast}
    <div class="toast" class:success={toast.type === 'success'} class:error={toast.type === 'error'} class:info={toast.type === 'info'}>
      <span class="toast-icon">
        {#if toast.type === 'success'}✓{:else if toast.type === 'error'}!{:else}i{/if}
      </span>
      <span class="toast-message">{toast.message}</span>
    </div>
  {/if}

  <!-- Floating Action Button with Inline Functionality -->
  <div class="fab-container" class:expanded={fabMode !== 'closed'}>
    {#if fabMode !== 'closed'}
      <div class="fab-backdrop" on:click={closeFab} on:keydown={(e) => e.key === 'Escape' && closeFab()} role="button" tabindex="0" aria-label="Close"></div>
    {/if}

    <!-- Expanded FAB Panel -->
    {#if fabMode === 'search'}
      <div class="fab-panel">
        <div class="fab-panel-header">
          <h4>Quick Add</h4>
          <button class="fab-close" on:click={closeFab}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <form class="fab-search-form" on:submit|preventDefault={fabSearch}>
          <input
            type="text"
            class="fab-search-input"
            placeholder="Search movies, shows..."
            bind:value={fabSearchTerm}
          />
          <button type="submit" class="fab-search-btn" disabled={fabSearching}>
            {#if fabSearching}
              <span class="spinner"></span>
            {:else}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
            {/if}
          </button>
        </form>
        {#if fabSearchResults.length > 0}
          <div class="fab-results">
            {#each fabSearchResults as item (item.Id)}
              <button class="fab-result-item" on:click={() => quickAddFromFab(item)}>
                <div class="fab-result-info">
                  <span class="fab-result-title">{item.Name}</span>
                  <span class="fab-result-meta">{item.Type} {item.ProductionYear ? `• ${item.ProductionYear}` : ''}</span>
                </div>
                <span class="fab-add-icon">+</span>
              </button>
            {/each}
          </div>
        {:else if fabSearchTerm && !fabSearching}
          <p class="fab-no-results">No results found</p>
        {/if}
      </div>
    {:else if fabMode === 'menu'}
      <div class="fab-menu">
        <button class="fab-option" on:click={openFabSearch}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <span>Search & Add</span>
        </button>
        <button class="fab-option" on:click={() => { enterBulkMode(); closeFab(); }}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
          </svg>
          <span>Bulk Select</span>
        </button>
      </div>
    {/if}

    <!-- Main FAB Button -->
    <button
      class="fab-main"
      class:active={fabMode !== 'closed'}
      on:click={() => fabMode = fabMode === 'closed' ? 'menu' : 'closed'}
      title="Quick actions"
    >
      <svg class="fab-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
      </svg>
    </button>
  </div>
{/if}

<style>
  /* Master-Detail Layout */
  .master-detail-container {
    display: grid;
    grid-template-columns: 1fr 340px;
    gap: 16px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    overflow: hidden;
    min-height: 520px;
    /* Allow the page to control height; keep internal scroll areas instead of forcing viewport height */
    max-height: 100%;
    align-items: stretch;
  }

  @media (max-width: 900px) {
    .master-detail-container {
      grid-template-columns: 1fr;
      height: auto;
    }
    .detail-panel:not(.has-selection) {
      display: none;
    }
    .master-panel,
    .detail-panel {
      height: auto;
      position: static;
    }
  }

  .master-panel {
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--border);
    overflow: hidden;
    min-height: 0;
    height: 100%;
  }

  .master-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-secondary);
    gap: 8px;
    position: sticky;
    top: 0;
    z-index: 5;
  }

  .title-with-user {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .master-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text-primary);
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }

  .count-badge {
    padding: 1px 6px;
    background: rgba(139, 92, 246, 0.15);
    color: var(--accent);
    border-radius: 999px;
    font-size: 10px;
    font-size: 11px;
    font-weight: 600;
  }

  .master-actions {
    display: flex;
    gap: 6px;
  }

  .action-btn {
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
  }

  .action-btn:hover {
    color: var(--accent);
    border-color: rgba(139, 92, 246, 0.4);
  }

  .action-btn.text-btn {
    width: auto;
    padding: 0 10px;
    font-size: 12px;
    font-weight: 500;
  }

  .action-btn.cancel {
    color: var(--text-tertiary);
  }

  .favorites-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
    min-height: 0;
  }

  .favorite-row {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.15s;
    text-align: left;
    margin-bottom: 4px;
    position: relative;
  }

  .favorite-row:hover {
    background: var(--bg-hover);
    border-color: var(--border);
  }

  .favorite-row.selected {
    background: rgba(139, 92, 246, 0.12);
    border-color: rgba(139, 92, 246, 0.4);
  }

  .favorite-row.bulk-selected {
    background: rgba(139, 92, 246, 0.08);
    border-color: rgba(139, 92, 246, 0.3);
  }

  .bulk-check {
    width: 18px;
    height: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid var(--border);
    border-radius: 4px;
    font-size: 11px;
    color: white;
    flex-shrink: 0;
    transition: all 0.15s;
  }

  .bulk-check.checked {
    background: var(--accent);
    border-color: var(--accent);
  }

  .row-thumb {
    width: 40px;
    height: 56px;
    object-fit: cover;
    border-radius: 6px;
    flex-shrink: 0;
  }

  .row-thumb.no-img {
    background: var(--bg-primary);
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-tertiary);
    font-size: 14px;
  }

  .row-info {
    flex: 1;
    min-width: 0;
  }

  .row-title {
    font-weight: 600;
    font-size: 13px;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 4px;
  }

  .row-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: var(--text-secondary);
  }

  .type-tag {
    padding: 2px 6px;
    background: rgba(139, 92, 246, 0.15);
    color: var(--accent);
    border-radius: 4px;
    font-size: 10px;
    text-transform: uppercase;
    font-weight: 500;
  }

  .inline-remove {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    color: var(--text-tertiary);
    cursor: pointer;
    opacity: 0;
    transition: all 0.15s;
    flex-shrink: 0;
  }

  .favorite-row:hover .inline-remove {
    opacity: 1;
  }

    .inline-remove:hover {
      color: #f87171;
      border-color: rgba(248, 113, 113, 0.3);
      background: rgba(248, 113, 113, 0.1);
    }

    .inline-actions {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-left: auto;
    }

    .inline-copy,
    .card-copy {
      border: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text-secondary);
      width: 30px;
      height: 30px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      cursor: pointer;
      transition: all 0.18s ease;
    }

    .inline-copy:hover,
    .card-copy:hover {
      color: var(--text-primary);
      border-color: rgba(59, 130, 246, 0.35);
      background: rgba(59, 130, 246, 0.12);
    }

    .copy-menu {
      position: absolute;
      top: 100%;
      right: 0;
      margin-top: 10px;
      background: linear-gradient(180deg, #1c132c 0%, #120c1d 100%);
      border: 1px solid rgba(139, 92, 246, 0.35);
      border-radius: 14px;
      box-shadow: 0 18px 42px rgba(0, 0, 0, 0.45);
      padding: 10px;
      min-width: 240px;
      z-index: 60;
    }

    .card-menu {
      top: 12px;
      right: 12px;
      left: 12px;
    }

    .copy-search input {
      width: 100%;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid rgba(139, 92, 246, 0.35);
      background: rgba(255, 255, 255, 0.04);
      color: var(--text-primary);
      font-size: 13px;
      margin-bottom: 8px;
    }

    .copy-search input:focus {
      outline: none;
      border-color: var(--accent);
    }

    .copy-list {
      max-height: 280px;
      overflow-y: auto;
      padding-right: 4px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .copy-option {
      width: 100%;
      display: grid;
      grid-template-columns: 32px 1fr 20px;
      align-items: center;
      gap: 8px;
      padding: 8px 10px;
      border: none;
      background: rgba(255, 255, 255, 0.02);
      color: var(--text-primary);
      border-radius: 10px;
      cursor: pointer;
      transition: all 0.12s ease;
      text-align: left;
    }

    .copy-option:hover {
      background: rgba(139, 92, 246, 0.15);
      border-color: rgba(139, 92, 246, 0.35);
    }

    .copy-avatar {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: linear-gradient(135deg, #6d28d9, #8b5cf6);
      display: grid;
      place-items: center;
      font-size: 12px;
      color: #fff;
      font-weight: 700;
    }

    .copy-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .copy-check {
      color: var(--accent);
      font-size: 14px;
      text-align: right;
    }

    .copy-empty {
      padding: 10px;
      font-size: 12px;
      color: var(--text-secondary);
      text-align: center;
    }

  .bulk-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border);
  }

  .bulk-count {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 10px 12px;
    border-top: 1px solid var(--border);
    background: var(--bg-secondary);
    position: static;
    z-index: 2;
    margin-top: auto;
  }

  .page-btn {
    padding: 6px 10px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
  }

  .page-btn.secondary {
    background: rgba(139, 92, 246, 0.1);
    border-color: rgba(139, 92, 246, 0.3);
    color: var(--accent);
  }

  .page-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .page-btn:not(:disabled):hover {
    border-color: rgba(139, 92, 246, 0.4);
    color: var(--accent);
  }

  .page-info {
    font-size: 12px;
    color: var(--text-secondary);
    white-space: nowrap;
  }

  /* Tooltips */
  .has-tooltip {
    position: relative;
    overflow: visible;
  }

  .has-tooltip::after {
    content: attr(data-tooltip);
    position: absolute;
    bottom: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    background: rgba(17, 24, 39, 0.9);
    color: #f9fafb;
    padding: 6px 8px;
    border-radius: 8px;
    font-size: 11px;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
    transition: opacity 120ms ease, transform 120ms ease;
    transform-origin: center bottom;
    z-index: 20;
  }

  .has-tooltip:hover::after,
  .has-tooltip:focus-visible::after {
    opacity: 1;
    transform: translateX(-50%) translateY(-2px);
  }

  .view-toggle,
  .action-btn {
    overflow: visible;
  }

  .icon {
    width: 14px;
    height: 14px;
  }

  .btn-danger {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
  }

  .btn-danger:hover {
    background: rgba(239, 68, 68, 0.25);
  }

  /* Detail Panel */
  .detail-panel {
    display: flex;
    flex-direction: column;
    background: var(--bg-secondary);
    overflow-y: auto;
    position: sticky;
    top: 0;
    height: 100%;
    align-self: stretch;
    min-height: 100%;
  }

  .detail-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 16px;
    gap: 12px;
    border-bottom: 1px solid var(--border);
  }

  .detail-title {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-primary);
    flex: 1;
  }

  .close-detail {
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
    flex-shrink: 0;
    transition: all 0.2s;
  }

  .close-detail:hover {
    color: #f87171;
    border-color: rgba(248, 113, 113, 0.4);
  }

  .detail-image {
    padding: 16px;
    display: flex;
    justify-content: center;
  }

  .detail-image img {
    max-width: 180px;
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  }

  .no-image-placeholder {
    width: 180px;
    height: 270px;
    background: var(--bg-primary);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-tertiary);
    font-size: 13px;
  }

  .detail-meta {
    padding: 0 16px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .meta-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .meta-label {
    font-size: 12px;
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .meta-value {
    font-size: 13px;
    color: var(--text-primary);
    font-weight: 500;
  }

  .status-tag {
    padding: 2px 8px;
    background: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border-radius: 4px;
    font-size: 11px;
  }

  .detail-overview {
    padding: 0 16px 16px;
    border-top: 1px solid var(--border);
    padding-top: 16px;
  }

  .detail-overview p {
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.5;
    margin-top: 8px;
  }

  .detail-actions {
    padding: 16px;
    margin-top: auto;
    border-top: 1px solid var(--border);
  }

  .detail-actions .btn {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
  }

  .detail-hint {
    text-align: center;
    padding: 12px;
    font-size: 11px;
    color: var(--text-tertiary);
  }

  .detail-hint kbd {
    padding: 2px 5px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-family: inherit;
    font-size: 10px;
  }

  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 32px;
    text-align: center;
    gap: 12px;
    color: var(--text-tertiary);
  }

  /* Toast */
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

  .search-section {
    background: var(--bg-primary);
    padding: 16px;
    border-radius: 12px;
    margin-top: 16px;
    border: 1px solid var(--border);
  }

  .collections-panel {
    background: var(--bg-primary);
    padding: 16px;
    border-radius: 12px;
    margin-top: 16px;
    border: 1px solid var(--border);
  }

  .collections-skeleton {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .collection-skel-row {
    display: grid;
    grid-template-columns: 32px 1fr 50px;
    align-items: center;
    gap: 10px;
    padding: 10px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--bg-card);
  }

  .skeleton.circle {
    width: 32px;
    height: 32px;
    border-radius: 50%;
  }

  .skeleton.pill {
    height: 12px;
    border-radius: 999px;
  }

  .collections-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  .collection-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 200px;
    overflow-y: auto;
  }

  .collection-btn {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 12px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
    transition: all 0.2s;
    text-align: left;
  }

  .collection-btn:hover {
    border-color: rgba(139, 92, 246, 0.3);
  }

  .collection-btn.active {
    background: rgba(139, 92, 246, 0.15);
    border-color: rgba(139, 92, 246, 0.4);
  }

  .collection-name {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
  }

  .search-results {
    margin-top: 16px;
    max-height: 400px;
    overflow-y: auto;
  }

  .result-item {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 8px;
    transition: all 0.2s;
  }

  .result-item:hover {
    border-color: rgba(139, 92, 246, 0.3);
  }

  .result-item img {
    width: 50px;
    height: 75px;
    object-fit: cover;
    border-radius: 8px;
    flex-shrink: 0;
  }

  .result-info {
    flex: 1;
    min-width: 0;
  }

  .result-title {
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .result-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }

  .add-with-user {
    display: flex;
    align-items: center;
    gap: 8px;
    position: relative;
  }

  .mini-user {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 10px;
    cursor: pointer;
    min-width: 120px;
  }

  .mini-user:hover {
    border-color: rgba(139, 92, 246, 0.4);
  }

  .mini-name {
    font-size: 12px;
    color: var(--text-primary);
    white-space: nowrap;
  }

  .mini-user .chevron {
    color: var(--text-tertiary);
  }

  .mini-user-dropdown {
    position: absolute;
    top: calc(100% + 6px);
    right: 0;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: 0 12px 28px rgba(0,0,0,0.35);
    z-index: 40;
    overflow: hidden;
    min-width: 180px;
  }

  .mini-user-option {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: transparent;
    border: none;
    color: var(--text-primary);
    text-align: left;
    cursor: pointer;
    transition: background 0.12s;
  }

  .mini-user-option:hover {
    background: var(--bg-hover);
  }

  .mini-user-option.active {
    background: rgba(139, 92, 246, 0.12);
  }

  .user-avatar.tiny {
    width: 20px;
    height: 20px;
    font-size: 10px;
  }

  .favorites-skeleton {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .skeleton-row {
    display: grid;
    grid-template-columns: 50px 1fr auto;
    align-items: center;
    gap: 12px;
    padding: 10px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--bg-card);
  }

  .skeleton {
    background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.12) 37%, rgba(255,255,255,0.04) 63%);
    background-size: 400% 100%;
    animation: shimmer 1.4s ease infinite;
    border-radius: 8px;
  }

  .skeleton.thumb {
    width: 50px;
    height: 75px;
    border-radius: 8px;
  }

  .skeleton.text {
    height: 10px;
    border-radius: 4px;
  }

  .skeleton.text.w-60 { width: 60%; }
  .skeleton.text.w-40 { width: 40%; }

  @keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }

  /* View Toggle */
  .view-toggle {
    display: flex;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 6px;
    overflow: hidden;
  }

  .view-btn {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    transition: all 0.15s;
  }

  .view-btn:hover {
    color: var(--text-secondary);
    background: var(--bg-hover);
  }

  .view-btn.active {
    color: var(--accent);
    background: rgba(139, 92, 246, 0.15);
  }

  /* Card Grid View */
  .favorites-grid {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 12px;
    align-content: start;
    min-height: 0;
  }

  .favorite-card {
    position: relative;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    cursor: pointer;
    transition: all 0.15s;
    text-align: left;
    padding: 0;
  }

  .favorite-card:hover {
    border-color: rgba(139, 92, 246, 0.4);
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  }

  .favorite-card.selected {
    border-color: var(--accent);
    box-shadow: 0 0 0 2px rgba(139, 92, 246, 0.3);
  }

  .favorite-card.bulk-selected {
    border-color: rgba(139, 92, 246, 0.5);
    background: rgba(139, 92, 246, 0.08);
  }

  .card-check {
    position: absolute;
    top: 8px;
    left: 8px;
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 4px;
    font-size: 11px;
    color: white;
    z-index: 2;
    transition: all 0.15s;
  }

  .card-check.checked {
    background: var(--accent);
    border-color: var(--accent);
  }

  .card-image {
    position: relative;
    width: 100%;
    aspect-ratio: 2/3;
    overflow: hidden;
  }

  .card-image img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .card-image .no-img {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-primary);
    color: var(--text-tertiary);
    font-size: 20px;
  }

  .card-overlay {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 24px 8px 8px;
    background: linear-gradient(to top, rgba(0, 0, 0, 0.85) 0%, rgba(0, 0, 0, 0.6) 50%, transparent 100%);
  }

  .card-overlay-title {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    font-size: 12px;
    font-weight: 600;
    color: #fff;
    line-height: 1.3;
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
  }

  .card-actions {
    position: absolute;
    top: 8px;
    right: 8px;
    display: flex;
    gap: 6px;
    align-items: center;
    opacity: 0;
    transition: all 0.15s;
    z-index: 2;
  }

  .card-copy,
  .card-remove {
    width: 26px;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    border: none;
    border-radius: 6px;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.15s;
  }

  .favorite-card:hover .card-actions {
    opacity: 1;
  }

  .card-remove:hover {
    background: rgba(248, 113, 113, 0.9);
    color: white;
  }

  .card-info {
    padding: 10px;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border);
  }

  .card-title {
    font-weight: 600;
    font-size: 13px;
    color: #fff;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.3;
    margin-bottom: 4px;
    min-height: 2.6em;
  }

  .card-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
  }

  .card-meta .year {
    color: var(--text-secondary);
  }

  /* User Switcher */
  .user-switcher {
    position: relative;
  }

  .user-trigger {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px 4px 4px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 20px;
    cursor: pointer;
    transition: all 0.2s;
  }

  .user-trigger:hover {
    border-color: rgba(139, 92, 246, 0.4);
    background: var(--bg-hover);
  }

  .user-switcher.open .user-trigger {
    border-color: var(--accent);
    background: rgba(139, 92, 246, 0.1);
  }

  .user-avatar {
    width: 22px;
    height: 22px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--accent), #a855f7);
    color: white;
    border-radius: 50%;
    font-size: 10px;
    font-weight: 600;
  }

  .user-name {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-primary);
    max-width: 100px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .user-chevron {
    color: var(--text-tertiary);
    transition: transform 0.2s;
    flex-shrink: 0;
  }

  .user-chevron.rotated {
    transform: rotate(180deg);
  }

  .user-dropdown {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    width: 240px;
    max-height: 340px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
    z-index: 100;
    overflow: hidden;
    animation: dropdownIn 0.15s ease;
    display: flex;
    flex-direction: column;
    padding: 8px;
  }

  @keyframes dropdownIn {
    from { opacity: 0; transform: translateY(-8px) scale(0.95); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .user-search {
    position: sticky;
    top: 0;
    background: var(--bg-card);
    padding-bottom: 6px;
  }

  .user-search-input {
    width: 100%;
    padding: 8px 10px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-size: 12px;
  }

  .user-search-input:focus {
    outline: none;
    border-color: var(--accent);
  }

  .user-options {
    overflow-y: auto;
    max-height: 260px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding-right: 2px;
  }

  .user-empty {
    padding: 12px 8px;
    font-size: 12px;
    color: var(--text-tertiary);
    text-align: center;
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
    background: rgba(139, 92, 246, 0.12);
  }

  .user-option.active svg {
    color: var(--accent);
  }

  .option-avatar {
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, #6366f1, #a855f7);
    color: white;
    border-radius: 50%;
    font-size: 9px;
    font-weight: 600;
  }

  .option-name {
    flex: 1;
  }

  /* FAB Styles */
  .fab-container {
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
  }

  .fab-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: -1;
    animation: fadeIn 0.15s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .fab-menu {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 12px;
    animation: fabMenuIn 0.2s ease;
  }

  @keyframes fabMenuIn {
    from { opacity: 0; transform: translateY(10px) scale(0.95); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .fab-option {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    color: var(--text-primary);
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    white-space: nowrap;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    transition: all 0.15s;
  }

  .fab-option:hover {
    background: var(--bg-hover);
    border-color: rgba(139, 92, 246, 0.4);
    transform: translateX(-4px);
  }

  .fab-option svg {
    color: var(--accent);
  }

  /* FAB Panel (Search) */
  .fab-panel {
    width: 320px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
    margin-bottom: 12px;
    overflow: hidden;
    animation: fabPanelIn 0.2s ease;
  }

  @keyframes fabPanelIn {
    from { opacity: 0; transform: translateY(20px) scale(0.95); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .fab-panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--bg-secondary);
  }

  .fab-panel-header h4 {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0;
  }

  .fab-close {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--text-tertiary);
    cursor: pointer;
    border-radius: 6px;
    transition: all 0.15s;
  }

  .fab-close:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
  }

  .fab-search-form {
    display: flex;
    padding: 12px;
    gap: 8px;
  }

  .fab-search-input {
    flex: 1;
    padding: 10px 12px;
    background: var(--bg-primary);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 13px;
  }

  .fab-search-input:focus {
    outline: none;
    border-color: var(--accent);
  }

  .fab-search-input::placeholder {
    color: var(--text-tertiary);
  }

  .fab-search-btn {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--accent);
    border: none;
    border-radius: 8px;
    color: white;
    cursor: pointer;
    transition: all 0.15s;
  }

  .fab-search-btn:hover {
    background: #9b6dfa;
  }

  .fab-search-btn:disabled {
    opacity: 0.7;
  }

  .fab-results {
    max-height: 240px;
    overflow-y: auto;
    border-top: 1px solid var(--border);
  }

  .fab-result-item {
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    background: transparent;
    border: none;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    transition: background 0.15s;
    text-align: left;
  }

  .fab-result-item:last-child {
    border-bottom: none;
  }

  .fab-result-item:hover {
    background: var(--bg-hover);
  }

  .fab-result-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    flex: 1;
  }

  .fab-result-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .fab-result-meta {
    font-size: 11px;
    color: var(--text-tertiary);
  }

  .fab-add-icon {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(139, 92, 246, 0.15);
    color: var(--accent);
    border-radius: 6px;
    font-size: 16px;
    font-weight: 600;
    flex-shrink: 0;
  }

  .fab-no-results {
    padding: 20px;
    text-align: center;
    color: var(--text-tertiary);
    font-size: 13px;
  }

  .fab-main {
    width: 56px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--accent);
    border: none;
    border-radius: 16px;
    color: white;
    cursor: pointer;
    box-shadow: 0 4px 16px rgba(139, 92, 246, 0.4);
    transition: all 0.2s;
  }

  .fab-main:hover {
    transform: scale(1.05);
    box-shadow: 0 6px 20px rgba(139, 92, 246, 0.5);
  }

  .fab-main.active {
    background: #f87171;
    box-shadow: 0 4px 16px rgba(248, 113, 113, 0.4);
  }

  .fab-main.active .fab-icon {
    transform: rotate(45deg);
  }

  .fab-icon {
    transition: transform 0.2s ease;
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

    .toast.info {
      border-color: rgba(59, 130, 246, 0.5);
      background: linear-gradient(135deg, rgba(59, 130, 246, 0.14), rgba(59, 130, 246, 0.06));
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
</style>
