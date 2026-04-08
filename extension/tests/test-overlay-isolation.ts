/**
 * Tests that the overlay is isolated from host page CSS via Shadow DOM,
 * and that cleanup leaves no DOM behind.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  showScoreBadge,
  showReviewPanel,
  removeOverlay,
  __getActiveShadowRoot,
} from "../src/overlay/overlay.js";
import { resetDom } from "./test-setup.js";
import type { ScoreResponse } from "../src/types/index.js";

beforeEach(() => {
  resetDom();
  removeOverlay();
});

const SCORE: ScoreResponse = {
  fit_score: 87,
  verdict: "yes",
  comp_est: null,
  gaps: [],
};

describe("Shadow DOM isolation", () => {
  it("test_shadow_dom_created: badge host has shadow root", () => {
    showScoreBadge(SCORE);
    const host = document.getElementById("jobcrawler-badge-host")!;
    expect(host).not.toBeNull();
    expect(host.shadowRoot).not.toBeNull();
    expect(__getActiveShadowRoot()).toBe(host.shadowRoot);
  });

  it("test_styles_isolated: overlay carries its own stylesheet inside the shadow root", () => {
    // Inject hostile global CSS into the host document. In a real browser, the
    // shadow boundary makes these selectors unreachable. jsdom's CSS engine
    // does not enforce shadow boundaries reliably, so this test verifies the
    // *structural* guarantees: (1) the overlay's own <style> lives inside the
    // shadow root, (2) the host page's <style> does not, (3) document-scope
    // querySelector cannot reach overlay nodes.
    const hostile = document.createElement("style");
    hostile.id = "hostile-css";
    hostile.textContent = `
      .jc-btn-submit { display: none !important; }
      button { background: rgb(255, 0, 0) !important; }
    `;
    document.head.appendChild(hostile);

    void showReviewPanel(
      { title: "T", company: "C", location: "L" },
      [{ name: "email", label: "Email", type: "text" }],
      [
        {
          label: "Email",
          value: "a@b.com",
          source: "pattern",
          confidence: 1,
          is_manual_review: false,
        },
      ],
    );

    const shadow = __getActiveShadowRoot()!;

    // 1. Overlay's stylesheet is *inside* the shadow root.
    const shadowStyles = shadow.querySelectorAll("style");
    expect(shadowStyles.length).toBeGreaterThanOrEqual(1);
    expect(shadowStyles[0].textContent).toContain(".jc-panel");

    // 2. Hostile CSS lives only in document.head, not the shadow root.
    expect(document.getElementById("hostile-css")).not.toBeNull();
    expect(shadow.getElementById("hostile-css")).toBeNull();

    // 3. Document-scope queries cannot pierce the shadow boundary.
    expect(document.querySelector('[data-jc="submit"]')).toBeNull();
    // But the same selector finds it inside the shadow root.
    expect(shadow.querySelector('[data-jc="submit"]')).not.toBeNull();
  });

  it("test_cleanup: removeOverlay clears all hosts", () => {
    showScoreBadge(SCORE);
    void showReviewPanel(
      { title: "T", company: "C", location: "L" },
      [],
      [],
    );
    expect(document.getElementById("jobcrawler-badge-host")).not.toBeNull();
    expect(document.getElementById("jobcrawler-overlay-host")).not.toBeNull();

    removeOverlay();

    expect(document.getElementById("jobcrawler-badge-host")).toBeNull();
    expect(document.getElementById("jobcrawler-overlay-host")).toBeNull();
    expect(__getActiveShadowRoot()).toBeNull();
  });

  it("calling showReviewPanel twice replaces the previous host", () => {
    void showReviewPanel({ title: "T", company: "C", location: "L" }, [], []);
    void showReviewPanel({ title: "T2", company: "C2", location: "L2" }, [], []);
    const hosts = document.querySelectorAll("#jobcrawler-overlay-host");
    expect(hosts.length).toBe(1);
  });
});
