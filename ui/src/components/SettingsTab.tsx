import React, { useState, useRef } from 'react';
import axios from 'axios';
import {
  MessageSquare, Key, Brain, Database, Save, Loader2, RefreshCw,
  FileText, Sparkles, Code, Eye, Cpu, CheckCircle2, Mic,
  Shield, Download, RotateCcw
} from 'lucide-react';
import { API } from '../types';
import type { Config } from '../types';

// --- Backup & Restore (used inside SettingsTab) ---
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

// --- Settings Tab ---
export default function SettingsTab({ config, onSave, saving, saveMsg, onDirtyChange }: any) {
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
    // STT
    sttProvider: config.sttProvider || 'openai',
    whisperModelSize: config.whisperModelSize || 'base',
    // Secrets start empty - user must type/paste them
    telegramToken: '',
    llmApiKey: '',
    dbPassword: '',
    openaiApiKey: '',
    groqApiKey: '',
  });
  const [sttStatus, setSttStatus] = React.useState<any>(null);
  const [installing, setInstalling] = React.useState('');

  // Track which fields are visible (for secrets)
  const [visible, setVisible] = React.useState<Record<string, boolean>>({});

  const markDirty = () => { if (onDirtyChange) onDirtyChange(true); };
  const set = (k: keyof Config) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setEdits(prev => ({ ...prev, [k]: e.target.value }));
    markDirty();
  };

  const toggleVisibility = (k: string) => () =>
    setVisible(prev => ({ ...prev, [k]: !prev[k] }));

  const handleSave = () => {
    const toSave: Partial<Config> = { ...edits };
    // Remove empty secret values - backend keeps existing when empty
    (['telegramToken', 'llmApiKey', 'dbPassword', 'openaiApiKey', 'groqApiKey'] as (keyof Config)[]).forEach(k => {
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

      <Section title="Voice Transcription (STT)" icon={<Mic size={20} color="var(--accent)" />}>
        <p style={{ marginBottom: '1.25rem', fontSize: '0.9rem' }}>
          Choose how voice messages from Telegram are transcribed. Each provider auto-detects the spoken language.
        </p>

        {/* Provider selector */}
        <div className="input-group" style={{ marginBottom: '1.25rem' }}>
          <label>STT Provider</label>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {([
              ['openai', '☁️ OpenAI Whisper API', 'Fast, accurate. Requires OPENAI_API_KEY (direct OpenAI, not OpenRouter).'],
              ['groq', '⚡ Groq', 'Very fast, free tier. Requires GROQ_API_KEY.'],
              ['local', '🖥️ Local Whisper', 'Fully private, runs on-device. Requires openai-whisper package + ffmpeg.'],
            ] as [string, string, string][]).map(([value, label, desc]) => (
              <button
                key={value}
                onClick={() => { setEdits(prev => ({ ...prev, sttProvider: value })); markDirty(); }}
                style={{
                  flex: '1 1 0', minWidth: '160px', padding: '0.75rem', borderRadius: '8px', cursor: 'pointer',
                  border: `1.5px solid ${edits.sttProvider === value ? 'var(--accent)' : 'rgba(255,255,255,0.1)'}`,
                  background: edits.sttProvider === value ? 'rgba(59,130,246,0.12)' : 'transparent',
                  textAlign: 'left', transition: 'all 0.15s',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: '0.88rem', color: edits.sttProvider === value ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{label}</div>
                <div style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>{desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Provider-specific settings */}
        {edits.sttProvider === 'openai' && (
          <div style={{ padding: '1rem', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'rgba(59,130,246,0.05)' }}>
            <SecretInput
              field="openaiApiKey"
              label="OpenAI API Key (leave blank to keep existing)"
              placeholder="sk-... (direct OpenAI key, NOT OpenRouter)"
            />
            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0.5rem 0 0' }}>
              Get a key at <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>platform.openai.com/api-keys</a>. This is separate from your OpenRouter key.
            </p>
          </div>
        )}

        {edits.sttProvider === 'groq' && (
          <div style={{ padding: '1rem', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'rgba(59,130,246,0.05)' }}>
            <SecretInput
              field="groqApiKey"
              label="Groq API Key (leave blank to keep existing)"
              placeholder="gsk_..."
            />
            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0.5rem 0 0' }}>
              Free tier available at <a href="https://console.groq.com" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>console.groq.com</a>. Uses Whisper large-v3-turbo.
            </p>
            {sttStatus && !sttStatus.groq_installed && (
              <button
                className="btn btn-secondary"
                style={{ marginTop: '0.75rem', fontSize: '0.82rem' }}
                disabled={installing === 'groq'}
                onClick={async () => {
                  setInstalling('groq');
                  try {
                    const r = await axios.post(`${API}/stt/install-groq`);
                    setSttStatus((prev: any) => ({ ...prev, groq_installed: true }));
                    alert(r.data.message);
                  } catch (e: any) { alert('Install failed: ' + (e?.response?.data?.detail || e.message)); }
                  finally { setInstalling(''); }
                }}
              >
                {installing === 'groq' ? <><Loader2 size={14} className="animate-spin" /> Installing...</> : '📦 Install Groq SDK'}
              </button>
            )}
          </div>
        )}

        {edits.sttProvider === 'local' && (
          <div style={{ padding: '1rem', borderRadius: '8px', border: '1px solid var(--glass-border)', background: 'rgba(59,130,246,0.05)' }}>
            <div className="input-group" style={{ marginBottom: '0.75rem' }}>
              <label>Model Size</label>
              <div style={{ display: 'flex', gap: '0.4rem' }}>
                {['tiny', 'base', 'small', 'medium', 'large'].map(size => (
                  <button
                    key={size}
                    onClick={() => { setEdits(prev => ({ ...prev, whisperModelSize: size })); markDirty(); }}
                    style={{
                      padding: '0.3rem 0.7rem', borderRadius: '6px', fontSize: '0.8rem', cursor: 'pointer',
                      border: `1px solid ${edits.whisperModelSize === size ? 'var(--accent)' : 'rgba(255,255,255,0.1)'}`,
                      background: edits.whisperModelSize === size ? 'rgba(59,130,246,0.15)' : 'transparent',
                      color: edits.whisperModelSize === size ? 'var(--text-primary)' : 'var(--text-secondary)',
                    }}
                  >
                    {size}
                  </button>
                ))}
              </div>
              <p style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', margin: '0.4rem 0 0' }}>
                tiny (~39MB, fastest) → large (~2.9GB, most accurate). Recommended: <strong>base</strong> for balanced speed/quality.
              </p>
            </div>

            {sttStatus && !sttStatus.whisper_installed ? (
              <button
                className="btn"
                style={{ fontSize: '0.82rem' }}
                disabled={installing === 'whisper'}
                onClick={async () => {
                  setInstalling('whisper');
                  try {
                    const r = await axios.post(`${API}/stt/install-whisper`);
                    setSttStatus((prev: any) => ({ ...prev, whisper_installed: true }));
                    alert(r.data.message);
                  } catch (e: any) { alert('Install failed: ' + (e?.response?.data?.detail || e.message)); }
                  finally { setInstalling(''); }
                }}
              >
                {installing === 'whisper' ? <><Loader2 size={14} className="animate-spin" /> Installing (may take a few minutes)...</> : '📦 Install Local Whisper'}
              </button>
            ) : sttStatus?.whisper_installed ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--success)', fontSize: '0.85rem' }}>
                  <CheckCircle2 size={16} /> Local Whisper installed
                  {sttStatus.whisper_models?.length > 0 && (
                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                      (cached models: {sttStatus.whisper_models.join(', ')})
                    </span>
                  )}
                </div>
                {/* Pre-download model button */}
                {!sttStatus.whisper_models?.includes(edits.whisperModelSize || 'base') && (
                  <button
                    className="btn btn-secondary"
                    style={{ fontSize: '0.82rem', alignSelf: 'flex-start' }}
                    disabled={installing === 'download'}
                    onClick={async () => {
                      setInstalling('download');
                      try {
                        const r = await axios.post(`${API}/stt/download-model?model_size=${edits.whisperModelSize || 'base'}`);
                        setSttStatus((prev: any) => ({
                          ...prev,
                          whisper_models: [...(prev?.whisper_models || []), edits.whisperModelSize || 'base'],
                        }));
                        alert(r.data.message);
                      } catch (e: any) { alert('Download failed: ' + (e?.response?.data?.detail || e.message)); }
                      finally { setInstalling(''); }
                    }}
                  >
                    {installing === 'download' ? <><Loader2 size={14} className="animate-spin" /> Downloading '{edits.whisperModelSize}' model...</> : `⬇️ Download '${edits.whisperModelSize}' model now`}
                  </button>
                )}
              </div>
            ) : (
              <button
                className="btn btn-secondary"
                style={{ fontSize: '0.82rem' }}
                onClick={async () => {
                  try { const r = await axios.get(`${API}/stt/status`); setSttStatus(r.data); }
                  catch { setSttStatus({ whisper_installed: false, whisper_models: [], groq_installed: false }); }
                }}
              >
                <RefreshCw size={14} /> Check Installation Status
              </button>
            )}

            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', margin: '0.75rem 0 0' }}>
              Requires <code>ffmpeg</code> installed on your system. The first transcription will download the selected model.
            </p>
          </div>
        )}

        {/* Fetch status on mount if not already loaded */}
        {!sttStatus && (
          <button
            className="btn btn-secondary"
            style={{ marginTop: '0.75rem', fontSize: '0.82rem' }}
            onClick={async () => {
              try { const r = await axios.get(`${API}/stt/status`); setSttStatus(r.data); }
              catch { setSttStatus({ whisper_installed: false, whisper_models: [], groq_installed: false }); }
            }}
          >
            <RefreshCw size={14} /> Check STT Status
          </button>
        )}
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

      <BackupRestoreSection />

      {/* Sticky save bar — always visible at bottom */}
      <div style={{
        position: 'sticky', bottom: 0, zIndex: 10,
        padding: '0.75rem 1.25rem', marginTop: '1.5rem',
        background: 'rgba(20, 20, 30, 0.95)', backdropFilter: 'blur(12px)',
        borderTop: '1px solid var(--glass-border)', borderRadius: '12px 12px 0 0',
        display: 'flex', alignItems: 'center', gap: '1rem',
      }}>
        <button className="btn" onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
          Save Changes
        </button>
        {saveMsg && <span style={{ fontSize: '0.9rem', color: saveMsg.startsWith('✅') ? 'var(--success)' : 'var(--error)' }}>{saveMsg}</span>}
      </div>
    </div>
  );
}
