import { IfcViewer, STATUS_COLOR_HEX } from './viewer.js';
import { api } from './api.js';

window.STATUS_COLOR_HEX = STATUS_COLOR_HEX;

window.addEventListener('alpine:init', () => {
  Alpine.data('fsbApp', () => ({
    sessionId: null,
    model: null,
    presets: null,
    selectedDoorId: null,
    selectedDoorDetail: null,
    viewer: null,
    loading: false,
    loadingMsg: '',
    error: null,
    activeTab: 'regulation',
    filterStatus: 'all',
    filterStoreyId: null,
    failCursor: 0,
    unknownCursor: 0,
    thrEditRowIdx: 0,
    thrEditWidthMm: '',
    exportMsg: null,

    get unknownsList() {
      let list = this.doors.filter(d => !d.check_result || d.check_result.status === 'non_passage');
      if (this.filterStoreyId) list = list.filter(d => d.storey_global_id === this.filterStoreyId);
      list = this._applySearch(list);
      return list;
    },
    exportMsgKind: 'info',
    searchQuery: '',
    highlightFireExit: false,
    thresholdDialogOpen: false,
    thrDialogRows: [],

    init() {
      this.$nextTick(() => {
        try {
          this.viewer = new IfcViewer('viewerCanvas');
          this.viewer.onPick = (gid) => this.selectDoor(gid);
          this.loadPresets();
        } catch (e) {
          console.error('viewer init error:', e);
          this.error = `init failed: ${e.message}. If xeokit CDN issue, check F12 console.`;
        }
      });
      window.addEventListener('beforeunload', () => {
        if (this.sessionId) {
          api.deleteSession(this.sessionId);
        }
      });
    },

    async loadPresets() {
      try {
        this.presets = await api.getPresets();
      } catch (e) {
        this.error = `load presets failed: ${e.message}`;
      }
    },

    get hasModel() { return this.model !== null; },
    get doors() { return this.model ? this.model.doors : []; },
    get spaces() { return this.model ? this.model.spaces : []; },
    get storeys() { return this.model ? this.model.storeys : []; },
    get summary() { return this.model ? this.model.summary : null; },

    get filteredDoors() {
      let list = this.doors;
      if (this.filterStatus === 'checked') {
        list = list.filter(d => d.is_checked);
      } else if (this.filterStatus === 'unchecked') {
        list = list.filter(d => !d.is_checked);
      } else if (this.filterStatus === 'non_passage') {
        list = list.filter(d => !d.check_result || d.check_result.status === 'non_passage');
      } else if (this.filterStatus !== 'all') {
        list = list.filter(d => d.check_result && d.check_result.status === this.filterStatus);
      }
      if (this.filterStoreyId) {
        list = list.filter(d => d.storey_global_id === this.filterStoreyId);
      }
      const q = (this.searchQuery || '').trim().toLowerCase();
      if (q) {
        list = list.filter(d => {
          const gid = (d.global_id || '').toLowerCase();
          const name = (d.name || '').toLowerCase();
          return gid.includes(q) || name.includes(q);
        });
      }
      return list;
    },

    get failsList() {
      let list = this.doors.filter(d => d.check_result && d.check_result.status === 'fail');
      if (this.filterStoreyId) list = list.filter(d => d.storey_global_id === this.filterStoreyId);
      list = this._applySearch(list);
      return list;
    },

    _applySearch(list) {
      const q = (this.searchQuery || '').trim().toLowerCase();
      if (!q) return list;
      return list.filter(d => {
        const gid = (d.global_id || '').toLowerCase();
        const name = (d.name || '').toLowerCase();
        return gid.includes(q) || name.includes(q);
      });
    },

    get storeyDoorCounts() {
      const m = {};
      for (const d of this.doors) {
        if (d.storey_global_id) m[d.storey_global_id] = (m[d.storey_global_id] || 0) + 1;
      }
      return m;
    },

    get currentThresholdRow() {
      const rows = this.presets?.default?.table_b2_thresholds || [];
      return rows[this.thrEditRowIdx] || null;
    },

    get selectedDoor() {
      if (!this.selectedDoorId || !this.model) return null;
      return this.doors.find(d => d.global_id === this.selectedDoorId) || null;
    },

    async onFileSelected(event) {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      if (!this.viewer) {
        this.error = 'Viewer not initialized. Check F12 console for xeokit errors.';
        return;
      }
      if (this.sessionId) {
        try { await api.deleteSession(this.sessionId); } catch (e) { /* ignore */ }
        this.sessionId = null;
      }
      this.loading = true;
      this.loadingMsg = `Uploading ${file.name}...`;
      this.error = null;
      this.exportMsg = null;
      try {
        this.model = await api.uploadIfc(file);
        this.sessionId = this.model.session_id;
        this.loadingMsg = 'Loading 3D geometry...';
        const buffer = await file.arrayBuffer();
        await this.viewer.loadIfcArrayBuffer(buffer, {
          normalizeFallback: true,
          fetchNormalized: async () => {
            this.loadingMsg = 'Primary load failed — re-encoding via ifcopenshell...';
            return api.normalizeIfc(file);
          },
        });
        this.viewer.setNonDoorsXrayed(0.5);
        this.applyCheckColors();
        this.activeTab = 'results';
      } catch (e) {
        const msg = String(e.message || e);
        if (msg.includes('primary load failed') || msg.includes('model load error') || msg.includes('normalize')) {
          this.error = 'Failed to load IFC in 3D viewer even after ifcopenshell re-encode. ' +
            'The file may use an old/proprietary STEP variant that web-ifc@0.0.51 cannot parse. ' +
            'Backend analysis still worked (sidebar data is valid). ' +
            'Try samples/Duplex_xeokit.ifc or samples/Clinic_Architectural_IFC2x3.ifc for 3D viewing.';
        } else {
          this.error = msg;
        }
      } finally {
        this.loading = false;
        this.loadingMsg = '';
        event.target.value = '';
      }
    },

    async selectDoor(gid) {
      this.selectedDoorId = gid;
      this.viewer.unhighlightAll();
      this.viewer.highlightDoor(gid);
      if (this.sessionId) {
        try {
          this.selectedDoorDetail = await api.getDoor(gid, this.sessionId);
        } catch (e) {
          this.selectedDoorDetail = null;
        }
      }
      this.activeTab = 'door';
    },

    flyToDoor(gid) {
      this.viewer.flyTo(gid);
      this.selectDoor(gid);
    },

    applyCheckColors() {
      if (!this.model) return;
      const results = this.doors.map(d => d.check_result).filter(Boolean);
      this.viewer.colorizeByStatus(results);
      this._applyFireExitHighlight();
    },

    _applyFireExitHighlight() {
      if (!this.viewer) return;
      const fireGids = this.doors.filter(d => d.is_fire_exit).map(d => d.global_id);
      this.viewer.highlightFireExitDoors(fireGids, this.highlightFireExit);
    },

    toggleHighlightFireExit() {
      this.highlightFireExit = !this.highlightFireExit;
      this._applyFireExitHighlight();
    },

    async runCheck() {
      if (!this.sessionId) return;
      this.loading = true;
      this.loadingMsg = 'Running check...';
      try {
        const r = await api.runCheck(this.sessionId);
        this.model.summary = r.summary;
        for (const newResult of r.results) {
          const d = this.doors.find(x => x.global_id === newResult.door_global_id);
          if (d) d.check_result = newResult;
        }
        this.applyCheckColors();
        if (this.filterStoreyId) this._focusStoreyInViewer(this.filterStoreyId);
        else this.viewer.focusDoors([]);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
        this.loadingMsg = '';
      }
    },

    async toggleFireExit(door) {
      const newVal = !door.is_fire_exit;
      try {
        await api.override(this.sessionId, {
          type: 'fire_exit',
          global_id: door.global_id,
          value: newVal,
        });
        door.is_fire_exit = newVal;
        door.fire_exit_source = newVal ? 'user_override' : 'not_fire_exit';
        this._applyFireExitHighlight();
      } catch (e) {
        this.error = e.message;
      }
    },

    async overrideOccupancy(space, value) {
      const n = parseInt(value, 10);
      if (isNaN(n) || n < 0) return;
      try {
        await api.override(this.sessionId, {
          type: 'occupancy',
          global_id: space.global_id,
          value: n,
        });
        space.occupant_capacity = n;
        space.capacity_source = 'user_input';
        this._refreshDoorsOfSpace(space.global_id);
      } catch (e) {
        this.error = e.message;
      }
    },

    async overrideSpaceUse(space, useClass) {
      try {
        await api.override(this.sessionId, {
          type: 'space_use',
          global_id: space.global_id,
          value: useClass,
        });
        this._refreshDoorsOfSpace(space.global_id);
        if (this.selectedDoorDetail && this.selectedDoorDetail.related_space) {
          this.selectedDoorDetail = await api.getDoor(this.selectedDoorId, this.sessionId);
        }
      } catch (e) {
        this.error = e.message;
      }
    },

    async overrideThreshold(capacityMin, capacityMax, newWidthMm) {
      try {
        await api.override(this.sessionId, {
          type: 'threshold',
          global_id: 'hk_fsb_2011_b2_default',
          value: {
            capacity_min: parseInt(capacityMin, 10),
            capacity_max: capacityMax ? parseInt(capacityMax, 10) : null,
            min_width_per_door_mm: parseFloat(newWidthMm),
          },
        });
        this.model = await api.getSummary(this.sessionId).then(async (s) => {
          const full = await api.runCheck(this.sessionId);
          for (const nr of full.results) {
            const d = this.doors.find(x => x.global_id === nr.door_global_id);
            if (d) d.check_result = nr;
          }
          this.model.summary = full.summary;
          return this.model;
        });
        this.applyCheckColors();
        if (this.filterStoreyId) this._focusStoreyInViewer(this.filterStoreyId);
      } catch (e) {
        this.error = e.message;
      }
    },

    get defaultThresholdBands() {
      return (this.presets?.default?.table_b2_thresholds || []).map(r => ({
        capacity_min: r.capacity_min,
        capacity_max: r.capacity_max,
        min_doors: r.min_doors,
        min_width_per_door_mm: r.min_width_per_door_mm,
      }));
    },

    openThresholdDialog() {
      const defaults = this.defaultThresholdBands;
      this.thrDialogRows = defaults.map(r => ({
        capacity_min: r.capacity_min,
        capacity_max: r.capacity_max,
        min_doors: r.min_doors,
        min_width_per_door_mm: r.min_width_per_door_mm,
        _original: JSON.stringify(r),
      }));
      const hasCustom = this.model?.summary?._custom_thresholds;
      if (this.sessionId && hasCustom) {
        api.getSummary(this.sessionId).then(s => {}).catch(() => {});
      }
      if (this.sessionId) {
        api.getSummary(this.sessionId).then(s => {
          const ct = s._custom_threshold_table;
          if (ct && Array.isArray(ct) && ct.length > 0) {
            this.thrDialogRows = ct.map(r => ({
              capacity_min: r.capacity_min,
              capacity_max: r.capacity_max ?? null,
              min_doors: r.min_doors ?? null,
              min_width_per_door_mm: r.min_width_per_door_mm,
              _original: JSON.stringify(r),
            }));
          }
        }).catch(() => {});
      }
      this.$sortThresholdRows();
      this.thresholdDialogOpen = true;
      this.$nextTick(() => {
        const dlg = document.getElementById('thresholdDialog');
        if (dlg && typeof dlg.showModal === 'function') dlg.showModal();
      });
    },

    $sortThresholdRows() {
      this.thrDialogRows.sort((a, b) => (a.capacity_min || 0) - (b.capacity_min || 0));
    },

    closeThresholdDialog() {
      this.thresholdDialogOpen = false;
      const dlg = document.getElementById('thresholdDialog');
      if (dlg && dlg.open) dlg.close();
    },

    addThresholdBand() {
      const last = this.thrDialogRows[this.thrDialogRows.length - 1];
      const nextMin = last ? (last.capacity_max ?? last.capacity_min + 100) + 1 : 3;
      this.thrDialogRows.push({
        capacity_min: nextMin,
        capacity_max: null,
        min_doors: null,
        min_width_per_door_mm: null,
        _original: null,
      });
      this.$sortThresholdRows();
    },

    removeThresholdBand(row) {
      const idx = this.thrDialogRows.indexOf(row);
      if (idx >= 0) this.thrDialogRows.splice(idx, 1);
      this.$sortThresholdRows();
    },

    async saveThresholdTable() {
      if (!this.sessionId) return;
      this.$sortThresholdRows();
      const bands = this.thrDialogRows.map(r => ({
        capacity_min: parseInt(r.capacity_min, 10),
        capacity_max: r.capacity_max != null ? parseInt(r.capacity_max, 10) : null,
        min_doors: r.min_doors != null ? parseInt(r.min_doors, 10) : null,
        min_width_per_door_mm: r.min_width_per_door_mm != null ? parseFloat(r.min_width_per_door_mm) : null,
      }));
      for (const b of bands) {
        if (isNaN(b.capacity_min) || b.capacity_min < 3) {
          this.error = `capacity_min must be >= 3 for all bands`;
          return;
        }
        if (b.capacity_max != null && (isNaN(b.capacity_max) || b.capacity_max < b.capacity_min)) {
          this.error = `capacity_max must be >= capacity_min for all bands`;
          return;
        }
        if (b.min_width_per_door_mm != null && (isNaN(b.min_width_per_door_mm) || b.min_width_per_door_mm <= 0)) {
          this.error = `min_width_per_door_mm must be a positive number for all bands`;
          return;
        }
      }
      this.loading = true;
      this.loadingMsg = 'Saving threshold table...';
      try {
        const r = await api.saveThresholdTable(this.sessionId, bands);
        this.model.summary = r.summary || this.model.summary;
        if (r.affected_results) {
          for (const nr of r.affected_results) {
            const d = this.doors.find(x => x.global_id === nr.door_global_id);
            if (d) d.check_result = nr;
          }
        }
        for (const row of this.thrDialogRows) {
          row._original = JSON.stringify(row);
        }
        this.applyCheckColors();
        if (this.filterStoreyId) this._focusStoreyInViewer(this.filterStoreyId);
        else this.viewer.focusDoors([]);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
        this.loadingMsg = '';
      }
    },

    async resetAllThresholds() {
      if (!this.sessionId) return;
      this.loading = true;
      this.loadingMsg = 'Resetting all thresholds to defaults...';
      try {
        const r = await api.resetThresholdTable(this.sessionId);
        this.model.summary = r.summary || this.model.summary;
        if (r.affected_results) {
          for (const nr of r.affected_results) {
            const d = this.doors.find(x => x.global_id === nr.door_global_id);
            if (d) d.check_result = nr;
          }
        }
        this.thrDialogRows = this.defaultThresholdBands.map(r => ({
          capacity_min: r.capacity_min,
          capacity_max: r.capacity_max,
          min_doors: r.min_doors,
          min_width_per_door_mm: r.min_width_per_door_mm,
          _original: JSON.stringify(r),
        }));
        this.applyCheckColors();
        if (this.filterStoreyId) this._focusStoreyInViewer(this.filterStoreyId);
        else this.viewer.focusDoors([]);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
        this.loadingMsg = '';
      }
    },

    selectStoreyFilter(storeyGid) {
      this.filterStoreyId = (storeyGid === '' || storeyGid === null) ? null : storeyGid;
      if (this.filterStoreyId) this._focusStoreyInViewer(this.filterStoreyId);
      else if (this.viewer) this.viewer.focusDoors([]);
    },

    _focusStoreyInViewer(storeyGid) {
      if (!this.viewer) return;
      this.viewer.focusStorey(storeyGid);
    },

    async exportModel(format) {
      if (!this.sessionId) return;
      this.exportMsg = null;
      this.loading = true;
      this.loadingMsg = `Requesting ${format.toUpperCase()} export...`;
      try {
        await api.exportModel(this.sessionId, format);
        this.exportMsg = `${format.toUpperCase()} export completed (unexpected — MVP returns 501).`;
        this.exportMsgKind = 'info';
      } catch (e) {
        if (e.status === 501) {
          this.exportMsg = `${format.toUpperCase()} export is designed but not implemented in MVP. ` +
            `See docs/EXPORT_DESIGN.md (BCF → Revit/Solibri; HTML → email; JSON → CI/LLM).`;
          this.exportMsgKind = 'warn';
        } else {
          this.error = e.message;
        }
      } finally {
        this.loading = false;
        this.loadingMsg = '';
      }
    },

    resetView() {
      if (!this.viewer) return;
      this.filterStoreyId = null;
      this.viewer.focusDoors([]);
      try {
        this.viewer.cameraFlight.flyTo(this.viewer.scene);
      } catch (e) { /* ignore */ }
    },

    _refreshDoorsOfSpace(spaceGid) {
      this.applyCheckColors();
    },

    nextFail() {
      const fails = this.failsList;
      if (fails.length === 0) return;
      this.failCursor = (this.failCursor + 1) % fails.length;
      const d = fails[this.failCursor];
      this.flyToDoor(d.global_id);
    },

    nextUnknown() {
      const unknowns = this.unknownsList;
      if (unknowns.length === 0) return;
      this.unknownCursor = (this.unknownCursor + 1) % unknowns.length;
      const d = unknowns[this.unknownCursor];
      this.flyToDoor(d.global_id);
    },

    onKeydown(event) {
      if (event.key === 'f' || event.key === 'F') this.nextFail();
      else if (event.key === 'u' || event.key === 'U') this.nextUnknown();
    },

    fmtWidth(mm) {
      if (mm === null || mm === undefined) return '—';
      return `${Math.round(mm)} mm`;
    },

    fmtCapacity(n) {
      if (n === null || n === undefined) return '—';
      return `${n}`;
    },

    statusLabel(status) {
      return { pass: 'PASS', fail: 'FAIL', non_passage: 'NON-PASSAGE' }[status] || status;
    },

    statusColor(status) {
      return STATUS_COLOR_HEX[status] || '#999';
    },

    shortGid(gid) {
      if (!gid) return '';
      return gid.length > 14 ? gid.slice(0, 12) + '…' : gid;
    },

    ruleLink() {
      if (!this.presets) return '#';
      return this.presets.default.rule_link || '#';
    },

    openThresholdDialog() {
      const defaults = this.presets?.default?.table_b2_thresholds || [];
      this.thrDialogRows = defaults.map(row => ({
        capacity_min: row.capacity_min,
        capacity_max: row.capacity_max,
        min_doors: row.min_doors,
        default_width: row.min_width_per_door_mm,
        current_width: row.min_width_per_door_mm,
        edit_width: '',
        is_override: false,
      }));
      if (this.sessionId) {
        api.getSummary(this.sessionId).then(s => {
          const overrides = s.overrides?.filter(o => o.type === 'threshold') || [];
          for (const ov of overrides) {
            const v = ov.value || {};
            const cmin = v.capacity_min;
            const cmax = v.capacity_max ?? null;
            const row = this.thrDialogRows.find(r => r.capacity_min === cmin && (r.capacity_max ?? null) === (cmax ?? null));
            if (row) {
              row.current_width = v.min_width_per_door_mm;
              row.is_override = true;
            }
          }
        }).catch(() => {});
      }
      this.thresholdDialogOpen = true;
      this.$nextTick(() => {
        const dlg = document.getElementById('thresholdDialog');
        if (dlg && typeof dlg.showModal === 'function') dlg.showModal();
      });
    },

    closeThresholdDialog() {
      this.thresholdDialogOpen = false;
      const dlg = document.getElementById('thresholdDialog');
      if (dlg && dlg.open) dlg.close();
    },

    async applyThresholdBand(row) {
      const w = parseFloat(row.edit_width);
      if (isNaN(w) || w <= 0) {
        this.error = 'Invalid width (must be a positive number in mm).';
        return;
      }
      this.loading = true;
      this.loadingMsg = `Applying threshold ${row.capacity_min}-${row.capacity_max ?? '∞'} → ${w}mm...`;
      try {
        await this.overrideThreshold(row.capacity_min, row.capacity_max, w);
        row.current_width = w;
        row.is_override = true;
        row.edit_width = '';
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
        this.loadingMsg = '';
      }
    },

    async deleteThresholdBand(row) {
      this.loading = true;
      this.loadingMsg = `Resetting band ${row.capacity_min}-${row.capacity_max ?? '∞'} to default...`;
      try {
        const r = await api.deleteThresholdOverride(this.sessionId, row.capacity_min, row.capacity_max);
        this.model.summary = r.summary || this.model.summary;
        if (r.affected_results) {
          for (const nr of r.affected_results) {
            const d = this.doors.find(x => x.global_id === nr.door_global_id);
            if (d) d.check_result = nr;
          }
        }
        row.current_width = row.default_width;
        row.is_override = false;
        this.applyCheckColors();
        if (this.filterStoreyId) this._focusStoreyInViewer(this.filterStoreyId);
        else this.viewer.focusDoors([]);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
        this.loadingMsg = '';
      }
    },

    async resetAllThresholds() {
      if (!this.sessionId) return;
      this.loading = true;
      this.loadingMsg = 'Resetting all thresholds to defaults...';
      try {
        const r = await api.deleteAllThresholdOverrides(this.sessionId);
        this.model.summary = r.summary || this.model.summary;
        if (r.affected_results) {
          for (const nr of r.affected_results) {
            const d = this.doors.find(x => x.global_id === nr.door_global_id);
            if (d) d.check_result = nr;
          }
        }
        for (const row of this.thrDialogRows) {
          row.current_width = row.default_width;
          row.is_override = false;
          row.edit_width = '';
        }
        this.applyCheckColors();
        if (this.filterStoreyId) this._focusStoreyInViewer(this.filterStoreyId);
        else this.viewer.focusDoors([]);
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
        this.loadingMsg = '';
      }
    },

    async toggleDoorChecked(door) {
      const newVal = !door.is_checked;
      try {
        await api.override(this.sessionId, {
          type: 'checked',
          global_id: door.global_id,
          value: newVal,
        });
        door.is_checked = newVal;
      } catch (e) {
        this.error = e.message;
      }
    },

    async batchToggleChecked(value) {
      if (!this.sessionId) return;
      const ids = this.filteredDoors.map(d => d.global_id);
      if (ids.length === 0) return;
      this.loading = true;
      this.loadingMsg = `${value ? 'Checking' : 'Unchecking'} ${ids.length} doors...`;
      try {
        await api.batchChecked(this.sessionId, ids, value);
        for (const d of this.filteredDoors) {
          d.is_checked = value;
        }
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
        this.loadingMsg = '';
      }
    },

    tooltip(name) {
      const tips = {
        global_id: 'IFC GlobalId — 22-character base64 unique identifier for this door entity in the IFC file',
        overall_width: 'Overall Width — door overall width from IFC OverallWidth attribute (100% fill rate). This is NOT clear width; it is the door panel width, actual clear width may be smaller',
        width_source: 'Width Source — how width was obtained: overall_estimate (from OverallWidth, proxy for clear width) | clear_width (field-measured) | unknown (no width data)',
        fire_exit: 'Fire Exit — whether this door serves as a fire exit. Source: pset (Pset_DoorCommon.FireExit, 0% fill rate) | name_keyword (door name contains fire/emergency) | user_override (manually marked)',
        fe_source: 'FE Source — how fire exit status was determined: pset | name_keyword | user_override | not_fire_exit',
        related_space: 'Related Space — the IfcSpace connected to this door via IfcRelSpaceBoundary. Capacity and UseClass are inherited from this space',
        use_class: 'UseClass — space usage classification per Table B1 (16 categories). Determines occupant density factor (m²/person or beds/seats). Source: longname_keyword | user_override',
        occupant_capacity: 'Occupant Capacity — estimated number of occupants in the related space. Calculation: area × use_factor (for area_per_person_m2 type). Source: auto_area_calc | user_input | unknown',
        capacity_source: 'Capacity Source — how capacity was derived: auto_area_calc (area×factor) | user_input (manually entered) | table_b1_factor | unknown (missing area or use_class)',
        threshold: 'Threshold — minimum required clear door width (mm) per Table B2 (capacity>3) or Clause B13.4 (capacity≤3, absolute minimum 750mm). May be overridden by user',
        measured: 'Measured — the door width used for compliance check (mm). Currently OverallWidth proxy, NOT field-measured clear width',
        deficit: 'Deficit — Threshold minus Measured (mm). Positive = door too narrow (FAIL). Negative = surplus margin',
        needs_review: 'Needs Human Review — true when width_source is not clear_width (OverallWidth is a proxy, not actual clear width) or capacity is unknown. Requires field verification',
        status: 'Status — pass (meets threshold) | fail (below threshold) | non_passage (cannot determine, non-egress door)',
        rule_clause: 'Rule Clause — the FSB 2011 clause applied: B7.1 (Table B2, capacity>3) | B13.4 (absolute minimum, capacity≤3) | N/A (excluded space)',
        is_checked: 'Checked — manual human review flag. Marks whether a human reviewer has inspected this door. Does not affect compliance calculation',
      };
      return tips[name] || '';
    },
  }));
});
