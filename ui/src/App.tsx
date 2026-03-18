import { useEffect, useState, useCallback, useRef } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain, Loader2, MessageSquare, Activity, Settings as SettingsIcon,
  Terminal, Download
} from 'lucide-react';
import { API, EMPTY_CONFIG } from './types';
import type { Tab, Config, Health, Memory, LogEntry } from './types';
import HealthBar from './components/HealthBar';
import DashboardTab from './components/DashboardTab';
import ChatTab from './components/ChatTab';
import IngestTab from './components/IngestTab';
import SettingsTab from './components/SettingsTab';
import LogsTab from './components/LogsTab';
import WizardOverlay from './components/WizardOverlay';

export default function App() {
  const [tab, setTab] = useState<Tab>('dashboard');
  const [health, setHealth] = useState<Health | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [config, setConfig] = useState<Config>(EMPTY_CONFIG);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');
  const settingsDirtyRef = useRef(false);
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
      const payload = partial || {};
      await axios.post(`${API}/config`, payload);
      settingsDirtyRef.current = false;
      setSaveMsg('✅ Saved! Restarting backend...');
      closeWizard();
      // Auto-restart backend services
      try {
        await axios.post(`${API}/restart`);
        setSaveMsg('✅ Saved & backend restarted successfully.');
      } catch {
        setSaveMsg('✅ Saved! Backend restart failed — you may need to restart manually.');
      }
      fetchAll();
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Unknown error';
      setSaveMsg(`❌ Failed to save: ${detail}`);
    } finally {
      setSaving(false);
    }
  };

  const trySetTab = (newTab: Tab) => {
    if (tab === 'settings' && newTab !== 'settings' && settingsDirtyRef.current) {
      const action = window.confirm('You have unsaved settings changes.\n\nPress OK to save and switch, or Cancel to discard and switch.');
      if (action) {
        // Save then switch
        saveConfig().then(() => setTab(newTab));
        return;
      }
      // Discard
      settingsDirtyRef.current = false;
    }
    setTab(newTab);
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
              onClick={() => trySetTab(t)}
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
          {tab === 'settings' && <SettingsTab config={config} setConfig={setConfig} onSave={saveConfig} saving={saving} saveMsg={saveMsg} onDirtyChange={(d: boolean) => { settingsDirtyRef.current = d; }} />}
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
