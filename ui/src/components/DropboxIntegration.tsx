import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Loader2, CheckCircle2, Search, X, Download, Upload, HelpCircle, Link
} from 'lucide-react';
import { API } from '../types';

interface DropboxAccount { email: string; name: string; connected: boolean; connected_at?: string; }
interface DropboxFile { id: string; name: string; path: string; size: string; modifiedTime: string; already_synced: boolean; }

export default function DropboxIntegration() {
  const [hasCreds, setHasCreds] = useState(false);
  const [accounts, setAccounts] = useState<DropboxAccount[]>([]);
  const [connecting, setConnecting] = useState(false);
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [showSetup, setShowSetup] = useState(false);

  const [query, setQuery] = useState('');
  const [path, setPath] = useState('');
  const [fileType, setFileType] = useState('');
  const [files, setFiles] = useState<DropboxFile[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [searching, setSearching] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/dropbox/status`);
      setHasCreds(res.data.has_credentials);
      setAccounts(res.data.accounts || []);
      if (!activeAccount && res.data.accounts?.length > 0) setActiveAccount(res.data.accounts[0].email);
    } catch {}
  }, [activeAccount]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const connect = async () => {
    setConnecting(true); setMsg(null);
    const win = window.open('about:blank', '_blank');
    try {
      const res = await axios.post(`${API}/dropbox/connect`);
      if (res.data.auth_url) {
        if (win) win.location.href = res.data.auth_url;
        else setMsg({ ok: false, text: `Popup blocked — open: ${res.data.auth_url}` });
      }
      const poll = setInterval(async () => {
        const s = await axios.get(`${API}/dropbox/status`);
        const accts = s.data.accounts || [];
        if (accts.length > accounts.length) {
          setAccounts(accts);
          setActiveAccount(accts[accts.length - 1].email);
          clearInterval(poll); setConnecting(false);
          setMsg({ ok: true, text: `Connected: ${accts[accts.length - 1].email}` });
        }
      }, 3000);
      setTimeout(() => { clearInterval(poll); setConnecting(false); }, 120000);
    } catch (err: any) {
      if (win) win.close();
      setMsg({ ok: false, text: err?.response?.data?.detail || 'Failed to start OAuth' });
      setConnecting(false);
    }
  };

  const disconnect = async (email: string) => {
    await axios.post(`${API}/dropbox/disconnect`, { email });
    setAccounts(prev => prev.filter(a => a.email !== email));
    if (activeAccount === email) setActiveAccount(accounts.find(a => a.email !== email)?.email || null);
    setMsg({ ok: true, text: `Disconnected ${email}` });
  };

  const searchFiles = async () => {
    if (!activeAccount) return;
    setSearching(true); setMsg(null); setFiles([]); setSelected(new Set());
    try {
      const res = await axios.post(`${API}/dropbox/search`, {
        email: activeAccount, query, path, file_type: fileType, max_results: 30,
      });
      setFiles(res.data.files || []);
      if (res.data.files?.length === 0) setMsg({ ok: true, text: 'No files found.' });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Search failed' }); }
    finally { setSearching(false); }
  };

  const ingestFiles = async () => {
    if (!activeAccount || selected.size === 0) return;
    setIngesting(true); setMsg(null);
    const paths = files.filter(f => selected.has(f.id)).map(f => f.path);
    try {
      const res = await axios.post(`${API}/dropbox/ingest`, { email: activeAccount, file_paths: paths });
      const n = res.data.ingested?.length || 0;
      const e = res.data.errors?.length || 0;
      setMsg({ ok: e === 0, text: `Ingested ${n} files${e > 0 ? `, ${e} errors` : ''}` });
      setSelected(new Set());
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Ingest failed' }); }
    finally { setIngesting(false); }
  };

  const toggle = (id: string) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  const selectAll = () => setSelected(new Set(files.filter(f => !f.already_synced).map(f => f.id)));

  const sty = {
    filter: { display: 'flex', gap: '0.4rem', flexWrap: 'wrap' as const, marginBottom: '0.5rem' },
    inp: { fontSize: '0.82rem', padding: '0.3rem 0.5rem', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.04)', color: 'var(--text-primary)', flex: 1, minWidth: '120px' },
  };

  return (
    <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 2L6 6.5L12 11L18 6.5L12 2Z" fill="#0061FF"/><path d="M6 6.5L0 11L6 15.5L12 11L6 6.5Z" fill="#0061FF"/><path d="M18 6.5L12 11L18 15.5L24 11L18 6.5Z" fill="#0061FF"/><path d="M6 15.5L12 20L18 15.5L12 11L6 15.5Z" fill="#0061FF"/></svg>
        <h2 style={{ margin: 0, flex: 1 }}>Dropbox</h2>
        <button className="btn" onClick={connect} disabled={connecting} style={{ padding: '0.35rem 0.8rem', fontSize: '0.8rem' }}>
          {connecting ? <Loader2 size={13} className="animate-spin" /> : <Link size={13} />}
          {connecting ? 'Authorizing...' : 'Add Account'}
        </button>
      </div>

      {!hasCreds && (
        <div style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)', marginBottom: '0.75rem', fontSize: '0.85rem', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span>No credentials configured.</span>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', cursor: 'pointer', background: 'rgba(245,158,11,0.2)', padding: '0.25rem 0.6rem', borderRadius: '6px', fontSize: '0.82rem', fontWeight: 600 }}>
            <Upload size={13} /> Upload credentials JSON
            <input type="file" accept=".json" hidden onChange={async (e) => {
              const f = e.target.files?.[0]; if (!f) return;
              const form = new FormData(); form.append('file', f);
              try { await axios.post(`${API}/dropbox/credentials/upload`, form); setHasCreds(true); setMsg({ ok: true, text: 'Credentials uploaded.' }); }
              catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Upload failed' }); }
              e.target.value = '';
            }} />
          </label>
        </div>
      )}

      <button onClick={() => setShowSetup(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', fontSize: '0.82rem', padding: '0 0 0.5rem 0', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
        <HelpCircle size={13} /> {showSetup ? 'Hide' : 'Show'} Setup Guide
      </button>

      {showSetup && (
        <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(0,97,255,0.08)', border: '1px solid rgba(0,97,255,0.2)', marginBottom: '1rem', fontSize: '0.85rem' }}>
          <strong>Dropbox App Setup:</strong>
          <ol style={{ margin: '0.5rem 0 0 1.2rem', padding: 0, lineHeight: 1.6 }}>
            <li>Go to <a href="https://www.dropbox.com/developers/apps" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Dropbox App Console</a></li>
            <li>Click <strong>Create app</strong> → <strong>Scoped access</strong> → <strong>Full Dropbox</strong></li>
            <li>Under <strong>Permissions</strong>, enable: <code>files.metadata.read</code>, <code>files.content.read</code></li>
            <li>Under <strong>Settings</strong> → <strong>OAuth 2</strong> → Add redirect URI: <code style={{ background: 'rgba(255,255,255,0.08)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>http://localhost:8000/api/dropbox/callback</code></li>
            <li>Create a JSON file with: <code>{`{"app_key": "YOUR_KEY", "app_secret": "YOUR_SECRET"}`}</code></li>
            <li>Upload it above, then click <strong>Add Account</strong></li>
          </ol>
        </div>
      )}

      {accounts.length > 0 && (
        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
          {accounts.map(a => (
            <div key={a.email} onClick={() => setActiveAccount(a.email)}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.3rem 0.7rem', borderRadius: '8px', fontSize: '0.82rem', cursor: 'pointer',
                background: activeAccount === a.email ? 'rgba(0,97,255,0.15)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${activeAccount === a.email ? 'rgba(0,97,255,0.4)' : 'rgba(255,255,255,0.08)'}` }}>
              <CheckCircle2 size={12} color="var(--success)" /> {a.email}
              <button onClick={e => { e.stopPropagation(); disconnect(a.email); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 0 0.3rem', color: 'var(--text-secondary)' }}><X size={12} /></button>
            </div>
          ))}
        </div>
      )}

      {activeAccount && (
        <div>
          <div style={sty.filter}>
            <input style={sty.inp} placeholder="Search files..." value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchFiles()} />
            <input style={{ ...sty.inp, maxWidth: '140px' }} placeholder="Path (optional)" value={path} onChange={e => setPath(e.target.value)} />
            <select style={{ ...sty.inp, maxWidth: '130px' }} value={fileType} onChange={e => setFileType(e.target.value)}>
              <option value="">All types</option>
              <option value="document">Docs</option>
              <option value="spreadsheet">Sheets</option>
              <option value="pdf">PDFs</option>
              <option value="image">Images</option>
            </select>
            <button className="btn" onClick={searchFiles} disabled={searching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}>
              {searching ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />} Search
            </button>
          </div>
          {searching && <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}><Loader2 size={16} className="animate-spin" color="var(--accent)" /> Searching Dropbox...</div>}
          {files.length > 0 && (
            <div style={{ maxHeight: '250px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '0.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', padding: '0.3rem 0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                <button onClick={selectAll} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select all</button>
                <span style={{ marginLeft: 'auto' }}>{selected.size} selected</span>
              </div>
              {files.map(f => (
                <label key={f.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.6rem', fontSize: '0.82rem', cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.03)', opacity: f.already_synced ? 0.5 : 1 }}>
                  <input type="checkbox" checked={selected.has(f.id)} onChange={() => toggle(f.id)} style={{ accentColor: 'var(--accent)' }} />
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{f.modifiedTime?.slice(0, 10)}</span>
                  {f.already_synced && <span style={{ fontSize: '0.7rem', color: 'var(--success)' }}>synced</span>}
                </label>
              ))}
            </div>
          )}
          {files.length > 0 && selected.size > 0 && (
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
