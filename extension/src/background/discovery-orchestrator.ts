import {
  discoveryIngest,
  discoveryEnrich,
  discoveryScoreBatch,
} from "../utils/api-client.js";
import type { DiscoveryConfig, RawJob } from "../types/index.js";

const KEEPALIVE_ALARM = "discovery-keepalive";
const PAGE_SCRAPE_TIMEOUT_MS = 3 * 60 * 1000;   // 3 minutes per page
const ENRICHMENT_DELAY_MIN_MS = 2000;
const ENRICHMENT_DELAY_MAX_MS = 5000;
const TAB_EXTRA_DELAY_MIN_MS = 2000;
const TAB_EXTRA_DELAY_MAX_MS = 3000;
const MAX_PAGES_PER_KEYWORD = 40;  // 40 pages × 25 = 1000 results
const FULL_PAGE_THRESHOLD = 20;    // if ≥20 results, assume more pages exist

const MAX_RATE_LIMITS = 3;
const RATE_LIMIT_PAUSE_MS = 5 * 60 * 1000; // 5 minutes

interface ScrapeResult {
  jobs: RawJob[];
  rateLimited: boolean;
}

class DiscoveryOrchestrator {
  private running = false;
  private rateLimitCount = 0;

  async start(config: DiscoveryConfig): Promise<void> {
    if (this.running) return;
    this.running = true;
    this.rateLimitCount = 0;

    this.startKeepalive();
    this.persistStatus({ phase: "discovering", progress: 0, total: 0 });

    try {
      await this.runDiscovery(config);
    } catch (err) {
      this.persistStatus({ phase: "error", error: String(err) });
    } finally {
      this.running = false;
      this.stopKeepalive();
    }
  }

  stop(): void {
    this.running = false;
  }

  private async runDiscovery(config: DiscoveryConfig): Promise<void> {
    const allRawJobs: RawJob[] = [];

    for (let ki = 0; ki < config.keywords.length; ki++) {
      if (!this.running) break;

      const keyword = config.keywords[ki];
      this.broadcastStatus({
        phase: "discovering",
        progress: ki,
        total: config.keywords.length,
        discovered: this.dedup(allRawJobs).length,
      });

      const baseUrl = this.buildSearchUrl(keyword, config);
      const tab = await chrome.tabs.create({ url: baseUrl, active: false });
      const tabId = tab.id!;

      try {
        for (let page = 0; page < MAX_PAGES_PER_KEYWORD; page++) {
          if (!this.running) break;

          if (page > 0) {
            await chrome.tabs.update(tabId, { url: `${baseUrl}&start=${page * 25}` });
          }

          await this.waitForTabLoad(tabId);

          let { jobs, rateLimited } = await this.runDiscoveryScrape(tabId);

          if (rateLimited) {
            this.rateLimitCount++;

            if (this.rateLimitCount >= MAX_RATE_LIMITS) {
              this.broadcastStatus({
                phase: "error",
                error: "LinkedIn rate limit detected 3 times. Stopping to protect your account.",
              });
              this.running = false;
              return;
            }

            this.broadcastStatus({
              phase: "discovering",
              progress: ki,
              total: config.keywords.length,
              discovered: this.dedup(allRawJobs).length,
              error: `Rate limited by LinkedIn. Pausing 5 min (${this.rateLimitCount}/${MAX_RATE_LIMITS})…`,
            });

            await this.randomDelay(RATE_LIMIT_PAUSE_MS, RATE_LIMIT_PAUSE_MS);
            if (!this.running) break;

            // Retry the same page once after the pause.
            const retryUrl = page > 0 ? `${baseUrl}&start=${page * 25}` : baseUrl;
            await chrome.tabs.update(tabId, { url: retryUrl });
            await this.waitForTabLoad(tabId);
            const retryResult = await this.runDiscoveryScrape(tabId);
            jobs = retryResult.jobs;
            // Don't re-check rateLimited on retry — just use whatever was returned.
          }

          allRawJobs.push(...jobs);

          this.broadcastStatus({
            phase: "discovering",
            progress: ki,
            total: config.keywords.length,
            discovered: this.dedup(allRawJobs).length,
          });

          if (jobs.length < FULL_PAGE_THRESHOLD) break;
        }
      } finally {
        await chrome.tabs.remove(tabId).catch(() => undefined);
      }
    }

    if (!this.running) return;

    const uniqueJobs = this.dedup(allRawJobs);

    this.broadcastStatus({
      phase: "filtering",
      progress: 0,
      total: uniqueJobs.length,
      discovered: uniqueJobs.length,
    });

    const ingestResult = await discoveryIngest(uniqueJobs, "linkedin_extension");
    const needsEnrichment = ingestResult.needs_enrichment;

    this.broadcastStatus({
      phase: "enriching",
      progress: 0,
      total: needsEnrichment.length,
      discovered: uniqueJobs.length,
      filtered: ingestResult.filtered_count,
    });

    await this.enrichJobs(needsEnrichment, uniqueJobs.length, ingestResult.filtered_count);

    if (!this.running) return;

    this.broadcastStatus({
      phase: "scoring",
      progress: 0,
      total: needsEnrichment.length,
    });

    const scoreResult = await discoveryScoreBatch();

    const completeStatus = {
      type: "discovery_status",
      phase: "complete",
      discovered: uniqueJobs.length,
      filtered: ingestResult.ingested,       // jobs that survived the filter
      scored: scoreResult.scored,
      approved: scoreResult.auto_approved,
      needsReview: scoreResult.needs_review,
    };

    // Broadcast to any open popup and persist so reopening the popup shows READY.
    chrome.runtime.sendMessage(completeStatus).catch(() => undefined);
    chrome.storage.local.set({ discoveryStatus: completeStatus }).catch(() => undefined);
  }

  private async enrichJobs(
    jobIds: string[],
    discovered: number,
    filtered: number,
  ): Promise<void> {
    for (let i = 0; i < jobIds.length; i++) {
      if (!this.running) break;

      const jobId = jobIds[i];
      const url = `https://www.linkedin.com/jobs/view/${jobId}/`;

      const tab = await chrome.tabs.create({ url, active: false });
      const tabId = tab.id!;

      try {
        await this.waitForTabLoad(tabId);
        const details = await this.extractJobDetails(tabId);

        // Always enrich even if description is empty — marks job as enriched
        // so score-batch can still score it on title/company alone.
        await discoveryEnrich(
          jobId,
          details?.description ?? "",
          details?.applicant_count ?? "",
        ).catch(() => undefined);
      } finally {
        await chrome.tabs.remove(tabId).catch(() => undefined);
      }

      this.broadcastStatus({
        phase: "enriching",
        progress: i + 1,
        total: jobIds.length,
        discovered,
        filtered,
      });

      await this.randomDelay(ENRICHMENT_DELAY_MIN_MS, ENRICHMENT_DELAY_MAX_MS);
    }
  }

  // Sends 'start_discovery_scrape' and waits for 'discovery_page_complete'.
  // Also handles tab closure (user closes background tab) and rate-limit flag.
  private runDiscoveryScrape(tabId: number): Promise<ScrapeResult> {
    return new Promise((resolve) => {
      const cleanup = (): void => {
        clearTimeout(timer);
        chrome.runtime.onMessage.removeListener(listener);
        chrome.tabs.onRemoved.removeListener(onTabRemoved);
      };

      const timer = setTimeout(() => {
        cleanup();
        resolve({ jobs: [], rateLimited: false });
      }, PAGE_SCRAPE_TIMEOUT_MS);

      const listener = (msg: { type: string; jobs?: RawJob[]; rateLimited?: boolean }): void => {
        if (msg.type === "discovery_page_complete") {
          cleanup();
          resolve({ jobs: msg.jobs ?? [], rateLimited: msg.rateLimited ?? false });
        }
      };

      const onTabRemoved = (removedId: number): void => {
        if (removedId === tabId) {
          cleanup();
          resolve({ jobs: [], rateLimited: false });
        }
      };

      chrome.runtime.onMessage.addListener(listener);
      chrome.tabs.onRemoved.addListener(onTabRemoved);

      chrome.tabs.sendMessage(tabId, { type: "start_discovery_scrape" }).catch(() => {
        cleanup();
        resolve({ jobs: [], rateLimited: false });
      });
    });
  }

  // Sends 'extract_job_details' and awaits the sendResponse callback.
  private extractJobDetails(tabId: number): Promise<{
    description: string;
    applicant_count: string;
  } | null> {
    return new Promise((resolve) => {
      const onTabRemoved = (removedId: number): void => {
        if (removedId === tabId) {
          chrome.tabs.onRemoved.removeListener(onTabRemoved);
          clearTimeout(fallback);
          resolve(null);
        }
      };
      chrome.tabs.onRemoved.addListener(onTabRemoved);

      const fallback = setTimeout(() => {
        chrome.tabs.onRemoved.removeListener(onTabRemoved);
        resolve(null);
      }, 15_000);

      chrome.tabs.sendMessage(
        tabId,
        { type: "extract_job_details" },
        (response) => {
          chrome.tabs.onRemoved.removeListener(onTabRemoved);
          clearTimeout(fallback);
          if (chrome.runtime.lastError) {
            resolve(null);
          } else {
            resolve(response as { description: string; applicant_count: string } | null);
          }
        },
      );
    });
  }

  private waitForTabLoad(tabId: number): Promise<void> {
    return new Promise((resolve) => {
      const cleanup = (): void => {
        chrome.tabs.onUpdated.removeListener(onUpdated);
        chrome.tabs.onRemoved.removeListener(onRemoved);
        clearTimeout(safetyTimer);
      };

      const onUpdated = (tid: number, info: chrome.tabs.TabChangeInfo): void => {
        if (tid === tabId && info.status === "complete") {
          cleanup();
          const extra =
            TAB_EXTRA_DELAY_MIN_MS +
            Math.random() * (TAB_EXTRA_DELAY_MAX_MS - TAB_EXTRA_DELAY_MIN_MS);
          setTimeout(resolve, extra);
        }
      };

      // If the user closes the tab, don't leave waitForTabLoad hanging.
      const onRemoved = (removedId: number): void => {
        if (removedId === tabId) { cleanup(); resolve(); }
      };

      const safetyTimer = setTimeout(() => { cleanup(); resolve(); }, 30_000);

      chrome.tabs.onUpdated.addListener(onUpdated);
      chrome.tabs.onRemoved.addListener(onRemoved);
    });
  }

  private buildSearchUrl(keyword: string, config: DiscoveryConfig): string {
    const params = new URLSearchParams({
      keywords: keyword,
      location: config.location,
      f_EA: "true",
      f_TPR: config.timeRange,
      sortBy: "DD",
    });
    if (config.experienceLevels) params.set("f_E", config.experienceLevels);
    if (config.remoteFilter) params.set("f_WT", config.remoteFilter);
    return `https://www.linkedin.com/jobs/search/?${params.toString()}`;
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

  // Sends status to any open popup AND persists to storage for when popup reopens.
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
