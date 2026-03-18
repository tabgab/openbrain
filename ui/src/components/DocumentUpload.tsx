import { useState, useRef } from 'react';
import axios from 'axios';
import { Loader2, Upload } from 'lucide-react';
import { API } from '../types';

export default function DocumentUpload({ onUploaded }: { onUploaded: () => void }) {
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
