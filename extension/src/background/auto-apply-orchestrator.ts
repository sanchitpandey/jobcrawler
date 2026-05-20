/**
 * auto-apply-orchestrator.ts
 *
 * Processes the approved job queue by opening each job URL in a background tab,
 * triggering the linkedin.ts batch apply flow, and recording the result.
 *
 * Flow per job:
 *   set batchMode → PATCH status 'applying' → open tab → wait for signal
 *   → PATCH status 'applied'/'failed'/'skipped' → close tab → delay → repeat
 */

import { getDiscoveryQueue, patchDiscoveryStatus } from "../utils/api-client.js";
import type { AutoApplyStatus, QueueItem } from "../types/index.js";

const DEFAULT_MAX_JOBS = 15;
const HARD_CAP = 25;
const CONSECUTIVE_FAILURE_LIMIT = 3;
const JOB_TIMEOUT_MS = 120_000; // 2 minutes per job
const KEEPALIVE_ALARM = "auto_apply_keepalive";

interface BatchJobResult {
  success: boolean;
  skipped: boolean;
  captcha: boolean;
  filledFields: Record<string, string>;
  error?: string;
}

export class AutoApplyOrchestrator {
  private running = false;
  private stopRequested = false;
  private pendingResolve: ((r: BatchJobResult) => void) | null = null;
  private pendingTabId: number | null = null;
  // Audit N8: validate that batch_job_complete/failed messages name the job
  // we actually opened — a script on a LinkedIn page (with the right origin)
  // would otherwise be able to fake completion of an arbitrary job and
  // corrupt dashboard state / trip the consecutive-failure stop.
  private pendingLinkedinJobId: string | null = null;

  async start(maxJobs = DEFAULT_MAX_JOBS): Promise<void> {
    if (this.running) return;
    this.running = true;
    this.stopRequested = false;

    // Keep the MV3 service worker alive across the long session.
    chrome.alarms.create(KEEPALIVE_ALARM, { periodInMinutes: 0.4 });

    try {
      await this._run(Math.min(maxJobs, HARD_CAP));
    } finally {
      this.running = false;
      await chrome.storage.local.set({ batchMode: false, currentJobId: null });
      chrome.alarms.clear(KEEPALIVE_ALARM);
    }
  }

  stop(): void {
    this.stopRequested = true;
    // Resolve any pending wait so the loop unblocks immediately.
    if (this.pendingResolve) {
      this.pendingResolve({ success: false, skipped: false, captcha: false, filledFields: {} });
      this.pendingResolve = null;
    }
    if (this.pendingTabId !== null) {
      chrome.tabs.remove(this.pendingTabId).catch(() => undefined);
      this.pendingTabId = null;
    }
    this.pendingLinkedinJobId = null;
  }

  /**
   * Validate that a batch_job_complete/failed message is for the job we're
   * currently working on. Audit N8: a script running on a LinkedIn page can
   * pass the SW's origin allowlist; we additionally require the message to
   * come from the active background tab AND to reference the active queue
   * item's linkedin_job_id (extracted from the tab URL). The only exception
   * is the `session_expired` failure, where LinkedIn has redirected the tab
   * to /login / /feed and the job ID is no longer in the URL — we still
   * scope that case to ``pendingTabId`` so a forged message from another
   * LinkedIn tab can't fake a session-expired stop.
   */
  private isMessageForActiveJob(tabId: number, tabUrl: string, error?: string): boolean {
    if (this.pendingResolve === null) return false;
    if (tabId !== this.pendingTabId) return false;
    if (error === "session_expired") return true;
    const expected = this.pendingLinkedinJobId;
    if (!expected) return false;
    // LinkedIn URLs carry the job id as a numeric path segment or query param:
    //   /jobs/view/1234567/  or  ?currentJobId=1234567  or
    //   /jobs/collections/?currentJobId=1234567 etc.
    return tabUrl.includes(expected);
  }

  /** Called by service-worker when it receives 'batch_job_complete' from a tab. */
  handleBatchJobComplete(
    msg: { success: boolean; skipped?: boolean; filledFields?: Record<string, string> },
    tabId: number,
    tabUrl: string,
  ): void {
    if (!this.isMessageForActiveJob(tabId, tabUrl)) return;
    const resolve = this.pendingResolve;
    if (!resolve) return;
    this.pendingResolve = null;
    resolve({
      success: msg.success,
      skipped: msg.skipped ?? false,
      captcha: false,
      filledFields: msg.filledFields ?? {},
    });
  }

  /** Called by service-worker when it receives 'batch_job_failed' from a tab. */
  handleBatchJobFailed(error: string, tabId: number, tabUrl: string): void {
    if (!this.isMessageForActiveJob(tabId, tabUrl, error)) return;
    const resolve = this.pendingResolve;
    if (!resolve) return;
    this.pendingResolve = null;
    resolve({
      success: false,
      skipped: false,
      captcha: error === "captcha_detected",
      filledFields: {},
      error,
    });
  }

  private async _run(limit: number): Promise<void> {
    let queueData: { queue: QueueItem[] };
    try {
      queueData = await getDiscoveryQueue(limit);
    } catch (err) {
      this._notifyPopup({ phase: "stopped", stopReason: String(err) });
      return;
    }

    const queue = queueData.queue;
    let applied = 0;
    let skipped = 0;
    let failed = 0;
    let consecutiveFailures = 0;
    let lastError: string | undefined;

    this._notifyPopup({ phase: "applying", current: 0, total: queue.length, applied, skipped, failed });

    for (let i = 0; i < queue.length; i++) {
      if (this.stopRequested) break;

      const job = queue[i];

      this._notifyPopup({
        phase: "applying",
        current: i + 1,
        total: queue.length,
        applied,
        skipped,
        failed,
        currentJob: { company: job.company, title: job.title, score: job.fit_score },
        lastError,
      });

      await chrome.storage.local.set({ batchMode: true, currentJobId: job.id });
      patchDiscoveryStatus(job.id, "applying").catch(() => undefined);

      const tab = await chrome.tabs.create({ url: job.url, active: false }).catch(() => null);
      if (!tab?.id) {
        await chrome.storage.local.set({ batchMode: false, currentJobId: null });
        failed++;
        consecutiveFailures++;
        if (consecutiveFailures >= CONSECUTIVE_FAILURE_LIMIT) break;
        continue;
      }

      this.pendingTabId = tab.id;
      // Audit N8: capture the expected job id so handleBatchJobComplete /
      // handleBatchJobFailed can reject forged messages from other LinkedIn tabs.
      this.pendingLinkedinJobId = job.linkedin_job_id ?? null;
      await this._waitForTabLoad(tab.id);

      // Detect if the user manually closes the background tab before the apply
      // flow signals completion — resolve immediately instead of waiting for timeout.
      const onTabRemoved = (removedId: number): void => {
        if (removedId !== tab.id || !this.pendingResolve) return;
        chrome.tabs.onRemoved.removeListener(onTabRemoved);
        const resolve = this.pendingResolve;
        this.pendingResolve = null;
        resolve({ success: false, skipped: false, captcha: false, filledFields: {}, error: "tab_closed_by_user" });
      };
      chrome.tabs.onRemoved.addListener(onTabRemoved);

      const result = await this._waitForJobCompletion();

      // Clean up listener in the normal completion path (tab still open).
      chrome.tabs.onRemoved.removeListener(onTabRemoved);

      await chrome.tabs.remove(tab.id).catch(() => undefined);
      this.pendingTabId = null;
      this.pendingLinkedinJobId = null;
      await chrome.storage.local.set({ batchMode: false, currentJobId: null });

      if (result.captcha) {
        patchDiscoveryStatus(job.id, "skipped").catch(() => undefined);
        this._notifyPopup({
          phase: "stopped",
          current: i + 1,
          total: queue.length,
          applied,
          skipped: skipped + 1,
          failed,
          stopReason: "captcha",
        });
        return;
      }

      if (result.error === "session_expired") {
        patchDiscoveryStatus(job.id, "failed").catch(() => undefined);
        this._notifyPopup({
          phase: "stopped",
          current: i + 1,
          total: queue.length,
          applied,
          skipped,
          failed: failed + 1,
          stopReason: "session_expired",
        });
        return;
      }

      if (result.skipped) {
        patchDiscoveryStatus(job.id, "skipped").catch(() => undefined);
        skipped++;
        consecutiveFailures = 0;
        lastError = undefined;
      } else if (result.success) {
        await patchDiscoveryStatus(job.id, "applied", result.filledFields).catch(() => undefined);
        applied++;
        consecutiveFailures = 0;
        lastError = undefined;
      } else {
        patchDiscoveryStatus(job.id, "failed").catch(() => undefined);
        failed++;
        consecutiveFailures++;
        lastError = result.error;
      }

      if (consecutiveFailures >= CONSECUTIVE_FAILURE_LIMIT) {
        this._notifyPopup({
          phase: "stopped",
          current: i + 1,
          total: queue.length,
          applied,
          skipped,
          failed,
          stopReason: "consecutive_failures",
        });
        return;
      }

      // Human-like gap between jobs: 30-90 seconds.
      if (i < queue.length - 1 && !this.stopRequested) {
        await new Promise<void>((r) => setTimeout(r, 30_000 + Math.random() * 60_000));
      }
    }

    this._notifyPopup({ phase: "complete", current: queue.length, total: queue.length, applied, skipped, failed, stopReason: lastError });
  }

  private _waitForJobCompletion(): Promise<BatchJobResult> {
    return new Promise<BatchJobResult>((resolve) => {
      this.pendingResolve = resolve;
      setTimeout(() => {
        if (this.pendingResolve === resolve) {
          this.pendingResolve = null;
          resolve({ success: false, skipped: false, captcha: false, filledFields: {}, error: "timeout" });
        }
      }, JOB_TIMEOUT_MS);
    });
  }

  private _waitForTabLoad(tabId: number): Promise<void> {
    return new Promise<void>((resolve) => {
      const cleanup = (): void => {
        chrome.tabs.onUpdated.removeListener(onUpdated);
        chrome.tabs.onRemoved.removeListener(onRemoved);
      };
      const onUpdated = (_id: number, info: chrome.tabs.TabChangeInfo): void => {
        if (_id === tabId && info.status === "complete") {
          cleanup();
          setTimeout(resolve, 2000 + Math.random() * 1000);
        }
      };
      const onRemoved = (removedId: number): void => {
        if (removedId === tabId) { cleanup(); resolve(); }
      };
      chrome.tabs.onUpdated.addListener(onUpdated);
      chrome.tabs.onRemoved.addListener(onRemoved);
      // Safety timeout — resolve anyway after 30s.
      setTimeout(() => { cleanup(); resolve(); }, 30_000);
    });
  }

  private _notifyPopup(data: AutoApplyStatus & { stopReason?: string }): void {
    chrome.runtime.sendMessage({ type: "auto_apply_progress", ...data }).catch(() => undefined);
    chrome.storage.local.set({ autoApplyStatus: data });
  }
}

export const autoApplyOrchestrator = new AutoApplyOrchestrator();
