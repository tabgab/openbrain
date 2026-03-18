import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Brain, Loader2, Search, Send, Sparkles, HelpCircle, BookmarkPlus,
  CheckCircle2, Cpu
} from 'lucide-react';
import { API } from '../types';

interface ChatEntry {
  role: 'user' | 'brain';
  content: string;
  type?: 'answer' | 'memory';
  category?: string;
  summary?: string;
  memory_id?: string;
  sources?: { id: string; source_type: string; summary: string }[];
  thinking?: string[];
  mode?: string;
  timestamp: Date;
}

export default function ChatTab({ onMemoryAdded }: { onMemoryAdded: () => void }) {
  const [messages, setMessages] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [mode, setMode] = useState<'' | 'question' | 'memory'>('');
  const [searchMode, setSearchMode] = useState<'advanced' | 'memory_only'>('advanced');
  const [liveThinking, setLiveThinking] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, liveThinking]);

  const send = async () => {
    const text = input.trim();
    if (!text || sending) return;

    const userMsg: ChatEntry = { role: 'user', content: text, mode: mode || 'auto', timestamp: new Date() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setSending(true);
    setLiveThinking([]);

    try {
      const resp = await fetch(`${API}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, force_mode: mode, search_mode: searchMode }),
      });

      if (!resp.ok || !resp.body) throw new Error('Stream failed');

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === 'thinking') {
              setLiveThinking(prev => [...prev, data.step]);
            } else if (data.type === 'answer') {
              setLiveThinking(prev => {
                const finalThinking = [...prev];
                setMessages(old => [...old, {
                  role: 'brain', content: data.content, type: 'answer',
                  sources: data.sources, thinking: finalThinking, timestamp: new Date(),
                }]);
                return [];
              });
            } else if (data.type === 'memory') {
              setLiveThinking([]);
              setMessages(old => [...old, {
                role: 'brain', content: data.content, type: 'memory',
                category: data.category, summary: data.summary,
                memory_id: data.memory_id, timestamp: new Date(),
              }]);
              onMemoryAdded();
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (err: any) {
      setLiveThinking([]);
      const errMsg = err?.message || 'Something went wrong';
      setMessages(prev => [...prev, { role: 'brain', content: `Error: ${errMsg}`, timestamp: new Date() }]);
    } finally {
      setSending(false);
      setLiveThinking([]);
      inputRef.current?.focus();
    }
  };

  const modeLabel = mode === 'question' ? 'Ask' : mode === 'memory' ? 'Store' : 'Auto';
  const modeColor = mode === 'question' ? '#3b82f6' : mode === 'memory' ? '#10b981' : 'var(--text-secondary)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 220px)', minHeight: '400px' }}>
      <div className="glass-panel" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Chat header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--glass-border)' }}>
          <Brain size={20} color="var(--accent)" />
          <h2 style={{ margin: 0, flex: 1 }}>Chat with Open Brain</h2>
          <div style={{ display: 'flex', gap: '0.25rem', fontSize: '0.8rem' }}>
            {([['', 'Auto'], ['question', 'Ask'], ['memory', 'Store']] as ['' | 'question' | 'memory', string][]).map(([m, label]) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`btn ${mode === m ? '' : 'btn-secondary'}`}
                style={{ padding: '0.25rem 0.6rem', fontSize: '0.78rem' }}
                title={m === '' ? 'Auto-detect question vs memory' : m === 'question' ? 'Force as question (search & answer)' : 'Force as memory (store)'}
              >
                {m === '' && <Sparkles size={12} />}
                {m === 'question' && <HelpCircle size={12} />}
                {m === 'memory' && <BookmarkPlus size={12} />}
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', paddingRight: '0.5rem' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-secondary)' }}>
              <Brain size={48} opacity={0.3} style={{ margin: '0 auto 1rem' }} />
              <p style={{ fontSize: '1.05rem', fontWeight: 500, marginBottom: '0.5rem' }}>Talk to your Open Brain</p>
              <p style={{ fontSize: '0.85rem', maxWidth: '400px', margin: '0 auto' }}>
                Ask questions about your stored memories, or type something to save as a new memory.
                The system auto-detects your intent — or use the mode toggle above.
              </p>
            </div>
          )}
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: '0.75rem',
              }}
            >
              <div style={{
                maxWidth: '75%',
                padding: '0.75rem 1rem',
                borderRadius: msg.role === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                background: msg.role === 'user'
                  ? 'linear-gradient(135deg, #3b82f6, #6366f1)'
                  : 'var(--glass-bg)',
                border: msg.role === 'brain' ? '1px solid var(--glass-border)' : 'none',
                color: msg.role === 'user' ? 'white' : 'var(--text-primary)',
              }}>
                {/* User mode badge */}
                {msg.role === 'user' && msg.mode && (
                  <div style={{ fontSize: '0.7rem', opacity: 0.7, marginBottom: '0.25rem' }}>
                    {msg.mode === 'auto' ? '✨ auto' : msg.mode === 'question' ? '❓ question' : '📝 memory'}
                  </div>
                )}

                {/* Brain response type badge */}
                {msg.role === 'brain' && msg.type && (
                  <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: '0.3rem',
                    fontSize: '0.72rem', fontWeight: 600, marginBottom: '0.4rem',
                    padding: '0.15rem 0.5rem', borderRadius: '999px',
                    background: msg.type === 'answer' ? 'rgba(59,130,246,0.15)' : 'rgba(16,185,129,0.15)',
                    color: msg.type === 'answer' ? '#60a5fa' : '#34d399',
                  }}>
                    {msg.type === 'answer' ? <><Search size={10} /> Answer</> : <><CheckCircle2 size={10} /> Stored</>}
                  </div>
                )}

                {/* Collapsible thinking process */}
                {msg.thinking && msg.thinking.length > 0 && (
                  <details style={{ marginBottom: '0.4rem' }}>
                    <summary style={{ cursor: 'pointer', fontSize: '0.72rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '0.3rem', userSelect: 'none' }}>
                      <Cpu size={11} /> Thinking process ({msg.thinking.length} steps)
                    </summary>
                    <div style={{ marginTop: '0.3rem', padding: '0.4rem 0.6rem', borderRadius: '6px', background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.12)', fontSize: '0.75rem', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                      {msg.thinking.map((step, si) => (
                        <div key={si} style={{ display: 'flex', gap: '0.4rem', alignItems: 'flex-start', marginBottom: si < msg.thinking!.length - 1 ? '0.2rem' : 0 }}>
                          <span style={{ color: 'rgba(139,92,246,0.6)', fontWeight: 600, flexShrink: 0 }}>{si + 1}.</span>
                          <span>{step}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                )}

                <div style={{ whiteSpace: 'pre-wrap', fontSize: '0.9rem', lineHeight: 1.5 }}>{msg.content}</div>

                {/* Memory saved info */}
                {msg.type === 'memory' && msg.category && (
                  <div style={{ marginTop: '0.4rem', fontSize: '0.78rem', opacity: 0.7 }}>
                    Category: {msg.category}{msg.summary ? ` · ${msg.summary}` : ''}
                  </div>
                )}

                {/* Sources for answers */}
                {msg.sources && msg.sources.length > 0 && (
                  <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--glass-border)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                    <span style={{ fontWeight: 600 }}>Sources:</span>
                    {msg.sources.map((s, j) => (
                      <div key={j} style={{ marginTop: '0.2rem', paddingLeft: '0.5rem' }}>
                        · <span style={{ color: 'var(--accent)' }}>{s.source_type}</span>: {s.summary}
                      </div>
                    ))}
                  </div>
                )}

                <div style={{ fontSize: '0.68rem', opacity: 0.5, marginTop: '0.3rem', textAlign: msg.role === 'user' ? 'right' : 'left' }}>
                  {msg.timestamp.toLocaleTimeString()}
                </div>
              </div>
            </motion.div>
          ))}
          {sending && (
            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: '0.75rem' }}>
              <div style={{ padding: '0.75rem 1rem', borderRadius: '16px 16px 16px 4px', background: 'var(--glass-bg)', border: '1px solid rgba(139,92,246,0.25)', maxWidth: '75%', minWidth: '200px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: liveThinking.length > 0 ? '0.4rem' : 0 }}>
                  <Loader2 size={14} className="animate-spin" color="#a78bfa" />
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#a78bfa' }}>
                    <Cpu size={11} style={{ display: 'inline', verticalAlign: '-1px', marginRight: '0.2rem' }} />
                    Thinking{liveThinking.length > 0 ? ` (${liveThinking.length} steps)` : '...'}
                  </span>
                </div>
                {liveThinking.length > 0 && (
                  <div style={{ padding: '0.35rem 0.5rem', borderRadius: '6px', background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.12)', fontSize: '0.73rem', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
                    {liveThinking.map((step, si) => (
                      <div key={si} style={{ display: 'flex', gap: '0.35rem', alignItems: 'flex-start', marginBottom: si < liveThinking.length - 1 ? '0.15rem' : 0, opacity: si === liveThinking.length - 1 ? 1 : 0.6 }}>
                        <span style={{ color: 'rgba(139,92,246,0.6)', fontWeight: 600, flexShrink: 0 }}>{si + 1}.</span>
                        <span>{step}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div style={{ paddingTop: '0.75rem', borderTop: '1px solid var(--glass-border)', marginTop: '0.5rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <div style={{ fontSize: '0.75rem', color: modeColor, alignSelf: 'center', minWidth: '40px', textAlign: 'center', fontWeight: 600 }}>
              {modeLabel}
            </div>
            <textarea
              ref={inputRef as any}
              className="input-field"
              placeholder={mode === 'question' ? 'Ask a question...' : mode === 'memory' ? 'Type a memory to store...' : 'Ask a question or store a memory...'}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              disabled={sending}
              rows={1}
              style={{ flex: 1, margin: 0, resize: 'none', minHeight: '38px', maxHeight: '150px', overflow: 'auto' }}
              autoFocus
            />
            <button className="btn" onClick={send} disabled={sending || !input.trim()} style={{ padding: '0.5rem 1rem' }}>
              {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginTop: '0.4rem', paddingLeft: '48px' }}>
            <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginRight: '0.2rem' }}>Search:</span>
            {([['memory_only', '🧠 Memory Only'], ['advanced', '🔎 Advanced']] as ['memory_only' | 'advanced', string][]).map(([m, label]) => (
              <button
                key={m}
                onClick={() => setSearchMode(m)}
                style={{
                  padding: '0.15rem 0.5rem', fontSize: '0.7rem', borderRadius: '10px', cursor: 'pointer',
                  border: `1px solid ${searchMode === m ? (m === 'advanced' ? '#a78bfa' : '#60a5fa') : 'rgba(255,255,255,0.1)'}`,
                  background: searchMode === m ? (m === 'advanced' ? 'rgba(167,139,250,0.15)' : 'rgba(96,165,250,0.15)') : 'transparent',
                  color: searchMode === m ? 'var(--text-primary)' : 'var(--text-secondary)',
                  transition: 'all 0.15s',
                }}
                title={m === 'memory_only' ? 'Search only stored memories' : 'Search memories + Google Calendar + Gmail'}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
