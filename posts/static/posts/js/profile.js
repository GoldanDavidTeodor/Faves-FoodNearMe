let modalMap = null;
let modalMarker = null;

function setProfileTab(tabName, options = {}) {
  const { updateHash = false } = options;
  const tabButtons = document.querySelectorAll('[data-profile-tab]');
  const panels = document.querySelectorAll('[data-profile-panel]');

  tabButtons.forEach(btn => {
    const isActive = btn.dataset.profileTab === tabName;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
  });

  panels.forEach(panel => {
    panel.classList.toggle('active', panel.dataset.profilePanel === tabName);
  });

  applyProfileSort();

  if (updateHash) {
    try {
      const url = new URL(window.location.href);
      // Avoid anchor scrolling; keep tab state in query string.
      url.hash = '';
      if (tabName === 'liked') {
        url.searchParams.set('tab', 'liked');
      } else {
        url.searchParams.delete('tab');
      }
      history.replaceState(null, '', url.toString());
    } catch (e) {
      // ignore
    }
  }
}

const profileSortRoot = document.getElementById('profileSort');
const profileSortButton = profileSortRoot?.querySelector('.profile-select-btn');
const profileSortLabel = profileSortRoot?.querySelector('[data-profile-select-label]');
const profileSortOptions = Array.from(profileSortRoot?.querySelectorAll('.profile-select-option') || []);
let currentProfileSort = 'newest';

const profileRatingRoot = document.getElementById('profileRatingFilter');
const profileRatingButton = profileRatingRoot?.querySelector('.profile-select-btn');
const profileRatingLabel = profileRatingRoot?.querySelector('[data-profile-select-label]');
const profileRatingOptions = Array.from(profileRatingRoot?.querySelectorAll('.profile-select-option') || []);
let currentProfileRatingFilter = 'all';

function setProfileSort(value) {
  currentProfileSort = value === 'oldest' ? 'oldest' : 'newest';
  if (profileSortLabel) {
    profileSortLabel.textContent = currentProfileSort === 'oldest' ? 'Oldest' : 'Newest';
  }
  profileSortOptions.forEach(opt => {
    opt.setAttribute('aria-selected', opt.dataset.value === currentProfileSort ? 'true' : 'false');
  });
  applyProfileSort();
}

function closeProfileSortMenu() {
  if (!profileSortRoot) return;
  profileSortRoot.classList.remove('open');
  profileSortButton?.setAttribute('aria-expanded', 'false');
}

function closeProfileRatingMenu() {
  if (!profileRatingRoot) return;
  profileRatingRoot.classList.remove('open');
  profileRatingButton?.setAttribute('aria-expanded', 'false');
}

function openProfileSortMenu() {
  if (!profileSortRoot) return;
  profileSortRoot.classList.add('open');
  profileSortButton?.setAttribute('aria-expanded', 'true');
  const selected = profileSortRoot.querySelector('.profile-select-option[aria-selected="true"]');
  (selected || profileSortOptions[0])?.focus?.();
}

function openProfileRatingMenu() {
  if (!profileRatingRoot) return;
  profileRatingRoot.classList.add('open');
  profileRatingButton?.setAttribute('aria-expanded', 'true');
  const selected = profileRatingRoot.querySelector('.profile-select-option[aria-selected="true"]');
  (selected || profileRatingOptions[0])?.focus?.();
}

function toggleProfileSortMenu() {
  if (!profileSortRoot) return;
  if (profileSortRoot.classList.contains('open')) {
    closeProfileSortMenu();
  } else {
    closeProfileRatingMenu();
    openProfileSortMenu();
  }
}

function toggleProfileRatingMenu() {
  if (!profileRatingRoot) return;
  if (profileRatingRoot.classList.contains('open')) {
    closeProfileRatingMenu();
  } else {
    closeProfileSortMenu();
    openProfileRatingMenu();
  }
}

function setProfileRatingFilter(value) {
  currentProfileRatingFilter = value === 'high' ? 'high' : 'all';
  if (profileRatingLabel) {
    profileRatingLabel.textContent = currentProfileRatingFilter === 'high' ? 'High Rated' : 'All';
  }
  profileRatingOptions.forEach(opt => {
    opt.setAttribute('aria-selected', opt.dataset.value === currentProfileRatingFilter ? 'true' : 'false');
  });
  applyProfileSort();
}

function applyProfileSort() {
  const sortValue = currentProfileSort;
  const ratingFilterValue = currentProfileRatingFilter;
  const activePanel = document.querySelector('.profile-tab-panel.active');
  const grid = activePanel?.querySelector('.mini-grid');
  if (!grid) {
    return;
  }

  const cards = Array.from(grid.querySelectorAll('.mini-post-card'));

  if (cards.length >= 2) {
    cards.sort((a, b) => {
      const aTs = parseInt(a.dataset.created || '0', 10) || 0;
      const bTs = parseInt(b.dataset.created || '0', 10) || 0;
      return sortValue === 'oldest' ? aTs - bTs : bTs - aTs;
    });

    cards.forEach(card => grid.appendChild(card));
  }

  cards.forEach(card => {
    const rating = parseFloat(card.dataset.rating || '0') || 0;
    const shouldShow = ratingFilterValue === 'high' ? rating > 7 : true;
    card.style.display = shouldShow ? '' : 'none';
  });
}

profileSortButton?.addEventListener('click', toggleProfileSortMenu);

profileRatingButton?.addEventListener('click', toggleProfileRatingMenu);

profileSortOptions.forEach(opt => {
  opt.addEventListener('click', () => {
    setProfileSort(opt.dataset.value || 'newest');
    closeProfileSortMenu();
    profileSortButton?.focus?.();
  });
});

profileRatingOptions.forEach(opt => {
  opt.addEventListener('click', () => {
    setProfileRatingFilter(opt.dataset.value || 'all');
    closeProfileRatingMenu();
    profileRatingButton?.focus?.();
  });
});

document.addEventListener('click', (e) => {
  if (!(e.target instanceof Element)) return;
  if (profileSortRoot?.classList.contains('open') && !profileSortRoot.contains(e.target)) {
    closeProfileSortMenu();
  }
  if (profileRatingRoot?.classList.contains('open') && !profileRatingRoot.contains(e.target)) {
    closeProfileRatingMenu();
  }
});

document.addEventListener('keydown', (e) => {
  const sortOpen = !!profileSortRoot?.classList.contains('open');
  const ratingOpen = !!profileRatingRoot?.classList.contains('open');
  if (!sortOpen && !ratingOpen) return;

  if (e.key === 'Escape') {
    e.preventDefault();
    if (sortOpen) {
      closeProfileSortMenu();
      profileSortButton?.focus?.();
    }
    if (ratingOpen) {
      closeProfileRatingMenu();
      profileRatingButton?.focus?.();
    }
    return;
  }

  const activeEl = document.activeElement;
  if (!(activeEl instanceof HTMLElement) || !activeEl.classList.contains('profile-select-option')) {
    return;
  }

  const options = sortOpen ? profileSortOptions : profileRatingOptions;
  const idx = options.indexOf(activeEl);
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    (options[Math.min(idx + 1, options.length - 1)] || activeEl).focus();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    (options[Math.max(idx - 1, 0)] || activeEl).focus();
  } else if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    if (sortOpen) {
      setProfileSort(activeEl.dataset.value || 'newest');
      closeProfileSortMenu();
      profileSortButton?.focus?.();
    } else {
      setProfileRatingFilter(activeEl.dataset.value || 'all');
      closeProfileRatingMenu();
      profileRatingButton?.focus?.();
    }
  }
});

document.querySelectorAll('[data-profile-tab]').forEach(btn => {
  btn.addEventListener('click', () => setProfileTab(btn.dataset.profileTab, { updateHash: true }));
});

let initialTab = 'posts';
try {
  const url = new URL(window.location.href);
  const tab = (url.searchParams.get('tab') || '').trim();
  if (tab === 'liked') {
    initialTab = 'liked';
  } else if (location.hash === '#liked') {
    initialTab = 'liked';
  }
} catch (e) {
  if (location.hash === '#liked') {
    initialTab = 'liked';
  }
}

setProfileTab(initialTab, { updateHash: initialTab === 'liked' && location.hash === '#liked' });

// If we landed on a legacy #liked URL, the browser may have auto-scrolled.
// Ensure the profile header/card stays aligned at the top.
if (location.hash === '#liked') {
  try {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  } catch (e) {
    window.scrollTo(0, 0);
  }
}

// Ensure initial sort is applied
setProfileRatingFilter('all');
setProfileSort('newest');

const commentModal = document.getElementById('commentModal');
const commentModalClose = document.getElementById('commentModalClose');
const commentModalTitle = document.getElementById('comment-modal-title');
const commentModalImages = document.getElementById('commentModalImages');
const commentModalList = document.getElementById('commentModalList');
const commentModalForm = document.getElementById('commentModalForm');
const commentModalUserName = document.getElementById('commentModalUserName');
const commentModalUserAvatar = document.getElementById('commentModalUserAvatar');
const commentModalDescription = document.getElementById('commentModalDescription');
const commentModalDate = document.getElementById('commentModalDate');

function setActiveModalTab(targetId) {
  document.querySelectorAll('[data-modal-tab]').forEach(b => b.classList.remove('active'));
  document.querySelector(`[data-modal-tab="${targetId}"]`)?.classList.add('active');
  document.getElementById('modal-images').style.display = targetId === 'modal-images' ? 'block' : 'none';
  document.getElementById('modal-location').style.display = targetId === 'modal-location' ? 'block' : 'none';
  if (targetId === 'modal-location' && modalMap) {
    setTimeout(() => modalMap.invalidateSize(), 60);
  }
}

document.querySelectorAll('[data-modal-tab]').forEach(btn => {
  btn.addEventListener('click', () => setActiveModalTab(btn.dataset.modalTab));
});

function renderModalImagesGrid(images) {
  if (!images.length) {
    commentModalImages.innerHTML = '<div class="modal-no-images">No images</div>';
    return;
  }
  commentModalImages.innerHTML = images
    .map(img => `<div class="modal-image-tile"><img src="${img.src}" alt="${img.alt}"></div>`)
    .join('');
}

function openCommentModalFromCard(card) {
  const username = card.querySelector('.mini-user-name')?.textContent?.trim() || 'Post';
  const title = card.querySelector('.mini-title')?.textContent?.trim() || 'Post';
  const desc = card.querySelector('.mini-desc')?.textContent?.trim() || '';
  const date = card.querySelector('.mini-date')?.textContent?.trim() || '';
  const avatarImg = card.querySelector('.mini-avatar');
  const avatarPlaceholder = card.querySelector('.mini-avatar-placeholder');
  const modalData = card.querySelector('.comment-modal-data');

  commentModalTitle.textContent = title;
  if (commentModalUserName) commentModalUserName.textContent = username;
  if (commentModalDescription) commentModalDescription.textContent = desc;
  if (commentModalDate) commentModalDate.textContent = date;

  if (commentModalUserAvatar) {
    if (avatarImg?.getAttribute('src')) {
      commentModalUserAvatar.innerHTML = `<img class="mini-avatar" src="${avatarImg.getAttribute('src')}" alt="">`;
    } else {
      const initial = avatarPlaceholder?.textContent?.trim() || username.slice(0, 1).toUpperCase();
      commentModalUserAvatar.innerHTML = `<div class="mini-avatar-placeholder">${initial}</div>`;
    }
  }

  if (!modalData) {
    commentModalList.innerHTML = '<p class="comment-empty">No comments yet.</p>';
    renderModalImagesGrid([]);
    return;
  }

  commentModalList.innerHTML = modalData.querySelector('[data-modal-comments]')?.innerHTML || '<p class="comment-empty">No comments yet.</p>';

  const images = Array.from(modalData.querySelectorAll('[data-modal-images] img')).map(img => ({
    src: img.getAttribute('src'),
    alt: img.getAttribute('alt') || '',
  }));
  renderModalImagesGrid(images);

  const postId = modalData.dataset.postId;
  if (commentModalForm && postId) {
    commentModalForm.action = `/posts/${postId}/comment/`;
  }

  const lat = parseFloat(modalData.dataset.lat);
  const lng = parseFloat(modalData.dataset.lng);
  if (!Number.isNaN(lat) && !Number.isNaN(lng) && window.L) {
    if (!modalMap) {
      modalMap = L.map('modal-map').setView([lat, lng], 15);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OSM' }).addTo(modalMap);
      modalMarker = L.marker([lat, lng]).addTo(modalMap);
    } else {
      modalMap.setView([lat, lng], 15);
      modalMarker?.setLatLng([lat, lng]);
    }
  }

  setActiveModalTab('modal-images');
  commentModal.classList.add('active');
  commentModal.setAttribute('aria-hidden', 'false');
}

document.querySelectorAll('[data-post-card]').forEach(card => {
  card.addEventListener('click', (e) => {
    if (e.target.closest('form, button, a, textarea, input')) {
      return;
    }
    openCommentModalFromCard(card);
  });
});

function closeCommentModal() {
  commentModal.classList.remove('active');
  commentModal.setAttribute('aria-hidden', 'true');
}

commentModalClose?.addEventListener('click', closeCommentModal);
commentModal?.addEventListener('click', (e) => {
  if (e.target === commentModal) {
    closeCommentModal();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && commentModal.classList.contains('active')) {
    closeCommentModal();
  }
});

const ratingModal = document.getElementById('ratingModal');
const ratingChoices = ratingModal.querySelectorAll('.rating-choice');
const ratingCancel = document.getElementById('ratingCancel');
let activeRateForm = null;

function closeRatingModal() {
  ratingModal.classList.remove('active');
  ratingModal.setAttribute('aria-hidden', 'true');
  activeRateForm = null;
}

function openRatingModal(form, currentValue) {
  activeRateForm = form;
  ratingChoices.forEach(choice => {
    choice.classList.toggle('active', choice.dataset.value === currentValue);
  });
  ratingModal.classList.add('active');
  ratingModal.setAttribute('aria-hidden', 'false');
}

document.querySelectorAll('[data-rate-trigger]').forEach(btn => {
  btn.addEventListener('click', () => {
    const form = btn.closest('[data-rate-form]');
    const ratingInput = form.querySelector('input[name="rating"]');
    openRatingModal(form, ratingInput.value || btn.dataset.currentRating || '');
  });
});

ratingChoices.forEach(choice => {
  choice.addEventListener('click', () => {
    if (!activeRateForm) {
      return;
    }

    const ratingInput = activeRateForm.querySelector('input[name="rating"]');
    ratingInput.value = choice.dataset.value;
    activeRateForm.submit();
  });
});

ratingCancel.addEventListener('click', closeRatingModal);

ratingModal.addEventListener('click', (event) => {
  if (event.target === ratingModal) {
    closeRatingModal();
  }
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && ratingModal.classList.contains('active')) {
    closeRatingModal();
  }
});

const commentModalText = document.getElementById('commentModalText');
const commentModalParentId = document.getElementById('commentModalParentId');
const commentModalReplyingHint = document.getElementById('commentModalReplyingHint');
const commentModalReplyingUser = document.getElementById('commentModalReplyingUser');
const commentModalReplyCancel = document.getElementById('commentModalReplyCancel');

function clearModalReplyTarget() {
  if (!commentModalParentId || !commentModalReplyingHint || !commentModalText) {
    return;
  }
  commentModalParentId.value = '';
  commentModalReplyingHint.classList.remove('active');
  commentModalText.placeholder = 'Add a comment...';
}

function setModalReplyTarget(parentId, username) {
  if (!commentModalParentId || !commentModalReplyingHint || !commentModalReplyingUser || !commentModalText) {
    return;
  }
  commentModalParentId.value = String(parentId);
  commentModalReplyingUser.textContent = username;
  commentModalReplyingHint.classList.add('active');
  commentModalText.placeholder = `Reply to ${username}...`;
  commentModalText.focus();
}

commentModalList?.addEventListener('click', (event) => {
  const replyBtn = event.target.closest('.reply-btn');
  if (replyBtn) {
    setModalReplyTarget(replyBtn.dataset.replyParent || '', replyBtn.dataset.replyUsername || '');
    return;
  }

  const repliesToggle = event.target.closest('[data-replies-toggle]');
  if (!repliesToggle) {
    return;
  }

  const thread = repliesToggle.parentElement?.querySelector('.comment-replies');
  if (!thread) {
    return;
  }

  const isOpen = thread.classList.toggle('active');
  const count = repliesToggle.dataset.repliesCount || '0';
  repliesToggle.textContent = isOpen ? 'Hide replies' : `View replies (${count})`;
});

commentModalReplyCancel?.addEventListener('click', clearModalReplyTarget);
