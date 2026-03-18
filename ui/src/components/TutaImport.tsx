import { useState, useRef } from 'react';
import axios from 'axios';
import { Loader2, Upload, Mail, Shield } from 'lucide-react';
import { API } from '../types';

export default function TutaImport() {
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
      form.append('source_service', 'tuta_mail');
      form.append('chat_name', 'Tuta Mail Import');
      const res = await axios.post(`${API}/email-import/${endpoint}`, form);
      if (res.data.ingested > 0) {
        setResult({ ok: true, msg: `Imported ${res.data.ingested} emails from Tuta` });
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
        <Shield size={20} color="#840010" />
        <h2 style={{ margin: 0, flex: 1 }}>Tuta</h2>
      </div>

      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '0.75rem', lineHeight: 1.5 }}>
        Tuta (formerly Tutanota) is end-to-end encrypted — there's no third-party API. Export your emails and import them here.
      </p>

      <button onClick={() => setShowGuide(v => !v)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--accent)', fontSize: '0.82rem', padding: '0 0 0.5rem 0' }}>
        {showGuide ? 'Hide' : 'Show'} Export Guide
      </button>
      {showGuide && (
        <div style={{ padding: '0.75rem', borderRadius: '8px', background: 'rgba(132,0,16,0.08)', border: '1px solid rgba(132,0,16,0.2)', marginBottom: '0.75rem', fontSize: '0.85rem' }}>
          <strong>How to export from Tuta:</strong>
          <ol style={{ margin: '0.5rem 0 0 1.2rem', padding: 0, lineHeight: 1.6 }}>
            <li>Open <a href="https://app.tuta.com" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Tuta</a> in your browser or desktop app</li>
            <li>Select emails you want to export (use Ctrl/Cmd+A for all in a folder)</li>
            <li>Click the <strong>⋮</strong> menu → <strong>Export</strong></li>
            <li>Tuta exports individual <strong>.eml</strong> files (possibly zipped)</li>
            <li>If you receive a .zip file, extract it first</li>
            <li>Upload the .eml file(s) below</li>
          </ol>
          <div style={{ marginTop: '0.5rem', padding: '0.4rem', borderRadius: '6px', background: 'rgba(132,0,16,0.06)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
            <strong>Desktop app:</strong> The <a href="https://tuta.com/blog/desktop-clients" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>Tuta desktop app</a> supports bulk email export. It's the easiest way to export large mailboxes.
          </div>
        </div>
      )}

      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
        <input ref={fileRef} type="file" accept=".mbox,.eml" multiple onChange={e => setFile(e.target.files?.[0] || null)} style={{ fontSize: '0.85rem', flex: 1, minWidth: '200px' }} />
        <button className="btn" onClick={doImport} disabled={importing} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem', background: '#840010' }}>
          {importing ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
          {importing ? 'Importing...' : 'Import Emails'}
        </button>
      </div>

      <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', margin: '0.25rem 0 0' }}>
        <Mail size={12} style={{ verticalAlign: 'middle' }} /> Supports .mbox and .eml files
      </p>

      {result && <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: result.ok ? 'var(--success)' : 'var(--error)' }}>{result.ok ? '✅' : '❌'} {result.msg}</div>}
    </div>
  );
}
