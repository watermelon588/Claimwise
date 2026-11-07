// Policy check for the O3 pause: facts read from the uploaded policy, editable before confirming.
import { useId, useState } from 'react'
import { Check, ChevronDown, ExternalLink, FileCheck2, Shield } from 'lucide-react'
import { Accent, Quiet } from './ui.jsx'
import { ICON } from './tokens.js'

const GROUPS = [
  {
    title: 'Policy and members',
    Icon: FileCheck2,
    fields: [
      { key: 'insurer', label: 'Insurer', wide: true },
      { key: 'policy_number', label: 'Policy number', mono: true },
      { key: 'policy_type', label: 'Policy type', type: 'select' },
      { key: 'members', label: 'Covered members', type: 'textarea', wide: true, hint: 'Separate names with commas.' },
    ],
  },
  {
    title: 'Coverage',
    Icon: Shield,
    fields: [
      { key: 'sum_insured', label: 'Sum insured', type: 'number', mono: true },
      { key: 'tpa', label: 'Third-party administrator (TPA)' },
      { key: 'period_start', label: 'Cover starts', type: 'date', mono: true },
      { key: 'period_end', label: 'Cover ends', type: 'date', mono: true },
    ],
  },
]

/** Turn a policy record into editable string values. */
function toForm(policy) {
  const form = {}
  for (const { key } of GROUPS.flatMap((group) => group.fields)) {
    form[key] = key === 'members' ? (policy.members ?? []).join(', ') : String(policy[key] ?? '')
  }
  return form
}

/** Turn an edited value back into the backend type (list, number or string; empty means null). */
function fromForm(key, value) {
  if (key === 'members') return value.split(',').map((s) => s.trim()).filter(Boolean)
  if (value === '') return null
  return key === 'sum_insured' ? Number(value) : value
}

/** Render a labeled native control, with edited and keyboard-focus states. */
function PolicyField({ field, value, edited, onChange }) {
  const id = useId()
  const { key, label, type = 'text', mono, wide, hint } = field
  const control = {
    id,
    name: key,
    value,
    onChange: (event) => onChange(event.target.value),
    'aria-describedby': hint ? `${id}-hint` : undefined,
    className: `min-w-0 w-full bg-transparent p-0 text-sm font-medium text-ink ${mono ? 'font-mono tabular-nums' : ''}`,
  }
  return (
    <div className={`policy-field min-w-0 rounded-xl border px-3.5 py-2.5 transition-colors focus-within:border-coral-ink focus-within:ring-2 focus-within:ring-coral/20 ${edited ? 'border-coral/55 bg-coral-soft/35' : 'border-line bg-milk/55 hover:border-ink/35'} ${wide ? 'sm:col-span-2' : ''}`}>
      <div className="mb-1 flex flex-wrap items-baseline justify-between gap-x-2">
        <label htmlFor={id} className="text-xs font-semibold leading-tight text-muted">{label}</label>
        {edited && <span className="text-[11px] font-semibold text-coral-ink">Edited</span>}
      </div>
      {type === 'select' ? (
        <div className="relative">
          <select {...control} className={`${control.className} appearance-none pr-6`}>
            <option value="">Not stated</option>
            <option value="individual">Individual</option>
            <option value="family_floater">Family floater</option>
            <option value="group">Group</option>
          </select>
          <ChevronDown {...ICON} size={14} className="pointer-events-none absolute top-1/2 right-0 -translate-y-1/2 text-muted" />
        </div>
      ) : type === 'textarea' ? (
        <textarea {...control} rows={2} className={`${control.className} block resize-y leading-relaxed`} />
      ) : (
        <div className="flex items-center gap-2">
          {type === 'number' && <span className="text-sm font-medium text-muted" aria-hidden="true">₹</span>}
          <input {...control} type={type} aria-label={type === 'number' ? 'Sum insured in rupees' : undefined} />
        </div>
      )}
      {hint && <p id={`${id}-hint`} className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  )
}

/**
 * Policy confirmation form.
 * @param {{pending: object, onAnswer: (approved: boolean, corrections?: object) => void, busy: boolean, onOpenDocument: (id: string) => void}} props
 * @returns {JSX.Element}
 */
export default function ConfirmPolicy({ pending, onAnswer, busy, onOpenDocument }) {
  const original = toForm(pending.policy)
  const [form, setForm] = useState(original)
  const changed = Object.keys(form).filter((k) => form[k] !== original[k]).length

  /** Send only the fields the user changed as corrections. */
  function confirm(e) {
    e.preventDefault()
    const corrections = {}
    for (const key of Object.keys(form)) {
      if (form[key] !== original[key]) corrections[key] = fromForm(key, form[key])
    }
    onAnswer(true, corrections)
  }

  return (
    <form onSubmit={confirm} aria-label="Policy details" className="overflow-hidden rounded-2xl border border-line bg-paper shadow-[0_10px_24px_-20px_rgb(86_62_25/0.45)]">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line bg-milk/65 px-4 py-3.5 sm:px-5">
        <div>
          <p className="text-sm font-semibold">Extracted policy details</p>
          <p className="text-xs text-muted">Compare with the upload and correct anything that differs.</p>
        </div>
        <button type="button" onClick={() => onOpenDocument(pending.policy.doc_id)} className="inline-flex min-h-9 shrink-0 items-center gap-2 rounded-lg border border-line bg-paper px-3 text-xs font-semibold text-coral-ink transition-colors hover:border-coral-ink hover:bg-coral-soft/50">
          <ExternalLink {...ICON} size={14} /> View original
        </button>
      </div>
      <div className="space-y-5 px-4 py-4 sm:px-5 sm:py-5">
        {GROUPS.map(({ title, Icon, fields }) => (
          <fieldset key={title} className="min-w-0">
            <legend className="mb-2.5 text-sm font-semibold">
              <span className="inline-flex items-center gap-2"><Icon {...ICON} size={15} className="text-coral-ink" /> {title}</span>
            </legend>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {fields.map((field) => (
                <PolicyField
                  key={field.key}
                  field={field}
                  value={form[field.key]}
                  edited={form[field.key] !== original[field.key]}
                  onChange={(value) => setForm((previous) => ({ ...previous, [field.key]: value }))}
                />
              ))}
            </div>
          </fieldset>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-3.5 sm:px-5">
        <Accent type="submit" disabled={busy}>
          <Check {...ICON} /> {changed ? `Confirm with ${changed} ${changed === 1 ? 'fix' : 'fixes'}` : 'Confirm details'}
        </Accent>
        <Quiet onClick={() => onAnswer(false)} disabled={busy}>Wrong document</Quiet>
      </div>
    </form>
  )
}
