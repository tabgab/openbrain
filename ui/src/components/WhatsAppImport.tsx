import { useState, useRef } from 'react';
import axios from 'axios';
import { Phone, Upload, Loader2 } from 'lucide-react';
import { API } from '../types';

export default function WhatsAppImportSection({ onImported }: { onImported: () => void }) {
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
