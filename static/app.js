/* Lilith -- web client.
 *
 * Two ways her words arrive:
 *   streaming  -- POST /chat/stream, server-sent events, rendered as they land.
 *                 This is the real thing; nothing is simulated.
 *   typed      -- POST /chat, then the old character-at-a-time animation.
 *
 * The toggle lives in the settings drawer and is remembered per browser. It is
 * forced off when /capabilities reports that the configured backend (or an
 * enabled translator) cannot produce partial text, so the switch never claims
 * something the server cannot do.
 */
(function () {
    "use strict";

    const BOOT = window.LILITH_BOOT || {};
    const api = (path) => (BOOT.apiBase ? BOOT.apiBase + path : path);

    const $ = (id) => document.getElementById(id);
    const portrait = $("portrait");
    const dialogue = $("dialogue");
    const echo = $("echo");
    const input = $("userInput");
    const sendBtn = $("sendBtn");
    const composer = $("composer");
    const settingsBtn = $("settingsBtn");
    const drawer = $("drawer");
    const gateOverlay = $("gateOverlay");

    const ACCENTS = [
        { name: "soft pink", rose: "#f0a8c4", deep: "#8d3f60" },
        { name: "rose", rose: "#ef8fa8", deep: "#8e3145" },
        { name: "lilac", rose: "#c8a9f0", deep: "#5f3f8d" },
        { name: "ember", rose: "#f0b48f", deep: "#8d5133" },
        { name: "ash", rose: "#c3c8d2", deep: "#4a5060" },
    ];

    const DEFAULTS = {
        stream: true,
        speed: 30,
        pauses: true,
        accent: 0,
        text: 100,
        portrait: 88,
        glass: 62,
        blink: true,
        revert: true,
    };

    const STORE_KEY = "lilith.settings";
    const CONSENT_KEY = "lilith.safetyConsentVersion";

    let settings = Object.assign({}, DEFAULTS);
    let character = "";
    let characterReady = false;
    try { character = window.localStorage.getItem("lilith.character") || ""; } catch (_) {}
    if (!["lilith", "mira"].includes(character)) character = "";
    const temperaments = {};
    function temperamentFor(profile) {
        if (temperaments[profile]) return temperaments[profile];
        try { return window.localStorage.getItem("lilith.temperament." + profile) === "yandere" ? "yandere" : "soft"; }
        catch (_) { return "soft"; }
    }
    function apiFetch(url, options = {}) {
        return fetch(url, Object.assign({}, options, {headers: Object.assign({}, options.headers || {},
            {"X-Lilith-Character": character || "lilith", "X-Lilith-Temperament": temperamentFor(character || "lilith")})}));
    }
    let consented = false;
    let busy = false;
    let canStream = true;          // until /capabilities says otherwise
    let validatedReplies = false;
    let userName = BOOT.userName || "";
    let userNameSet = Boolean(BOOT.userNameSet);
    let rooms = [];
    let currentRoom = "";
    let typingTimer = null;
    let blinkTimer = null;
    let blinkRestoreTimer = null;
    let portraitEmotion = "idle";
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let revertTimer = null;

    /* ── storage ────────────────────────────────────────────────────── */

    function load() {
        try {
            const raw = window.localStorage.getItem(STORE_KEY);
            if (raw) settings = Object.assign({}, DEFAULTS, JSON.parse(raw));
        } catch (err) {
            console.warn("Settings could not be read; using defaults.", err);
        }
    }

    function save() {
        try {
            window.localStorage.setItem(STORE_KEY, JSON.stringify(settings));
        } catch (err) {
            console.warn("Settings could not be saved.", err);
        }
    }

    function storedConsent() {
        try {
            return window.localStorage.getItem(CONSENT_KEY);
        } catch (err) {
            console.warn("Consent could not be read from local storage.", err);
            return null;
        }
    }

    /* ── appearance ─────────────────────────────────────────────────── */

    function applySettings() {
        const accent = ACCENTS[settings.accent] || ACCENTS[0];
        const root = document.documentElement.style;
        root.setProperty("--rose", accent.rose);
        root.setProperty("--rose-deep", accent.deep);
        root.setProperty("--text-scale", settings.text / 100);
        root.setProperty("--portrait", settings.portrait);
        root.setProperty("--glass", settings.glass / 100);
        startBlinking();
    }

    const MIRA_EXPRESSIONS = {
        idle: "idle", blinking: "blinking", smile: "smiling", happy: "smiling",
        playful: "blushing", cheeky: "blushing", talking: "smiling",
        thinking: "thinking", thinking_happy: "thinking", thinking_sad: "sad_confused",
        sad: "sad", dissapointed: "sad", confused: "confused", sleep: "blinking",
        blushing: "blushing", sad_confused: "sad_confused", angry: "angry",
    };

    function startBlinking() {
        clearInterval(blinkTimer);
        clearTimeout(blinkRestoreTimer);
        if (character !== "mira" && portraitEmotion === "blinking") portraitEmotion = "idle";
        if (characterReady) setPortrait(portraitEmotion);
        if (!settings.blink || reducedMotion.matches) return;
        blinkTimer = setInterval(() => {
            if (character === "mira" || portraitEmotion !== "idle") return;
            const previous = portraitEmotion;
            setPortrait("blinking");
            blinkRestoreTimer = setTimeout(() => {
                if (portraitEmotion === "blinking") setPortrait(previous);
            }, 240);
        }, 8000);
    }

    function setPortrait(emotion) {
        clearTimeout(blinkRestoreTimer);
        portraitEmotion = emotion;
        if (character === "mira") {
            const state = MIRA_EXPRESSIONS[emotion] || "idle";
            const extension = settings.blink && !reducedMotion.matches ? "webp" : "png";
            const folder = temperamentFor("mira") === "yandere" ? "static/mira/yandere/" : "static/mira/";
            portrait.src = folder + state + "." + extension + "?v=yandere-art-1";
            $("miraGalleryLink").querySelector("a").href = folder + "preview.html";
        } else {
            const fallback = {blushing:"smile", angry:"dissapointed", sad_confused:"sad", confused:"thinking"};
            portrait.src = "static/" + (fallback[emotion] || emotion) + ".png";
        }
    }

    function setEmotion(emotion) {
        clearTimeout(revertTimer);
        setPortrait(emotion);
        if (settings.revert && emotion !== "idle") {
            revertTimer = setTimeout(() => setPortrait("idle"), 5000);
        }
    }

    /* ── dialogue rendering ─────────────────────────────────────────── */

    function showEcho(text) {
        echo.textContent = (userName || "you") + ": " + text;
        echo.hidden = false;
    }

    function beginReply() {
        clearTimeout(typingTimer);
        dialogue.textContent = "";
        dialogue.classList.add("writing");
    }

    function append(text) {
        dialogue.textContent += text;
        dialogue.scrollTop = dialogue.scrollHeight;
    }

    function endReply() {
        dialogue.classList.remove("writing");
    }

    function showWaiting() {
        const hearts = ["♡", "♥"];
        let index = 0;
        dialogue.classList.remove("writing");
        dialogue.textContent = hearts[0];
        return setInterval(() => {
            index = (index + 1) % hearts.length;
            dialogue.textContent = hearts[index];
        }, 420);
    }

    /** The animation used when streaming is off: characters on a timer. */
    function typeOut(text) {
        beginReply();
        let i = 0;
        const step = () => {
            if (i >= text.length) { endReply(); return; }
            const char = text.charAt(i++);
            append(char);
            let delay = settings.speed;
            if (settings.pauses && (char === "." || char === "…")) delay += 340;
            else if (settings.pauses && (char === "," || char === "~")) delay += 190;
            typingTimer = setTimeout(step, delay);
        };
        step();
    }

    /* ── talking to the server ──────────────────────────────────────── */

    function chatHeaders() {
        const headers = { "Content-Type": "application/json" };
        headers[BOOT.consentHeader] = BOOT.consentVersion;
        return headers;
    }

    async function refreshCapabilities() {
        try {
            const res = await apiFetch(api("/capabilities"));
            if (!res.ok) return;
            const data = await res.json();
            canStream = Boolean(data.streaming);
            validatedReplies = Boolean(data.validated_replies);
            rooms = data.rooms || [];
            currentRoom = data.current_room || "";
            renderRooms();
            renderStreamToggle();
        } catch (err) {
            console.warn("Could not read server capabilities.", err);
        }
    }

    function streamingOn() {
        return settings.stream && canStream && typeof ReadableStream !== "undefined";
    }

    /** Reads an SSE body and hands each decoded event to `onEvent`. */
    async function readEvents(response, onEvent) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let cut;
            while ((cut = buffer.indexOf("\n\n")) >= 0) {
                const frame = buffer.slice(0, cut);
                buffer = buffer.slice(cut + 2);
                const line = frame.split("\n").find((l) => l.startsWith("data:"));
                if (!line) continue;
                try {
                    onEvent(JSON.parse(line.slice(5).trim()));
                } catch (err) {
                    console.warn("Unreadable stream event.", err);
                }
            }
        }
    }

    async function sendStreaming(message) {
        const res = await apiFetch(api("/chat/stream"), {
            method: "POST",
            headers: chatHeaders(),
            body: JSON.stringify({ message: message }),
        });
        if (!res.ok) throw await httpFailure(res);
        if (!res.body) throw new Error("This browser cannot read a streamed reply.");

        let started = false;
        let failure = null;
        await readEvents(res, (event) => {
            if (event.type === "delta") {
                if (!started) { beginReply(); started = true; }
                append(event.text);
            } else if (event.type === "done") {
                if (event.emotion) setEmotion(event.emotion);
            } else if (event.type === "error") {
                failure = event;
            }
        });
        endReply();
        if (failure) {
            // `shown` marks the case where her words did arrive but the turn
            // was not written to memory. Saying so is the honest thing: she
            // will not remember this exchange next time.
            if (failure.shown) {
                append("\n\n(" + failure.error + ")");
                setEmotion("thinking");
            } else {
                throw new Error(failure.error);
            }
        }
    }

    async function sendWhole(message) {
        const waiting = showWaiting();
        try {
            const res = await apiFetch(api("/chat"), {
                method: "POST",
                headers: chatHeaders(),
                body: JSON.stringify({ message: message }),
            });
            if (!res.ok) throw await httpFailure(res);
            const data = await res.json();
            clearInterval(waiting);
            if (data.emotion) setEmotion(data.emotion);
            typeOut(data.reply || "...");
        } finally {
            clearInterval(waiting);
        }
    }

    async function httpFailure(res) {
        if (res.status === 428) {
            setConsent(false, true);
            return new Error("Consent is required before chatting.");
        }
        const data = await res.json().catch(() => ({}));
        return new Error(data.error || "The chat request was not accepted.");
    }

    async function send(message) {
        if (busy) return;
        busy = true;
        input.disabled = true;
        sendBtn.disabled = true;
        showEcho(message);
        // Every question waits on a neutral expression. Asking whether she is
        // real must never be met with guilt or disappointment.
        setPortrait("thinking");
        try {
            if (streamingOn()) await sendStreaming(message);
            else await sendWhole(message);
        } catch (err) {
            endReply();
            dialogue.textContent = err.message ||
                "Something went wrong... Lilith seems distant.";
            setEmotion("sad");
        } finally {
            busy = false;
            input.disabled = !consented;
            sendBtn.disabled = !consented;
            if (consented) input.focus();
        }
    }

    /* ── nickname & rooms ───────────────────────────────────────────── */

    async function askNickname(force) {
        if (!consented) return null;
        for (;;) {
            const text = window.prompt(
                force ? "she leans closer. what should she call you?"
                      : "whisper the name you want her to hold.",
                userName
            );
            if (text === null) {
                if (userName) return userName;
                force = true;
                continue;
            }
            const trimmed = text.trim();
            if (!trimmed) { force = true; continue; }
            try {
                const res = await apiFetch(api("/nickname"), {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ user_name: trimmed }),
                });
                if (!res.ok) throw new Error("failed to save name");
                userName = (await res.json()).user_name;
                userNameSet = true;
                $("optName").textContent = userName || "—";
                return userName;
            } catch (err) {
                console.error(err);
                window.alert("she couldn't hold onto that. try again?");
                force = true;
            }
        }
    }

    async function roomAction(action, name, newName) {
        try {
            const res = await apiFetch(api("/rooms"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: action, name: name, new_name: newName }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) { window.alert(data.error || "that didn't work."); return; }
            rooms = data.rooms || [];
            currentRoom = data.current || "";
            renderRooms();
            if (action === "switch" || action === "clear") {
                dialogue.textContent = "...";
                echo.hidden = true;
                loadTranscript(true);
            }
        } catch (err) {
            console.error(err);
            window.alert("she couldn't reach that room.");
        }
    }

    function renderRooms() {
        const list = $("roomList");
        list.innerHTML = "";
        rooms.forEach((name) => {
            const li = document.createElement("li");
            const button = document.createElement("button");
            button.type = "button";
            button.textContent = name;
            if (name === currentRoom) button.setAttribute("aria-current", "true");
            button.addEventListener("click", () => roomAction("switch", name));
            li.appendChild(button);
            list.appendChild(li);
        });
    }

    async function loadTranscript(keepHidden) {
        const panel = $("transcript");
        if (keepHidden && panel.hidden) return;
        try {
            const res = await apiFetch(api("/history"));
            const data = await res.json();
            panel.innerHTML = "";
            (data.history || []).forEach((turn) => {
                const p = document.createElement("p");
                const who = document.createElement("span");
                who.className = turn.role === "assistant" ? "who" : "you";
                who.textContent = (turn.role === "assistant"
                    ? (character === "mira" ? "Mira" : "Lilith") : (userName || "you")) + ": ";
                p.appendChild(who);
                p.appendChild(document.createTextNode(turn.content || ""));
                panel.appendChild(p);
            });
            if (!panel.childNodes.length) panel.textContent = "nothing here yet.";
        } catch (err) {
            panel.textContent = "the transcript could not be read.";
        }
    }

    /* ── settings UI ────────────────────────────────────────────────── */

    function renderStreamToggle() {
        const box = $("optStream");
        const note = $("streamNote");
        box.checked = settings.stream && canStream;
        box.disabled = !canStream;
        note.textContent = canStream
            ? (validatedReplies ? "her reply and expression appear after validation" : "words appear as she writes them")
            : "this backend cannot stream; typing animation is used";
    }

    function renderSwatches() {
        const holder = $("optAccent");
        holder.innerHTML = "";
        ACCENTS.forEach((accent, index) => {
            const button = document.createElement("button");
            button.type = "button";
            button.title = accent.name;
            button.setAttribute("role", "radio");
            button.setAttribute("aria-label", accent.name);
            button.setAttribute("aria-checked", String(index === settings.accent));
            button.style.background =
                "linear-gradient(140deg," + accent.rose + "," + accent.deep + ")";
            button.addEventListener("click", () => {
                settings.accent = index;
                save();
                applySettings();
                renderSwatches();
            });
            holder.appendChild(button);
        });
    }

    function bindSetting(id, key, transform) {
        const element = $(id);
        const isCheck = element.type === "checkbox";
        if (isCheck) element.checked = settings[key];
        else element.value = settings[key];
        element.addEventListener("input", () => {
            settings[key] = isCheck ? element.checked : Number(element.value);
            save();
            if (transform) transform();
        });
    }

    function openDrawer(open) {
        drawer.hidden = !open;
        settingsBtn.setAttribute("aria-expanded", String(open));
        if (open) {
            $("optName").textContent = userName || "—";
            refreshCapabilities();
        }
    }

    /* ── consent ────────────────────────────────────────────────────── */

    function setConsent(accepted, persist) {
        consented = accepted;
        gateOverlay.hidden = accepted;
        gateOverlay.inert = !characterReady;
        input.disabled = !accepted || !characterReady || busy;
        sendBtn.disabled = !accepted || !characterReady || busy;
        settingsBtn.disabled = !accepted || !characterReady;
        input.placeholder = accepted
            ? "say something..." : "Accept the notice below to chat";
        if (!persist) return;
        try {
            if (accepted) {
                window.localStorage.setItem(CONSENT_KEY, BOOT.consentVersion);
            } else {
                window.localStorage.removeItem(CONSENT_KEY);
            }
        } catch (err) {
            console.warn("Consent could not be saved to local storage.", err);
        }
    }

    async function chooseCharacter(next) {
        if (busy) return;
        clearTimeout(typingTimer);
        clearTimeout(revertTimer);
        endReply();
        setPortrait("idle");
        const previous = character;
        characterReady = false;
        character = next;
        $("characterOverlay").hidden = false;
        setConsent(consented, false);
        $("characterError").textContent = "";
        $("chooseLilith").disabled = true;
        $("chooseMira").disabled = true;
        try {
            const res = await apiFetch(api("/character"));
            if (!res.ok) throw new Error("Could not open this character. Try again.");
            const data = await res.json();
            userName = data.user_name || "";
            userNameSet = Boolean(data.user_name_set);
            const name = next === "mira" ? "Mira" : "Lilith";
            $("characterName").textContent = name;
            portrait.alt = name + " portrait";
            $("miraExpressionRow").hidden = next !== "mira";
            $("miraGalleryLink").hidden = next !== "mira";
            $("miraExpression").value = "idle";
            $("temperament").value = temperamentFor(next);
            setPortrait("idle");
            document.title = name;
            dialogue.textContent = next === "mira" ? "heyy" : "...there you are.";
            echo.hidden = true;
            $("transcript").replaceChildren();
            $("optName").textContent = userName || "—";
            try { window.localStorage.setItem("lilith.character", next); } catch (_) {}
            characterReady = true;
            $("characterOverlay").hidden = true;
            setConsent(consented, false);
            await refreshCapabilities();
            if (consented) input.focus();
            else $("acceptConsent").focus();
        } catch (err) {
            character = previous;
            $("characterError").textContent = err.message;
        } finally {
            $("chooseLilith").disabled = false;
            $("chooseMira").disabled = false;
        }
    }

    /* ── wiring ─────────────────────────────────────────────────────── */

    reducedMotion.addEventListener("change", startBlinking);
    $("temperament").addEventListener("change", (event) => {
        temperaments[character] = event.target.value;
        try { window.localStorage.setItem("lilith.temperament." + character, event.target.value); }
        catch (_) { dialogue.textContent = "Your browser could not save this setting."; }
        if (character === "mira") setPortrait(portraitEmotion);
    });
    $("miraExpression").addEventListener("change", (event) => {
        if (character === "mira" && !busy) {
            clearTimeout(revertTimer);
            setPortrait(event.target.value);
        }
    });
    load();
    applySettings();
    renderSwatches();
    renderStreamToggle();

    bindSetting("optStream", "stream", renderStreamToggle);
    bindSetting("optSpeed", "speed");
    bindSetting("optPauses", "pauses");
    bindSetting("optText", "text", applySettings);
    bindSetting("optPortrait", "portrait", applySettings);
    bindSetting("optGlass", "glass", applySettings);
    bindSetting("optBlink", "blink", applySettings);
    bindSetting("optRevert", "revert");

    composer.addEventListener("submit", (event) => {
        event.preventDefault();
        const message = input.value.trim();
        if (!consented || !characterReady || !message || busy) return;
        if (["/mira", "/lilith"].includes(message.toLowerCase())) {
            input.value = "";
            chooseCharacter(message.slice(1).toLowerCase());
            return;
        }
        input.value = "";
        if (!userNameSet || !userName) {
            askNickname(true).then((name) => { if (name) send(message); });
            return;
        }
        send(message);
    });

    settingsBtn.addEventListener("click", () => openDrawer(drawer.hidden));
    $("closeDrawer").addEventListener("click", () => openDrawer(false));
    $("optName").addEventListener("click", () => askNickname(true));

    $("roomNew").addEventListener("click", () => {
        const name = (window.prompt("name for the new room?") || "").trim();
        if (name) roomAction("create", name);
    });
    $("roomRename").addEventListener("click", () => {
        const name = (window.prompt("rename this room to?", currentRoom) || "").trim();
        if (name) roomAction("rename", currentRoom, name);
    });
    $("roomClear").addEventListener("click", () => {
        if (window.confirm("Erase every turn in '" + currentRoom + "'? "
            + "This cannot be undone.")) roomAction("clear", currentRoom);
    });
    $("roomDelete").addEventListener("click", () => {
        if (window.confirm("Delete the room '" + currentRoom + "' and its history?")) {
            roomAction("delete", currentRoom);
        }
    });
    $("showLog").addEventListener("click", () => {
        const panel = $("transcript");
        panel.hidden = !panel.hidden;
        $("showLog").textContent = panel.hidden
            ? "show this room's transcript" : "hide transcript";
        if (!panel.hidden) loadTranscript(false);
    });

    $("acceptConsent").addEventListener("click", () => {
        setConsent(true, true);
        dialogue.textContent = "...there you are.";
        input.focus();
        refreshCapabilities();
        if (!userNameSet || !userName) setTimeout(() => askNickname(true), 400);
    });
    $("declineConsent").addEventListener("click", () => {
        setConsent(false, true);
        dialogue.textContent = "Consent was not given. The scene stays closed.";
    });
    $("revokeConsent").addEventListener("click", () => {
        setConsent(false, true);
        openDrawer(false);
        dialogue.textContent = "Consent withdrawn. The scene stays closed.";
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Tab" && !$("characterOverlay").hidden) {
            const choices = [$("chooseLilith"), $("chooseMira")];
            event.preventDefault();
            if (!choices[0].disabled) {
                const index = choices.indexOf(document.activeElement);
                choices[(index + 1) % 2].focus();
            }
        }
        if (event.key === "Escape" && !drawer.hidden) openDrawer(false);
    });

    ["Lilith", "Mira"].forEach((name) => {
        $("choose" + name).addEventListener("click", () => chooseCharacter(name.toLowerCase()));
        $("switch" + name).addEventListener("click", () => chooseCharacter(name.toLowerCase()));
    });
    setConsent(storedConsent() === BOOT.consentVersion, false);
    if (character) chooseCharacter(character);
    else {
        $("characterOverlay").hidden = false;
        $("chooseLilith").focus();
    }
    if (consented && characterReady) {
        refreshCapabilities();
        if (!userNameSet || !userName) setTimeout(() => askNickname(true), 500);
    }
}());
