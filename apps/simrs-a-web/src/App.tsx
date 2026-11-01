// @ts-nocheck -- logic ported verbatim from the design canvas; data comes from src/api.
import {Component} from "react";
import {QrScannerPanel} from "@jejakjkn/web-qr-scanner";
import {cancelRecord, completeSync, correctRecord, createClinicalEvent, fmtLongDate, loadAll, retryDelivery, scan, submitClaim} from "./api/client";
import {View} from "./design/View";

const EMPTY_VISIT = {id: '', ref: '', enc: '', inT: '', outT: '', status: 'OPEN', presence: 'QR_VERIFIED', sync: 'LOCAL_ONLY', err: null, pending: 0, failed: 0, delivered: 0, marking: false, records: []};

export default class App extends Component<object, any> {
  scanPending = false;
  scanAttempt = null;

  newDraft(v, patch) {
    const sel = {};
    v.records.forEach((r) => { if (r.type !== 'STAGE_COMPLETION' && r.status !== 'CANCELLED') sel[r.rid] = { on: true, qty: r.qty }; });
    return Object.assign({ vid: v.id, pn: v.pn, care: 'RJ', sel, amount: '', ack: false, error: false }, patch || {});
  }

  emptyForm() {
    return { type: 'DIAGNOSIS', cs: 'ICD-10', code: '', display: '', qty: '', unit: '', stage: 'STAFF_COMPLETED' };
  }

  emptyExc() {
    return { reason: null, patientId: '', service: 'OUTPATIENT', approver: '', evidence: '', notes: '' };
  }

  state = {
    screen: 'list', mode: 'CHECK_IN', token: '', tokenErr: false, result: null,
    visits: [], sel: null, open: {}, form: this.emptyForm(), dialog: null,
    excPhase: 'CHECK_IN', exc: this.emptyExc(), dFilter: 'ALL', deliveries: [],
    bclaims: [], draft: null, cid: null, justSent: false, submitting: false
  };

  submitScan = async (rawToken) => {
    const token = rawToken.trim();
    if (token.length < 32 || this.scanPending) {
      if (token.length < 32) this.setState({tokenErr: true, result: null});
      return;
    }
    const mode = this.state.mode;
    const kind = mode === 'CHECK_IN' ? 'check-in' : 'check-out';
    const fingerprint = kind + ':' + token;
    if (!this.scanAttempt || this.scanAttempt.fingerprint !== fingerprint) {
      this.scanAttempt = {
        fingerprint,
        idempotencyKey: crypto.randomUUID(),
        reference: kind === 'check-in' ? 'VISIT-' + Date.now() : undefined
      };
    }
    this.scanPending = true;
    this.setState({submitting: true, token, tokenErr: false, result: null});
    try {
      const scanned = await scan(kind, token, this.scanAttempt);
      await this.load();
      this.scanAttempt = null;
      this.setState({sel: scanned.encounter_id, token: '', result: {kind: 'ok', vid: scanned.encounter_id, purpose: mode}, tokenErr: false});
    } catch (error) {
      const code = ['QR_TOKEN_EXPIRED', 'QR_ALREADY_CONSUMED', 'WRONG_QR_PURPOSE', 'INVALID_ENCOUNTER_STATE', 'INVALID_QR_SIGNATURE', 'INVALID_QR_TOKEN', 'FACILITY_MISMATCH'].includes(error.code) ? error.code : 'HTTP 503';
      this.setState({result: {kind: 'err', code}, tokenErr: false});
    } finally {
      this.scanPending = false;
      this.setState({submitting: false});
    }
  };

  componentDidMount() {
    this.load();
    this.poll = setInterval(() => this.load(), 2000);
  }

  componentWillUnmount() {
    clearInterval(this.poll);
    this.scanAttempt = null;
  }

  async load() {
    try {
      this.setState(await loadAll());
    } catch {
      // The next poll retries; the page keeps showing the last known data.
    }
  }

  async act(run, after) {
    await run();
    if (after) this.setState(after);
    await this.load();
  }

  renderVals() {
    const s = this.state;
    const accent = this.props.accent ?? '#3F5E48';
    const tone = {
      ok: { bg: '#E2EBE4', fg: '#2F4A37' },
      warn: { bg: '#FBEBD7', fg: '#8A4206' },
      info: { bg: '#E1ECF8', fg: '#1E4E8C' },
      neutral: { bg: '#E8ECEA', fg: '#3E4A45' }
    };
    const ENC = { OPEN: ['Sedang berlangsung', 'info'], CHECKED_OUT: ['Sudah keluar', 'ok'], CLOSED_WITH_EXCEPTION: ['Ditutup dengan pengecualian', 'warn'] };
    const PRES = { QR_VERIFIED: ['QR', 'ok'], EXCEPTION_DOCUMENTED: ['Pengecualian', 'warn'] };
    const TYPE = { DIAGNOSIS: 'Diagnosis', PROCEDURE: 'Tindakan', MEDICATION_PRESCRIBED: 'Resep obat', MEDICATION_DISPENSED: 'Obat diserahkan', STAGE_COMPLETION: 'Tahap selesai' };
    const REC = { ACTIVE: ['Aktif', 'neutral'], CORRECTED: ['Dikoreksi', 'info'], CANCELLED: ['Dibatalkan', 'warn'] };
    const ACT = { RECORDED: 'Dicatat', CORRECTED: 'Dikoreksi', CANCELLED: 'Dibatalkan' };
    const STAGE = { STARTED: 'Dimulai', STAFF_COMPLETED: 'Selesai oleh petugas' };
    const syncInfo = (v) => {
      if (v.sync === 'LOCAL_ONLY') return ['Belum ada pengiriman', 'neutral', 'Belum ada catatan layanan yang dikirim ke JejakJKN.'];
      if (v.sync === 'PENDING') return v.pending > 0
        ? ['Dalam antrean kirim', 'info', v.pending + ' pengiriman menunggu diterima JejakJKN.']
        : ['Belum ditandai lengkap', 'info', 'Semua catatan sudah diterima. Tandai lengkap setelah seluruh layanan selesai dicatat.'];
      if (v.sync === 'SYNC_COMPLETE') return ['Lengkap', 'ok', 'JejakJKN menerima seluruh catatan sampai urutan terakhir.'];
      if (v.sync === 'INCOMPLETE_SYNC') return ['Belum lengkap', 'warn', 'JejakJKN menandai ada urutan catatan yang belum diterima.'];
      return ['Pengiriman ditolak', 'warn', 'JejakJKN menolak ' + v.failed + ' pengiriman. Pengiriman yang ditolak tidak diulang otomatis.'];
    };
    const qtyText = (qty, unit) => qty ? qty + ' ' + (unit || '') : '';

    const visits = s.visits;
    const sel = visits.find((v) => v.id === s.sel) || visits[0] || EMPTY_VISIT;

    const visitRows = visits.map((v) => {
      const e = ENC[v.status], p = PRES[v.presence], y = syncInfo(v);
      return {
        ref: v.ref, encShort: v.enc.slice(0, 8) + '…',
        time: v.inT + ' – ' + (v.outT || '…'),
        pLabel: p[0], pBg: tone[p[1]].bg, pFg: tone[p[1]].fg,
        sLabel: e[0], sBg: tone[e[1]].bg, sFg: tone[e[1]].fg,
        yLabel: y[0], yBg: tone[y[1]].bg, yFg: tone[y[1]].fg,
        open: () => this.setState({ screen: 'visit', sel: v.id, open: {}, form: this.emptyForm() })
      };
    });
    const openCount = visits.filter((v) => v.status === 'OPEN').length;
    const issueCount = visits.filter((v) => v.sync === 'FAILED' || v.sync === 'INCOMPLETE_SYNC').length;
    const listSummary = visits.length + ' kunjungan · ' + openCount + ' sedang berlangsung' + (issueCount ? ' · ' + issueCount + ' perlu dicek' : '');

    const ERR = {
      QR_TOKEN_EXPIRED: ['QR sudah kedaluwarsa', 'QR hanya berlaku 60 detik. Minta pasien menampilkan QR baru.'],
      QR_ALREADY_CONSUMED: ['QR sudah dipakai', 'QR ini sudah pernah dipindai. Minta pasien menampilkan QR baru. Jika kunjungan sudah tercatat, cek daftar kunjungan hari ini.'],
      WRONG_QR_PURPOSE: ['Jenis QR tidak sesuai', s.mode === 'CHECK_IN' ? 'Pasien menunjukkan QR Keluar. Minta QR Masuk, atau pindah ke mode QR Keluar.' : 'Pasien menunjukkan QR Masuk. Minta QR Keluar, atau pindah ke mode QR Masuk.'],
      INVALID_ENCOUNTER_STATE: ['Kunjungan tidak dapat ditutup', 'Kunjungan untuk QR ini sudah tidak berlangsung.'],
      INVALID_QR_SIGNATURE: ['QR tidak sah', 'QR tidak memiliki tanda tangan JejakJKN yang valid. Minta pasien membuat QR baru dari aplikasi.'],
      INVALID_QR_TOKEN: ['QR tidak valid', 'Isi QR tidak dikenali JejakJKN. Minta pasien membuat QR baru dari aplikasi.'],
      FACILITY_MISMATCH: ['QR untuk faskes lain', 'QR ini tidak diterbitkan untuk faskes ini. Minta pasien membuat QR di lokasi yang benar.'],
      'HTTP 503': ['JejakJKN tidak dapat dihubungi', 'Lanjutkan pelayanan. Coba pindai lagi beberapa saat, atau catat pengecualian bila gangguan berlanjut.']
    };
    const showErr = (code) => this.setState({ result: { kind: 'err', code: ERR[code] ? code : 'HTTP 503' }, tokenErr: false });
    const runScan = () => this.submitScan(s.token);

    let res = {}, err = {};
    if (s.result && s.result.kind === 'ok') {
      const rv = visits.find((v) => v.id === s.result.vid);
      const e = rv ? ENC[rv.status] : ['Berhasil diproses', 'ok'];
      const isIn = s.result.purpose === 'CHECK_IN';
      res = {
        title: isIn ? 'Masuk berhasil' : 'Keluar berhasil',
        enc: rv?.enc || s.result.vid, ref: rv?.ref || 'Muat ulang daftar kunjungan',
        sLabel: e[0], sBg: tone[e[1]].bg, sFg: tone[e[1]].fg,
        timeLabel: isIn ? 'Waktu masuk' : 'Waktu keluar',
        time: rv ? (isIn ? rv.inT : rv.outT) : '—',
        open: () => rv ? this.setState({ screen: 'visit', sel: rv.id, open: {}, form: this.emptyForm() }) : this.load()
      };
    }
    if (s.result && s.result.kind === 'err') {
      const e = ERR[s.result.code];
      err = { title: e[0], text: e[1], code: s.result.code };
    }
    const seg = (on) => ({ bg: on ? '#FFFFFF' : 'transparent', fg: on ? '#1F2A22' : '#56625D', shadow: on ? '0 1px 2px rgba(31,42,34,0.12)' : 'none' });
    const segIn = seg(s.mode === 'CHECK_IN'), segOut = seg(s.mode === 'CHECK_OUT');

    const EXC_REASONS = [
      ['NO_SMARTPHONE', 'Pasien tidak punya ponsel pintar'],
      ['EMERGENCY_UNCONSCIOUS', 'Gawat darurat atau pasien tidak sadar'],
      ['QR_DEVICE_FAILURE', 'QR atau perangkat gagal'],
      ['NETWORK_OUTAGE', 'Gangguan jaringan'],
      ['PATIENT_INCAPACITATED', 'Pasien tidak mampu menunjukkan QR']
    ];
    const ex = s.exc || this.emptyExc();
    const setExc = (patch) => this.setState({ exc: Object.assign({}, (this.state && this.state.exc) || ex, patch) });
    const excIn = s.excPhase === 'CHECK_IN';
    const excInvalid = !ex.reason || !ex.approver.trim() || (excIn && !ex.patientId.trim());
    const exc = {
      isIn: excIn, isOut: !excIn,
      title: excIn ? 'Catat pengecualian masuk' : 'Tutup kunjungan dengan pengecualian',
      sub: excIn ? 'Untuk pasien yang tidak dapat menunjukkan QR Masuk.' : 'Untuk pasien yang tidak dapat menunjukkan QR Keluar.',
      backLabel: excIn ? 'Pindai QR' : 'Kembali ke kunjungan',
      ref: sel.ref, inT: sel.inT,
      patientId: ex.patientId, service: ex.service, approver: ex.approver, evidence: ex.evidence, notes: ex.notes,
      setPatientId: (e) => setExc({ patientId: e.target.value }),
      setService: (e) => setExc({ service: e.target.value }),
      setApprover: (e) => setExc({ approver: e.target.value }),
      setEvidence: (e) => setExc({ evidence: e.target.value }),
      setNotes: (e) => setExc({ notes: e.target.value.slice(0, 500) }),
      reasons: EXC_REASONS.map(([code, label]) => ({
        code, label, checked: ex.reason === code,
        border: ex.reason === code ? accent : '#DDE3DE',
        bg: ex.reason === code ? '#F1F5F2' : '#FFFFFF',
        pick: () => setExc({ reason: code })
      })),
      invalid: excInvalid,
      submit: () => { if (!excInvalid) window.alert('Jalur pengecualian belum tersambung ke backend pada versi demo ini.'); }
    };

    const open = s.open || {};
    const records = sel.records.map((r) => {
      const st = REC[r.status];
      const cancelled = r.status === 'CANCELLED';
      return {
        typeLabel: TYPE[r.type],
        display: r.display,
        codeLine: (r.cs === 'LOCAL' ? 'Kode RS ' : r.cs + ' ') + r.code + (r.stage ? ' · ' + STAGE[r.stage] : ''),
        qtyLine: qtyText(r.qty, r.unit) || '—',
        ver: r.ver,
        stLabel: st[0], stBg: tone[st[1]].bg, stFg: tone[st[1]].fg,
        strike: cancelled ? 'line-through' : 'none',
        opacity: cancelled ? '0.6' : '1',
        canEdit: !cancelled,
        isOpen: !!open[r.rid],
        expanded: String(!!open[r.rid]),
        caret: open[r.rid] ? '▴' : '▾',
        hist: r.hist.map((h) => ({ v: h.v, action: ACT[h.action], time: h.time, desc: h.desc, note: h.note, hasNote: !!h.note })),
        toggle: () => this.setState({ open: Object.assign({}, open, { [r.rid]: !open[r.rid] }) }),
        correct: () => this.setState({ dialog: { type: 'correct', rid: r.rid, cs: r.cs, code: r.code, display: r.display, qty: r.qty, unit: r.unit, reason: '' } }),
        cancel: () => this.setState({ dialog: { type: 'cancel', rid: r.rid, reason: '' } })
      };
    });
    const e = ENC[sel.status], p = PRES[sel.presence];
    const active = sel.records.filter((r) => r.status !== 'CANCELLED').length;
    const vis = {
      ref: sel.ref, enc: sel.enc, inT: sel.inT, outT: sel.outT ? sel.outT + ' WIB' : 'Belum keluar',
      sLabel: e[0], sBg: tone[e[1]].bg, sFg: tone[e[1]].fg,
      pLabel: p[0] === 'QR' ? 'Kehadiran: QR' : 'Kehadiran: pengecualian', pBg: tone[p[1]].bg, pFg: tone[p[1]].fg,
      records,
      noRecords: records.length === 0,
      countText: active + ' aktif' + (records.length > active ? ' · ' + (records.length - active) + ' dibatalkan' : ''),
      isOpen: sel.status === 'OPEN',
      canAdd: true
    };

    const y = syncInfo(sel);
    const sync = {
      label: y[0], bg: tone[y[1]].bg, fg: tone[y[1]].fg, text: y[2],
      pending: sel.pending, failed: sel.failed, delivered: sel.delivered,
      failedBg: sel.failed ? '#FBEBD7' : '#F3F5F1', failedFg: sel.failed ? '#8A4206' : '#1F2A22',
      hasError: !!sel.err,
      error: sel.err === 'HTTP 422' ? 'Alasan: data ditolak karena isinya tidak memenuhi format yang diterima JejakJKN.' : 'Alasan: JejakJKN belum dapat dihubungi. Pengiriman dicoba lagi otomatis.',
      cannotMark: sel.records.length === 0 || sel.marking || sel.sync === 'SYNC_COMPLETE'
    };

    const f = s.form || this.emptyForm();
    const setForm = (patch) => this.setState({ form: Object.assign({}, (this.state && this.state.form) || f, patch) });
    const formInvalid = !f.cs.trim() || !f.code.trim() || !f.display.trim();
    const form = {
      type: f.type, cs: f.cs, code: f.code, display: f.display, qty: f.qty, unit: f.unit, stage: f.stage,
      isStage: f.type === 'STAGE_COMPLETION',
      hasQty: f.type === 'MEDICATION_PRESCRIBED' || f.type === 'MEDICATION_DISPENSED',
      invalid: formInvalid,
      setType: (ev) => {
        const t = ev.target.value;
        setForm({ type: t, cs: t === 'DIAGNOSIS' ? 'ICD-10' : 'LOCAL' });
      },
      setCs: (ev) => setForm({ cs: ev.target.value }),
      setCode: (ev) => setForm({ code: ev.target.value }),
      setDisplay: (ev) => setForm({ display: ev.target.value }),
      setQty: (ev) => setForm({ qty: ev.target.value }),
      setUnit: (ev) => setForm({ unit: ev.target.value }),
      setStage: (ev) => setForm({ stage: ev.target.value })
    };
    const addRecord = (ev) => {
      if (ev && ev.preventDefault) ev.preventDefault();
      if (formInvalid) return;
      this.act(() => createClinicalEvent(sel.id, f), { form: this.emptyForm() });
    };

    const d = s.dialog;
    let dlg = {};
    if (d) {
      const setD = (patch) => this.setState({ dialog: Object.assign({}, (this.state && this.state.dialog) || d, patch) });
      const isCorrect = d.type === 'correct';
      const rec = sel.records.find((r) => r.rid === d.rid) || {};
      const invalid = !d.reason.trim() || (isCorrect && (!d.cs.trim() || !d.code.trim() || !d.display.trim()));
      dlg = {
        isCorrect,
        title: isCorrect ? 'Koreksi catatan' : 'Batalkan catatan',
        sub: isCorrect
          ? (rec.display || '') + ' · versi baru v' + ((rec.ver || 1) + 1) + '. Versi lama tetap tersimpan dan ikut dikirim sebagai riwayat.'
          : (rec.display || '') + ' akan ditandai dibatalkan. Catatan tidak dihapus dan riwayatnya tetap tersimpan.',
        cs: d.cs || '', code: d.code || '', display: d.display || '', qty: d.qty || '', unit: d.unit || '', reason: d.reason,
        setCs: (ev) => setD({ cs: ev.target.value }),
        setCode: (ev) => setD({ code: ev.target.value }),
        setDisplay: (ev) => setD({ display: ev.target.value }),
        setQty: (ev) => setD({ qty: ev.target.value }),
        setUnit: (ev) => setD({ unit: ev.target.value }),
        setReason: (ev) => setD({ reason: ev.target.value.slice(0, 500) }),
        reasonLabel: isCorrect ? 'Alasan koreksi' : 'Alasan pembatalan',
        submitLabel: isCorrect ? 'Simpan koreksi' : 'Batalkan catatan',
        btnBg: isCorrect ? accent : '#8A4206',
        invalid,
        submit: () => {
          if (invalid) return;
          this.act(
            () => isCorrect ? correctRecord(d.rid, rec.type, d) : cancelRecord(d.rid, d.reason),
            { dialog: null, open: Object.assign({}, open, { [d.rid]: true }) }
          );
        }
      };
    }

    const DT = {
      DELIVERED: ['Diterima', 'ok', '✓'], PENDING: ['Menunggu', 'info', '…'],
      RETRYING: ['Mencoba lagi', 'warn', '↻'], FAILED: ['Ditolak', 'bad', '✗']
    };
    const dtone = {
      ok: { bg: '#E2EBE4', fg: '#2F4A37', bar: '#5E8A69', tint: '#FFFFFF' },
      info: { bg: '#E1ECF8', fg: '#1E4E8C', bar: '#5B8BC9', tint: '#FFFFFF' },
      warn: { bg: '#FBEBD7', fg: '#8A4206', bar: '#D08A3E', tint: '#FFFBF6' },
      bad: { bg: '#FBE4E1', fg: '#A1271B', bar: '#C8473A', tint: '#FDF4F2' }
    };
    const deliveries = s.deliveries || [];
    const dCount = (st) => deliveries.filter((d) => d.st === st).length;
    const problems = dCount('FAILED') + dCount('RETRYING');
    const dFilter = s.dFilter || 'ALL';
    const dl = {
      hasProblem: problems > 0, problemCount: problems,
      tiles: [
        { n: dCount('PENDING') + dCount('RETRYING'), label: 'Menunggu diterima', sub: 'Termasuk yang sedang dicoba lagi otomatis', fg: '#1E4E8C', bar: '#5B8BC9' },
        { n: dCount('FAILED'), label: 'Ditolak JejakJKN', sub: 'Perlu diperiksa dan dikirim ulang', fg: '#A1271B', bar: '#C8473A' },
        { n: dCount('DELIVERED'), label: 'Diterima hari ini', sub: 'Sudah tersimpan di JejakJKN', fg: '#2F4A37', bar: '#5E8A69' }
      ],
      filters: [['ALL', 'Semua'], ['WAIT', 'Menunggu'], ['FAILED', 'Ditolak'], ['DELIVERED', 'Diterima']].map(([id, label]) => ({
        label, pressed: String(dFilter === id),
        count: id === 'ALL' ? deliveries.length : id === 'WAIT' ? dCount('PENDING') + dCount('RETRYING') : dCount(id),
        border: dFilter === id ? accent : '#CBD3CF', bg: dFilter === id ? '#E2EBE4' : '#FFFFFF',
        pick: () => this.setState({ dFilter: id })
      })),
      rows: deliveries.filter((d) => dFilter === 'ALL' || (dFilter === 'WAIT' ? (d.st === 'PENDING' || d.st === 'RETRYING') : d.st === dFilter)).map((d) => {
        const t = DT[d.st], tn = dtone[t[1]];
        const v = visits.find((x) => x.id === d.vid) || visits[0];
        return {
          time: d.time, ref: v.ref, what: d.what, kind: d.kind, status: t[0], icon: t[2], bg: tn.bg, fg: tn.fg, bar: tn.bar, tint: tn.tint,
          note: d.note, canRetry: d.st === 'FAILED',
          retry: () => this.act(() => retryDelivery(d.id)),
          open: () => this.setState({ screen: 'visit', sel: v.id, open: {}, form: this.emptyForm() })
        };
      })
    };
    dl.empty = dl.rows.length === 0;

    // Klaim BPJS
    const rp = (n) => 'Rp' + String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const btone = { ok: dtone.ok, warn: dtone.warn, info: dtone.info, neutral: { bg: '#E8ECEA', fg: '#3E4A45', bar: '#AAB4AF', tint: '#FFFFFF' } };
    const bclaims = s.bclaims || [];
    const BST = { RECEIVED: ['Diterima BPJS', 'info', 1], VERIFYING: ['Sedang diverifikasi', 'warn', 2], DONE: ['Selesai diverifikasi', 'ok', 3] };
    const readiness = (v) => {
      if (v.status === 'OPEN') return ['Belum bisa diajukan', 'neutral', 'Pasien belum keluar. Klaim bisa diajukan setelah kunjungan selesai.', true];
      if (v.sync === 'FAILED' || v.sync === 'INCOMPLETE_SYNC') return ['Perlu dicek', 'warn', 'Ada catatan yang ditolak JejakJKN. Perbaiki pengiriman dulu agar verifikator melihat data lengkap.', false];
      if (v.sync !== 'SYNC_COMPLETE') return ['Perlu dicek', 'warn', 'Data kunjungan belum ditandai lengkap di JejakJKN.', false];
      return ['Siap diajukan', 'ok', 'Semua catatan sudah diterima JejakJKN.', false];
    };
    const unclaimed = visits.filter((v) => !v.claimId);
    const rd = unclaimed.map((v) => ({ v, r: readiness(v) }));
    const startDraft = (v) => this.setState({ screen: 'claimForm', draft: this.newDraft(v), dialog: null });
    const nOf = (lab) => rd.filter((x) => x.r[0] === lab).length;
    const bc = {
      readyCount: nOf('Siap diajukan'), hasReady: nOf('Siap diajukan') > 0,
      tiles: [
        { n: nOf('Siap diajukan'), label: 'Siap diajukan', sub: 'Data lengkap di JejakJKN', fg: '#2F4A37', bar: '#5E8A69' },
        { n: nOf('Perlu dicek'), label: 'Perlu dicek dulu', sub: 'Masih bisa diajukan', fg: '#8A4206', bar: '#D08A3E' },
        { n: nOf('Belum bisa diajukan'), label: 'Kunjungan berlangsung', sub: 'Pasien belum keluar', fg: '#1F2A22', bar: '#AAB4AF' },
        { n: bclaims.length, label: 'Sudah diajukan', sub: 'Termasuk hari sebelumnya', fg: '#1E4E8C', bar: '#5B8BC9' }
      ],
      visits: rd.map(({ v, r }) => {
        const t = btone[r[1]];
        const n = v.records.filter((x) => x.type !== 'STAGE_COMPLETION' && x.status !== 'CANCELLED').length;
        return {
          ref: v.ref, time: v.inT + ' – ' + (v.outT || '…'), count: n + ' layanan',
          label: r[0], note: r[2], bg: t.bg, fg: t.fg, blocked: r[3],
          btnBg: r[0] === 'Siap diajukan' ? accent : '#FFFFFF', btnFg: r[0] === 'Siap diajukan' ? '#FFFFFF' : '#1F2A22', btnBorder: r[0] === 'Siap diajukan' ? accent : '#CBD3CF',
          start: () => { if (!r[3]) startDraft(v); }
        };
      }),
      sent: bclaims.map((c) => {
        const st = BST[c.st], t = btone[st[1]];
        return {
          id: c.id, ref: c.ref, visitDate: c.visitDate, sentAt: c.at[0], amount: rp(c.amount), status: st[0], bg: t.bg, fg: t.fg,
          tint: c.id === s.cid && s.justSent ? '#F6FAF7' : '#FFFFFF',
          open: () => this.setState({ screen: 'claimView', cid: c.id, justSent: false })
        };
      })
    };
    bc.noVisits = bc.visits.length === 0;

    const dr = s.draft;
    let cfm = {};
    if (dr) {
      const dv = visits.find((v) => v.id === dr.vid) || visits[0];
      const setDr = (patch) => this.setState({ draft: Object.assign({}, (this.state && this.state.draft) || dr, patch) });
      const recs = dv.records.filter((r) => dr.sel[r.rid]);
      const onItems = recs.filter((r) => dr.sel[r.rid].on);
      const amountN = parseInt(String(dr.amount).replace(/\D/g, ''), 10) || 0;
      const qtyBad = onItems.some((r) => r.qty && !(Number(dr.sel[r.rid].qty) > 0));
      const missing = [];
      if (String(dr.pn).trim().length < 3) missing.push('nomor peserta');
      if (!onItems.length) missing.push('minimal 1 layanan');
      if (qtyBad) missing.push('jumlah obat');
      if (!amountN) missing.push('nominal tagihan');
      if (!dr.ack) missing.push('centang pemeriksaan');
      const invalid = missing.length > 0;
      const submit = async () => {
        if (invalid) return;
        try {
          const claim = await submitClaim(dv, dr, onItems, amountN);
          await this.load();
          this.setState({ draft: null, screen: 'claimView', cid: claim.id, justSent: true });
        } catch {
          setDr({ error: true });
        }
      };
      cfm = {
        ref: dv.ref, pn: dr.pn, amount: dr.amount, ack: dr.ack, hasError: !!dr.error,
        hasSyncWarn: dv.sync === 'FAILED' || dv.sync === 'INCOMPLETE_SYNC',
        date: fmtLongDate(dv.startedAt) + ' · ' + dv.inT + ' – ' + (dv.outT || '…') + ' WIB',
        presence: dv.presence === 'QR_VERIFIED' ? 'QR masuk dan keluar' : 'Pengecualian tercatat',
        cares: [['RJ', 'Rawat jalan'], ['RI', 'Rawat inap']].map(([id, label]) => {
          const g = seg(dr.care === id);
          return { label, on: String(dr.care === id), bg: g.bg, fg: g.fg, shadow: g.shadow, pick: () => setDr({ care: id }) };
        }),
        countText: onItems.length + ' dari ' + recs.length + ' layanan dipilih',
        amountHint: amountN ? rp(amountN) : 'Total tagihan sesuai berkas klaim.',
        items: recs.map((r) => {
          const x = dr.sel[r.rid];
          const differs = !!r.qty && x.on && String(x.qty) !== String(r.qty);
          return {
            display: r.display, typeLabel: TYPE[r.type],
            codeLine: (r.cs === 'LOCAL' ? 'Kode RS ' : r.cs + ' ') + r.code,
            on: x.on, opacity: x.on ? '1' : '0.55', tint: differs ? '#FFF9F1' : '#FFFFFF',
            hasQty: !!r.qty, noQty: !r.qty, qty: x.qty, unit: r.unit, qtyLabel: 'Jumlah ' + r.display,
            differs, recorded: qtyText(r.qty, r.unit), qtyBorder: differs ? '#D08A3E' : '#CBD3CF',
            toggle: () => setDr({ sel: Object.assign({}, dr.sel, { [r.rid]: Object.assign({}, x, { on: !x.on }) }) }),
            setQty: (ev) => setDr({ sel: Object.assign({}, dr.sel, { [r.rid]: Object.assign({}, x, { qty: ev.target.value }) }) })
          };
        }),
        setPn: (ev) => setDr({ pn: ev.target.value }),
        setAmount: (ev) => setDr({ amount: ev.target.value }),
        toggleAck: () => setDr({ ack: !dr.ack }),
        invalid,
        why: invalid ? 'Belum bisa diajukan: lengkapi ' + missing.join(', ') + '.' : 'Klaim akan dikirim ke Sistem Klaim BPJS dan mendapat nomor klaim.',
        submit: () => { if (dr.error) setDr({ error: false }); submit(); },
        failDemo: () => setDr({ error: true })
      };
    }

    const cc = bclaims.find((c) => c.id === s.cid) || bclaims[0];
    let cv = {};
    if (cc) {
      const st = BST[cc.st], t = btone[st[1]];
      cv = {
        id: cc.id, status: st[0], bg: t.bg, fg: t.fg, justSent: !!s.justSent,
        steps: ['Diajukan', 'Diterima BPJS', 'Sedang diverifikasi', 'Selesai diverifikasi'].map((label, i) => ({
          label, at: cc.at[i] || (i <= st[2] ? '' : 'Belum'), bar: i <= st[2] ? accent : '#E3E8E5', fg: i <= st[2] ? '#1F2A22' : '#8A958F'
        })),
        items: cc.items.map((it) => ({ typeLabel: TYPE[it.type], display: it.display, codeLine: (it.cs === 'LOCAL' ? 'Kode RS ' : it.cs + ' ') + it.code, qtyLine: qtyText(it.qty, it.unit) || '—' })),
        facts: [
          { k: 'Kunjungan', v: cc.ref }, { k: 'Tanggal', v: cc.visitDate }, { k: 'Peserta', v: cc.pn },
          { k: 'Jenis', v: cc.care === 'RI' ? 'Rawat inap' : 'Rawat jalan' }, { k: 'Nominal', v: rp(cc.amount) }, { k: 'Diajukan oleh', v: 'Petugas Demo' }
        ],
        openVisit: () => cc.vid ? this.setState({ screen: 'visit', sel: cc.vid, open: {}, form: this.emptyForm() }) : this.setState({ screen: 'list' })
      };
    }

    const nav = (on) => ({ bg: on ? '#E2EBE4' : 'transparent', fg: on ? '#1F2A22' : '#3E4A45' });
    const navList = nav(s.screen === 'list' || s.screen === 'visit');
    const navScan = nav(s.screen === 'scan' || s.screen === 'exc');
    const navSync = nav(s.screen === 'sync');
    const navClaim = nav(['claims', 'claimForm', 'claimView'].includes(s.screen));
    const selClaim = sel.claimId && bclaims.find((c) => c.id === sel.claimId);
    vis.isDone = sel.status !== 'OPEN';
    vis.claimLabel = selClaim ? selClaim.id + ' · ' + BST[selClaim.st][0] : 'Belum diajukan';
    vis.claimBtn = selClaim ? 'Lihat klaim' : 'Ajukan klaim';
    vis.claimAct = () => selClaim ? this.setState({ screen: 'claimView', cid: selClaim.id, justSent: false }) : startDraft(sel);

    return {
      accent,
      todayText: new Intl.DateTimeFormat('id-ID', { timeZone: 'Asia/Jakarta', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date()),
      bc, cfm, cv,
      isClaims: s.screen === 'claims', isClaimForm: s.screen === 'claimForm', isClaimView: s.screen === 'claimView',
      navClaimBg: navClaim.bg, navClaimFg: navClaim.fg, navClaimCurrent: s.screen === 'claims' ? 'page' : undefined,
      goClaims: () => this.setState({ screen: 'claims', dialog: null, justSent: false }),
      dl,
      isSync: s.screen === 'sync',
      navSyncBg: navSync.bg, navSyncFg: navSync.fg, navSyncCurrent: s.screen === 'sync' ? 'page' : undefined,
      goSync: () => this.setState({ screen: 'sync', dialog: null }),
      isList: s.screen === 'list',
      isScan: s.screen === 'scan',
      isExc: s.screen === 'exc',
      isVisit: s.screen === 'visit',
      navListBg: navList.bg, navListFg: navList.fg, navListCurrent: s.screen === 'list' ? 'page' : undefined,
      navScanBg: navScan.bg, navScanFg: navScan.fg, navScanCurrent: s.screen === 'scan' ? 'page' : undefined,
      goList: () => { this.scanAttempt = null; this.setState({ screen: 'list', dialog: null, token: '' }); },
      goScan: () => { this.scanAttempt = null; this.setState({ screen: 'scan', result: null, token: '', tokenErr: false }); },

      listSummary,
      visitRows,

      modeName: s.mode === 'CHECK_IN' ? 'QR Masuk' : 'QR Keluar',
      inPressed: String(s.mode === 'CHECK_IN'), outPressed: String(s.mode === 'CHECK_OUT'),
      inBg: segIn.bg, inFg: segIn.fg, inShadow: segIn.shadow,
      outBg: segOut.bg, outFg: segOut.fg, outShadow: segOut.shadow,
      modeIn: () => { if (!s.submitting) { this.scanAttempt = null; this.setState({ mode: 'CHECK_IN', result: null, token: '' }); } },
      modeOut: () => { if (!s.submitting) { this.scanAttempt = null; this.setState({ mode: 'CHECK_OUT', result: null, token: '' }); } },
      token: s.token,
      setToken: (ev) => { if (!s.submitting) this.setState({ token: ev.target.value, tokenErr: false }); },
      noToken: !s.token.trim() || s.submitting,
      tokenErr: !!s.tokenErr,
      process: () => {
        if (s.token.trim().length < 32) { this.setState({ tokenErr: true, result: null }); return; }
        runScan();
      },
      demoButtons: [
        ['ok', 'Berhasil'], ['QR_TOKEN_EXPIRED', 'Kedaluwarsa'], ['QR_ALREADY_CONSUMED', 'Sudah dipakai'],
        ['WRONG_QR_PURPOSE', 'Jenis QR salah'], ['HTTP 503', 'JejakJKN tidak terhubung']
      ].map(([code, label]) => ({ label, run: () => code === 'ok' ? runScan() : showErr(code) })),
      noResult: !s.result,
      resOk: !!s.result && s.result.kind === 'ok',
      resErr: !!s.result && s.result.kind === 'err',
      resBorder: s.result ? (s.result.kind === 'ok' ? '#B9CBBE' : '#E7B98A') : '#DDE3DE',
      res, err,
      openExcIn: () => this.setState({ screen: 'exc', excPhase: 'CHECK_IN', exc: this.emptyExc() }),
      openExcOut: () => this.setState({ screen: 'exc', excPhase: 'CHECK_OUT', exc: this.emptyExc() }),
      excBack: () => this.setState({ screen: s.excPhase === 'CHECK_IN' ? 'scan' : 'visit' }),
      exc,

      vis, sync, form, addRecord,
      refresh: () => this.load(),
      markComplete: () => this.act(() => completeSync(sel.id)),

      dialogOpen: !!d,
      dlg,
      closeDialog: () => this.setState({ dialog: null }),

      scannerSlot: s.screen === 'scan' ? (
        <QrScannerPanel
          key={s.screen + ':' + s.mode}
          disabled={s.submitting}
          resetKey={s.screen + ':' + s.mode}
          modeName={s.mode === 'CHECK_IN' ? 'QR Masuk' : 'QR Keluar'}
          onDecoded={(token) => this.submitScan(token)}
          onError={() => undefined}
          viewfinderHeight={220}
          borderRadius={14}
        />
      ) : null
    };
  }

  render() {
    return <View v={this.renderVals()} />;
  }
}
