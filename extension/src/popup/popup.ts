import {
  getBillingStatus,
  getUsage,
  getDiscoveryStats,
  getSearchPreferences,
  saveSearchPreferences,
  getDiscoveryQueue,
  patchDiscoveryStatus,
  approveBatch,
  type BillingPlan,
  type SearchPreferencePayload,
} from "../utils/api-client.js";
import type { QueueItem } from "../types/index.js";
import { getAuthToken } from "../utils/storage.js";

// ── Types ──────────────────────────────────────────────────────────────────────

type AppState =
  | "NOT_LOGGED_IN"
  | "NO_PREFERENCES"
  | "IDLE"
  | "DISCOVERING"
  | "ENRICHING"
  | "SCORING"
  | "READY"
  | "APPLYING"
  | "PAUSED"
  | "COMPLETE"
  | "REVIEW";

interface StoredDiscoveryStatus {
  phase?: string;
  progress?: number;
  total?: number;
  discovered?: number;
  filtered?: number;
  scored?: number;
  approved?: number;
  needsReview?: number;
  error?: string;
}

interface StoredAutoApplyStatus {
  phase?: string;
  current?: number;
  total?: number;
  applied?: number;
  skipped?: number;
  failed?: number;
  currentJob?: { company: string; title: string; score: number };
  stopReason?: string;
}

interface LocalStorage {
  discoveryStatus?: StoredDiscoveryStatus;
  autoApplyStatus?: StoredAutoApplyStatus;
  user_email?: string;
}

// ── JWT helpers ────────────────────────────────────────────────────────────────

function decodeJwtPayload(token: string): Record<string, unknown> {
  const parts = token.split(".");
  if (parts.length !== 3) return {};
  try {
    const b64 = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(parts[1].length / 4) * 4, "=");
    return JSON.parse(atob(b64)) as Record<string, unknown>;
  } catch {
    return {};
  }
}

// ── Storage helpers ────────────────────────────────────────────────────────────

function readStorage(keys: string[]): Promise<LocalStorage> {
  return new Promise((resolve) =>
    chrome.storage.local.get(keys, (r) => resolve(r as LocalStorage))
  );
}

function getStoredEmail(): Promise<string | null> {
  return readStorage(["user_email"]).then((d) => d.user_email ?? null);
}

function setStoredEmail(email: string): Promise<void> {
  return new Promise((resolve) => chrome.storage.local.set({ user_email: email }, resolve));
}

function clearStoredEmail(): Promise<void> {
  return new Promise((resolve) => chrome.storage.local.remove("user_email", resolve));
}

// ── Service-worker message helpers ────────────────────────────────────────────

function sendLoginMessage(email: string, password: string): Promise<void> {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(
      { type: "LOGIN", payload: { email, password } },
      (response: unknown) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        const r = response as { type: string; payload?: { message?: string } };
        if (r?.type === "ERROR") {
          reject(new Error(r.payload?.message ?? "Login failed"));
          return;
        }
        resolve();
      }
    );
  });
}

function sendLogoutMessage(): Promise<void> {
  return new Promise((resolve) =>
    chrome.runtime.sendMessage({ type: "CLEAR_AUTH_TOKEN" }, () => resolve())
  );
}

// ── DOM refs ───────────────────────────────────────────────────────────────────

const loginView   = document.querySelector<HTMLDivElement>("#login-view")!;
const appView     = document.querySelector<HTMLDivElement>("#app-view")!;

const loginForm      = document.querySelector<HTMLFormElement>("#login-form")!;
const emailInput     = document.querySelector<HTMLInputElement>("#email-input")!;
const passwordInput  = document.querySelector<HTMLInputElement>("#password-input")!;
const loginBtn       = document.querySelector<HTMLButtonElement>("#login-btn")!;
const loginError     = document.querySelector<HTMLParagraphElement>("#login-error")!;

const userAvatar      = document.querySelector<HTMLDivElement>("#user-avatar")!;
const userEmailEl     = document.querySelector<HTMLDivElement>("#user-email-display")!;
const userTierEl      = document.querySelector<HTMLDivElement>("#user-tier-display")!;
const logoutBtn       = document.querySelector<HTMLButtonElement>("#logout-btn")!;

// panels
const prefPanel        = document.querySelector<HTMLDivElement>("#preferences-panel")!;
const idlePanel        = document.querySelector<HTMLDivElement>("#idle-panel")!;
const discoveringPanel = document.querySelector<HTMLDivElement>("#discovering-panel")!;
const enrichingPanel   = document.querySelector<HTMLDivElement>("#enriching-panel")!;
const scoringPanel     = document.querySelector<HTMLDivElement>("#scoring-panel")!;
const readyPanel       = document.querySelector<HTMLDivElement>("#ready-panel")!;
const applyingPanel    = document.querySelector<HTMLDivElement>("#applying-panel")!;
const pausedPanel      = document.querySelector<HTMLDivElement>("#paused-panel")!;
const completePanel    = document.querySelector<HTMLDivElement>("#complete-panel")!;
const reviewPanel      = document.querySelector<HTMLDivElement>("#review-panel")!;

const ALL_PANELS = [
  prefPanel, idlePanel, discoveringPanel, enrichingPanel,
  scoringPanel, readyPanel, applyingPanel, pausedPanel, completePanel, reviewPanel,
];

// preferences panel
const prefKeywords       = document.querySelector<HTMLTextAreaElement>("#pref-keywords")!;
const prefLocation       = document.querySelector<HTMLInputElement>("#pref-location")!;
const prefExp            = document.querySelector<HTMLSelectElement>("#pref-exp")!;
const prefRemote         = document.querySelector<HTMLInputElement>("#pref-remote")!;
const prefThreshold      = document.querySelector<HTMLInputElement>("#pref-threshold")!;
const prefThresholdDisp  = document.querySelector<HTMLSpanElement>("#pref-threshold-display")!;
const preferencesError   = document.querySelector<HTMLParagraphElement>("#preferences-error")!;
const savePrefBtn        = document.querySelector<HTMLButtonElement>("#save-preferences-btn")!;

// idle panel
const statToday    = document.querySelector<HTMLDivElement>("#stat-applied-today")!;
const statWeek     = document.querySelector<HTMLDivElement>("#stat-applied-week")!;
const statQueue    = document.querySelector<HTMLDivElement>("#stat-queue")!;
const discoverBtn  = document.querySelector<HTMLButtonElement>("#discover-btn")!;
const applyBtn     = document.querySelector<HTMLButtonElement>("#apply-btn")!;
const reviewBtn    = document.querySelector<HTMLButtonElement>("#review-btn")!;
const usageCount   = document.querySelector<HTMLDivElement>("#usage-count")!;
const usageBar     = document.querySelector<HTMLDivElement>("#usage-bar")!;
const usageReset   = document.querySelector<HTMLDivElement>("#usage-reset")!;
const usageError   = document.querySelector<HTMLParagraphElement>("#usage-error")!;
const upgradeCard  = document.querySelector<HTMLDivElement>("#upgrade-card")!;
const proStatusCard = document.querySelector<HTMLDivElement>("#pro-status-card")!;
const proPlanLabel = document.querySelector<HTMLSpanElement>("#pro-plan-label")!;
const proExpires   = document.querySelector<HTMLDivElement>("#pro-expires")!;
const planMonthly  = document.querySelector<HTMLButtonElement>("#plan-monthly")!;
const planAnnual   = document.querySelector<HTMLButtonElement>("#plan-annual")!;
const upgradeBtn   = document.querySelector<HTMLButtonElement>("#upgrade-btn")!;
const billingError = document.querySelector<HTMLParagraphElement>("#billing-error")!;

// discovering panel
const discKeyLabel   = document.querySelector<HTMLParagraphElement>("#disc-keyword-label")!;
const discFound      = document.querySelector<HTMLDivElement>("#disc-found")!;
const discProgBar    = document.querySelector<HTMLDivElement>("#disc-progress-bar")!;
const discProgLabel  = document.querySelector<HTMLParagraphElement>("#disc-progress-label")!;
const stopDiscBtn    = document.querySelector<HTMLButtonElement>("#stop-discovery-btn")!;

// enriching panel
const enrichCurrent  = document.querySelector<HTMLSpanElement>("#enrich-current")!;
const enrichTotal    = document.querySelector<HTMLSpanElement>("#enrich-total")!;
const enrichProgBar  = document.querySelector<HTMLDivElement>("#enrich-progress-bar")!;
const stopEnrichBtn  = document.querySelector<HTMLButtonElement>("#stop-enriching-btn")!;

// ready panel
const readyDiscovered   = document.querySelector<HTMLSpanElement>("#ready-discovered")!;
const readyFiltered     = document.querySelector<HTMLSpanElement>("#ready-filtered")!;
const readyScored       = document.querySelector<HTMLSpanElement>("#ready-scored")!;
const readyApproved     = document.querySelector<HTMLSpanElement>("#ready-approved")!;
const readyNeedsReview  = document.querySelector<HTMLSpanElement>("#ready-needs-review")!;
const startApplyBtn     = document.querySelector<HTMLButtonElement>("#start-apply-btn")!;
const readyBackBtn      = document.querySelector<HTMLButtonElement>("#ready-back-btn")!;

// applying panel
const currentJobCard  = document.querySelector<HTMLDivElement>("#current-job-card")!;
const applyCompany    = document.querySelector<HTMLDivElement>("#apply-company")!;
const applyTitle      = document.querySelector<HTMLDivElement>("#apply-title")!;
const applyScore      = document.querySelector<HTMLDivElement>("#apply-score")!;
const applyCurrent    = document.querySelector<HTMLSpanElement>("#apply-current")!;
const applyTotalEl    = document.querySelector<HTMLSpanElement>("#apply-total")!;
const applyProgBar    = document.querySelector<HTMLDivElement>("#apply-progress-bar")!;
const applyApplied    = document.querySelector<HTMLSpanElement>("#apply-applied")!;
const applySkipped    = document.querySelector<HTMLSpanElement>("#apply-skipped")!;
const applyFailed     = document.querySelector<HTMLSpanElement>("#apply-failed")!;
const applyLastError  = document.querySelector<HTMLParagraphElement>("#apply-last-error")!;
const pauseApplyBtn   = document.querySelector<HTMLButtonElement>("#pause-apply-btn")!;
const stopApplyBtn    = document.querySelector<HTMLButtonElement>("#stop-apply-btn")!;

// paused panel
const resumeApplyBtn  = document.querySelector<HTMLButtonElement>("#resume-apply-btn")!;
const pausedStopBtn   = document.querySelector<HTMLButtonElement>("#paused-stop-btn")!;

// complete panel
const completeIcon        = document.querySelector<HTMLDivElement>("#complete-icon")!;
const completeTitleEl     = document.querySelector<HTMLParagraphElement>("#complete-title")!;
const completeApplied     = document.querySelector<HTMLSpanElement>("#complete-applied")!;
const completeSkipped     = document.querySelector<HTMLSpanElement>("#complete-skipped")!;
const completeFailed      = document.querySelector<HTMLSpanElement>("#complete-failed")!;
const completeReasonRow   = document.querySelector<HTMLDivElement>("#complete-reason-row")!;
const completeReasonEl    = document.querySelector<HTMLSpanElement>("#complete-reason")!;
const completeDiscoverBtn = document.querySelector<HTMLButtonElement>("#complete-discover-btn")!;
const completeIdleBtn     = document.querySelector<HTMLButtonElement>("#complete-idle-btn")!;

// review panel
const reviewSubtitle  = document.querySelector<HTMLParagraphElement>("#review-subtitle")!;
const reviewJobList   = document.querySelector<HTMLDivElement>("#review-job-list")!;
const reviewError     = document.querySelector<HTMLParagraphElement>("#review-error")!;
const reviewBackBtn   = document.querySelector<HTMLButtonElement>("#review-back-btn")!;
const approveAllBtn   = document.querySelector<HTMLButtonElement>("#approve-all-btn")!

// ── State ──────────────────────────────────────────────────────────────────────

let currentState: AppState = "NOT_LOGGED_IN";
let selectedPlan: BillingPlan = "monthly";
let cachedPreferences: SearchPreferencePayload | null = null;

// ── Panel / view management ────────────────────────────────────────────────────

const PANEL_FOR: Partial<Record<AppState, HTMLDivElement>> = {
  NO_PREFERENCES: prefPanel,
  IDLE:           idlePanel,
  DISCOVERING:    discoveringPanel,
  ENRICHING:      enrichingPanel,
  SCORING:        scoringPanel,
  READY:          readyPanel,
  APPLYING:       applyingPanel,
  PAUSED:         pausedPanel,
  COMPLETE:       completePanel,
  REVIEW:         reviewPanel,
};

function setState(state: AppState): void {
  currentState = state;

  if (state === "NOT_LOGGED_IN") {
    loginView.classList.add("on");
    appView.classList.remove("on");
    return;
  }

  loginView.classList.remove("on");
  appView.classList.add("on");

  for (const p of ALL_PANELS) p.classList.remove("on");
  PANEL_FOR[state]?.classList.add("on");
}

function setLoggedInHeader(email: string): void {
  userEmailEl.textContent = email;
  userAvatar.textContent = email.charAt(0).toUpperCase();
}

// ── Usage & billing ────────────────────────────────────────────────────────────

async function loadUsage(): Promise<void> {
  try {
    const u = await getUsage();
    const lim = u.limit === -1 ? "∞" : String(u.limit);
    usageCount.innerHTML = `${u.used} <span>/ ${lim}</span>`;
    const pct = u.limit === -1 ? 0 : Math.min(100, Math.round((u.used / u.limit) * 100));
    usageBar.style.width = `${pct}%`;
    userTierEl.textContent = u.is_paid ? "Pro" : "Free";
    const resetsAt = new Date(u.resets_at);
    usageReset.textContent = `Resets ${resetsAt.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
  } catch (err) {
    usageError.textContent = err instanceof Error ? err.message : "Could not load usage";
  }
}

async function loadBillingStatus(): Promise<void> {
  try {
    const s = await getBillingStatus();
    if (s.is_active && s.tier === "paid") {
      upgradeCard.style.display = "none";
      proStatusCard.style.display = "block";
      proPlanLabel.textContent = s.plan === "annual" ? "Annual" : "Monthly";
      if (s.expires_at) {
        proExpires.textContent = `Expires ${new Date(s.expires_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
      }
    } else {
      upgradeCard.style.display = "block";
      proStatusCard.style.display = "none";
    }
  } catch (err) {
    billingError.textContent = err instanceof Error ? err.message : "Could not load billing";
  }
}

function selectPlan(plan: BillingPlan): void {
  selectedPlan = plan;
  planMonthly.classList.toggle("sel", plan === "monthly");
  planAnnual.classList.toggle("sel", plan === "annual");
}

planMonthly.addEventListener("click", () => selectPlan("monthly"));
planAnnual.addEventListener("click",  () => selectPlan("annual"));
upgradeBtn.addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL(`checkout.html?plan=${encodeURIComponent(selectedPlan)}`) });
});

// ── Stats ──────────────────────────────────────────────────────────────────────

async function loadStats(): Promise<void> {
  try {
    const s = await getDiscoveryStats();
    statToday.textContent  = String(s.applied_today);
    statWeek.textContent   = String(s.applied_week);
    statQueue.textContent  = String(s.queue_approved);
    applyBtn.disabled      = s.queue_approved === 0;
    applyBtn.textContent   = s.queue_approved > 0
      ? `Apply to Queue (${s.queue_approved})`
      : "Apply to Queue";
    if (s.scored_needs_review > 0) {
      reviewBtn.style.display = "flex";
      reviewBtn.textContent   = `Review Scored Jobs (${s.scored_needs_review})`;
    } else {
      reviewBtn.style.display = "none";
    }
  } catch {
    // non-fatal: leave as —
  }
}

// ── Preferences ────────────────────────────────────────────────────────────────

function populatePrefsForm(p: SearchPreferencePayload): void {
  prefKeywords.value        = (p.keywords ?? []).join(", ");
  prefLocation.value        = p.location;
  prefExp.value             = p.experience_levels;
  prefRemote.checked        = p.remote_filter === "2";
  prefThreshold.value       = String(p.auto_apply_threshold);
  prefThresholdDisp.textContent = String(p.auto_apply_threshold);
}

function readPrefsForm(): SearchPreferencePayload {
  return {
    keywords: prefKeywords.value.split(",").map((k) => k.trim()).filter(Boolean),
    location: prefLocation.value.trim(),
    experience_levels: prefExp.value,
    remote_filter: prefRemote.checked ? "2" : "",
    time_range: "r86400",
    auto_apply_threshold: parseInt(prefThreshold.value, 10),
    max_daily_applications: 15,
  };
}

prefThreshold.addEventListener("input", () => {
  prefThresholdDisp.textContent = prefThreshold.value;
});

savePrefBtn.addEventListener("click", async () => {
  preferencesError.textContent = "";
  const pref = readPrefsForm();
  if (!pref.keywords || pref.keywords.length === 0) {
    preferencesError.textContent = "Please enter at least one keyword.";
    return;
  }
  savePrefBtn.disabled = true;
  savePrefBtn.textContent = "Saving…";
  try {
    await saveSearchPreferences(pref);
    cachedPreferences = pref;
    setState("IDLE");
    void loadStats();
    void loadUsage();
    void loadBillingStatus();
  } catch (err) {
    preferencesError.textContent = err instanceof Error ? err.message : "Failed to save";
  } finally {
    savePrefBtn.disabled = false;
    savePrefBtn.textContent = "Save & Continue";
  }
});

// ── Discovery controls ────────────────────────────────────────────────────────

function startDiscovery(): void {
  if (!cachedPreferences) return;
  const config = {
    keywords:        cachedPreferences.keywords ?? [],
    location:        cachedPreferences.location,
    experienceLevels: cachedPreferences.experience_levels,
    remoteFilter:    cachedPreferences.remote_filter,
    timeRange:       cachedPreferences.time_range,
  };
  chrome.runtime.sendMessage({ type: "start_discovery", payload: config });
  setState("DISCOVERING");
  discFound.textContent     = "0";
  discProgBar.style.width   = "0%";
  discProgLabel.textContent = "keyword 0 of 0";
  discKeyLabel.textContent  = "Scanning LinkedIn…";
}

discoverBtn.addEventListener("click", startDiscovery);

function stopDiscovery(): void {
  chrome.runtime.sendMessage({ type: "stop_discovery" });
  setState("IDLE");
  void loadStats();
}

stopDiscBtn.addEventListener("click",   stopDiscovery);
stopEnrichBtn.addEventListener("click", stopDiscovery);

// ── Auto-apply controls ───────────────────────────────────────────────────────

function startAutoApply(): void {
  chrome.runtime.sendMessage({ type: "start_auto_apply" });
  setState("APPLYING");
  applyCurrent.textContent    = "0";
  applyTotalEl.textContent    = "0";
  applyApplied.textContent    = "0";
  applySkipped.textContent    = "0";
  applyFailed.textContent     = "0";
  applyProgBar.style.width    = "0%";
  currentJobCard.style.display = "none";
}

applyBtn.addEventListener("click",      startAutoApply);
startApplyBtn.addEventListener("click", startAutoApply);
resumeApplyBtn.addEventListener("click", startAutoApply);

pauseApplyBtn.addEventListener("click", () => {
  // Orchestrator pause not yet supported — stop instead
  chrome.runtime.sendMessage({ type: "stop_auto_apply" });
});
stopApplyBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "stop_auto_apply" });
});
pausedStopBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "stop_auto_apply" });
  setState("IDLE");
  void loadStats();
});

readyBackBtn.addEventListener("click", () => {
  setState("IDLE");
  void loadStats();
});

// ── Review panel ───────────────────────────────────────────────────────────────

reviewBtn.addEventListener("click", () => {
  setState("REVIEW");
  void loadScoredJobs();
});

reviewBackBtn.addEventListener("click", () => {
  setState("IDLE");
  void loadStats();
});

approveAllBtn.addEventListener("click", async () => {
  approveAllBtn.disabled = true;
  approveAllBtn.textContent = "Approving…";
  reviewError.textContent = "";
  try {
    const result = await approveBatch(0);
    reviewSubtitle.textContent = `Approved ${result.approved} job${result.approved !== 1 ? "s" : ""}.`;
    reviewJobList.innerHTML = "";
    void loadStats();
  } catch (err) {
    reviewError.textContent = err instanceof Error ? err.message : "Failed to approve";
  } finally {
    approveAllBtn.disabled = false;
    approveAllBtn.textContent = "Approve All";
  }
});

async function loadScoredJobs(): Promise<void> {
  reviewSubtitle.textContent = "Loading…";
  reviewJobList.innerHTML = "";
  reviewError.textContent = "";
  approveAllBtn.disabled = true;

  try {
    const data = await getDiscoveryQueue(50, "scored");
    const jobs = data.queue;

    if (jobs.length === 0) {
      reviewSubtitle.textContent = "No scored jobs to review.";
      return;
    }

    reviewSubtitle.textContent = `${jobs.length} job${jobs.length !== 1 ? "s" : ""} awaiting review`;
    approveAllBtn.disabled = false;

    for (const job of jobs) {
      reviewJobList.appendChild(makeJobReviewCard(job));
    }
  } catch (err) {
    reviewError.textContent = err instanceof Error ? err.message : "Failed to load jobs";
  }
}

function makeJobReviewCard(job: QueueItem): HTMLDivElement {
  const score = Math.round(job.fit_score ?? 0);
  const scoreColor = score >= 75 ? "var(--green)" : score >= 55 ? "var(--amber)" : "var(--red)";

  const card = document.createElement("div");
  card.style.cssText = "display:flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:7px 10px;margin-bottom:6px";

  const info = document.createElement("div");
  info.style.cssText = "flex:1;min-width:0";
  info.innerHTML = `
    <div style="font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(job.company ?? "")}</div>
    <div style="font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;line-height:1.3">${escHtml(job.title ?? "")}</div>
  `;

  const scoreEl = document.createElement("span");
  scoreEl.style.cssText = `font-family:var(--mono);font-size:13px;font-weight:700;color:${scoreColor};flex-shrink:0`;
  scoreEl.textContent = String(score);

  const approveBtn = document.createElement("button");
  approveBtn.className = "btn btn-g btn-sm";
  approveBtn.style.cssText = "padding:3px 8px;font-size:11px;flex-shrink:0";
  approveBtn.textContent = "✓";
  approveBtn.title = "Approve";

  const rejectBtn = document.createElement("button");
  rejectBtn.className = "btn btn-d btn-sm";
  rejectBtn.style.cssText = "padding:3px 8px;font-size:11px;flex-shrink:0";
  rejectBtn.textContent = "✗";
  rejectBtn.title = "Reject";

  const onAction = async (newStatus: "approved" | "rejected"): Promise<void> => {
    approveBtn.disabled = true;
    rejectBtn.disabled = true;
    try {
      await patchDiscoveryStatus(job.id, newStatus);
      card.style.opacity = "0.4";
      card.style.pointerEvents = "none";
    } catch {
      approveBtn.disabled = false;
      rejectBtn.disabled = false;
    }
  };

  approveBtn.addEventListener("click", () => void onAction("approved"));
  rejectBtn.addEventListener("click",  () => void onAction("rejected"));

  card.append(info, scoreEl, approveBtn, rejectBtn);
  return card;
}

function escHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

completeIdleBtn.addEventListener("click", () => {
  setState("IDLE");
  void loadStats();
});

completeDiscoverBtn.addEventListener("click", () => {
  if (cachedPreferences) {
    startDiscovery();
  } else {
    setState("IDLE");
    void loadStats();
  }
});

// ── Runtime message listener ──────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg: Record<string, unknown>) => {
  if (msg.type === "discovery_status") {
    onDiscoveryStatus(msg);
  } else if (msg.type === "auto_apply_progress") {
    onAutoApplyProgress(msg);
  }
});

function pct(n: number, d: number): string {
  return d > 0 ? `${Math.round((n / d) * 100)}%` : "0%";
}

function onDiscoveryStatus(msg: Record<string, unknown>): void {
  const phase     = msg.phase as string | undefined;
  const progress  = (msg.progress  as number) ?? 0;
  const total     = (msg.total     as number) ?? 0;
  const discovered = (msg.discovered as number) ?? 0;

  if (phase === "discovering" || phase === "filtering") {
    if (currentState !== "DISCOVERING") setState("DISCOVERING");
    discFound.textContent     = String(discovered);
    discProgBar.style.width   = pct(progress, total);
    discProgLabel.textContent = `keyword ${progress} of ${total}`;
  } else if (phase === "enriching") {
    if (currentState !== "ENRICHING") setState("ENRICHING");
    enrichCurrent.textContent  = String(progress);
    enrichTotal.textContent    = String(total);
    enrichProgBar.style.width  = pct(progress, total);
  } else if (phase === "scoring") {
    if (currentState !== "SCORING") setState("SCORING");
  } else if (phase === "complete") {
    setState("READY");
    readyDiscovered.textContent  = String(msg.discovered  ?? "—");
    readyFiltered.textContent    = String(msg.filtered    ?? "—");
    readyScored.textContent      = String(msg.scored      ?? "—");
    readyApproved.textContent    = String(msg.approved    ?? "—");
    readyNeedsReview.textContent = String(msg.needsReview ?? "—");
    const approved = (msg.approved as number) ?? 0;
    startApplyBtn.textContent = approved > 0 ? `Start Applying (${approved} jobs)` : "Start Applying";
    startApplyBtn.disabled = approved === 0;
  } else if (phase === "error") {
    setState("IDLE");
    void loadStats();
  }

  chrome.storage.local.set({ discoveryStatus: msg }).catch(() => undefined);
}

function onAutoApplyProgress(msg: Record<string, unknown>): void {
  const phase   = msg.phase   as string | undefined;
  const current = (msg.current as number) ?? 0;
  const total   = (msg.total   as number) ?? 0;
  const applied = (msg.applied as number) ?? 0;
  const skipped = (msg.skipped as number) ?? 0;
  const failed  = (msg.failed  as number) ?? 0;

  if (phase === "applying") {
    if (currentState !== "APPLYING") setState("APPLYING");
    applyCurrent.textContent = String(current);
    applyTotalEl.textContent = String(total);
    applyProgBar.style.width = pct(current, total);
    applyApplied.textContent = String(applied);
    applySkipped.textContent = String(skipped);
    applyFailed.textContent  = String(failed);
    const job = msg.currentJob as { company: string; title: string; score: number } | undefined;
    if (job) {
      currentJobCard.style.display = "block";
      applyCompany.textContent = job.company;
      applyTitle.textContent   = job.title;
      applyScore.textContent   = `Score ${job.score}`;
    }
    const lastErr = msg.lastError as string | undefined;
    if (lastErr) {
      const REASON_LABELS: Record<string, string> = {
        session_expired:         "Logged out of LinkedIn",
        no_easy_apply_button:    "Easy Apply button not found",
        apply_surface_not_found: "Apply form did not open",
        modal_not_found:         "Apply modal did not open",
        tab_closed_by_user:      "Tab was closed by user",
        timeout:                 "Timed out waiting for page",
        not_job_page:            "Not a job page",
        captcha_detected:        "CAPTCHA detected",
      };
      applyLastError.textContent = `Last failure: ${REASON_LABELS[lastErr] ?? lastErr}`;
      applyLastError.style.display = "block";
    } else {
      applyLastError.style.display = "none";
    }
  } else if (phase === "paused") {
    setState("PAUSED");
  } else if (phase === "complete" || phase === "stopped") {
    setState("COMPLETE");
    completeApplied.textContent = String(applied);
    completeSkipped.textContent = String(skipped);
    completeFailed.textContent  = String(failed);
    const reason = msg.stopReason as string | undefined;
    const REASON_LABELS: Record<string, string> = {
      captcha:              "CAPTCHA detected",
      consecutive_failures: "Too many failures",
      session_expired:      "Logged out of LinkedIn — please sign in and retry",
      no_easy_apply_button: "Easy Apply button not found",
      apply_surface_not_found: "Apply form did not open",
      tab_closed_by_user:   "Tab was closed",
      timeout:              "Timed out waiting for page",
      not_job_page:         "Job page did not load",
      modal_not_found:      "Apply modal did not open",
    };
    if (reason) {
      completeReasonRow.style.display = "flex";
      completeReasonEl.textContent    = REASON_LABELS[reason] ?? reason;
      completeIcon.textContent        = "!";
      completeTitleEl.textContent     = "Session Stopped";
    } else {
      completeReasonRow.style.display = "none";
      completeIcon.textContent        = "✓";
      completeTitleEl.textContent     = "Session Complete";
    }
    void loadStats();
  }

  chrome.storage.local.set({ autoApplyStatus: msg }).catch(() => undefined);
}

// ── Login / logout ────────────────────────────────────────────────────────────

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email    = emailInput.value.trim();
  const password = passwordInput.value;
  if (!email || !password) {
    loginError.textContent = "Email and password are required.";
    return;
  }
  loginBtn.disabled = true;
  loginBtn.textContent = "Signing in…";
  loginError.textContent = "";
  try {
    await sendLoginMessage(email, password);
    await setStoredEmail(email);
    setLoggedInHeader(email);
    await enterLoggedInState();
  } catch (err) {
    loginError.textContent = err instanceof Error ? err.message : "Login failed. Please try again.";
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = "Sign In";
  }
});

logoutBtn.addEventListener("click", async () => {
  await sendLogoutMessage();
  await clearStoredEmail();
  chrome.storage.local.remove(["discoveryStatus", "autoApplyStatus"]);
  cachedPreferences = null;
  emailInput.value   = "";
  passwordInput.value = "";
  setState("NOT_LOGGED_IN");
});

// ── Restore state on popup open ───────────────────────────────────────────────

async function enterLoggedInState(): Promise<void> {
  const storage = await readStorage(["discoveryStatus", "autoApplyStatus"]);

  // Restore in-progress auto-apply
  const as = storage.autoApplyStatus;
  if (as?.phase === "applying") {
    setState("APPLYING");
    applyCurrent.textContent    = String(as.current ?? 0);
    applyTotalEl.textContent    = String(as.total   ?? 0);
    applyApplied.textContent    = String(as.applied ?? 0);
    applySkipped.textContent    = String(as.skipped ?? 0);
    applyFailed.textContent     = String(as.failed  ?? 0);
    applyProgBar.style.width    = pct(as.current ?? 0, as.total ?? 1);
    if (as.currentJob) {
      currentJobCard.style.display = "block";
      applyCompany.textContent = as.currentJob.company;
      applyTitle.textContent   = as.currentJob.title;
      applyScore.textContent   = `Score ${as.currentJob.score}`;
    }
    return;
  }
  if (as?.phase === "paused") {
    setState("PAUSED");
    return;
  }

  // Restore in-progress discovery
  const ds = storage.discoveryStatus;
  const activeDiscoveryPhases = ["discovering", "filtering", "enriching", "scoring"];
  if (ds?.phase && activeDiscoveryPhases.includes(ds.phase)) {
    if (ds.phase === "discovering" || ds.phase === "filtering") {
      setState("DISCOVERING");
      discFound.textContent     = String(ds.discovered ?? 0);
      discProgBar.style.width   = pct(ds.progress ?? 0, ds.total ?? 1);
      discProgLabel.textContent = `keyword ${ds.progress ?? 0} of ${ds.total ?? 0}`;
    } else if (ds.phase === "enriching") {
      setState("ENRICHING");
      enrichCurrent.textContent = String(ds.progress ?? 0);
      enrichTotal.textContent   = String(ds.total    ?? 0);
      enrichProgBar.style.width = pct(ds.progress ?? 0, ds.total ?? 1);
    } else if (ds.phase === "scoring") {
      setState("SCORING");
    }
    return;
  }

  // Restore completed discovery (show READY)
  if (ds?.phase === "complete") {
    setState("READY");
    readyDiscovered.textContent  = String(ds.discovered  ?? "—");
    readyFiltered.textContent    = String(ds.filtered    ?? "—");
    readyScored.textContent      = String(ds.scored      ?? "—");
    readyApproved.textContent    = String(ds.approved    ?? "—");
    readyNeedsReview.textContent = String(ds.needsReview ?? "—");
    const approved = ds.approved ?? 0;
    startApplyBtn.textContent = approved > 0 ? `Start Applying (${approved} jobs)` : "Start Applying";
    startApplyBtn.disabled    = approved === 0;
    return;
  }

  // Normal flow — check preferences
  try {
    const prefs = await getSearchPreferences();
    if (!prefs || !prefs.keywords || prefs.keywords.length === 0) {
      setState("NO_PREFERENCES");
    } else {
      cachedPreferences = prefs;
      populatePrefsForm(prefs);
      setState("IDLE");
      void loadStats();
      void loadUsage();
      void loadBillingStatus();
    }
  } catch {
    // Can't reach backend — go to IDLE anyway
    setState("IDLE");
    void loadStats();
    void loadUsage();
    void loadBillingStatus();
  }
}

// ── Init ───────────────────────────────────────────────────────────────────────

async function init(): Promise<void> {
  const [token, email] = await Promise.all([getAuthToken(), getStoredEmail()]);

  if (token && email) {
    const payload = decodeJwtPayload(token.access_token);
    if (typeof payload.sub === "string") {
      setLoggedInHeader(email);
      await enterLoggedInState();
      return;
    }
  }

  setState("NOT_LOGGED_IN");
}

init();
