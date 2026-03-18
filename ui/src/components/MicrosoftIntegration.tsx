import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Loader2, CheckCircle2, Search, X, Download, HelpCircle, Link, Mail, CalendarDays
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
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [savingCreds, setSavingCreds] = useState(false);

  // OneDrive
  const [driveQuery, setDriveQuery] = useState('');
  const [driveType, setDriveType] = useState('');
  const [driveFiles, setDriveFiles] = useState<MsFile[]>([]);
  const [driveSelected, setDriveSelected] = useState<Set<string>>(new Set());
  const [driveSearching, setDriveSearching] = useState(false);
  const [driveIngesting, setDriveIngesting] = useState(false);
  const [drivePageTokens, setDrivePageTokens] = useState<string[]>([]);
  const [driveNextToken, setDriveNextToken] = useState('');

  // Outlook
  const [mailQuery, setMailQuery] = useState('');
  const [mailFrom, setMailFrom] = useState('');
  const [mailSubject, setMailSubject] = useState('');
  const [mailNewer, setMailNewer] = useState(7);
  const [mailMsgs, setMailMsgs] = useState<MsEmail[]>([]);
  const [mailSelected, setMailSelected] = useState<Set<string>>(new Set());
  const [mailSearching, setMailSearching] = useState(false);
  const [mailIngesting, setMailIngesting] = useState(false);
  const [mailPageTokens, setMailPageTokens] = useState<string[]>([]);
  const [mailNextToken, setMailNextToken] = useState('');

  // Calendar
  const [calEvents, setCalEvents] = useState<MsEvent[]>([]);
  const [calSelected, setCalSelected] = useState<Set<string>>(new Set());
  const [calScanning, setCalScanning] = useState(false);
  const [calIngesting, setCalIngesting] = useState(false);
  const [calPageTokens, setCalPageTokens] = useState<string[]>([]);
  const [calNextToken, setCalNextToken] = useState('');

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
  const fetchDrivePage = async (pageToken: string) => {
    if (!activeAccount) return;
    setDriveSearching(true); setMsg(null); setDriveFiles([]); setDriveSelected(new Set());
    try {
      const res = await axios.post(`${API}/microsoft/onedrive/search`, { email: activeAccount, query: driveQuery, file_type: driveType, max_results: 30, page_token: pageToken });
      setDriveFiles(res.data.files || []);
      setDriveNextToken(res.data.nextPageToken || '');
      if (res.data.files?.length === 0) setMsg({ ok: true, text: 'No files found.' });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'OneDrive search failed' }); }
    finally { setDriveSearching(false); }
  };
  const searchDrive = () => { setDrivePageTokens(['']); fetchDrivePage(''); };
  const driveNextPage = () => { if (!driveNextToken) return; setDrivePageTokens(prev => [...prev, driveNextToken]); fetchDrivePage(driveNextToken); };
  const drivePrevPage = () => { if (drivePageTokens.length <= 1) return; const t = [...drivePageTokens]; t.pop(); setDrivePageTokens(t); fetchDrivePage(t[t.length - 1]); };

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
  const fetchMailPage = async (pageToken: string) => {
    if (!activeAccount) return;
    setMailSearching(true); setMsg(null); setMailMsgs([]); setMailSelected(new Set());
    try {
      const res = await axios.post(`${API}/microsoft/outlook/search`, {
        email: activeAccount, query: mailQuery, from_filter: mailFrom,
        subject_filter: mailSubject, newer_than_days: mailNewer, max_results: 30, page_token: pageToken,
      });
      setMailMsgs(res.data.messages || []);
      setMailNextToken(res.data.nextPageToken || '');
      if (res.data.messages?.length === 0) setMsg({ ok: true, text: 'No emails found.' });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Outlook search failed' }); }
    finally { setMailSearching(false); }
  };
  const searchMail = () => { setMailPageTokens(['']); fetchMailPage(''); };
  const mailNextPage = () => { if (!mailNextToken) return; setMailPageTokens(prev => [...prev, mailNextToken]); fetchMailPage(mailNextToken); };
  const mailPrevPage = () => { if (mailPageTokens.length <= 1) return; const t = [...mailPageTokens]; t.pop(); setMailPageTokens(t); fetchMailPage(t[t.length - 1]); };

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
  const fetchCalPage = async (pageToken: string) => {
    if (!activeAccount) return;
    setCalScanning(true); setMsg(null); setCalEvents([]); setCalSelected(new Set());
    try {
      const res = await axios.post(`${API}/microsoft/calendar/scan`, { email: activeAccount, page_token: pageToken });
      setCalEvents(res.data.events || []);
      setCalNextToken(res.data.nextPageToken || '');
      const newCount = (res.data.events || []).filter((e: MsEvent) => !e.already_synced).length;
      setMsg({ ok: true, text: `Found ${res.data.total} events (${newCount} new)` });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Calendar scan failed' }); }
    finally { setCalScanning(false); }
  };
  const scanCal = () => { setCalPageTokens(['']); fetchCalPage(''); };
  const calNextPage = () => { if (!calNextToken) return; setCalPageTokens(prev => [...prev, calNextToken]); fetchCalPage(calNextToken); };
  const calPrevPage = () => { if (calPageTokens.length <= 1) return; const t = [...calPageTokens]; t.pop(); setCalPageTokens(t); fetchCalPage(t[t.length - 1]); };

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

      <button onClick={() => setShowSetup(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', fontSize: '0.82rem', padding: '0 0 0.5rem 0', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
        <HelpCircle size={13} /> {showSetup ? 'Hide' : 'Show'} Setup Guide
      </button>

      {showSetup && (
        <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(0,164,239,0.08)', border: '1px solid rgba(0,164,239,0.2)', marginBottom: '1rem', fontSize: '0.85rem' }}>
          <strong>Step 1 — Register an Azure app:</strong>
          <ol style={{ margin: '0.5rem 0 0 1.2rem', padding: 0, lineHeight: 1.7 }}>
            <li>Go to <a href="https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Azure Portal → App registrations</a> and sign in</li>
            <li>Click <strong>+ New registration</strong> at the top</li>
            <li>Enter a name (e.g. "Open Brain")</li>
            <li>
              Under <strong>Supported account types</strong>, you'll see four options. Select:<br/>
              <strong style={{ color: '#00A4EF' }}>"Accounts in any organizational directory (Any Microsoft Entra ID tenant — Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)"</strong>
              <div style={{ margin: '0.35rem 0 0 0', padding: '0.4rem 0.6rem', borderRadius: '6px', background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.25)', fontSize: '0.8rem', color: '#f59e0b' }}>
                <strong>Important:</strong> If you plan to sign in with a personal Microsoft account (@outlook.com, @hotmail.com, @live.com, etc.), you <em>must</em> pick this option.
                The other options (Single tenant, Multitenant only) will reject personal accounts with a "Tenant mismatch" error.
              </div>
            </li>
            <li>Under <strong>Redirect URI</strong>, select <strong>Web</strong> from the dropdown and enter:<br/><code style={{ background: 'rgba(255,255,255,0.08)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>http://localhost:8000/api/microsoft/callback</code></li>
            <li>Click <strong>Register</strong></li>
          </ol>

          <strong style={{ display: 'block', marginTop: '0.75rem' }}>Step 2 — Enable v2.0 tokens (required for personal accounts):</strong>
          <div style={{ margin: '0.35rem 0 0 0', padding: '0.4rem 0.6rem', borderRadius: '6px', background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.25)', fontSize: '0.8rem', color: '#f59e0b', marginBottom: '0.4rem' }}>
            <strong>Skip this step if you'll only use work/school accounts.</strong> But for personal accounts, Azure will block sign-in unless you do this first.
          </div>
          <ol style={{ margin: '0.25rem 0 0 1.2rem', padding: 0, lineHeight: 1.7 }}>
            <li>In your app's left sidebar, click <strong>Manifest</strong></li>
            <li>Find the property <code style={{ background: 'rgba(255,255,255,0.08)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>requestedAccessTokenVersion</code> — it will likely be <code>null</code> or <code>1</code></li>
            <li>Change it to <code style={{ background: 'rgba(255,255,255,0.08)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>2</code> — so it reads: <code>"requestedAccessTokenVersion": 2</code></li>
            <li>Click <strong>Save</strong> at the top</li>
          </ol>
          <p style={{ margin: '0.25rem 0 0 1.2rem', lineHeight: 1.5, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            Microsoft has two identity platform versions. v1.0 only supports work/school accounts; v2.0 supports both personal and organizational accounts.
            Without this change, selecting "personal accounts" in the account types will throw an error about access token version mismatch.
          </p>

          <strong style={{ display: 'block', marginTop: '0.75rem' }}>Step 3 — Find your Application (client) ID:</strong>
          <p style={{ margin: '0.25rem 0 0 1.2rem', lineHeight: 1.6 }}>
            Go back to <strong>Overview</strong> (top of the left sidebar). Copy the <strong>Application (client) ID</strong> shown near the top — it's a UUID like <code style={{ background: 'rgba(255,255,255,0.08)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx</code>.
          </p>

          <strong style={{ display: 'block', marginTop: '0.75rem' }}>Step 4 — Create a client secret:</strong>
          <ol style={{ margin: '0.25rem 0 0 1.2rem', padding: 0, lineHeight: 1.7 }}>
            <li>In the left sidebar, click <strong>Certificates & secrets</strong></li>
            <li>Under the <strong>Client secrets</strong> tab, click <strong>+ New client secret</strong></li>
            <li>Enter a description (e.g. "Open Brain"), pick an expiry, and click <strong>Add</strong></li>
            <li>
              Copy the <strong>Value</strong> column immediately — it's only shown once
              <div style={{ margin: '0.25rem 0 0 0', fontSize: '0.8rem', color: '#f59e0b' }}>
                <strong>Copy the "Value", not the "Secret ID".</strong> The Value is the long string you need. The Secret ID is just an internal identifier.
              </div>
            </li>
          </ol>

          <strong style={{ display: 'block', marginTop: '0.75rem' }}>Step 5 — Add API permissions:</strong>
          <ol style={{ margin: '0.25rem 0 0 1.2rem', padding: 0, lineHeight: 1.7 }}>
            <li>In the left sidebar, click <strong>API permissions</strong></li>
            <li>Click <strong>+ Add a permission</strong> → <strong>Microsoft Graph</strong> → <strong>Delegated permissions</strong></li>
            <li>Search for and check each of these: <code>User.Read</code>, <code>Files.Read</code>, <code>Mail.Read</code>, <code>Calendars.Read</code></li>
            <li>Click <strong>Add permissions</strong></li>
          </ol>

          <div style={{ margin: '0.75rem 0 0 0', padding: '0.5rem 0.6rem', borderRadius: '6px', background: 'rgba(0,164,239,0.06)', border: '1px solid rgba(0,164,239,0.15)', fontSize: '0.82rem' }}>
            <strong>Troubleshooting:</strong>
            <ul style={{ margin: '0.3rem 0 0 1rem', padding: 0, lineHeight: 1.6 }}>
              <li><strong>"Tenant mismatch"</strong> or sign-in rejected → Go to <strong>Authentication</strong> and verify the account type is set to allow personal accounts (see Step 1).</li>
              <li><strong>"Access token version" error</strong> when saving account types → You need to set <code>requestedAccessTokenVersion</code> to <code>2</code> in the Manifest first (see Step 2).</li>
              <li><strong>Changes not taking effect</strong> → Wait 60 seconds after saving settings for Azure to propagate changes.</li>
            </ul>
          </div>

          <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Then paste the Application ID and Secret Value into the fields below.</p>
        </div>
      )}

      {!hasCreds && (
        <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(0,164,239,0.06)', border: '1px solid rgba(0,164,239,0.15)', marginBottom: '0.75rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.2rem', fontWeight: 600 }}>Application (client) ID</label>
              <input value={clientId} onChange={e => setClientId(e.target.value)} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" style={{ width: '100%', fontSize: '0.82rem', padding: '0.35rem 0.5rem', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.04)', color: 'var(--text-primary)', fontFamily: 'monospace' }} />
              <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Overview → Application (client) ID</span>
            </div>
            <div style={{ flex: 1, minWidth: '200px' }}>
              <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '0.2rem', fontWeight: 600 }}>Client Secret Value</label>
              <input value={clientSecret} onChange={e => setClientSecret(e.target.value)} type="password" placeholder="Paste secret value here" style={{ width: '100%', fontSize: '0.82rem', padding: '0.35rem 0.5rem', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.04)', color: 'var(--text-primary)', fontFamily: 'monospace' }} />
              <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Certificates & secrets → Value (not Secret ID)</span>
            </div>
          </div>
          <button className="btn" disabled={savingCreds || !clientId.trim() || !clientSecret.trim()} onClick={async () => {
            setSavingCreds(true); setMsg(null);
            try {
              await axios.post(`${API}/microsoft/credentials/save`, { client_id: clientId.trim(), client_secret: clientSecret.trim() });
              setHasCreds(true); setMsg({ ok: true, text: 'Credentials saved. Click Add Account to connect.' });
            } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Save failed' }); }
            finally { setSavingCreds(false); }
          }} style={{ padding: '0.35rem 0.9rem', fontSize: '0.82rem' }}>
            {savingCreds ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
            Save Credentials
          </button>
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
              {driveFiles.length > 0 && (drivePageTokens.length > 1 || driveNextToken) && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', padding: '0.5rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <button className="btn" onClick={drivePrevPage} disabled={drivePageTokens.length <= 1 || driveSearching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: drivePageTokens.length <= 1 ? 0.4 : 1 }}>← Prev</button>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Page {drivePageTokens.length}</span>
                  <button className="btn" onClick={driveNextPage} disabled={!driveNextToken || driveSearching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: !driveNextToken ? 0.4 : 1 }}>Next →</button>
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
              {mailMsgs.length > 0 && (mailPageTokens.length > 1 || mailNextToken) && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', padding: '0.5rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <button className="btn" onClick={mailPrevPage} disabled={mailPageTokens.length <= 1 || mailSearching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: mailPageTokens.length <= 1 ? 0.4 : 1 }}>← Prev</button>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Page {mailPageTokens.length}</span>
                  <button className="btn" onClick={mailNextPage} disabled={!mailNextToken || mailSearching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: !mailNextToken ? 0.4 : 1 }}>Next →</button>
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
              {calEvents.length > 0 && (calPageTokens.length > 1 || calNextToken) && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', padding: '0.5rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <button className="btn" onClick={calPrevPage} disabled={calPageTokens.length <= 1 || calScanning} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: calPageTokens.length <= 1 ? 0.4 : 1 }}>← Prev</button>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Page {calPageTokens.length}</span>
                  <button className="btn" onClick={calNextPage} disabled={!calNextToken || calScanning} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: !calNextToken ? 0.4 : 1 }}>Next →</button>
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
