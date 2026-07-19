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

    async init() {
      try {
        this.viewer = new IfcViewer('viewerCanvas');
        this.viewer.onPick = (gid) => this.selectDoor(gid);
        this.presets = await api.getPresets();
      } catch (e) {
        this.error = `init failed: ${e.message}`;
      }
    },

    get hasModel() { return this.model !== null; },
    get doors() { return this.model ? this.model.doors : []; },
    get spaces() { return this.model ? this.model.spaces : []; },
    get storeys() { return this.model ? this.model.storeys : []; },
    get summary() { return this.model ? this.model.summary : null; },

    get filteredDoors() {
      let list = this.doors;
      if (this.filterStatus !== 'all') {
        list = list.filter(d => d.check_result && d.check_result.status === this.filterStatus);
      }
      return list;
    },

    get failsList() {
      return this.doors.filter(d => d.check_result && d.check_result.status === 'fail');
    },

    get unknownsList() {
      return this.doors.filter(d => d.check_result && d.check_result.status === 'unknown');
    },

    get selectedDoor() {
      if (!this.selectedDoorId || !this.model) return null;
      return this.doors.find(d => d.global_id === this.selectedDoorId) || null;
    },

    async onFileSelected(event) {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      this.loading = true;
      this.loadingMsg = `Uploading ${file.name}...`;
      this.error = null;
      try {
        this.model = await api.uploadIfc(file);
        this.sessionId = this.model.session_id;
        this.loadingMsg = 'Loading 3D geometry...';
        const url = URL.createObjectURL(file);
        await this.viewer.loadIfcUrl(url);
        this.viewer.setNonDoorsXrayed(0.5);
        this.applyCheckColors();
        this.activeTab = 'results';
      } catch (e) {
        this.error = e.message;
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
      } catch (e) {
        this.error = e.message;
      }
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
      return { pass: 'PASS', fail: 'FAIL', unknown: 'UNKNOWN', overridden: 'OVERRIDE' }[status] || status;
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
  }));
});
