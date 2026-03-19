import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Loader2, Search, Download, X, CheckCircle2, HelpCircle, LogIn, Eye, EyeOff } from 'lucide-react';
import { API } from '../types';

interface MegaAccount { email: string; connected: boolean; connected_at: string; }
interface MegaFile { id: string; name: string; size: string; modifiedTime: string; already_synced: boolean; }

export default function MegaIntegration() {
  const [accounts, setAccounts] = useState<MegaAccount[]>([]);
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [showSetup, setShowSetup] = useState(false);

  // Login form
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [connecting, setConnecting] = useState(false);

  // File browsing
  const [query, setQuery] = useState('');
  const [fileType, setFileType] = useState('');
  const [allFiles, setAllFiles] = useState<MegaFile[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [searching, setSearching] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 30;

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/mega/status`);
      setAccounts(res.data.accounts || []);
      if (!activeAccount && res.data.accounts?.length > 0) setActiveAccount(res.data.accounts[0].email);
    } catch {}
  }, [activeAccount]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const connect = async () => {
    if (!loginEmail || !loginPassword) { setMsg({ ok: false, text: 'Enter your MEGA email and password.' }); return; }
    setConnecting(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/mega/connect`, { email: loginEmail, password: loginPassword });
      setAccounts(prev => [...prev.filter(a => a.email !== res.data.email), { email: res.data.email, connected: true, connected_at: new Date().toISOString() }]);
      setActiveAccount(res.data.email);
      setMsg({ ok: true, text: `Connected: ${res.data.email}` });
      setLoginEmail(''); setLoginPassword('');
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Login failed' }); }
    finally { setConnecting(false); }
  };

  const disconnect = async (email: string) => {
    await axios.post(`${API}/mega/disconnect`, { email });
    setAccounts(prev => prev.filter(a => a.email !== email));
    if (activeAccount === email) setActiveAccount(accounts.find(a => a.email !== email)?.email || null);
    setMsg({ ok: true, text: `Disconnected ${email}` });
  };

  const searchFiles = async () => {
    if (!activeAccount) return;
    setSearching(true); setMsg(null); setAllFiles([]); setSelected(new Set()); setPage(1);
    try {
      const res = await axios.post(`${API}/mega/search`, {
        email: activeAccount, query, file_type: fileType, max_results: 500,
      });
      setAllFiles(res.data.files || []);
      if (res.data.files?.length === 0) setMsg({ ok: true, text: 'No files found.' });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Search failed' }); }
    finally { setSearching(false); }
  };

  const totalPages = Math.max(1, Math.ceil(allFiles.length / PAGE_SIZE));
  const files = allFiles.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const ingestFiles = async () => {
    if (!activeAccount || selected.size === 0) return;
    setIngesting(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/mega/ingest`, { email: activeAccount, file_ids: Array.from(selected) });
      const n = res.data.ingested?.length || 0;
      const e = res.data.errors?.length || 0;
      setMsg({ ok: e === 0, text: `Ingested ${n} files${e > 0 ? `, ${e} errors` : ''}` });
      setSelected(new Set());
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Ingest failed' }); }
    finally { setIngesting(false); }
  };

  const toggle = (id: string) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  const selectAll = () => setSelected(new Set(allFiles.map(f => f.id)));
  const selectPage = () => setSelected(prev => { const s = new Set(prev); files.forEach(f => s.add(f.id)); return s; });

  const sty = {
    filter: { display: 'flex', gap: '0.4rem', flexWrap: 'wrap' as const, marginBottom: '0.5rem' },
    inp: { fontSize: '0.82rem', padding: '0.3rem 0.5rem', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.04)', color: 'var(--text-primary)', flex: 1, minWidth: '120px' },
  };

  return (
    <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <svg width="20" height="20" viewBox="0 0 24 24"><rect x="1" y="1" width="22" height="22" rx="4" fill="#D9272E"/><text x="12" y="17" textAnchor="middle" fill="#fff" fontSize="12" fontWeight="bold">M</text></svg>
        <h2 style={{ margin: 0, flex: 1 }}>MEGA</h2>
      </div>

      <button onClick={() => setShowSetup(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', fontSize: '0.82rem', padding: '0 0 0.5rem 0', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
        <HelpCircle size={13} /> {showSetup ? 'Hide' : 'Show'} Setup Info
      </button>

      {showSetup && (
        <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(217,39,46,0.08)', border: '1px solid rgba(217,39,46,0.2)', marginBottom: '1rem', fontSize: '0.85rem' }}>
          <strong>MEGA Integration:</strong>
          <p style={{ margin: '0.5rem 0 0 0', lineHeight: 1.6 }}>
            MEGA uses end-to-end encryption — there is no OAuth or third-party API access.
            Instead, sign in directly with your MEGA email and password. Your credentials are stored locally
            and used only to authenticate with MEGA's servers.
          </p>
          <p style={{ margin: '0.4rem 0 0 0', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            <strong>Tip:</strong> If you have two-factor authentication enabled on your MEGA account,
            you may need to generate an app-specific password or temporarily disable 2FA.
          </p>
        </div>
      )}

      {/* Login form */}
      <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '0.75rem', alignItems: 'center' }}>
        <input
          style={{ ...sty.inp, minWidth: '160px' }}
          placeholder="MEGA email"
          type="email"
          value={loginEmail}
          onChange={e => setLoginEmail(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && connect()}
        />
        <div style={{ position: 'relative', flex: 1, minWidth: '140px', display: 'flex' }}>
          <input
            style={{ ...sty.inp, paddingRight: '2rem', width: '100%' }}
            placeholder="Password"
            type={showPassword ? 'text' : 'password'}
            value={loginPassword}
            onChange={e => setLoginPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && connect()}
          />
          <button onClick={() => setShowPassword(v => !v)}
            style={{ position: 'absolute', right: '0.3rem', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', padding: '0.2rem' }}>
            {showPassword ? <EyeOff size={13} /> : <Eye size={13} />}
          </button>
        </div>
        <button className="btn" onClick={connect} disabled={connecting} style={{ padding: '0.35rem 0.8rem', fontSize: '0.8rem', background: '#D9272E' }}>
          {connecting ? <Loader2 size={13} className="animate-spin" /> : <LogIn size={13} />}
          {connecting ? 'Signing in...' : 'Sign In'}
        </button>
      </div>

      {accounts.length > 0 && (
        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
          {accounts.map(a => (
            <div key={a.email} onClick={() => setActiveAccount(a.email)}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.3rem 0.7rem', borderRadius: '8px', fontSize: '0.82rem', cursor: 'pointer',
                background: activeAccount === a.email ? 'rgba(217,39,46,0.15)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${activeAccount === a.email ? 'rgba(217,39,46,0.4)' : 'rgba(255,255,255,0.08)'}` }}>
              <CheckCircle2 size={12} color="var(--success)" /> {a.email}
              <button onClick={e => { e.stopPropagation(); disconnect(a.email); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 0 0.3rem', color: 'var(--text-secondary)' }}><X size={12} /></button>
            </div>
          ))}
        </div>
      )}

      {activeAccount && (
        <div>
          <div style={sty.filter}>
            <input style={sty.inp} placeholder="Filter files by name..." value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchFiles()} />
            <select style={{ ...sty.inp, maxWidth: '130px' }} value={fileType} onChange={e => setFileType(e.target.value)}>
              <option value="">All types</option>
              <option value="document">Docs</option>
              <option value="spreadsheet">Sheets</option>
              <option value="pdf">PDFs</option>
              <option value="image">Images</option>
            </select>
            <button className="btn" onClick={searchFiles} disabled={searching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}>
              {searching ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />} List Files
            </button>
          </div>
          {searching && <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}><Loader2 size={16} className="animate-spin" color="var(--accent)" /> Listing MEGA files...</div>}
          {files.length > 0 && (
            <div style={{ maxHeight: '250px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', padding: '0.3rem 0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                <button onClick={selectPage} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select page</button>
                {allFiles.length > PAGE_SIZE && <button onClick={selectAll} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select all ({allFiles.length})</button>}
                <span style={{ marginLeft: 'auto' }}>{selected.size} selected</span>
              </div>
              {files.map(f => (
                <label key={f.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.6rem', fontSize: '0.82rem', cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                  <input type="checkbox" checked={selected.has(f.id)} onChange={() => toggle(f.id)} style={{ accentColor: 'var(--accent)' }} />
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{f.modifiedTime?.slice(0, 10)}</span>
                </label>
              ))}
            </div>
          )}
          {allFiles.length > PAGE_SIZE && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', padding: '0.5rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <button className="btn" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: page <= 1 ? 0.4 : 1 }}>← Prev</button>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Page {page} of {totalPages}</span>
              <button className="btn" onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: page >= totalPages ? 0.4 : 1 }}>Next →</button>
            </div>
          )}
          {allFiles.length > 0 && selected.size > 0 && (
            <button className="btn" onClick={ingestFiles} disabled={ingesting} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem' }}>
              {ingesting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
              Ingest {selected.size} file{selected.size !== 1 ? 's' : ''}
            </button>
          )}
        </div>
      )}

      {msg && <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: msg.ok ? 'var(--success)' : 'var(--error)' }}>{msg.ok ? '✅' : '❌'} {msg.text}</div>}
    </div>
  );
}
