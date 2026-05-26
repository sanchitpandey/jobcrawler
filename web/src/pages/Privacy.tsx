import { Link } from 'react-router-dom'

function Section({ id, title, children }: { id?: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="space-y-3 scroll-mt-20">
      <h2 className="font-serif text-lg text-cream border-b border-line2 pb-2">{title}</h2>
      <div className="space-y-2 text-sm text-cream2 leading-relaxed">{children}</div>
    </section>
  )
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="font-mono text-[11px] uppercase tracking-wider text-mute mt-0.5 shrink-0 w-28">{label}</span>
      <span>{children}</span>
    </div>
  )
}

const LAST_UPDATED = '27 May 2026'

export function Privacy() {
  return (
    <div className="min-h-screen bg-ink text-cream">
      {/* Nav */}
      <header className="border-b border-line2 px-6 h-14 flex items-center justify-between">
        <Link to="/" className="inline-flex items-center gap-2.5">
          <span className="relative w-7 h-7 inline-flex items-center justify-center shrink-0">
            <span className="absolute inset-0 rounded-lg border border-line2" />
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.7">
              <circle cx="12" cy="12" r="3.2" stroke="#FF8A1F" />
              <path d="M12 8.8V4M12 15.2V20M8.8 12H4M15.2 12H20M9.7 9.7L6.3 6.3M14.3 9.7L17.7 6.3M9.7 14.3L6.3 17.7M14.3 14.3L17.7 17.7" stroke="#EDE6D6" />
            </svg>
          </span>
          <span className="font-semibold tracking-tight text-[15px] text-cream">JobCrawler</span>
        </Link>
        <Link to="/login" className="text-sm text-mute hover:text-cream transition">Sign in</Link>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-12 space-y-10">
        <div>
          <h1 className="font-serif text-[2rem] text-cream">Privacy Policy</h1>
          <p className="text-sm text-mute mt-1">Last updated: {LAST_UPDATED}</p>
        </div>

        <Section title="Who we are">
          <p>
            JobCrawler is a job application automation service. We help you discover, score, and apply to
            LinkedIn Easy Apply jobs. To exercise any of the rights below, email{' '}
            <a href="mailto:privacy@jobcrawler.io" className="text-amber hover:text-amber2 underline underline-offset-2">
              privacy@jobcrawler.io
            </a>.
          </p>
        </Section>

        <Section title="Data we collect">
          <div className="space-y-2">
            <Item label="Account">Email address, hashed password (bcrypt, never stored in plain text).</Item>
            <Item label="Profile">Name, contact info, work history, skills, preferences, salary expectations — everything you enter in the profile wizard.</Item>
            <Item label="Applications">Job listings we discover for you, your application history, status transitions, and AI-generated form answers.</Item>
            <Item label="Billing">Subscription tier, Razorpay order IDs and payment status. We never see or store your card number — that stays on Razorpay's servers.</Item>
            <Item label="Usage">LLM token counts (for rate limiting) and HTTP access logs (retained 30 days for security).</Item>
          </div>
        </Section>

        <Section title="How we use it">
          <ul className="list-disc list-inside space-y-1 ml-1">
            <li>Operate the service: job matching, form filling, application tracking.</li>
            <li>Billing and subscription management via Razorpay.</li>
            <li>Security: rate limiting, brute-force detection, session management.</li>
            <li>We do not sell your data or use it for advertising.</li>
          </ul>
        </Section>

        <Section title="Third-party processors">
          <div className="space-y-3">
            <div className="border border-line2 rounded-lg p-4 space-y-1">
              <p className="font-medium text-cream">Razorpay</p>
              <p>
                Handles payment processing. Razorpay retains payment records for 7 years for statutory tax
                compliance — these records persist even if you delete your JobCrawler account. Their privacy
                policy:{' '}
                <a
                  href="https://razorpay.com/privacy/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-amber hover:text-amber2 underline underline-offset-2"
                >
                  razorpay.com/privacy
                </a>
              </p>
            </div>
            <div className="border border-line2 rounded-lg p-4 space-y-1">
              <p className="font-medium text-cream">LLM providers</p>
              <p>
                Job scoring and form-answer generation use one of: Vertex AI (Google), Groq, OpenRouter,
                Cerebras, or Together AI. We send your profile fields and the job description to generate
                a match score and answers. No provider retains this data beyond their standard request
                logging TTL (typically 0–30 days depending on provider).
              </p>
            </div>
            <div className="border border-line2 rounded-lg p-4 space-y-1">
              <p className="font-medium text-cream">Sentry</p>
              <p>
                Error monitoring for the web app. Sentry receives stack traces and browser metadata on
                unhandled exceptions. We configure{' '}
                <span className="font-mono text-xs text-cream2">sendDefaultPii: false</span> — your
                email and profile data are not forwarded.
              </p>
            </div>
          </div>
        </Section>

        <Section title="Data retention">
          <ul className="list-disc list-inside space-y-1 ml-1">
            <li>Account, profile, and application data: retained until you delete your account.</li>
            <li>HTTP access logs: 30 days, then purged.</li>
            <li>Razorpay payment records: 7 years (statutory requirement, outside our control).</li>
          </ul>
        </Section>

        <Section id="rights" title="Your rights">
          <p>
            Under <strong className="text-cream">GDPR</strong> (Art. 15 &amp; 17) and{' '}
            <strong className="text-cream">India DPDP</strong> (§11 &amp; §12), you have:
          </p>
          <div className="space-y-2 mt-2">
            <Item label="Access">
              <span>
                Download everything we hold on you:{' '}
                <Link to="/settings" className="text-amber hover:text-amber2 underline underline-offset-2">
                  Settings → Export Data
                </Link>
              </span>
            </Item>
            <Item label="Erasure">
              <span>
                Permanently delete your account and all data:{' '}
                <Link to="/settings" className="text-amber hover:text-amber2 underline underline-offset-2">
                  Settings → Delete Account
                </Link>
              </span>
            </Item>
            <Item label="Portability">The export is standard JSON — import it into any tool.</Item>
            <Item label="Contact">
              <a href="mailto:privacy@jobcrawler.io" className="text-amber hover:text-amber2 underline underline-offset-2">
                privacy@jobcrawler.io
              </a>
            </Item>
          </div>
        </Section>

        <Section id="cookies" title="Cookies">
          <p>We use three cookies. Two are strictly necessary; one is third-party.</p>
          <div className="mt-3 space-y-2">
            <div className="border border-line2 rounded-lg divide-y divide-line2 overflow-hidden">
              <div className="grid grid-cols-[160px_1fr] gap-4 px-4 py-3 bg-ink2/40">
                <span className="font-mono text-[11px] uppercase tracking-wider text-mute">Cookie</span>
                <span className="font-mono text-[11px] uppercase tracking-wider text-mute">Purpose</span>
              </div>
              <div className="grid grid-cols-[160px_1fr] gap-4 px-4 py-3">
                <span className="font-mono text-xs text-cream2">jc_refresh</span>
                <span>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-green bg-green/10 border border-green/20 rounded-full px-2 py-0.5 mr-2">Strictly necessary</span>
                  HttpOnly, SameSite=Strict, path=/auth. Stores your session refresh token so you stay logged in. No consent required.
                </span>
              </div>
              <div className="grid grid-cols-[160px_1fr] gap-4 px-4 py-3">
                <span className="font-mono text-xs text-cream2">jc_csrf</span>
                <span>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-green bg-green/10 border border-green/20 rounded-full px-2 py-0.5 mr-2">Strictly necessary</span>
                  SameSite=Strict, path=/auth. Double-submit CSRF protection token read by the web client. No consent required.
                </span>
              </div>
              <div className="grid grid-cols-[160px_1fr] gap-4 px-4 py-3">
                <span className="font-mono text-xs text-cream2">razorpay.com</span>
                <span>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-amber bg-amber/10 border border-amber/20 rounded-full px-2 py-0.5 mr-2">Third-party</span>
                  Razorpay's checkout iframe sets analytics and fraud-prevention cookies from razorpay.com when you use the billing page. These are outside our control. You can decline non-essential cookies in the cookie banner; the billing page will show a notice before loading Razorpay.
                </span>
              </div>
            </div>
          </div>
        </Section>

        <Section title="Changes to this policy">
          <p>
            We will update this page when our practices change and note the new date at the top.
            Continued use of the service after changes constitutes acceptance.
          </p>
        </Section>

        <div className="border-t border-line2 pt-6 text-xs text-mute flex items-center justify-between">
          <span>© {new Date().getFullYear()} JobCrawler</span>
          <Link to="/" className="hover:text-cream transition">← Back to home</Link>
        </div>
      </main>
    </div>
  )
}
