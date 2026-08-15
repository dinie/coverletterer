// CoverLetterer Capture — background service worker.
//
// Click the toolbar icon on a job-ad page to send its URL to CoverLetterer,
// which scrapes the description and creates a JobApplication using your
// default resume. No popup — a single click does everything; feedback is
// shown via the toolbar badge + its hover title (no OS notifications, so no
// icon assets are required for a personal "load unpacked" extension).

const DEFAULT_TITLE = "Add this job to CoverLetterer";
const BADGE_CLEAR_MS = 8000;
let clearTimer = null;

function setBadge(text, color, title) {
  chrome.action.setBadgeText({ text });
  if (color) chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setTitle({ title: title || DEFAULT_TITLE });
  if (clearTimer) clearTimeout(clearTimer);
  if (text) {
    clearTimer = setTimeout(() => {
      chrome.action.setBadgeText({ text: "" });
      chrome.action.setTitle({ title: DEFAULT_TITLE });
    }, BADGE_CLEAR_MS);
  }
}

async function getSettings() {
  const { backendUrl, token } = await chrome.storage.sync.get(["backendUrl", "token"]);
  return { backendUrl: (backendUrl || "").replace(/\/+$/, ""), token: token || "" };
}

// The visible tab URL sometimes carries tracking params (e.g. Indeed's
// ?from=shareddesktop_copy); prefer the page's canonical link when present.
async function getCanonicalUrl(tabId, fallbackUrl) {
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const link = document.querySelector('link[rel="canonical"]');
        return (link && link.href) || window.location.href;
      },
    });
    return result || fallbackUrl;
  } catch (err) {
    // Can't inject into some pages (chrome://, the Web Store, etc.) — fall
    // back to the tab's own URL.
    return fallbackUrl;
  }
}

chrome.action.onClicked.addListener(async (tab) => {
  const { backendUrl, token } = await getSettings();
  if (!backendUrl || !token) {
    setBadge("!", "#d97706", "Set up the extension first: right-click the icon -> Options");
    return;
  }
  if (!tab.id || !tab.url || !/^https?:/.test(tab.url)) {
    setBadge("✗", "#dc2626", "This isn't a regular web page — open a job ad first");
    return;
  }

  setBadge("…", "#3b82f6", "Adding to CoverLetterer…");

  let url;
  try {
    url = await getCanonicalUrl(tab.id, tab.url);

    const response = await fetch(`${backendUrl}/api/applications`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ url }),
    });

    if (response.status === 401) {
      setBadge("!", "#dc2626", "Invalid or missing token — check the extension's Options page");
      return;
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setBadge("✗", "#dc2626", body.error || `Request failed (HTTP ${response.status})`);
      return;
    }

    const data = await response.json();
    const label = [data.job_title, data.company].filter(Boolean).join(" @ ") || "this job";

    if (data.already_existed) {
      setBadge("✓", "#16a34a", `Already tracked: ${label}`);
    } else if (data.status === "parsed") {
      setBadge("✓", "#16a34a", `Added: ${label}`);
    } else if (data.status === "needs_manual_paste") {
      setBadge("!", "#d97706", `Added, but couldn't auto-read the description — open CoverLetterer to paste it in`);
    } else {
      setBadge("!", "#d97706", `Added, but something went wrong parsing it — check CoverLetterer`);
    }
  } catch (err) {
    setBadge("✗", "#dc2626", `Could not reach CoverLetterer: ${err.message}`);
  }
});
