const backendUrlInput = document.getElementById("backendUrl");
const tokenInput = document.getElementById("token");
const statusEl = document.getElementById("status");
const saveButton = document.getElementById("save");

function setStatus(message, ok) {
  statusEl.textContent = message;
  statusEl.className = ok ? "ok" : "err";
}

async function load() {
  const { backendUrl, token } = await chrome.storage.sync.get(["backendUrl", "token"]);
  backendUrlInput.value = backendUrl || "http://localhost:8000";
  tokenInput.value = token || "";
}

saveButton.addEventListener("click", async () => {
  const backendUrl = backendUrlInput.value.trim().replace(/\/+$/, "");
  const token = tokenInput.value.trim();

  if (!backendUrl || !token) {
    setStatus("Enter both a backend URL and a token.", false);
    return;
  }

  saveButton.disabled = true;
  setStatus("Testing…", true);

  try {
    const response = await fetch(`${backendUrl}/api/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setStatus(body.error || `Request failed (HTTP ${response.status})`, false);
      return;
    }
    const data = await response.json();
    await chrome.storage.sync.set({ backendUrl, token });
    setStatus(`Saved — signed in as ${data.username}.`, true);
  } catch (err) {
    setStatus(`Could not reach ${backendUrl}: ${err.message}`, false);
  } finally {
    saveButton.disabled = false;
  }
});

load();
