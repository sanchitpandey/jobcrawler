import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'

// API uses `skills`, `eeo`, `short_answers` (not _json suffixes)
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
  auto_apply_threshold: number
  max_daily_applications: number
  skip_companies: string[] | null
  skip_title_keywords: string[] | null
}

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

const TOTAL_STEPS = 7

const STEP_LABELS = [
  'About You',
  'Experience',
  'Education',
  'Compensation',
  'Skills & Summary',
  'Preferences',
  'Resume',
]

const STEP_DESCS = [
  'Your personal contact details and online presence.',
  'Your work history, authorization status, and availability.',
  'Your academic background.',
  'Current and expected salary information.',
  'Your technical skills and professional summary for AI form filling.',
  'What jobs to find, where, and how aggressively to apply.',
  'Upload your resume so forms can be filled accurately.',
]

function skillsToText(skills: Record<string, string>): string {
  return Object.keys(skills).join(', ')
}

function textToSkills(text: string): Record<string, string> {
  const result: Record<string, string> = {}
  text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
    .forEach((s) => {
      result[s] = ''
    })
  return result
}

function csvToArray(text: string): string[] {
  return text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

// ── Shared UI primitives ───────────────────────────────────────────────────────

function Label({ children }: { children: string }) {
  return (
    <label className="font-mono text-[11px] uppercase tracking-wider text-cream2">
      {children}
    </label>
  )
}

function FieldError({ msg }: { msg?: string }) {
  if (!msg) return null
  return <p className="font-mono text-[10px] text-red-soft mt-0.5">{msg}</p>
}

interface InputProps {
  type?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  hasError?: boolean
  readOnly?: boolean
}

function Input({ type = 'text', value, onChange, placeholder, hasError, readOnly }: InputProps) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      readOnly={readOnly}
      className={`w-full h-11 px-3 rounded-lg border bg-ink text-cream text-sm placeholder:text-mute focus:outline-none focus:border-amber transition ${
        readOnly ? 'opacity-50 cursor-not-allowed' : ''
      } ${hasError ? 'border-red-soft' : 'border-line2'}`}
    />
  )
}

interface ToggleProps {
  value: string
  onChange: (v: string) => void
  labels?: [string, string]
  values?: [string, string]
}

function Toggle({
  value,
  onChange,
  labels = ['Yes', 'No'],
  values = ['yes', 'no'],
}: ToggleProps) {
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

interface SelectProps {
  value: string
  onChange: (v: string) => void
  options: { value: string; label: string }[]
  placeholder?: string
}

function Select({ value, onChange, options, placeholder }: SelectProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full h-11 px-3 rounded-lg border border-line2 bg-ink text-cream text-sm focus:outline-none focus:border-amber transition appearance-none"
    >
      {placeholder && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {options.map((o) => (
        <option key={o.value} value={o.value} className="bg-ink">
          {o.label}
        </option>
      ))}
    </select>
  )
}

interface TextareaProps {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  rows?: number
  maxLength?: number
}

function Textarea({ value, onChange, placeholder, rows = 5, maxLength }: TextareaProps) {
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

// ── Step content ───────────────────────────────────────────────────────────────

interface StepProps {
  form: FormState
  set: (k: keyof FormState, v: FormState[keyof FormState]) => void
  errors: Partial<Record<keyof FormState, string>>
  userEmail: string
}

function Step1({ form, set, errors, userEmail }: StepProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Full Name *</Label>
          <Input
            value={form.name}
            onChange={(v) => set('name', v)}
            placeholder="Sanchit Pandey"
            hasError={!!errors.name}
          />
          <FieldError msg={errors.name} />
        </div>
        <div className="space-y-1.5">
          <Label>Email</Label>
          <Input value={userEmail} onChange={() => {}} readOnly />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Phone</Label>
          <Input
            type="tel"
            value={form.phone}
            onChange={(v) => set('phone', v)}
            placeholder="+91 98765 43210"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Current City</Label>
          <Input
            value={form.location_current}
            onChange={(v) => set('location_current', v)}
            placeholder="Bengaluru, India"
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label>LinkedIn URL</Label>
        <Input
          type="url"
          value={form.linkedin_url}
          onChange={(v) => set('linkedin_url', v)}
          placeholder="https://linkedin.com/in/yourname"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>GitHub URL</Label>
          <Input
            type="url"
            value={form.github_url}
            onChange={(v) => set('github_url', v)}
            placeholder="https://github.com/yourname"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Portfolio URL</Label>
          <Input
            type="url"
            value={form.portfolio_url}
            onChange={(v) => set('portfolio_url', v)}
            placeholder="https://yoursite.dev"
          />
        </div>
      </div>
    </div>
  )
}

function Step2({ form, set, errors: _errors }: StepProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Years of Experience</Label>
          <Input
            value={form.total_experience}
            onChange={(v) => set('total_experience', v)}
            placeholder="3 years"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Notice Period</Label>
          <Input
            value={form.notice_period}
            onChange={(v) => set('notice_period', v)}
            placeholder="immediate / 30 days"
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Current Job Title</Label>
          <Input
            value={form.current_title}
            onChange={(v) => set('current_title', v)}
            placeholder="ML Engineer"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Current Company</Label>
          <Input
            value={form.current_company}
            onChange={(v) => set('current_company', v)}
            placeholder="Acme Corp"
          />
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
          <Toggle
            value={form.willing_to_relocate}
            onChange={(v) => set('willing_to_relocate', v)}
          />
        </div>
        <div className="space-y-2">
          <Label>Sponsorship Required</Label>
          <Toggle
            value={form.sponsorship_required}
            onChange={(v) => set('sponsorship_required', v)}
          />
        </div>
      </div>
    </div>
  )
}

function Step3({ form, set, errors: _errors }: StepProps) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Degree</Label>
        <Input
          value={form.degree}
          onChange={(v) => set('degree', v)}
          placeholder="B.E. Computer Science"
        />
      </div>
      <div className="space-y-1.5">
        <Label>College / University</Label>
        <Input
          value={form.college}
          onChange={(v) => set('college', v)}
          placeholder="BITS Pilani"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Graduation Year</Label>
          <Input
            value={form.graduation_year}
            onChange={(v) => set('graduation_year', v)}
            placeholder="2025"
          />
        </div>
        <div className="space-y-1.5">
          <Label>GPA / CGPA</Label>
          <Input
            value={form.cgpa}
            onChange={(v) => set('cgpa', v)}
            placeholder="8.5 / 10"
          />
        </div>
      </div>
    </div>
  )
}

function Step4({ form, set, errors: _errors }: StepProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Current CTC / Salary</Label>
          <Input
            value={form.current_ctc}
            onChange={(v) => set('current_ctc', v)}
            placeholder="18 LPA"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Expected CTC / Salary</Label>
          <Input
            value={form.expected_ctc}
            onChange={(v) => set('expected_ctc', v)}
            placeholder="25 LPA"
          />
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
          <p className="font-mono text-[10px] text-mute">
            Jobs below this are auto-rejected
          </p>
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
    </div>
  )
}

function Step5({ form, set, errors: _errors }: StepProps) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Technical Skills</Label>
        <Input
          value={form.skills_text}
          onChange={(v) => set('skills_text', v)}
          placeholder="python, pytorch, sql, react, docker, llm"
        />
        <p className="font-mono text-[10px] text-mute">
          Comma-separated. Used to fill skills checkboxes on job forms.
        </p>
      </div>
      <div className="space-y-1.5">
        <Label>Candidate Summary</Label>
        <Textarea
          value={form.candidate_summary}
          onChange={(v) => set('candidate_summary', v)}
          placeholder="3+ years building ML systems at scale. Specialised in LLM fine-tuning, RAG pipelines, and production inference. Strong Python, PyTorch, and SQL. Open to remote-first roles in India."
          rows={5}
          maxLength={1500}
        />
        <p className="font-mono text-[10px] text-mute">
          This is what the AI uses to answer "tell us about yourself" questions.
        </p>
      </div>
      <div className="space-y-1.5">
        <Label>Experience Highlights</Label>
        <Textarea
          value={form.experience_highlights}
          onChange={(v) => set('experience_highlights', v)}
          placeholder="Led re-ranking model that improved CTR by 18%. Built RAG pipeline serving 2M daily queries. Reduced inference latency 40% via quantization."
          rows={4}
          maxLength={2000}
        />
      </div>
    </div>
  )
}

const EXP_LEVEL_OPTIONS = [
  { value: '1', label: 'Internship' },
  { value: '2', label: 'Entry Level' },
  { value: '3', label: 'Associate' },
  { value: '4', label: 'Mid-Senior' },
  { value: '5', label: 'Director' },
]

function Step6({ form, set, errors: _errors }: StepProps) {
  function toggleLevel(val: string) {
    const current = form.experience_levels
    const next = current.includes(val)
      ? current.filter((v) => v !== val)
      : [...current, val]
    set('experience_levels', next)
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Target Job Titles / Keywords</Label>
        <Input
          value={form.preferred_roles}
          onChange={(v) => set('preferred_roles', v)}
          placeholder="ML Engineer, AI Engineer, Backend Engineer"
        />
        <p className="font-mono text-[10px] text-mute">
          Comma-separated. Used as LinkedIn search keywords.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Target Locations</Label>
          <Input
            value={form.target_locations}
            onChange={(v) => set('target_locations', v)}
            placeholder="Bengaluru, Remote"
          />
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
              onClick={() => toggleLevel(opt.value)}
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
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Companies to Avoid</Label>
          <Input
            value={form.avoid_companies}
            onChange={(v) => set('avoid_companies', v)}
            placeholder="TCS, Infosys, Wipro"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Title Keywords to Skip</Label>
          <Input
            value={form.avoid_roles}
            onChange={(v) => set('avoid_roles', v)}
            placeholder="intern, staff, principal, manager"
          />
        </div>
      </div>
      <div className="space-y-3">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Auto-Apply Score Threshold</Label>
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
        </div>
        <div className="space-y-1.5">
          <Label>Max Daily Applications</Label>
          <Input
            type="number"
            value={String(form.max_daily_applications)}
            onChange={(v) => set('max_daily_applications', Math.min(30, Math.max(1, Number(v) || 15)))}
            placeholder="15"
          />
          <p className="font-mono text-[10px] text-mute">Maximum 30 per day.</p>
        </div>
      </div>
    </div>
  )
}

function Step7() {
  return (
    <div className="space-y-6">
      <div className="border border-line2 rounded-lg bg-ink2/40 p-5 space-y-3">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg border border-amber/30 bg-amber/10 flex items-center justify-center shrink-0">
            <svg viewBox="0 0 24 24" className="w-4 h-4 text-amber" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
          </div>
          <div>
            <p className="text-sm text-cream font-medium">Upload via Chrome Extension</p>
            <p className="font-mono text-[11px] text-mute mt-0.5">
              Open the JobCrawler extension popup → Settings → Upload Resume
            </p>
          </div>
        </div>
      </div>

      <div className="border border-line2 rounded-lg bg-ink2/40 p-5 space-y-3">
        <p className="font-mono text-[11px] uppercase tracking-wider text-cream2">Why your resume matters</p>
        <ul className="space-y-2">
          {[
            'Fills "upload resume" fields on job applications automatically',
            'Provides context for AI-generated cover letters',
            'Helps score your fit against job descriptions',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-cream2">
              <span className="text-amber mt-0.5 shrink-0">→</span>
              {item}
            </li>
          ))}
        </ul>
      </div>

      <div className="border border-green/20 bg-green/5 rounded-lg px-4 py-3 font-mono text-xs text-green">
        Your profile is saved. You can upload your resume anytime from the extension or the Profile page.
      </div>
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────────

export function Onboarding() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [step, setStep] = useState(1)
  const [form, setForm] = useState<FormState>(EMPTY)
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({})
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [loaded, setLoaded] = useState(false)

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
      } catch {
        // Profile doesn't exist yet — start fresh
      }

      try {
        const pref = await api.get<SearchPrefShape>('/discovery/preferences')
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
      } catch {
        // Preferences don't exist yet
      }

      setLoaded(true)
    }
    load()
  }, [])

  function setField(k: keyof FormState, v: FormState[keyof FormState]) {
    setForm((f) => ({ ...f, [k]: v }))
    setErrors((e) => ({ ...e, [k]: undefined }))
  }

  function validate(): boolean {
    const errs: Partial<Record<keyof FormState, string>> = {}
    if (step === 1 && !form.name.trim()) errs.name = 'Full name is required'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  async function save() {
    if (step === 1) {
      await api.patch('/profile', {
        name: form.name,
        phone: form.phone || null,
        linkedin_url: form.linkedin_url || null,
        github_url: form.github_url || null,
        portfolio_url: form.portfolio_url || null,
        location_current: form.location_current || null,
      })
    } else if (step === 2) {
      await api.patch('/profile', {
        total_experience: form.total_experience || null,
        work_authorization: form.work_authorization || null,
        willing_to_relocate: form.willing_to_relocate,
        sponsorship_required: form.sponsorship_required,
        notice_period: form.notice_period || null,
        short_answers: {
          current_title: form.current_title,
          current_company: form.current_company,
        },
      })
    } else if (step === 3) {
      await api.patch('/profile', {
        degree: form.degree || null,
        college: form.college || null,
        graduation_year: form.graduation_year || null,
        cgpa: form.cgpa || null,
      })
    } else if (step === 4) {
      await api.patch('/profile', {
        current_ctc: form.current_ctc || null,
        expected_ctc: form.expected_ctc || null,
        expected_ctc_min_lpa: form.expected_ctc_min_lpa || null,
        min_comp_lpa: form.min_comp_lpa || 0,
      })
    } else if (step === 5) {
      await api.patch('/profile', {
        skills: textToSkills(form.skills_text),
        candidate_summary: form.candidate_summary || null,
        experience_highlights: form.experience_highlights || null,
      })
    } else if (step === 6) {
      const keywords = csvToArray(form.preferred_roles)
      const skip_companies = csvToArray(form.avoid_companies)
      const skip_title_keywords = csvToArray(form.avoid_roles)

      await Promise.all([
        api.post('/discovery/preferences', {
          keywords: keywords.length ? keywords : null,
          location: form.target_locations,
          experience_levels: form.experience_levels.join(','),
          remote_filter: form.remote_filter,
          time_range: 'r86400',
          auto_apply_threshold: form.auto_apply_threshold,
          max_daily_applications: form.max_daily_applications,
          skip_companies: skip_companies.length ? skip_companies : null,
          skip_title_keywords: skip_title_keywords.length ? skip_title_keywords : null,
        }),
        api.patch('/profile', {
          preferred_roles: form.preferred_roles || null,
          target_locations: form.target_locations || null,
          avoid_companies: form.avoid_companies || null,
          avoid_roles: form.avoid_roles || null,
        }),
      ])
    }
    // step 7 — resume — no save, just navigate
  }

  async function handleNext() {
    if (!validate()) return
    setSaving(true)
    setSaveError('')
    try {
      await save()
      if (step === TOTAL_STEPS) {
        navigate('/dashboard')
      } else {
        setStep((s) => s + 1)
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const stepProps: StepProps = {
    form,
    set: setField,
    errors,
    userEmail: user?.email ?? '',
  }

  if (!loaded) {
    return (
      <div className="min-h-screen bg-ink flex items-center justify-center">
        <div className="font-mono text-sm text-mute animate-pulse">Loading profile…</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-ink text-cream px-4 py-8">
      <link
        href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap"
        rel="stylesheet"
      />

      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <Link to="/" className="inline-flex items-center gap-2">
            <span className="relative w-7 h-7 inline-flex items-center justify-center">
              <span className="absolute inset-0 rounded-md border border-line2" />
              <svg
                viewBox="0 0 24 24"
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
              >
                <circle cx="12" cy="12" r="3.2" stroke="#FF8A1F" />
                <path
                  d="M12 8.8V4M12 15.2V20M8.8 12H4M15.2 12H20M9.7 9.7L6.3 6.3M14.3 9.7L17.7 6.3M9.7 14.3L6.3 17.7M14.3 14.3L17.7 17.7"
                  stroke="#EDE6D6"
                />
              </svg>
            </span>
            <span className="font-semibold tracking-tight text-[15px]">JobCrawler</span>
          </Link>
          <Link
            to="/dashboard"
            className="font-mono text-xs text-mute hover:text-cream2 transition"
          >
            Skip setup →
          </Link>
        </div>

        {/* Progress bar */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-[11px] uppercase tracking-wider text-cream2">
              Step {step} of {TOTAL_STEPS} — {STEP_LABELS[step - 1]}
            </span>
            <span className="font-mono text-xs text-mute">
              {Math.round((step / TOTAL_STEPS) * 100)}%
            </span>
          </div>
          <div className="h-1 bg-line2 rounded-full overflow-hidden">
            <div
              className="h-full bg-amber rounded-full transition-all duration-500"
              style={{ width: `${(step / TOTAL_STEPS) * 100}%` }}
            />
          </div>
          {/* Step dots */}
          <div className="flex items-center justify-between mt-3 px-0.5">
            {STEP_LABELS.map((lbl, i) => (
              <button
                key={i}
                type="button"
                onClick={() => i + 1 < step && setStep(i + 1)}
                title={lbl}
                className={`flex flex-col items-center gap-1 ${i + 1 < step ? 'cursor-pointer' : 'cursor-default'}`}
              >
                <div
                  className={`w-2 h-2 rounded-full transition-all ${
                    i + 1 < step
                      ? 'bg-amber'
                      : i + 1 === step
                        ? 'bg-amber ring-2 ring-amber/25 scale-125'
                        : 'bg-line2'
                  }`}
                />
                <span
                  className={`hidden sm:block font-mono text-[9px] leading-none ${
                    i + 1 <= step ? 'text-cream2' : 'text-mute'
                  }`}
                >
                  {lbl}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Step card */}
        <div className="border border-line2 rounded-xl bg-ink2/60 p-7">
          <h2 className="font-serif text-3xl mb-1 text-cream">{STEP_LABELS[step - 1]}</h2>
          <p className="text-cream2 text-sm mb-6">{STEP_DESCS[step - 1]}</p>

          {saveError && (
            <div className="mb-5 border border-red-soft/30 bg-red-soft/10 rounded-lg px-4 py-3 font-mono text-xs text-red-soft">
              {saveError}
            </div>
          )}

          {step === 1 && <Step1 {...stepProps} />}
          {step === 2 && <Step2 {...stepProps} />}
          {step === 3 && <Step3 {...stepProps} />}
          {step === 4 && <Step4 {...stepProps} />}
          {step === 5 && <Step5 {...stepProps} />}
          {step === 6 && <Step6 {...stepProps} />}
          {step === 7 && <Step7 />}
        </div>

        {/* Navigation */}
        <div className="mt-6 flex items-center justify-between">
          {step > 1 ? (
            <button
              type="button"
              onClick={() => {
                setStep((s) => s - 1)
                setSaveError('')
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}
              className="h-10 px-5 rounded-lg border border-line2 text-cream2 text-sm hover:text-cream hover:border-cream2 transition"
            >
              ← Back
            </button>
          ) : (
            <div />
          )}
          <button
            type="button"
            onClick={handleNext}
            disabled={saving}
            className="h-10 px-6 rounded-lg bg-amber text-ink font-semibold text-sm hover:bg-amber2 disabled:opacity-50 transition"
          >
            {saving ? 'Saving…' : step === TOTAL_STEPS ? 'Complete Setup →' : 'Save & Continue →'}
          </button>
        </div>
      </div>
    </div>
  )
}
