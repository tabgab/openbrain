import { useState } from 'react';
import axios from 'axios';
import {
  Search, Loader2, X, ListTree, Bot, AlertCircle, Pencil, Trash2, Check
} from 'lucide-react';
import { API } from '../types';
import type { Memory, Health } from '../types';
export default function DashboardTab({ memories, health, onOpenWizard, onRefresh }: { memories: Memory[]; health: Health | null; onOpenWizard: () => void; onRefresh: () => void }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Memory[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const doSearch = async () => {
    if (!searchQuery.trim()) { setSearchResults(null); return; }
    setSearching(true);
    try {
      const res = await axios.get(`${API}/memories/search`, { params: { q: searchQuery.trim() } });
      setSearchResults(res.data.memories || []);
    } catch { setSearchResults([]); }
    finally { setSearching(false); }
  };

  const clearSearch = () => { setSearchQuery(''); setSearchResults(null); };

  const startEdit = (m: Memory) => { setEditingId(m.id); setEditContent(m.content); };
  const cancelEdit = () => { setEditingId(null); setEditContent(''); };
  const saveEdit = async () => {
    if (!editingId) return;
    try {
      await axios.put(`${API}/memories/${editingId}`, { content: editContent });
      cancelEdit();
      onRefresh();
      if (searchResults) doSearch();
    } catch (e) { alert('Failed to update memory.'); }
  };

  const confirmDelete = async (id: string) => {
    try {
      await axios.delete(`${API}/memories/${id}`);
      setDeletingId(null);
      onRefresh();
      if (searchResults) doSearch();
    } catch (e) { alert('Failed to delete memory.'); }
  };

  const displayList = searchResults !== null ? searchResults : memories;

  return (
    <div>
      {!health?.telegram.ok && (
        <div className="event-card" style={{ borderColor: 'rgba(239,68,68,0.3)', marginBottom: '1.5rem', background: 'rgba(239,68,68,0.05)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <AlertCircle size={20} color="var(--error)" />
            <strong style={{ color: 'var(--error)' }}>Telegram bot is not connected.</strong>
            <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
              {health?.telegram.error || 'Unknown error.'} No messages will be captured until this is resolved.
            </span>
            <button onClick={onOpenWizard} className="btn" style={{ marginLeft: 'auto', padding: '0.35rem 0.9rem', fontSize: '0.85rem' }}>
              Fix in Wizard
            </button>
          </div>
        </div>
      )}

      {/* Search bar & Document Upload */}
      <div className="glass-panel" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.75rem' }}>
          <Search size={18} color="var(--text-secondary)" />
          <input
            type="text"
            className="input-field"
            placeholder="Search memories..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && doSearch()}
            style={{ flex: 1, margin: 0 }}
          />
          <button className="btn" onClick={doSearch} disabled={searching} style={{ padding: '0.45rem 1rem', fontSize: '0.85rem' }}>
            {searching ? <Loader2 size={16} className="animate-spin" /> : 'Search'}
          </button>
          {searchResults !== null && (
            <button className="btn btn-secondary" onClick={clearSearch} style={{ padding: '0.45rem 0.8rem', fontSize: '0.85rem' }}>
              <X size={14} /> Clear
            </button>
          )}
        </div>
      </div>

      <div className="glass-panel">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
          <ListTree color="var(--accent)" size={20} />
          <h2>{searchResults !== null ? `Search Results (${displayList.length})` : `Recent Memories (${displayList.length})`}</h2>
        </div>
        {displayList.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--text-secondary)' }}>
            <Bot size={48} opacity={0.4} style={{ margin: '0 auto 1rem auto', display: 'block' }} />
            {searchResults !== null
              ? <p style={{ fontSize: '1.1rem', fontWeight: 500 }}>No memories match your search.</p>
              : <>
                  <p style={{ fontSize: '1.1rem', fontWeight: 500 }}>Your Open Brain is empty.</p>
                  <p style={{ fontSize: '0.9rem' }}>Once Telegram is connected, send a message to your bot to create your first memory!</p>
                </>
            }
          </div>
        ) : displayList.map(m => (
          <div key={m.id} className="event-card" style={{ position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', flexWrap: 'wrap', gap: '0.5rem' }}>
              <span className="status-badge success">{m.metadata?.category || 'memory'}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {m.source_type} · {new Date(m.created_at).toLocaleString()}
                </span>
                {editingId !== m.id && deletingId !== m.id && (
                  <>
                    <button onClick={() => startEdit(m)} title="Edit" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.2rem', color: 'var(--text-secondary)', display: 'flex' }}>
                      <Pencil size={14} />
                    </button>
                    <button onClick={() => setDeletingId(m.id)} title="Delete" style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.2rem', color: 'var(--text-secondary)', display: 'flex' }}>
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Delete confirmation */}
            {deletingId === m.id && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', borderRadius: '8px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', marginBottom: '0.5rem' }}>
                <AlertCircle size={16} color="var(--error)" />
                <span style={{ fontSize: '0.85rem', color: 'var(--error)', flex: 1 }}>Delete this memory permanently?</span>
                <button className="btn" onClick={() => confirmDelete(m.id)} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem', background: 'var(--error)' }}>
                  <Trash2 size={13} /> Delete
                </button>
                <button className="btn btn-secondary" onClick={() => setDeletingId(null)} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
                  Cancel
                </button>
              </div>
            )}

            {/* Edit mode */}
            {editingId === m.id ? (
              <div>
                <textarea
                  className="input-field"
                  value={editContent}
                  onChange={e => setEditContent(e.target.value)}
                  rows={4}
                  style={{ width: '100%', resize: 'vertical', fontFamily: 'inherit', marginBottom: '0.5rem' }}
                />
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button className="btn" onClick={saveEdit} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
                    <Check size={14} /> Save
                  </button>
                  <button className="btn btn-secondary" onClick={cancelEdit} style={{ padding: '0.3rem 0.75rem', fontSize: '0.8rem' }}>
                    <X size={14} /> Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div onClick={() => setExpandedId(expandedId === m.id ? null : m.id)} style={{ cursor: 'pointer' }}>
                {expandedId === m.id ? (
                  <p style={{ color: 'var(--text-primary)', marginBottom: '0.5rem', whiteSpace: 'pre-wrap', maxHeight: '60vh', overflowY: 'auto' }}>{m.content}</p>
                ) : (
                  <p style={{ color: 'var(--text-primary)', marginBottom: '0.5rem' }}>{m.content.substring(0, 200)}{m.content.length > 200 ? '…' : ''}</p>
                )}
                {m.metadata?.summary && <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>Summary: {m.metadata.summary}</p>}
                {m.content.length > 200 && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--accent)', opacity: 0.8 }}>{expandedId === m.id ? 'Click to collapse' : 'Click to expand'}</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
