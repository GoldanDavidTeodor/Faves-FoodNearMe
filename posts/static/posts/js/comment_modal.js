(function () {
  document.addEventListener('DOMContentLoaded', function () {
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

    const commentModalText = document.getElementById('commentModalText');
    const commentModalParentId = document.getElementById('commentModalParentId');
    const commentModalReplyingHint = document.getElementById('commentModalReplyingHint');
    const commentModalReplyingUser = document.getElementById('commentModalReplyingUser');
    const commentModalReplyCancel = document.getElementById('commentModalReplyCancel');

    if (!commentModal || !commentModalTitle || !commentModalImages || !commentModalList) {
      return;
    }

    let modalMap = null;
    let modalMarker = null;

    function setActiveModalTab(targetId) {
      document.querySelectorAll('[data-modal-tab]').forEach(b => b.classList.remove('active'));
      document.querySelector(`[data-modal-tab="${targetId}"]`)?.classList.add('active');

      const imagesPanel = document.getElementById('modal-images');
      const locationPanel = document.getElementById('modal-location');
      if (imagesPanel) imagesPanel.style.display = targetId === 'modal-images' ? 'block' : 'none';
      if (locationPanel) locationPanel.style.display = targetId === 'modal-location' ? 'block' : 'none';

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

    commentModalList.addEventListener('click', (event) => {
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

      clearModalReplyTarget();

      if (!modalData) {
        commentModalList.innerHTML = '<p class="comment-empty">No comments yet.</p>';
        renderModalImagesGrid([]);
      } else {
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
      }

      setActiveModalTab('modal-images');
      commentModal.classList.add('active');
      commentModal.setAttribute('aria-hidden', 'false');
    }

    function closeCommentModal() {
      commentModal.classList.remove('active');
      commentModal.setAttribute('aria-hidden', 'true');
    }

    document.querySelectorAll('[data-post-card]').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('form, button, a, textarea, input')) {
          return;
        }
        openCommentModalFromCard(card);
      });
    });

    commentModalClose?.addEventListener('click', closeCommentModal);
    commentModal.addEventListener('click', (e) => {
      if (e.target === commentModal) {
        closeCommentModal();
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && commentModal.classList.contains('active')) {
        closeCommentModal();
      }
    });
  });
})();
