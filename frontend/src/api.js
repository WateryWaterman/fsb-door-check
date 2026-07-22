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

  async normalizeIfc(file) {
    const fd = new FormData();
    fd.append('file', file);
    const r = await fetch(`${API_BASE}/model/normalize`, { method: 'POST', body: fd });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `normalize failed (${r.status})`);
    }
    return r.arrayBuffer();
  },

  async deleteSession(sessionId) {
    try {
      await fetch(`${API_BASE}/model/${sessionId}`, { method: 'DELETE' });
    } catch (e) {
      console.warn('[api] deleteSession failed (ignored on unload):', e);
    }
  },

  async exportModel(sessionId, format) {
    const r = await fetch(`${API_BASE}/export/${sessionId}?format=${encodeURIComponent(format)}`, { method: 'POST' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      if (r.status === 501 && err?.detail) {
        const e = new Error(err.detail);
        e.status = 501;
        e.designDoc = err.design_doc;
        e.planned = err.planned_formats;
        throw e;
      }
      throw new Error(err.detail || `export failed (${r.status})`);
    }
    return r.blob();
  },

  async deleteAllThresholdOverrides(sessionId) {
    const r = await fetch(`${API_BASE}/override/${sessionId}/threshold/all`, { method: 'DELETE' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `delete all thresholds failed (${r.status})`);
    }
    return r.json();
  },

  async batchChecked(sessionId, globalIds, value) {
    const r = await fetch(`${API_BASE}/override/${sessionId}/checked/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ global_ids: globalIds, value }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `batch checked failed (${r.status})`);
    }
    return r.json();
  },

  async saveThresholdTable(sessionId, bands) {
    const r = await fetch(`${API_BASE}/override/${sessionId}/threshold/table`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bands }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `save threshold table failed (${r.status})`);
    }
    return r.json();
  },

  async resetThresholdTable(sessionId) {
    const r = await fetch(`${API_BASE}/override/${sessionId}/threshold/table`, { method: 'DELETE' });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `reset threshold table failed (${r.status})`);
    }
    return r.json();
  },

  async postEmailReport(sessionId, payload) {
    const r = await fetch(`${API_BASE}/export/${sessionId}/email_report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || `email report failed (${r.status})`);
    }
    return r.json();
  },
};
