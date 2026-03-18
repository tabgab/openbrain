import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Loader2, CheckCircle2, Search, X, Download, Upload, HelpCircle, Link, Mail, CalendarDays
} from 'lucide-react';
import { API } from '../types';

interface MsAccount { email: string; name: string; connected: boolean; connected_at?: string; }
interface MsFile { id: string; name: string; size: string; modifiedTime: string; mimeType: string; already_synced: boolean; }
interface MsEmail { id: string; from: string; from_name: string; subject: string; date: string; snippet: string; already_synced: boolean; }
interface MsEvent { id: string; summary: string; start: string; end: string; location: string; is_all_day: boolean; is_recurring: boolean; already_synced: boolean; }

export default function MicrosoftIntegration() {
  const [hasCreds, setHasCreds] = useState(false);
  const [accounts, setAccounts] = useState<MsAccount[]>([]);
  const [connecting, setConnecting] = useState(false);
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'onedrive' | 'outlook' | 'calendar'>('onedrive');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [showSetup, setShowSetup] = useState(false);

  // OneDrive
  const [driveQuery, setDriveQuery] = useState('');
  const [driveType, setDriveType] = useState('');
  const [driveFiles, setDriveFiles] = useState<MsFile[]>([]);
  const [driveSelected, setDriveSelected] = useState<Set<string>>(new Set());
  const [driveSearching, setDriveSearching] = useState(false);
  const [driveIngesting, setDriveIngesting] = useState(false);

  // Outlook
  const [mailQuery, setMailQuery] = useState('');
  const [mailFrom, setMailFrom] = useState('');
  const [mailSubject, setMailSubject] = useState('');
  const [mailNewer, setMailNewer] = useState(7);
  const [mailMsgs, setMailMsgs] = useState<MsEmail[]>([]);
  const [mailSelected, setMailSelected] = useState<Set<string>>(new Set());
  const [mailSearching, setMailSearching] = useState(false);
  const [mailIngesting, setMailIngesting] = useState(false);

  // Calendar
  const [calEvents, setCalEvents] = useState<MsEvent[]>([]);
  const [calSelected, setCalSelected] = useState<Set<string>>(new Set());
  const [calScanning, setCalScanning] = useState(false);
  const [calIngesting, setCalIngesting] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/microsoft/status`);
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
      const res = await axios.post(`${API}/microsoft/connect`);
      if (res.data.auth_url) {
        if (win) win.location.href = res.data.auth_url;
        else setMsg({ ok: false, text: `Popup blocked — open: ${res.data.auth_url}` });
      }
      const poll = setInterval(async () => {
        const s = await axios.get(`${API}/microsoft/status`);
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
    await axios.post(`${API}/microsoft/disconnect`, { email });
    setAccounts(prev => prev.filter(a => a.email !== email));
    if (activeAccount === email) setActiveAccount(accounts.find(a => a.email !== email)?.email || null);
  };

  // OneDrive
  const searchDrive = async () => {
    if (!activeAccount) return;
    setDriveSearching(true); setMsg(null); setDriveFiles([]); setDriveSelected(new Set());
    try {
      const res = await axios.post(`${API}/microsoft/onedrive/search`, { email: activeAccount, query: driveQuery, file_type: driveType, max_results: 30 });
      setDriveFiles(res.data.files || []);
      if (res.data.files?.length === 0) setMsg({ ok: true, text: 'No files found.' });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'OneDrive search failed' }); }
    finally { setDriveSearching(false); }
  };

  const ingestDrive = async () => {
    if (!activeAccount || driveSelected.size === 0) return;
    setDriveIngesting(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/microsoft/onedrive/ingest`, { email: activeAccount, file_ids: Array.from(driveSelected) });
      const n = res.data.ingested?.length || 0;
      setMsg({ ok: true, text: `Ingested ${n} files from OneDrive` });
      setDriveSelected(new Set());
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Ingest failed' }); }
    finally { setDriveIngesting(false); }
  };

  // Outlook
  const searchMail = async () => {
    if (!activeAccount) return;
    setMailSearching(true); setMsg(null); setMailMsgs([]); setMailSelected(new Set());
    try {
      const res = await axios.post(`${API}/microsoft/outlook/search`, {
        email: activeAccount, query: mailQuery, from_filter: mailFrom,
        subject_filter: mailSubject, newer_than_days: mailNewer, max_results: 30,
      });
      setMailMsgs(res.data.messages || []);
      if (res.data.messages?.length === 0) setMsg({ ok: true, text: 'No emails found.' });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Outlook search failed' }); }
    finally { setMailSearching(false); }
  };

  const ingestMail = async () => {
    if (!activeAccount || mailSelected.size === 0) return;
    setMailIngesting(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/microsoft/outlook/ingest`, { email: activeAccount, message_ids: Array.from(mailSelected) });
      const n = res.data.ingested?.length || 0;
      setMsg({ ok: true, text: `Ingested ${n} emails from Outlook` });
      setMailSelected(new Set());
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Ingest failed' }); }
    finally { setMailIngesting(false); }
  };

  // Calendar
  const scanCal = async () => {
    if (!activeAccount) return;
    setCalScanning(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/microsoft/calendar/scan`, { email: activeAccount });
      setCalEvents(res.data.events || []);
      const newCount = (res.data.events || []).filter((e: MsEvent) => !e.already_synced).length;
      setMsg({ ok: true, text: `Found ${res.data.total} events (${newCount} new)` });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Calendar scan failed' }); }
    finally { setCalScanning(false); }
  };

  const ingestCal = async () => {
    if (!activeAccount || calSelected.size === 0) return;
    setCalIngesting(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/microsoft/calendar/ingest`, { email: activeAccount, event_ids: Array.from(calSelected) });
      const n = res.data.ingested?.length || 0;
      setMsg({ ok: true, text: `Ingested ${n} calendar events` });
      setCalSelected(new Set());
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Ingest failed' }); }
    finally { setCalIngesting(false); }
  };

  const toggleSet = (set: Set<string>, setFn: (s: Set<string>) => void, id: string) => {
    setFn((() => { const s = new Set(set); s.has(id) ? s.delete(id) : s.add(id); return s; })());
  };

  const formatTime = (iso: string) => {
    if (!iso || !iso.includes('T')) return 'all day';
    return iso.slice(11, 16);
  };

  const sty = {
    filter: { display: 'flex', gap: '0.4rem', flexWrap: 'wrap' as const, marginBottom: '0.5rem' },
    inp: { fontSize: '0.82rem', padding: '0.3rem 0.5rem', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.04)', color: 'var(--text-primary)', flex: 1, minWidth: '120px' },
  };

  return (
    <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <svg width="20" height="20" viewBox="0 0 24 24"><rect x="1" y="1" width="10" height="10" fill="#F25022"/><rect x="13" y="1" width="10" height="10" fill="#7FBA00"/><rect x="1" y="13" width="10" height="10" fill="#00A4EF"/><rect x="13" y="13" width="10" height="10" fill="#FFB900"/></svg>
        <h2 style={{ margin: 0, flex: 1 }}>Microsoft 365</h2>
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
              try { await axios.post(`${API}/microsoft/credentials/upload`, form); setHasCreds(true); setMsg({ ok: true, text: 'Credentials uploaded.' }); }
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
        <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(0,164,239,0.08)', border: '1px solid rgba(0,164,239,0.2)', marginBottom: '1rem', fontSize: '0.85rem' }}>
          <strong>Microsoft 365 App Setup:</strong>
          <ol style={{ margin: '0.5rem 0 0 1.2rem', padding: 0, lineHeight: 1.6 }}>
            <li>Go to <a href="https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Azure App Registrations</a></li>
            <li>Click <strong>New registration</strong> → name it (e.g. "Open Brain") → select <strong>Accounts in any organizational directory and personal Microsoft accounts</strong></li>
            <li>Under <strong>Redirect URIs</strong>, add: <code style={{ background: 'rgba(255,255,255,0.08)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>http://localhost:8000/api/microsoft/callback</code> (type: Web)</li>
            <li>Go to <strong>Certificates & secrets</strong> → <strong>New client secret</strong> → copy the <strong>Value</strong></li>
            <li>Go to <strong>API permissions</strong> → Add: <code>User.Read</code>, <code>Files.Read</code>, <code>Mail.Read</code>, <code>Calendars.Read</code> (all delegated)</li>
            <li>Create a JSON file: <code>{`{"client_id": "APP_ID", "client_secret": "SECRET_VALUE"}`}</code></li>
            <li>Upload it above, then click <strong>Add Account</strong></li>
          </ol>
        </div>
      )}

      {accounts.length > 0 && (
        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
          {accounts.map(a => (
            <div key={a.email} onClick={() => setActiveAccount(a.email)}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.3rem 0.7rem', borderRadius: '8px', fontSize: '0.82rem', cursor: 'pointer',
                background: activeAccount === a.email ? 'rgba(0,164,239,0.15)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${activeAccount === a.email ? 'rgba(0,164,239,0.4)' : 'rgba(255,255,255,0.08)'}` }}>
              <CheckCircle2 size={12} color="var(--success)" /> {a.email}
              <button onClick={e => { e.stopPropagation(); disconnect(a.email); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 0 0.3rem', color: 'var(--text-secondary)' }}><X size={12} /></button>
            </div>
          ))}
        </div>
      )}

      {activeAccount && (
        <>
          <div style={{ display: 'flex', gap: '0.3rem', marginBottom: '0.75rem' }}>
            {(['onedrive', 'outlook', 'calendar'] as const).map(t => (
              <button key={t} onClick={() => setActiveTab(t)}
                style={{ padding: '0.3rem 0.8rem', borderRadius: '6px', fontSize: '0.82rem', border: 'none', cursor: 'pointer',
                  background: activeTab === t ? 'rgba(0,164,239,0.2)' : 'transparent', color: activeTab === t ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: activeTab === t ? 600 : 400 }}>
                {t === 'onedrive' && <><Download size={13} /> OneDrive</>}
                {t === 'outlook' && <><Mail size={13} /> Outlook</>}
                {t === 'calendar' && <><CalendarDays size={13} /> Calendar</>}
              </button>
            ))}
          </div>

          {/* OneDrive */}
          {activeTab === 'onedrive' && (
            <div>
              <div style={sty.filter}>
                <input style={sty.inp} placeholder="Search files..." value={driveQuery} onChange={e => setDriveQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchDrive()} />
                <select style={{ ...sty.inp, maxWidth: '130px' }} value={driveType} onChange={e => setDriveType(e.target.value)}>
                  <option value="">All types</option><option value="document">Docs</option><option value="spreadsheet">Sheets</option><option value="pdf">PDFs</option><option value="image">Images</option>
                </select>
                <button className="btn" onClick={searchDrive} disabled={driveSearching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}>
                  {driveSearching ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />} Search
                </button>
              </div>
              {driveSearching && <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}><Loader2 size={16} className="animate-spin" color="var(--accent)" /> Searching OneDrive...</div>}
              {driveFiles.length > 0 && (
                <div style={{ maxHeight: '250px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', padding: '0.3rem 0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    <button onClick={() => setDriveSelected(new Set(driveFiles.map(f => f.id)))} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select all</button>
                    <span style={{ marginLeft: 'auto' }}>{driveSelected.size} selected</span>
                  </div>
                  {driveFiles.map(f => (
                    <label key={f.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.6rem', fontSize: '0.82rem', cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                      <input type="checkbox" checked={driveSelected.has(f.id)} onChange={() => toggleSet(driveSelected, setDriveSelected, f.id)} style={{ accentColor: 'var(--accent)' }} />
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{f.modifiedTime?.slice(0, 10)}</span>
                    </label>
                  ))}
                </div>
              )}
              {driveFiles.length > 0 && driveSelected.size > 0 && (
                <button className="btn" onClick={ingestDrive} disabled={driveIngesting} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem' }}>
                  {driveIngesting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                  Ingest {driveSelected.size} file{driveSelected.size !== 1 ? 's' : ''}
                </button>
              )}
            </div>
          )}

          {/* Outlook */}
          {activeTab === 'outlook' && (
            <div>
              <div style={sty.filter}>
                <input style={sty.inp} placeholder="Search query..." value={mailQuery} onChange={e => setMailQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchMail()} />
                <input style={{ ...sty.inp, maxWidth: '150px' }} placeholder="From" value={mailFrom} onChange={e => setMailFrom(e.target.value)} />
                <input style={{ ...sty.inp, maxWidth: '150px' }} placeholder="Subject" value={mailSubject} onChange={e => setMailSubject(e.target.value)} />
              </div>
              <div style={sty.filter}>
                <select style={{ ...sty.inp, maxWidth: '120px' }} value={mailNewer} onChange={e => setMailNewer(Number(e.target.value))}>
                  <option value={1}>Last 24h</option><option value={3}>Last 3 days</option><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={365}>Last year</option>
                </select>
                <button className="btn" onClick={searchMail} disabled={mailSearching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}>
                  {mailSearching ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />} Search
                </button>
              </div>
              {mailSearching && <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}><Loader2 size={16} className="animate-spin" color="var(--accent)" /> Searching Outlook...</div>}
              {mailMsgs.length > 0 && (
                <div style={{ maxHeight: '300px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', padding: '0.3rem 0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    <button onClick={() => setMailSelected(new Set(mailMsgs.map(m => m.id)))} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select all</button>
                    <span style={{ marginLeft: 'auto' }}>{mailSelected.size} selected</span>
                  </div>
                  {mailMsgs.map(m => (
                    <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.6rem', fontSize: '0.82rem', cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                      <input type="checkbox" checked={mailSelected.has(m.id)} onChange={() => toggleSet(mailSelected, setMailSelected, m.id)} style={{ accentColor: 'var(--accent)' }} />
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <strong style={{ fontSize: '0.8rem' }}>{m.from_name || m.from}</strong>{' '}
                        <span style={{ color: 'var(--text-secondary)' }}>{m.subject}</span>
                      </span>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{m.date?.slice(0, 10)}</span>
                    </label>
                  ))}
                </div>
              )}
              {mailMsgs.length > 0 && mailSelected.size > 0 && (
                <button className="btn" onClick={ingestMail} disabled={mailIngesting} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem' }}>
                  {mailIngesting ? <Loader2 size={13} className="animate-spin" /> : <Mail size={13} />}
                  Ingest {mailSelected.size} email{mailSelected.size !== 1 ? 's' : ''}
                </button>
              )}
            </div>
          )}

          {/* Calendar */}
          {activeTab === 'calendar' && (
            <div>
              <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.5rem' }}>
                <button className="btn" onClick={scanCal} disabled={calScanning} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}>
                  {calScanning ? <Loader2 size={13} className="animate-spin" /> : <CalendarDays size={13} />}
                  {calScanning ? 'Scanning...' : 'Scan Calendar'}
                </button>
              </div>
              {calScanning && <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}><Loader2 size={16} className="animate-spin" color="var(--accent)" /> Scanning calendar...</div>}
              {calEvents.length > 0 && (
                <div style={{ maxHeight: '300px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', padding: '0.3rem 0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    <button onClick={() => setCalSelected(new Set(calEvents.filter(e => !e.already_synced).map(e => e.id)))} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select all new</button>
                    <span style={{ marginLeft: 'auto' }}>{calSelected.size} selected</span>
                  </div>
                  {calEvents.map(ev => (
                    <label key={ev.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.6rem', fontSize: '0.82rem', cursor: 'pointer', borderBottom: '1px solid rgba(255,255,255,0.03)', opacity: ev.already_synced ? 0.5 : 1 }}>
                      <input type="checkbox" checked={calSelected.has(ev.id)} onChange={() => toggleSet(calSelected, setCalSelected, ev.id)} style={{ accentColor: 'var(--accent)' }} />
                      <div style={{ flex: 1, overflow: 'hidden' }}>
                        <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ev.summary}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                          {ev.start?.slice(0, 10)} {formatTime(ev.start)} — {formatTime(ev.end)}
                          {ev.location && ` · ${ev.location}`}
                        </div>
                      </div>
                      {ev.already_synced && <span style={{ fontSize: '0.7rem', color: 'var(--success)' }}>synced</span>}
                    </label>
                  ))}
                </div>
              )}
              {calEvents.length > 0 && calSelected.size > 0 && (
                <button className="btn" onClick={ingestCal} disabled={calIngesting} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem' }}>
                  {calIngesting ? <Loader2 size={13} className="animate-spin" /> : <CalendarDays size={13} />}
                  Ingest {calSelected.size} event{calSelected.size !== 1 ? 's' : ''}
                </button>
              )}
            </div>
          )}
        </>
      )}

      {msg && <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: msg.ok ? 'var(--success)' : 'var(--error)' }}>{msg.ok ? '✅' : '❌'} {msg.text}</div>}
    </div>
  );
}
