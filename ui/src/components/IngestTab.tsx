import { useState, type ReactNode } from 'react';
import { Upload, Cloud, Mail, Phone } from 'lucide-react';
import DocumentUpload from './DocumentUpload';
import GoogleIntegrationSection from './GoogleIntegration';
import MicrosoftIntegration from './MicrosoftIntegration';
import DropboxIntegration from './DropboxIntegration';
import PCloudIntegration from './PCloudIntegration';
import ProtonImport from './ProtonImport';
import ICloudImport from './ICloudImport';
import TutaImport from './TutaImport';
import WhatsAppImportSection from './WhatsAppImport';

type Section = 'files' | 'cloud' | 'email' | 'messaging';

export default function IngestTab({ onRefresh }: { onRefresh: () => void }) {
  const [section, setSection] = useState<Section>('files');

  const sections: { key: Section; label: string; icon: ReactNode }[] = [
    { key: 'files', label: 'Files', icon: <Upload size={14} /> },
    { key: 'cloud', label: 'Cloud Storage', icon: <Cloud size={14} /> },
    { key: 'email', label: 'Email', icon: <Mail size={14} /> },
    { key: 'messaging', label: 'Messaging', icon: <Phone size={14} /> },
  ];

  return (
    <div>
      {/* Section tabs */}
      <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {sections.map(s => (
          <button key={s.key} onClick={() => setSection(s.key)}
            className={`btn ${section === s.key ? '' : 'btn-secondary'}`}
            style={{ padding: '0.45rem 1rem', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            {s.icon} {s.label}
          </button>
        ))}
      </div>

      {/* Files section */}
      {section === 'files' && (
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
      )}

      {/* Cloud Storage section */}
      {section === 'cloud' && (
        <>
          <GoogleIntegrationSection />
          <MicrosoftIntegration />
          <DropboxIntegration />
          <PCloudIntegration />
        </>
      )}

      {/* Email section */}
      {section === 'email' && (
        <>
          <ProtonImport />
          <ICloudImport />
          <TutaImport />
        </>
      )}

      {/* Messaging section */}
      {section === 'messaging' && (
        <WhatsAppImportSection onImported={onRefresh} />
      )}
    </div>
  );
}
