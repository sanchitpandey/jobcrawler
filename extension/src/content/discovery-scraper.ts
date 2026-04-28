// Content script for linkedin.com/jobs/search/* pages.
// Activated by discovery-orchestrator via message — does NOT auto-run on load.

interface RawJob {
  linkedin_job_id: string
  title: string
  company: string
  location: string
  url: string
  posted_text: string
  is_easy_apply: boolean
  applicant_count: string
}

// Returns true when LinkedIn is showing a rate-limit or error page instead of results.
function isRateLimitPage(): boolean {
  const text = document.body.innerText.toLowerCase()
  const title = document.title.toLowerCase()
  return (
    text.includes('something went wrong') ||
    text.includes('too many requests') ||
    text.includes("you've been temporarily blocked") ||
    title.includes('security verification') ||
    title.includes('security check') ||
    !!document.querySelector('.error-content, #error-content')
  )
}

// All LinkedIn search-page selectors in one place — update here when LinkedIn changes DOM
const SELECTORS = {
  jobCard: '.jobs-search-results__list-item, .job-card-container',
  jobTitle: '.job-card-list__title, .job-card-container__link',
  company: '.job-card-container__primary-description, .artdeco-entity-lockup__subtitle',
  location: '.job-card-container__metadata-item, .artdeco-entity-lockup__caption',
  easyApplyBadge: '.job-card-container__apply-method, [aria-label*="Easy Apply"]',
  postedDate: 'time, .job-card-container__listed-time',
  jobLink: 'a[href*="/jobs/view/"]',
  resultsContainer: '.jobs-search-results-list, .scaffold-layout__list',
  noResults: '.jobs-search-no-results-banner',
  applicantCount: '.job-card-container__applicant-count',
}

function extractVisibleJobs(): RawJob[] {
  const jobs: RawJob[] = []
  const cards = document.querySelectorAll(SELECTORS.jobCard)

  for (const card of Array.from(cards)) {
    const linkEl = card.querySelector(SELECTORS.jobLink) as HTMLAnchorElement | null
    if (!linkEl?.href) continue

    const match = linkEl.href.match(/\/jobs\/view\/(\d+)/)
    if (!match) continue

    const jobId = match[1]

    if (jobs.some((j) => j.linkedin_job_id === jobId)) continue

    const titleEl = card.querySelector(SELECTORS.jobTitle)
    const companyEl = card.querySelector(SELECTORS.company)
    const locationEl = card.querySelector(SELECTORS.location)
    const easyApplyEl = card.querySelector(SELECTORS.easyApplyBadge)
    const postedEl = card.querySelector(SELECTORS.postedDate)
    const applicantEl = card.querySelector(SELECTORS.applicantCount)

    jobs.push({
      linkedin_job_id: jobId,
      title: titleEl?.textContent?.trim() ?? '',
      company: companyEl?.textContent?.trim() ?? '',
      location: locationEl?.textContent?.trim() ?? '',
      url: `https://www.linkedin.com/jobs/view/${jobId}/`,
      posted_text: postedEl?.textContent?.trim() ?? '',
      is_easy_apply: !!easyApplyEl,
      applicant_count: applicantEl?.textContent?.trim() ?? '',
    })
  }

  return jobs
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function scrollAndCollectAll(): Promise<RawJob[]> {
  const allJobs: RawJob[] = []
  const seenIds = new Set<string>()
  let consecutiveEmptyScrolls = 0

  while (consecutiveEmptyScrolls < 5) {
    const visible = extractVisibleJobs()
    let newCount = 0

    for (const job of visible) {
      if (!seenIds.has(job.linkedin_job_id)) {
        seenIds.add(job.linkedin_job_id)
        allJobs.push(job)
        newCount++
      }
    }

    if (newCount === 0) {
      consecutiveEmptyScrolls++
    } else {
      consecutiveEmptyScrolls = 0
    }

    const scrollContainer = document.querySelector(SELECTORS.resultsContainer)
    const scrollDistance = 600 + Math.random() * 400

    if (scrollContainer) {
      scrollContainer.scrollTop += scrollDistance
    } else {
      window.scrollBy({ top: scrollDistance, behavior: 'smooth' })
    }

    chrome.runtime.sendMessage({ type: 'discovery_progress', count: allJobs.length })

    // Human-like delay: 1500–3500ms
    await delay(1500 + Math.random() * 2000)
  }

  return allJobs
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'start_discovery_scrape') {
    if (isRateLimitPage()) {
      // Signal rate limit immediately so the orchestrator can pause and retry.
      chrome.runtime.sendMessage({
        type: 'discovery_page_complete',
        jobs: [],
        searchUrl: window.location.href,
        rateLimited: true,
      })
      sendResponse({ ack: true })
      return true
    }
    scrollAndCollectAll().then((jobs) => {
      chrome.runtime.sendMessage({
        type: 'discovery_page_complete',
        jobs,
        searchUrl: window.location.href,
      })
    })
    sendResponse({ ack: true })
  }
  return true
})
