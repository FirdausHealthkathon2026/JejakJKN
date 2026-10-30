// @ts-nocheck -- logic ported verbatim from the design canvas; data comes from src/api.
import {Component} from "react";
import {addRecord, completeSync, fmtLongDate, loadAll, retryDelivery, scan, submitClaim} from "./api/client";
import {View} from "./design/View";

const EMPTY_VISIT = {id: '', ref: '', inT: '', outT: '', status: 'OPEN', presence: 'QR', records: [], pending: 0, failed: 0, delivered: 0, sync: 'LOCAL_ONLY', marking: false};

export default class App extends Component<object, any> {
  catalogAll() {
    return {
      TINDAKAN: [['RJ-DOK-001', 'Konsultasi dokter umum', 'layanan', 1, 'layanan'], ['MATA-01', 'Pemeriksaan mata', 'layanan', 1, 'layanan'], ['MATA-SLIT', 'Biomikroskopi slit lamp', 'layanan', 1, 'layanan'], ['JANTUNG-EKG', 'Elektrokardiografi', 'layanan', 1, 'layanan']],
      LAB: [['DL-001', 'Darah lengkap', 'pemeriksaan', 1, 'layanan']],
      OBAT: [['OB-PCT500', 'Paracetamol 500 mg', 'tablet', 1, 'tablet'], ['OB-PCT500-STR', 'Paracetamol 500 mg', 'strip (isi 10)', 10, 'tablet'], ['OB-AMX500', 'Amoxicillin 500 mg', 'tablet', 1, 'tablet'], ['OB-LFX-ED', 'Levofloxacin tetes mata 5 mL', 'botol', 1, 'botol']],
      DIAGNOSIS: [['H10.9', 'Konjungtivitis', 'diagnosis', 0, ''], ['J06.9', 'ISPA akut', 'diagnosis', 0, '']]
    };
  }

  emptyExc() {
    return { reason: null, patientId: '', ref: '', service: 'OUTPATIENT', approver: '', evidence: '', notes: '' };
  }

  newDraft(v) {
    const sel = {};
    v.records.forEach((r) => { if (r.status !== 'CANCELLED') sel[r.rid] = true; });
    return { vid: v.id, pn: v.pn, care: 'RJ', sel, amount: '', ack: false };
  }

  state = {
    screen: 'list', mode: 'IN', token: '', refInput: '', result: null, visits: [], sel: null,
    tab: 'TINDAKAN', pick: null, qty: '1', manual: false, manualCode: '',
    excPhase: 'IN', exc: this.emptyExc(), open: {}, dialog: null, deliveries: [], dFilter: 'ALL',
    bclaims: [], draft: null, cid: null, justSent: false
  };

  componentDidMount() {
    this.load();
    this.poll = setInterval(() => this.load(), 2000);
  }

  componentWillUnmount() {
    clearInterval(this.poll);
  }

  describe = (r) => {
    const c = (this.catalogAll()[r.jenis] || []).find((x) => x[0] === r.kode);
    if (!c) return r.kode;
    return r.jenis === 'DIAGNOSIS' ? c[1] : c[1] + ' · ' + (r.jumlah || 1) + ' ' + c[2].replace(' (isi 10)', '');
  };

  async load() {
    try {
      this.setState(await loadAll(this.describe));
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
    const tone = {
      ok: { bg: '#DFF0E6', fg: '#1F6B45', bar: '#2F7A55', tint: '#FFFFFF' },
      bad: { bg: '#FBE4E1', fg: '#A1271B', bar: '#C8473A', tint: '#FDF4F2' },
      warn: { bg: '#FBEBD7', fg: '#8A4206', bar: '#D08A3E', tint: '#FFFBF6' },
      info: { bg: '#E1ECF8', fg: '#1E4E8C', bar: '#2B5C8A', tint: '#FFFFFF' },
      neutral: { bg: '#E6ECF2', fg: '#3A4A5B', bar: '#C5CED8', tint: '#FFFFFF' }
    };
    const CAT = this.catalogAll();
    const find = (jenis, kode) => (CAT[jenis] || []).find((c) => c[0] === kode);
    const JENIS = { TINDAKAN: 'Tindakan', LAB: 'Lab', OBAT: 'Obat', DIAGNOSIS: 'Diagnosis' };
    const canonOf = (jenis, kode, jumlah) => {
      const c = find(jenis, kode);
      if (!c) return null;
      if (jenis === 'DIAGNOSIS') return 'Diagnosis ' + c[1];
      if (jenis !== 'OBAT') return c[1] + ' · ' + (jumlah || 1) + ' layanan';
      return c[1] + ' · ' + ((Number(jumlah) || 0) * c[3]) + ' ' + c[4] + ' diserahkan';
    };
    const localOf = (jenis, kode, jumlah) => {
      const c = find(jenis, kode);
      if (!c) return kode;
      return jenis === 'DIAGNOSIS' ? c[1] : c[1] + ' · ' + (jumlah || 1) + ' ' + c[2].replace(' (isi 10)', '');
    };
    const syncInfo = (v) => {
      if (v.sync === 'LOCAL_ONLY') return ['Belum ada pengiriman', 'neutral', 'Belum ada catatan yang dikirim.'];
      if (v.sync === 'SYNC_COMPLETE') return ['Lengkap', 'ok', 'JejakJKN sudah menerima semua catatan kunjungan ini.'];
      if (v.sync === 'FAILED') return ['Ada yang ditolak', 'bad', v.failed + ' pengiriman ditolak JejakJKN. Lihat halaman Pengiriman untuk alasannya dan kirim ulang.'];
      if (v.pending > 0) return ['Sedang dikirim', 'info', v.pending + ' pengiriman menunggu diterima JejakJKN.'];
      return ['Belum ditandai selesai', 'info', 'Semua catatan sudah diterima. Tekan "Pelayanan selesai" setelah seluruh layanan dicatat.'];
    };
    const ST = { OPEN: ['Sedang dilayani', 'info'], CHECKED_OUT: ['Sudah keluar', 'ok'], CLOSED_WITH_EXCEPTION: ['Keluar tanpa QR', 'warn'] };
    const visits = s.visits;
    const sel = visits.find((v) => v.id === s.sel) || visits[0] || EMPTY_VISIT;
    const rows = visits.map((v) => {
      const st = ST[v.status], y = syncInfo(v);
      return {
        ref: v.ref, inT: v.inT, outT: v.outT || 'Belum keluar', outColor: v.outT ? '#1C2733' : '#8794A1',
        status: st[0] + (v.presence === 'EXC' && v.status === 'OPEN' ? ' · masuk tanpa QR' : ''), sBg: tone[v.presence === 'EXC' ? 'warn' : st[1]].bg, sFg: tone[v.presence === 'EXC' ? 'warn' : st[1]].fg,
        count: v.records.length, sync: y[0], yBg: tone[y[1]].bg, yFg: tone[y[1]].fg,
        open: () => this.setState({ screen: 'visit', sel: v.id, tab: 'TINDAKAN', pick: null, qty: '1', manual: false, open: {} })
      };
    });
    const openN = visits.filter((v) => v.status === 'OPEN').length;

    const RES = {
      QR_ALREADY_CONSUMED: ['QR sudah dipakai', 'QR ini sudah pernah dipindai. Minta pasien menampilkan QR baru.'],
      QR_TOKEN_EXPIRED: ['QR sudah kedaluwarsa', 'QR hanya berlaku 60 detik. Minta pasien menampilkan QR baru.'],
      DOWN: ['JejakJKN tidak dapat dihubungi', 'Lanjutkan pelayanan. Coba pindai lagi beberapa saat lagi, atau catat pengecualian.']
    };
    const runScan = async (code) => {
      if (code !== 'ok') { this.setState({ result: { kind: code } }); return; }
      if (s.token.trim().length < 32) return;
      try {
        const scanned = await scan(s.mode, s.token.trim(), s.refInput.trim() || 'RJ-' + Date.now());
        await this.load();
        this.setState({ sel: scanned.encounter_id, token: '', result: { kind: 'ok', vid: scanned.encounter_id, mode: s.mode } });
      } catch (error) {
        this.setState({ result: { kind: RES[error.code] ? error.code : 'DOWN' } });
      }
    };
    let res = { empty: true, show: false, bar: tone.neutral.bar };
    if (s.result) {
      if (s.result.kind === 'ok') {
        const rv = visits.find((v) => v.id === s.result.vid) || visits[0];
        const isIn = s.result.mode === 'IN';
        res = { empty: false, show: true, ok: true, icon: '✓', fg: tone.ok.fg, bar: tone.ok.bar,
          title: isIn ? 'Masuk berhasil' : 'Keluar berhasil',
          text: (isIn ? 'Kunjungan ' + rv.ref + ' dibuat pukul ' + rv.inT + '.' : 'Kunjungan ' + rv.ref + ' ditutup pukul ' + rv.outT + '.') + ' Kunjungan sudah terhubung ke JejakJKN.',
          open: () => this.setState({ screen: 'visit', sel: rv.id, tab: 'TINDAKAN', pick: null, qty: '1', manual: false, open: {} }) };
      } else {
        const e = RES[s.result.kind];
        res = { empty: false, show: true, ok: false, icon: '!', fg: tone.bad.fg, bar: tone.bad.bar, title: e[0], text: e[1] };
      }
    }
    const seg = (on) => ({ bg: on ? '#2B5C8A' : '#FFFFFF', fg: on ? '#FFFFFF' : '#1C2733' });
    const sIn = seg(s.mode === 'IN'), sOut = seg(s.mode === 'OUT');

    const EXC_REASONS = [
      ['NO_SMARTPHONE', 'Pasien tidak punya ponsel pintar'],
      ['EMERGENCY_UNCONSCIOUS', 'Gawat darurat atau pasien tidak sadar'],
      ['QR_DEVICE_FAILURE', 'QR atau perangkat gagal'],
      ['NETWORK_OUTAGE', 'Gangguan jaringan'],
      ['PATIENT_INCAPACITATED', 'Pasien tidak mampu menunjukkan QR']
    ];
    const ex = s.exc || this.emptyExc();
    const setExc = (patch) => this.setState({ exc: Object.assign({}, (this.state && this.state.exc) || ex, patch) });
    const excIn = s.excPhase === 'IN';
    const excInvalid = !ex.reason || !ex.approver.trim() || (excIn && !ex.patientId.trim());
    const exc = {
      isIn: excIn, isOut: !excIn,
      title: excIn ? 'Catat pengecualian masuk' : 'Tutup kunjungan tanpa QR keluar',
      sub: excIn ? 'Untuk pasien yang tidak dapat menunjukkan QR Masuk saat mendaftar.' : 'Untuk pasien yang tidak dapat menunjukkan QR Keluar saat pulang.',
      backLabel: excIn ? 'Pindai QR pasien' : 'Kembali ke kunjungan',
      submitLabel: excIn ? 'Simpan dan buat kunjungan' : 'Simpan dan tutup kunjungan',
      visitRef: sel.ref, visitIn: sel.inT + ' WIB',
      patientId: ex.patientId, ref: ex.ref, service: ex.service, approver: ex.approver, evidence: ex.evidence, notes: ex.notes,
      setPatientId: (e) => setExc({ patientId: e.target.value }),
      setRef: (e) => setExc({ ref: e.target.value }),
      setService: (e) => setExc({ service: e.target.value }),
      setApprover: (e) => setExc({ approver: e.target.value }),
      setEvidence: (e) => setExc({ evidence: e.target.value }),
      setNotes: (e) => setExc({ notes: e.target.value.slice(0, 500) }),
      reasons: EXC_REASONS.map(([code, label]) => ({
        label, checked: ex.reason === code,
        border: ex.reason === code ? '#2B5C8A' : '#D8DFE6', bg: ex.reason === code ? '#EEF4FA' : '#FFFFFF',
        pick: () => setExc({ reason: code })
      })),
      invalid: excInvalid,
      submit: () => { if (!excInvalid) window.alert('Jalur pengecualian belum tersambung ke backend pada versi demo ini.'); }
    };

    const REC = { ACTIVE: ['Aktif', 'neutral'], CORRECTED: ['Dikoreksi', 'info'], CANCELLED: ['Dibatalkan', 'bad'] };
    const ACT = { RECORDED: ['Dicatat', 'neutral'], CORRECTED: ['Dikoreksi', 'info'], CANCELLED: ['Dibatalkan', 'bad'] };
    const open = s.open || {};
    const st = ST[sel.status];
    const active = sel.records.filter((r) => r.status !== 'CANCELLED').length;
    const vis = {
      ref: sel.ref, inT: sel.inT, outT: sel.outT || 'belum', status: st[0], sBg: tone[st[1]].bg, sFg: tone[st[1]].fg,
      isOpen: sel.status === 'OPEN',
      countText: active + ' aktif' + (sel.records.length > active ? ' · ' + (sel.records.length - active) + ' dibatalkan' : ''),
      empty: sel.records.length === 0,
      records: sel.records.map((r) => {
        const c = find(r.jenis, r.kode);
        const cancelled = r.status === 'CANCELLED';
        const rs = REC[r.status];
        return {
          jenis: JENIS[r.jenis], kode: r.kode,
          local: c ? c[1] + (r.jenis === 'OBAT' ? ' (per ' + c[2] + ')' : '') : r.kode,
          qty: r.jumlah ? r.jumlah + ' ' + (c ? c[2].replace(' (isi 10)', '') : '') : '—',
          canon: cancelled ? 'Dibatalkan di JejakJKN' : (canonOf(r.jenis, r.kode, r.jumlah) || 'Belum dapat dipetakan'),
          ver: r.ver, stLabel: rs[0], stBg: tone[rs[1]].bg, stFg: tone[rs[1]].fg,
          strike: cancelled ? 'line-through' : 'none', opacity: cancelled ? '0.7' : '1',
          canEdit: !cancelled, isOpen: !!open[r.rid], expanded: String(!!open[r.rid]), caret: open[r.rid] ? '▴' : '▾',
          hist: r.hist.map((h) => { const a = ACT[h.action]; return { v: h.v, action: a[0], time: h.time, who: h.who, desc: h.desc, note: h.note, hasNote: !!h.note, bg: tone[a[1]].bg, fg: tone[a[1]].fg }; }),
          toggle: () => this.setState({ open: Object.assign({}, open, { [r.rid]: !open[r.rid] }) }),
          correct: () => this.setState({ dialog: { type: 'correct', rid: r.rid, kode: r.kode, qty: String(r.jumlah || 1), reason: '' } }),
          cancel: () => this.setState({ dialog: { type: 'cancel', rid: r.rid, reason: '' } })
        };
      })
    };
    const y = syncInfo(sel);
    const sync = { label: y[0], bg: tone[y[1]].bg, fg: tone[y[1]].fg, text: y[2], pending: sel.pending, failed: sel.failed, delivered: sel.delivered,
      failedBg: sel.failed ? tone.bad.bg : '#F5F7F9', failedFg: sel.failed ? tone.bad.fg : '#1C2733',
      cannotMark: sel.records.length === 0 || sel.sync === 'SYNC_COMPLETE' || sel.marking };

    const list = CAT[s.tab] || [];
    const pickRow = list.find((c) => c[0] === s.pick);
    const manualRow = s.manual ? find(s.tab, s.manualCode.trim()) : null;
    const chosen = s.manual ? manualRow : pickRow;
    const unknown = s.manual && s.manualCode.trim() && !manualRow;
    const isDiag = s.tab === 'DIAGNOSIS';
    let preview;
    if (unknown) preview = { title: 'Kode tidak dikenali', text: 'Kode ' + s.manualCode.trim() + ' belum ada di katalog pemetaan JejakJKN.', note: 'Catatan ini tidak bisa dikirim. Pilih dari katalog, atau minta admin SIMRS menambahkan pemetaan kode ini.', bg: tone.bad.bg, border: '#E9B6AE', fg: tone.bad.fg, hasNote: true };
    else if (chosen) preview = { title: 'Akan tercatat di JejakJKN sebagai', text: canonOf(s.tab, chosen[0], s.qty), note: s.tab === 'OBAT' && chosen[3] > 1 ? '1 ' + chosen[2] + ' dihitung sebagai ' + chosen[3] + ' ' + chosen[4] + '.' : '', bg: tone.ok.bg, border: '#B5D8C3', fg: tone.ok.fg, hasNote: s.tab === 'OBAT' && chosen[3] > 1 };
    else preview = { title: 'Pratinjau', text: 'Pilih item untuk melihat bagaimana catatan ini tercatat di JejakJKN.', note: '', bg: '#F5F7F9', border: '#D8DFE6', fg: '#5A6876', hasNote: false };
    const cannotSave = !chosen || (!isDiag && !(Number(s.qty) > 0));

    const d = s.dialog;
    let dlg = {};
    if (d) {
      const rec = sel.records.find((r) => r.rid === d.rid) || sel.records[0];
      const isCorrect = d.type === 'correct';
      const setD = (patch) => this.setState({ dialog: Object.assign({}, (this.state && this.state.dialog) || d, patch) });
      const hasQty = rec.jenis !== 'DIAGNOSIS';
      const nc = find(rec.jenis, d.kode);
      const changed = isCorrect && (d.kode !== rec.kode || String(d.qty) !== String(rec.jumlah || 1));
      const invalid = !d.reason.trim() || (isCorrect && (!changed || (hasQty && !(Number(d.qty) > 0))));
      dlg = {
        isCorrect, hasQty, ver: rec.ver, nextVer: rec.ver + 1,
        title: isCorrect ? 'Koreksi catatan' : 'Batalkan catatan',
        sub: isCorrect ? 'Versi lama tetap tersimpan di riwayat. Versi baru dikirim ke JejakJKN.' : 'Catatan tidak dihapus. Statusnya menjadi dibatalkan, dan pembatalan dikirim ke JejakJKN.',
        current: localOf(rec.jenis, rec.kode, rec.jumlah) + ' → ' + (canonOf(rec.jenis, rec.kode, rec.jumlah) || ''),
        kode: d.kode, qty: d.qty, unit: nc ? nc[2] : '',
        options: (CAT[rec.jenis] || []).map((c) => ({ kode: c[0], name: c[1], per: c[2], checked: d.kode === c[0], border: d.kode === c[0] ? '#2B5C8A' : '#D8DFE6', bg: d.kode === c[0] ? '#EEF4FA' : '#FFFFFF', pick: () => setD({ kode: c[0] }) })),
        next: nc ? localOf(rec.jenis, d.kode, d.qty) + ' → ' + canonOf(rec.jenis, d.kode, d.qty) : '',
        reason: d.reason, reasonLabel: isCorrect ? 'Alasan koreksi' : 'Alasan pembatalan',
        setKode: (e) => setD({ kode: e.target.value }), setQty: (e) => setD({ qty: e.target.value }), setReason: (e) => setD({ reason: e.target.value.slice(0, 500) }),
        submitLabel: isCorrect ? 'Simpan koreksi' : 'Batalkan catatan', btnBg: isCorrect ? '#2B5C8A' : '#A1271B', bar: isCorrect ? '#2B5C8A' : '#C8473A',
        invalid,
        submit: () => { if (!invalid) window.alert('Koreksi dan pembatalan SIMRS B belum tersambung ke backend pada versi demo ini.'); }
      };
    }

    const DT = { DELIVERED: ['Diterima', 'ok', '✓'], PENDING: ['Menunggu', 'info', '…'], RETRYING: ['Mencoba lagi', 'warn', '↻'], FAILED: ['Ditolak', 'bad', '✗'] };
    const dels = s.deliveries || [];
    const dCount = (k) => dels.filter((x) => x.st === k).length;
    const problems = dCount('FAILED');
    const dFilter = s.dFilter || 'ALL';
    const dl = {
      tiles: [
        { n: dCount('PENDING') + dCount('RETRYING'), label: 'Menunggu diterima', sub: 'Termasuk yang sedang dicoba lagi otomatis', fg: tone.info.fg, bar: tone.info.bar },
        { n: dCount('FAILED'), label: 'Ditolak JejakJKN', sub: 'Perlu diperiksa dan dikirim ulang', fg: tone.bad.fg, bar: tone.bad.bar },
        { n: dCount('DELIVERED'), label: 'Diterima hari ini', sub: 'Sudah tersimpan di JejakJKN', fg: tone.ok.fg, bar: tone.ok.bar }
      ],
      filters: [['ALL', 'Semua'], ['WAIT', 'Menunggu'], ['FAILED', 'Ditolak'], ['DELIVERED', 'Diterima']].map(([id, label]) => ({
        label, pressed: String(dFilter === id),
        count: id === 'ALL' ? dels.length : id === 'WAIT' ? dCount('PENDING') + dCount('RETRYING') : dCount(id),
        border: dFilter === id ? '#2B5C8A' : '#C5CED8', bg: dFilter === id ? '#2B5C8A' : '#FFFFFF', fg: dFilter === id ? '#FFFFFF' : '#1C2733',
        pick: () => this.setState({ dFilter: id })
      })),
      rows: dels.filter((x) => dFilter === 'ALL' || (dFilter === 'WAIT' ? (x.st === 'PENDING' || x.st === 'RETRYING') : x.st === dFilter)).map((x) => {
        const t = DT[x.st], tn = tone[t[1]];
        const v = visits.find((vv) => vv.id === x.vid) || visits[0];
        return {
          time: x.time, ref: v.ref, what: x.what, kind: x.kind, status: t[0], icon: t[2], bg: tn.bg, fg: tn.fg, bar: tn.bar, tint: tn.tint,
          note: x.note, canRetry: x.st === 'FAILED',
          retry: () => this.act(() => retryDelivery(x.id)),
          open: () => this.setState({ screen: 'visit', sel: v.id, open: {}, tab: 'TINDAKAN', pick: null })
        };
      })
    };
    dl.empty = dl.rows.length === 0;

    // Klaim BPJS
    const rp = (n) => 'Rp' + String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const bclaims = s.bclaims || [];
    const BST = { RECEIVED: ['Diterima BPJS', 'info', 1], VERIFYING: ['Sedang diverifikasi', 'warn', 2], DONE: ['Selesai diverifikasi', 'ok', 3] };
    const canonShort = (r) => (canonOf(r.jenis, r.kode, r.jumlah) || r.kode).replace(/^Diagnosis /, '').replace(/ diserahkan$/, '');
    const readiness = (v) => {
      if (v.status === 'OPEN') return ['Belum bisa', 'neutral', 'Pasien belum keluar.', true];
      if (v.sync === 'FAILED') return ['Perlu dicek', 'warn', 'Ada catatan yang ditolak JejakJKN.', false];
      if (v.sync !== 'SYNC_COMPLETE') return ['Perlu dicek', 'warn', 'Belum ditandai pelayanan selesai.', false];
      return ['Siap diajukan', 'ok', 'Semua catatan diterima JejakJKN.', false];
    };
    const rd = visits.filter((v) => !v.claimId).map((v) => ({ v, r: readiness(v) }));
    const nOf = (lab) => rd.filter((x) => x.r[0] === lab).length;
    const startDraft = (v) => this.setState({ screen: 'claimForm', draft: this.newDraft(v), dialog: null });
    const bc = {
      tiles: [
        { n: nOf('Siap diajukan'), label: 'Siap diajukan', sub: 'Data lengkap di JejakJKN', fg: tone.ok.fg, bar: tone.ok.bar },
        { n: nOf('Perlu dicek'), label: 'Perlu dicek dulu', sub: 'Masih bisa diajukan', fg: tone.warn.fg, bar: tone.warn.bar },
        { n: nOf('Belum bisa'), label: 'Sedang dilayani', sub: 'Pasien belum keluar', fg: '#1C2733', bar: tone.neutral.bar },
        { n: bclaims.length, label: 'Sudah diajukan', sub: 'Termasuk hari sebelumnya', fg: tone.info.fg, bar: tone.info.bar }
      ],
      visits: rd.map(({ v, r }) => {
        const t = tone[r[1]], ready = r[0] === 'Siap diajukan';
        return {
          ref: v.ref, time: v.inT + ' – ' + (v.outT || '…'), count: v.records.filter((x) => x.status !== 'CANCELLED').length,
          label: r[0], note: r[2], bg: t.bg, fg: t.fg, blocked: r[3],
          btnBg: ready ? '#2B5C8A' : '#FFFFFF', btnFg: ready ? '#FFFFFF' : '#1C2733', btnBorder: ready ? '#2B5C8A' : '#C5CED8',
          start: () => { if (!r[3]) startDraft(v); }
        };
      }),
      sent: bclaims.map((c) => {
        const st = BST[c.st], t = tone[st[1]];
        return { id: c.id, ref: c.ref, visitDate: c.visitDate, sentAt: c.at[0], amount: rp(c.amount), status: st[0], bg: t.bg, fg: t.fg,
          tint: c.id === s.cid && s.justSent ? '#F3FAF6' : '#FFFFFF', open: () => this.setState({ screen: 'claimView', cid: c.id, justSent: false }) };
      })
    };
    const dr = s.draft;
    let cfm = {};
    if (dr) {
      const dv = visits.find((v) => v.id === dr.vid) || visits[0];
      const setDr = (patch) => this.setState({ draft: Object.assign({}, (this.state && this.state.draft) || dr, patch) });
      const recs = dv.records.filter((r) => r.rid in dr.sel);
      const onRecs = recs.filter((r) => dr.sel[r.rid]);
      const amountN = parseInt(String(dr.amount).replace(/\D/g, ''), 10) || 0;
      const missing = [];
      if (String(dr.pn).trim().length < 3) missing.push('nomor peserta');
      if (!onRecs.length) missing.push('minimal 1 layanan');
      if (!amountN) missing.push('nominal tagihan');
      if (!dr.ack) missing.push('centang pemeriksaan');
      const invalid = missing.length > 0;
      cfm = {
        ref: dv.ref, pn: dr.pn, care: dr.care, amount: dr.amount, ack: dr.ack,
        hasSyncWarn: dv.sync === 'FAILED',
        date: fmtLongDate(dv.startedAt) + ' · ' + dv.inT + ' – ' + (dv.outT || '…'),
        countText: onRecs.length + ' dari ' + recs.length + ' dipilih',
        amountHint: amountN ? rp(amountN) : 'Total tagihan sesuai berkas klaim.',
        items: recs.map((r) => ({
          jenis: JENIS[r.jenis], kode: r.kode, local: localOf(r.jenis, r.kode, r.jumlah), canon: canonShort(r),
          on: !!dr.sel[r.rid], opacity: dr.sel[r.rid] ? '1' : '0.55',
          toggle: () => setDr({ sel: Object.assign({}, dr.sel, { [r.rid]: !dr.sel[r.rid] }) })
        })),
        setPn: (e) => setDr({ pn: e.target.value }), setCare: (e) => setDr({ care: e.target.value }),
        setAmount: (e) => setDr({ amount: e.target.value }), toggleAck: () => setDr({ ack: !dr.ack }),
        invalid,
        why: invalid ? 'Belum bisa diajukan: lengkapi ' + missing.join(', ') + '.' : 'Klaim akan dikirim ke Sistem Klaim BPJS dan mendapat nomor klaim.',
        submit: async () => {
          if (invalid) return;
          const claim = await submitClaim(dv, dr, onRecs, amountN);
          await this.load();
          this.setState({ draft: null, screen: 'claimView', cid: claim.id, justSent: true });
        }
      };
    }
    const cc = bclaims.find((c) => c.id === s.cid) || bclaims[0];
    let cv = {};
    if (cc) {
      const st = BST[cc.st], t = tone[st[1]];
      cv = {
        id: cc.id, status: st[0], bg: t.bg, fg: t.fg, justSent: !!s.justSent,
        steps: ['Diajukan', 'Diterima BPJS', 'Sedang diverifikasi', 'Selesai diverifikasi'].map((label, i) => ({
          label, at: cc.at[i] || 'Belum', bar: i <= st[2] ? '#2B5C8A' : '#D8DFE6', fg: i <= st[2] ? '#1C2733' : '#8794A1'
        })),
        items: cc.items.map((r) => ({ jenis: JENIS[r.jenis], canon: canonShort(r) })),
        facts: [{ k: 'Kunjungan', v: cc.ref }, { k: 'Tanggal', v: cc.visitDate }, { k: 'Peserta', v: cc.pn }, { k: 'Jenis', v: cc.care === 'RI' ? 'Rawat inap' : 'Rawat jalan' }, { k: 'Nominal', v: rp(cc.amount) }]
      };
    }

    return {
      nav: [['list', 'Pasien hari ini'], ['scan', 'Pindai QR'], ['sync', 'Pengiriman'], ['claims', 'Klaim BPJS']].map(([id, label]) => {
        const on = s.screen === id || (id === 'list' && s.screen === 'visit') || (id === 'scan' && s.screen === 'exc' && excIn) || (id === 'claims' && (s.screen === 'claimForm' || s.screen === 'claimView'));
        return { label, border: on ? '#7FB2E0' : 'transparent', fg: on ? '#FFFFFF' : '#B7C4D1', current: on ? 'page' : undefined,
          hasBadge: id === 'sync' && problems > 0, badge: problems,
          go: () => this.setState({ screen: id, result: null, token: '', dialog: null, justSent: false }) };
      }),
      todayText: new Intl.DateTimeFormat('id-ID', { timeZone: 'Asia/Jakarta', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date()),
      bc, cfm, cv,
      isClaims: s.screen === 'claims', isClaimForm: s.screen === 'claimForm', isClaimView: s.screen === 'claimView',
      goClaims: () => this.setState({ screen: 'claims', dialog: null, justSent: false }),
      goSync: () => this.setState({ screen: 'sync', dialog: null }),
      isList: s.screen === 'list', isScan: s.screen === 'scan', isVisit: s.screen === 'visit', isExc: s.screen === 'exc', isSync: s.screen === 'sync',
      goList: () => this.setState({ screen: 'list', dialog: null }),
      goScan: () => this.setState({ screen: 'scan', result: null, token: '' }),
      listSummary: visits.length + ' kunjungan · ' + openN + ' sedang dilayani',
      rows,

      modeName: s.mode === 'IN' ? 'QR Masuk' : 'QR Keluar', isIn: s.mode === 'IN',
      inPressed: String(s.mode === 'IN'), outPressed: String(s.mode === 'OUT'),
      inBg: sIn.bg, inFg: sIn.fg, outBg: sOut.bg, outFg: sOut.fg,
      modeIn: () => this.setState({ mode: 'IN', result: null }),
      modeOut: () => this.setState({ mode: 'OUT', result: null }),
      token: s.token, setToken: (e) => this.setState({ token: e.target.value }),
      refInput: s.refInput, setRef: (e) => this.setState({ refInput: e.target.value }),
      noToken: s.token.trim().length < 32,
      process: () => runScan('ok'),
      demo: [['ok', 'Berhasil'], ['QR_ALREADY_CONSUMED', 'Sudah dipakai'], ['QR_TOKEN_EXPIRED', 'Kedaluwarsa'], ['DOWN', 'Tidak terhubung']].map(([k, label]) => ({ label, run: () => runScan(k) })),
      res,
      openExcIn: () => this.setState({ screen: 'exc', excPhase: 'IN', exc: this.emptyExc() }),
      openExcOut: () => this.setState({ screen: 'exc', excPhase: 'OUT', exc: this.emptyExc() }),
      excBack: () => this.setState({ screen: excIn ? 'scan' : 'visit' }),
      exc,

      vis, sync,
      refresh: () => this.load(),
      markDone: () => this.act(() => completeSync(sel.id)),
      tabs: Object.keys(JENIS).map((k) => ({ label: JENIS[k], pressed: String(s.tab === k), bg: s.tab === k ? '#2B5C8A' : '#FFFFFF', fg: s.tab === k ? '#FFFFFF' : '#1C2733', pick: () => this.setState({ tab: k, pick: null, manualCode: '' }) })),
      catalog: list.map((c) => ({ kode: c[0], name: c[1], per: c[2], checked: s.pick === c[0], border: s.pick === c[0] ? '#2B5C8A' : '#D8DFE6', bg: s.pick === c[0] ? '#EEF4FA' : '#FFFFFF', pick: () => this.setState({ pick: c[0] }) })),
      manualOn: !!s.manual, manualOff: !s.manual,
      manualCode: s.manualCode, setManual: (e) => this.setState({ manualCode: e.target.value }),
      toggleManual: () => this.setState({ manual: !s.manual, manualCode: '', pick: null }),
      manualToggleLabel: s.manual ? 'Pilih dari katalog' : 'Ketik kode manual',
      hasQty: !isDiag,
      unitLabel: chosen ? chosen[2] : (s.tab === 'OBAT' ? 'sesuai kemasan' : 'layanan'),
      qty: s.qty, setQty: (e) => this.setState({ qty: e.target.value }),
      preview, cannotSave,
      save: () => {
        if (cannotSave) return;
        this.act(() => addRecord(sel.id, s.tab, chosen[0], isDiag ? null : s.qty), { pick: null, qty: '1', manualCode: '' });
      },

      dialogOpen: !!d, dlg,
      closeDialog: () => this.setState({ dialog: null }),
      dl
    };
  }

  render() {
    return <View v={this.renderVals()} />;
  }
}
