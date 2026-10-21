(() => {
    const toast = document.querySelector('[data-toast]');
    const commentLoads = new WeakMap();
    let toastTimer;
    let previousFocus;

    function showToast(message) {
        if (!toast) return;
        toast.textContent = message;
        toast.classList.add('is-visible');
        window.clearTimeout(toastTimer);
        toastTimer = window.setTimeout(() => toast.classList.remove('is-visible'), 2600);
    }

    async function postForm(form) {
        const response = await fetch(form.action, {
            method: 'POST',
            body: new FormData(form),
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
            },
            credentials: 'same-origin',
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.errors ? 'Izoh matnini tekshiring.' : 'Amalni bajarib bo‘lmadi.');
        }
        return data;
    }

    async function getJson(url) {
        const response = await fetch(url, {
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
            },
            credentials: 'same-origin',
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Ma’lumotlarni yuklab bo‘lmadi.');
        }
        return data;
    }

    function createComment(commentData) {
        const item = document.createElement('article');
        item.className = 'comment-item';
        item.dataset.commentId = commentData.id;

        const avatarLink = document.createElement('a');
        avatarLink.className = 'comment-avatar-link';
        avatarLink.href = commentData.profile_url;
        const avatar = document.createElement('img');
        avatar.className = 'comment-avatar';
        avatar.src = commentData.avatar_url;
        avatar.alt = '';
        avatar.loading = 'lazy';
        avatarLink.append(avatar);

        const body = document.createElement('div');
        body.className = 'comment-body';
        const heading = document.createElement('div');
        heading.className = 'comment-heading';
        const username = document.createElement('a');
        username.className = 'comment-username';
        username.href = commentData.profile_url;
        username.textContent = `@${commentData.username}`;
        const time = document.createElement('time');
        time.className = 'comment-time';
        time.dateTime = commentData.created_at_iso;
        time.textContent = commentData.created_at;
        heading.append(username, time);

        const text = document.createElement('p');
        text.className = 'comment-text';
        text.textContent = commentData.text;
        body.append(heading, text);
        item.append(avatarLink, body);
        return item;
    }

    async function loadComments(card) {
        const list = card.querySelector('[data-comments-list]');
        if (list.dataset.commentsLoaded === 'true') return;
        if (commentLoads.has(list)) return commentLoads.get(list);

        const loading = (async () => {
            try {
                const data = await getJson(list.dataset.commentsUrl);
                const fragment = document.createDocumentFragment();
                if (data.comments.length) {
                    data.comments.forEach((comment) => fragment.append(createComment(comment)));
                } else {
                    const empty = document.createElement('p');
                    empty.className = 'comments-status';
                    empty.textContent = 'Hali izoh yo‘q. Birinchi bo‘lib fikr bildiring.';
                    fragment.append(empty);
                }
                list.replaceChildren(fragment);
                list.dataset.commentsLoaded = 'true';
                card.querySelectorAll('[data-comments-count]').forEach((count) => {
                    count.textContent = data.comments_count;
                });
            } catch (error) {
                const status = document.createElement('p');
                status.className = 'comments-status comments-error';
                status.textContent = error.message || 'Izohlarni yuklab bo‘lmadi.';
                list.replaceChildren(status);
                throw error;
            } finally {
                commentLoads.delete(list);
            }
        })();

        commentLoads.set(list, loading);
        return loading;
    }

    document.querySelectorAll('[data-like-form]').forEach((form) => {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const button = form.querySelector('[data-like-button]');
            if (button.disabled) return;
            button.disabled = true;
            try {
                const data = await postForm(form);
                button.classList.toggle('is-liked', data.liked);
                button.setAttribute('aria-pressed', String(data.liked));
                const count = form.closest('[data-post-card]').querySelector('[data-likes-count]');
                count.textContent = data.likes_count;
                const summary = form.closest('[data-post-card]').querySelector('.like-summary strong');
                if (summary) summary.textContent = data.likes_count;
            } catch (error) {
                showToast(error.message || 'Layk yuborilmadi. Qayta urinib ko‘ring.');
            } finally {
                button.disabled = false;
            }
        });
    });

    document.querySelectorAll('[data-comments-toggle]').forEach((button) => {
        button.addEventListener('click', async () => {
            const card = button.closest('[data-post-card]');
            const list = card.querySelector('[data-comments-list]');
            const isOpening = list.hidden;
            list.hidden = !isOpening;
            button.setAttribute('aria-expanded', String(isOpening));
            if (isOpening) {
                try {
                    await loadComments(card);
                } catch (error) {
                    showToast(error.message || 'Izohlarni yuklab bo‘lmadi.');
                }
            }
        });
    });

    document.querySelectorAll('[data-comment-form]').forEach((form) => {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const input = form.querySelector('[name="text"]');
            const errorTarget = form.querySelector('[data-comment-error]');
            const button = form.querySelector('button[type="submit"]');
            const card = form.closest('[data-post-card]');
            const list = card.querySelector('[data-comments-list]');
            const commentsWereLoaded = list.dataset.commentsLoaded === 'true';
            errorTarget.textContent = '';
            button.disabled = true;
            try {
                const data = await postForm(form);
                const toggle = card.querySelector('[data-comments-toggle]');
                list.hidden = false;
                toggle.setAttribute('aria-expanded', 'true');
                if (commentsWereLoaded) {
                    const comment = createComment(data.comment);
                    const emptyMessage = list.querySelector('.comments-status');
                    if (emptyMessage) emptyMessage.remove();
                    list.append(comment);
                } else {
                    try {
                        await loadComments(card);
                        const commentIsRendered = Array.from(
                            list.querySelectorAll('[data-comment-id]'),
                        ).some((item) => item.dataset.commentId === String(data.comment.id));
                        if (!commentIsRendered) {
                            const emptyMessage = list.querySelector('.comments-status');
                            if (emptyMessage) emptyMessage.remove();
                            list.append(createComment(data.comment));
                        }
                    } catch {
                        list.replaceChildren(createComment(data.comment));
                        list.dataset.commentsLoaded = 'true';
                        showToast('Izoh qo‘shildi, lekin oldingi izohlarni yuklab bo‘lmadi.');
                    }
                }
                card.querySelectorAll('[data-comments-count]').forEach((count) => {
                    count.textContent = data.comments_count;
                });
                list.scrollTop = list.scrollHeight;
                input.value = '';
            } catch (error) {
                errorTarget.textContent = error.message || 'Izoh yuborilmadi. Qayta urinib ko‘ring.';
            } finally {
                button.disabled = false;
                input.focus();
            }
        });
    });

    const postDeleteModal = document.querySelector('[data-post-delete-modal]');
    const postDeleteForm = postDeleteModal?.querySelector('[data-post-delete-form]');
    const postDeleteDescription = postDeleteModal?.querySelector('[data-post-delete-description]');
    let postMenuFocus;

    document.querySelectorAll('[data-post-menu-toggle]').forEach((button) => {
        button.addEventListener('click', (event) => {
            event.stopPropagation();
            const menu = document.getElementById(button.getAttribute('aria-controls'));
            const willOpen = menu.hidden;
            document.querySelectorAll('[data-post-menu-dropdown]').forEach((otherMenu) => {
                otherMenu.hidden = true;
                otherMenu.closest('.post-menu-wrap')
                    .querySelector('[data-post-menu-toggle]')
                    .setAttribute('aria-expanded', 'false');
            });
            menu.hidden = !willOpen;
            button.setAttribute('aria-expanded', String(willOpen));
        });
    });

    document.querySelectorAll('[data-post-delete-open]').forEach((button) => {
        button.addEventListener('click', () => {
            if (!postDeleteModal || !postDeleteForm || !postDeleteDescription) return;
            postMenuFocus = button.closest('.post-menu-wrap')
                .querySelector('[data-post-menu-toggle]');
            postDeleteForm.action = button.dataset.deleteUrl;
            postDeleteDescription.textContent =
                `"${button.dataset.postTitle}" postini rostdan ham o‘chirmoqchimisiz? Bu amalni bekor qilib bo‘lmaydi.`;
            button.closest('[data-post-menu-dropdown]').hidden = true;
            postMenuFocus.setAttribute('aria-expanded', 'false');
            postDeleteModal.hidden = false;
            document.body.classList.add('modal-open');
            postDeleteModal.querySelector('[data-post-delete-cancel]').focus();
        });
    });

    if (postDeleteModal) {
        function closePostDeleteModal() {
            postDeleteModal.hidden = true;
            document.body.classList.remove('modal-open');
            if (postMenuFocus instanceof HTMLElement) postMenuFocus.focus();
        }

        postDeleteModal.querySelectorAll('[data-post-delete-cancel]').forEach((button) => {
            button.addEventListener('click', closePostDeleteModal);
        });

        postDeleteForm?.addEventListener('submit', (event) => {
            if (!postDeleteForm.action || postDeleteForm.action.endsWith('/')) {
                event.preventDefault();
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            if (!postDeleteModal.hidden) {
                closePostDeleteModal();
                return;
            }
            document.querySelectorAll('[data-post-menu-dropdown]').forEach((menu) => {
                menu.hidden = true;
                menu.closest('.post-menu-wrap')
                    .querySelector('[data-post-menu-toggle]')
                    .setAttribute('aria-expanded', 'false');
            });
        });
    }

    document.addEventListener('click', (event) => {
        if (event.target.closest('.post-menu-wrap')) return;
        document.querySelectorAll('[data-post-menu-dropdown]').forEach((menu) => {
            menu.hidden = true;
            menu.closest('.post-menu-wrap')
                .querySelector('[data-post-menu-toggle]')
                .setAttribute('aria-expanded', 'false');
        });
    });

    const connectionsModal = document.querySelector('[data-connections-modal]');
    if (connectionsModal) {
        const dialogTitle = connectionsModal.querySelector('[data-connections-title]');
        const list = connectionsModal.querySelector('[data-connections-list]');

        function closeConnections() {
            connectionsModal.hidden = true;
            document.body.classList.remove('modal-open');
            if (previousFocus instanceof HTMLElement) previousFocus.focus();
        }

        document.querySelectorAll('[data-connections-url]').forEach((button) => {
            button.addEventListener('click', async () => {
                previousFocus = button;
                dialogTitle.textContent = button.dataset.connectionsTitle;
                list.replaceChildren();
                const loading = document.createElement('p');
                loading.className = 'connections-status';
                loading.textContent = 'Ro‘yxat yuklanmoqda…';
                list.append(loading);
                connectionsModal.hidden = false;
                document.body.classList.add('modal-open');
                connectionsModal.querySelector('[data-connections-close]').focus();

                try {
                    const data = await getJson(button.dataset.connectionsUrl);
                    if (connectionsModal.hidden) return;
                    if (!data.users.length) {
                        const empty = document.createElement('p');
                        empty.className = 'connections-status';
                        empty.textContent = 'Bu ro‘yxat hozircha bo‘sh.';
                        list.replaceChildren(empty);
                        return;
                    }

                    const fragment = document.createDocumentFragment();
                    data.users.forEach((user) => {
                        const row = document.createElement('a');
                        row.className = 'connection-user';
                        row.href = user.profile_url;
                        const avatar = document.createElement('img');
                        avatar.className = 'connection-avatar';
                        avatar.src = user.avatar_url;
                        avatar.alt = '';
                        avatar.loading = 'lazy';
                        const names = document.createElement('span');
                        names.className = 'connection-names';
                        const displayName = document.createElement('strong');
                        displayName.textContent = user.display_name;
                        const username = document.createElement('small');
                        username.textContent = `@${user.username}`;
                        names.append(displayName, username);
                        const arrow = document.createElement('span');
                        arrow.className = 'connection-arrow';
                        arrow.setAttribute('aria-hidden', 'true');
                        arrow.textContent = '↗';
                        row.append(avatar, names, arrow);
                        fragment.append(row);
                    });
                    list.replaceChildren(fragment);
                } catch (error) {
                    const errorMessage = document.createElement('p');
                    errorMessage.className = 'connections-status connections-error';
                    errorMessage.textContent = error.message || 'Ro‘yxatni yuklab bo‘lmadi.';
                    list.replaceChildren(errorMessage);
                }
            });
        });

        connectionsModal.querySelectorAll('[data-connections-close]').forEach((button) => {
            button.addEventListener('click', closeConnections);
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && !connectionsModal.hidden) closeConnections();
        });
    }

    document.querySelectorAll('[data-follow-form]').forEach((form) => {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const button = form.querySelector('[data-follow-button]');
            button.disabled = true;
            try {
                const data = await postForm(form);
                button.classList.toggle('is-following', data.following);
                button.setAttribute('aria-pressed', String(data.following));
                if (button.classList.contains('follow-mini')) {
                    button.textContent = data.following ? '✓' : '+';
                    button.setAttribute('aria-label', data.following ? 'Kuzatishni bekor qilish' : 'Kuzatish');
                } else {
                    button.textContent = data.following ? 'Kuzatyapsiz' : 'Kuzatish';
                }
                document.querySelectorAll('[data-followers-count]').forEach((count) => {
                    count.textContent = data.followers_count;
                });
            } catch (error) {
                showToast(error.message || 'Kuzatish amalini bajarib bo‘lmadi.');
            } finally {
                button.disabled = false;
            }
        });
    });

    document.querySelectorAll('[data-copy-link]').forEach((button) => {
        button.addEventListener('click', async () => {
            try {
                await navigator.clipboard.writeText(button.dataset.copyLink);
                showToast('Profil havolasi nusxalandi.');
            } catch {
                showToast('Havolani nusxalab bo‘lmadi.');
            }
        });
    });
})();
