import { Link } from 'react-router-dom'

const TICKER_ITEMS = [
  { color: 'text-green', label: 'applied', text: 'ML Engineer @ Razorpay · Bengaluru · 94/100' },
  { color: 'text-green', label: 'applied', text: 'Senior Backend @ Swiggy · Remote · 91/100' },
  { color: 'text-amber', label: 'reviewed', text: 'Data Scientist @ Cred · Bengaluru · 78/100' },
  { color: 'text-green', label: 'applied', text: 'Staff ML @ Flipkart · Bengaluru · 96/100' },
  { color: 'text-green', label: 'applied', text: 'Backend Engineer @ Zerodha · Remote · 89/100' },
  { color: 'text-mute', label: 'skipped', text: 'Frontend Lead @ Meesho · 41/100 (off-target)' },
  { color: 'text-green', label: 'applied', text: 'Applied Scientist @ Sprinklr · Remote · 92/100' },
  { color: 'text-green', label: 'applied', text: 'Backend SDE-2 @ PhonePe · Bengaluru · 90/100' },
]

function TickerRow() {
  return (
    <div className="flex gap-10 px-5 shrink-0">
      {TICKER_ITEMS.map((item, i) => (
        <span key={i}>
          <span className={item.color}>●</span> {item.label} · {item.text}
        </span>
      ))}
    </div>
  )
}

const STEPS = [
  {
    num: '01',
    time: '~3 min',
    title: 'Tell us who you are.',
    desc: "Drop in your resume. Confirm your skills, years of experience, salary band, and target locations. We'll auto-extract everything else.",
    demo: (
      <div className="mt-6 border border-line rounded-lg bg-ink2/60 p-4 font-mono text-xs">
        <div className="flex items-center gap-2 text-mute mb-3">
          <span className="w-2 h-2 rounded-full bg-red-soft" />
          <span className="w-2 h-2 rounded-full bg-amber" />
          <span className="w-2 h-2 rounded-full bg-green" />
          <span className="ml-2">profile.json</span>
        </div>
        <div className="space-y-1.5 text-cream2">
          <div><span className="text-mute">role:</span> <span className="text-cream">"ML Engineer"</span></div>
          <div><span className="text-mute">years:</span> <span className="text-amber">4</span></div>
          <div><span className="text-mute">skills:</span> <span className="text-cream">["pytorch", "ranking", "llm-eval", ...]</span></div>
          <div><span className="text-mute">target_locations:</span> <span className="text-cream">["Bengaluru", "Remote-IN"]</span></div>
          <div><span className="text-mute">min_ctc:</span> <span className="text-amber">28<span className="text-mute">L</span></span></div>
        </div>
      </div>
    ),
  },
  {
    num: '02',
    time: 'click once',
    title: <>Hit <em>Crawl</em>.</>,
    desc: 'The extension paginates through Easy Apply listings that match your filters. Hundreds of jobs, indexed in minutes.',
    demo: (
      <div className="mt-6 border border-line rounded-lg bg-ink2/60 p-5">
        <div className="flex items-center justify-between">
          <div className="font-mono text-xs text-cream2">CRAWLING /jobs/search</div>
          <div className="font-mono text-xs text-amber flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber blink" /> live
          </div>
        </div>
        <div className="mt-4 h-2 bg-line rounded-full overflow-hidden">
          <div className="h-full bg-amber" style={{ width: '67%' }} />
        </div>
        <div className="mt-3 flex items-center justify-between font-mono text-xs">
          <span className="text-cream">page 14 / 21</span>
          <span className="text-cream2">312 jobs found</span>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-2 font-mono text-[10.5px] text-cream2">
          <div className="border border-line rounded px-2 py-1.5">~1.8s/page</div>
          <div className="border border-line rounded px-2 py-1.5">human delay</div>
          <div className="border border-line rounded px-2 py-1.5">no headless</div>
        </div>
      </div>
    ),
  },
  {
    num: '03',
    time: 'LLM scoring',
    title: <>Each job gets a <em className="text-amber">score</em>.</>,
    desc: 'Every JD is read against your profile by a tuned LLM. Below your threshold (default 75) we skip. Above, we queue for application.',
    demo: (
      <div className="mt-6 space-y-2.5">
        {[
          { score: 94, color: 'bg-green', w: '94%', label: 'Staff ML @ Flipkart' },
          { score: 88, color: 'bg-green', w: '88%', label: 'SDE-2 Backend @ Zerodha' },
          { score: 61, color: 'bg-amber', w: '61%', label: 'Frontend @ Razorpay' },
          { score: 38, color: 'bg-mute', w: '38%', label: 'QA Manual @ Infosys', dim: true },
        ].map((row) => (
          <div key={row.score} className={`border border-line rounded-md bg-ink2/60 p-3 flex items-center gap-3 font-mono text-xs${row.dim ? ' opacity-60' : ''}`}>
            <div className={`w-9 ${row.dim ? 'text-mute' : 'text-cream'}`}>{row.score}</div>
            <div className="flex-1 h-1.5 bg-line rounded-full overflow-hidden">
              <div className={`h-full ${row.color}`} style={{ width: row.w }} />
            </div>
            <div className={`truncate w-40 text-right ${row.dim ? 'text-mute line-through' : 'text-cream2'}`}>{row.label}</div>
          </div>
        ))}
      </div>
    ),
  },
  {
    num: '04',
    time: 'overnight',
    title: <>It applies. <em>Slowly.</em></>,
    desc: 'Random delays between 40s–4min. Mouse jitter. Realistic typing. It looks like you, having a productive evening — not a script.',
    demo: (
      <div className="mt-6 border border-line rounded-lg bg-ink2/60 p-4 font-mono text-xs space-y-1.5">
        <div className="flex justify-between"><span className="text-mute">22:14:08</span><span className="text-green">→ apply: ML @ Razorpay</span></div>
        <div className="flex justify-between"><span className="text-mute">22:16:51</span><span className="text-cream">resume.pdf attached</span></div>
        <div className="flex justify-between"><span className="text-mute">22:17:33</span><span className="text-cream">screening Q&A · 4 fields</span></div>
        <div className="flex justify-between"><span className="text-mute">22:18:44</span><span className="text-green">✓ submitted</span></div>
        <div className="flex justify-between"><span className="text-mute">22:21:02</span><span className="text-cream2">→ idle 2m 18s</span></div>
        <div className="flex justify-between"><span className="text-mute">22:23:20</span><span className="text-green">→ apply: Backend @ Zerodha</span></div>
      </div>
    ),
  },
]

const CONCERNS = [
  {
    num: '01',
    q: '"Won\'t LinkedIn ban me?"',
    a: "JobCrawler runs inside your Chrome session — same cookies, same fingerprint, same IP as when you browse normally. No headless browser, no proxy, no API abuse. From LinkedIn's side it looks like a logged-in human clicking through Easy Apply slowly. We've run 1.4M applications across 8,000 accounts. Zero bans.",
    badge: '0 bans across 1.4M applications',
    badgeColor: 'text-green',
  },
  {
    num: '02',
    q: '"What if it applies to a job I\'d hate?"',
    a: "Set a minimum score (default 75). Set a hard blocklist of companies. Set a \"review queue\" mode where it surfaces matches and you tap to apply. Defaults are conservative on purpose — most users start in review mode for the first 24 hours, then graduate to autopilot once they trust the scoring.",
    badge: 'review-mode for the first 24h, by default',
    badgeColor: 'text-cream2',
  },
  {
    num: '03',
    q: '"Where does my data go?"',
    a: 'Your resume and profile sit on our cloud (encrypted, India region). Job descriptions are sent to our scoring API, which forwards them to the LLM with your profile redacted of PII. We never store LinkedIn cookies, never see your password, and you can wipe everything with one button.',
    badge: 'Open-source extension · India-region storage',
    badgeColor: 'text-cream2',
  },
]

const TESTIMONIALS = [
  { initials: 'PR', color: 'bg-amber/20 text-amber', name: 'Priya R.', role: 'ML Engineer · Bengaluru', quote: '"Got 6 interviews in week one. I haven\'t logged into LinkedIn manually in a month."' },
  { initials: 'AK', color: 'bg-green/20 text-green', name: 'Arjun K.', role: 'Backend Dev · Remote', quote: '"I was suspicious. Started in review mode. After 2 days I let it loose. The match scores are scary good."' },
  { initials: 'SM', color: 'bg-cream/10 text-cream', name: 'Sneha M.', role: 'Data Scientist · Hyderabad', quote: '"Notice period was 60 days. JobCrawler did the boring part. I just showed up to the calls."' },
]

const FAQS = [
  {
    q: 'Will LinkedIn detect this and ban my account?',
    a: "Short answer: no. JobCrawler runs inside your real Chrome session — it's a Manifest V3 extension, not a bot. There's no automated browser, no scraped API, no IP rotation. From LinkedIn's perspective, it's you, clicking buttons. We add randomized delays (40s–4min between applications) so the cadence looks human. Across 1.4M applications and 8,000+ accounts, we've never had a single ban.",
  },
  {
    q: "What if it applies to a job I'd never want?",
    a: "You set the minimum match score (we suggest 75/100). You set a company blocklist. You can require a manual tap before any apply — that's \"review mode\" and we recommend it for the first 24 hours so you can calibrate.",
  },
  {
    q: 'Does it answer those custom screening questions?',
    a: "Yes — for the easy ones (years of experience, notice period, current CTC, expected CTC, work auth) it pulls from your profile. For long-form questions, the default is to flag for review. We will never fabricate work experience or credentials.",
  },
  {
    q: 'Where is my resume stored?',
    a: "Encrypted at rest in AWS Mumbai (ap-south-1). It's only decrypted in-memory when the extension uploads it to LinkedIn or when scoring needs to read your skills. There's a \"delete everything\" button in Settings.",
  },
  {
    q: 'Do you support non-Easy-Apply jobs?',
    a: "Not yet. Easy Apply covers ~70% of relevant LinkedIn postings. External-redirect jobs (Greenhouse, Lever, company portals) are on the roadmap for Q3 2026.",
  },
  {
    q: 'Can I pause or stop a run mid-way?',
    a: 'One click. Or close the LinkedIn tab. Or hit Cmd/Ctrl + period. Any of those — and the next run picks up cleanly from where the queue left off.',
  },
]

export function Landing() {
  return (
    <div className="font-sans antialiased bg-ink text-cream">
      {/* Google Fonts */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />

      {/* Top bar */}
      <div className="border-b border-line">
        <div className="max-w-[1240px] mx-auto px-6 h-10 flex items-center justify-between font-mono text-[11px] text-cream2">
          <span className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-green blink" />
            <span>SYSTEM ONLINE · 4,218 applications today</span>
          </span>
          <div className="hidden md:flex items-center gap-5">
            <span>v1.4.2</span>
            <span>·</span>
            <span>Made in Bengaluru</span>
          </div>
        </div>
      </div>

      {/* Nav */}
      <header className="border-b border-line">
        <div className="max-w-[1240px] mx-auto px-6 h-16 flex items-center justify-between">
          <a href="#" className="flex items-center gap-2.5">
            <span className="relative w-7 h-7 inline-flex items-center justify-center">
              <span className="absolute inset-0 rounded-md border border-line2" />
              <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.7">
                <circle cx="12" cy="12" r="3.2" className="text-amber" stroke="currentColor" />
                <path d="M12 8.8V4M12 15.2V20M8.8 12H4M15.2 12H20M9.7 9.7L6.3 6.3M14.3 9.7L17.7 6.3M9.7 14.3L6.3 17.7M14.3 14.3L17.7 17.7" className="text-cream" />
              </svg>
            </span>
            <span className="font-semibold tracking-tight text-[15px]">JobCrawler</span>
            <span className="ml-1 font-mono text-[10px] text-mute uppercase tracking-widest">/early access</span>
          </a>
          <nav className="hidden md:flex items-center gap-7 text-[13px] text-cream2">
            <a href="#how" className="hover:text-cream">How it works</a>
            <a href="#pricing" className="hover:text-cream">Pricing</a>
            <a href="#faq" className="hover:text-cream">FAQ</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link to="/login" className="hidden md:inline-flex h-9 items-center px-3 text-[13px] text-cream2 hover:text-cream">Sign in</Link>
            <Link to="/register" className="inline-flex items-center gap-2 h-9 px-3.5 rounded-md bg-cream text-ink text-[13px] font-medium hover:bg-white transition">
              Get started
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden" style={{ background: 'radial-gradient(60% 50% at 70% 0%, rgba(255,138,31,0.18), transparent 60%), radial-gradient(40% 40% at 10% 20%, rgba(125,220,138,0.06), transparent 60%)' }}>
        <div className="absolute inset-0 grid-bg opacity-50" />
        <div className="relative max-w-[1240px] mx-auto px-6 pt-20 pb-24 md:pt-28 md:pb-32">
          <div className="flex items-center gap-3 font-mono text-[11px] text-cream2 mb-7">
            <span className="px-2 py-1 border border-line2 rounded-full">CHROME · MV3</span>
            <span className="px-2 py-1 border border-line2 rounded-full">LinkedIn Easy Apply</span>
            <span className="px-2 py-1 border border-line2 rounded-full">India · Remote</span>
          </div>

          <h1 className="font-serif text-[68px] md:text-[104px] leading-[0.95] tracking-[-0.02em] max-w-[12ch]">
            Apply to <span className="italic text-amber">300 jobs</span><br />
            while you <span className="italic">sleep.</span>
          </h1>

          <p className="mt-8 max-w-[58ch] text-lg md:text-[19px] leading-[1.55] text-cream2">
            JobCrawler is a Chrome extension that scans LinkedIn for matching roles, scores each one against your profile with an LLM, and auto-applies to the best ones — at human speed, while you do literally anything else.
          </p>

          <div className="mt-10 flex flex-wrap items-center gap-3">
            <Link to="/register" className="group inline-flex items-center gap-2.5 h-12 px-5 rounded-md bg-amber text-ink text-[15px] font-semibold hover:bg-amber2 transition">
              Get started — it's free for 7 days
              <svg viewBox="0 0 24 24" className="w-4 h-4 -mr-0.5 transition group-hover:translate-x-0.5" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </Link>
            <a href="#how" className="inline-flex items-center gap-2 h-12 px-4 rounded-md border border-line2 text-[14px] text-cream hover:bg-ink2">
              See how it works →
            </a>
            <span className="ml-1 font-mono text-xs text-mute">no card · uninstall in one click</span>
          </div>

          {/* Stat strip */}
          <div className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-px bg-line2 border border-line2 rounded-lg overflow-hidden">
            {[
              { label: 'Avg. apps / night', value: '142' },
              { label: 'Median match score', value: <span>87<span className="text-cream2 text-xl">/100</span></span> },
              { label: 'Time saved / wk', value: '14h' },
              { label: 'Bengaluru users', value: '2,400+' },
            ].map((stat, i) => (
              <div key={i} className="bg-ink p-5">
                <div className="font-mono text-[11px] text-mute uppercase tracking-wider">{stat.label}</div>
                <div className="mt-2 font-mono text-3xl text-cream">{stat.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Ticker */}
      <section className="border-y border-line overflow-hidden bg-ink2/60">
        <div className="relative">
          <div className="absolute inset-y-0 left-0 w-24 bg-gradient-to-r from-ink2 to-transparent z-10" />
          <div className="absolute inset-y-0 right-0 w-24 bg-gradient-to-l from-ink2 to-transparent z-10" />
          <div className="flex marquee-track whitespace-nowrap py-3 font-mono text-xs text-cream2">
            <TickerRow />
            <TickerRow />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="py-28">
        <div className="max-w-[1240px] mx-auto px-6">
          <div className="flex items-end justify-between flex-wrap gap-6 mb-14">
            <div className="max-w-2xl">
              <div className="font-mono text-[11px] uppercase tracking-widest text-amber">/01 · how it works</div>
              <h2 className="mt-3 font-serif text-5xl md:text-6xl tracking-tight leading-[1.02]">
                Set it up once.<br /><span className="italic text-cream2">Then forget it exists.</span>
              </h2>
            </div>
            <p className="max-w-sm text-cream2 text-[15px] leading-relaxed">
              The whole loop runs in your browser. Your LinkedIn session never leaves the device. We never ask for your password.
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-px bg-line2 border border-line2 rounded-xl overflow-hidden">
            {STEPS.map((step) => (
              <div key={step.num} className="bg-ink p-8 md:p-10">
                <div className="flex items-baseline justify-between">
                  <div className="font-mono text-[11px] text-mute">STEP {step.num}</div>
                  <div className="font-mono text-[11px] text-cream2">{step.time}</div>
                </div>
                <h3 className="mt-3 font-serif text-3xl">{step.title}</h3>
                <p className="mt-3 text-cream2 text-[14.5px] leading-relaxed">{step.desc}</p>
                {step.demo}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust / Concerns */}
      <section className="py-28 border-t border-line">
        <div className="max-w-[1240px] mx-auto px-6">
          <div className="max-w-3xl mb-16">
            <div className="font-mono text-[11px] uppercase tracking-widest text-amber">/02 · the elephant in the room</div>
            <h2 className="mt-3 font-serif text-5xl md:text-6xl tracking-tight leading-[1.02]">
              Yes, we know <span className="italic">exactly</span> what you're thinking.
            </h2>
          </div>

          <div className="grid md:grid-cols-3 gap-px bg-line2 border border-line2 rounded-xl overflow-hidden">
            {CONCERNS.map((c) => (
              <div key={c.num} className="bg-ink p-8">
                <div className="font-mono text-[11px] text-mute mb-3">CONCERN · {c.num}</div>
                <h3 className="font-serif text-2xl leading-tight mb-4">{c.q}</h3>
                <p className="text-cream2 text-sm leading-relaxed">{c.a}</p>
                <div className={`mt-5 flex items-center gap-2 font-mono text-[11px] ${c.badgeColor}`}>
                  <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 12l4 4L19 6" /></svg>
                  {c.badge}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-px grid md:grid-cols-4 gap-px bg-line2 border-x border-line2 border-b border-line2 rounded-b-xl overflow-hidden">
            {[
              { label: 'Stops on', text: 'Captcha, login wall, salary mismatch, blocklist hit' },
              { label: 'Throttle', text: '40s–4min per app · randomized' },
              { label: 'Daily cap', text: 'Defaults to 50 apps/day · adjustable' },
              { label: 'Kill switch', text: 'Cmd+. or close tab — instant' },
            ].map((item) => (
              <div key={item.label} className="bg-ink p-5">
                <div className="font-mono text-[10px] text-mute uppercase tracking-widest">{item.label}</div>
                <div className="mt-2 text-sm">{item.text}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="border-y border-line bg-ink2/40 py-24">
        <div className="max-w-[1240px] mx-auto px-6">
          <div className="font-mono text-[11px] uppercase tracking-widest text-amber mb-2">/03 · what users say</div>
          <h2 className="font-serif text-4xl md:text-5xl tracking-tight leading-[1.05] max-w-3xl">
            No more refreshing<br />LinkedIn at 1AM.
          </h2>
          <div className="mt-12 grid md:grid-cols-3 gap-5">
            {TESTIMONIALS.map((t) => (
              <figure key={t.initials} className="border border-line rounded-xl p-7 bg-ink">
                <blockquote className="font-serif text-[22px] leading-snug">{t.quote}</blockquote>
                <figcaption className="mt-6 flex items-center gap-3">
                  <div className={`w-9 h-9 rounded-full flex items-center justify-center font-mono text-[11px] ${t.color}`}>{t.initials}</div>
                  <div>
                    <div className="text-[13px] font-medium">{t.name}</div>
                    <div className="font-mono text-[11px] text-mute">{t.role}</div>
                  </div>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-28">
        <div className="max-w-[1240px] mx-auto px-6">
          <div className="grid md:grid-cols-[1fr_2fr] gap-12 items-start">
            <div>
              <div className="font-mono text-[11px] uppercase tracking-widest text-amber">/04 · pricing</div>
              <h2 className="mt-3 font-serif text-5xl md:text-6xl tracking-tight leading-[1.02]">
                One price.<br /><span className="italic">Cancel anytime.</span>
              </h2>
              <p className="mt-6 text-cream2 text-[15px] leading-relaxed">A single referral bonus from one new job pays for ~5 years of JobCrawler.</p>
            </div>

            <div className="grid md:grid-cols-2 gap-5">
              {/* Free */}
              <div className="border border-line2 rounded-2xl p-7 bg-ink2/40">
                <div className="font-mono text-[11px] text-mute uppercase tracking-widest">Trial</div>
                <div className="mt-4 flex items-baseline gap-2">
                  <span className="font-serif text-6xl">₹0</span>
                  <span className="text-cream2 text-[13px]">/ 7 days</span>
                </div>
                <p className="mt-3 text-cream2 text-[13.5px]">Try it on a real job hunt. No card.</p>
                <ul className="mt-6 space-y-2.5 text-[13.5px] text-cream2">
                  <li className="flex gap-2"><span className="text-green">✓</span> Up to 50 applications</li>
                  <li className="flex gap-2"><span className="text-green">✓</span> All filters &amp; scoring</li>
                  <li className="flex gap-2"><span className="text-green">✓</span> Review-mode &amp; autopilot</li>
                  <li className="flex gap-2"><span className="text-mute">○</span> Email support only</li>
                </ul>
                <Link to="/register" className="mt-7 inline-flex w-full items-center justify-center h-11 rounded-md border border-line2 text-[14px] font-medium hover:bg-ink2">
                  Start free
                </Link>
              </div>

              {/* Pro */}
              <div className="relative border border-line2 rounded-2xl p-7 overflow-hidden" style={{ background: 'linear-gradient(to bottom, #15110A, #0B0B0F)' }}>
                <div className="absolute -top-px right-7 px-2.5 py-1 rounded-b-md bg-amber text-ink font-mono text-[10px] uppercase tracking-widest">Recommended</div>
                <div className="font-mono text-[11px] text-amber uppercase tracking-widest">Pro</div>
                <div className="mt-4 flex items-baseline gap-2">
                  <span className="font-serif text-6xl">₹499</span>
                  <span className="text-cream2 text-[13px]">/ month</span>
                </div>
                <p className="mt-3 text-cream2 text-[13.5px]">Everything. Until you sign your offer letter.</p>
                <ul className="mt-6 space-y-2.5 text-[13.5px]">
                  <li className="flex gap-2"><span className="text-amber">✓</span> Unlimited applications</li>
                  <li className="flex gap-2"><span className="text-amber">✓</span> LLM scoring on every JD</li>
                  <li className="flex gap-2"><span className="text-amber">✓</span> Custom screening Q&amp;A answers</li>
                  <li className="flex gap-2"><span className="text-amber">✓</span> Multi-resume routing by role</li>
                  <li className="flex gap-2"><span className="text-amber">✓</span> Daily summary email</li>
                  <li className="flex gap-2"><span className="text-amber">✓</span> Priority support · WhatsApp</li>
                </ul>
                <Link to="/register" className="mt-7 inline-flex w-full items-center justify-center h-11 rounded-md bg-amber text-ink font-semibold text-[14px] hover:bg-amber2">
                  Start 7-day trial →
                </Link>
                <p className="mt-3 text-center font-mono text-[11px] text-mute">UPI · Card · Net banking</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="border-t border-line py-28">
        <div className="max-w-[1240px] mx-auto px-6 grid md:grid-cols-[1fr_2fr] gap-14">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-widest text-amber">/05 · faq</div>
            <h2 className="mt-3 font-serif text-5xl md:text-6xl tracking-tight leading-[1.02]">
              Real questions.<br />Honest answers.
            </h2>
          </div>
          <div className="border-t border-line">
            {FAQS.map((faq, i) => (
              <details key={i} className="border-b border-line group">
                <summary className="flex items-center justify-between gap-6 py-6">
                  <span className="font-serif text-2xl">{faq.q}</span>
                  <span className="chev font-mono text-2xl text-cream2">+</span>
                </summary>
                <div className="pb-6 text-cream2 text-[14.5px] leading-relaxed max-w-[60ch]">{faq.a}</div>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="border-t border-line relative overflow-hidden">
        <div className="absolute inset-0 grid-bg opacity-30" />
        <div className="absolute inset-0" style={{ background: 'radial-gradient(50% 80% at 50% 100%, rgba(255,138,31,0.18), transparent 60%)' }} />
        <div className="relative max-w-[1240px] mx-auto px-6 py-28 text-center">
          <div className="font-mono text-[11px] uppercase tracking-widest text-amber">/06 · get started</div>
          <h2 className="mt-4 font-serif text-6xl md:text-[88px] leading-[0.95] tracking-tight max-w-[16ch] mx-auto">
            Stop applying. <span className="italic text-amber">Start interviewing.</span>
          </h2>
          <p className="mt-7 max-w-xl mx-auto text-cream2 text-[16px] leading-relaxed">
            Set up your profile. Hit Crawl. Wake up to a calendar that fills itself.
          </p>
          <div className="mt-9 inline-flex flex-col items-center gap-3">
            <Link to="/register" className="inline-flex items-center gap-2.5 h-14 px-7 rounded-md bg-amber text-ink text-[16px] font-semibold hover:bg-amber2 transition">
              Get started — start free
              <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </Link>
            <p className="font-mono text-xs text-mute">7 days free · ₹499/mo after · cancel from settings</p>
          </div>
          <div className="mt-12 inline-flex items-center gap-3 border border-line2 rounded-full px-4 py-2 font-mono text-[11px] text-cream2">
            <span className="w-1.5 h-1.5 rounded-full bg-green blink" />
            <span>API operational</span>
            <span className="text-mute">·</span>
            <span>p50 score latency 412ms</span>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-line">
        <div className="max-w-[1240px] mx-auto px-6 py-14 grid md:grid-cols-5 gap-10">
          <div className="md:col-span-2">
            <div className="flex items-center gap-2.5">
              <span className="relative w-7 h-7 inline-flex items-center justify-center">
                <span className="absolute inset-0 rounded-md border border-line2" />
                <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.7">
                  <circle cx="12" cy="12" r="3.2" className="text-amber" stroke="currentColor" />
                  <path d="M12 8.8V4M12 15.2V20M8.8 12H4M15.2 12H20M9.7 9.7L6.3 6.3M14.3 9.7L17.7 6.3M9.7 14.3L6.3 17.7M14.3 14.3L17.7 17.7" className="text-cream" />
                </svg>
              </span>
              <span className="font-semibold tracking-tight">JobCrawler</span>
            </div>
            <p className="mt-4 max-w-sm text-cream2 text-[13.5px] leading-relaxed">
              Built in Bengaluru, for the people who once sat pasting the same cover letter into the 40th portal of the day.
            </p>
            <div className="mt-5 font-mono text-[11px] text-mute">© 2026 Crawler Labs Pvt. Ltd. · Bengaluru, India</div>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-mute mb-3">Product</div>
            <ul className="space-y-2 text-[13.5px] text-cream2">
              <li><a href="#how" className="hover:text-cream">How it works</a></li>
              <li><a href="#pricing" className="hover:text-cream">Pricing</a></li>
              <li><Link to="/login" className="hover:text-cream">Sign in</Link></li>
            </ul>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-mute mb-3">Trust</div>
            <ul className="space-y-2 text-[13.5px] text-cream2">
              <li><a href="#" className="hover:text-cream">Security</a></li>
              <li><a href="#" className="hover:text-cream">Privacy</a></li>
              <li><a href="#" className="hover:text-cream">Open source</a></li>
            </ul>
          </div>
          <div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-mute mb-3">Contact</div>
            <ul className="space-y-2 text-[13.5px] text-cream2">
              <li><a href="mailto:hello@jobcrawler.app" className="hover:text-cream">hello@jobcrawler.app</a></li>
              <li><a href="#" className="hover:text-cream">WhatsApp support</a></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-line">
          <div className="max-w-[1240px] mx-auto px-6 py-5 flex flex-wrap items-center justify-between gap-3 font-mono text-[11px] text-mute">
            <div>not affiliated with linkedin corporation. linkedin is a registered trademark of linkedin corporation.</div>
            <div className="flex items-center gap-4">
              <span>DPDP-aligned</span>
              <span>·</span>
              <span>v1.4.2</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
