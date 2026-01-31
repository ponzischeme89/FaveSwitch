<script>
  import { createEventDispatcher } from 'svelte';
  import { api } from '../api.js';
  import { getServerIcon as getSharedServerIcon, usesNativeColor } from '../serverIcons.js';

  export let serverId = null;
  export let item;
  export let user = null;
  export let users = []; // All available users for popover
  export let onUserPick = null; // optional: open inline picker
  export let serverLabel = '';
  export let serverType = '';
  export let onOpen = null; // optional: quick preview handler
  export let onFavorite = null; // optional: immediate favourite handler
  export let onShowPopover = null; // optional: show quick-add popover

  const dispatch = createEventDispatcher();

  let activeUser = user;
  let isFavorite = item.UserData?.IsFavorite || item.isFavorite || false;
  let toggling = false;
  let showUserPicker = false;
  let pendingFavorite = false;
  let cardEl;

  async function toggleFavorite(evt = null, skipPrompt = false) {
    // Shift+Click: Quick add via callback
    if (evt?.shiftKey && onFavorite) {
      onFavorite(item);
      return;
    }

    // Alt/Option+Click: Show popover for advanced options
    if (evt?.altKey && onShowPopover) {
      onShowPopover(item, evt);
      return;
    }

    if (users?.length > 1 && !skipPrompt && !showUserPicker) {
      showUserPicker = true;
      pendingFavorite = true;
      return;
    }

    if (!activeUser || !serverId || toggling) return;

    toggling = true;
    try {
      if (isFavorite) {
        await api.removeFavorite(serverId, activeUser.Id, item.Id);
        isFavorite = false;
        dispatch('favoriteChanged', { item, isFavorite: false });
      } else {
        if ((serverLabel || '').toLowerCase() === 'audiobookshelf' || serverType === 'audiobookshelf') {
          await api.addAbsUserFavourite(serverId, activeUser.Name || '', item.Id);
        } else {
          await api.addFavorite(serverId, activeUser.Id, item.Id, activeUser.Name || '');
        }
        isFavorite = true;
        dispatch('favoriteChanged', { item, isFavorite: true });
      }
    } catch (e) {
      console.error('Failed to toggle favorite:', e);
    } finally {
      toggling = false;
      pendingFavorite = false;
    }
  }

  function getYear(item) {
    return item.ProductionYear || item.PremiereDate?.substring(0, 4) || '';
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
        return api.getImageUrl(serverId, item.Id, 'Primary', 300, item.ImageTags.Primary);
      }
      return api.getImageUrl(serverId, item.Id, 'Primary', 300);
    }
    return null;
  }

  function getServerIconUrl(type) {
    return getSharedServerIcon(type);
  }

  $: isNativeColor = usesNativeColor(serverLabel);

  function handleClick(event) {
    // Shift-click: instant favourite for speed
    if (event.shiftKey && onFavorite) {
      onFavorite(item);
      return;
    }
    // Regular click: open quick preview if provided
    if (onOpen) {
      onOpen(item);
    }
  }

  function handleCardKeydown(event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleClick(event);
    }
  }

  function requestUserPick(event) {
    event.stopPropagation();
    showUserPicker = !showUserPicker;
    pendingFavorite = false;
    if (onUserPick) onUserPick(item);
  }

  function selectActiveUser(u) {
    activeUser = u;
    showUserPicker = false;
    dispatch('userSelected', { user: u, item });
    if (pendingFavorite) {
      pendingFavorite = false;
      toggleFavorite(null, true);
    }
  }

  function handleWindowClick(event) {
    if (showUserPicker && cardEl && !cardEl.contains(event.target)) {
      showUserPicker = false;
      pendingFavorite = false;
    }
  }

  $: if (user && (!activeUser || activeUser?.Id !== user?.Id)) {
    activeUser = user;
  }
</script>

<svelte:window on:click={handleWindowClick} />
<div
  class="media-card"
  role="button"
  tabindex="0"
  aria-label={`${item.Type}: ${item.Name}`}
  bind:this={cardEl}
  on:click|stopPropagation={handleClick}
  on:keydown|stopPropagation={handleCardKeydown}
>
  {#if serverLabel}
    <span class="server-tag">
      {#if getServerIconUrl(serverLabel)}
        <img src={getServerIconUrl(serverLabel)} alt={`${serverLabel} icon`} class:native-color={isNativeColor} />
      {:else}
        {serverLabel}
      {/if}
    </span>
  {/if}
  {#if getImageUrl(item)}
    <img src={getImageUrl(item)} alt={item.Name} loading="lazy" />
  {:else}
    <div class="no-image">
      <span class="text-[--text-tertiary] text-sm">No Image</span>
    </div>
  {/if}

  <div class="info">
    <div class="title" title={item.Name}>{item.Name}</div>
    <div class="meta">
      {#if getYear(item)}
        <span class="year">{getYear(item)}</span>
      {/if}
      <span class="type">{item.Type}</span>
      {#if getStatusLabel(item)}
        <span class="status">{getStatusLabel(item)}</span>
      {/if}
    </div>

    <div class="actions">
      {#if activeUser}
        <button
          class="fav-btn"
          class:is-favorite={isFavorite}
          on:click|stopPropagation={(e) => toggleFavorite(e)}
          disabled={toggling}
          title={isFavorite ? 'Remove from favorites' : 'Add to favorites (⇧+Click: Quick add, ⌥+Click: Options)'}
        >
          {#if toggling}
            <span class="spinner"></span>
          {:else}
            <svg width="18" height="18" viewBox="0 0 24 24" fill={isFavorite ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="2">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
          {/if}
        </button>
      {/if}
      {#if users?.length > 1 && showUserPicker}
        <div
          class="user-popover"
          role="menu"
          tabindex="-1"
          aria-label="Select user"
          on:click|stopPropagation
          on:keydown|stopPropagation
        >
          {#each users as u (u.Id)}
            <button class="user-option" class:active={activeUser?.Id === u.Id} on:click={() => selectActiveUser(u)}>
              <span class="option-avatar">{u.Name?.charAt(0) || '?'}</span>
              <span class="option-name">{u.Name}</span>
            </button>
          {/each}
        </div>
      {/if}
    </div>
  </div>
</div>

<style>
  .media-card {
    position: relative;
  }

  img {
    width: 100%;
    aspect-ratio: 2/3;
    object-fit: cover;
    border-radius: 12px 12px 0 0;
    display: block;
  }

  .no-image {
    width: 100%;
    aspect-ratio: 2/3;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-primary);
    border-radius: 12px 12px 0 0;
  }

  .info {
    padding: 12px;
    position: relative;
  }

  .title {
    font-weight: 600;
    font-size: 14px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--text-primary);
    margin-bottom: 4px;
  }

  .meta {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }

  .server-tag {
    position: absolute;
    top: 8px;
    left: 8px;
    padding: 4px 8px;
    background: rgba(0, 0, 0, 0.65);
    color: #fff;
    border-radius: 999px;
    font-size: 11px;
    z-index: 2;
    backdrop-filter: blur(4px);
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .server-tag img {
    width: 14px;
    height: 14px;
    filter: brightness(0) invert(1);
  }

  .server-tag img.native-color {
    filter: none;
  }

  .year {
    color: var(--text-secondary);
  }

  .type {
    color: var(--accent);
    text-transform: uppercase;
    font-weight: 500;
    font-size: 10px;
    padding: 2px 6px;
    background: rgba(139, 92, 246, 0.15);
    border-radius: 4px;
  }

  .status {
    color: #34d399;
    text-transform: uppercase;
    font-weight: 600;
    font-size: 10px;
    padding: 2px 6px;
    background: rgba(16, 185, 129, 0.15);
    border-radius: 4px;
  }

  .actions {
    position: absolute;
    top: -36px;
    right: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .user-popover {
    position: absolute;
    bottom: 110%;
    right: 0;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
    z-index: 90;
    min-width: 180px;
    overflow: hidden;
    animation: dropdownIn 0.15s ease;
    max-height: 240px;
    overflow-y: auto;
  }

  .user-option {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 14px;
    background: transparent;
    border: none;
    color: var(--text-primary);
    text-align: left;
    cursor: pointer;
    transition: background 0.12s;
  }

  .user-option:hover {
    background: var(--bg-hover);
  }

  .user-option.active {
    background: rgba(139, 92, 246, 0.12);
  }

  .option-avatar {
    width: 24px;
    height: 24px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, var(--accent), #9b6dfa);
    color: white;
    border-radius: 50%;
    font-size: 11px;
    font-weight: 700;
  }

  .option-name {
    flex: 1;
    font-size: 13px;
    line-height: 1.2;
  }

  @keyframes dropdownIn {
    from { opacity: 0; transform: translateY(6px) scale(0.98); }
    to { opacity: 1; transform: translateY(0) scale(1); }
  }

  .fav-btn {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    border: none;
    border-radius: 8px;
    font-size: 18px;
    cursor: pointer;
    color: var(--text-secondary);
    transition: all 0.2s;
  }

  .fav-btn:hover {
    background: rgba(0, 0, 0, 0.8);
    color: #fbbf24;
  }

  .fav-btn.is-favorite {
    color: #fbbf24;
  }

  .fav-btn:disabled {
    opacity: 0.5;
    cursor: wait;
  }

  .fav-btn .spinner {
    width: 14px;
    height: 14px;
    border: 2px solid rgba(255, 255, 255, 0.2);
    border-top-color: currentColor;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
