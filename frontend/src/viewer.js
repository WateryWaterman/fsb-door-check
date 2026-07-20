// xeokit viewer 封装 — IFC 加载 + 拾取 + 高亮 + X-ray + 楼层隔离
// 对应 docs/CONTRACT.md §5 高亮映射规则
// xeokit 2.6.x WebIFCLoaderPlugin 需显式注入 web-ifc@0.0.51 的 {WebIFC, IfcAPI}(本地化,绕开 CDN Tracking Prevention)

import * as xeokit from '../lib/xeokit-sdk.es.min.js';
import * as WebIFC from '../lib/web-ifc-api.js';

const STATUS_COLORS = {
  pass:        [0.10, 0.50, 0.25],
  fail:        [0.94, 0.27, 0.27],
  non_passage: [0.55, 0.55, 0.60],
};

const WASM_PATH = '/lib/';

export class IfcViewer {
  constructor(canvasId) {
    this.canvasId = canvasId;
    if (!xeokit || !xeokit.Viewer) {
      throw new Error('xeokit SDK not loaded (import failed). Check /lib/xeokit-sdk.es.min.js');
    }
    if (!xeokit.WebIFCLoaderPlugin) {
      throw new Error('xeokit.WebIFCLoaderPlugin not found in this xeokit version.');
    }
    if (!WebIFC || !WebIFC.IfcAPI) {
      throw new Error('web-ifc-api.js not loaded (import failed). Check /lib/web-ifc-api.js');
    }
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
      throw new Error(`canvas #${canvasId} not found in DOM`);
    }
    this.viewer = new xeokit.Viewer({
      canvasId,
      transparent: true,
    });
    this.scene = this.viewer.scene;
    this.cameraFlight = this.viewer.cameraFlight;
    this._doorIds = new Set();
    this._storeyIds = new Set();
    this._storeyEntityMap = {};
    this.onPick = null;
    this._setupPicking();
    this._webIfcApiPromise = null;
  }

  _setXrayAlpha(alpha) {
    const m = this.scene && this.scene.xrayMaterial;
    if (m) m.alpha = alpha;
  }

  async _ensureWebIfcApi() {
    if (this._webIfcApiPromise) {
      return this._webIfcApiPromise;
    }
    this._webIfcApiPromise = (async () => {
      console.log('[viewer] initializing WebIFC IfcAPI, wasmPath=', WASM_PATH);
      const ifcAPI = new WebIFC.IfcAPI();
      ifcAPI.SetWasmPath(WASM_PATH);
      await ifcAPI.Init();
      console.log('[viewer] WebIFC IfcAPI ready');
      return ifcAPI;
    })();
    return this._webIfcApiPromise;
  }

  _destroyCurrentModel() {
    if (this._currentModel) {
      try {
        this._currentModel.destroy();
        console.log('[viewer] destroyed previous model');
      } catch (e) {
        console.warn('[viewer] destroy previous model failed:', e);
      }
      this._currentModel = null;
    }
    this._doorIds = new Set();
    this._storeyIds = new Set();
    this._storeyEntityMap = {};
  }

  async _loadModelBuffer(buffer, { label = 'primary' } = {}) {
    const ifcAPI = await this._ensureWebIfcApi();
    let webIFCLoader;
    try {
      webIFCLoader = new xeokit.WebIFCLoaderPlugin(this.viewer, {
        WebIFC,
        IfcAPI: ifcAPI,
      });
      console.log(`[viewer] WebIFCLoaderPlugin created (${label})`);
    } catch (e) {
      console.error('[viewer] WebIFCLoaderPlugin ctor failed:', e);
      throw new Error(`WebIFCLoaderPlugin ctor: ${e.message || e}`);
    }
    const modelId = `ifcModel_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    let model;
    try {
      model = webIFCLoader.load({ id: modelId, ifc: buffer, edges: true });
      console.log(`[viewer] load() returned (${label}), id=${modelId}, typeof=`, typeof model,
        'isPromise=', !!(model && typeof model.then === 'function'),
        'hasOn=', !!(model && typeof model.on === 'function'),
        'loaded=', !!(model && model.loaded));
    } catch (e) {
      console.error(`[viewer] load() threw (${label}):`, e);
      throw new Error(`WebIFCLoaderPlugin.load threw: ${e.message || e}`);
    }
    try {
      if (model && typeof model.then === 'function') {
        await model;
      } else if (model && typeof model.on === 'function') {
        await new Promise((resolve, reject) => {
          let settled = false;
          const done = () => { if (!settled) { settled = true; resolve(); } };
          if (model.loaded) { done(); return; }
          model.on('loaded', () => { console.log(`[viewer] model loaded event (${label})`); done(); });
          model.on('error', (err) => {
            console.error(`[viewer] model error event (${label}):`, err);
            if (!settled) { settled = true; reject(new Error(`model load error: ${err}`)); }
          });
          setTimeout(() => { if (!settled) { console.warn(`[viewer] load timeout 60s (${label}), continuing`); done(); } }, 60000);
        });
      } else {
        console.warn(`[viewer] model is neither Promise nor EventEmitter (${label}), assuming sync load`);
      }
      this._currentModel = model;
      return model;
    } catch (e) {
      if (model) {
        try { model.destroy(); } catch (_) { /* ignore */ }
      }
      throw e;
    }
  }

  async loadIfcArrayBuffer(buffer, { normalizeFallback = true, fetchNormalized } = {}) {
    console.log('[viewer] loadIfcArrayBuffer start, bytes=', buffer.byteLength,
      'fallback=', normalizeFallback);
    this._destroyCurrentModel();
    try {
      await this._loadModelBuffer(buffer, { label: 'primary' });
    } catch (primaryErr) {
      console.error('[viewer] primary load failed:', primaryErr.message || primaryErr);
      this._destroyCurrentModel();
      if (!normalizeFallback || !fetchNormalized) {
        throw primaryErr;
      }
      console.log('[viewer] falling back to backend normalize (ifcopenshell rewrite)...');
      const normBuffer = await fetchNormalized();
      console.log('[viewer] normalize buffer received, bytes=', normBuffer.byteLength);
      this._destroyCurrentModel();
      await this._loadModelBuffer(normBuffer, { label: 'normalized' });
    }
    try {
      this._indexDoorsAndStoreys();
    } catch (e) {
      console.warn('[viewer] _indexDoorsAndStoreys error:', e);
    }
    try {
      if (this.viewer.cameraFlight && typeof this.viewer.cameraFlight.flyTo === 'function') {
        this.viewer.cameraFlight.flyTo(this.viewer.scene);
        console.log('[viewer] flyTo done');
      } else {
        console.warn('[viewer] cameraFlight.flyTo not available');
      }
    } catch (e) {
      console.warn('[viewer] flyTo error:', e);
    }
    const objCount = Object.keys(this.viewer.scene.objects).length;
    console.log('[viewer] loadIfcArrayBuffer done, scene.objects count=', objCount);
    if (objCount === 0) {
      console.error('[viewer] WARNING: no objects in scene after load — IFC parsing likely failed');
    }
  }

  _indexDoorsAndStoreys() {
    this._doorIds = new Set();
    this._storeyIds = new Set();
    this._storeyEntityMap = {};
    const metaScene = this.viewer.metaScene;
    const metaObjects = metaScene ? metaScene.metaObjects : null;
    const objects = this.viewer.scene.objects;
    for (const id in objects) {
      const meta = metaObjects && metaObjects[id];
      if (meta) {
        if (meta.type === 'IfcDoor') this._doorIds.add(id);
      }
    }
    if (metaObjects) {
      for (const id in metaObjects) {
        const m = metaObjects[id];
        if (m && m.type === 'IfcBuildingStorey') this._storeyIds.add(id);
      }
      for (const storeyId of this._storeyIds) {
        const entitySet = new Set();
        const collect = (pid) => {
          entitySet.add(pid);
          const m = metaObjects[pid];
          if (m && m.children) {
            for (const c of m.children) collect(c.id);
          }
        };
        collect(storeyId);
        this._storeyEntityMap[storeyId] = entitySet;
      }
    }
    for (const id in objects) {
      const obj = objects[id];
      obj.pickable = this._doorIds.has(id);
    }
    console.log(`[viewer] indexed ${this._doorIds.size} doors, ${this._storeyIds.size} storeys, ${Object.keys(objects).length} total objects; non-doors set non-pickable`);
  }

  _setupPicking() {
    const input = (this.scene && this.scene.input) || this.viewer.input;
    if (!input || typeof input.on !== 'function') {
      console.warn('[viewer] input not available (xeokit 2.x API), picking disabled');
      return;
    }
    input.on('mouseclicked', (coords) => {
      const hit = this.viewer.scene.pick({ canvasPos: coords });
      if (hit && hit.entity && hit.entity.id) {
        const gid = hit.entity.id;
        if (this._doorIds.has(gid) && this.onPick) {
          this.onPick(gid);
        }
      }
    });
  }

  getDoorIds() {
    return Array.from(this._doorIds);
  }

  setNonDoorsXrayed(alpha = 0.5) {
    const objects = this.viewer.scene.objects;
    for (const id in objects) {
      const obj = objects[id];
      if (!this._doorIds.has(id)) {
        obj.xrayed = true;
        this._setXrayAlpha(alpha);
      } else {
        obj.xrayed = false;
      }
    }
  }

  colorizeByStatus(results) {
    for (const r of results) {
      const gid = r.door_global_id;
      const status = r.status;
      const obj = this.viewer.scene.objects[gid];
      if (!obj) continue;
      const color = STATUS_COLORS[status];
      if (!color) continue;
      obj.colorize = color;
      obj.xrayed = false;
    }
  }

  resetDoorColors() {
    for (const id of this._doorIds) {
      const obj = this.viewer.scene.objects[id];
      if (obj) {
        obj.colorize = null;
        obj.xrayed = false;
      }
    }
  }

  highlightFireExitDoors(fireExitGlobalIds, on) {
    const fireSet = new Set(fireExitGlobalIds);
    const scene = this.viewer.scene;
    if (scene.highlightMaterial) {
      scene.highlightMaterial.color = [0.937, 0.267, 0.267];
      scene.highlightMaterial.alpha = 0.6;
    }
    for (const id of this._doorIds) {
      const obj = scene.objects[id];
      if (!obj) continue;
      obj.highlighted = on && fireSet.has(id);
    }
  }

  highlightDoor(globalId) {
    const obj = this.viewer.scene.objects[globalId];
    if (obj) {
      obj.selected = true;
    }
  }

  unhighlightAll() {
    for (const id in this.viewer.scene.objects) {
      this.viewer.scene.objects[id].selected = false;
    }
  }

  flyTo(globalId) {
    const obj = this.viewer.scene.objects[globalId];
    if (!obj) return;
    const aabb = obj.aabb;
    if (!aabb) {
      this.viewer.cameraFlight.flyTo([obj]);
      return;
    }
    const cx = (aabb[0] + aabb[3]) / 2;
    const cy = (aabb[1] + aabb[4]) / 2;
    const cz = (aabb[2] + aabb[5]) / 2;
    const dx = aabb[3] - aabb[0];
    const dy = aabb[4] - aabb[1];
    const dz = aabb[5] - aabb[2];
    const maxDim = Math.max(dx, dy, dz);
    const padding = Math.max(maxDim * 2, 1.5);
    const expanded = [
      cx - padding, cy - padding, cz - padding,
      cx + padding, cy + padding, cz + padding,
    ];
    this.viewer.cameraFlight.flyTo({ aabb: expanded });
  }

  isolateStorey(storeyId) {
    const metaScene = this.viewer.metaScene;
    const metaObjects = metaScene ? metaScene.metaObjects : null;
    const objects = this.viewer.scene.objects;
    const visibleIds = new Set();
    if (storeyId !== null && metaObjects) {
      const collect = (parentId) => {
        visibleIds.add(parentId);
        const children = metaObjects[parentId];
        if (children && children.children) {
          for (const c of children.children) collect(c.id);
        }
      };
      collect(storeyId);
    }
    for (const id in objects) {
      objects[id].visible = (storeyId === null || visibleIds.has(id));
    }
  }

  focusDoors(doorGlobalIds) {
    const objects = this.viewer.scene.objects;
    for (const id in objects) {
      objects[id].visible = true;
    }
    for (const id in objects) {
      const obj = objects[id];
      if (this._doorIds.has(id)) {
        obj.xrayed = false;
      } else {
        obj.xrayed = true;
        this._setXrayAlpha(0.5);
      }
    }
  }

  focusStorey(storeyId) {
    if (!storeyId) {
      this.focusDoors([]);
      return;
    }
    this._setXrayAlpha(0.35);
    const storeyEntities = this._storeyEntityMap[storeyId] || new Set();
    const objects = this.scene.objects;
    for (const id in objects) {
      const obj = objects[id];
      const inStorey = storeyEntities.has(id);
      const isDoor = this._doorIds.has(id);
      if (inStorey) {
        obj.visible = true;
        obj.xrayed = !isDoor;
      } else {
        obj.visible = false;
        obj.xrayed = false;
      }
    }
  }

  showAllStoreys() {
    const objects = this.viewer.scene.objects;
    for (const id in objects) {
      objects[id].visible = true;
    }
  }
}

export const STATUS_COLOR_HEX = {
  pass:        '#15803d',
  fail:        '#ef4444',
  non_passage: '#8b8b96',
};
