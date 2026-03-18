import { useState } from 'react';
import axios from 'axios';
import { CheckCircle2, XCircle, RefreshCw, X, Loader2 } from 'lucide-react';
import { API } from '../types';
import type { Health } from '../types';

interface DbStats {
  total_memories: number;
  source_breakdown: Record<string, number>;
  category_breakdown: Record<string, number>;
  oldest_memory: string | null;
  newest_memory: string | null;
  db_size: string;
  table_size: string;
  index_size: string;
  embedding_dim: number | null;
  secrets_count: number;
}

export default function HealthBar({ health, onRefresh, onGoSettings }: { health: Health | null; onRefresh: () => void; onGoSettings: () => void }) {
  const [showDbStats, setShowDbStats] = useState(false);
  const [dbStats, setDbStats] = useState<DbStats | null>(null);
  const [dbStatsLoading, setDbStatsLoading] = useState(false);

  const toggleDbStats = async () => {
    if (showDbStats) { setShowDbStats(false); return; }
    setShowDbStats(true);
    setDbStatsLoading(true);
    try {
      const res = await axios.get(`${API}/db/stats`);
      setDbStats(res.data);
    } catch { setDbStats(null); }
    finally { setDbStatsLoading(false); }
  };

  if (!health) return null;

  const checks = [
    { label: 'Database', ...health.db },
    { label: 'LLM', ...health.llm },
    { label: 'Telegram', ok: health.telegram.ok, error: health.telegram.error, extra: health.telegram.bot_name ? `@${health.telegram.bot_name}` : '' },
  ];

  return (
    <div style={{ position: 'relative', marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'center' }}>
        {checks.map(c => (
          <div key={c.label} title={c.ok ? (c as any).extra || 'Connected' : c.error} style={{
            display: 'flex', alignItems: 'center', gap: '0.4rem',
            padding: '0.4rem 0.9rem', borderRadius: '999px', fontSize: '0.85rem', fontWeight: 500,
            background: c.ok ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.12)',
            color: c.ok ? 'var(--success)' : 'var(--error)',
            border: `1px solid ${c.ok ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
            cursor: c.label === 'Database' && c.ok ? 'pointer' : (c.ok ? 'default' : 'pointer'),
          }} onClick={c.label === 'Database' && c.ok ? toggleDbStats : (c.ok ? undefined : onGoSettings)}>
            {c.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
            {c.label} {c.ok && (c as any).extra ? `·  ${(c as any).extra}` : ''}
            {!c.ok && <span style={{ fontSize: '0.78rem', opacity: 0.8 }}>— {c.error || 'Not configured'}</span>}
          </div>
        ))}
        <button onClick={onRefresh} className="btn btn-secondary" style={{ padding: '0.4rem 0.8rem', marginLeft: 'auto', fontSize: '0.85rem' }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Database Stats Panel */}
      {showDbStats && (
        <div className="glass-panel" style={{ position: 'absolute', top: '100%', left: 0, zIndex: 50, marginTop: '0.5rem', minWidth: '340px', maxWidth: '420px', padding: '1rem', boxShadow: '0 8px 32px rgba(0,0,0,0.4)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h3 style={{ margin: 0, fontSize: '0.95rem' }}>Database Metrics</h3>
            <button onClick={() => setShowDbStats(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', display: 'flex' }}>
              <X size={16} />
            </button>
          </div>
          {dbStatsLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '1rem' }}><Loader2 size={20} className="animate-spin" color="var(--accent)" /></div>
          ) : dbStats ? (
            <div style={{ display: 'grid', gap: '0.5rem', fontSize: '0.82rem' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                <div className="event-card" style={{ padding: '0.5rem 0.7rem' }}>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--accent)' }}>{dbStats.total_memories}</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>Total Memories</div>
                </div>
                <div className="event-card" style={{ padding: '0.5rem 0.7rem' }}>
                  <div style={{ fontSize: '1.3rem', fontWeight: 700, color: 'var(--accent)' }}>{dbStats.db_size}</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>Database Size</div>
                </div>
              </div>
              <div className="event-card" style={{ padding: '0.5rem 0.7rem' }}>
                <div style={{ marginBottom: '0.3rem', fontWeight: 600, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Storage</div>
                <div style={{ display: 'flex', gap: '1rem' }}>
                  <span><strong>Table:</strong> {dbStats.table_size}</span>
                  <span><strong>Indexes:</strong> {dbStats.index_size}</span>
                  {dbStats.embedding_dim && <span><strong>Vectors:</strong> {dbStats.embedding_dim}d</span>}
                </div>
              </div>
              {Object.keys(dbStats.source_breakdown).length > 0 && (
                <div className="event-card" style={{ padding: '0.5rem 0.7rem' }}>
                  <div style={{ marginBottom: '0.3rem', fontWeight: 600, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>By Source</div>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {Object.entries(dbStats.source_breakdown).map(([k, v]) => (
                      <span key={k} style={{ padding: '0.15rem 0.5rem', borderRadius: '4px', background: 'rgba(139,92,246,0.1)', fontSize: '0.78rem' }}>
                        {k}: <strong>{v}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {Object.keys(dbStats.category_breakdown).length > 0 && (
                <div className="event-card" style={{ padding: '0.5rem 0.7rem' }}>
                  <div style={{ marginBottom: '0.3rem', fontWeight: 600, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>By Category</div>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {Object.entries(dbStats.category_breakdown).map(([k, v]) => (
                      <span key={k} style={{ padding: '0.15rem 0.5rem', borderRadius: '4px', background: 'rgba(59,130,246,0.1)', fontSize: '0.78rem' }}>
                        {k}: <strong>{v}</strong>
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div className="event-card" style={{ padding: '0.5rem 0.7rem' }}>
                <div style={{ marginBottom: '0.3rem', fontWeight: 600, fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Timeline</div>
                <div style={{ display: 'flex', gap: '1rem', fontSize: '0.78rem' }}>
                  {dbStats.oldest_memory && <span><strong>First:</strong> {new Date(dbStats.oldest_memory).toLocaleDateString()}</span>}
                  {dbStats.newest_memory && <span><strong>Latest:</strong> {new Date(dbStats.newest_memory).toLocaleDateString()}</span>}
                </div>
              </div>
              {dbStats.secrets_count > 0 && (
                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textAlign: 'right' }}>
                  {dbStats.secrets_count} secret{dbStats.secrets_count !== 1 ? 's' : ''} in vault
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: 'var(--error)', fontSize: '0.85rem' }}>Failed to load database stats.</div>
          )}
        </div>
      )}
    </div>
  );
}
