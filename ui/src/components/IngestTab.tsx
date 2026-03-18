import { Upload } from 'lucide-react';
import DocumentUpload from './DocumentUpload';
import GoogleIntegrationSection from './GoogleIntegration';
import WhatsAppImportSection from './WhatsAppImport';

export default function IngestTab({ onRefresh }: { onRefresh: () => void }) {
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
