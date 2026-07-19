const API_BASE = '';

export const api = {
  async uploadIfc(file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(`${API_BASE}/model/upload`, { method: 'POST', body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `upload failed (${r.status})`);
    }
    return r.json();
  },

  async getPresets() {
    const r = await fetch(`${API_BASE}/presets`);
    if (!r.ok) throw new Error(`presets failed (${r.status})`);
    return r.json();
  },

  async getDoor(globalId, sessionId) {
    const r = await fetch(`${API_BASE}/doors/${encodeURIComponent(globalId)}?session=${encodeURIComponent(sessionId)}`);
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `get door failed (${r.status})`);
    }
    return r.json();
  },

  async runCheck(sessionId) {
    const r = await fetch(`${API_BASE}/check/${sessionId}`, { method: 'POST' });
    if (!r.ok) throw new Error(`check failed (${r.status})`);
    return r.json();
  },

  async override(sessionId, payload) {
    const r = await fetch(`${API_BASE}/override/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `override failed (${r.status})`);
    }
    return r.json();
  },

  async getSummary(sessionId) {
    const r = await fetch(`${API_BASE}/model/${sessionId}/summary`);
    if (!r.ok) throw new Error(`summary failed (${r.status})`);
    return r.json();
  },
};
