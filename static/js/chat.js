(() => {
    const app = document.querySelector("[data-chat-app]");
    const socketPath = app?.dataset.socketPath;
    const stream = document.querySelector("[data-message-stream]");
    const form = document.querySelector("[data-message-form]");
    const input = document.querySelector("[data-message-input]");
    const sendButton = document.querySelector("[data-send-button]");
    const typingNotice = document.querySelector("[data-typing-notice]");
    const status = document.querySelector("[data-socket-status]");
    const peerStatus = document.querySelector("[data-peer-status]");
    const peerPresence = document.querySelector("[data-peer-presence]");
    const imageInput = document.querySelector("[data-image-input]");
    const imageButton = document.querySelector("[data-image-button]");
    const emojiButton = document.querySelector("[data-emoji-button]");
    const emojiPicker = document.querySelector("[data-emoji-picker]");
    const recordButton = document.querySelector("[data-record-button]");
    const recordIcon = document.querySelector("[data-record-icon]");
    const feedback = document.querySelector("[data-composer-feedback]");

    if (!socketPath || !stream || !form || !input || !sendButton) return;

    const currentUserId = stream.dataset.currentUser;
    const uploadUrl = form.dataset.uploadUrl;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}${socketPath}`);
    const emojis = ["😀", "😂", "🥹", "😍", "🥰", "😎", "🤔", "😭", "😊", "😉", "😘", "🫶", "❤️", "🔥", "👏", "👍", "🙏", "🎉", "✨", "💯", "🙂", "🙌", "💔", "😅", "🤝", "💚", "💜", "🌹", "☕", "✅"];
    let typingTimer;
    let typingSent = false;
    let mediaRecorder;
    let recordingChunks = [];
    let recordingTimer;

    const setStatus = (message, isError = false) => {
        status.textContent = message;
        status.classList.toggle("is-error", isError);
    };

    const setFeedback = (message, isError = false) => {
        feedback.textContent = message;
        feedback.classList.toggle("is-error", isError);
    };

    const scrollToLatest = () => {
        stream.scrollTop = stream.scrollHeight;
    };

    const createMessageActions = (row, messageType) => {
        if (row.classList.contains("is-mine")) {
            const actions = document.createElement("div");
            actions.className = "message-actions";
            if (messageType === "text") {
                const editButton = document.createElement("button");
                editButton.type = "button";
                editButton.dataset.messageAction = "edit";
                editButton.setAttribute("aria-label", "Xabarni tahrirlash");
                editButton.textContent = "Tahrirlash";
                actions.append(editButton);
            }
            const deleteButton = document.createElement("button");
            deleteButton.type = "button";
            deleteButton.dataset.messageAction = "delete";
            deleteButton.setAttribute("aria-label", "Xabarni o‘chirish");
            deleteButton.textContent = "O‘chirish";
            actions.append(deleteButton);
            return actions;
        }
        return null;
    };

    const appendMessage = (message) => {
        if (stream.querySelector(`[data-message-id="${message.id}"]`)) return;
        document.querySelector(".conversation-start")?.remove();
        const mine = message.sender_id === currentUserId;
        const row = document.createElement("article");
        row.className = `message-row${mine ? " is-mine" : ""}`;
        row.dataset.messageId = message.id;
        row.dataset.messageType = message.message_type;

        if (!mine) {
            const avatar = document.createElement("img");
            avatar.className = "message-avatar";
            avatar.src = message.avatar_url;
            avatar.alt = "";
            row.append(avatar);
        }

        const content = document.createElement("div");
        content.className = "message-content";
        const actions = createMessageActions(row, message.message_type);
        if (actions) content.append(actions);
        if (message.message_type === "image") {
            const link = document.createElement("a");
            link.className = "message-media-link";
            link.href = message.media_url;
            link.target = "_blank";
            link.rel = "noopener";
            const image = document.createElement("img");
            image.className = "message-image";
            image.src = message.media_url;
            image.alt = "Yuborilgan rasm";
            image.loading = "lazy";
            link.append(image);
            content.append(link);
        } else if (message.message_type === "audio") {
            const audio = document.createElement("audio");
            audio.className = "message-audio";
            audio.controls = true;
            audio.preload = "metadata";
            audio.src = message.media_url;
            content.append(audio);
        } else {
            const bubble = document.createElement("p");
            bubble.className = "message-bubble";
            bubble.textContent = message.text;
            content.append(bubble);
        }
        const time = document.createElement("time");
        time.className = "message-time";
        time.textContent = message.created_at;
        const meta = document.createElement("span");
        meta.className = "message-meta";
        meta.append(time);
        if (message.edited_at) {
            const editedLabel = document.createElement("span");
            editedLabel.className = "message-edited";
            editedLabel.dataset.editedLabel = "";
            editedLabel.textContent = "Tahrirlangan";
            meta.append(editedLabel);
        }
        content.append(meta);
        row.append(content);
        stream.append(row);
        const activeConversation = document.querySelector("[data-conversation].is-active");
        const preview = activeConversation?.querySelector("[data-conversation-preview]");
        const previewTime = activeConversation?.querySelector("[data-conversation-time]");
        const previewText = message.message_type === "image"
            ? "📷 Rasm"
            : message.message_type === "audio"
                ? "🎤 Ovozli xabar"
                : message.text;
        if (preview) preview.textContent = `${mine ? "Siz: " : ""}${previewText}`;
        if (preview) preview.dataset.lastMessageId = message.id;
        if (previewTime) previewTime.textContent = message.created_at;
        scrollToLatest();
    };

    const updateMessage = (message) => {
        const row = stream.querySelector(`[data-message-id="${message.id}"]`);
        const bubble = row?.querySelector(".message-bubble");
        if (!row || !bubble) return;
        bubble.textContent = message.text;
        row.querySelector("[data-edited-label]")?.remove();
        const editedLabel = document.createElement("span");
        editedLabel.className = "message-edited";
        editedLabel.dataset.editedLabel = "";
        editedLabel.textContent = "Tahrirlangan";
        row.querySelector(".message-meta")?.append(editedLabel);

        const preview = document.querySelector("[data-conversation-preview]");
        if (preview?.dataset.lastMessageId === message.id) {
            preview.textContent = `Siz: ${message.text}`;
        }
    };

    const updateConversationPreview = (message) => {
        const preview = document.querySelector("[data-conversation-preview]");
        const previewTime = document.querySelector("[data-conversation-time]");
        if (!preview || !previewTime) return;
        if (!message) {
            preview.textContent = "Suhbatni boshlang";
            delete preview.dataset.lastMessageId;
            previewTime.textContent = "";
            return;
        }
        const mine = message.sender_id === currentUserId;
        preview.textContent = `${mine ? "Siz: " : ""}${message.text}`;
        preview.dataset.lastMessageId = message.id;
        previewTime.textContent = message.created_at;
    };

    const beginMessageEdit = (row) => {
        if (row.querySelector(".message-edit-form")) return;
        const bubble = row.querySelector(".message-bubble");
        const meta = row.querySelector(".message-meta");
        if (!bubble || !meta) return;
        const content = row.querySelector(".message-content");
        const formElement = document.createElement("form");
        formElement.className = "message-edit-form";
        const textarea = document.createElement("textarea");
        textarea.className = "message-edit-input";
        textarea.maxLength = 5000;
        textarea.value = bubble.textContent;
        textarea.setAttribute("aria-label", "Xabar matnini tahrirlash");
        const controls = document.createElement("div");
        controls.className = "message-edit-controls";
        const cancelButton = document.createElement("button");
        cancelButton.type = "button";
        cancelButton.dataset.editCancel = "";
        cancelButton.textContent = "Bekor qilish";
        const saveButton = document.createElement("button");
        saveButton.type = "submit";
        saveButton.textContent = "Saqlash";
        controls.append(cancelButton, saveButton);
        formElement.append(textarea, controls);
        bubble.hidden = true;
        meta.hidden = true;
        content.insertBefore(formElement, bubble);
        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    };

    stream.addEventListener("click", (event) => {
        const actionButton = event.target.closest("[data-message-action]");
        const cancelButton = event.target.closest("[data-edit-cancel]");
        const row = event.target.closest("[data-message-id]");
        if (!row) return;
        if (cancelButton) {
            row.querySelector(".message-edit-form")?.remove();
            row.querySelector(".message-bubble").hidden = false;
            row.querySelector(".message-meta").hidden = false;
            return;
        }
        if (!actionButton) return;
        if (actionButton.dataset.messageAction === "edit") {
            beginMessageEdit(row);
        } else if (actionButton.dataset.messageAction === "delete") {
            if (window.confirm("Bu xabarni o‘chirishni xohlaysizmi?")) {
                socket.send(JSON.stringify({
                    type: "delete_message",
                    message_id: row.dataset.messageId,
                }));
            }
        }
    });

    stream.addEventListener("submit", (event) => {
        const editForm = event.target.closest(".message-edit-form");
        if (!editForm) return;
        event.preventDefault();
        const row = editForm.closest("[data-message-id]");
        const editInput = editForm.querySelector(".message-edit-input");
        const text = editInput.value.trim();
        if (!text || socket.readyState !== WebSocket.OPEN) return;
        socket.send(JSON.stringify({
            type: "edit_message",
            message_id: row.dataset.messageId,
            text,
        }));
        editForm.querySelector('[type="submit"]').disabled = true;
    });

    const sendTyping = (typing) => {
        if (socket.readyState !== WebSocket.OPEN || typingSent === typing) return;
        typingSent = typing;
        socket.send(JSON.stringify({ type: "typing", typing }));
    };

    socket.addEventListener("open", () => {
        input.disabled = false;
        sendButton.disabled = false;
        imageButton.disabled = false;
        emojiButton.disabled = false;
        recordButton.disabled = false;
        setStatus("Ulangan");
        input.focus();
    });

    socket.addEventListener("message", (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === "message") {
            appendMessage(payload.message);
            typingNotice.hidden = true;
        } else if (payload.type === "message_updated") {
            updateMessage(payload.message);
        } else if (payload.type === "message_deleted") {
            stream.querySelector(`[data-message-id="${payload.message_id}"]`)?.remove();
            updateConversationPreview(payload.last_message);
            if (!stream.querySelector("[data-message-id]")) {
                const emptyState = document.createElement("div");
                emptyState.className = "conversation-start";
                const symbol = document.createElement("span");
                symbol.textContent = "✳";
                const heading = document.createElement("strong");
                heading.textContent = "Suhbat";
                const description = document.createElement("p");
                description.textContent = "Suhbatni davom ettirish uchun xabar yozing.";
                emptyState.append(symbol, heading, description);
                stream.append(emptyState);
            }
        } else if (payload.type === "typing") {
            typingNotice.hidden = !payload.typing;
            scrollToLatest();
        } else if (payload.type === "presence") {
            const online = payload.online;
            if (payload.user_id === app.dataset.peerId) {
                peerStatus.textContent = online ? "Online" : "Offline";
                peerStatus.classList.toggle("is-online", online);
                peerPresence.classList.toggle("is-offline", !online);
            }
            document.querySelectorAll("[data-presence-dot]").forEach((dot) => {
                if (dot.dataset.presenceDot !== payload.user_id) return;
                dot.classList.toggle("is-offline", !online);
            });
        } else if (payload.type === "error") {
            setFeedback(payload.message, true);
        }
    });

    socket.addEventListener("close", () => {
        input.disabled = true;
        sendButton.disabled = true;
        imageButton.disabled = true;
        emojiButton.disabled = true;
        recordButton.disabled = true;
        typingNotice.hidden = true;
        setStatus("Ulanish uzildi. Sahifani yangilang.", true);
        peerStatus.textContent = "Offline";
        peerStatus.classList.remove("is-online");
        peerPresence.classList.add("is-offline");
    });

    socket.addEventListener("error", () => {
        setStatus("Chat serveriga ulanib bo‘lmadi.", true);
    });

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text || socket.readyState !== WebSocket.OPEN) return;
        socket.send(JSON.stringify({ type: "message", text }));
        input.value = "";
        input.style.height = "22px";
        sendTyping(false);
    });

    const uploadFile = async (file, type) => {
        if (!file || !uploadUrl) return;
        if (file.size > 10 * 1024 * 1024) {
            setFeedback("Fayl 10 MB dan kichik bo‘lishi kerak.", true);
            return;
        }
        const formData = new FormData();
        formData.append("type", type);
        formData.append("file", file);
        setFeedback(type === "image" ? "Rasm yuborilmoqda…" : "Ovozli xabar yuborilmoqda…");
        imageButton.disabled = true;
        recordButton.disabled = true;
        try {
            const response = await fetch(uploadUrl, {
                method: "POST",
                body: formData,
                credentials: "same-origin",
                headers: {
                    "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value,
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Faylni yuborib bo‘lmadi.");
            appendMessage(result.message);
            setFeedback("");
        } catch (error) {
            setFeedback(error.message || "Yuborishda xatolik yuz berdi.", true);
        } finally {
            imageButton.disabled = socket.readyState !== WebSocket.OPEN;
            recordButton.disabled = socket.readyState !== WebSocket.OPEN;
        }
    };

    imageButton.addEventListener("click", () => imageInput.click());
    imageInput.addEventListener("change", () => {
        const [file] = imageInput.files;
        if (file) uploadFile(file, "image");
        imageInput.value = "";
    });

    emojis.forEach((emoji) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "emoji-choice";
        button.textContent = emoji;
        button.setAttribute("aria-label", `Emoji ${emoji}`);
        button.addEventListener("click", () => {
            const start = input.selectionStart;
            const end = input.selectionEnd;
            input.setRangeText(emoji, start, end, "end");
            input.dispatchEvent(new Event("input", { bubbles: true }));
            input.focus();
            emojiPicker.hidden = true;
        });
        emojiPicker.append(button);
    });

    emojiButton.addEventListener("click", () => {
        emojiPicker.hidden = !emojiPicker.hidden;
    });

    const stopRecording = () => {
        if (mediaRecorder?.state === "recording") mediaRecorder.stop();
        window.clearInterval(recordingTimer);
        recordButton.classList.remove("is-recording");
        recordButton.setAttribute("aria-label", "Ovoz yozishni boshlash");
        recordIcon.textContent = "●";
    };

    recordButton.addEventListener("click", async () => {
        if (mediaRecorder?.state === "recording") {
            stopRecording();
            return;
        }
        if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
            setFeedback("Brauzeringizda ovoz yozish qo‘llab-quvvatlanmaydi.", true);
            return;
        }
        try {
            const streamInput = await navigator.mediaDevices.getUserMedia({ audio: true });
            const options = {};
            if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
                options.mimeType = "audio/webm;codecs=opus";
            } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
                options.mimeType = "audio/mp4";
            }
            mediaRecorder = new MediaRecorder(streamInput, options);
            recordingChunks = [];
            mediaRecorder.addEventListener("dataavailable", (event) => {
                if (event.data.size) recordingChunks.push(event.data);
            });
            mediaRecorder.addEventListener("stop", () => {
                streamInput.getTracks().forEach((track) => track.stop());
                if (!recordingChunks.length) {
                    setFeedback("Ovoz yozilmadi. Mikrofon ruxsatini tekshiring.", true);
                    return;
                }
                const audioBlob = new Blob(recordingChunks, {
                    type: mediaRecorder.mimeType || "audio/webm",
                });
                const extension = audioBlob.type.startsWith("audio/mp4") ? "m4a" : "webm";
                const audioFile = new File([audioBlob], `voice-message.${extension}`, {
                    type: audioBlob.type,
                });
                uploadFile(audioFile, "audio");
            });
            mediaRecorder.start();
            recordButton.classList.add("is-recording");
            recordButton.setAttribute("aria-label", "Ovoz yozishni to‘xtatish");
            recordIcon.textContent = "■";
            setFeedback("Ovoz yozilmoqda… 60 soniyagacha");
            recordingTimer = window.setTimeout(stopRecording, 60_000);
        } catch {
            setFeedback("Mikrofonga ruxsat berilmadi yoki u ishlamayapti.", true);
        }
    });

    input.addEventListener("input", () => {
        input.style.height = "22px";
        input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
        sendTyping(input.value.trim().length > 0);
        window.clearTimeout(typingTimer);
        typingTimer = window.setTimeout(() => sendTyping(false), 1200);
    });

    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    window.setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "heartbeat" }));
        }
    }, 30_000);

    document.querySelector("[data-chat-search]")?.addEventListener("input", (event) => {
        const query = event.target.value.trim().toLocaleLowerCase();
        document.querySelectorAll("[data-conversation]").forEach((item) => {
            item.hidden = !item.dataset.searchName.includes(query);
        });
    });

    document.addEventListener("click", (event) => {
        if (!emojiPicker.contains(event.target) && !emojiButton.contains(event.target)) {
            emojiPicker.hidden = true;
        }
    });

    scrollToLatest();
})();
