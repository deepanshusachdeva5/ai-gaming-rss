(() => {
  const feed        = document.getElementById("feed");
  const searchInput = document.getElementById("search");
  const refreshBtn  = document.getElementById("refresh-btn");
  const statusText  = document.getElementById("status-text");
  const articleCount = document.getElementById("article-count");

  let autoRefreshTimer = null;

  // ---------------------------------------------------------------- helpers

  function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return "";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  function badgeClass(category) {
    if (category === "GitHub")   return "badge-github";
    if (category === "Research") return "badge-research";
    if (category === "Game Dev AI" || category === "Gaming") return "badge-game";
    return "badge-ai"; // "AI Models", "AI", or anything else
  }

  function truncate(text, max = 300) {
    if (!text) return "";
    return text.length > max ? text.slice(0, max).trimEnd() + "…" : text;
  }

  function renderCard(article) {
    const card = document.createElement("article");
    card.className = "card";

    const catLabel = article.category || "AI";

    card.innerHTML = `
      <div class="card-meta">
        <span class="badge ${badgeClass(article.category)}">${catLabel}</span>
        <span class="source-name">${escHtml(article.source)}</span>
        <span class="card-date">${formatDate(article.published)}</span>
      </div>
      <div class="card-title">
        <a href="${escHtml(article.url)}" target="_blank" rel="noopener noreferrer">
          ${escHtml(article.title)}
        </a>
      </div>
      ${article.summary ? `<p class="card-summary">${escHtml(truncate(article.summary))}</p>` : ""}
      <a class="card-link" href="${escHtml(article.url)}" target="_blank" rel="noopener noreferrer">
        Read article &rarr;
      </a>
    `;
    return card;
  }

  function escHtml(str) {
    const d = document.createElement("div");
    d.textContent = str || "";
    return d.innerHTML;
  }

  // ---------------------------------------------------------------- fetch

  async function loadArticles(keyword = "") {
    const url = keyword ? `/api/articles?q=${encodeURIComponent(keyword)}` : "/api/articles";
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const articles = await res.json();

      feed.innerHTML = "";
      if (articles.length === 0) {
        feed.innerHTML = `<div class="empty">No articles found${keyword ? ` for "<strong>${escHtml(keyword)}</strong>"` : ""}.</div>`;
      } else {
        articles.forEach(a => feed.appendChild(renderCard(a)));
      }
      articleCount.textContent = `${articles.length} article${articles.length !== 1 ? "s" : ""}`;
    } catch (err) {
      feed.innerHTML = `<div class="error">Failed to load articles: ${err.message}</div>`;
    }
  }

  async function updateStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      if (data.last_fetched) {
        const d = new Date(data.last_fetched);
        statusText.textContent = `Last updated: ${d.toLocaleTimeString()}`;
      } else {
        statusText.textContent = "No articles fetched yet.";
      }
    } catch {
      statusText.textContent = "Status unavailable.";
    }
  }

  // ---------------------------------------------------------------- events

  // Debounce search
  let searchDebounce = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      loadArticles(searchInput.value.trim());
    }, 350);
  });

  // Manual refresh button
  refreshBtn.addEventListener("click", async () => {
    refreshBtn.disabled = true;
    refreshBtn.textContent = "Refreshing…";
    statusText.textContent = "Fetching latest articles…";
    try {
      await fetch("/api/refresh", { method: "POST" });
      await loadArticles(searchInput.value.trim());
      await updateStatus();
    } catch (err) {
      statusText.textContent = `Refresh failed: ${err.message}`;
    } finally {
      refreshBtn.disabled = false;
      refreshBtn.innerHTML = "&#8635; Refresh";
    }
  });

  // ---------------------------------------------------------------- auto-refresh (every 5 min)
  function scheduleAutoRefresh() {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = setInterval(async () => {
      await loadArticles(searchInput.value.trim());
      await updateStatus();
    }, 5 * 60 * 1000);
  }

  // ---------------------------------------------------------------- feed modal
  const addFeedBtn        = document.getElementById("add-feed-btn");
  const feedModal         = document.getElementById("feed-modal");
  const modalClose        = document.getElementById("modal-close");
  const feedUrlInput      = document.getElementById("feed-url");
  const feedNameInput     = document.getElementById("feed-name");
  const feedCatSelect     = document.getElementById("feed-category");
  const checkFeedBtn      = document.getElementById("check-feed-btn");
  const submitFeedBtn     = document.getElementById("submit-feed-btn");
  const feedUrlStatus     = document.getElementById("feed-url-status");
  const submitStatus      = document.getElementById("submit-status");
  const customFeedsList   = document.getElementById("custom-feeds-list");

  const siteUrlInput      = document.getElementById("site-url");
  const siteNameInput     = document.getElementById("site-name");
  const siteQueryInput    = document.getElementById("site-query");
  const siteCatSelect     = document.getElementById("site-category");
  const submitSiteBtn     = document.getElementById("submit-site-btn");
  const submitSiteStatus  = document.getElementById("submit-site-status");
  const scrapedSitesList  = document.getElementById("scraped-sites-list");

  // ---------------------------------------------------------------- tabs
  document.querySelectorAll(".modal-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".modal-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      const target = tab.dataset.tab;
      document.querySelectorAll(".tab-content").forEach(s => s.classList.add("hidden"));
      document.getElementById(`tab-${target}`).classList.remove("hidden");
    });
  });

  function openModal() {
    feedModal.classList.remove("hidden");
    feedUrlInput.value = "";
    feedNameInput.value = "";
    feedUrlStatus.textContent = "";
    submitStatus.textContent = "";
    siteUrlInput.value = "";
    siteNameInput.value = "";
    siteQueryInput.value = "";
    submitSiteStatus.textContent = "";
    loadCustomFeeds();
    loadScrapedSites();
  }
  function closeModal() { feedModal.classList.add("hidden"); }

  addFeedBtn.addEventListener("click", openModal);
  modalClose.addEventListener("click", closeModal);
  feedModal.addEventListener("click", e => { if (e.target === feedModal) closeModal(); });
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });

  async function loadCustomFeeds() {
    customFeedsList.innerHTML = "<p class='field-hint'>Loading…</p>";
    try {
      const res = await fetch("/api/feeds");
      const feeds = await res.json();
      if (!feeds.length) {
        customFeedsList.innerHTML = "<p class='field-hint'>No custom feeds yet.</p>";
        return;
      }
      customFeedsList.innerHTML = feeds.map(f => `
        <div class="custom-feed-item">
          <div class="custom-feed-info">
            <span class="custom-feed-name">${escHtml(f.name)}</span>
            <span class="custom-feed-url">${escHtml(f.url)}</span>
            <span class="badge ${badgeClass(f.category)}" style="margin-top:4px;width:fit-content">${escHtml(f.category)}</span>
          </div>
          <button class="delete-feed-btn" data-id="${f.id}" title="Remove feed">✕</button>
        </div>
      `).join("");

      customFeedsList.querySelectorAll(".delete-feed-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          await fetch(`/api/feeds/${btn.dataset.id}`, { method: "DELETE" });
          await loadCustomFeeds();
          await loadArticles(searchInput.value.trim());
        });
      });
    } catch {
      customFeedsList.innerHTML = "<p class='field-hint err'>Failed to load feeds.</p>";
    }
  }

  async function loadScrapedSites() {
    scrapedSitesList.innerHTML = "<p class='field-hint'>Loading…</p>";
    try {
      const res = await fetch("/api/sites");
      const sites = await res.json();
      if (!sites.length) {
        scrapedSitesList.innerHTML = "<p class='field-hint'>No scraped websites yet.</p>";
        return;
      }
      scrapedSitesList.innerHTML = sites.map(s => `
        <div class="custom-feed-item">
          <div class="custom-feed-info">
            <span class="custom-feed-name">${escHtml(s.name)}</span>
            <span class="custom-feed-url">${escHtml(s.url)}</span>
            ${s.query ? `<span class="custom-feed-url">Query: ${escHtml(s.query)}</span>` : ""}
            <span class="badge ${badgeClass(s.category)}" style="margin-top:4px;width:fit-content">${escHtml(s.category)}</span>
          </div>
          <button class="delete-feed-btn" data-id="${s.id}" title="Remove site">✕</button>
        </div>
      `).join("");

      scrapedSitesList.querySelectorAll(".delete-feed-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          await fetch(`/api/sites/${btn.dataset.id}`, { method: "DELETE" });
          await loadScrapedSites();
          await loadArticles(searchInput.value.trim());
        });
      });
    } catch {
      scrapedSitesList.innerHTML = "<p class='field-hint err'>Failed to load sites.</p>";
    }
  }

  // "Check" — validate RSS URL and auto-fill name
  checkFeedBtn.addEventListener("click", async () => {
    const url = feedUrlInput.value.trim();
    if (!url) return;
    checkFeedBtn.disabled = true;
    feedUrlStatus.className = "field-hint";
    feedUrlStatus.textContent = "Checking…";
    try {
      const res = await fetch(`/api/feeds/preview?url=${encodeURIComponent(url)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      feedUrlStatus.className = "field-hint ok";
      feedUrlStatus.textContent = `✓ Valid feed — ${data.entry_count} articles found`;
      if (data.title && !feedNameInput.value) feedNameInput.value = data.title;
    } catch (err) {
      feedUrlStatus.className = "field-hint err";
      feedUrlStatus.textContent = `✗ ${err.message}`;
    } finally {
      checkFeedBtn.disabled = false;
    }
  });

  // Submit — add RSS feed
  submitFeedBtn.addEventListener("click", async () => {
    const url = feedUrlInput.value.trim();
    if (!url) { submitStatus.textContent = "Please enter a URL."; return; }
    submitFeedBtn.disabled = true;
    submitFeedBtn.textContent = "Adding…";
    submitStatus.textContent = "";
    try {
      const res = await fetch("/api/feeds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          name: feedNameInput.value.trim(),
          category: feedCatSelect.value,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      submitStatus.className = "field-hint ok";
      submitStatus.textContent = `✓ Added "${data.name}" — ${data.fetched} articles fetched.`;
      feedUrlInput.value = "";
      feedNameInput.value = "";
      feedUrlStatus.textContent = "";
      await loadCustomFeeds();
      await loadArticles(searchInput.value.trim());
    } catch (err) {
      submitStatus.className = "field-hint err";
      submitStatus.textContent = `✗ ${err.message}`;
    } finally {
      submitFeedBtn.disabled = false;
      submitFeedBtn.textContent = "Add Feed";
    }
  });

  // Submit — add scraped website via Tavily
  submitSiteBtn.addEventListener("click", async () => {
    const url = siteUrlInput.value.trim();
    if (!url) { submitSiteStatus.textContent = "Please enter a URL."; return; }
    submitSiteBtn.disabled = true;
    submitSiteBtn.textContent = "Scraping…";
    submitSiteStatus.className = "field-hint";
    submitSiteStatus.textContent = "Contacting Tavily AI…";
    try {
      const res = await fetch("/api/sites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          name: siteNameInput.value.trim(),
          query: siteQueryInput.value.trim(),
          category: siteCatSelect.value,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error);
      submitSiteStatus.className = "field-hint ok";
      submitSiteStatus.textContent = `✓ Added "${data.name}" — ${data.fetched} articles scraped.`;
      siteUrlInput.value = "";
      siteNameInput.value = "";
      siteQueryInput.value = "";
      await loadScrapedSites();
      await loadArticles(searchInput.value.trim());
    } catch (err) {
      submitSiteStatus.className = "field-hint err";
      submitSiteStatus.textContent = `✗ ${err.message}`;
    } finally {
      submitSiteBtn.disabled = false;
      submitSiteBtn.textContent = "Add Website";
    }
  });

  // ---------------------------------------------------------------- init
  (async () => {
    feed.innerHTML = '<div class="loading">Fetching articles…</div>';
    await loadArticles();
    await updateStatus();
    scheduleAutoRefresh();
  })();
})();
