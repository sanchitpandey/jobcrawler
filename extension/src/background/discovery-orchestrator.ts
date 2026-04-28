import {
  discoveryIngest,
  discoveryEnrichBatch,
  discoveryScoreBatch,
} from "../utils/api-client.js";
import type { DiscoveryConfig, RawJob } from "../types/index.js";

const KEEPALIVE_ALARM = "discovery-keepalive";
const SEARCH_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search";
const POSTING_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting";
const MAX_PAGES_PER_KEYWORD = 40;
const FETCH_DELAY_MIN = 300;
const FETCH_DELAY_MAX = 500;
const RATE_LIMIT_WAIT_SEARCH = 5_000;
const RATE_LIMIT_WAIT_ENRICH = 10_000;
const ENRICH_BATCH_SIZE = 50;
const DESCRIPTION_MAX_CHARS = 5_000;

// ── HTML parsing helpers ──────────────────────────────────────────────────────

function stripHtml(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Finds the first element with markerClass as a CSS class, then extracts its text content.
function extractTextNear(html: string, markerClass: string): string {
  const pattern = new RegExp(`class="[^"]*${markerClass}[^"]*"`, "i");
  const match = pattern.exec(html);
  if (!match) return "";
  const tagStart = html.lastIndexOf("<", match.index);
  if (tagStart === -1) return "";
  const chunk = html.slice(tagStart, tagStart + 500);
  return stripHtml(chunk).slice(0, 200);
}

// The guest search API returns a sequence of <li> elements.
// Split on <li to get one chunk per card, extract fields via regex.
function parseJobCards(html: string): RawJob[] {
  const jobs: RawJob[] = [];
  const seen = new Set<string>();

  const parts = html.split(/<li[\s>]/);

  for (let i = 1; i < parts.length; i++) {
    const card = parts[i];

    // Primary: data-entity-urn="urn:li:jobPosting:4394771146" — present on every card div
    const urnMatch = card.match(/data-entity-urn="urn:li:jobPosting:(\d+)"/);
    // Fallback: extract trailing numeric ID from slug URL /jobs/view/some-title-12345678?
    const slugMatch = card.match(/\/jobs\/view\/[^?"]*?-(\d{7,})[?"]/);

    const jobId = (urnMatch ?? slugMatch)?.[1];
    if (!jobId) continue;
    if (seen.has(jobId)) continue;
    seen.add(jobId);

    const titleMatch = card.match(
      /<h3[^>]*base-search-card__title[^>]*>([\s\S]*?)<\/h3>/i,
    );
    const companyMatch = card.match(
      /<h4[^>]*base-search-card__subtitle[^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)<\/a>/i,
    );
    const locationMatch = card.match(/job-search-card__location[^>]*>\s*([^<]+)/i);
    const postedMatch = card.match(/<time[^>]*datetime="([^"]+)"/i);
    const isEasyApply = /easy apply/i.test(card);

    jobs.push({
      linkedin_job_id: jobId,
      title: titleMatch ? stripHtml(titleMatch[1]) : "",
      company: companyMatch ? stripHtml(companyMatch[1]) : "",
      location: locationMatch ? locationMatch[1].trim() : "",
      url: `https://www.linkedin.com/jobs/view/${jobId}/`,
      posted_text: postedMatch ? postedMatch[1] : "",
      is_easy_apply: isEasyApply,
      applicant_count: "",
    });
  }

  return jobs;
}

// The jobPosting endpoint returns a full HTML page.
// Extract the description text from known content containers.
function parseJobDescription(html: string): string {
  const markers = ["show-more-less-html__markup", "description__text"];

  for (const marker of markers) {
    const pattern = new RegExp(`class="[^"]*${marker}[^"]*"`, "i");
    const match = pattern.exec(html);
    if (!match) continue;
    const tagStart = html.lastIndexOf("<", match.index);
    if (tagStart === -1) continue;
    const chunk = html.slice(tagStart, tagStart + 8000);
    const text = stripHtml(chunk);
    if (text.length > 50) return text.slice(0, DESCRIPTION_MAX_CHARS);
  }

  return "";
}

// ── Orchestrator ──────────────────────────────────────────────────────────────

class DiscoveryOrchestrator {
  private running = false;

  async start(config: DiscoveryConfig): Promise<void> {
    if (this.running) return;
    this.running = true;
    this.startKeepalive();
    this.persistStatus({ phase: "discovering", progress: 0, total: 0 });

    try {
      await this.runDiscovery(config);
    } catch (err) {
      this.broadcastStatus({ phase: "error", error: String(err) });
    } finally {
      this.running = false;
      this.stopKeepalive();
    }
  }

  stop(): void {
    this.running = false;
  }

  private async runDiscovery(config: DiscoveryConfig): Promise<void> {
    console.log("[discovery] starting with config:", JSON.stringify(config));
    const allRawJobs: RawJob[] = [];

    if (config.keywords.length === 0) {
      console.warn("[discovery] no keywords in config — nothing to search");
      this.broadcastStatus({ phase: "complete", discovered: 0, filtered: 0, scored: 0, approved: 0, needsReview: 0 });
      return;
    }

    // Split comma-separated location string into individual locations.
    // User may enter "bengaluru, pune, remote" — we run a separate search per location.
    const locations = config.location
      .split(",")
      .map((l) => l.trim())
      .filter(Boolean);
    const effectiveLocations = locations.length > 0 ? locations : [""];

    // Build all keyword × location combinations
    const searches: Array<{ keyword: string; location: string }> = [];
    for (const keyword of config.keywords) {
      for (const location of effectiveLocations) {
        searches.push({ keyword, location });
      }
    }

    // Phase 1: Fetch search result pages via guest API
    for (let si = 0; si < searches.length; si++) {
      if (!this.running) break;
      const { keyword, location } = searches[si];

      for (let page = 0; page < MAX_PAGES_PER_KEYWORD; page++) {
        if (!this.running) break;

        const params = new URLSearchParams({
          keywords: keyword,
          location,
          f_TPR: config.timeRange,
          sortBy: "DD",
          start: String(page * 25),
        });
        if (config.experienceLevels) params.set("f_E", config.experienceLevels);
        if (config.remoteFilter) params.set("f_WT", config.remoteFilter);
        // NOTE: f_EA is unsupported on the guest API; Easy Apply is detected from card HTML.

        const html = await this.fetchWithRetry(
          `${SEARCH_BASE}?${params.toString()}`,
          RATE_LIMIT_WAIT_SEARCH,
        );

        if (html === null) break; // rate-limited after retry or network error

        const jobs = parseJobCards(html);
        console.log(`[discovery] "${keyword}" @ "${location}" page=${page} → ${jobs.length} cards`);
        allRawJobs.push(...jobs);

        const uniqueCount = this.dedup(allRawJobs).length;
        this.broadcastStatus({
          phase: "discovering",
          progress: si,
          total: searches.length,
          discovered: uniqueCount,
          message: `Searching "${keyword}" in ${location || "all locations"}... found ${uniqueCount} jobs`,
        });

        if (jobs.length === 0) break; // end of results for this search
        await this.randomDelay(FETCH_DELAY_MIN, FETCH_DELAY_MAX);
      }
    }

    if (!this.running) return;

    const uniqueJobs = this.dedup(allRawJobs);

    this.broadcastStatus({
      phase: "filtering",
      discovered: uniqueJobs.length,
      message: `Filtering ${uniqueJobs.length} jobs...`,
    });

    const ingestResult = await discoveryIngest(uniqueJobs, "linkedin_extension");
    const needsEnrichment = ingestResult.needs_enrichment;

    this.broadcastStatus({
      phase: "enriching",
      progress: 0,
      total: needsEnrichment.length,
      discovered: uniqueJobs.length,
      filtered: ingestResult.filtered_count,
      message: `Getting details... 0/${needsEnrichment.length}`,
    });

    // Phase 2: Enrich via jobPosting endpoint in batches
    await this.enrichJobs(needsEnrichment, uniqueJobs.length, ingestResult.filtered_count);

    if (!this.running) return;

    this.broadcastStatus({
      phase: "scoring",
      total: needsEnrichment.length,
      message: `Scoring ${needsEnrichment.length} jobs...`,
    });

    const scoreResult = await discoveryScoreBatch();

    const completeStatus = {
      type: "discovery_status",
      phase: "complete",
      discovered: uniqueJobs.length,
      filtered: ingestResult.ingested,
      scored: scoreResult.scored,
      approved: scoreResult.auto_approved,
      needsReview: scoreResult.needs_review,
    };
    chrome.runtime.sendMessage(completeStatus).catch(() => undefined);
    chrome.storage.local.set({ discoveryStatus: completeStatus }).catch(() => undefined);
  }

  private async enrichJobs(
    jobIds: string[],
    discovered: number,
    filtered: number,
  ): Promise<void> {
    type EnrichItem = {
      linkedin_job_id: string;
      description: string;
      title: string;
      company: string;
    };
    const batch: EnrichItem[] = [];

    for (let i = 0; i < jobIds.length; i++) {
      if (!this.running) break;

      const jobId = jobIds[i];
      const html = await this.fetchWithRetry(
        `${POSTING_BASE}/${jobId}`,
        RATE_LIMIT_WAIT_ENRICH,
      );

      if (html !== null) {
        batch.push({
          linkedin_job_id: jobId,
          description: parseJobDescription(html),
          title: extractTextNear(html, "top-card-layout__title"),
          company: extractTextNear(html, "topcard__org-name-link"),
        });
      }

      this.broadcastStatus({
        phase: "enriching",
        progress: i + 1,
        total: jobIds.length,
        discovered,
        filtered,
        message: `Getting details... ${i + 1}/${jobIds.length}`,
      });

      if (batch.length >= ENRICH_BATCH_SIZE || i === jobIds.length - 1) {
        if (batch.length > 0) {
          await discoveryEnrichBatch(batch).catch(() => undefined);
          batch.length = 0;
        }
      }

      await this.randomDelay(FETCH_DELAY_MIN, FETCH_DELAY_MAX);
    }
  }

  // Fetches url; on HTTP 429 waits waitMs then retries once. Returns null on failure.
  private async fetchWithRetry(url: string, waitMs: number): Promise<string | null> {
    let res = await this.doFetch(url);
    if (res === null) return null;

    if (res.status === 429) {
      console.log("[discovery] 429 rate-limited, waiting", waitMs, "ms then retrying");
      await this.randomDelay(waitMs, waitMs + 2_000);
      if (!this.running) return null;
      res = await this.doFetch(url);
      if (res === null || res.status === 429) {
        console.warn("[discovery] still rate-limited after retry, skipping");
        return null;
      }
    }

    if (!res.ok) {
      console.warn("[discovery] fetch failed:", res.status, res.statusText, url.slice(0, 120));
      return null;
    }

    const html = await res.text();
    console.log("[discovery] fetched", html.length, "chars from", url.slice(0, 120));
    return html;
  }

  private offscreenFailed = false; // skip offscreen after first total failure

  private async doFetch(url: string): Promise<Response | null> {
    // Try direct fetch first — works when Chrome grants host_permissions CORS bypass.
    try {
      const res = await fetch(url, {
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
          Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          "Accept-Language": "en-US,en;q=0.5",
        },
      });
      if (res.ok || res.status === 429) return res;
      // Non-ok but not CORS — fall through to offscreen for a retry
    } catch (err) {
      console.warn("[discovery] direct fetch blocked (CORS?), trying offscreen:", String(err));
    }

    // Fallback: route through offscreen document which runs in a page context
    // and is not subject to the same CORS restrictions as the service worker.
    if (this.offscreenFailed) return null;
    try {
      return await this.fetchViaOffscreen(url);
    } catch (err) {
      console.error("[discovery] offscreen fetch also failed:", String(err));
      this.offscreenFailed = true;
      return null;
    }
  }

  private async fetchViaOffscreen(url: string): Promise<Response | null> {
    // Ensure the offscreen document exists.
    const existing = await chrome.offscreen.hasDocument().catch(() => false);
    if (!existing) {
      await chrome.offscreen.createDocument({
        url: "offscreen.html",
        reasons: [chrome.offscreen.Reason.WORKERS],
        justification: "Relay LinkedIn guest API fetch to bypass service-worker CORS",
      });
    }

    const requestId = Math.random().toString(36).slice(2);

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        chrome.runtime.onMessage.removeListener(listener);
        resolve(null);
      }, 15_000);

      const listener = (msg: { type: string; requestId?: string; html?: string; status?: number }): void => {
        if (msg.type !== "OFFSCREEN_FETCH_RESULT" || msg.requestId !== requestId) return;
        clearTimeout(timeout);
        chrome.runtime.onMessage.removeListener(listener);

        const html = msg.html ?? "";
        const status = msg.status ?? 0;

        // Synthesise a minimal Response-like object the rest of the code can consume.
        const blob = new Blob([html], { type: "text/html" });
        const synth = new Response(blob, { status: status || 200 });
        resolve(status > 0 ? synth : null);
      };

      chrome.runtime.onMessage.addListener(listener);
      chrome.runtime.sendMessage({ type: "OFFSCREEN_FETCH", url, requestId }).catch(() => {
        clearTimeout(timeout);
        chrome.runtime.onMessage.removeListener(listener);
        resolve(null);
      });
    });
  }

  private dedup(jobs: RawJob[]): RawJob[] {
    const seen = new Set<string>();
    return jobs.filter((j) => {
      if (seen.has(j.linkedin_job_id)) return false;
      seen.add(j.linkedin_job_id);
      return true;
    });
  }

  private randomDelay(min: number, max: number): Promise<void> {
    return new Promise((r) => setTimeout(r, min + Math.random() * (max - min)));
  }

  private broadcastStatus(data: Record<string, unknown>): void {
    chrome.runtime.sendMessage({ type: "discovery_status", ...data }).catch(() => undefined);
    chrome.storage.local.set({ discoveryStatus: data }).catch(() => undefined);
  }

  private persistStatus(data: Record<string, unknown>): void {
    chrome.storage.local.set({ discoveryStatus: data }).catch(() => undefined);
  }

  private startKeepalive(): void {
    chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.4 });
    chrome.alarms.onAlarm.addListener(this.onKeepaliveAlarm);
  }

  private stopKeepalive(): void {
    chrome.alarms.clear(KEEPALIVE_ALARM).catch(() => undefined);
    chrome.alarms.onAlarm.removeListener(this.onKeepaliveAlarm);
  }

  private readonly onKeepaliveAlarm = (alarm: chrome.alarms.Alarm): void => {
    if (alarm.name === KEEPALIVE_ALARM) {
      chrome.storage.local.get("discoveryStatus").catch(() => undefined);
    }
  };
}

export const discoveryOrchestrator = new DiscoveryOrchestrator();
