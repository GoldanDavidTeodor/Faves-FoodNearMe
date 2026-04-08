(function () {
  document.addEventListener('DOMContentLoaded', function () {
    const thread = document.getElementById('thread');
    if (thread) {
      thread.scrollTop = thread.scrollHeight;
    }

    const search = document.getElementById('followersSearch');
    if (search) {
      search.addEventListener('input', () => {
        const query = (search.value || '').trim().toLowerCase();
        document.querySelectorAll('[data-follower-row]').forEach(row => {
          const username = row.getAttribute('data-username') || '';
          row.style.display = !query || username.includes(query) ? '' : 'none';
        });
      });
    }
  });
})();
