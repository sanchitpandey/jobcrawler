// Content script for linkedin.com/jobs/view/* pages.
// Responds to 'extract_job_details' from enrichment-orchestrator.
// Coexists with orchestrator.ts — does NOT handle apply flow messages.

interface JobDetails {
  linkedin_job_id: string
  description: string
  title: string
  company: string
  applicant_count: string
  has_easy_apply: boolean
}

// Returns true when LinkedIn is showing an error/rate-limit page.
function isErrorPage(): boolean {
  const text = document.body.innerText.toLowerCase()
  const title = document.title.toLowerCase()
  return (
    text.includes('something went wrong') ||
    text.includes('too many requests') ||
    title.includes('security verification') ||
    title.includes('security check')
  )
}

// All LinkedIn job-page selectors in one place — update here when LinkedIn changes DOM
const JD_SELECTORS = {
  description: [
    '.jobs-description__content',
    '.jobs-box__html-content',
    '.jobs-description-content__text',
    '.show-more-less-html__markup',
    '#job-details',
    '.jobs-unified-description__content',
    '.jobs-description__container',
    '.jobs-description-content',
    '.jobs-description__text',
    '[data-test-job-description]',
    '[data-job-description]',
    'section.jobs-description',
    'div[class*="jobs-box__html-content"]',
    'div[class*="jobs-description"] [class*="html-content"]',
    'article[class*="jobs-description"]',
  ],
  title: '.jobs-unified-top-card__job-title, .job-details-jobs-unified-top-card__job-title, .top-card-layout__title, h1',
  company: '.jobs-unified-top-card__company-name, .job-details-jobs-unified-top-card__company-name, .topcard__org-name-link',
  applicants: '.jobs-unified-top-card__applicant-count, .job-details-jobs-unified-top-card__applicant-count',
  easyApplyButton: '.jobs-apply-button--top-card, button[aria-label*="Easy Apply"]',
}

const DESCRIPTION_END_MARKERS = [
  'seniority level',
  'employment type',
  'job function',
  'industries',
  'referrals increase',
  'show more',
  'similar jobs',
]

function cleanText(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

function trimDescriptionFromPageText(text: string): string {
  const cleaned = cleanText(text)
  const lower = cleaned.toLowerCase()
  const startMarkers = ['about the job', 'job description', 'description']
  let start = -1

  for (const marker of startMarkers) {
    const idx = lower.indexOf(marker)
    if (idx !== -1 && (start === -1 || idx < start)) start = idx + marker.length
  }

  const fromStart = start === -1 ? cleaned : cleaned.slice(start).trim()
  const lowerFromStart = fromStart.toLowerCase()
  let end = fromStart.length

  for (const marker of DESCRIPTION_END_MARKERS) {
    const idx = lowerFromStart.indexOf(marker)
    if (idx > 100 && idx < end) end = idx
  }

  return fromStart.slice(0, end).trim()
}

function looksLikeDescription(text: string): boolean {
  if (text.length < 80) return false
  const lower = text.toLowerCase()
  const signals = [
    'responsibilities',
    'requirements',
    'qualifications',
    'experience',
    'skills',
    'about the job',
    'job description',
    'what you',
    'we are',
    'you will',
  ]
  return signals.some((signal) => lower.includes(signal))
}

function elementIsUsableDescription(el: Element): boolean {
  const tag = el.tagName.toLowerCase()
  if (['script', 'style', 'nav', 'header', 'footer', 'button', 'input'].includes(tag)) return false
  const linkCount = el.querySelectorAll('a').length
  const buttonCount = el.querySelectorAll('button').length
  const text = cleanText(el.textContent ?? '')
  if (!looksLikeDescription(text)) return false
  return linkCount + buttonCount < 8
}

export function extractJobDescription(): string {
  for (const selector of JD_SELECTORS.description) {
    const el = document.querySelector(selector)
    const text = cleanText(el?.textContent ?? '')
    if (text) {
      return trimDescriptionFromPageText(text).slice(0, 5000)
    }
  }

  const heading = Array.from(document.querySelectorAll('h2, h3, span, div'))
    .find((el) => cleanText(el.textContent ?? '').toLowerCase() === 'about the job')
  const sectionText = cleanText(
    heading?.closest('section, article, div')?.textContent ??
    heading?.parentElement?.textContent ??
    '',
  )
  if (sectionText) {
    return trimDescriptionFromPageText(sectionText).slice(0, 5000)
  }

  const fallback = Array.from(document.querySelectorAll('main section, main article, main div, section, article'))
    .filter(elementIsUsableDescription)
    .map((el) => trimDescriptionFromPageText(cleanText(el.textContent ?? '')))
    .sort((a, b) => b.length - a.length)[0]
  if (fallback) return fallback.slice(0, 5000)

  const bodyFallback = trimDescriptionFromPageText(document.body.innerText ?? '')
  if (looksLikeDescription(bodyFallback)) return bodyFallback.slice(0, 5000)

  return ''
}

export function extractJobDetails(): JobDetails {
  const match = window.location.href.match(/\/jobs\/view\/(\d+)/)
  const jobId = match?.[1] ?? ''

  return {
    linkedin_job_id: jobId,
    description: extractJobDescription(),
    title: document.querySelector(JD_SELECTORS.title)?.textContent?.trim() ?? '',
    company: document.querySelector(JD_SELECTORS.company)?.textContent?.trim() ?? '',
    applicant_count: document.querySelector(JD_SELECTORS.applicants)?.textContent?.trim() ?? '',
    has_easy_apply: !!document.querySelector(JD_SELECTORS.easyApplyButton),
  }
}

if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg.type !== 'extract_job_details') return

    // If LinkedIn is showing an error/rate-limit page, return empty immediately.
    if (isErrorPage()) {
      sendResponse(extractJobDetails())
      return true
    }

    const check = setInterval(() => {
      const desc = extractJobDescription()
      if (desc.length > 50) {
        clearInterval(check)
        clearTimeout(deadline)
        sendResponse(extractJobDetails())
      }
    }, 500)

    const deadline = setTimeout(() => {
      clearInterval(check)
      sendResponse(extractJobDetails())
    }, 10_000)

    return true // keep message channel open for async sendResponse
  })
}
