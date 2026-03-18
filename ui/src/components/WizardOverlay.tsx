import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Key, Bot, Save, ArrowRight, Loader2 } from 'lucide-react';
import type { Config } from '../types';

export default function WizardOverlay({ step, setStep, config, setConfig, onSave, saving, onClose }: any) {
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
