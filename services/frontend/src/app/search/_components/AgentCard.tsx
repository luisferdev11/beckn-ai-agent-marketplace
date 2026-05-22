'use client';

import type { DiscoveredAgent } from '@/lib/beckn-api';
import { iconForAgent } from '@/lib/beckn-api';

interface AgentCardProps {
  agent: DiscoveredAgent;
  index: number;
  onSelect: (agent: DiscoveredAgent) => void;
}

export function AgentCard({ agent, index, onSelect }: AgentCardProps) {
  const icon = iconForAgent(agent.name);
  const slaSeconds = Math.round(agent.sla.maxLatencyMs / 1000);
  const slaDisplay = slaSeconds < 60 ? `${slaSeconds}s` : `${Math.round(slaSeconds / 60)}m`;
  const accuracy = agent.sla.accuracy ? `${Math.round(agent.sla.accuracy * 100)}%` : null;
  const currencySymbol = agent.pricing.currency === 'INR' ? '₹' : agent.pricing.currency === 'USD' ? '$' : agent.pricing.currency;

  return (
    <div
      className="agent-card"
      style={{
        animationDelay: `${index * 70}ms`,
        background: '#FFFFFF',
        border: '1px solid rgba(0,124,195,0.12)',
        borderRadius: 18,
        padding: '22px',
        cursor: 'pointer',
        transition: 'box-shadow 0.2s, border-color 0.2s, transform 0.15s',
        display: 'flex', flexDirection: 'column',
      }}
      onClick={() => onSelect(agent)}
      onMouseEnter={e => {
        const el = e.currentTarget;
        el.style.boxShadow = '0 10px 36px rgba(0,124,195,0.12)';
        el.style.borderColor = 'rgba(0,124,195,0.3)';
        el.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={e => {
        const el = e.currentTarget;
        el.style.boxShadow = 'none';
        el.style.borderColor = 'rgba(0,124,195,0.12)';
        el.style.transform = 'translateY(0)';
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 46, height: 46, fontSize: 22,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'var(--infosys-cobalt-light)',
            borderRadius: 12, flexShrink: 0,
            border: '1px solid rgba(0,124,195,0.1)',
          }}>
            {icon}
          </div>
          <div>
            <h3 style={{
              fontFamily: 'var(--font-plex)',
              fontSize: 16, fontWeight: 700,
              color: 'var(--text-primary)',
              lineHeight: 1.2, marginBottom: 3,
              letterSpacing: '-0.01em',
            }}>
              {agent.name}
            </h3>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)', lineHeight: 1.4 }}>
              {agent.description.slice(0, 80)}{agent.description.length > 80 ? '…' : ''}
            </p>
          </div>
        </div>
        {accuracy && (
          <div style={{
            padding: '3px 8px', borderRadius: 6,
            background: 'rgba(0,135,90,0.08)',
            border: '1px solid rgba(0,135,90,0.15)',
            fontSize: 11, fontWeight: 600,
            color: 'var(--trust-high)',
            fontFamily: 'var(--font-mono)',
            whiteSpace: 'nowrap',
          }}>
            {accuracy}
          </div>
        )}
      </div>

      {/* Skills */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 10 }}>
        {agent.skills.slice(0, 3).map(s => (
          <span key={s.id} style={{
            fontSize: 11, padding: '3px 8px', borderRadius: 20,
            background: 'var(--infosys-cobalt-light)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-plex)',
            border: '1px solid rgba(0,124,195,0.08)',
          }}>
            {s.id.replace(/_/g, ' ')}
          </span>
        ))}
      </div>

      {/* Modalities + Jurisdiction */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {agent.modalities.map(m => (
          <span key={m} style={{
            fontSize: 10, padding: '2px 6px', borderRadius: 4,
            background: 'var(--bg-elevated)',
            color: 'var(--text-tertiary)',
            fontFamily: 'var(--font-mono)',
            border: '1px solid var(--border-subtle)',
            textTransform: 'uppercase', letterSpacing: '0.04em',
          }}>
            {m}
          </span>
        ))}
        {agent.jurisdiction && (
          <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-plex)' }}>
            {agent.jurisdiction === 'IN' ? '🇮🇳 India' : agent.jurisdiction === 'US' ? '🇺🇸 US' : agent.jurisdiction}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
          {agent.provider}
        </span>
      </div>

      {/* Price + CTA */}
      <div style={{
        marginTop: 'auto', paddingTop: 14,
        borderTop: '1px solid rgba(0,124,195,0.08)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
      }}>
        <div>
          <div>
            <span style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
              {currencySymbol}{agent.pricing.value}
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-plex)', marginLeft: 4 }}>
              / {agent.pricing.model.replace(/_/g, ' ')}
            </span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
            SLA · {slaDisplay}
          </div>
        </div>

        <button
          onClick={(e) => { e.stopPropagation(); onSelect(agent); }}
          style={{
            padding: '9px 20px',
            background: 'var(--infosys-cobalt)',
            border: 'none', borderRadius: 10,
            color: '#fff', fontFamily: 'var(--font-plex)',
            fontWeight: 600, fontSize: 13,
            cursor: 'pointer', transition: 'opacity 0.15s',
            flexShrink: 0,
            boxShadow: '0 3px 12px rgba(0,124,195,0.3)',
          }}
          onMouseEnter={e => { (e.currentTarget).style.opacity = '0.85'; }}
          onMouseLeave={e => { (e.currentTarget).style.opacity = '1'; }}
        >
          Select
        </button>
      </div>
    </div>
  );
}
