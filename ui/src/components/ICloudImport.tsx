import { useState, useRef } from 'react';
import axios from 'axios';
import { Loader2, Upload, Mail, HardDrive, Apple } from 'lucide-react';
import { API } from '../types';
import DocumentUpload from './DocumentUpload';

export default function ICloudImport() {
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
      form.append('source_service', 'icloud_mail');
      form.append('chat_name', 'iCloud Mail Import');
      const res = await axios.post(`${API}/email-import/${endpoint}`, form);
      if (res.data.ingested > 0) {
        setResult({ ok: true, msg: `Imported ${res.data.ingested} emails from iCloud Mail` });
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
        <Apple size={20} color="#A2AAAD" />
        <h2 style={{ margin: 0, flex: 1 }}>Apple iCloud</h2>
      </div>

      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.75rem', lineHeight: 1.5 }}>
        Apple doesn't provide a third-party API for iCloud. Export your data and import it here.
      </p>

      <div style={{ display: 'flex', gap: '0.3rem', marginBottom: '0.75rem' }}>
        {(['mail', 'drive'] as const).map(t => (
          <button key={t} onClick={() => setActiveTab(t)}
            style={{ padding: '0.3rem 0.8rem', borderRadius: '6px', fontSize: '0.82rem', border: 'none', cursor: 'pointer',
              background: activeTab === t ? 'rgba(162,170,173,0.2)' : 'transparent', color: activeTab === t ? '#A2AAAD' : 'var(--text-secondary)', fontWeight: activeTab === t ? 600 : 400 }}>
            {t === 'mail' && <><Mail size={13} /> Mail</>}
            {t === 'drive' && <><HardDrive size={13} /> iCloud Drive</>}
          </button>
        ))}
      </div>

      {activeTab === 'mail' && (
        <div>
          <button onClick={() => setShowGuide(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', fontSize: '0.82rem', padding: '0 0 0.5rem 0' }}>
            {showGuide ? 'Hide' : 'Show'} Export Guide
          </button>
          {showGuide && (
            <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(162,170,173,0.08)', border: '1px solid rgba(162,170,173,0.2)', marginBottom: '0.75rem', fontSize: '0.85rem' }}>
              <strong>How to export from Apple Mail / iCloud:</strong>
              <ol style={{ margin: '0.5rem 0 0 1.2rem', padding: 0, lineHeight: 1.6 }}>
                <li>Open <strong>Apple Mail</strong> on your Mac</li>
                <li>Select a mailbox in the sidebar</li>
                <li>Go to <strong>Mailbox</strong> → <strong>Export Mailbox…</strong></li>
                <li>Choose a save location — this creates a <strong>.mbox</strong> file</li>
                <li>Upload the .mbox file below</li>
              </ol>
              <div style={{ marginTop: '0.5rem', padding: '0.4rem', borderRadius: '6px', background: 'rgba(162,170,173,0.06)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                <strong>Bulk export:</strong> You can also request all your data from <a href="https://privacy.apple.com/" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Apple Data & Privacy</a> — this includes iCloud Mail data in MBOX format.
              </div>
            </div>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
            <input ref={fileRef} type="file" accept=".mbox,.eml" onChange={e => setFile(e.target.files?.[0] || null)} style={{ fontSize: '0.85rem', flex: 1, minWidth: '200px' }} />
            <button className="btn" onClick={doImport} disabled={importing} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem' }}>
              {importing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {importing ? 'Importing...' : 'Import Emails'}
            </button>
          </div>
        </div>
      )}

      {activeTab === 'drive' && (
        <div>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
            Download files from <a href="https://www.icloud.com/iclouddrive" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>iCloud Drive</a> (or from Finder on Mac), then upload them here.
          </p>
          <DocumentUpload onUploaded={() => {}} />
        </div>
      )}

      {result && <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: result.ok ? 'var(--success)' : 'var(--error)' }}>{result.ok ? '✅' : '❌'} {result.msg}</div>}
    </div>
  );
}
