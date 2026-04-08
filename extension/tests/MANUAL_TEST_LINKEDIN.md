# Manual Testing: LinkedIn Easy Apply

End-to-end smoke tests against the live LinkedIn DOM. Run these after every
change to `extension/src/content/sites/linkedin.ts`, the field scanner, or the
form filler.

## Prerequisites

1. Build the extension: `cd extension && npm run build`
2. Load it in Chrome: `chrome://extensions` → enable Developer mode →
   "Load unpacked" → select `extension/dist`
3. Backend running locally: `cd api && uvicorn api.main:app --reload`
4. Logged into LinkedIn in the same Chrome profile
5. Logged into JobCrawler: click the extension icon → log in
6. Profile created (POST `/profile` or `/profile/import-markdown`)
7. Open DevTools → Console on the LinkedIn tab and filter for `[JobCrawler`

## Test 1 — Single-step Easy Apply (fill only, do not submit)

1. Find a job with a 1–2 field Easy Apply (e.g. just phone number).
2. Click **Easy Apply**.
3. **Verify in console:**
   - `[JobCrawler:linkedin] Easy Apply started:` log with title/company/url
   - `SCORE_JOB` and `TRACK_JOB` calls succeed
4. **Verify in DOM:**
   - Each field is filled with a sensible value
   - Typing happens with visible per-character delays (human-like)
   - No fields with React-controlled inputs are reverted after fill
5. Click **Dismiss** without submitting. Confirm the discard dialog handling
   does not break the next attempt.

## Test 2 — Multi-step Easy Apply

1. Find a job that requires 3+ steps (typical: contact info → questions →
   review → submit).
2. Click **Easy Apply**.
3. **Verify:**
   - Step 1 fields filled
   - **Next** button clicked automatically
   - Step 2 fields scanned and filled
   - Process repeats until the **Review** screen
   - Extension stops at **Submit application** and leaves the final click to
     you (intentional safety check)
4. **Verify console:** `reached Submit — leaving final click to user.`
5. Click **Submit application** manually. Confirm the application appears in
   the API: `GET /jobs` → status `applied` (the orchestrator marks the row
   `applying` on the submit step; you may PATCH it to `applied` manually
   during testing if the auto-submit observer isn't wired yet).

## Test 3 — Validation error retry

1. Find a job with a numeric field (e.g. "Years of experience").
2. Temporarily edit your profile so the value LinkedIn rejects (e.g. set
   `years_experience` to a non-numeric token).
3. Click **Easy Apply**.
4. **Verify:**
   - First fill triggers a red inline error
   - Console logs: `validation errors detected, retrying:` with the field/error
   - Second fill produces a valid value and the error clears
5. Restore the profile.

## Test 4 — Pre-filled field skip

1. Find an Easy Apply job and manually type a value into the first field
   **before** clicking Easy Apply (LinkedIn often remembers prior values).
2. Click **Easy Apply**.
3. **Verify:** the pre-filled field is left untouched, and the API call
   in DevTools Network panel only includes the empty fields.

## Test 5 — File upload step

1. Find a job whose first Easy Apply step contains only a resume upload.
2. Click **Easy Apply**.
3. **Verify:**
   - No `ANSWER_FIELDS` request is sent for that step
   - The extension clicks **Next** without trying to fill anything
   - The resume from your LinkedIn profile remains attached

## Test 6 — Modal closed unexpectedly

1. Click **Easy Apply** then immediately click **Dismiss** (or the X).
2. **Verify:** console shows `modal_closed` or a graceful return — no uncaught
   exceptions, no zombie observers.
3. Reopen Easy Apply on a different job in the same tab; the observer
   re-arms and the second attempt works.

## Regression checklist

- [ ] Test 1 — single-step fill works
- [ ] Test 2 — multi-step navigation reaches Submit
- [ ] Test 3 — validation error retry succeeds
- [ ] Test 4 — pre-filled fields are not overwritten
- [ ] Test 5 — file-upload-only steps are skipped cleanly
- [ ] Test 6 — modal close is handled gracefully
