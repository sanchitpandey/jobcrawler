import { describe, expect, it, beforeEach } from "vitest";
import {
  extractJobDescription,
  extractJobDetails,
} from "../src/content/job-page-scraper.js";
import { resetDom } from "./test-setup.js";

beforeEach(resetDom);

describe("job-page-scraper", () => {
  it("extracts descriptions from LinkedIn's jobs-box html content container", () => {
    document.body.innerHTML = `
      <main>
        <section>
          <h2>About the job</h2>
          <div class="jobs-box__html-content">
            You will build ML systems, own experimentation, and partner with data science teams.
          </div>
        </section>
      </main>
    `;

    expect(extractJobDescription()).toContain("build ML systems");
  });

  it("falls back to the About the job section when class names change", () => {
    document.body.innerHTML = `
      <main>
        <section class="new-linkedin-description-class">
          <h2>About the job</h2>
          <p>We are hiring a data scientist to build forecasting models.</p>
          <p>Responsibilities include model evaluation, SQL analysis, and stakeholder work.</p>
        </section>
        <section><h2>Seniority level</h2><p>Mid-Senior level</p></section>
      </main>
    `;

    const description = extractJobDescription();

    expect(description).toContain("forecasting models");
    expect(description).toContain("Responsibilities");
    expect(description).not.toContain("Mid-Senior");
  });

  it("extracts title, company, applicants, and Easy Apply state from current job detail selectors", () => {
    window.history.replaceState({}, "", "https://www.linkedin.com/jobs/view/4405354941/");
    document.body.innerHTML = `
      <h1 class="job-details-jobs-unified-top-card__job-title">Data Scientist</h1>
      <div class="job-details-jobs-unified-top-card__company-name">Acme Analytics</div>
      <span class="job-details-jobs-unified-top-card__applicant-count">34 applicants</span>
      <button aria-label="Easy Apply to Data Scientist">Easy Apply</button>
      <div class="jobs-box__html-content">Requirements include Python, ML, and experimentation.</div>
    `;

    const details = extractJobDetails();

    expect(details.linkedin_job_id).toBe("4405354941");
    expect(details.title).toBe("Data Scientist");
    expect(details.company).toBe("Acme Analytics");
    expect(details.applicant_count).toBe("34 applicants");
    expect(details.has_easy_apply).toBe(true);
    expect(details.description).toContain("Python");
  });
});
