import { useState, useRef } from 'react';
import axios from 'axios';
import { Loader2, Upload, Mail, HardDrive, Shield } from 'lucide-react';
import { API } from '../types';
import DocumentUpload from './DocumentUpload';

export default function ProtonImport() {
  const [activeTab, setActiveTab] = useState<'mail' | 'drive'>('mail');
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [showGuide, setShowGuide] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const doImport = async () => {
    if (!file) { setResult({ ok: false, msg: 'Please select an MBOX or EML file.' }); return; }
    setImporting(true); setResult(null);
    const ext = file.name.split('.').pop()?.toLowerCase();
    const endpoint = ext === 'eml' ? 'eml' : 'mbox';
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('source_service', 'proton_mail');
      form.append('chat_name', 'Proton Mail Import');
      const res = await axios.post(`${API}/email-import/${endpoint}`, form);
      if (res.data.ingested > 0) {
        setResult({ ok: true, msg: `Imported ${res.data.ingested} emails from Proton Mail` });
        setFile(null);
        if (fileRef.current) fileRef.current.value = '';
      } else {
        setResult({ ok: false, msg: res.data.message || 'No emails found in file.' });
      }
    } catch (err: any) {
      setResult({ ok: false, msg: err?.response?.data?.detail || 'Import failed' });
    } finally { setImporting(false); }
  };

  return (
    <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
        <Shield size={20} color="#6D4AFF" />
        <h2 style={{ margin: 0, flex: 1 }}>Proton Mail & Drive</h2>
      </div>

      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.75rem', lineHeight: 1.5 }}>
        Proton is end-to-end encrypted — there's no third-party API access. Instead, export your data from Proton and import it here.
      </p>

      <div style={{ display: 'flex', gap: '0.3rem', marginBottom: '0.75rem' }}>
        {(['mail', 'drive'] as const).map(t => (
          <button key={t} onClick={() => setActiveTab(t)}
            style={{ padding: '0.3rem 0.8rem', borderRadius: '6px', fontSize: '0.82rem', border: 'none', cursor: 'pointer',
              background: activeTab === t ? 'rgba(109,74,255,0.2)' : 'transparent', color: activeTab === t ? '#6D4AFF' : 'var(--text-secondary)', fontWeight: activeTab === t ? 600 : 400 }}>
            {t === 'mail' && <><Mail size={13} /> Mail</>}
            {t === 'drive' && <><HardDrive size={13} /> Drive</>}
          </button>
        ))}
      </div>

      {activeTab === 'mail' && (
        <div>
          <button onClick={() => setShowGuide(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', fontSize: '0.82rem', padding: '0 0 0.5rem 0' }}>
            {showGuide ? 'Hide' : 'Show'} Export Guide
          </button>
          {showGuide && (
            <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(109,74,255,0.08)', border: '1px solid rgba(109,74,255,0.2)', marginBottom: '0.75rem', fontSize: '0.85rem' }}>
              <strong>How to export from Proton Mail:</strong>
              <ol style={{ margin: '0.5rem 0 0 1.2rem', padding: 0, lineHeight: 1.6 }}>
                <li>Install <a href="https://proton.me/mail/bridge" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Proton Mail Bridge</a> on your computer</li>
                <li>Connect your mail client (Thunderbird recommended) via Bridge</li>
                <li>In Thunderbird, select emails → right-click → <strong>Save As</strong> → save as <strong>.eml</strong> files</li>
                <li>Or use <a href="https://addons.thunderbird.net/en-US/thunderbird/addon/importexporttools-ng/" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>ImportExportTools NG</a> to export entire folders as <strong>.mbox</strong></li>
                <li>Upload the exported .mbox or .eml file(s) below</li>
              </ol>
              <div style={{ marginTop: '0.5rem', padding: '0.4rem', borderRadius: '6px', background: 'rgba(109,74,255,0.06)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                <strong>Alternative:</strong> Go to <a href="https://account.proton.me/u/0/mail/import-export" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Proton Settings → Import/Export</a> and use the built-in export tool to download your emails.
              </div>
            </div>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
            <input ref={fileRef} type="file" accept=".mbox,.eml" onChange={e => setFile(e.target.files?.[0] || null)} style={{ fontSize: '0.85rem', flex: 1, minWidth: '200px' }} />
            <button className="btn" onClick={doImport} disabled={importing} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem', background: '#6D4AFF' }}>
              {importing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {importing ? 'Importing...' : 'Import Emails'}
            </button>
          </div>
        </div>
      )}

      {activeTab === 'drive' && (
        <div>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
            Download files from <a href="https://drive.proton.me" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Proton Drive</a>, then upload them here to ingest into your knowledge base.
          </p>
          <DocumentUpload onUploaded={() => {}} />
        </div>
      )}

      {result && <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: result.ok ? 'var(--success)' : 'var(--error)' }}>{result.ok ? '✅' : '❌'} {result.msg}</div>}
    </div>
  );
}
