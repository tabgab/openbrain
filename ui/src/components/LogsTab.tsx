import { Terminal, RefreshCw } from 'lucide-react';
import type { LogEntry } from '../types';

export default function LogsTab({ logs, onRefresh }: { logs: LogEntry[]; onRefresh: () => void }) {
  const colors: Record<string, string> = {
    success: 'var(--success)', error: 'var(--error)', warning: 'var(--warning)', info: 'var(--text-secondary)'
  };
  return (
    <div className="glass-panel">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <Terminal size={20} color="var(--accent)" />
        <h2>System Logs</h2>
        <button onClick={onRefresh} className="btn btn-secondary" style={{ marginLeft: 'auto', padding: '0.35rem 0.8rem', fontSize: '0.85rem' }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>
      {logs.length === 0 ? (
        <p style={{ textAlign: 'center', padding: '2rem 0' }}>No events yet — they will appear here as the system runs.</p>
      ) : (
        <div style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
          {logs.map((l, i) => (
            <div key={i} style={{ display: 'flex', gap: '1rem', padding: '0.5rem 0', borderBottom: '1px solid var(--glass-border)' }}>
              <span style={{ color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{new Date(l.timestamp).toLocaleTimeString()}</span>
              <span style={{ color: colors[l.level] || 'white', textTransform: 'uppercase', fontWeight: 600, minWidth: '60px' }}>{l.level}</span>
              <span style={{ color: 'var(--accent)', minWidth: '90px' }}>{l.source}</span>
              <span style={{ color: 'var(--text-primary)', flex: 1 }}>{l.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
