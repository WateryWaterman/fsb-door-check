// xeokit viewer 封装 — IFC 加载 + 拾取 + 高亮 + X-ray + 楼层隔离
// 对应 docs/CONTRACT.md §5 高亮映射规则

const STATUS_COLORS = {
  pass:       [0.133, 0.773, 0.369],
  fail:       [0.937, 0.267, 0.267],
  unknown:    [0.918, 0.702, 0.031],
  overridden: [0.231, 0.510, 0.965],
};

export class IfcViewer {
  constructor(canvasId) {
    this.canvasId = canvasId;
    this.viewer = new xeokit.Viewer({
      canvasId,
      transparent: true,
      dtxEnabled: true,
    });
    this.scene = this.viewer.scene;
    this.cameraFlight = this.viewer.cameraFlight;
    this._doorIds = new Set();
    this._storeyObjects = {};
    this.onPick = null;
    this._setupPicking();
  }

  async loadIfcUrl(url, wasmPath) {
    const ifcLoader = new xeokit.IfcLoader();
    ifcLoader.loadWasm(wasmPath || 'https://cdn.jsdelivr.net/npm/@xeokit/xeokit-sdk/dist/');
    await ifcLoader.load({ src: url, viewer: this.viewer });
    this.viewer.cameraFlight.flyTo(this.viewer.scene);
    this._indexDoorsAndStoreys();
  }

  _indexDoorsAndStoreys() {
    this._doorIds = new Set();
    this._storeyObjects = {};
    const objects = this.viewer.scene.objects;
    for (const id in objects) {
      const obj = objects[id];
      if (obj.isType && obj.isType('IfcDoor')) {
        this._doorIds.add(id);
      }
      const meta = obj.meta || {};
      if (meta.type === 'IfcBuildingStorey' || (obj.isType && obj.isType('IfcBuildingStorey'))) {
        this._storeyObjects[id] = obj;
      }
    }
  }

  _setupPicking() {
    this.viewer.input.on('mouseclicked', (coords) => {
      const hit = this.viewer.scene.pick({ canvasPos: coords });
      if (hit && hit.entity && hit.entity.id) {
        const gid = hit.entity.id;
        if (this.onPick) this.onPick(gid);
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
        if (obj.xrayMaterial) obj.xrayMaterial.alpha = alpha;
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
      if (status === 'pass') {
        obj.xrayed = true;
        if (obj.xrayMaterial) obj.xrayMaterial.alpha = 0.3;
      } else {
        obj.xrayed = false;
      }
    }
  }

  resetDoorColors() {
    for (const id of this._doorIds) {
      const obj = this.viewer.scene.objects[id];
      if (obj) {
        obj.colorize = null;
        obj.xrayed = true;
        if (obj.xrayMaterial) obj.xrayMaterial.alpha = 0.3;
      }
    }
  }

  highlightDoor(globalId) {
    const obj = this.viewer.scene.objects[globalId];
    if (obj) {
      obj.selected = true;
      obj.xrayed = false;
    }
  }

  unhighlightAll() {
    for (const id in this.viewer.scene.objects) {
      this.viewer.scene.objects[id].selected = false;
    }
  }

  flyTo(globalId) {
    const obj = this.viewer.scene.objects[globalId];
    if (obj) {
      this.viewer.cameraFlight.flyTo([obj]);
    }
  }

  isolateStorey(storeyId) {
    const objects = this.viewer.scene.objects;
    for (const id in objects) {
      const obj = objects[id];
      const objStoreyId = (obj.meta && obj.meta.parent) ? obj.meta.parent : null;
      if (storeyId === null) {
        obj.visible = true;
      } else if (objStoreyId === storeyId) {
        obj.visible = true;
      } else {
        obj.visible = false;
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
  pass: '#22c55e',
  fail: '#ef4444',
  unknown: '#eab308',
  overridden: '#3b82f6',
};
