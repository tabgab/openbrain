import React, { useEffect, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain, Database, Key, CheckCircle2, XCircle, AlertCircle,
  Loader2, MessageSquare, Activity, Settings as SettingsIcon,
  Terminal, ArrowRight, Save, RefreshCw, ListTree, Bot,
  Search, Pencil, Trash2, X, Check, Upload, FileText, Eye, Code, Cpu, Sparkles,
  Send, BookmarkPlus, HelpCircle, Download, Shield, RotateCcw,
  Cloud, Mail, Link, Phone
} from 'lucide-react';

const API = 'http://localhost:8000/api';

interface Health {
  db: { ok: boolean; error: string };
  llm: { ok: boolean; error: string };
  telegram: { ok: boolean; error: string; bot_name: string };
}
interface Memory { id: string; source_type: string; content: string; created_at: string; metadata: any; }
interface LogEntry { level: string; source: string; message: string; timestamp: string; }
interface Config {
  telegramToken: string; llmApiKey: string; dbPassword: string;
  dbUser: string; dbName: string; dbHost: string; llmBaseUrl: string;
  modelText: string; modelReasoning: string; modelCoding: string;
  modelVision: string; modelEmbedding: string;
}

type Tab = 'dashboard' | 'chat' | 'ingest' | 'settings' | 'logs';

const EMPTY_CONFIG: Config = {
  telegramToken: '', llmApiKey: '', dbPassword: '',
  dbUser: '', dbName: '', dbHost: '', llmBaseUrl: '',
  modelText: '', modelReasoning: '', modelCoding: '',
  modelVision: '', modelEmbedding: '',
};

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [health, setHealth] = useState<Health | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [config, setConfig] = useState<Config>(EMPTY_CONFIG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState(0);
  // Once user explicitly dismisses/saves wizard, never auto-reopen via polling
  const wizardDismissed = useRef(false);

  const closeWizard = useCallback(() => {
    wizardDismissed.current = true;
    setShowWizard(false);
  }, []);

  const fetchAll = useCallback(async () => {
    try {
      const [h, m, l, c] = await Promise.all([
        axios.get(`${API}/health`),
        axios.get(`${API}/events`),
        axios.get(`${API}/logs`),
        axios.get(`${API}/config`),
      ]);
      setHealth(h.data);
      setMemories(m.data.memories || []);
      setLogs(l.data.logs || []);
      setConfig({ ...EMPTY_CONFIG, ...c.data });
      // Only auto-show wizard on very first load when everything is unconfigured
      // and the user has not yet dismissed it.
      if (!wizardDismissed.current) {
        const isNew = !h.data.db.ok && !h.data.llm.ok && !h.data.telegram.ok;
        setShowWizard(isNew);
      }
    } catch {
      // API not ready yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 8000);
    return () => clearInterval(id);
  }, [fetchAll]);

  const saveConfig = async (partial?: Partial<Config>) => {
    setSaving(true); setSaveMsg('');
    try {
      // Only send the fields the user explicitly set — never send masked values from config state
      const payload = partial || {};
      await axios.post(`${API}/config`, payload);
      setSaveMsg('✅ Saved! Restart the backend for changes to take effect.');
      closeWizard();
      fetchAll();
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
      setSaveMsg(`❌ Failed to save: ${detail}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <Loader2 size={48} className="animate-spin" color="var(--accent)" />
    </div>
  );

  return (
    <div className="app-container">
      {/* Header */}
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)', padding: '10px', borderRadius: '12px' }}>
            <Brain size={28} color="white" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.75rem', margin: 0 }}>Open Brain</h1>
            <p style={{ margin: 0, fontSize: '0.9rem' }}>Personal Agentic Knowledge Base</p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {(['dashboard', 'chat', 'ingest', 'settings', 'logs'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`btn ${tab === t ? '' : 'btn-secondary'}`}
              style={{ padding: '0.5rem 1rem', fontSize: '0.9rem', textTransform: 'capitalize' }}
            >
              {t === 'dashboard' && <Activity size={16} />}
              {t === 'chat' && <MessageSquare size={16} />}
              {t === 'ingest' && <Download size={16} />}
              {t === 'settings' && <SettingsIcon size={16} />}
              {t === 'logs' && <Terminal size={16} />}
              {t === 'ingest' ? 'Ingest' : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </header>

      {/* Health bar always visible */}
      <HealthBar health={health} onRefresh={fetchAll} onGoSettings={() => setTab('settings')} />

      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
          {tab === 'dashboard' && <DashboardTab memories={memories} health={health} onOpenWizard={() => setShowWizard(true)} onRefresh={fetchAll} />}
          {tab === 'chat' && <ChatTab onMemoryAdded={fetchAll} />}
          {tab === 'ingest' && <IngestTab onRefresh={fetchAll} />}
          {tab === 'settings' && <SettingsTab config={config} setConfig={setConfig} onSave={saveConfig} saving={saving} saveMsg={saveMsg} />}
          {tab === 'logs' && <LogsTab logs={logs} onRefresh={fetchAll} />}
        </motion.div>
      </AnimatePresence>

      {/* Setup Wizard Overlay */}
      {showWizard && (
        <WizardOverlay
          step={wizardStep}
          setStep={setWizardStep}
          config={config}
          setConfig={setConfig}
          onSave={saveConfig}
          saving={saving}
          onClose={closeWizard}
        />
      )}
    </div>
  );
}

// --- Health Bar ---
function HealthBar({ health, onRefresh, onGoSettings }: { health: Health | null; onRefresh: () => void; onGoSettings: () => void }) {
  if (!health) return null;

  const checks = [
    { label: 'Database', ...health.db },
    { label: 'LLM', ...health.llm },
    { label: 'Telegram', ok: health.telegram.ok, error: health.telegram.error, extra: health.telegram.bot_name ? `@${health.telegram.bot_name}` : '' },
  ];

  return (
    <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
      {checks.map(c => (
        <div key={c.label} title={c.ok ? (c as any).extra || 'Connected' : c.error} style={{
          display: 'flex', alignItems: 'center', gap: '0.4rem',
          padding: '0.4rem 0.9rem', borderRadius: '999px', fontSize: '0.85rem', fontWeight: 500,
          background: c.ok ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.12)',
          color: c.ok ? 'var(--success)' : 'var(--error)',
          border: `1px solid ${c.ok ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
          cursor: c.ok ? 'default' : 'pointer',
        }} onClick={c.ok ? undefined : onGoSettings}>
          {c.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
          {c.label} {c.ok && (c as any).extra ? `·  ${(c as any).extra}` : ''}
          {!c.ok && <span style={{ fontSize: '0.78rem', opacity: 0.8 }}>— {c.error || 'Not configured'}</span>}
        </div>
      ))}
      <button onClick={onRefresh} className="btn btn-secondary" style={{ padding: '0.4rem 0.8rem', marginLeft: 'auto', fontSize: '0.85rem' }}>
        <RefreshCw size={14} /> Refresh
      </button>
    </div>
  );
}

// --- Document Upload ---
function DocumentUpload({ onUploaded }: { onUploaded: () => void }) {
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const res = await axios.post(`${API}/ingest`, form);
      if (res.data.success) {
        setResult({ ok: true, msg: `Ingested "${res.data.filename}" as ${res.data.category || 'memory'} (${res.data.method})` });
        onUploaded();
      } else {
        setResult({ ok: false, msg: res.data.error || 'Unknown error' });
      }
    } catch (err: any) {
      setResult({ ok: false, msg: err?.response?.data?.detail || err.message || 'Upload failed' });
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
      <input ref={fileRef} type="file" id="doc-upload" onChange={handleFile} style={{ display: 'none' }}
        accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.docx,.doc,.xlsx,.xls,.txt,.md,.csv" />
      <button className="btn btn-secondary" onClick={() => fileRef.current?.click()} disabled={uploading}
        style={{ padding: '0.4rem 0.85rem', fontSize: '0.85rem' }}>
        {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
        {uploading ? 'Processing…' : 'Ingest Document'}
      </button>
      <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>PDF, images, Word, Excel, text</span>
      {result && (
        <span style={{ fontSize: '0.82rem', color: result.ok ? 'var(--success)' : 'var(--error)' }}>
          {result.ok ? '✅' : '❌'} {result.msg}
        </span>
      )}
    </div>
  );
}

// --- Dashboard ---
function DashboardTab({ memories, health, onOpenWizard, onRefresh }: { memories: Memory[]; health: Health | null; onOpenWizard: () => void; onRefresh: () => void }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Memory[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const doSearch = async () => {
    if (!searchQuery.trim()) { setSearchResults(null); return; }
    setSearching(true);
    try {
      const res = await axios.get(`${API}/memories/search`, { params: { q: searchQuery.trim() } });
      setSearchResults(res.data.memories || []);
    } catch { setSearchResults([]); }
    finally { setSearching(false); }
  };

  const clearSearch = () => { setSearchQuery(''); setSearchResults(null); };

  const startEdit = (m: Memory) => { setEditingId(m.id); setEditContent(m.content); };
  const cancelEdit = () => { setEditingId(null); setEditContent(''); };
  const saveEdit = async () => {
    if (!editingId) return;
    try {
      await axios.put(`${API}/memories/${editingId}`, { content: editContent });
      cancelEdit();
      onRefresh();
      if (searchResults) doSearch();
    } catch (e) { alert('Failed to update memory.'); }
  };

  const confirmDelete = async (id: string) => {
    try {
      await axios.delete(`${API}/memories/${id}`);
      setDeletingId(null);
      onRefresh();
      if (searchResults) doSearch();
    } catch (e) { alert('Failed to delete memory.'); }
  };

  const displayList = searchResults !== null ? searchResults : memories;

  return (
    <div>
      {!health?.telegram.ok && (
        <div className="event-card" style={{ borderColor: 'rgba(239,68,68,0.3)', marginBottom: '1.5rem', background: 'rgba(239,68,68,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertCircle size={20} color="var(--error)" />
            <strong style={{ color: 'var(--error)' }}>Telegram bot is not connected.</strong>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              {health?.telegram.error || 'Unknown error.'} No messages will be captured until this is resolved.
            </span>
            <button onClick={onOpenWizard} className="btn" style={{ marginLeft: 'auto', padding: '0.35rem 0.9rem', fontSize: '0.85rem' }}>
              Fix in Wizard
            </button>
          </div>
        </div>
      )}

      {/* Search bar & Document Upload */}
      <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <Search size={18} color="var(--text-secondary)" />
          <input
            type="text"
            className="input-field"
            placeholder="Search memories..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch()}
            style={{ flex: 1, margin: 0 }}
          />
          <button className="btn" onClick={doSearch} disabled={searching} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem' }}>
            {searching ? <Loader2 size={16} className="animate-spin" /> : 'Search'}
          </button>
          {searchResults !== null && (
            <button className="btn btn-secondary" onClick={clearSearch} style={{ padding: '0.45rem 0.8rem', fontSize: '0.85rem' }}>
              <X size={14} /> Clear
            </button>
          )}
        </div>
      </div>

      <div className="glass-panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
          <ListTree color="var(--accent)" size={20} />
          <h2>{searchResults !== null ? `Search Results (${displayList.length})` : `Recent Memories (${displayList.length})`}</h2>
        </div>
        {displayList.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-secondary)' }}>
            <Bot size={48} opacity={0.4} style={{ margin: '0 auto 1rem auto', display: 'block' }} />
            {searchResults !== null
              ? <p style={{ fontSize: '1.1rem', fontWeight: 500 }}>No memories match your search.</p>
              : <>
                  <p style={{ fontSize: '1.1rem', fontWeight: 500 }}>Your Open Brain is empty.</p>
                  <p style={{ fontSize: '0.9rem' }}>Once Telegram is connected, send a message to your bot to create your first memory!</p>
                </>
            }
          </div>
        ) : displayList.map(m => (
          <div key={m.id} className="event-card" style={{ position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <span className="status-badge success">{m.metadata?.category || 'memory'}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {m.source_type} · {new Date(m.created_at).toLocaleString()}
                </span>
                {editingId !== m.id && deletingId !== m.id && (
                  <>
                    <button onClick={() => startEdit(m)} title="Edit" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.2rem', color: 'var(--text-secondary)', display: 'flex' }}>
                      <Pencil size={14} />
                    </button>
                    <button onClick={() => setDeletingId(m.id)} title="Delete" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.2rem', color: 'var(--text-secondary)', display: 'flex' }}>
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Delete confirmation */}
            {deletingId === m.id && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', borderRadius: '8px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', marginBottom: '0.5rem' }}>
                <AlertCircle size={16} color="var(--error)" />
                <span style={{ fontSize: '0.85rem', color: 'var(--error)', flex: 1 }}>Delete this memory permanently?</span>
                <button className="btn" onClick={() => confirmDelete(m.id)} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem', background: 'var(--error)' }}>
                  <Trash2 size={13} /> Delete
                </button>
                <button className="btn btn-secondary" onClick={() => setDeletingId(null)} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
                  Cancel
                </button>
              </div>
            )}

            {/* Edit mode */}
            {editingId === m.id ? (
              <div>
                <textarea
                  className="input-field"
                  value={editContent}
                  onChange={e => setEditContent(e.target.value)}
                  rows={4}
                  style={{ width: '100%', resize: 'vertical', fontFamily: 'inherit', marginBottom: '0.5rem' }}
                />
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="btn" onClick={saveEdit} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
                    <Check size={14} /> Save
                  </button>
                  <button className="btn btn-secondary" onClick={cancelEdit} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
                    <X size={14} /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <p style={{ color: 'var(--text-primary)', marginBottom: '0.5rem' }}>{m.content.substring(0, 200)}{m.content.length > 200 ? '…' : ''}</p>
                {m.metadata?.summary && <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Summary: {m.metadata.summary}</p>}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Chat Tab ---
interface ChatEntry {
  role: 'user' | 'brain';
  content: string;
  type?: 'answer' | 'memory';
  category?: string;
  summary?: string;
  memory_id?: string;
  sources?: { id: string; source_type: string; summary: string }[];
  mode?: string;
  timestamp: Date;
}

function ChatTab({ onMemoryAdded }: { onMemoryAdded: () => void }) {
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [mode, setMode] = useState<'' | 'question' | 'memory'>('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;

    const userMsg: ChatEntry = { role: 'user', content: text, mode: mode || 'auto', timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setSending(true);

    try {
      const res = await axios.post(`${API}/chat`, { message: text, force_mode: mode });
      const data = res.data;
      const brainMsg: ChatEntry = {
        role: 'brain',
        content: data.content,
        type: data.type,
        category: data.category,
        summary: data.summary,
        memory_id: data.memory_id,
        sources: data.sources,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, brainMsg]);
      if (data.type === 'memory') onMemoryAdded();
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail || err?.message || 'Something went wrong';
      setMessages(prev => [...prev, { role: 'brain', content: `Error: ${errMsg}`, timestamp: new Date() }]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const modeLabel = mode === 'question' ? 'Ask' : mode === 'memory' ? 'Store' : 'Auto';
  const modeColor = mode === 'question' ? '#3b82f6' : mode === 'memory' ? '#10b981' : 'var(--text-secondary)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 220px)', minHeight: '400px' }}>
      <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Chat header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--glass-border)' }}>
          <Brain size={20} color="var(--accent)" />
          <h2 style={{ margin: 0, flex: 1 }}>Chat with Open Brain</h2>
          <div style={{ display: 'flex', gap: '0.25rem', fontSize: '0.8rem' }}>
            {([['', 'Auto'], ['question', 'Ask'], ['memory', 'Store']] as ['' | 'question' | 'memory', string][]).map(([m, label]) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`btn ${mode === m ? '' : 'btn-secondary'}`}
                style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}
                title={m === '' ? 'Auto-detect question vs memory' : m === 'question' ? 'Force as question (search & answer)' : 'Force as memory (store)'}
              >
                {m === '' && <Sparkles size={12} />}
                {m === 'question' && <HelpCircle size={12} />}
                {m === 'memory' && <BookmarkPlus size={12} />}
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', paddingRight: '0.5rem' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-secondary)' }}>
              <Brain size={48} opacity={0.3} style={{ margin: '0 auto 1rem' }} />
              <p style={{ fontSize: '1.05rem', fontWeight: 500, marginBottom: '0.5rem' }}>Talk to your Open Brain</p>
              <p style={{ fontSize: '0.85rem', maxWidth: '400px', margin: '0 auto' }}>
                Ask questions about your stored memories, or type something to save as a new memory.
                The system auto-detects your intent — or use the mode toggle above.
              </p>
            </div>
          )}
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: '0.75rem',
              }}
            >
              <div style={{
                maxWidth: '75%',
                padding: '0.75rem 1rem',
                borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                background: msg.role === 'user'
                  ? 'linear-gradient(135deg, #3b82f6, #6366f1)'
                  : 'var(--glass-bg)',
                border: msg.role === 'brain' ? '1px solid var(--glass-border)' : 'none',
                color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
              }}>
                {/* User mode badge */}
                {msg.role === 'user' && msg.mode && (
                  <div style={{ fontSize: '0.7rem', opacity: 0.7, marginBottom: '0.25rem' }}>
                    {msg.mode === 'auto' ? '✨ auto' : msg.mode === 'question' ? '❓ question' : '📝 memory'}
                  </div>
                )}

                {/* Brain response type badge */}
                {msg.role === 'brain' && msg.type && (
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                    fontSize: '0.72rem', fontWeight: 600, marginBottom: '0.4rem',
                    padding: '0.15rem 0.5rem', borderRadius: '999px',
                    background: msg.type === 'answer' ? 'rgba(59,130,246,0.15)' : 'rgba(16,185,129,0.15)',
                    color: msg.type === 'answer' ? '#60a5fa' : '#34d399',
                  }}>
                    {msg.type === 'answer' ? <><Search size={10} /> Answer</> : <><CheckCircle2 size={10} /> Stored</>}
                  </div>
                )}

                <div style={{ whiteSpace: 'pre-wrap', fontSize: '0.9rem', lineHeight: 1.5 }}>{msg.content}</div>

                {/* Memory saved info */}
                {msg.type === 'memory' && msg.category && (
                  <div style={{ marginTop: '0.4rem', fontSize: '0.78rem', opacity: 0.7 }}>
                    Category: {msg.category}{msg.summary ? ` · ${msg.summary}` : ''}
                  </div>
                )}

                {/* Sources for answers */}
                {msg.sources && msg.sources.length > 0 && (
                  <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--glass-border)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    <span style={{ fontWeight: 600 }}>Sources:</span>
                    {msg.sources.map((s, j) => (
                      <div key={j} style={{ marginTop: '0.2rem', paddingLeft: '0.5rem' }}>
                        · <span style={{ color: 'var(--accent)' }}>{s.source_type}</span>: {s.summary}
                      </div>
                    ))}
                  </div>
                )}

                <div style={{ fontSize: '0.68rem', opacity: 0.5, marginTop: '0.3rem', textAlign: msg.role === 'user' ? 'right' : 'left' }}>
                  {msg.timestamp.toLocaleTimeString()}
                </div>
              </div>
            </motion.div>
          ))}
          {sending && (
            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '0.75rem' }}>
              <div style={{ padding: '0.75rem 1rem', borderRadius: '16px 16px 16px 4px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)' }}>
                <Loader2 size={16} className="animate-spin" color="var(--accent)" />
                <span style={{ marginLeft: '0.5rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Thinking...</span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div style={{ display: 'flex', gap: '0.5rem', paddingTop: '0.75rem', borderTop: '1px solid var(--glass-border)', marginTop: '0.5rem' }}>
          <div style={{ fontSize: '0.75rem', color: modeColor, alignSelf: 'center', minWidth: '40px', textAlign: 'center', fontWeight: 600 }}>
            {modeLabel}
          </div>
          <input
            ref={inputRef}
            type="text"
            className="input-field"
            placeholder={mode === 'question' ? 'Ask a question...' : mode === 'memory' ? 'Type a memory to store...' : 'Ask a question or store a memory...'}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
            disabled={sending}
            style={{ flex: 1, margin: 0 }}
            autoFocus
          />
          <button className="btn" onClick={send} disabled={sending || !input.trim()} style={{ padding: '0.5rem 1rem' }}>
            {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  );
}

// --- Settings Tab ---
function SettingsTab({ config, onSave, saving, saveMsg }: any) {
  // Initialize with empty strings for secrets, real values for non-secrets
  const [edits, setEdits] = React.useState<Partial<Config>>({
    llmBaseUrl: config.llmBaseUrl,
    dbUser: config.dbUser,
    dbName: config.dbName,
    dbHost: config.dbHost,
    modelText: config.modelText,
    modelReasoning: config.modelReasoning,
    modelCoding: config.modelCoding,
    modelVision: config.modelVision,
    modelEmbedding: config.modelEmbedding,
    // Secrets start empty - user must type/paste them
    telegramToken: '',
    llmApiKey: '',
    dbPassword: '',
  });

  // Track which fields are visible (for secrets)
  const [visible, setVisible] = React.useState<Record<string, boolean>>({});

  const set = (k: keyof Config) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setEdits(prev => ({ ...prev, [k]: e.target.value }));

  const toggleVisibility = (k: string) => () =>
    setVisible(prev => ({ ...prev, [k]: !prev[k] }));

  const handleSave = () => {
    const toSave: Partial<Config> = { ...edits };
    // Remove empty secret values - backend keeps existing when empty
    (['telegramToken', 'llmApiKey', 'dbPassword'] as (keyof Config)[]).forEach(k => {
      if (!edits[k]?.trim()) {
        delete toSave[k];
      }
    });
    onSave(toSave);
  };

  const SecretInput = ({ field, label, placeholder }: { field: keyof Config; label: string; placeholder: string }) => (
    <div className="input-group">
      <label>{label}</label>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <input
          type={visible[field] ? 'text' : 'password'}
          className="input-field"
          value={(edits as any)[field] ?? ''}
          onChange={set(field)}
          placeholder={placeholder}
          style={{ flex: 1, margin: 0 }}
        />
        <button
          type="button"
          className="btn btn-secondary"
          onClick={toggleVisibility(field)}
          style={{ padding: '0.4rem 0.6rem', fontSize: '0.8rem' }}
          title={visible[field] ? 'Hide' : 'Show'}
        >
          {visible[field] ? '🙈' : '👁️'}
        </button>
      </div>
    </div>
  );

  const Section = ({ title, icon, children }: any) => (
    <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
        {icon}<h2 style={{ margin: 0 }}>{title}</h2>
      </div>
      {children}
    </div>
  );

  const modelRoles: { key: keyof Config; label: string; icon: React.ReactNode; desc: string }[] = [
    { key: 'modelText',      label: 'Text (General)',     icon: <FileText size={16} color="var(--accent)" />, desc: 'Categorization, extraction, simple chat — cheap & fast' },
    { key: 'modelReasoning', label: 'Reasoning',          icon: <Sparkles size={16} color="#f59e0b" />,       desc: 'Complex analysis, research, nuanced Q&A' },
    { key: 'modelCoding',    label: 'Coding',             icon: <Code size={16} color="#10b981" />,           desc: 'Code generation, debugging, technical analysis' },
    { key: 'modelVision',    label: 'Vision / OCR',       icon: <Eye size={16} color="#8b5cf6" />,            desc: 'Image recognition, invoice/receipt parsing (multimodal)' },
    { key: 'modelEmbedding', label: 'Embedding',          icon: <Cpu size={16} color="#6366f1" />,            desc: 'Vector embeddings for semantic search' },
  ];

  return (
    <div>
      <Section title="Telegram Capture Bot" icon={<MessageSquare size={20} color="var(--accent)" />}>
        <p style={{ marginBottom: '1.25rem', fontSize: '0.9rem' }}>
          Get a bot token from <strong>@BotFather</strong> on Telegram (<code>/newbot</code>).
        </p>
        <SecretInput
          field="telegramToken"
          label="Bot Token (leave blank to keep existing)"
          placeholder="Paste new token to update…"
        />
      </Section>

      <Section title="LLM Configuration" icon={<Key size={20} color="var(--accent)" />}>
        <p style={{ marginBottom: '1.25rem', fontSize: '0.9rem' }}>
          Shared API key and base URL for all model roles. Using <strong>OpenRouter</strong> lets you mix models from different providers with one key.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
          <SecretInput
            field="llmApiKey"
            label="API Key (leave blank to keep existing)"
            placeholder="Paste new key to update…"
          />
          <div className="input-group">
            <label>Base URL</label>
            <input type="text" className="input-field" value={edits.llmBaseUrl ?? ''} onChange={set('llmBaseUrl')} />
          </div>
        </div>
      </Section>

      <Section title="Model Roles" icon={<Brain size={20} color="var(--accent)" />}>
        <p style={{ marginBottom: '1.25rem', fontSize: '0.9rem' }}>
          Assign a different model to each task type. All use the shared API key above. Use OpenRouter format: <code>provider/model-name</code>.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {modelRoles.map(r => (
            <div key={r.key} style={{ display: 'grid', gridTemplateColumns: '180px 1fr', gap: '1rem', alignItems: 'center', padding: '0.6rem 0', borderBottom: '1px solid var(--glass-border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {r.icon}
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem' }}>{r.label}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{r.desc}</div>
                </div>
              </div>
              <input
                type="text"
                className="input-field"
                value={(edits as any)[r.key] ?? ''}
                onChange={set(r.key)}
                style={{ margin: 0 }}
                placeholder="e.g. openai/gpt-4o-mini"
              />
            </div>
          ))}
        </div>
      </Section>

      <Section title="Database" icon={<Database size={20} color="var(--accent)" />}>
        <p style={{ marginBottom: '1.25rem', fontSize: '0.9rem' }}>
          Must match your <code>docker-compose.yml</code>. Password is never displayed for security.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="input-group">
            <label>Host</label>
            <input type="text" className="input-field" value={edits.dbHost ?? ''} onChange={set('dbHost')} />
          </div>
          <div className="input-group">
            <label>Database Name</label>
            <input type="text" className="input-field" value={edits.dbName ?? ''} onChange={set('dbName')} />
          </div>
          <div className="input-group">
            <label>User</label>
            <input type="text" className="input-field" value={edits.dbUser ?? ''} onChange={set('dbUser')} />
          </div>
          <SecretInput
            field="dbPassword"
            label="Password (leave blank to keep existing)"
            placeholder="Paste new password to update…"
          />
        </div>
      </Section>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
        <button className="btn" onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
          Save Changes
        </button>
        {saveMsg && <span style={{ fontSize: '0.9rem', color: saveMsg.startsWith('✅') ? 'var(--success)' : 'var(--error)' }}>{saveMsg}</span>}
      </div>

      <BackupRestoreSection />
    </div>
  );
}

// --- Backup & Restore ---
function BackupRestoreSection() {
  const [backupPassword, setBackupPassword] = useState('');
  const [backupStatus, setBackupStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const [backingUp, setBackingUp] = useState(false);
  const [includeSecrets, setIncludeSecrets] = useState(true);

  const [restorePassword, setRestorePassword] = useState('');
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restoreStatus, setRestoreStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const [restoring, setRestoring] = useState(false);
  const restoreFileRef = useRef<HTMLInputElement>(null);

  const doBackup = async () => {
    if (backupPassword.length < 4) {
      setBackupStatus({ ok: false, msg: 'Password must be at least 4 characters.' });
      return;
    }
    setBackingUp(true);
    setBackupStatus(null);
    try {
      const res = await axios.post(`${API}/backup`, { password: backupPassword, include_secrets: includeSecrets }, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      const disposition = res.headers['content-disposition'] || '';
      const match = disposition.match(/filename=(.+)/);
      link.download = match ? match[1] : `openbrain_backup.obk`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setBackupStatus({ ok: true, msg: 'Encrypted backup downloaded successfully.' });
      setBackupPassword('');
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Backup failed';
      setBackupStatus({ ok: false, msg: typeof detail === 'string' ? detail : 'Backup failed' });
    } finally {
      setBackingUp(false);
    }
  };

  const doRestore = async () => {
    if (!restoreFile) {
      setRestoreStatus({ ok: false, msg: 'Please select a .obk backup file.' });
      return;
    }
    if (restorePassword.length < 4) {
      setRestoreStatus({ ok: false, msg: 'Password must be at least 4 characters.' });
      return;
    }
    setRestoring(true);
    setRestoreStatus(null);
    try {
      const form = new FormData();
      form.append('file', restoreFile);
      form.append('password', restorePassword);
      const res = await axios.post(`${API}/restore`, form);
      const summary = res.data.summary || {};
      const tables = (summary.tables_restored || []).map((t: any) => t.error ? `${t.table}: ERROR` : `${t.table}: ${t.rows} rows`).join(', ');
      setRestoreStatus({ ok: true, msg: `Restored: ${tables}. Env: ${summary.env_restored ? 'yes' : 'no'}. Restart the backend to apply.` });
      setRestorePassword('');
      setRestoreFile(null);
      if (restoreFileRef.current) restoreFileRef.current.value = '';
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Restore failed';
      setRestoreStatus({ ok: false, msg: typeof detail === 'string' ? detail : 'Restore failed' });
    } finally {
      setRestoring(false);
    }
  };

  return (
    <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <Shield size={20} color="var(--accent)" />
        <h2 style={{ margin: 0 }}>Backup & Restore</h2>
      </div>
      <p style={{ fontSize: '0.9rem', marginBottom: '1.25rem', color: 'var(--text-secondary)' }}>
        Create an AES-256 encrypted backup of your entire Open Brain (all memories, vault secrets, and configuration).
        Restore it to any fresh instance with the correct password.
      </p>

      {/* Backup */}
      <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.15)', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <Download size={16} color="#3b82f6" />
          <strong style={{ fontSize: '0.95rem' }}>Create Backup</strong>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="password"
            className="input-field"
            placeholder="Encryption password (min 4 chars)"
            value={backupPassword}
            onChange={e => setBackupPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doBackup()}
            style={{ flex: 1, margin: 0, minWidth: '200px' }}
          />
          <button className="btn" onClick={doBackup} disabled={backingUp} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem' }}>
            {backingUp ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
            {backingUp ? 'Creating...' : 'Download Backup'}
          </button>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.6rem', fontSize: '0.85rem', cursor: 'pointer', color: 'var(--text-secondary)' }}>
          <input
            type="checkbox"
            checked={includeSecrets}
            onChange={e => setIncludeSecrets(e.target.checked)}
            style={{ accentColor: 'var(--accent)' }}
          />
          Include LLM API key & Telegram token
          <span style={{ fontSize: '0.78rem', opacity: 0.7 }}>(DB password & vault are always included)</span>
        </label>
        {backupStatus && (
          <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: backupStatus.ok ? 'var(--success)' : 'var(--error)' }}>
            {backupStatus.ok ? '✅' : '❌'} {backupStatus.msg}
          </div>
        )}
      </div>

      {/* Restore */}
      <div style={{ padding: '1rem', borderRadius: '10px', background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.15)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
          <RotateCcw size={16} color="#f59e0b" />
          <strong style={{ fontSize: '0.95rem' }}>Restore from Backup</strong>
        </div>
        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
          This will <strong>overwrite</strong> all current memories, vault secrets, and configuration with the backup contents.
        </p>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
          <input
            ref={restoreFileRef}
            type="file"
            accept=".obk"
            onChange={e => setRestoreFile(e.target.files?.[0] || null)}
            style={{ fontSize: '0.85rem', flex: 1, minWidth: '200px' }}
          />
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="password"
            className="input-field"
            placeholder="Backup password"
            value={restorePassword}
            onChange={e => setRestorePassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doRestore()}
            style={{ flex: 1, margin: 0, minWidth: '200px' }}
          />
          <button className="btn" onClick={doRestore} disabled={restoring} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem', background: '#f59e0b' }}>
            {restoring ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
            {restoring ? 'Restoring...' : 'Restore System'}
          </button>
        </div>
        {restoreStatus && (
          <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: restoreStatus.ok ? 'var(--success)' : 'var(--error)' }}>
            {restoreStatus.ok ? '✅' : '❌'} {restoreStatus.msg}
          </div>
        )}
      </div>
    </div>
  );
}

// --- Ingest Tab ---
function IngestTab({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div>
      <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
          <Upload size={20} color="var(--accent)" />
          <h2 style={{ margin: 0 }}>Ingest Document</h2>
        </div>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Upload a file to ingest into your knowledge base. Supports PDF, images, Word, Excel, text, and more.
        </p>
        <DocumentUpload onUploaded={onRefresh} />
      </div>
      <GoogleIntegrationSection />
      <WhatsAppImportSection onImported={onRefresh} />
    </div>
  );
}

// --- Google Drive & Gmail (multi-account, search/filter/preview/ingest) ---
interface GoogleAccount { email: string; connected: boolean; connected_at?: string; drive_last_sync?: string; gmail_last_sync?: string; }
interface DriveFile { id: string; name: string; mimeType: string; modifiedTime: string; size: string; already_synced: boolean; }
interface GmailMsg { id: string; from: string; subject: string; date: string; snippet: string; already_synced: boolean; }

function GoogleIntegrationSection() {
  const [hasCreds, setHasCreds] = useState(false);
  const [accounts, setAccounts] = useState<GoogleAccount[]>([]);
  const [connecting, setConnecting] = useState(false);
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'drive' | 'gmail'>('drive');
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
  const [gmailNewer, setGmailNewer] = useState('7d');
  const [gmailMsgs, setGmailMsgs] = useState<GmailMsg[]>([]);
  const [gmailSelected, setGmailSelected] = useState<Set<string>>(new Set());
  const [gmailSearching, setGmailSearching] = useState(false);
  const [gmailIngesting, setGmailIngesting] = useState(false);
  const [gmailIncludeImages, setGmailIncludeImages] = useState(false);
  const [expandedEmail, setExpandedEmail] = useState<string | null>(null);
  const [emailPreview, setEmailPreview] = useState<{ id: string; from: string; to: string; subject: string; date: string; body: string; html_body?: string; image_count?: number } | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/google/status`);
      setHasCreds(res.data.has_credentials_file);
      setAccounts(res.data.accounts || []);
      if (!activeAccount && res.data.accounts?.length > 0) setActiveAccount(res.data.accounts[0].email);
    } catch {}
  }, [activeAccount]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const connect = async () => {
    setConnecting(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/google/connect`);
      if (res.data.auth_url) window.open(res.data.auth_url, '_blank');
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

  // Gmail search
  const searchGmail = async () => {
    if (!activeAccount) return;
    setGmailSearching(true); setMsg(null); setGmailMsgs([]); setGmailSelected(new Set());
    try {
      const res = await axios.post(`${API}/google/gmail/search`, {
        email: activeAccount, query: gmailQuery, from_filter: gmailFrom,
        subject_filter: gmailSubject, label: gmailLabel, newer_than: gmailNewer, max_results: 30,
      });
      setGmailMsgs(res.data.messages || []);
      if (res.data.messages?.length === 0) setMsg({ ok: true, text: 'No emails found matching your filters.' });
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Gmail search failed' }); }
    finally { setGmailSearching(false); }
  };

  const ingestGmailMsgs = async () => {
    if (!activeAccount || gmailSelected.size === 0) return;
    setGmailIngesting(true); setMsg(null);
    try {
      const res = await axios.post(`${API}/google/gmail/ingest`, { email: activeAccount, message_ids: Array.from(gmailSelected), include_images: gmailIncludeImages });
      const n = res.data.ingested?.length || 0;
      const e = res.data.errors?.length || 0;
      setMsg({ ok: e === 0, text: `Ingested ${n} emails${e > 0 ? `, ${e} errors` : ''}` });
      setGmailSelected(new Set());
      searchGmail();
    } catch (err: any) { setMsg({ ok: false, text: err?.response?.data?.detail || 'Ingest failed' }); }
    finally { setGmailIngesting(false); }
  };

  const toggleDrive = (id: string) => setDriveSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
  const toggleGmail = (id: string) => setGmailSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });

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
        <h2 style={{ margin: 0, flex: 1 }}>Google Drive & Gmail</h2>
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
            <li>Go to <strong>APIs & Services</strong> &rarr; <strong>Library</strong>, search for and enable both <strong>Google Drive API</strong> and <strong>Gmail API</strong></li>
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

      {/* Drive / Gmail tabs */}
      {activeAccount && (
        <>
          <div style={{ display: 'flex', gap: '0.3rem', marginBottom: '0.75rem' }}>
            {(['drive', 'gmail'] as const).map(t => (
              <button key={t} onClick={() => setActiveTab(t)}
                style={{ padding: '0.3rem 0.8rem', borderRadius: '6px', fontSize: '0.82rem', border: 'none', cursor: 'pointer',
                  background: activeTab === t ? 'rgba(59,130,246,0.2)' : 'transparent', color: activeTab === t ? 'var(--accent)' : 'var(--text-secondary)', fontWeight: activeTab === t ? 600 : 400 }}>
                {t === 'drive' ? <><Cloud size={13} /> Drive</> : <><Mail size={13} /> Gmail</>}
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
                      <input type="checkbox" checked={driveSelected.has(f.id)} onChange={() => toggleDrive(f.id)} disabled={f.already_synced} style={{ accentColor: 'var(--accent)' }} />
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
                <select style={{ ...sty.inp, maxWidth: '120px' }} value={gmailLabel} onChange={e => setGmailLabel(e.target.value)}>
                  <option value="">All labels</option>
                  <option value="INBOX">Inbox</option>
                  <option value="STARRED">Starred</option>
                  <option value="IMPORTANT">Important</option>
                  <option value="SENT">Sent</option>
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
                        <input type="checkbox" checked={gmailSelected.has(m.id)} onChange={() => toggleGmail(m.id)} disabled={m.already_synced}
                          style={{ accentColor: 'var(--accent)' }} onClick={e => e.stopPropagation()} />
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
              {gmailMsgs.length > 0 && gmailSelected.size > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.7rem', flexWrap: 'wrap' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.82rem', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                    <input type="checkbox" checked={gmailIncludeImages} onChange={e => setGmailIncludeImages(e.target.checked)} style={{ accentColor: 'var(--accent)' }} />
                    Include images (vision OCR)
                  </label>
                  <button className="btn" onClick={ingestGmailMsgs} disabled={gmailIngesting} style={{ padding: '0.35rem 0.8rem', fontSize: '0.82rem' }}>
                    {gmailIngesting ? <Loader2 size={13} className="animate-spin" /> : <Mail size={13} />}
                    Ingest {gmailSelected.size} email{gmailSelected.size !== 1 ? 's' : ''}{gmailIncludeImages ? ' + images' : ''}
                  </button>
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

// --- WhatsApp Import ---
function WhatsAppImportSection({ onImported }: { onImported: () => void }) {
  const [chatName, setChatName] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const doImport = async () => {
    if (!file) { setResult({ ok: false, msg: 'Please select a WhatsApp export .txt file.' }); return; }
    setImporting(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('chat_name', chatName || 'WhatsApp Chat');
      const res = await axios.post(`${API}/whatsapp/import`, form);
      if (res.data.error) {
        setResult({ ok: false, msg: res.data.error });
      } else {
        setResult({ ok: true, msg: `Imported ${res.data.ingested} message groups (${res.data.total_messages} messages) from "${res.data.chat_name}"` });
        onImported();
        setFile(null);
        setChatName('');
        if (fileRef.current) fileRef.current.value = '';
      }
    } catch (err: any) {
      setResult({ ok: false, msg: err?.response?.data?.detail || 'Import failed' });
    } finally { setImporting(false); }
  };

  return (
    <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <Phone size={20} color="#25D366" />
        <h2 style={{ margin: 0 }}>WhatsApp Import</h2>
      </div>
      <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
        Import a WhatsApp chat export. In WhatsApp, open a chat → tap ⋮ → <strong>Export chat</strong> → <strong>Without media</strong> → save the .txt file.
      </p>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
        <input
          ref={fileRef}
          type="file"
          accept=".txt"
          onChange={e => setFile(e.target.files?.[0] || null)}
          style={{ fontSize: '0.85rem', flex: 1, minWidth: '200px' }}
        />
      </div>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="text"
          className="input-field"
          placeholder="Chat name (e.g. Family Group)"
          value={chatName}
          onChange={e => setChatName(e.target.value)}
          style={{ flex: 1, margin: 0, minWidth: '200px' }}
        />
        <button className="btn" onClick={doImport} disabled={importing} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem', background: '#25D366' }}>
          {importing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          {importing ? 'Importing...' : 'Import Chat'}
        </button>
      </div>
      {result && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: result.ok ? 'var(--success)' : 'var(--error)' }}>
          {result.ok ? '✅' : '❌'} {result.msg}
        </div>
      )}
    </div>
  );
}

// --- Logs Tab ---
function LogsTab({ logs, onRefresh }: { logs: LogEntry[]; onRefresh: () => void }) {
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

// --- Setup Wizard Overlay ---
function WizardOverlay({ step, setStep, config, setConfig, onSave, saving, onClose }: any) {
  const set = (k: keyof Config) => (e: React.ChangeEvent<HTMLInputElement>) => setConfig((c: Config) => ({ ...c, [k]: e.target.value }));

  const steps = [
    {
      title: "Welcome to Open Brain",
      icon: <Brain size={48} color="var(--accent)" />,
      desc: "This wizard will help you connect your Open Brain to the outside world.",
      content: <p>Fill out the steps to connect your database, LLM engine, and Telegram capture bot. You can change all settings later in the <strong>Settings</strong> tab.</p>
    },
    {
      title: "LLM API Key",
      icon: <Key size={48} color="var(--accent)" />,
      desc: "We recommend OpenRouter — it lets you use any model (Claude, GPT-4o, etc.) with one key.",
      content: (
        <>
          <div className="input-group">
            <label>API Key (OpenRouter or OpenAI)</label>
            <input type="password" className="input-field" value={config.llmApiKey} onChange={set('llmApiKey')} placeholder="sk-or-v1-..." autoFocus />
          </div>
          <div className="input-group">
            <label>Base URL (leave blank for OpenAI)</label>
            <input type="text" className="input-field" value={config.llmBaseUrl} onChange={set('llmBaseUrl')} placeholder="https://openrouter.ai/api/v1" />
          </div>
        </>
      )
    },
    {
      title: "Telegram Bot Token",
      icon: <Bot size={48} color="var(--accent)" />,
      desc: "Message @BotFather on Telegram, send /newbot, and paste the token below.",
      content: (
        <div className="input-group">
          <label>Telegram Bot Token</label>
          <input type="password" className="input-field" value={config.telegramToken} onChange={set('telegramToken')} placeholder="123456789:ABCDEF..." autoFocus />
        </div>
      )
    },
  ];

  const cur = steps[step];
  const isLast = step === steps.length - 1;

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100 }}>
      <div className="glass-panel" style={{ maxWidth: '520px', width: '90%' }}>
        <button onClick={onClose} style={{ float: 'right', background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '1.25rem' }}>✕</button>
        <div style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
          {cur.icon}
          <h2 style={{ marginTop: '1rem' }}>{cur.title}</h2>
          <p>{cur.desc}</p>
        </div>
        <AnimatePresence mode="wait">
          <motion.div key={step} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.2 }}>
            {cur.content}
          </motion.div>
        </AnimatePresence>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '2rem' }}>
          {step > 0 ? <button className="btn btn-secondary" onClick={() => setStep((s: number) => s - 1)}>Back</button> : <div />}
          <button className="btn" disabled={saving} onClick={() => isLast ? onSave() : setStep((s: number) => s + 1)}>
            {saving ? <Loader2 size={18} className="animate-spin" /> : isLast ? <><Save size={18} /> Save & Close</> : <>Next <ArrowRight size={18} /></>}
          </button>
        </div>
        <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginTop: '2rem' }}>
          {steps.map((_, i) => (
            <div key={i} style={{ height: '4px', width: '2rem', borderRadius: '2px', background: i <= step ? 'var(--accent)' : 'rgba(255,255,255,0.1)', transition: 'background 0.3s' }} />
          ))}
        </div>
      </div>
    </div>
  );
}
