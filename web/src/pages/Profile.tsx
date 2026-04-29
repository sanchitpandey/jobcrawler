import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'

// ── API shapes ─────────────────────────────────────────────────────────────────

interface ProfileApiShape {
  name: string | null
  phone: string | null
  linkedin_url: string | null
  github_url: string | null
  portfolio_url: string | null
  location_current: string | null
  total_experience: string | null
  work_authorization: string | null
  willing_to_relocate: string | null
  sponsorship_required: string | null
  notice_period: string | null
  degree: string | null
  college: string | null
  graduation_year: string | null
  cgpa: string | null
  current_ctc: string | null
  expected_ctc: string | null
  expected_ctc_min_lpa: string | null
  min_comp_lpa: number
  skills: Record<string, string>
  short_answers: Record<string, string>
  candidate_summary: string | null
  experience_highlights: string | null
  preferred_roles: string | null
  target_locations: string | null
  avoid_companies: string | null
  avoid_roles: string | null
}

interface SearchPrefShape {
  keywords: string[] | null
  location: string
  experience_levels: string
  remote_filter: string
  time_range: string
  auto_apply_threshold: number
  max_daily_applications: number
  skip_companies: string[] | null
  skip_title_keywords: string[] | null
}

interface CompletenessData {
  percent: number
  missing: string[]
}

// ── Form state ─────────────────────────────────────────────────────────────────

interface FormState {
  name: string
  phone: string
  linkedin_url: string
  github_url: string
  portfolio_url: string
  location_current: string
  total_experience: string
  current_title: string
  current_company: string
  work_authorization: string
  willing_to_relocate: string
  sponsorship_required: string
  notice_period: string
  degree: string
  college: string
  graduation_year: string
  cgpa: string
  current_ctc: string
  expected_ctc: string
  expected_ctc_min_lpa: string
  min_comp_lpa: number
  skills_text: string
  candidate_summary: string
  experience_highlights: string
  preferred_roles: string
  target_locations: string
  remote_filter: string
  experience_levels: string[]
  avoid_companies: string
  avoid_roles: string
  auto_apply_threshold: number
  max_daily_applications: number
}

const EMPTY: FormState = {
  name: '',
  phone: '',
  linkedin_url: '',
  github_url: '',
  portfolio_url: '',
  location_current: '',
  total_experience: '',
  current_title: '',
  current_company: '',
  work_authorization: '',
  willing_to_relocate: 'no',
  sponsorship_required: 'no',
  notice_period: '',
  degree: '',
  college: '',
  graduation_year: '',
  cgpa: '',
  current_ctc: '',
  expected_ctc: '',
  expected_ctc_min_lpa: '',
  min_comp_lpa: 0,
  skills_text: '',
  candidate_summary: '',
  experience_highlights: '',
  preferred_roles: '',
  target_locations: '',
  remote_filter: '',
  experience_levels: [],
  avoid_companies: '',
  avoid_roles: '',
  auto_apply_threshold: 75,
  max_daily_applications: 15,
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function skillsToText(s: Record<string, string>): string {
  return Object.keys(s).join(', ')
}

function textToSkills(text: string): Record<string, string> {
  const result: Record<string, string> = {}
  text.split(',').map((s) => s.trim()).filter(Boolean).forEach((s) => { result[s] = '' })
  return result
}

function csvToArray(text: string): string[] {
  return text.split(',').map((s) => s.trim()).filter(Boolean)
}

// ── Shared UI ──────────────────────────────────────────────────────────────────

function Label({ children }: { children: string }) {
  return (
    <label className="font-mono text-[11px] uppercase tracking-wider text-cream2">
      {children}
    </label>
  )
}

interface InputProps {
  type?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  readOnly?: boolean
}

function Input({ type = 'text', value, onChange, placeholder, readOnly }: InputProps) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      readOnly={readOnly}
      className={`w-full h-11 px-3 rounded-lg border bg-ink text-cream text-sm placeholder:text-mute focus:outline-none focus:border-amber transition ${
        readOnly ? 'opacity-50 cursor-not-allowed' : 'border-line2'
      }`}
    />
  )
}

function Toggle({
  value,
  onChange,
  labels = ['Yes', 'No'],
  values = ['yes', 'no'],
}: {
  value: string
  onChange: (v: string) => void
  labels?: [string, string]
  values?: [string, string]
}) {
  return (
    <div className="flex gap-2">
      {values.map((v, i) => (
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={`h-9 px-4 rounded-lg border text-sm font-medium transition ${
            value === v
              ? 'bg-amber border-amber text-ink'
              : 'border-line2 text-cream2 hover:border-cream2 hover:text-cream'
          }`}
        >
          {labels[i]}
        </button>
      ))}
    </div>
  )
}

function Select({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full h-11 px-3 rounded-lg border border-line2 bg-ink text-cream text-sm focus:outline-none focus:border-amber transition appearance-none"
    >
      {placeholder && <option value="" disabled>{placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value} className="bg-ink">{o.label}</option>
      ))}
    </select>
  )
}

function Textarea({
  value,
  onChange,
  placeholder,
  rows = 4,
  maxLength,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  rows?: number
  maxLength?: number
}) {
  return (
    <div className="relative">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        maxLength={maxLength}
        className="w-full px-3 py-2.5 rounded-lg border border-line2 bg-ink text-cream text-sm placeholder:text-mute focus:outline-none focus:border-amber transition resize-none"
      />
      {maxLength && (
        <span className="absolute bottom-2 right-3 font-mono text-[10px] text-mute">
          {value.length}/{maxLength}
        </span>
      )}
    </div>
  )
}

// ── Accordion ─────────────────────────────────────────────────────────────────

function Accordion({
  id,
  title,
  open,
  onToggle,
  children,
}: {
  id: string
  title: string
  open: boolean
  onToggle: (id: string) => void
  children: React.ReactNode
}) {
  return (
    <div className="border border-line2 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => onToggle(id)}
        className="w-full px-5 py-3.5 flex items-center justify-between bg-ink2/40 hover:bg-ink2/60 transition text-left"
      >
        <span className="font-mono text-[11px] uppercase tracking-wider text-cream2">{title}</span>
        <svg
          viewBox="0 0 24 24"
          className={`w-4 h-4 text-mute transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && <div className="px-5 py-5 space-y-4">{children}</div>}
    </div>
  )
}

// ── Experience level options ───────────────────────────────────────────────────

const EXP_LEVEL_OPTIONS = [
  { value: '1', label: 'Internship' },
  { value: '2', label: 'Entry Level' },
  { value: '3', label: 'Associate' },
  { value: '4', label: 'Mid-Senior' },
  { value: '5', label: 'Director' },
]

// ── Main component ─────────────────────────────────────────────────────────────

const ALL_SECTIONS = [
  'personal',
  'experience',
  'education',
  'compensation',
  'skills',
  'preferences',
  'blacklists',
  'autoapply',
]

export function Profile() {
  const { user } = useAuth()
  const [form, setForm] = useState<FormState>(EMPTY)
  const [prefState, setPrefState] = useState<SearchPrefShape | null>(null)
  const [completeness, setCompleteness] = useState<CompletenessData | null>(null)
  const [open, setOpen] = useState<Set<string>>(new Set(ALL_SECTIONS))
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState('')

  useEffect(() => {
    async function load() {
      try {
        const profile = await api.get<ProfileApiShape>('/profile')
        setForm((f) => ({
          ...f,
          name: profile.name ?? f.name,
          phone: profile.phone ?? f.phone,
          linkedin_url: profile.linkedin_url ?? f.linkedin_url,
          github_url: profile.github_url ?? f.github_url,
          portfolio_url: profile.portfolio_url ?? f.portfolio_url,
          location_current: profile.location_current ?? f.location_current,
          total_experience: profile.total_experience ?? f.total_experience,
          current_title: profile.short_answers?.current_title ?? f.current_title,
          current_company: profile.short_answers?.current_company ?? f.current_company,
          work_authorization: profile.work_authorization ?? f.work_authorization,
          willing_to_relocate: profile.willing_to_relocate ?? f.willing_to_relocate,
          sponsorship_required: profile.sponsorship_required ?? f.sponsorship_required,
          notice_period: profile.notice_period ?? f.notice_period,
          degree: profile.degree ?? f.degree,
          college: profile.college ?? f.college,
          graduation_year: profile.graduation_year ?? f.graduation_year,
          cgpa: profile.cgpa ?? f.cgpa,
          current_ctc: profile.current_ctc ?? f.current_ctc,
          expected_ctc: profile.expected_ctc ?? f.expected_ctc,
          expected_ctc_min_lpa: profile.expected_ctc_min_lpa ?? f.expected_ctc_min_lpa,
          min_comp_lpa: profile.min_comp_lpa ?? f.min_comp_lpa,
          skills_text: profile.skills ? skillsToText(profile.skills) : f.skills_text,
          candidate_summary: profile.candidate_summary ?? f.candidate_summary,
          experience_highlights: profile.experience_highlights ?? f.experience_highlights,
          preferred_roles: profile.preferred_roles ?? f.preferred_roles,
          target_locations: profile.target_locations ?? f.target_locations,
          avoid_companies: profile.avoid_companies ?? f.avoid_companies,
          avoid_roles: profile.avoid_roles ?? f.avoid_roles,
        }))
      } catch { /* new user */ }

      try {
        const pref = await api.get<SearchPrefShape>('/discovery/preferences')
        setPrefState(pref)
        setForm((f) => ({
          ...f,
          remote_filter: pref.remote_filter || f.remote_filter,
          experience_levels: pref.experience_levels
            ? pref.experience_levels.split(',').filter(Boolean)
            : f.experience_levels,
          auto_apply_threshold: pref.auto_apply_threshold ?? f.auto_apply_threshold,
          max_daily_applications: pref.max_daily_applications ?? f.max_daily_applications,
          preferred_roles: pref.keywords?.join(', ') || f.preferred_roles,
          avoid_companies: pref.skip_companies?.join(', ') || f.avoid_companies,
          avoid_roles: pref.skip_title_keywords?.join(', ') || f.avoid_roles,
          target_locations: pref.location || f.target_locations,
        }))
      } catch { /* no prefs yet */ }

      try {
        const c = await api.get<CompletenessData>('/profile/completeness')
        setCompleteness(c)
      } catch { /* endpoint may not exist */ }

      setLoaded(true)
    }
    load()
  }, [])

  function set(k: keyof FormState, v: FormState[keyof FormState]) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  function toggleSection(id: string) {
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleSave() {
    setSaving(true)
    setSaveError('')
    setSaved(false)
    try {
      const keywords = csvToArray(form.preferred_roles)
      const skip_companies = csvToArray(form.avoid_companies)
      const skip_title_keywords = csvToArray(form.avoid_roles)

      await Promise.all([
        api.patch('/profile', {
          name: form.name || null,
          phone: form.phone || null,
          linkedin_url: form.linkedin_url || null,
          github_url: form.github_url || null,
          portfolio_url: form.portfolio_url || null,
          location_current: form.location_current || null,
          total_experience: form.total_experience || null,
          work_authorization: form.work_authorization || null,
          willing_to_relocate: form.willing_to_relocate,
          sponsorship_required: form.sponsorship_required,
          notice_period: form.notice_period || null,
          short_answers: {
            current_title: form.current_title,
            current_company: form.current_company,
          },
          degree: form.degree || null,
          college: form.college || null,
          graduation_year: form.graduation_year || null,
          cgpa: form.cgpa || null,
          current_ctc: form.current_ctc || null,
          expected_ctc: form.expected_ctc || null,
          expected_ctc_min_lpa: form.expected_ctc_min_lpa || null,
          min_comp_lpa: form.min_comp_lpa || 0,
          skills: textToSkills(form.skills_text),
          candidate_summary: form.candidate_summary || null,
          experience_highlights: form.experience_highlights || null,
          preferred_roles: form.preferred_roles || null,
          target_locations: form.target_locations || null,
          avoid_companies: form.avoid_companies || null,
          avoid_roles: form.avoid_roles || null,
        }),
        api.post('/discovery/preferences', {
          keywords: keywords.length ? keywords : null,
          location: form.target_locations,
          experience_levels: form.experience_levels.join(','),
          remote_filter: form.remote_filter,
          time_range: prefState?.time_range ?? 'r86400',
          auto_apply_threshold: form.auto_apply_threshold,
          max_daily_applications: form.max_daily_applications,
          skip_companies: skip_companies.length ? skip_companies : null,
          skip_title_keywords: skip_title_keywords.length ? skip_title_keywords : null,
        }),
      ])

      // Refresh completeness
      try {
        const c = await api.get<CompletenessData>('/profile/completeness')
        setCompleteness(c)
      } catch { /* ignore */ }

      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (!loaded) {
    return (
      <div className="p-8 flex items-center justify-center py-32">
        <span className="font-mono text-sm text-mute animate-pulse">Loading profile…</span>
      </div>
    )
  }

  return (
    <div className="p-8 max-w-3xl">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="font-serif text-[2rem] text-cream">Profile</h1>
          <p className="text-cream2 text-sm mt-1">
            All your details in one place. Saved on click.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {saved && (
            <span className="font-mono text-xs text-green flex items-center gap-1.5">
              <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M20 6L9 17l-5-5" />
              </svg>
              Saved!
            </span>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="h-9 px-5 rounded-lg bg-amber text-ink text-sm font-semibold hover:bg-amber2 disabled:opacity-50 transition"
          >
            {saving ? 'Saving…' : 'Save Profile'}
          </button>
        </div>
      </div>

      {saveError && (
        <div className="mb-5 border border-red-soft/30 bg-red-soft/10 rounded-lg px-4 py-3 font-mono text-xs text-red-soft">
          {saveError}
        </div>
      )}

      {/* Completeness bar */}
      {completeness && (
        <div className="mb-6 border border-line2 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[11px] uppercase tracking-wider text-cream2">
              Profile Completeness
            </span>
            <span className="font-mono text-sm text-amber">{completeness.percent}%</span>
          </div>
          <div className="h-2 bg-line2 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                completeness.percent >= 80 ? 'bg-green' : 'bg-amber'
              }`}
              style={{ width: `${completeness.percent}%` }}
            />
          </div>
          {completeness.missing.length > 0 && (
            <p className="text-xs text-cream2">
              Your profile is <span className="text-amber">{completeness.percent}%</span> complete.
              {' '}Fill in{' '}
              <span className="text-cream">{completeness.missing.slice(0, 3).join(', ')}</span>
              {completeness.missing.length > 3 ? ` and ${completeness.missing.length - 3} more` : ''}
              {' '}to improve match quality.
            </p>
          )}
        </div>
      )}

      {/* Sections */}
      <div className="space-y-3">
        {/* Personal Information */}
        <Accordion id="personal" title="Personal Information" open={open.has('personal')} onToggle={toggleSection}>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Full Name</Label>
              <Input value={form.name} onChange={(v) => set('name', v)} placeholder="Sanchit Pandey" />
            </div>
            <div className="space-y-1.5">
              <Label>Email</Label>
              <Input value={user?.email ?? ''} onChange={() => {}} readOnly />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Phone</Label>
              <Input type="tel" value={form.phone} onChange={(v) => set('phone', v)} placeholder="+91 98765 43210" />
            </div>
            <div className="space-y-1.5">
              <Label>Current City</Label>
              <Input value={form.location_current} onChange={(v) => set('location_current', v)} placeholder="Bengaluru, India" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>LinkedIn URL</Label>
            <Input type="url" value={form.linkedin_url} onChange={(v) => set('linkedin_url', v)} placeholder="https://linkedin.com/in/yourname" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>GitHub URL</Label>
              <Input type="url" value={form.github_url} onChange={(v) => set('github_url', v)} placeholder="https://github.com/yourname" />
            </div>
            <div className="space-y-1.5">
              <Label>Portfolio URL</Label>
              <Input type="url" value={form.portfolio_url} onChange={(v) => set('portfolio_url', v)} placeholder="https://yoursite.dev" />
            </div>
          </div>
        </Accordion>

        {/* Experience */}
        <Accordion id="experience" title="Experience" open={open.has('experience')} onToggle={toggleSection}>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Years of Experience</Label>
              <Input value={form.total_experience} onChange={(v) => set('total_experience', v)} placeholder="3 years" />
            </div>
            <div className="space-y-1.5">
              <Label>Notice Period</Label>
              <Input value={form.notice_period} onChange={(v) => set('notice_period', v)} placeholder="immediate / 30 days" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Current Job Title</Label>
              <Input value={form.current_title} onChange={(v) => set('current_title', v)} placeholder="ML Engineer" />
            </div>
            <div className="space-y-1.5">
              <Label>Current Company</Label>
              <Input value={form.current_company} onChange={(v) => set('current_company', v)} placeholder="Acme Corp" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Work Authorization</Label>
            <Select
              value={form.work_authorization}
              onChange={(v) => set('work_authorization', v)}
              placeholder="Select authorization status"
              options={[
                { value: 'Citizen', label: 'Citizen' },
                { value: 'PR', label: 'Permanent Resident (PR)' },
                { value: 'H1B', label: 'H1B' },
                { value: 'OPT', label: 'OPT / F-1' },
                { value: 'Need Sponsorship', label: 'Need Sponsorship' },
              ]}
            />
          </div>
          <div className="grid grid-cols-2 gap-6">
            <div className="space-y-2">
              <Label>Willing to Relocate</Label>
              <Toggle value={form.willing_to_relocate} onChange={(v) => set('willing_to_relocate', v)} />
            </div>
            <div className="space-y-2">
              <Label>Sponsorship Required</Label>
              <Toggle value={form.sponsorship_required} onChange={(v) => set('sponsorship_required', v)} />
            </div>
          </div>
        </Accordion>

        {/* Education */}
        <Accordion id="education" title="Education" open={open.has('education')} onToggle={toggleSection}>
          <div className="space-y-1.5">
            <Label>Degree</Label>
            <Input value={form.degree} onChange={(v) => set('degree', v)} placeholder="B.E. Computer Science" />
          </div>
          <div className="space-y-1.5">
            <Label>College / University</Label>
            <Input value={form.college} onChange={(v) => set('college', v)} placeholder="BITS Pilani" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Graduation Year</Label>
              <Input value={form.graduation_year} onChange={(v) => set('graduation_year', v)} placeholder="2025" />
            </div>
            <div className="space-y-1.5">
              <Label>GPA / CGPA</Label>
              <Input value={form.cgpa} onChange={(v) => set('cgpa', v)} placeholder="8.5 / 10" />
            </div>
          </div>
        </Accordion>

        {/* Compensation */}
        <Accordion id="compensation" title="Compensation" open={open.has('compensation')} onToggle={toggleSection}>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Current CTC / Salary</Label>
              <Input value={form.current_ctc} onChange={(v) => set('current_ctc', v)} placeholder="18 LPA" />
            </div>
            <div className="space-y-1.5">
              <Label>Expected CTC / Salary</Label>
              <Input value={form.expected_ctc} onChange={(v) => set('expected_ctc', v)} placeholder="25 LPA" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Minimum Acceptable (LPA)</Label>
              <Input
                type="number"
                value={String(form.min_comp_lpa || '')}
                onChange={(v) => set('min_comp_lpa', Number(v) || 0)}
                placeholder="15"
              />
              <p className="font-mono text-[10px] text-mute">Jobs below this are auto-rejected</p>
            </div>
            <div className="space-y-1.5">
              <Label>Expected Min (text)</Label>
              <Input
                value={form.expected_ctc_min_lpa}
                onChange={(v) => set('expected_ctc_min_lpa', v)}
                placeholder="20 LPA or ₹2,00,000/month"
              />
            </div>
          </div>
        </Accordion>

        {/* Skills & Summary */}
        <Accordion id="skills" title="Skills & Summary" open={open.has('skills')} onToggle={toggleSection}>
          <div className="space-y-1.5">
            <Label>Technical Skills</Label>
            <Input
              value={form.skills_text}
              onChange={(v) => set('skills_text', v)}
              placeholder="python, pytorch, sql, react, docker, llm"
            />
            <p className="font-mono text-[10px] text-mute">Comma-separated. Used to fill skills checkboxes on job forms.</p>
          </div>
          <div className="space-y-1.5">
            <Label>Candidate Summary</Label>
            <Textarea
              value={form.candidate_summary}
              onChange={(v) => set('candidate_summary', v)}
              placeholder="3+ years building ML systems at scale. Specialised in LLM fine-tuning, RAG pipelines, and production inference."
              rows={5}
              maxLength={1500}
            />
            <p className="font-mono text-[10px] text-mute">Used to answer "tell us about yourself" questions.</p>
          </div>
          <div className="space-y-1.5">
            <Label>Experience Highlights</Label>
            <Textarea
              value={form.experience_highlights}
              onChange={(v) => set('experience_highlights', v)}
              placeholder="Led re-ranking model that improved CTR by 18%. Built RAG pipeline serving 2M daily queries."
              rows={4}
              maxLength={2000}
            />
          </div>
        </Accordion>

        {/* Job Preferences */}
        <Accordion id="preferences" title="Job Preferences" open={open.has('preferences')} onToggle={toggleSection}>
          <div className="space-y-1.5">
            <Label>Target Job Titles / Keywords</Label>
            <Input
              value={form.preferred_roles}
              onChange={(v) => set('preferred_roles', v)}
              placeholder="ML Engineer, AI Engineer, Backend Engineer"
            />
            <p className="font-mono text-[10px] text-mute">Comma-separated. Used as LinkedIn search keywords.</p>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Target Locations</Label>
              <Input value={form.target_locations} onChange={(v) => set('target_locations', v)} placeholder="Bengaluru, Remote" />
            </div>
            <div className="space-y-1.5">
              <Label>Remote Preference</Label>
              <Select
                value={form.remote_filter}
                onChange={(v) => set('remote_filter', v)}
                placeholder="Any"
                options={[
                  { value: '', label: 'Any' },
                  { value: '2', label: 'Remote Only' },
                  { value: '3', label: 'Hybrid' },
                  { value: '1', label: 'On-site' },
                ]}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Experience Levels</Label>
            <div className="flex flex-wrap gap-2">
              {EXP_LEVEL_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => {
                    const current = form.experience_levels
                    const next = current.includes(opt.value)
                      ? current.filter((v) => v !== opt.value)
                      : [...current, opt.value]
                    set('experience_levels', next)
                  }}
                  className={`h-8 px-3 rounded-lg border text-xs font-medium transition ${
                    form.experience_levels.includes(opt.value)
                      ? 'bg-amber/20 border-amber text-amber'
                      : 'border-line2 text-cream2 hover:border-cream2'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </Accordion>

        {/* Blacklists */}
        <Accordion id="blacklists" title="Blacklists" open={open.has('blacklists')} onToggle={toggleSection}>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Companies to Avoid</Label>
              <Input
                value={form.avoid_companies}
                onChange={(v) => set('avoid_companies', v)}
                placeholder="TCS, Infosys, Wipro"
              />
              <p className="font-mono text-[10px] text-mute">Jobs at these companies are auto-skipped.</p>
            </div>
            <div className="space-y-1.5">
              <Label>Title Keywords to Skip</Label>
              <Input
                value={form.avoid_roles}
                onChange={(v) => set('avoid_roles', v)}
                placeholder="intern, staff, principal, manager"
              />
              <p className="font-mono text-[10px] text-mute">Jobs with these title words are auto-skipped.</p>
            </div>
          </div>
        </Accordion>

        {/* Auto-Apply Settings */}
        <Accordion id="autoapply" title="Auto-Apply Settings" open={open.has('autoapply')} onToggle={toggleSection}>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Score Threshold</Label>
              <span className="font-mono text-sm text-amber">{form.auto_apply_threshold}</span>
            </div>
            <input
              type="range"
              min={50}
              max={95}
              step={5}
              value={form.auto_apply_threshold}
              onChange={(e) => set('auto_apply_threshold', Number(e.target.value))}
              className="w-full accent-amber"
            />
            <div className="flex justify-between font-mono text-[10px] text-mute">
              <span>50 — apply more</span>
              <span>95 — apply less</span>
            </div>
            <p className="font-mono text-[10px] text-mute">
              Jobs scoring ≥ {form.auto_apply_threshold} are auto-approved.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>Max Daily Applications</Label>
            <input
              type="number"
              min={1}
              max={30}
              value={form.max_daily_applications}
              onChange={(e) => set('max_daily_applications', Math.min(30, Math.max(1, Number(e.target.value) || 15)))}
              className="w-32 h-9 px-3 rounded-lg border border-line2 bg-ink text-cream text-sm focus:outline-none focus:border-amber transition"
            />
            <p className="font-mono text-[10px] text-mute">Maximum 30 per day enforced by the extension.</p>
          </div>
        </Accordion>
      </div>

      {/* Bottom save */}
      <div className="mt-6 flex items-center gap-4">
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="h-10 px-6 rounded-lg bg-amber text-ink font-semibold text-sm hover:bg-amber2 disabled:opacity-50 transition"
        >
          {saving ? 'Saving…' : 'Save Profile'}
        </button>
        {saved && (
          <span className="font-mono text-xs text-green flex items-center gap-1.5">
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M20 6L9 17l-5-5" />
            </svg>
            Saved!
          </span>
        )}
        {saveError && (
          <span className="font-mono text-xs text-red-soft">{saveError}</span>
        )}
      </div>
    </div>
  )
}
