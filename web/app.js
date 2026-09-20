import {
    initializeApp
} from "https://www.gstatic.com/firebasejs/12.1.0/firebase-app.js";

import {
    getDatabase,
    ref,
    onValue
} from "https://www.gstatic.com/firebasejs/12.1.0/firebase-database.js";


// ============================================================
// FIREBASE CONFIGURATION
// ============================================================

const firebaseConfig = {
    apiKey: "AIzaSyD2Nw5510Vy8aCB4794Duxy14b0j79SWrU",
    authDomain: "rfid-rickshaw-system.firebaseapp.com",
    databaseURL: "https://rfid-rickshaw-system-default-rtdb.asia-southeast1.firebasedatabase.app",
    projectId: "rfid-rickshaw-system",
    storageBucket: "rfid-rickshaw-system.firebasestorage.app",
    messagingSenderId: "1083389680683",
    appId: "1:1083389680683:web:a04ea0ef7c8a304a81de6e",
    measurementId: "G-LJSZPBFR6P"
};

const app = initializeApp(firebaseConfig);
const database = getDatabase(app);

// The HTML watchdog uses this only to detect a total CDN/module failure.
window.__rickshawModuleLoaded = true;


// ============================================================
// RUNTIME STATE
// ============================================================

let hasRenderedData = false;
let hasLiveData = false;
let publicUnsubscribe = null;
let retryTimer = null;
let slowConnectionTimer = null;
let retryDelayMs = 3000;

const MAX_RETRY_DELAY_MS = 30000;
const SLOW_CONNECTION_NOTICE_MS = 15000;


// ============================================================
// TOKEN
// ============================================================

const params = new URLSearchParams(window.location.search);
const token = (params.get("token") || "").trim();

if (!token) {
    showFatalError("Invalid QR code. Rickshaw token is missing.");
} else if (/[.#$\[\]\/]/.test(token)) {
    showFatalError("Invalid Rickshaw token.");
} else {
    restoreCachedRecord(token);
    monitorFirebaseConnection();
    attachPublicListener(token);
}


// ============================================================
// FIREBASE CONNECTION STATE
//
// Firebase documents /.info/connected as the client-specific
// connection indicator. A temporary false value is NOT treated as
// a fatal error. Existing vehicle data stays visible.
// ============================================================

function monitorFirebaseConnection() {
    const connectedRef = ref(database, ".info/connected");

    onValue(
        connectedRef,
        (snapshot) => {
            const connected = snapshot.val() === true;

            if (connected) {
                if (hasLiveData) {
                    setConnectionState("online", "Live Data Connected");
                } else {
                    setConnectionState("connecting", "Connected - loading data...");
                }

                // If a listener was previously cancelled for a temporary
                // reason, reconnect it immediately when Firebase is back.
                if (!publicUnsubscribe && token) {
                    scheduleReconnect(token, 0);
                }
            } else {
                if (hasRenderedData) {
                    setConnectionState(
                        "connecting",
                        "Reconnecting - showing last data"
                    );
                } else {
                    setConnectionState("connecting", "Reconnecting...");
                    setLoadingMessage("Connecting to live database...");
                }
            }
        },
        (error) => {
            console.warn("Firebase connection-state monitor error:", error);
            setConnectionState("connecting", "Reconnecting...");
        }
    );
}


// ============================================================
// PUBLIC REALTIME RICKSHAW RECORD
//
// Reads ONLY:
//     /public/by_token/{token}
// ============================================================

function attachPublicListener(tokenValue) {
    clearReconnectTimer();

    if (publicUnsubscribe) {
        try {
            publicUnsubscribe();
        } catch (_) {
            // Ignore an unsubscribe race.
        }
        publicUnsubscribe = null;
    }

    startSlowConnectionNotice();

    const publicRef = ref(
        database,
        "public/by_token/" + tokenValue
    );

    try {
        publicUnsubscribe = onValue(
            publicRef,
            (snapshot) => {
                clearSlowConnectionNotice();
                retryDelayMs = 3000;
                hasLiveData = true;

                if (!snapshot.exists()) {
                    // This is a real successful Firebase response, not a
                    // network fluctuation, so a missing record is fatal.
                    showFatalError(
                        "Rickshaw not found or this QR code is no longer active."
                    );
                    return;
                }

                const data = snapshot.val() || {};

                cachePublicRecord(tokenValue, data);
                renderRickshaw(data);
                hasRenderedData = true;

                setConnectionState("online", "Live Data Connected");
            },
            (error) => {
                clearSlowConnectionNotice();
                publicUnsubscribe = null;
                hasLiveData = false;

                console.error("Firebase public record listener error:", error);

                if (isPermissionError(error)) {
                    // Rules/permission errors will not heal from a simple
                    // network reconnect, so show the real problem.
                    showFatalError(
                        "This QR page does not have permission to read its public Rickshaw record."
                    );
                    return;
                }

                // Temporary listener errors must NOT wipe a valid dashboard.
                if (hasRenderedData) {
                    setConnectionState(
                        "connecting",
                        "Reconnecting - showing last data"
                    );
                } else {
                    setConnectionState("connecting", "Reconnecting...");
                    setLoadingMessage(
                        "Connection interrupted. Retrying automatically..."
                    );
                }

                scheduleReconnect(tokenValue);
            }
        );
    } catch (error) {
        publicUnsubscribe = null;
        hasLiveData = false;
        clearSlowConnectionNotice();

        console.error("Firebase listener setup error:", error);

        if (hasRenderedData) {
            setConnectionState(
                "connecting",
                "Reconnecting - showing last data"
            );
        } else {
            setConnectionState("connecting", "Reconnecting...");
            setLoadingMessage(
                "Connection interrupted. Retrying automatically..."
            );
        }

        scheduleReconnect(tokenValue);
    }
}


// ============================================================
// RECONNECT
// ============================================================

function scheduleReconnect(tokenValue, forcedDelay = null) {
    if (retryTimer) {
        return;
    }

    const delay = forcedDelay === null
        ? retryDelayMs
        : forcedDelay;

    retryTimer = window.setTimeout(() => {
        retryTimer = null;

        if (!navigator.onLine) {
            scheduleReconnect(tokenValue);
            return;
        }

        attachPublicListener(tokenValue);
    }, Math.max(0, delay));

    if (forcedDelay === null) {
        retryDelayMs = Math.min(
            retryDelayMs * 2,
            MAX_RETRY_DELAY_MS
        );
    }
}

function clearReconnectTimer() {
    if (retryTimer) {
        clearTimeout(retryTimer);
        retryTimer = null;
    }
}


// ============================================================
// SLOW CONNECTION NOTICE
//
// Unlike the old version, this NEVER replaces the dashboard with
// an error just because Firebase has not responded within 12-25 sec.
// ============================================================

function startSlowConnectionNotice() {
    clearSlowConnectionNotice();

    slowConnectionTimer = window.setTimeout(() => {
        if (hasLiveData) {
            return;
        }

        if (hasRenderedData) {
            setConnectionState(
                "connecting",
                "Reconnecting - showing last data"
            );
        } else {
            setConnectionState("connecting", "Connection slow - retrying...");
            setLoadingMessage(
                "The connection is slow. The page is still trying automatically..."
            );
        }
    }, SLOW_CONNECTION_NOTICE_MS);
}

function clearSlowConnectionNotice() {
    if (slowConnectionTimer) {
        clearTimeout(slowConnectionTimer);
        slowConnectionTimer = null;
    }
}


// ============================================================
// LIGHTWEIGHT LAST-KNOWN CACHE
//
// Public data is cached without the potentially large Base64 photo.
// If the page is reopened during a brief outage, the visitor can still
// see the last known vehicle state with a clear reconnecting indicator.
// ============================================================

function cacheKey(tokenValue) {
    return "rfid_rickshaw_public_" + tokenValue;
}

function cachePublicRecord(tokenValue, data) {
    try {
        const cached = {
            ...data,
            puller_photo: "",
            pullerPhoto: "",
            __cached_at: new Date().toISOString()
        };

        localStorage.setItem(
            cacheKey(tokenValue),
            JSON.stringify(cached)
        );
    } catch (error) {
        console.warn("Unable to cache public Rickshaw record:", error);
    }
}

function restoreCachedRecord(tokenValue) {
    try {
        const raw = localStorage.getItem(cacheKey(tokenValue));

        if (!raw) {
            return;
        }

        const cached = JSON.parse(raw);

        if (!cached || typeof cached !== "object") {
            return;
        }

        renderRickshaw(cached);
        hasRenderedData = true;
        hasLiveData = false;

        setConnectionState(
            "connecting",
            "Reconnecting - showing last data"
        );
    } catch (error) {
        console.warn("Unable to restore cached Rickshaw record:", error);
    }
}


// ============================================================
// RENDER
// ============================================================

function renderRickshaw(data) {
    showRickshawPage();

    const rickshawNumber = firstValue(
        data.rickshaw_number,
        data.rickshawNumber
    ) || "---";

    const registrationNumber = firstValue(
        data.registration_number,
        data.registrationNumber
    ) || "---";

    const garageName = firstValue(
        data.garage_name,
        data.garageName
    ) || "---";

    const garageLocation = firstValue(
        data.garage_location,
        data.garageLocation
    ) || "---";

    const ownerName = firstValue(
        data.owner_name,
        data.ownerName
    ) || "---";

    const status = String(
        firstValue(data.status, "IDLE")
    ).toUpperCase();

    setText("rickshawNumber", rickshawNumber);
    setText("quickRickshawNumber", rickshawNumber);

    setText("ownerName", ownerName);
    setText("ownerRecord", ownerName === "---" ? "---" : "Verified");
    setText("quickOwnerName", ownerName);

    setText("garageName", garageName);
    setText("garageLocation", garageLocation);
    setText("quickGarageName", garageName);
    setText("registrationNumber", registrationNumber);

    updateStatus(status);

    setText(
        "startedAt",
        status === "ACTIVE"
            ? formatDateTime(data.started_at)
            : "---"
    );

    setText(
        "updatedAt",
        formatDateTime(data.updated_at)
    );

    if (status === "ACTIVE") {
        showActivePuller(data);
    } else {
        showIdlePuller();
    }
}


// ============================================================
// STATUS
// ============================================================

function updateStatus(status) {
    const badge = document.getElementById("statusBadge");
    const text = document.getElementById("status");

    const currentStatus = String(status || "IDLE").toUpperCase();

    if (badge) {
        badge.classList.remove(
            "status-active",
            "status-idle",
            "status-completed"
        );
    }

    if (currentStatus === "ACTIVE") {
        if (badge) badge.classList.add("status-active");
        if (text) text.innerText = "ACTIVE";
        return;
    }

    if (
        currentStatus === "COMPLETED" ||
        currentStatus === "AUTO_ENDED" ||
        currentStatus === "ENDED"
    ) {
        if (badge) badge.classList.add("status-completed");
        if (text) text.innerText = "COMPLETED";
        return;
    }

    if (badge) badge.classList.add("status-idle");
    if (text) text.innerText = "INSIDE GARAGE";
}


// ============================================================
// ACTIVE PULLER
// ============================================================

function showActivePuller(data) {
    const pullerName = firstValue(
        data.puller_name,
        data.pullerName
    ) || "Authorized Puller";

    const pullerCode = firstValue(
        data.puller_code,
        data.pullerCode
    ) || "---";
    const pullerPhone = firstValue(
    data.puller_phone,
    data.pullerPhone
) || "---";



    setText("pullerName", pullerName);
    setText("pullerCode", pullerCode);
    setText("pullerPhone", pullerPhone);
    setText("pullerAuthorization", "RFID Authorized");
    setText("pullerStatus", "Currently Assigned");

    setPullerPhoto(
        firstValue(
            data.puller_photo,
            data.pullerPhoto
        ) || ""
    );
}


// ============================================================
// IDLE PULLER
// ============================================================

function showIdlePuller() {
    setText("pullerName", "No active puller");
    setText("pullerCode", "---");
    setText("pullerPhone", "---");
    setText("pullerAuthorization", "Not Active");
    setText("pullerStatus", "Inside Garage");
    setPullerPhoto("");
}


// ============================================================
// PULLER PHOTO
// ============================================================

function setPullerPhoto(photoUrl) {
    const image = document.getElementById("pullerPhoto");
    const placeholder = document.getElementById("noPullerPhoto");

    if (!image || !placeholder) {
        return;
    }

    const url = String(photoUrl || "").trim();

    if (!url) {
        image.removeAttribute("src");
        image.style.display = "none";
        placeholder.style.display = "flex";
        return;
    }

    image.onload = () => {
        image.style.display = "block";
        placeholder.style.display = "none";
    };

    image.onerror = () => {
        image.removeAttribute("src");
        image.style.display = "none";
        placeholder.style.display = "flex";
    };

    image.src = url;
}


// ============================================================
// CONNECTION STATUS
// ============================================================

function setConnectionState(state, message = "") {
    const container = document.getElementById("connectionState");
    const label = document.getElementById("connectionLabel");

    if (!container || !label) {
        return;
    }

    container.classList.remove(
        "connection-online",
        "connection-connecting",
        "connection-error"
    );

    if (state === "online") {
        container.classList.add("connection-online");
        label.innerText = message || "Live Data Connected";
        return;
    }

    if (state === "error") {
        container.classList.add("connection-error");
        label.innerText = message || "Connection Error";
        return;
    }

    container.classList.add("connection-connecting");
    label.innerText = message || "Reconnecting...";
}


// ============================================================
// HELPERS
// ============================================================

function setText(elementId, value) {
    const element = document.getElementById(elementId);

    if (!element) {
        return;
    }

    if (
        value === null ||
        value === undefined ||
        String(value).trim() === ""
    ) {
        element.innerText = "---";
    } else {
        element.innerText = String(value);
    }
}

function firstValue(...values) {
    for (const value of values) {
        if (
            value !== null &&
            value !== undefined &&
            String(value).trim() !== ""
        ) {
            return value;
        }
    }

    return null;
}

function formatDateTime(value) {
    if (value === null || value === undefined || value === "") {
        return "---";
    }

    try {
        let date;

        if (typeof value === "number") {
            let timestamp = value;
            if (timestamp < 10000000000) {
                timestamp *= 1000;
            }
            date = new Date(timestamp);
        } else {
            date = new Date(value);
        }

        if (Number.isNaN(date.getTime())) {
            return String(value);
        }

        return date.toLocaleString("en-BD", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: true
        });
    } catch (_) {
        return String(value);
    }
}

function showRickshawPage() {
    const loading = document.getElementById("loading");
    const error = document.getElementById("error");
    const rickshaw = document.getElementById("rickshaw");

    if (loading) loading.style.display = "none";
    if (error) error.style.display = "none";
    if (rickshaw) rickshaw.style.display = "block";
}

function setLoadingMessage(message) {
    const loading = document.getElementById("loading");

    if (!loading) {
        return;
    }

    // Loading container currently contains spinner + text div.
    const textNode = loading.querySelector("div:not(.spinner)");

    if (textNode) {
        textNode.innerText = message;
    }
}

function showFatalError(message) {
    clearSlowConnectionNotice();
    clearReconnectTimer();

    const loading = document.getElementById("loading");
    const rickshaw = document.getElementById("rickshaw");
    const error = document.getElementById("error");
    const errorMessage = document.getElementById("errorMessage");

    if (loading) loading.style.display = "none";
    if (rickshaw) rickshaw.style.display = "none";
    if (error) error.style.display = "flex";
    if (errorMessage) errorMessage.innerText = message;

    setConnectionState("error", "Unavailable");
}

function isPermissionError(error) {
    const code = String(error?.code || "").toLowerCase();
    const message = String(error?.message || "").toLowerCase();

    return (
        code.includes("permission") ||
        message.includes("permission denied")
    );
}


// ============================================================
// BROWSER NETWORK EVENTS
// ============================================================

window.addEventListener("offline", () => {
    hasLiveData = false;

    if (hasRenderedData) {
        setConnectionState(
            "connecting",
            "Offline - showing last data"
        );
    } else {
        setConnectionState("connecting", "Offline - waiting for internet");
        setLoadingMessage("No internet connection. Waiting to reconnect...");
    }
});

window.addEventListener("online", () => {
    setConnectionState("connecting", "Reconnecting...");

    if (token) {
        scheduleReconnect(token, 0);
    }
});
