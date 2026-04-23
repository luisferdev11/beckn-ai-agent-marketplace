'use client';

import { TrustGauge } from './TrustGauge';
import type { Agent } from '@/lib/mock-data';
export type { Agent };

interface AgentCardProps {
  agent: Agent;
  index: number;
  onSelect: (agent: Agent) => void;
}

export function AgentCard({ agent, index, onSelect }: AgentCardProps) {
  const slaDisplay =
    agent.sla_p95_seconds < 60
      ? `${agent.sla_p95_seconds}s`
      : `${Math.round(agent.sla_p95_seconds / 60)}m`;

  return (
    <div
      className="agent-card"
      style={{
        animationDelay: `${index * 70}ms`,
        background: '#FFFFFF',
        border: '1px solid rgba(109,40,217,0.1)',
        borderRadius: 18,
        padding: '22px',
        cursor: 'pointer',
        transition: 'box-shadow 0.2s, border-color 0.2s, transform 0.15s',
        display: 'flex', flexDirection: 'column',
      }}
      onMouseEnter={e => {
        const el = e.currentTarget as HTMLElement;
        el.style.boxShadow = '0 10px 36px rgba(109,40,217,0.12)';
        el.style.borderColor = 'rgba(109,40,217,0.25)';
        el.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={e => {
        const el = e.currentTarget as HTMLElement;
        el.style.boxShadow = 'none';
        el.style.borderColor = 'rgba(109,40,217,0.1)';
        el.style.transform = 'translateY(0)';
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 46, height: 46, fontSize: 22,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: '#F5F3FF',
            borderRadius: 12, flexShrink: 0,
            border: '1px solid rgba(109,40,217,0.1)',
          }}>
            {agent.icon}
          </div>
          <div>
            <h3 style={{
              fontFamily: 'var(--font-syne)',
              fontSize: 16, fontWeight: 700,
              color: 'var(--text-primary)',
              lineHeight: 1.2, marginBottom: 3,
              letterSpacing: '-0.01em',
            }}>
              {agent.name}
            </h3>
            <p style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)', lineHeight: 1.4 }}>
              {agent.tagline}
            </p>
          </div>
        </div>
        <TrustGauge score={agent.trust_score} />
      </div>

      {/* Credentials */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 10 }}>
        {agent.credentials.map(c => (
          <span key={c} style={{
            fontSize: 10, padding: '3px 8px', borderRadius: 20,
            background: 'var(--accent-dim)', color: 'var(--accent)',
            fontFamily: 'var(--font-dm)', fontWeight: 600,
            border: '1px solid rgba(109,40,217,0.18)',
          }}>
            {c}
          </span>
        ))}
      </div>

      {/* Capabilities */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 14 }}>
        {agent.capabilities.map(cap => (
          <span key={cap} style={{
            fontSize: 11, padding: '3px 8px', borderRadius: 20,
            background: '#F5F3FF', color: 'var(--text-secondary)',
            fontFamily: 'var(--font-dm)',
            border: '1px solid rgba(109,40,217,0.08)',
          }}>
            {cap}
          </span>
        ))}
      </div>

      {/* Residency + Provider */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {agent.data_residency.map(r => (
          <span key={r} style={{ fontSize: 12, color: 'var(--text-secondary)', fontFamily: 'var(--font-dm)' }}>
            {r === 'India' ? '🇮🇳' : r === 'EU' ? '🇪🇺' : '🌐'} {r}
          </span>
        ))}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
          {agent.provider}
        </span>
      </div>

      {/* Price + CTA */}
      <div style={{
        marginTop: 'auto', paddingTop: 14,
        borderTop: '1px solid rgba(109,40,217,0.08)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
      }}>
        <div>
          <div>
            <span style={{ fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>
              ₹{agent.price_per_task}
            </span>
            <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontFamily: 'var(--font-dm)', marginLeft: 4 }}>
              / task
            </span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
            SLA p95 · {slaDisplay}
          </div>
        </div>

        <button
          onClick={() => onSelect(agent)}
          style={{
            padding: '9px 20px',
            background: 'var(--accent-send)',
            border: 'none', borderRadius: 10,
            color: '#fff', fontFamily: 'var(--font-dm)',
            fontWeight: 600, fontSize: 13,
            cursor: 'pointer', transition: 'opacity 0.15s',
            flexShrink: 0, letterSpacing: '0.01em',
            boxShadow: '0 3px 12px rgba(109,40,217,0.3)',
          }}
          onMouseEnter={e => ((e.currentTarget as HTMLElement).style.opacity = '0.85')}
          onMouseLeave={e => ((e.currentTarget as HTMLElement).style.opacity = '1')}
        >
          Select
        </button>
      </div>
    </div>
  );
}
