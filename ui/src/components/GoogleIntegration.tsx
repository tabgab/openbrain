import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Loader2, CheckCircle2, AlertCircle, Search, X, Download, Eye, HelpCircle, Upload,
  Cloud, Mail, Link, CalendarDays, ChevronLeft, ChevronRight, List, Grid3X3,
  MapPin, Clock, Repeat, ImageIcon
} from 'lucide-react';
import { API } from '../types';

// --- Google Drive, Gmail, Calendar & Photos (multi-account, search/filter/preview/ingest) ---
interface GoogleAccount { email: string; connected: boolean; connected_at?: string; drive_last_sync?: string; gmail_last_sync?: string; }
interface DriveFile { id: string; name: string; mimeType: string; modifiedTime: string; size: string; already_synced: boolean; }
interface GmailMsg { id: string; from: string; subject: string; date: string; snippet: string; already_synced: boolean; }
interface CalEvent { id: string; recurring_id: string; summary: string; start: string; end: string; location: string; description: string; calendar: string; calendar_id: string; is_recurring: boolean; occurrence_count: number; recurrence_info: string; already_synced: boolean; }
interface CalInfo { id: string; name: string; color: string; }

export default function GoogleIntegrationSection() {
  const [hasCreds, setHasCreds] = useState(false);
  const [accounts, setAccounts] = useState<GoogleAccount[]>([]);
  const [connecting, setConnecting] = useState(false);
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'drive' | 'gmail' | 'calendar' | 'photos'>('drive');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [showSetup, setShowSetup] = useState(false);

  // Drive state
  const [driveQuery, setDriveQuery] = useState('');
  const [driveFolder, setDriveFolder] = useState('');
  const [driveType, setDriveType] = useState('');
  const [driveFiles, setDriveFiles] = useState<DriveFile[]>([]);
  const [driveSelected, setDriveSelected] = useState<Set<string>>(new Set());
  const [driveSearching, setDriveSearching] = useState(false);
  const [driveIngesting, setDriveIngesting] = useState(false);

  // Gmail state
  const [gmailQuery, setGmailQuery] = useState('');
  const [gmailFrom, setGmailFrom] = useState('');
  const [gmailSubject, setGmailSubject] = useState('');
  const [gmailLabel, setGmailLabel] = useState('');
  const [gmailLabels, setGmailLabels] = useState<{ id: string; name: string; type: string }[]>([]);
  const [gmailNewer, setGmailNewer] = useState('7d');
  const [gmailMsgs, setGmailMsgs] = useState<GmailMsg[]>([]);
  const [gmailSelected, setGmailSelected] = useState<Set<string>>(new Set());
  const [gmailSearching, setGmailSearching] = useState(false);
  const [gmailPageTokens, setGmailPageTokens] = useState<string[]>([]);  // stack of previous page tokens
  const [gmailNextToken, setGmailNextToken] = useState<string>('');       // token for the next page
  const [gmailIngesting, setGmailIngesting] = useState(false);
  const [gmailIncludeImages, setGmailIncludeImages] = useState(false);
  const [gmailIngestProgress, setGmailIngestProgress] = useState<{ current: number; total: number; results: { id: string; ok: boolean; subject: string }[] } | null>(null);
  const [expandedEmail, setExpandedEmail] = useState<string | null>(null);
  const [emailPreview, setEmailPreview] = useState<{ id: string; from: string; to: string; subject: string; date: string; body: string; html_body?: string; image_count?: number } | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Calendar state
  const [calEvents, setCalEvents] = useState<CalEvent[]>([]);
  const [calSelected, setCalSelected] = useState<Set<string>>(new Set());
  const [calScanning, setCalScanning] = useState(false);
  const [calIngesting, setCalIngesting] = useState(false);
  const [calFilter, setCalFilter] = useState('');
  const [calScanInfo, setCalScanInfo] = useState<{ is_first_scan: boolean; calendars_scanned: number } | null>(null);
  const [calShowPrompt, setCalShowPrompt] = useState(false);
  const [calView, setCalView] = useState<'list' | 'week' | 'month'>('week');
  const [calViewDate, setCalViewDate] = useState(new Date());
  const [calExpandedEvent, setCalExpandedEvent] = useState<CalEvent | null>(null);
  const [calCalendars, setCalCalendars] = useState<CalInfo[]>([]);
  const [calEnabledCals, setCalEnabledCals] = useState<Set<string>>(new Set());

  // Photos state
  interface PhotoItem { id: string; baseUrl: string; mimeType: string; filename: string; width: string; height: string; creationTime: string; cameraMake: string; cameraModel: string; already_synced: boolean; }
  const [photosPolling, setPhotosPolling] = useState(false);
  const [photosItems, setPhotosItems] = useState<PhotoItem[]>([]);
  const [photosSelected, setPhotosSelected] = useState<Set<string>>(new Set());
  const [photosIngesting, setPhotosIngesting] = useState(false);
  const [photosIngestProgress, setPhotosIngestProgress] = useState<{ current: number; total: number; results: { id: string; ok: boolean; filename: string }[] } | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/google/status`);
      setHasCreds(res.data.has_credentials_file);
      setAccounts(res.data.accounts || []);
      if (!activeAccount && res.data.accounts?.length > 0) setActiveAccount(res.data.accounts[0].email);
    } catch {}
  }, [activeAccount]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // Fetch Gmail labels when account or tab changes
  useEffect(() => {
    if (!activeAccount || activeTab !== 'gmail') return;
    (async () => {
      try {
        const res = await axios.get(`${API}/google/gmail/labels`, { params: { email: activeAccount } });
        setGmailLabels(res.data.labels || []);
      } catch { setGmailLabels([]); }
    })();
  }, [activeAccount, activeTab]);

  const connect = async () => {
    setConnecting(true); setMsg(null);
    // Open window synchronously (before await) so Safari doesn't block it
    const win = window.open('about:blank', '_blank');
    try {
      const res = await axios.post(`${API}/google/connect`);
      if (res.data.auth_url) {
        if (win) {
          win.location.href = res.data.auth_url;
        } else {
          // Popup was blocked — show a clickable fallback link
          setMsg({ ok: false, text: `Popup blocked — open this link to authorize: ${res.data.auth_url}` });
        }
      }
      const poll = setInterval(async () => {
        const s = await axios.get(`${API}/google/status`);
        const accts = s.data.accounts || [];
        if (accts.length > accounts.length) {
          setAccounts(accts);
          const newest = accts[accts.length - 1];
          setActiveAccount(newest.email);
          clearInterval(poll); setConnecting(false);
          setMsg({ ok: true, text: `Connected: ${newest.email}` });
        }
      }, 3000);
      setTimeout(() => { clearInterval(poll); setConnecting(false); }, 120000);
    } catch (err: any) {
      if (win) win.close();
      setMsg({ ok: false, text: err?.response?.data?.detail || 'Failed to start OAuth' });
      setConnecting(false);
    }
  };

  const disconnectAccount = async (email: string) => {
    await axios.post(`${API}/google/disconnect`, { email });
    setAccounts(prev => prev.filter(a => a.email !== email));
    if (activeAccount === email) setActiveAccount(accounts.find(a => a.email !== email)?.email || null);
    setMsg({ ok: true, text: `Disconnected ${email}` });
  };

  // Drive search
  const searchDrive = async () => {
    if (!activeAccount) return;
    setDriveSearching(true); setMsg(null); setDriveFiles([]); setDriveSelected(new Set());
    try {
      const res = await axios.post(`${API}/google/drive/search`, {
        email: activeAccount, query: driveQuery, folder_name: driveFolder, file_type: driveType, max_results: 30,
      });
      setDriveFiles(res.data.files || []);
      if (res.data.files?.length === 0) setMsg({ ok: true, text: 'No files found matching your filters.' });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Drive search failed' }); }
    finally { setDriveSearching(false); }
  };

  const ingestDriveFiles = async () => {
    if (!activeAccount || driveSelected.size === 0) return;
    setDriveIngesting(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/google/drive/ingest`, { email: activeAccount, file_ids: Array.from(driveSelected) });
      const n = res.data.ingested?.length || 0;
      const e = res.data.errors?.length || 0;
      setMsg({ ok: e === 0, text: `Ingested ${n} files${e > 0 ? `, ${e} errors` : ''}` });
      setDriveSelected(new Set());
      searchDrive(); // refresh to show synced status
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Ingest failed' }); }
    finally { setDriveIngesting(false); }
  };

  // Gmail search (with pagination)
  // gmailPageTokens is a stack: [''] means page 1, ['', 'tok_A'] means page 2, etc.
  const fetchGmailPage = async (pageToken: string) => {
    if (!activeAccount) return;
    setGmailSearching(true); setMsg(null); setGmailMsgs([]); setGmailSelected(new Set());
    setExpandedEmail(null); setEmailPreview(null);
    try {
      const res = await axios.post(`${API}/google/gmail/search`, {
        email: activeAccount, query: gmailQuery, from_filter: gmailFrom,
        subject_filter: gmailSubject, label: gmailLabel, newer_than: gmailNewer,
        max_results: 30, page_token: pageToken,
      });
      setGmailMsgs(res.data.messages || []);
      setGmailNextToken(res.data.nextPageToken || '');
      if (res.data.messages?.length === 0) setMsg({ ok: true, text: 'No emails found matching your filters.' });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Gmail search failed' }); }
    finally { setGmailSearching(false); }
  };

  const searchGmail = () => {
    setGmailPageTokens(['']);
    fetchGmailPage('');
  };

  const gmailNextPage = () => {
    if (!gmailNextToken) return;
    setGmailPageTokens(prev => [...prev, gmailNextToken]);
    fetchGmailPage(gmailNextToken);
  };

  const gmailPrevPage = () => {
    if (gmailPageTokens.length <= 1) return;
    const prevTokens = [...gmailPageTokens];
    prevTokens.pop();
    setGmailPageTokens(prevTokens);
    fetchGmailPage(prevTokens[prevTokens.length - 1]);
  };

  const ingestGmailMsgs = async () => {
    if (!activeAccount || gmailSelected.size === 0) return;
    setGmailIngesting(true); setMsg(null);
    const ids = Array.from(gmailSelected);
    const progress: { current: number; total: number; results: { id: string; ok: boolean; subject: string }[] } = { current: 0, total: ids.length, results: [] };
    setGmailIngestProgress({ ...progress });

    for (const msgId of ids) {
      progress.current++;
      setGmailIngestProgress({ ...progress, results: [...progress.results] });
      const emailInfo = gmailMsgs.find(m => m.id === msgId);
      const subject = emailInfo?.subject || msgId.slice(0, 12);
      try {
        await axios.post(`${API}/google/gmail/ingest`, {
          email: activeAccount, message_ids: [msgId], include_images: gmailIncludeImages,
        });
        progress.results.push({ id: msgId, ok: true, subject });
        // Mark as synced in the list immediately
        setGmailMsgs(prev => prev.map(m => m.id === msgId ? { ...m, already_synced: true } : m));
      } catch {
        progress.results.push({ id: msgId, ok: false, subject });
      }
      setGmailIngestProgress({ ...progress, results: [...progress.results] });
    }

    const ok = progress.results.filter(r => r.ok).length;
    const fail = progress.results.filter(r => !r.ok).length;
    setMsg({ ok: fail === 0, text: `Ingested ${ok} of ${ids.length} emails${fail > 0 ? ` (${fail} failed)` : ''}` });
    setGmailSelected(new Set());
    setGmailIngesting(false);
    // Keep progress visible for a moment, then clear
    setTimeout(() => setGmailIngestProgress(null), 4000);
  };

  // Calendar functions
  const scanCalendar = async () => {
    if (!activeAccount) return;
    setCalScanning(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/google/calendar/scan`, { email: activeAccount });
      setCalEvents(res.data.events || []);
      const cals: CalInfo[] = res.data.calendars || [];
      setCalCalendars(cals);
      setCalEnabledCals(new Set(cals.map(c => c.id)));
      setCalScanInfo({ is_first_scan: res.data.is_first_scan, calendars_scanned: res.data.calendars_scanned });
      const newCount = (res.data.events || []).filter((e: CalEvent) => !e.already_synced).length;
      if (newCount === 0) setMsg({ ok: true, text: `Scanned ${res.data.calendars_scanned} calendars — all events already synced.` });
      else setMsg({ ok: true, text: `Found ${res.data.total} events (${newCount} new) across ${res.data.calendars_scanned} calendars.` });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Calendar scan failed' }); }
    finally { setCalScanning(false); }
  };

  const ingestCalEvents = async () => {
    if (!activeAccount || calSelected.size === 0) return;
    setCalIngesting(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/google/calendar/ingest`, { email: activeAccount, event_ids: Array.from(calSelected) });
      const n = res.data.ingested?.length || 0;
      const e = res.data.errors?.length || 0;
      setMsg({ ok: e === 0, text: `Ingested ${n} calendar events${e > 0 ? `, ${e} errors` : ''}` });
      setCalSelected(new Set());
      scanCalendar();
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Calendar ingest failed' }); }
    finally { setCalIngesting(false); }
  };

  // Photos functions
  const openPhotosPicker = async () => {
    if (!activeAccount) return;
    setMsg(null); setPhotosItems([]); setPhotosSelected(new Set()); setPhotosIngestProgress(null);
    // Open window synchronously (before await) so Safari doesn't block it
    const win = window.open('about:blank', '_blank');
    try {
      const res = await axios.post(`${API}/google/photos/create-session`, {
        email: activeAccount,
      });
      const sid = res.data.session_id;
      const pickerUri = res.data.picker_uri;
      if (pickerUri) {
        if (win) {
          win.location.href = pickerUri;
        } else {
          // Popup was blocked — show a clickable fallback link
          setMsg({ ok: false, text: `Popup blocked — open this link to pick photos: ${pickerUri}` });
        }
      }
      // Start polling
      setPhotosPolling(true);
      const poll = setInterval(async () => {
        try {
          const p = await axios.get(`${API}/google/photos/poll-session`, { params: { email: activeAccount, session_id: sid } });
          if (p.data.media_items_set) {
            clearInterval(poll);
            setPhotosPolling(false);
            // Fetch selected items
            const items = await axios.get(`${API}/google/photos/media-items`, { params: { email: activeAccount, session_id: sid } });
            setPhotosItems(items.data.items || []);
            if (items.data.items?.length === 0) setMsg({ ok: true, text: 'No photos selected in the picker.' });
          }
        } catch {
          clearInterval(poll);
          setPhotosPolling(false);
          setMsg({ ok: false, text: 'Failed to poll Photos Picker session.' });
        }
      }, 3000);
      // Timeout after 5 minutes
      setTimeout(() => { clearInterval(poll); setPhotosPolling(false); }, 300000);
    } catch (err: any) {
      if (win) win.close();
      setMsg({ ok: false, text: err?.response?.data?.detail || 'Failed to create Photos Picker session' });
    }
  };

  const togglePhoto = (id: string) => {
    const photo = photosItems.find(p => p.id === id);
    if (photo?.already_synced && !photosSelected.has(id) && !window.confirm(`"${photo.filename}" was already ingested. Re-process it?`)) return;
    setPhotosSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  };
  const selectAllNewPhotos = () => setPhotosSelected(new Set(photosItems.filter(p => !p.already_synced).map(p => p.id)));

  const ingestSelectedPhotos = async () => {
    if (!activeAccount || photosSelected.size === 0) return;
    setPhotosIngesting(true); setMsg(null);
    const selectedItems = photosItems.filter(p => photosSelected.has(p.id));
    const progress: { current: number; total: number; results: { id: string; ok: boolean; filename: string }[] } = { current: 0, total: selectedItems.length, results: [] };
    setPhotosIngestProgress({ ...progress });

    for (const item of selectedItems) {
      progress.current++;
      setPhotosIngestProgress({ ...progress, results: [...progress.results] });
      try {
        await axios.post(`${API}/google/photos/ingest`, { email: activeAccount, items: [item] });
        progress.results.push({ id: item.id, ok: true, filename: item.filename });
        setPhotosItems(prev => prev.map(p => p.id === item.id ? { ...p, already_synced: true } : p));
      } catch {
        progress.results.push({ id: item.id, ok: false, filename: item.filename });
      }
      setPhotosIngestProgress({ ...progress, results: [...progress.results] });
    }

    const ok = progress.results.filter(r => r.ok).length;
    const fail = progress.results.filter(r => !r.ok).length;
    setMsg({ ok: fail === 0, text: `Ingested ${ok} of ${selectedItems.length} photos${fail > 0 ? ` (${fail} failed)` : ''}` });
    setPhotosSelected(new Set());
    setPhotosIngesting(false);
    setTimeout(() => setPhotosIngestProgress(null), 4000);
  };

  const toggleCal = (id: string) => {
    const ev = calEvents.find(e => e.id === id);
    if (ev?.already_synced && !calSelected.has(id) && !window.confirm(`"${ev.summary}" was already ingested. Re-process it?`)) return;
    setCalSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  };
  const selectAllNewCal = () => setCalSelected(new Set(calEvents.filter(e => !e.already_synced).map(e => e.id)));

  const calendarFiltered = calEnabledCals.size > 0
    ? calEvents.filter(e => calEnabledCals.has(e.calendar_id))
    : calEvents;
  const filteredCalEvents = calFilter
    ? calendarFiltered.filter(e => e.summary.toLowerCase().includes(calFilter.toLowerCase()) || e.calendar.toLowerCase().includes(calFilter.toLowerCase()) || e.location.toLowerCase().includes(calFilter.toLowerCase()))
    : calendarFiltered;

  const toggleCalendar = (calId: string) => setCalEnabledCals(prev => {
    const s = new Set(prev); s.has(calId) ? s.delete(calId) : s.add(calId); return s;
  });

  const calColorMap = Object.fromEntries(calCalendars.map(c => [c.id, c.color]));
  const getCalColor = (ev: CalEvent) => calColorMap[ev.calendar_id] || 'var(--accent)';

  // Calendar view helpers
  const getWeekDays = (d: Date): Date[] => {
    const start = new Date(d); start.setDate(start.getDate() - start.getDay() + 1); // Monday
    return Array.from({ length: 7 }, (_, i) => { const day = new Date(start); day.setDate(start.getDate() + i); return day; });
  };
  const getMonthDays = (d: Date): Date[] => {
    const first = new Date(d.getFullYear(), d.getMonth(), 1);
    const startDay = (first.getDay() + 6) % 7; // Mon=0
    const start = new Date(first); start.setDate(1 - startDay);
    return Array.from({ length: 42 }, (_, i) => { const day = new Date(start); day.setDate(start.getDate() + i); return day; });
  };
  const fmtDateKey = (d: Date) => d.toISOString().slice(0, 10);
  const eventsForDay = (dateKey: string) => filteredCalEvents.filter(ev => {
    const evDate = ev.start?.slice(0, 10) || '';
    return evDate === dateKey;
  });
  const navigateCal = (dir: number) => {
    setCalViewDate(prev => {
      const d = new Date(prev);
      if (calView === 'week') d.setDate(d.getDate() + dir * 7);
      else d.setMonth(d.getMonth() + dir);
      return d;
    });
  };
  const isToday = (d: Date) => fmtDateKey(d) === fmtDateKey(new Date());
  const isSameMonth = (d: Date) => d.getMonth() === calViewDate.getMonth();
  const formatTime = (iso: string) => {
    if (!iso || !iso.includes('T')) return 'all day';
    return iso.slice(11, 16);
  };
  const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

  // Auto-prompt calendar scan on first load when accounts exist
  useEffect(() => {
    if (accounts.length > 0 && activeAccount && !calShowPrompt && calEvents.length === 0) {
      setCalShowPrompt(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accounts, activeAccount]);

  const toggleDrive = (id: string) => {
    const file = driveFiles.find(f => f.id === id);
    if (file?.already_synced && !driveSelected.has(id) && !window.confirm(`"${file.name}" was already ingested. Re-process it?`)) return;
    setDriveSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  };
  const toggleGmail = (id: string) => {
    const msg = gmailMsgs.find(m => m.id === id);
    if (msg?.already_synced && !gmailSelected.has(id) && !window.confirm(`"${msg.subject || id}" was already ingested. Re-process it?`)) return;
    setGmailSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  };

  const previewEmail = async (msgId: string) => {
    if (expandedEmail === msgId) { setExpandedEmail(null); setEmailPreview(null); return; }
    setExpandedEmail(msgId); setEmailPreview(null); setLoadingPreview(true);
    try {
      const res = await axios.post(`${API}/google/gmail/preview`, { email: activeAccount, message_id: msgId });
      setEmailPreview(res.data);
    } catch { setEmailPreview({ id: msgId, from: '', to: '', subject: '', date: '', body: '(failed to load preview)' }); }
    finally { setLoadingPreview(false); }
  };
  const selectAllDrive = () => setDriveSelected(new Set(driveFiles.filter(f => !f.already_synced).map(f => f.id)));
  const selectAllGmail = () => setGmailSelected(new Set(gmailMsgs.filter(m => !m.already_synced).map(m => m.id)));

  const sty = { filter: { display: 'flex', gap: '0.4rem', flexWrap: 'wrap' as const, marginBottom: '0.5rem' },
    inp: { fontSize: '0.82rem', padding: '0.3rem 0.5rem', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.04)', color: 'var(--text-primary)', flex: 1, minWidth: '120px' } };

  return (
    <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <Cloud size={20} color="var(--accent)" />
        <h2 style={{ margin: 0, flex: 1 }}>Google Drive, Gmail, Calendar & Photos</h2>
        <button className="btn" onClick={connect} disabled={connecting} style={{ padding: '0.35rem 0.8rem', fontSize: '0.8rem' }}>
          {connecting ? <Loader2 size={13} className="animate-spin" /> : <Link size={13} />}
          {connecting ? 'Authorizing...' : 'Add Account'}
        </button>
      </div>

      {hasCreds ? (
        <div style={{ padding: '0.4rem 0.75rem', borderRadius: '8px', background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.2)', marginBottom: '0.75rem', fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <CheckCircle2 size={13} color="var(--success)" />
          <span><strong>App credentials loaded</strong> — this is your OAuth app identity, shared by all accounts. Click <strong>Add Account</strong> to connect additional Google accounts.</span>
        </div>
      ) : (
        <div style={{ padding: '0.5rem 0.75rem', borderRadius: '8px', background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)', marginBottom: '0.75rem', fontSize: '0.85rem', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span>No credentials file loaded.</span>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', cursor: 'pointer', background: 'rgba(245,158,11,0.2)', padding: '0.25rem 0.6rem', borderRadius: '6px', fontSize: '0.82rem', fontWeight: 600 }}>
            <Upload size={13} /> Upload credentials JSON
            <input type="file" accept=".json,application/json" hidden onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const form = new FormData();
              form.append('file', f);
              try {
                await axios.post(`${API}/google/credentials/upload`, form);
                setHasCreds(true);
                setMsg({ ok: true, text: `Credentials uploaded (${f.name}). You can now Add Account.` });
              } catch (err: any) {
                setMsg({ ok: false, text: err?.response?.data?.detail || 'Upload failed' });
              }
              e.target.value = '';
            }} />
          </label>
          <span style={{ fontSize: '0.78rem', opacity: 0.8 }}>Download from Google Cloud Console → Clients → download icon</span>
        </div>
      )}

      <button onClick={() => setShowSetup(v => !v)}
        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', fontSize: '0.82rem', padding: '0 0 0.5rem 0', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
        <HelpCircle size={13} /> {showSetup ? 'Hide' : 'Show'} Setup Guide
      </button>

      {showSetup && (
        <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', marginBottom: '1rem', fontSize: '0.85rem' }}>
          <strong>Google OAuth Setup Guide:</strong>
          <ol style={{ margin: '0.5rem 0 0 1.2rem', padding: 0, lineHeight: 1.6 }}>
            <li>Go to <a href="https://console.cloud.google.com/" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Google Cloud Console</a> and create a project (or select an existing one)</li>
            <li>Go to <strong>APIs & Services</strong> &rarr; <strong>Library</strong>, search for and enable <strong>Google Drive API</strong>, <strong>Gmail API</strong>, <strong>Google Calendar API</strong>, and <strong>Photos Picker API</strong></li>
            <li>
              Go to <strong>Google Auth Platform</strong> (or <strong>APIs & Services</strong> &rarr; <strong>OAuth consent screen</strong>), then in the left sidebar:
              <ul style={{ margin: '0.3rem 0 0.3rem 1rem', lineHeight: 1.5 }}>
                <li>Click <strong>Branding</strong> &mdash; fill in <strong>App name</strong> (e.g. "Open Brain") and your email for support &amp; developer contact, then <strong>Save</strong></li>
                <li><strong style={{ color: '#f59e0b' }}>Click Audience</strong> &mdash; if prompted, select <strong>External</strong>. Then under <strong>Test users</strong>, click <strong>+ Add users</strong></li>
                <li><strong style={{ color: '#f59e0b' }}>Add every Google email you want to connect</strong> (personal Gmail, work Gmail, etc.) and <strong>Save</strong></li>
              </ul>
              <span style={{ fontSize: '0.78rem', color: '#f59e0b' }}>Without adding test users you will get "403: access_denied" when signing in.</span>
            </li>
            <li>
              In the left sidebar, click <strong>Clients</strong> &rarr; <strong>+ Create Client</strong> (or go to <strong>Credentials</strong> &rarr; <strong>+ Create Credentials</strong> &rarr; <strong>OAuth client ID</strong>)
              <ul style={{ margin: '0.3rem 0 0.3rem 1rem', lineHeight: 1.5 }}>
                <li>Application type: <strong>Web application</strong></li>
                <li>Name: e.g. "Open Brain"</li>
                <li>Under <strong>Authorized redirect URIs</strong>, click <strong>+ Add URI</strong></li>
                <li>Paste exactly: <code style={{ background: 'rgba(255,255,255,0.08)', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>http://localhost:8000/api/google/callback</code></li>
                <li>Click <strong>Create</strong></li>
              </ul>
            </li>
            <li>Click <strong>Download JSON</strong> (or use the download icon next to the client) &mdash; then use the <strong>Upload credentials JSON</strong> button above to upload it (any filename works)</li>
            <li>Click <strong>Add Account</strong> above to connect your first Google account</li>
          </ol>
          <div style={{ marginTop: '0.5rem', padding: '0.5rem', borderRadius: '6px', background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.15)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            <strong>Note:</strong> One <code>google_credentials.json</code> works for all your Google accounts. It identifies the app, not the user. Each account you connect gets its own separate token. To add more accounts, just make sure each email is listed as a test user in the consent screen.
          </div>
        </div>
      )}

      {/* Account list */}
      {accounts.length > 0 && (
        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
          {accounts.map(a => (
            <div key={a.email} onClick={() => setActiveAccount(a.email)}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.3rem 0.7rem', borderRadius: '8px', fontSize: '0.82rem', cursor: 'pointer',
                background: activeAccount === a.email ? 'rgba(59,130,246,0.15)' : 'rgba(255,255,255,0.04)',
                border: `1px solid ${activeAccount === a.email ? 'rgba(59,130,246,0.4)' : 'rgba(255,255,255,0.08)'}` }}>
              <CheckCircle2 size={12} color={a.connected ? 'var(--success)' : 'var(--error)'} />
              {a.email}
              <button onClick={e => { e.stopPropagation(); disconnectAccount(a.email); }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0 0 0 0.3rem', color: 'var(--text-secondary)' }}>
                <X size={12} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Calendar scan prompt (on startup) */}
      {calShowPrompt && accounts.length > 0 && calEvents.length === 0 && !calScanning && (
        <div style={{ padding: '0.6rem 0.75rem', borderRadius: '8px', background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.2)', marginBottom: '0.75rem', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
          <CalendarDays size={16} color="var(--accent)" />
          <span>Would you like to scan your Google calendars for new events?</span>
          <button className="btn" onClick={() => { setActiveTab('calendar'); scanCalendar(); setCalShowPrompt(false); }} style={{ padding: '0.25rem 0.7rem', fontSize: '0.8rem' }}>
            <CalendarDays size={12} /> Scan Calendars
          </button>
          <button className="btn btn-secondary" onClick={() => setCalShowPrompt(false)} style={{ padding: '0.25rem 0.6rem', fontSize: '0.8rem' }}>
            Dismiss
          </button>
        </div>
      )}

      {/* Drive / Gmail / Calendar tabs */}
      {activeAccount && (
        <>
          <div style={{ display: 'flex', gap: '0.3rem', marginBottom: '0.75rem' }}>
            {(['drive', 'gmail', 'calendar', 'photos'] as const).map(t => (
              <button key={t} onClick={() => setActiveTab(t)}
                style={{ padding: '0.3rem 0.8rem', borderRadius: '6px', fontSize: '0.82rem', border: 'none', cursor: 'pointer',
                  background: activeTab === t ? 'rgba(59,130,246,0.2)' : 'transparent', color: activeTab === t ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: activeTab === t ? 600 : 400 }}>
                {t === 'drive' && <><Cloud size={13} /> Drive</>}
                {t === 'gmail' && <><Mail size={13} /> Gmail</>}
                {t === 'calendar' && <><CalendarDays size={13} /> Calendar</>}
                {t === 'photos' && <><ImageIcon size={13} /> Photos</>}
              </button>
            ))}
          </div>

          {/* DRIVE TAB */}
          {activeTab === 'drive' && (
            <div>
              <div style={sty.filter}>
                <input style={sty.inp} placeholder="Search file name..." value={driveQuery} onChange={e => setDriveQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchDrive()} />
                <input style={{ ...sty.inp, maxWidth: '140px' }} placeholder="Folder name" value={driveFolder} onChange={e => setDriveFolder(e.target.value)} />
                <select style={{ ...sty.inp, maxWidth: '130px' }} value={driveType} onChange={e => setDriveType(e.target.value)}>
                  <option value="">All types</option>
                  <option value="document">Docs</option>
                  <option value="spreadsheet">Sheets</option>
                  <option value="pdf">PDFs</option>
                  <option value="image">Images</option>
                </select>
                <button className="btn" onClick={searchDrive} disabled={driveSearching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}>
                  {driveSearching ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />} Search
                </button>
              </div>
              {driveSearching && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  <Loader2 size={16} className="animate-spin" color="var(--accent)" /> Searching Google Drive...
                </div>
              )}
              {driveFiles.length > 0 && (
                <div style={{ maxHeight: '250px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', padding: '0.3rem 0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    <button onClick={selectAllDrive} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select all new</button>
                    <span style={{ marginLeft: 'auto' }}>{driveSelected.size} selected</span>
                  </div>
                  {driveFiles.map(f => (
                    <label key={f.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.6rem', fontSize: '0.82rem', cursor: 'pointer',
                      borderBottom: '1px solid rgba(255,255,255,0.03)', opacity: f.already_synced ? 0.5 : 1 }}>
                      <input type="checkbox" checked={driveSelected.has(f.id)} onChange={() => toggleDrive(f.id)} style={{ accentColor: 'var(--accent)' }} />
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{f.modifiedTime?.slice(0, 10)}</span>
                      {f.already_synced && <span style={{ fontSize: '0.7rem', color: 'var(--success)' }}>synced</span>}
                    </label>
                  ))}
                </div>
              )}
              {driveFiles.length > 0 && driveSelected.size > 0 && (
                <button className="btn" onClick={ingestDriveFiles} disabled={driveIngesting} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem' }}>
                  {driveIngesting ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                  Ingest {driveSelected.size} file{driveSelected.size !== 1 ? 's' : ''}
                </button>
              )}
            </div>
          )}

          {/* GMAIL TAB */}
          {activeTab === 'gmail' && (
            <div>
              <div style={sty.filter}>
                <input style={sty.inp} placeholder="Search query..." value={gmailQuery} onChange={e => setGmailQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && searchGmail()} />
                <input style={{ ...sty.inp, maxWidth: '150px' }} placeholder="From (sender)" value={gmailFrom} onChange={e => setGmailFrom(e.target.value)} />
                <input style={{ ...sty.inp, maxWidth: '150px' }} placeholder="Subject contains" value={gmailSubject} onChange={e => setGmailSubject(e.target.value)} />
              </div>
              <div style={sty.filter}>
                <select style={{ ...sty.inp, maxWidth: '160px' }} value={gmailLabel} onChange={e => setGmailLabel(e.target.value)}>
                  <option value="">All labels</option>
                  {gmailLabels.filter(l => l.type === 'system').map(l => (
                    <option key={l.id} value={l.id}>{l.name}</option>
                  ))}
                  {gmailLabels.some(l => l.type === 'user') && (
                    <optgroup label="Custom Labels">
                      {gmailLabels.filter(l => l.type === 'user').map(l => (
                        <option key={l.id} value={l.id}>{l.name}</option>
                      ))}
                    </optgroup>
                  )}
                </select>
                <select style={{ ...sty.inp, maxWidth: '120px' }} value={gmailNewer} onChange={e => setGmailNewer(e.target.value)}>
                  <option value="1d">Last 24h</option>
                  <option value="3d">Last 3 days</option>
                  <option value="7d">Last 7 days</option>
                  <option value="30d">Last 30 days</option>
                  <option value="90d">Last 90 days</option>
                  <option value="1y">Last year</option>
                </select>
                <button className="btn" onClick={searchGmail} disabled={gmailSearching} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}>
                  {gmailSearching ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />} Search
                </button>
              </div>
              {gmailSearching && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  <Loader2 size={16} className="animate-spin" color="var(--accent)" /> Searching Gmail...
                </div>
              )}
              {gmailMsgs.length > 0 && (
                <div style={{ maxHeight: '400px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', padding: '0.3rem 0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    <button onClick={selectAllGmail} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select all new</button>
                    <span style={{ marginLeft: 'auto' }}>{gmailSelected.size} selected</span>
                  </div>
                  {gmailMsgs.map(m => (
                    <div key={m.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', opacity: m.already_synced ? 0.5 : 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.6rem', fontSize: '0.82rem', cursor: 'pointer' }}>
                        <input type="checkbox" checked={gmailSelected.has(m.id)} onChange={() => toggleGmail(m.id)} style={{ accentColor: 'var(--accent)' }} onClick={e => e.stopPropagation()} />
                        <span onClick={() => previewEmail(m.id)} style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer' }}>
                          <strong style={{ fontSize: '0.8rem' }}>{m.from?.split('<')[0]?.trim()}</strong>{' '}
                          <span style={{ color: 'var(--text-secondary)' }}>{m.subject}</span>
                        </span>
                        <button onClick={() => previewEmail(m.id)} title="Preview email"
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.1rem', color: expandedEmail === m.id ? 'var(--accent)' : 'var(--text-secondary)' }}>
                          <Eye size={13} />
                        </button>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{m.date?.slice(0, 16)}</span>
                        {m.already_synced && <span style={{ fontSize: '0.7rem', color: 'var(--success)' }}>synced</span>}
                      </div>
                      {expandedEmail === m.id && (
                        <div style={{ padding: '0.5rem 0.6rem 0.6rem 2rem', fontSize: '0.8rem', background: 'rgba(59,130,246,0.04)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                          {loadingPreview ? (
                            <span style={{ color: 'var(--text-secondary)' }}><Loader2 size={12} className="animate-spin" style={{ display: 'inline' }} /> Loading preview...</span>
                          ) : emailPreview ? (
                            <div>
                              <div style={{ marginBottom: '0.3rem', color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
                                <strong>From:</strong> {emailPreview.from}<br />
                                {emailPreview.to && <><strong>To:</strong> {emailPreview.to}<br /></>}
                                <strong>Date:</strong> {emailPreview.date}
                                {(emailPreview.image_count ?? 0) > 0 && <><br /><strong>Images:</strong> {emailPreview.image_count} attachment{emailPreview.image_count !== 1 ? 's' : ''}</>}
                              </div>
                              {emailPreview.html_body ? (
                                <iframe
                                  sandbox="allow-same-origin"
                                  title="Email preview"
                                  srcDoc={emailPreview.html_body}
                                  style={{ width: '100%', height: '300px', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '6px', background: '#fff', marginTop: '0.3rem' }}
                                />
                              ) : (
                                <div style={{ whiteSpace: 'pre-wrap', maxHeight: '200px', overflowY: 'auto', lineHeight: 1.4, color: 'var(--text-primary)', padding: '0.3rem 0', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                                  {emailPreview.body}
                                </div>
                              )}
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {gmailMsgs.length > 0 && (gmailPageTokens.length > 1 || gmailNextToken) && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', padding: '0.5rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <button
                    className="btn"
                    onClick={gmailPrevPage}
                    disabled={gmailPageTokens.length <= 1 || gmailSearching}
                    style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: gmailPageTokens.length <= 1 ? 0.4 : 1 }}
                  >
                    ← Prev
                  </button>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    Page {gmailPageTokens.length}
                  </span>
                  <button
                    className="btn"
                    onClick={gmailNextPage}
                    disabled={!gmailNextToken || gmailSearching}
                    style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem', opacity: !gmailNextToken ? 0.4 : 1 }}
                  >
                    Next →
                  </button>
                </div>
              )}
              {gmailMsgs.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem', flexWrap: 'wrap', padding: '0.5rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.82rem', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                    <input type="checkbox" checked={gmailIncludeImages} onChange={e => setGmailIncludeImages(e.target.checked)} style={{ accentColor: 'var(--accent)' }} />
                    Include images (vision OCR)
                  </label>
                  <button className="btn" onClick={ingestGmailMsgs} disabled={gmailIngesting || gmailSelected.size === 0} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem', opacity: gmailSelected.size === 0 ? 0.5 : 1 }}>
                    {gmailIngesting ? <Loader2 size={13} className="animate-spin" /> : <Mail size={13} />}
                    {gmailSelected.size > 0
                      ? `Ingest ${gmailSelected.size} email${gmailSelected.size !== 1 ? 's' : ''}${gmailIncludeImages ? ' + images' : ''}`
                      : 'Select emails to ingest'}
                  </button>
                </div>
              )}
              {/* Live ingestion progress */}
              {gmailIngestProgress && (
                <div style={{ padding: '0.75rem', borderRadius: '8px', border: '1px solid rgba(59,130,246,0.2)', background: 'rgba(59,130,246,0.05)', marginTop: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', fontSize: '0.85rem', fontWeight: 600 }}>
                    {gmailIngesting ? <Loader2 size={14} className="animate-spin" color="var(--accent)" /> : <CheckCircle2 size={14} color="var(--success)" />}
                    <span>{gmailIngesting ? `Ingesting ${gmailIngestProgress.current} of ${gmailIngestProgress.total}...` : `Done — ${gmailIngestProgress.results.filter(r => r.ok).length} of ${gmailIngestProgress.total} ingested`}</span>
                  </div>
                  {/* Progress bar */}
                  <div style={{ height: '4px', borderRadius: '2px', background: 'rgba(255,255,255,0.08)', marginBottom: '0.5rem', overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: '2px', background: 'var(--accent)', transition: 'width 0.3s ease', width: `${(gmailIngestProgress.results.length / gmailIngestProgress.total) * 100}%` }} />
                  </div>
                  {/* Per-email results */}
                  <div style={{ maxHeight: '150px', overflowY: 'auto', fontSize: '0.78rem' }}>
                    {gmailIngestProgress.results.map((r, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.15rem 0', color: r.ok ? 'var(--text-secondary)' : 'var(--error)' }}>
                        {r.ok ? <CheckCircle2 size={11} color="var(--success)" /> : <AlertCircle size={11} color="var(--error)" />}
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.subject}</span>
                      </div>
                    ))}
                    {/* Show which email is currently being processed */}
                    {gmailIngesting && gmailIngestProgress.current <= gmailIngestProgress.total && gmailIngestProgress.results.length < gmailIngestProgress.current && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.15rem 0', color: 'var(--accent)' }}>
                        <Loader2 size={11} className="animate-spin" />
                        <span>Processing...</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* CALENDAR TAB */}
          {activeTab === 'calendar' && (
            <div>
              {/* Top bar: scan + view toggle + navigation */}
              <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginBottom: '0.5rem', alignItems: 'center' }}>
                <button className="btn" onClick={scanCalendar} disabled={calScanning} style={{ padding: '0.3rem 0.7rem', fontSize: '0.8rem' }}>
                  {calScanning ? <Loader2 size={13} className="animate-spin" /> : <CalendarDays size={13} />}
                  {calScanning ? 'Scanning...' : 'Scan Calendars'}
                </button>
                {calScanInfo && (
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    {calScanInfo.calendars_scanned} cal{calScanInfo.calendars_scanned !== 1 ? 's' : ''}
                    {calScanInfo.is_first_scan ? ' · first scan (12 mo)' : ' · current month'}
                  </span>
                )}
                <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.2rem', alignItems: 'center' }}>
                  {(['list', 'week', 'month'] as const).map(v => (
                    <button key={v} onClick={() => setCalView(v)}
                      style={{ padding: '0.2rem 0.5rem', borderRadius: '5px', fontSize: '0.75rem', border: 'none', cursor: 'pointer',
                        background: calView === v ? 'rgba(59,130,246,0.2)' : 'transparent', color: calView === v ? 'var(--accent)' : 'var(--text-secondary)' }}>
                      {v === 'list' && <List size={12} />}
                      {v === 'week' && <CalendarDays size={12} />}
                      {v === 'month' && <Grid3X3 size={12} />}
                      {' '}{v.charAt(0).toUpperCase() + v.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Calendar toggle chips */}
              {calCalendars.length > 0 && (
                <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                  {calCalendars.map(cal => {
                    const enabled = calEnabledCals.has(cal.id);
                    const count = calEvents.filter(e => e.calendar_id === cal.id).length;
                    return (
                      <button key={cal.id} onClick={() => toggleCalendar(cal.id)}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', padding: '0.2rem 0.55rem', borderRadius: '12px', fontSize: '0.72rem',
                          border: `1px solid ${enabled ? cal.color : 'rgba(255,255,255,0.1)'}`,
                          background: enabled ? `${cal.color}18` : 'transparent',
                          color: enabled ? 'var(--text-primary)' : 'var(--text-secondary)',
                          opacity: enabled ? 1 : 0.5, cursor: 'pointer', transition: 'all 0.15s' }}>
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: cal.color, display: 'inline-block', opacity: enabled ? 1 : 0.3 }} />
                        {cal.name}
                        <span style={{ fontSize: '0.65rem', color: 'var(--text-secondary)' }}>({count})</span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Navigation bar for week/month views */}
              {calView !== 'list' && calEvents.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                  <button onClick={() => navigateCal(-1)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', padding: '0.2rem' }}><ChevronLeft size={16} /></button>
                  <span style={{ fontSize: '0.85rem', fontWeight: 600, minWidth: '160px', textAlign: 'center' }}>
                    {calView === 'week'
                      ? (() => { const days = getWeekDays(calViewDate); return `${days[0].toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} — ${days[6].toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`; })()
                      : `${MONTH_NAMES[calViewDate.getMonth()]} ${calViewDate.getFullYear()}`}
                  </span>
                  <button onClick={() => navigateCal(1)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', padding: '0.2rem' }}><ChevronRight size={16} /></button>
                  <button onClick={() => setCalViewDate(new Date())} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', fontSize: '0.75rem', padding: '0.15rem 0.4rem', borderRadius: '4px' }}>Today</button>
                  <input style={{ ...sty.inp, maxWidth: '200px', marginLeft: 'auto' }} placeholder="Filter..." value={calFilter} onChange={e => setCalFilter(e.target.value)} />
                </div>
              )}

              {calScanning && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  <Loader2 size={16} className="animate-spin" color="var(--accent)" /> Scanning calendars...
                </div>
              )}

              {calEvents.length > 0 && (
                <>
                  {/* LIST VIEW */}
                  {calView === 'list' && (
                    <>
                      <div style={sty.filter}>
                        <input style={sty.inp} placeholder="Filter events by name, calendar, or location..." value={calFilter} onChange={e => setCalFilter(e.target.value)} />
                      </div>
                      <div style={{ maxHeight: '400px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '0.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', padding: '0.3rem 0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                          <button onClick={selectAllNewCal} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select all new</button>
                          <span style={{ marginLeft: 'auto' }}>{calSelected.size} selected · {filteredCalEvents.length} shown</span>
                        </div>
                        {filteredCalEvents.map(ev => (
                          <div key={ev.id} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', padding: '0.4rem 0.6rem', fontSize: '0.82rem',
                            borderBottom: '1px solid rgba(255,255,255,0.03)', opacity: ev.already_synced ? 0.5 : 1 }}>
                            <input type="checkbox" checked={calSelected.has(ev.id)} onChange={() => toggleCal(ev.id)} style={{ accentColor: 'var(--accent)', marginTop: '0.15rem', cursor: 'pointer' }} />
                            <div style={{ flex: 1, minWidth: 0, cursor: 'pointer' }} onClick={() => setCalExpandedEvent(calExpandedEvent?.id === ev.id ? null : ev)}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ev.summary}</span>
                                {ev.is_recurring && (
                                  <span style={{ fontSize: '0.7rem', padding: '0.1rem 0.4rem', borderRadius: '4px', background: 'rgba(139,92,246,0.15)', color: '#a78bfa', whiteSpace: 'nowrap' }}>
                                    <Repeat size={9} /> {ev.recurrence_info || `×${ev.occurrence_count}`}
                                  </span>
                                )}
                                {ev.already_synced && <span style={{ fontSize: '0.68rem', padding: '0.1rem 0.4rem', borderRadius: '4px', background: 'rgba(34,197,94,0.12)', color: 'var(--success)', whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: '0.2rem' }}><CheckCircle2 size={9} /> In Brain</span>}
                              </div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.1rem' }}>
                                <Clock size={10} /> {ev.start?.slice(0, 16).replace('T', ' ')}
                                {ev.location && <> · <MapPin size={10} /> {ev.location}</>}
                                {ev.calendar && <> · <em>{ev.calendar}</em></>}
                              </div>
                              {calExpandedEvent?.id === ev.id && (
                                <div style={{ marginTop: '0.4rem', padding: '0.5rem', borderRadius: '6px', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', fontSize: '0.8rem' }}>
                                  <div style={{ marginBottom: '0.3rem' }}><strong>Time:</strong> {formatTime(ev.start)} — {formatTime(ev.end)}</div>
                                  {ev.location && <div style={{ marginBottom: '0.3rem' }}><MapPin size={11} /> {ev.location}</div>}
                                  {ev.calendar && <div style={{ marginBottom: '0.3rem' }}><CalendarDays size={11} /> {ev.calendar}</div>}
                                  {ev.is_recurring && <div style={{ marginBottom: '0.3rem' }}><Repeat size={11} /> {ev.recurrence_info || `Repeating (${ev.occurrence_count} occurrences)`}</div>}
                                  {ev.description && <div style={{ marginTop: '0.3rem', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', maxHeight: '120px', overflowY: 'auto', lineHeight: 1.4 }}>{ev.description}</div>}
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </>
                  )}

                  {/* WEEK VIEW */}
                  {calView === 'week' && (() => {
                    const days = getWeekDays(calViewDate);
                    return (
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '1px', background: 'rgba(255,255,255,0.06)', borderRadius: '8px', overflow: 'hidden', marginBottom: '0.5rem' }}>
                        {days.map((day, i) => {
                          const key = fmtDateKey(day);
                          const dayEvents = eventsForDay(key);
                          const today = isToday(day);
                          return (
                            <div key={key} style={{ background: 'var(--card-bg, rgba(0,0,0,0.3))', minHeight: '140px', padding: '0.3rem', display: 'flex', flexDirection: 'column' }}>
                              <div style={{ fontSize: '0.72rem', fontWeight: 600, textAlign: 'center', marginBottom: '0.3rem', color: today ? 'var(--accent)' : 'var(--text-secondary)' }}>
                                <div>{DAY_NAMES[i]}</div>
                                <div style={{ fontSize: '1rem', width: '1.6rem', height: '1.6rem', lineHeight: '1.6rem', borderRadius: '50%', margin: '0.1rem auto',
                                  background: today ? 'var(--accent)' : 'transparent', color: today ? '#fff' : 'var(--text-primary)' }}>
                                  {day.getDate()}
                                </div>
                              </div>
                              <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                {dayEvents.map(ev => (
                                  <div key={ev.id} onClick={() => setCalExpandedEvent(calExpandedEvent?.id === ev.id ? null : ev)}
                                    style={{ padding: '0.15rem 0.25rem', borderRadius: '3px', fontSize: '0.68rem', cursor: 'pointer', lineHeight: 1.3,
                                      background: ev.already_synced ? 'rgba(34,197,94,0.1)' : calSelected.has(ev.id) ? 'rgba(59,130,246,0.2)' : `${getCalColor(ev)}18`,
                                      borderLeft: `2px solid ${ev.already_synced ? 'var(--success)' : getCalColor(ev)}`,
                                      opacity: ev.already_synced ? 0.6 : 1 }}>
                                    <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ev.already_synced && '✓ '}{ev.summary}</div>
                                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.62rem' }}>
                                      {formatTime(ev.start)}{ev.is_recurring && ' ↻'}{ev.already_synced && ' · in brain'}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}

                  {/* MONTH VIEW */}
                  {calView === 'month' && (() => {
                    const days = getMonthDays(calViewDate);
                    return (
                      <>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '0', marginBottom: '1px' }}>
                          {DAY_NAMES.map(d => (
                            <div key={d} style={{ textAlign: 'center', fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-secondary)', padding: '0.2rem 0' }}>{d}</div>
                          ))}
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '1px', background: 'rgba(255,255,255,0.04)', borderRadius: '8px', overflow: 'hidden', marginBottom: '0.5rem' }}>
                          {days.map(day => {
                            const key = fmtDateKey(day);
                            const dayEvents = eventsForDay(key);
                            const today = isToday(day);
                            const inMonth = isSameMonth(day);
                            return (
                              <div key={key} style={{ background: 'var(--card-bg, rgba(0,0,0,0.3))', minHeight: '70px', padding: '0.2rem', opacity: inMonth ? 1 : 0.35 }}>
                                <div style={{ fontSize: '0.68rem', fontWeight: today ? 700 : 400, textAlign: 'right', padding: '0 0.15rem',
                                  color: today ? 'var(--accent)' : 'var(--text-secondary)' }}>
                                  {day.getDate()}
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
                                  {dayEvents.slice(0, 3).map(ev => (
                                    <div key={ev.id} onClick={() => setCalExpandedEvent(calExpandedEvent?.id === ev.id ? null : ev)}
                                      style={{ padding: '0.05rem 0.2rem', borderRadius: '2px', fontSize: '0.6rem', cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                        background: ev.already_synced ? 'rgba(34,197,94,0.1)' : calSelected.has(ev.id) ? 'rgba(59,130,246,0.2)' : `${getCalColor(ev)}18`,
                                        borderLeft: `2px solid ${ev.already_synced ? 'var(--success)' : getCalColor(ev)}` }}>
                                      {ev.already_synced ? '✓ ' : ''}{ev.summary}
                                    </div>
                                  ))}
                                  {dayEvents.length > 3 && (
                                    <div style={{ fontSize: '0.58rem', color: 'var(--text-secondary)', textAlign: 'center' }}>+{dayEvents.length - 3} more</div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </>
                    );
                  })()}

                  {/* Expanded event preview panel */}
                  {calExpandedEvent && (
                    <div style={{ padding: '0.6rem 0.75rem', borderRadius: '8px', background: calExpandedEvent.already_synced ? 'rgba(34,197,94,0.05)' : 'rgba(59,130,246,0.04)', border: `1px solid ${calExpandedEvent.already_synced ? 'rgba(34,197,94,0.25)' : 'rgba(59,130,246,0.15)'}`, marginBottom: '0.5rem', fontSize: '0.82rem' }}>
                      {calExpandedEvent.already_synced && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', marginBottom: '0.4rem', padding: '0.3rem 0.5rem', borderRadius: '6px', background: 'rgba(34,197,94,0.1)', color: 'var(--success)', fontSize: '0.78rem', fontWeight: 600 }}>
                          <CheckCircle2 size={14} /> Already ingested into Open Brain
                        </div>
                      )}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 700, fontSize: '0.95rem', marginBottom: '0.3rem' }}>{calExpandedEvent.summary}</div>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                            <div><Clock size={12} /> {calExpandedEvent.start?.slice(0, 16).replace('T', ' ')} — {formatTime(calExpandedEvent.end)}</div>
                            {calExpandedEvent.location && <div><MapPin size={12} /> {calExpandedEvent.location}</div>}
                            <div><CalendarDays size={12} /> {calExpandedEvent.calendar}</div>
                            {calExpandedEvent.is_recurring && <div><Repeat size={12} /> {calExpandedEvent.recurrence_info || `Repeating (${calExpandedEvent.occurrence_count} occurrences)`}</div>}
                          </div>
                          {calExpandedEvent.description && (
                            <div style={{ marginTop: '0.4rem', padding: '0.4rem', borderRadius: '6px', background: 'rgba(255,255,255,0.03)', whiteSpace: 'pre-wrap', maxHeight: '120px', overflowY: 'auto', lineHeight: 1.4, fontSize: '0.78rem' }}>
                              {calExpandedEvent.description}
                            </div>
                          )}
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', alignItems: 'flex-end' }}>
                          <button onClick={() => setCalExpandedEvent(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}><X size={14} /></button>
                          {!calExpandedEvent.already_synced && (
                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.75rem', cursor: 'pointer' }}>
                              <input type="checkbox" checked={calSelected.has(calExpandedEvent.id)} onChange={() => toggleCal(calExpandedEvent.id)} style={{ accentColor: 'var(--accent)' }} />
                              Select
                            </label>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Ingest bar */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem', flexWrap: 'wrap', padding: '0.5rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <button onClick={selectAllNewCal} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0 }}>Select all new</button>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{calSelected.size} selected</span>
                    <button className="btn" onClick={ingestCalEvents} disabled={calIngesting || calSelected.size === 0} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem', opacity: calSelected.size === 0 ? 0.5 : 1 }}>
                      {calIngesting ? <Loader2 size={13} className="animate-spin" /> : <CalendarDays size={13} />}
                      {calSelected.size > 0
                        ? ` Ingest ${calSelected.size} event${calSelected.size !== 1 ? 's' : ''}`
                        : ' Select events to ingest'}
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* PHOTOS TAB */}
          {activeTab === 'photos' && (
            <div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                <button className="btn" onClick={openPhotosPicker} disabled={photosPolling} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem' }}>
                  {photosPolling ? <Loader2 size={13} className="animate-spin" /> : <ImageIcon size={13} />}
                  {photosPolling ? ' Waiting for selection...' : ' Pick Photos'}
                </button>
                {photosPolling && (
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    Select photos in the Google picker window, then close it when done.
                  </span>
                )}
              </div>

              {photosItems.length > 0 && (
                <div style={{ maxHeight: '350px', overflowY: 'auto', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', padding: '0.3rem 0.6rem', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    <button onClick={selectAllNewPhotos} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '0.78rem', padding: 0, marginRight: '0.5rem' }}>Select all new</button>
                    <span style={{ marginLeft: 'auto' }}>{photosSelected.size} selected</span>
                  </div>
                  {photosItems.map(p => (
                    <label key={p.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.35rem 0.6rem', fontSize: '0.82rem', cursor: 'pointer',
                      borderBottom: '1px solid rgba(255,255,255,0.03)', opacity: p.already_synced ? 0.5 : 1 }}>
                      <input type="checkbox" checked={photosSelected.has(p.id)} onChange={() => togglePhoto(p.id)} style={{ accentColor: 'var(--accent)' }} />
                      <div style={{ width: 36, height: 36, borderRadius: '4px', background: 'rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <ImageIcon size={16} color="var(--text-secondary)" />
                      </div>
                      <div style={{ flex: 1, overflow: 'hidden' }}>
                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500 }}>{p.filename}</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                          {p.width && p.height ? `${p.width}×${p.height}` : ''}{p.cameraMake || p.cameraModel ? ` · ${[p.cameraMake, p.cameraModel].filter(Boolean).join(' ')}` : ''}
                        </div>
                      </div>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
                        {p.creationTime ? new Date(p.creationTime).toLocaleDateString() : ''}
                      </span>
                      {p.already_synced && <span style={{ fontSize: '0.7rem', color: 'var(--success)' }}>synced</span>}
                    </label>
                  ))}
                </div>
              )}

              {photosItems.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem', flexWrap: 'wrap', padding: '0.5rem 0', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <button className="btn" onClick={ingestSelectedPhotos} disabled={photosIngesting || photosSelected.size === 0} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem', opacity: photosSelected.size === 0 ? 0.5 : 1 }}>
                    {photosIngesting ? <Loader2 size={13} className="animate-spin" /> : <ImageIcon size={13} />}
                    {photosSelected.size > 0
                      ? ` Ingest ${photosSelected.size} photo${photosSelected.size !== 1 ? 's' : ''}`
                      : ' Select photos to ingest'}
                  </button>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Photos are described by the vision model and stored as memories.</span>
                </div>
              )}

              {/* Live ingestion progress */}
              {photosIngestProgress && (
                <div style={{ padding: '0.75rem', borderRadius: '8px', border: '1px solid rgba(59,130,246,0.2)', background: 'rgba(59,130,246,0.05)', marginTop: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', fontSize: '0.85rem', fontWeight: 600 }}>
                    {photosIngesting ? <Loader2 size={14} className="animate-spin" color="var(--accent)" /> : <CheckCircle2 size={14} color="var(--success)" />}
                    <span>{photosIngesting ? `Ingesting ${photosIngestProgress.current} of ${photosIngestProgress.total}...` : `Done — ${photosIngestProgress.results.filter(r => r.ok).length} of ${photosIngestProgress.total} ingested`}</span>
                  </div>
                  <div style={{ height: '4px', borderRadius: '2px', background: 'rgba(255,255,255,0.08)', marginBottom: '0.5rem', overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: '2px', background: 'var(--accent)', transition: 'width 0.3s ease', width: `${(photosIngestProgress.results.length / photosIngestProgress.total) * 100}%` }} />
                  </div>
                  <div style={{ maxHeight: '150px', overflowY: 'auto', fontSize: '0.78rem' }}>
                    {photosIngestProgress.results.map((r, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.15rem 0', color: r.ok ? 'var(--text-secondary)' : 'var(--error)' }}>
                        {r.ok ? <CheckCircle2 size={11} color="var(--success)" /> : <AlertCircle size={11} color="var(--error)" />}
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.filename}</span>
                      </div>
                    ))}
                    {photosIngesting && photosIngestProgress.results.length < photosIngestProgress.current && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.15rem 0', color: 'var(--accent)' }}>
                        <Loader2 size={11} className="animate-spin" />
                        <span>Processing with vision model...</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {msg && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: msg.ok ? 'var(--success)' : 'var(--error)' }}>
          {msg.ok ? '✅' : '❌'} {msg.text}
        </div>
      )}
    </div>
  );
}
