'use client';

export interface FilterState {
  data_residency: string[];
  credentials: string[];
  capabilities: string[];
  language_support: string[];
  price_max: number;
}

interface FilterPanelProps {
  filters: FilterState;
  onChange: (filters: FilterState) => void;
  complianceMode: boolean;
}

const DATA_RESIDENCY_OPTIONS = ['India', 'EU', 'US'];
const CREDENTIAL_OPTIONS = ['ISO 27001', 'DPDP Compliant', 'Govt Data', 'SEBI Approved', 'RBI Framework'];
const CAPABILITY_OPTIONS = ['summarization', 'ocr', 'translation', 'extraction', 'classification', 'audit'];
const LANGUAGE_OPTIONS = ['Hindi', 'English', 'Marathi', 'Tamil', 'Bengali', 'Telugu'];

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '5px 13px', borderRadius: 20,
        border: `1px solid ${active ? 'rgba(109,40,217,0.4)' : 'rgba(109,40,217,0.12)'}`,
        background: active ? 'var(--accent-dim)' : 'transparent',
        color: active ? 'var(--accent)' : 'var(--text-secondary)',
        fontFamily: 'var(--font-dm)', fontSize: 12,
        fontWeight: active ? 600 : 400,
        cursor: 'pointer', transition: 'all 0.15s',
        whiteSpace: 'nowrap',
      }}
      onMouseEnter={e => {
        if (!active) {
          (e.currentTarget as HTMLElement).style.borderColor = 'rgba(109,40,217,0.25)';
          (e.currentTarget as HTMLElement).style.color = 'var(--text-primary)';
        }
      }}
      onMouseLeave={e => {
        if (!active) {
          (e.currentTarget as HTMLElement).style.borderColor = 'rgba(109,40,217,0.12)';
          (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)';
        }
      }}
    >
      {active ? '✓ ' : ''}{label}
    </button>
  );
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      <span style={{
        fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)',
        fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap',
        minWidth: 76, textAlign: 'right', letterSpacing: '0.04em',
        textTransform: 'uppercase',
      }}>
        {label}
      </span>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 1 }}>{children}</div>
    </div>
  );
}

const DEFAULT_FILTERS: FilterState = {
  data_residency: [], credentials: [], capabilities: [],
  language_support: [], price_max: 5000,
};

export function FilterPanel({ filters, onChange, complianceMode: _c }: FilterPanelProps) {
  const toggle = <K extends keyof FilterState>(key: K, value: string) => {
    const arr = filters[key] as string[];
    const next = arr.includes(value) ? arr.filter(v => v !== value) : [...arr, value];
    onChange({ ...filters, [key]: next });
  };

  const activeCount =
    filters.data_residency.length + filters.credentials.length +
    filters.capabilities.length + filters.language_support.length +
    (filters.price_max < 5000 ? 1 : 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <FilterRow label="Location">
        {DATA_RESIDENCY_OPTIONS.map(opt => (
          <Chip key={opt} label={opt} active={filters.data_residency.includes(opt)}
            onClick={() => toggle('data_residency', opt)} />
        ))}
      </FilterRow>
      <FilterRow label="Compliance">
        {CREDENTIAL_OPTIONS.map(opt => (
          <Chip key={opt} label={opt} active={filters.credentials.includes(opt)}
            onClick={() => toggle('credentials', opt)} />
        ))}
      </FilterRow>
      <FilterRow label="Capability">
        {CAPABILITY_OPTIONS.map(opt => (
          <Chip key={opt} label={opt} active={filters.capabilities.includes(opt)}
            onClick={() => toggle('capabilities', opt)} />
        ))}
      </FilterRow>
      <FilterRow label="Language">
        {LANGUAGE_OPTIONS.map(opt => (
          <Chip key={opt} label={opt} active={filters.language_support.includes(opt)}
            onClick={() => toggle('language_support', opt)} />
        ))}
      </FilterRow>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 11, fontWeight: 600, color: 'var(--text-tertiary)',
          fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap',
          minWidth: 76, textAlign: 'right', letterSpacing: '0.04em', textTransform: 'uppercase',
        }}>
          Max Price
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
          <input
            type="range" min={100} max={5000} step={100}
            value={filters.price_max}
            onChange={e => onChange({ ...filters, price_max: Number(e.target.value) })}
            style={{ flex: 1, maxWidth: 200, accentColor: 'var(--accent)', cursor: 'pointer' }}
          />
          <span style={{ fontSize: 12, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600, minWidth: 60 }}>
            ₹{filters.price_max.toLocaleString('en-IN')}
          </span>
          {activeCount > 0 && (
            <button
              onClick={() => onChange(DEFAULT_FILTERS)}
              style={{
                fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-dm)',
                background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', padding: 0,
              }}
            >
              Clear all
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
