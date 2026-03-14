import React, { useEffect, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain, Database, Key, CheckCircle2, XCircle, AlertCircle,
  Loader2, MessageSquare, Activity, Settings as SettingsIcon,
  Terminal, ArrowRight, Save, RefreshCw, ListTree, Bot,
  Search, Pencil, Trash2, X, Check, Upload, FileText, Eye, Code, Cpu, Sparkles
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

type Tab = 'dashboard' | 'settings' | 'logs';

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
          {(['dashboard', 'settings', 'logs'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`btn ${tab === t ? '' : 'btn-secondary'}`}
              style={{ padding: '0.5rem 1rem', fontSize: '0.9rem', textTransform: 'capitalize' }}
            >
              {t === 'dashboard' && <Activity size={16} />}
              {t === 'settings' && <SettingsIcon size={16} />}
              {t === 'logs' && <Terminal size={16} />}
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      </header>

      {/* Health bar always visible */}
      <HealthBar health={health} onRefresh={fetchAll} onGoSettings={() => setTab('settings')} />

      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.2 }}>
          {tab === 'dashboard' && <DashboardTab memories={memories} health={health} onOpenWizard={() => setShowWizard(true)} onRefresh={fetchAll} />}
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
        <DocumentUpload onUploaded={onRefresh} />
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

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <button className="btn" onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
          Save Changes
        </button>
        {saveMsg && <span style={{ fontSize: '0.9rem', color: saveMsg.startsWith('✅') ? 'var(--success)' : 'var(--error)' }}>{saveMsg}</span>}
      </div>
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
