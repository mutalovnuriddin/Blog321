(function () {
    'use strict';

    const root = document.querySelector('[data-notif-root]');
    if (!root) return;

    const bell = root.querySelector('[data-notif-bell]');
    const badge = root.querySelector('[data-notif-badge]');
    const dropdown = root.querySelector('[data-notif-dropdown]');
    const listEl = root.querySelector('[data-notif-list]');
    const emptyEl = root.querySelector('[data-notif-empty]');
    const markAllButton = root.querySelector('[data-notif-mark-all]');
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')
        ? document.querySelector('[name=csrfmiddlewaretoken]').value : '';

    const VERB_ICONS = { like: '❤️', comment: '💬', follow: '👤', message: '✉️' };
    let unreadCount = 0;
    let isOpen = false;
    let socket = null;
    let reconnectTimer = null;

    function setUnreadCount(count) {
        unreadCount = count;
        badge.textContent = count > 99 ? '99+' : String(count);
        badge.hidden = count === 0;
    }

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value == null ? '' : String(value);
        return div.innerHTML;
    }

    function itemHtml(n) {
        const icon = VERB_ICONS[n.verb] || '🔔';
        const preview = n.preview
            ? '<p class="notif-preview">' + escapeHtml(n.preview) + '</p>'
            : '';
        return '<li class="notif-item' + (n.is_read ? '' : ' is-unread') + '" data-notif-item data-notif-id="' + escapeHtml(n.id) + '">' +
            '<a class="notif-link" href="' + escapeHtml(n.url) + '" data-notif-link>' +
                '<img class="notif-avatar" src="' + escapeHtml(n.avatar_url) + '" alt="">' +
                '<span class="notif-body">' +
                    '<p class="notif-text"><strong>' + escapeHtml(n.actor_name) + '</strong> ' +
                        '<span class="notif-verb-icon" aria-hidden="true">' + icon + '</span> ' +
                        escapeHtml(n.text) + '</p>' +
                    preview +
                    '<span class="notif-time">' + escapeHtml(n.created_at) + '</span>' +
                '</span>' +
                (n.is_read ? '' : '<span class="notif-dot" aria-hidden="true"></span>') +
            '</a></li>';
    }

    function showToast(n) {
        const toast = document.createElement('div');
        toast.className = 'notif-toast';
        toast.innerHTML =
            '<img class="notif-avatar" src="' + escapeHtml(n.avatar_url) + '" alt="">' +
            '<p class="notif-text"><strong>' + escapeHtml(n.actor_name) + '</strong> ' +
                '<span class="notif-verb-icon" aria-hidden="true">' + (VERB_ICONS[n.verb] || '🔔') + '</span> ' +
                escapeHtml(n.text) + '</p>';
        document.body.appendChild(toast);
        requestAnimationFrame(function () { toast.classList.add('is-visible'); });
        setTimeout(function () {
            toast.classList.remove('is-visible');
            setTimeout(function () { toast.remove(); }, 300);
        }, 4200);
    }

    function markRead(id) {
        const body = new URLSearchParams();
        if (id) body.append('id', id);
        return fetch(window.NOTIFICATIONS_READ_URL, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken },
            body: body,
            credentials: 'same-origin',
        }).then(function (res) {
            if (!res.ok) throw new Error('bad status');
            return res.json();
        }).catch(function () {});
    }

    function loadNotifications() {
        fetch(window.NOTIFICATIONS_DATA_URL, { credentials: 'same-origin' })
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (data) {
                if (!data) return;
                setUnreadCount(data.unread_count);
                renderList(data.notifications || []);
            })
            .catch(function () {});
    }

    function renderList(items) {
        listEl.innerHTML = items.map(itemHtml).join('');
        emptyEl.hidden = items.length > 0;
        markAllButton.style.visibility = unreadCount > 0 ? 'visible' : 'hidden';
    }

    function prependItem(n) {
        emptyEl.hidden = true;
        listEl.insertAdjacentHTML('afterbegin', itemHtml(n));
    }

    function toggle(open) {
        isOpen = typeof open === 'boolean' ? open : !isOpen;
        dropdown.hidden = !isOpen;
        bell.classList.toggle('is-open', isOpen);
        bell.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        if (isOpen) loadNotifications();
    }

    function closeIfOutside(event) {
        if (!isOpen) return;
        if (root.contains(event.target)) return;
        toggle(false);
    }

    function connect() {
        if (!window.NOTIFY_WS_URL || socket) return;
        socket = new WebSocket(window.NOTIFY_WS_URL);

        socket.onmessage = function (event) {
            let data;
            try {
                data = JSON.parse(event.data);
            } catch (e) {
                return;
            }
            if (data.type === 'unread_count') {
                setUnreadCount(data.count);
            } else if (data.type === 'new_notification') {
                setUnreadCount(data.unread_count);
                if (isOpen) prependItem(data.notification);
                showToast(data.notification);
                bell.classList.remove('is-new');
                void bell.offsetWidth; // animatsiyani qayta ishga tushirish
                bell.classList.add('is-new');
            }
        };

        socket.onclose = function () {
            socket = null;
            reconnectTimer = setTimeout(connect, 4000);
        };

        socket.onerror = function () {
            if (socket) { socket.close(); }
        };
    }

    bell.addEventListener('click', function (event) {
        event.preventDefault();
        toggle();
    });

    markAllButton.addEventListener('click', function () {
        markRead(null).then(function (data) {
            if (data && typeof data.unread_count === 'number') {
                setUnreadCount(data.unread_count);
            }
            listEl.querySelectorAll('.notif-item').forEach(function (item) {
                item.classList.remove('is-unread');
                const dot = item.querySelector('.notif-dot');
                if (dot) dot.remove();
            });
            markAllButton.style.visibility = 'hidden';
        });
    });

    listEl.addEventListener('click', function (event) {
        const link = event.target.closest('[data-notif-link]');
        if (!link) return;
        const item = link.closest('[data-notif-item]');
        const id = item ? item.getAttribute('data-notif-id') : '';
        if (item && item.classList.contains('is-unread')) {
            item.classList.remove('is-unread');
            const dot = item.querySelector('.notif-dot');
            if (dot) dot.remove();
            if (unreadCount > 0) setUnreadCount(unreadCount - 1);
            markRead(id);
        }
    });

    document.addEventListener('click', closeIfOutside);
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && isOpen) toggle(false);
    });

    setUnreadCount(0);
    loadNotifications();
    connect();
})();
