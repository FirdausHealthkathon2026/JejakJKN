// @ts-nocheck -- logic ported verbatim from the design canvas; data comes from src/api.
import {Component} from "react";
import {assignCase, decideCase, getCase, importClaims, listAssessments, listCases, listClaims, login, logout, recheckVerification, setClaimStatus, submitVerification, verificationDetail, waitForAssessment} from "./api/client";
import {parseClaimsCsv} from "./domain/csv";
import {buildScenario, fmtDate, fmtStamp, fmtTime, mapCase, mapClaim} from "./domain/scenario";
import {View} from "./design/View";

const BATCH_WORKERS = 8;
const MAX_CLAIM_ROWS = 100;
const FACILITY_NAMES = {'HOSP-DEMO-001': 'RS Demo Satu', 'HOSP-DEMO-002': 'RS Demo Dua'};
function saveCsv(fileName, rows) {
  const text = rows.map((row) => row.map((cell) => '"' + String(cell ?? '').replace(/"/g, '""') + '"').join(',')).join('\n');
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }));
  link.download = fileName;
  link.click();
}

const EMPTY_CLAIM = {id: '', rel: 'ORIGINAL', relId: '', pn: '', name: '', facName: '', date: '', days: 1, amount: 0, src: 'FASKES', items: []};
const EMPTY_CASE = {id: '', claimId: '', opened: '', state: 'OPEN', stale: false, owner: null, findingCodes: [], ai: {method: 'LLM', at: '', ready: false, text: null}, history: []};

export default class App extends Component<object, any> {
  state = {
    screen: 'login', q: '', src: 'ALL', claimId: null, job: null, from: 'claims',
    claims: [], assess: {}, details: {}, cases: [], runN: null, caseFilter: 'ALL',
    caseId: null, decision: null, reason: '', role: 'verifier', assignTo: '', username: '',
    up: { phase: 'pick' }
  };

  componentDidMount() {
    this.poll = setInterval(() => {
      const s = this.state;
      if (s.screen !== 'login' && s.up.phase !== 'run') this.refresh();
    }, 5000);
  }

  componentWillUnmount() {
    clearInterval(this.poll);
  }

  async signIn(username) {
    await login(username);
    this.setState({ username, role: username.startsWith('supervisor') ? 'supervisor' : 'verifier', screen: username.startsWith('supervisor') ? 'cases' : 'claims', caseFilter: username.startsWith('supervisor') ? 'MINE' : 'ALL' });
    await this.refresh();
  }

  async refresh() {
    try {
      const [rawClaims, assessments, rawCases] = await Promise.all([listClaims(), listAssessments(), listCases()]);
      const assess = {};
      for (const row of assessments) assess[row.claim_id] = row;
      this.setState((s) => ({
        claims: rawClaims.map(mapClaim), assess,
        cases: rawCases.map((row) => {
          const mapped = mapCase(row);
          const known = s.cases.find((c) => c.id === row.id);
          return known && known.history.length > 1 ? Object.assign(mapped, { history: known.history, ai: known.ai.ready ? known.ai : mapped.ai }) : mapped;
        })
      }));
    } catch (error) {
      if (error.status === 401) this.setState({ screen: 'login' });
    }
  }

  async loadDetail(claimId) {
    const assessment = this.state.assess[claimId];
    if (!assessment) return;
    const detail = await verificationDetail(claimId, assessment.verification_id);
    this.setState((s) => ({ details: Object.assign({}, s.details, { [claimId]: detail }) }));
  }

  async loadCase(caseId) {
    const row = await getCase(caseId);
    this.setState((s) => ({ cases: s.cases.map((c) => c.id === caseId ? mapCase(row) : c) }));
    return row;
  }

  // Keeps the review page live until the narrative worker has stored its summary.
  watchNarrative(caseId, attempts = 30) {
    clearTimeout(this.narrativeTimer);
    this.narrativeTimer = setTimeout(async () => {
      if (this.state.screen !== 'case' || this.state.caseId !== caseId) return;
      const row = await this.loadCase(caseId);
      if (!row.narrative && attempts > 0) this.watchNarrative(caseId, attempts - 1);
    }, 2000);
  }

  async enterCase(c, from) {
    this.setState({ screen: 'case', caseId: c.id, claimId: c.claimId, runN: null, from: from || 'cases', decision: null, reason: '', assignTo: '' });
    await Promise.all([this.loadCase(c.id), this.loadDetail(c.claimId)]);
    this.watchNarrative(c.id);
  }

  async runJob(kind) {
    const claim = this.state.claims.find((c) => c.id === this.state.claimId);
    this.setState({ screen: 'job', job: { status: 'QUEUED', ticks: 0, kind } });
    try {
      const existing = this.state.assess[claim.id];
      await setClaimStatus(claim.id, 'VERIFYING');
      const queued = kind === 'recheck' && existing ? await recheckVerification(existing.verification_id) : await submitVerification(claim.raw);
      this.setState({ job: { status: 'RUNNING', ticks: 0, kind } });
      const assessment = await waitForAssessment(queued.verification_id);
      if (assessment.status === 'FAILED') throw new Error('Verification failed');
      await this.finishJob(claim, assessment);
    } catch {
      this.setState({ job: { status: 'FAILED', ticks: 0, kind } });
    }
  }

  async finishJob(claim, assessment) {
    await this.refresh();
    if (!assessment.review_required) {
      await setClaimStatus(claim.id, 'DONE');
      await this.loadDetail(claim.id);
      this.setState({ screen: 'result', runN: null, job: null, from: 'claims' });
      return;
    }
    let found = null;
    for (let i = 0; i < 40 && !found; i++) {
      found = this.state.cases.find((c) => c.claimId === claim.id);
      if (!found) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        await this.refresh();
      }
    }
    this.setState({ job: null });
    if (found) await this.enterCase(found, 'claims');
    else this.setState({ screen: 'result', runN: null });
  }

  async pickCsv(fileName, text) {
    const parsed = parseClaimsCsv(fileName, text);
    this.setState({ up: { phase: 'preview', parsed, uploadedAt: new Date().toISOString() } });
  }

  async pickPublic(fileName) {
    const response = await fetch('/' + fileName);
    await this.pickCsv(fileName, await response.text());
  }

  pickLocal() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.csv,text/csv';
    input.onchange = async () => {
      const file = input.files[0];
      if (file) await this.pickCsv(file.name, await file.text());
    };
    input.click();
  }

  async runBatch() {
    const { parsed } = this.state.up;
    const started = new Date().toISOString();
    const total = parsed.claims.length;
    const counts = { done: 0, clear: 0, flagged: 0, failed: 0 };
    this.setState({ up: { phase: 'run', parsed, startedAt: started, ...counts } });
    let raw;
    try {
      await importClaims(parsed.fileName, parsed.claims);
      raw = await listClaims();
    } catch {
      const issue = { line: 'File', claim: parsed.fileName, what: 'Klaim gagal disimpan.', text: 'Sistem Klaim BPJS tidak dapat menerima file ini. Periksa isi file lalu coba lagi.' };
      this.setState({ up: { phase: 'preview', parsed: { ...parsed, issues: [issue, ...parsed.issues] } } });
      return;
    }
    const byId = new Map(raw.map((row) => [row.id, row]));
    const queue = [...parsed.claims];
    const worker = async () => {
      while (queue.length) {
        const claim = byId.get(queue.shift().id);
        try {
          const queued = await submitVerification(claim);
          const assessment = await waitForAssessment(queued.verification_id, 120000, 300);
          if (assessment.status === 'FAILED') counts.failed += 1;
          else if (assessment.review_required) counts.flagged += 1;
          else counts.clear += 1;
        } catch {
          counts.failed += 1;
        }
        counts.done += 1;
        this.setState({ up: { phase: 'run', parsed, startedAt: started, ...counts } });
      }
    };
    await Promise.all(Array.from({ length: BATCH_WORKERS }, worker));
    await this.refresh();
    this.setState({ up: { phase: 'done', parsed, startedAt: started, endedAt: new Date().toISOString(), ...counts }, lastBatch: parsed.fileName });
  }

  async afterDecision(kcase, decision) {
    if (decision === 'NO_ACTION' || decision === 'CLOSE_REVIEW') await setClaimStatus(kcase.claimId, 'DONE');
    await Promise.all([this.loadCase(kcase.id), this.refresh()]);
  }

  renderVals() {
    const s = this.state;
    const accent = this.props.accent ?? '#3F5E48';
    const tone = {
      ok: { bg: '#E2EBE4', fg: '#2F4A37', bar: '#5E8A69', tint: '#F6FAF7', icon: '✓' },
      bad: { bg: '#FBE4E1', fg: '#A1271B', bar: '#C8473A', tint: '#FDF4F2', icon: '✗' },
      warn: { bg: '#FBEBD7', fg: '#8A4206', bar: '#D08A3E', tint: '#FFF9F1', icon: '!' },
      info: { bg: '#E1ECF8', fg: '#1E4E8C', bar: '#5B8BC9', tint: '#F4F8FD', icon: 'i' },
      neutral: { bg: '#E8ECEA', fg: '#3E4A45', bar: '#AAB4AF', tint: '#FFFFFF', icon: '–' }
    };
    const rp = (n) => 'Rp' + String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const num = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    const CASE = { OPEN: ['Belum ditinjau', 'info'], IN_REVIEW: ['Sedang ditinjau', 'info'], NEEDS_MORE_EVIDENCE: ['Menunggu klarifikasi', 'warn'], COMPLETED: ['Selesai', 'ok'] };
    const DEC = [
      ['NO_ACTION', 'Klaim wajar', 'Setelah ditinjau, tidak ada yang perlu ditindaklanjuti.', 'COMPLETED'],
      ['REQUEST_CLARIFICATION', 'Minta klarifikasi', 'Perlu penjelasan atau bukti tambahan dari faskes.', 'NEEDS_MORE_EVIDENCE'],
      ['ESCALATE', 'Teruskan ke supervisor', 'Perlu keputusan dari pihak yang lebih berwenang.', 'IN_REVIEW'],
      ['CLOSE_REVIEW', 'Tutup peninjauan', 'Hentikan peninjauan tanpa tindak lanjut lain.', 'COMPLETED']
    ];
    const claims = s.claims;
    const scOf = (c) => buildScenario(c, s.assess[c.id], s.details[c.id]);
    const runOf = (a, re) => ({ n: 1, at: fmtStamp(a.completed_at || a.created_at), stale: a.data_freshness !== 'CURRENT', re, via: '' });
    const runsFor = (c) => {
      const a = s.assess[c.id];
      if (!a) return [];
      const history = s.details[c.id]?.history;
      const rows = history && history.length ? [...history].reverse() : [a];
      return rows.map((row, i) => Object.assign(runOf(row, i > 0), { n: i + 1, via: c.src === 'CSV' ? 'Dari unggahan ' + c.file : 'Diperiksa satu per satu' }));
    };
    const runs = {};
    for (const c of claims) runs[c.id] = runsFor(c);
    const caseOf = (id) => s.cases.find((c) => c.claimId === id);
    const lastRun = (id) => { const l = runs[id] || []; return l[l.length - 1]; };
    const qtyOf = (it, n) => it.kind === 'Obat' ? (n ?? it.qty) + ' ' + it.unit : it.kind === 'Diagnosis' ? 'Dicantumkan' : '1 kali';
    const stay = (c) => c.days > 1 ? 'Rawat inap · ' + c.days + ' hari' : 'Rawat jalan';
    const where = (c) => c.facName + ' · ' + c.date;
    const srcLabel = (c) => c.src === 'CSV' ? 'Unggahan CSV' : 'Diajukan faskes';
    const batchFile = s.lastBatch || claims.find((c) => c.file)?.file;
    const batchClaims = claims.filter((c) => c.file && c.file === batchFile);
    const flaggedBatch = batchClaims.filter((c) => s.assess[c.id]?.review_required);
    const BATCH = {
      file: batchFile || 'belum ada', when: s.up.endedAt ? fmtStamp(s.up.startedAt) + ' – ' + fmtTime(s.up.endedAt) : '', total: batchClaims.length,
      rows: batchClaims.reduce((n, c) => n + c.items.length, 0), flagged: flaggedBatch.length, clear: batchClaims.length - flaggedBatch.length, failed: s.up.failed || 0,
      amount: batchClaims.reduce((n, c) => n + c.amount, 0), review: flaggedBatch.reduce((n, c) => n + c.amount, 0)
    };

    const q = s.q.trim().toLowerCase();
    const bySrc = (c, id) => id === 'ALL' || c.src === id;
    const srcFilters = [['ALL', 'Semua'], ['FASKES', 'Diajukan faskes'], ['CSV', 'Dari unggahan CSV']].map(([id, label]) => ({
      label, count: claims.filter((c) => bySrc(c, id)).length, pressed: String(s.src === id),
      border: s.src === id ? accent : '#CBD3CF', bg: s.src === id ? '#E2EBE4' : '#FFFFFF',
      pick: () => this.setState({ src: id })
    }));
    const openResult = (id, from) => {
      const kc = caseOf(id);
      if (kc) openCase(kc, from || 'claims');
      else {
        this.setState({ screen: 'result', claimId: id, runN: null, from: from || 'claims' });
        this.loadDetail(id);
      }
    };
    const rank = (c) => (!s.assess[c.id] ? 0 : s.assess[c.id].review_required ? 1 : 2);
    const matchedClaims = claims.filter((c) => bySrc(c, s.src) && (!q || c.id.toLowerCase().includes(q) || c.pn.toLowerCase().includes(q))).sort((x, y) => rank(x) - rank(y));
    const claimRows = matchedClaims.slice(0, MAX_CLAIM_ROWS).map((c) => {
      const lr = lastRun(c.id), kc = caseOf(c.id), sc = scOf(c);
      const rev = !!(lr && kc && kc.state !== 'COMPLETED');
      let st;
      if (!lr) st = ['Belum diperiksa', 'neutral', ''];
      else if (lr.stale) st = ['Data berubah', 'warn', 'Periksa ulang untuk hasil terbaru'];
      else if (sc.clear) st = ['Sesuai', 'ok', sc.short];
      else if (kc && kc.state === 'COMPLETED') st = ['Selesai ditinjau', 'ok', sc.short];
      else st = ['Perlu ditinjau', 'warn', sc.short];
      const csv = c.src === 'CSV';
      return {
        id: c.id, kind: c.rel === 'CORRECTION' ? 'Koreksi dari ' + c.relId : (csv ? c.file : 'Klaim asli'),
        src: csv ? 'CSV' : 'Faskes', srcBg: csv ? '#E1ECF8' : '#EEF1EE', srcFg: csv ? '#1E4E8C' : '#3E4A45',
        pn: c.pn || c.name, pnNote: c.pn ? 'Nomor peserta' : 'Tanpa nomor peserta', pnNoteColor: c.pn ? '#56625D' : '#8A4206',
        facName: c.facName, date: c.date + (c.days > 1 ? ' · rawat inap' : ''), amount: rp(c.amount),
        status: st[0], bg: tone[st[1]].bg, fg: tone[st[1]].fg, sub: st[2],
        actionLabel: rev ? 'Tinjau' : lr ? 'Lihat hasil' : 'Periksa',
        btnBg: lr && !rev ? '#FFFFFF' : accent, btnFg: lr && !rev ? '#1F2A22' : '#FFFFFF', btnBorder: lr && !rev ? '#CBD3CF' : accent,
        action: () => lr ? openResult(c.id) : this.setState({ screen: 'confirm', claimId: c.id })
      };
    });

    const caseSel = s.screen === 'case' ? (s.cases.find((c) => c.id === s.caseId) || s.cases[0]) : null;
    const claim = claims.find((c) => c.id === (caseSel ? caseSel.claimId : s.claimId)) || claims[0] || EMPTY_CLAIM;
    const cf = {
      nameOnly: !claim.pn,
      rows: [
        { k: 'Nomor klaim', v: claim.id },
        { k: 'Jenis klaim', v: claim.rel === 'CORRECTION' ? 'Koreksi dari ' + claim.relId : 'Klaim asli' },
        { k: 'Asal klaim', v: claim.src === 'CSV' ? 'Unggahan CSV · ' + claim.file : 'Diajukan faskes ke Sistem Klaim BPJS' },
        { k: 'Pasien', v: claim.pn ? 'Nomor peserta ' + claim.pn : claim.name + ' (tanpa nomor peserta)' },
        { k: 'Faskes', v: claim.facName },
        { k: 'Tanggal layanan', v: claim.date + ' · ' + stay(claim) },
        { k: 'Nominal klaim', v: rp(claim.amount) }
      ],
      items: claim.items.map((it) => ({ label: it.label, kind: it.kind, qty: qtyOf(it) }))
    };

    const j = s.job || { status: 'QUEUED' };
    const pos = { QUEUED: 0, RUNNING: 1, FAILED: 2 }[j.status] ?? 0;
    const failed = j.status === 'FAILED';
    const job = {
      claimId: s.claimId,
      title: failed ? 'Pemeriksaan belum berhasil' : 'Sedang memeriksa klaim…',
      text: failed ? 'Data kunjungan tidak dapat diambil tepat waktu. Tidak ada hasil yang disimpan. Silakan coba lagi.' : 'Mencari kunjungan pasien dan mencocokkan setiap layanan. Hasil akan terbuka otomatis.',
      failed, running: !failed,
      steps: ['Diterima', 'Diperiksa', failed ? 'Gagal' : 'Selesai'].map((label, i) => ({
        label, bar: failed && i === 2 ? '#D08A3E' : (i <= pos ? accent : '#E3E8E5'), fg: i <= pos ? '#1F2A22' : '#8A958F'
      }))
    };

    const pill = (t, text) => ({ icon: tone[t].icon, text, bg: tone[t].bg, fg: tone[t].fg });
    const flat = (pre, p) => ({ [pre + 'Icon']: p.icon, [pre + 'Text']: p.text, [pre + 'Bg']: p.bg, [pre + 'Fg']: p.fg });
    const buildRows = (sc, c) => c.items.map((it) => {
      const row = sc.rows && sc.rows[it.ref];
      const base = { label: it.label, kind: it.kind, claimed: qtyOf(it) };
      if (!row) {
        return Object.assign(base, { _s: 'na', why: '', hasWhy: false, bar: tone.neutral.bar, tint: '#FFFFFF' },
          flat('fk', pill('neutral', 'Belum dibandingkan')), flat('pt', pill('neutral', 'Belum ada')),
          flat('res', pill('neutral', sc.visits.length ? 'Belum dinilai' : 'Tidak ada data')));
      }
      const good = row.fk && row.pt !== false;
      const t = good ? 'ok' : 'bad';
      return Object.assign(base, { _s: t, why: row.why, hasWhy: !!row.why, bar: tone[t].bar, tint: tone[t].tint },
        flat('fk', pill(row.fk ? 'ok' : 'bad', row.fkText)),
        flat('pt', row.pt === true ? pill('ok', 'Sesuai') : row.pt === false ? pill('bad', 'Tidak sesuai') : pill('neutral', 'Tidak ditanyakan')),
        flat('res', pill(t, good ? 'Sesuai' : 'Tidak sesuai')));
    });
    const cmpOf = (rows) => {
      const n = rows.length || 1;
      const ok = rows.filter((x) => x._s === 'ok').length;
      const bad = rows.filter((x) => x._s === 'bad').length;
      const na = rows.filter((x) => x._s === 'na').length;
      return { ok, bad, na, hasNa: na > 0, okW: (ok / n * 100) + '%', badW: (bad / n * 100) + '%' };
    };
    const rowsNoteOf = (sc) => sc.visits.length ? 'Layanan belum dibandingkan karena kunjungan pasien belum dapat dipastikan.' : 'Tidak ada catatan faskes untuk dibandingkan.';
    const attn = (sc, re) => sc.attention.concat(re ? [{ tone: 'info', title: 'Klaim ini sudah pernah diperiksa', text: 'Hasil pemeriksaan sebelumnya tetap tersimpan di riwayat.' }] : [])
      .map((a) => ({ title: a.title, text: a.text, icon: tone[a.tone].icon, bg: tone[a.tone].bg, fg: tone[a.tone].fg }));
    const factsOf = (c) => [
      { k: 'Nominal klaim', v: rp(c.amount) },
      { k: 'Jenis layanan', v: stay(c) },
      { k: 'Asal klaim', v: srcLabel(c) },
      { k: 'Pasien', v: c.pn ? 'Peserta ' + c.pn : c.name }
    ];

    const list = runs[claim.id] || [];
    const run = (s.runN && list.find((x) => x.n === s.runN)) || list[list.length - 1] || { n: 1, at: '—', stale: false, re: false, via: '' };
    const latestN = list.length ? list[list.length - 1].n : 1;
    const sc = scOf(claim);
    const kc = caseOf(claim.id);
    const vt = tone[sc.verdict[0]];
    const rRows = buildRows(sc, claim);
    const r = {
      claimId: claim.id, meta: where(claim) + (claim.rel === 'CORRECTION' ? ' · Koreksi dari ' + claim.relId : ''),
      backLabel: s.from === 'batch' ? 'Kembali ke ringkasan unggahan' : 'Kembali ke daftar klaim',
      facts: factsOf(claim),
      stale: run.stale,
      vTitle: sc.verdict[1], vSub: sc.verdict[2], vBg: vt.bg, vFg: vt.fg, vBar: vt.bar, vIcon: vt.icon,
      attention: attn(sc, run.re), hasAttention: sc.attention.length > 0 || run.re,
      checks: sc.checks.map((c, i) => ({ n: i + 1, q: c.q, a: c.a, note: c.note, icon: tone[c.tone].icon, bg: tone[c.tone].bg, fg: tone[c.tone].fg, bar: tone[c.tone].bar, tint: tone[c.tone].tint })),
      rows: rRows, cmp: cmpOf(rRows),
      rowsNote: !sc.rows, rowsNoteText: rowsNoteOf(sc),
      visitTitle: sc.vt[0], visitSub: sc.vt[1],
      visits: sc.visits.map((v) => ({
        kicker: v.kicker, fac: v.fac, when: v.when, status: v.status, bg: tone[v.tone].bg, fg: tone[v.tone].fg, bar: tone[v.tone].bar,
        rows: v.rows.map((pt) => ({ label: pt.label, text: pt.text, icon: tone[pt.tone].icon, bg: tone[pt.tone].bg, fg: tone[pt.tone].fg })),
        note: v.note || '', hasNote: !!v.note, noteBg: tone[v.noteTone || 'neutral'].bg, noteFg: tone[v.noteTone || 'neutral'].fg
      })),
      history: list.slice().reverse().map((h) => {
        const lab = h.stale ? ['Data sudah berubah', 'warn'] : (h.n === latestN ? ['Terbaru', 'ok'] : ['Sebelumnya', 'neutral']);
        return {
          n: h.n, at: h.at, via: h.via || '', label: lab[0], bg: tone[lab[1]].bg, fg: tone[lab[1]].fg,
          current: h.n === run.n, openLabel: h.n === run.n ? 'Sedang dilihat' : 'Lihat',
          open: () => this.setState({ runN: h.n })
        };
      }),
      canReview: !!kc && kc.state !== 'COMPLETED',
      openCase: () => kc && openCase(kc, s.from)
    };

    const startJob = (kind) => { this.setState({ claimId: claim.id }, () => this.runJob(kind)); };

    // Unggah CSV
    const up = s.up || { phase: 'pick' };
    const PH = ['pick', 'preview', 'run', 'done'];
    const phi = PH.indexOf(up.phase);
    const parsed = up.parsed;
    const csvCols = [
      ['nomor_klaim', 'Ya', 'Nomor SEP atau nomor klaim. Baris dengan nomor yang sama digabung jadi satu klaim.'],
      ['revisi_klaim', 'Tidak', 'Diisi bila klaim pernah dikoreksi. Kosong berarti revisi pertama.'],
      ['nomor_peserta', 'Ya*', 'Nomor peserta JKN. *Boleh kosong bila nama_pasien diisi, tetapi hasilnya kurang pasti.'],
      ['nama_pasien', 'Tidak', 'Hanya dipakai bila nomor peserta tidak ada.'],
      ['kode_faskes', 'Ya', 'Kode faskes yang mengajukan klaim, misalnya HOSP-DEMO-001.'],
      ['tanggal_mulai', 'Ya', 'Tanggal mulai layanan, format TTTT-BB-HH.'],
      ['tanggal_selesai', 'Ya', 'Sama dengan tanggal mulai untuk rawat jalan. Untuk rawat inap, tanggal pulang.'],
      ['jenis_layanan', 'Ya', 'Diagnosis, Tindakan, atau Obat.'],
      ['sistem_kode', 'Ya', 'ICD-10 untuk diagnosis, ICD-9-CM untuk tindakan, atau daftar kode obat.'],
      ['kode', 'Ya', 'Kode layanan sesuai sistem kodenya.'],
      ['jumlah', 'Tidak', 'Harus lebih dari 0. Kosong berarti 1.'],
      ['satuan', 'Tidak', 'Untuk obat, misalnya tablet atau botol.'],
      ['nominal_klaim', 'Tidak', 'Total nominal klaim dalam rupiah, tanpa titik. Cukup diisi di salah satu baris klaim.']
    ].map(([name, req, desc]) => ({ name, req, desc, reqFg: req === 'Tidak' ? '#56625D' : '#1F2A22' }));
    const csvSample = 'nomor_klaim,nomor_peserta,kode_faskes,tanggal_mulai,tanggal_selesai,jenis_layanan,sistem_kode,kode,jumlah,nominal_klaim\n410640524V001386,401155005,HOSP-DEMO-002,2024-05-31,2024-06-03,Diagnosis,ICD-10,E86,1,2174700\n410640524V001386,401155005,HOSP-DEMO-002,2024-05-31,2024-06-03,Tindakan,ICD-9-CM,9059,1,';
    const itemsText = (c) => c.items.map((it) => it.kind + ': ' + it.display).join(' · ');
    const T = (n, label, sub, t) => ({ n, label, sub, fg: t === 'neutral' ? '#1F2A22' : tone[t].fg, bar: tone[t].bar });
    const pvClaims = parsed ? parsed.claims : [];
    const pvAmount = pvClaims.reduce((n, c) => n + c.amount, 0);
    const facCount = (code) => pvClaims.filter((c) => c.facility_code === code).length;
    const skippedCount = parsed ? parsed.skipped.length : 0;
    const pv = {
      file: parsed ? parsed.fileName : '', fileLine: parsed ? num(parsed.rowCount) + ' baris dibaca · ' + num(pvClaims.length + skippedCount) + ' klaim · diunggah ' + fmtStamp(up.uploadedAt) : '',
      tiles: [
        T(num(pvClaims.length), 'Klaim siap diperiksa', skippedCount ? 'Dari ' + num(pvClaims.length + skippedCount) + ' klaim di file' : 'Tidak ada baris bermasalah', 'ok'),
        skippedCount ? T(num(skippedCount), 'Klaim tidak bisa diperiksa', (parsed.issues.length) + ' baris bermasalah', 'warn') : T(rp(pvAmount), 'Total nominal', 'Dari kolom nominal_klaim', 'neutral'),
        skippedCount ? T(rp(pvAmount), 'Total nominal', 'Klaim yang siap diperiksa', 'neutral') : T(num(facCount('HOSP-DEMO-001')) + ' · ' + num(facCount('HOSP-DEMO-002')), 'RS Demo Satu · RS Demo Dua', 'Jumlah klaim per faskes', 'neutral'),
        T(num(parsed ? parsed.rowCount : 0), 'Baris layanan', 'Satu baris untuk satu layanan', 'neutral')
      ],
      hasIssues: !!(parsed && parsed.issues.length), issueTitle: skippedCount + ' klaim tidak bisa diperiksa karena ada baris yang bermasalah',
      issues: parsed ? parsed.issues.slice(0, 10) : [],
      previewNote: 'Menampilkan ' + Math.min(pvClaims.length, 5) + ' dari ' + num(pvClaims.length) + ' klaim',
      rows: pvClaims.slice(0, 5).map((c) => ({ id: c.id, pn: c.participant_number || c.patient_name, fac: FACILITY_NAMES[c.facility_code], date: fmtDate(c.service_start), items: itemsText(c), amount: rp(c.amount), status: 'Siap diperiksa', bg: tone.ok.bg, fg: tone.ok.fg })),
      cta: skippedCount ? 'Periksa ' + num(pvClaims.length) + ' klaim, lewati ' + skippedCount : 'Periksa ' + num(pvClaims.length) + ' klaim'
    };
    const total = pvClaims.length || 1;
    const done = up.done || 0;
    const elapsed = up.startedAt ? (Date.now() - new Date(up.startedAt).getTime()) / 1000 : 0;
    const remainSec = done ? Math.round((total - done) * elapsed / done) : total * 0.152;
    const run2 = {
      file: pv.file, done: num(done), total: num(total), pct: Math.round(done / total * 100), w: (done / total * 100) + '%',
      eta: remainSec > 60 ? 'sekitar ' + Math.ceil(remainSec / 60) + ' menit lagi' : 'kurang dari 1 menit lagi',
      tiles: [
        { n: num(up.clear || 0), label: 'Sesuai', bg: tone.ok.tint, fg: tone.ok.fg },
        { n: num(up.flagged || 0), label: 'Perlu ditinjau', bg: tone.warn.tint, fg: tone.warn.fg },
        { n: num(up.failed || 0), label: 'Gagal diperiksa', bg: '#F7F9F7', fg: '#1F2A22' }
      ]
    };
    const codeCount = (...codes) => flaggedBatch.filter((c) => (s.assess[c.id]?.finding_codes || []).some((x) => codes.includes(x))).length;
    const FOUND = [
      ['Kunjungan tidak ditemukan', codeCount('NO_ENCOUNTER'), 'Tidak ada catatan kunjungan peserta di faskes dan tanggal yang diklaim.', '#C8473A'],
      ['Kunjungan juga dipakai klaim lain', codeCount('ENCOUNTER_REUSED', 'EVIDENCE_REUSED'), 'Tanda muncul di semua klaim yang berbagi kunjungan, jadi sebagian di antaranya kemungkinan klaim yang sah.', '#D08A3E'],
      ['Layanan yang diklaim tidak tercatat', codeCount('MISSING_OR_PRESCRIBED_ONLY'), 'Ada diagnosis atau tindakan pada klaim yang tidak ada di catatan faskes.', '#C8473A'],
      ['Kehadiran pasien belum terverifikasi', codeCount('CHECKOUT_EXCEPTION'), 'Kunjungan tercatat tanpa QR pasien. Layanannya sendiri cocok.', '#D08A3E']
    ].filter((row) => row[1] > 0);
    const flaggedSample = [...flaggedBatch].sort((a, b) => b.amount - a.amount).slice(0, 5);
    const bd = {
      file: BATCH.file, when: 'Selesai ' + BATCH.when,
      tiles: [T(num(BATCH.total), 'Klaim diperiksa', num(BATCH.rows) + ' baris dari file', 'neutral'), T(num(BATCH.clear), 'Sesuai', 'Tidak ada yang perlu ditinjau', 'ok'), T(num(BATCH.flagged), 'Perlu ditinjau', 'Sudah masuk daftar Perlu ditinjau', 'warn'), T('0', 'Gagal diperiksa', 'Tidak ada yang perlu diulang', 'neutral')],
      total: rp(BATCH.amount), review: rp(BATCH.review), clear: rp(BATCH.amount - BATCH.review),
      reviewPct: (BATCH.review / (BATCH.amount || 1) * 100).toFixed(1).replace('.', ',') + '%', reviewW: (BATCH.review / (BATCH.amount || 1) * 100) + '%',
      found: FOUND.map(([label, n, note, color]) => ({ label, n, note, color, w: (n / (BATCH.flagged || 1) * 100) + '%' })),
      rows: flaggedSample.map((c) => ({ id: c.id, fac: c.facName, date: c.date, amount: rp(c.amount), short: scOf(c).short, open: () => openResult(c.id, 'batch') })),
      more: 'Menampilkan ' + flaggedSample.length + ' dari ' + num(BATCH.flagged) + ' klaim yang perlu ditinjau. Daftar lengkap ada di halaman Perlu ditinjau dan di file hasil.'
    };
    const upTitle = { pick: ['Unggah klaim dari CSV', 'Periksa banyak klaim sekaligus. Satu baris untuk satu layanan yang diklaim.'], preview: ['Periksa isi file', 'Pastikan klaim terbaca dengan benar sebelum pemeriksaan dimulai.'], run: ['Pemeriksaan berjalan', 'Klaim diperiksa satu per satu dengan aturan yang sama seperti pemeriksaan biasa.'], done: ['Ringkasan unggahan', 'Hasil pemeriksaan semua klaim dari file ini.'] }[up.phase];
    const upV = {
      title: upTitle[0], sub: upTitle[1],
      isPick: up.phase === 'pick', isPreview: up.phase === 'preview', isRun: up.phase === 'run', isDone: up.phase === 'done',
      steps: ['Pilih file', 'Periksa isi', 'Pemeriksaan', 'Ringkasan'].map((label, i) => ({
        n: i + 1, label, bar: i <= phi ? accent : '#E3E8E5', fg: i <= phi ? '#1F2A22' : '#8A958F', weight: i === phi ? '700' : '500'
      }))
    };

    const isSup = s.role === 'supervisor';
    const me = s.username;
    const ownerName = (u) => !u ? 'Belum ada' : (u === me ? u + ' (Anda)' : u);
    const FILTERS = [['ALL', 'Semua'], ['MINE', isSup ? 'Diteruskan ke saya' : 'Tugas saya'], ['OPEN', 'Belum ditinjau'], ['IN_REVIEW', 'Sedang ditinjau'], ['NEEDS_MORE_EVIDENCE', 'Menunggu klarifikasi'], ['COMPLETED', 'Selesai']];
    const match = (c, id) => id === 'ALL' || (id === 'MINE' ? c.owner === me && c.state !== 'COMPLETED' : c.state === id);
    const caseFilters = FILTERS.map(([id, label]) => {
      const on = s.caseFilter === id;
      return {
        label, count: s.cases.filter((c) => match(c, id)).length,
        pressed: String(on), border: on ? accent : '#CBD3CF', bg: on ? '#E2EBE4' : '#FFFFFF',
        pick: () => this.setState({ caseFilter: id })
      };
    });
    const lastOf = (c, kind) => c.history.filter((h) => h.kind === kind).slice(-1)[0];
    const openCase = (c, from) => { this.enterCase(c, from); };
    const caseRows = s.cases.filter((c) => match(c, s.caseFilter) && claims.some((x) => x.id === c.claimId)).map((c) => {
      const cl = claims.find((x) => x.id === c.claimId);
      const st = CASE[c.state];
      const esc = lastOf(c, 'decision');
      return {
        claimId: c.claimId, where: where(cl), summary: scOf(cl).short,
        amount: rp(cl.amount),
        state: st[0], sBg: tone[st[1]].bg, sFg: tone[st[1]].fg, stale: c.stale, opened: c.opened,
        owner: ownerName(c.owner), ownerWeight: c.owner === me ? '700' : '500', ownerColor: c.owner ? '#1F2A22' : '#8A4206',
        escalated: !!(esc && esc.code === 'ESCALATE' && c.state !== 'COMPLETED'),
        rowBg: c.owner === me && c.state !== 'COMPLETED' ? '#F8FBF8' : '#FFFFFF',
        open: () => openCase(c)
      };
    });

    const kcase = s.cases.find((c) => c.id === s.caseId) || s.cases[0] || EMPTY_CASE;
    const kcl = claims.find((x) => x.id === kcase.claimId) || EMPTY_CLAIM;
    const ksc = scOf(kcl);
    const kst = CASE[kcase.state];
    const rec = lastOf(kcase, 'decision');
    const escEv = rec && rec.code === 'ESCALATE' && kcase.state !== 'COMPLETED' ? rec : null;
    const kRuns = runs[kcl.id] || [];
    const kRowsB = buildRows(ksc, kcl);
    const DTONE = { NO_ACTION: 'ok', REQUEST_CLARIFICATION: 'warn', ESCALATE: 'warn', CLOSE_REVIEW: 'ok' };
    const EV = { open: ['neutral', '•'], assign: ['info', '→'], access: ['neutral', '◉'] };
    const aiMeta = kcase.ai;
    const useLlm = aiMeta.method === 'LLM';
    const wrap = (arr) => arr.map((text) => ({ text }));
    const issues = ksc.attention.filter((a) => a.tone !== 'info');
    const tplOk = [], tplBad = [];
    const ck = ksc.checks;
    (ck[0].tone === 'ok' ? tplOk : tplBad).push('Kehadiran pasien: ' + ck[0].note);
    kRowsB.forEach((r) => {
      if (r._s === 'ok') tplOk.push(r.kind + ' ' + r.label + ' sesuai catatan faskes.');
      else if (r._s === 'bad') tplBad.push(r.kind + ' ' + r.label + ': ' + (r.why || 'tidak sesuai catatan faskes') + '.');
      else tplBad.push(r.kind + ' ' + r.label + ' belum dapat dibandingkan dengan catatan faskes.');
    });
    if (ck[2].tone === 'bad') tplBad.push('Dipakai klaim lain: ' + ck[2].note);
    if (ck[3].tone === 'bad') tplBad.push('Tanggapan pasien: ' + ck[3].note);
    const aiText = aiMeta.text || {
      ok: tplOk, bad: tplBad,
      q: issues.map((a) => 'Periksa: ' + a.title + '.'),
      l: ['Ini sinyal pemeriksaan, bukan keputusan kecurangan atau pembayaran.']
    };
    const ai = {
      title: useLlm ? 'Ringkasan AI' : 'Ringkasan otomatis',
      pending: !aiMeta.ready,
      sub: !aiMeta.ready ? 'Ringkasan sedang disusun. Sementara ini ditampilkan dari hasil pemeriksaan.' : useLlm ? 'Ditulis model AI dari hasil pemeriksaan di atas. Periksa kembali faktanya di perbandingan layanan sebelum memberi tindak lanjut.' : 'Disusun dari templat baku berdasarkan hasil pemeriksaan di atas.',
      chip: !aiMeta.ready ? 'Sedang disusun' : useLlm ? 'Ditulis AI' : 'Templat baku',
      chipBg: useLlm ? tone.info.bg : tone.neutral.bg, chipFg: useLlm ? tone.info.fg : tone.neutral.fg,
      iconBg: useLlm ? tone.info.bg : tone.neutral.bg, iconFg: useLlm ? tone.info.fg : tone.neutral.fg,
      border: useLlm ? '#C9DAF0' : '#DDE3DE', headBg: useLlm ? '#F4F8FD' : '#F7F9F7',
      isFallback: aiMeta.ready && !useLlm,
      ok: wrap(aiText.ok), bad: wrap(aiText.bad), okEmpty: !aiText.ok.length, badEmpty: !aiText.bad.length,
      questions: wrap(aiText.q), limits: wrap(aiText.l),
      foot: 'Disusun ' + aiMeta.at + ' · nama dan nomor peserta pasien tidak dikirim ke AI · bukan keputusan kecurangan atau pembayaran'
    };
    const k = {
      claimId: kcl.id, where: where(kcl), state: kst[0], sBg: tone[kst[1]].bg, sFg: tone[kst[1]].fg, stale: kcase.stale || run.stale,
      backLabel: s.from === 'batch' ? 'Kembali ke ringkasan unggahan' : s.from === 'claims' ? 'Kembali ke daftar klaim' : 'Kembali ke daftar tinjauan',
      attention: attn(ksc, kRuns.length && kRuns[kRuns.length - 1].re),
      ai, facts: factsOf(kcl),
      rows: kRowsB, cmp: cmpOf(kRowsB), rowsNote: !ksc.rows, rowsNoteText: rowsNoteOf(ksc),
      hasDecision: !!rec && !escEv, dLabel: rec ? rec.title : '', dReason: rec ? rec.text : '', dAt: rec ? rec.at + ' · ' + rec.who : '',
      formTitle: rec ? 'Catat tindak lanjut baru' : 'Tindak lanjut',
      hasEsc: !!escEv, escWho: escEv ? escEv.who : '', escAt: escEv ? escEv.at : '', escReason: escEv ? escEv.text : '',
      owner: ownerName(kcase.owner), ownerColor: kcase.owner ? '#1F2A22' : '#8A4206',
      canTake: kcase.owner !== me && kcase.state !== 'COMPLETED',
      timeline: kcase.history.slice().reverse().map((h) => {
        const t = h.kind === 'decision' ? [DTONE[h.code] || 'info', tone[DTONE[h.code] || 'info'].icon] : EV[h.kind];
        return { at: h.at, who: h.who === me ? h.who + ' (Anda)' : h.who, title: h.title, text: h.text, hasText: !!h.text, icon: t[1], bg: tone[t[0]].bg, fg: tone[t[0]].fg };
      })
    };
    const decisions = DEC.filter((d) => !(isSup && d[0] === 'ESCALATE')).map(([code, label, desc]) => ({
      label, desc, checked: s.decision === code,
      border: s.decision === code ? accent : '#DDE3DE', bg: s.decision === code ? '#F1F5F2' : '#FFFFFF',
      pick: () => this.setState({ decision: code })
    }));
    const rlen = s.reason.trim().length;

    const nav = (on, cur) => ({ bg: on ? '#E2EBE4' : 'transparent', fg: on ? '#1F2A22' : '#3E4A45', current: cur ? 'page' : undefined });
    const onUpload = s.screen === 'upload' || (s.screen === 'result' && s.from === 'batch');
    const onClaims = !onUpload && ['claims', 'confirm', 'job', 'result'].includes(s.screen);

    return {
      accent,
      isLogin: s.screen === 'login', notLogin: s.screen !== 'login',
      isClaims: s.screen === 'claims', isConfirm: s.screen === 'confirm', isJob: s.screen === 'job', isResult: s.screen === 'result',
      isCases: s.screen === 'cases', isCase: s.screen === 'case', isUpload: s.screen === 'upload',
      navA: nav(onClaims, s.screen === 'claims'), navU: nav(onUpload, s.screen === 'upload'), navB: nav(!onClaims && !onUpload, s.screen === 'cases'),
      me, roleLabel: isSup ? 'Supervisor' : 'Verifikator',
      navBLabel: isSup ? 'Diteruskan ke saya' : 'Perlu ditinjau',
      casesTitle: isSup ? 'Kasus yang diteruskan' : 'Perlu ditinjau',
      casesSub: isSup ? 'Kasus yang diteruskan verifikator untuk keputusan Anda, beserta seluruh kasus tim.' : 'Klaim yang hasil pemeriksaannya memuat hal yang perlu dilihat manusia.',
      loginSup: () => this.signIn('supervisor01'),
      assignTo: s.assignTo, setAssignTo: (e) => this.setState({ assignTo: e.target.value }),
      cannotAssign: !s.assignTo || s.assignTo === kcase.owner,
      assign: async () => {
        if (!s.assignTo || s.assignTo === kcase.owner) return;
        await assignCase(kcase.id, s.assignTo);
        this.setState({ assignTo: '' });
        await this.loadCase(kcase.id);
      },
      take: async () => {
        await assignCase(kcase.id, me);
        await this.loadCase(kcase.id);
      },
      openCases: s.cases.filter((c) => c.state !== 'COMPLETED' && (!isSup || c.owner === me)).length,
      login: () => this.signIn('verifier01'),
      logout: () => { logout(); this.setState({ screen: 'login', claims: [], assess: {}, details: {}, cases: [] }); },
      goClaims: () => this.setState({ screen: 'claims', job: null }),
      goCases: () => this.setState({ screen: 'cases', caseFilter: isSup ? 'MINE' : s.caseFilter }),
      goUpload: () => this.setState({ screen: 'upload', up: { phase: 'pick' } }),
      goBackFromCase: () => s.from === 'batch' ? this.setState({ screen: 'upload', up: Object.assign({}, up, { phase: 'done' }) }) : s.from === 'claims' ? this.setState({ screen: 'claims' }) : this.setState({ screen: 'cases', caseFilter: isSup ? 'MINE' : s.caseFilter }),
      goBackFromResult: () => s.from === 'batch' ? this.setState({ screen: 'upload', up: Object.assign({}, up, { phase: 'done' }) }) : this.setState({ screen: 'claims' }),

      q: s.q, setQ: (e) => this.setState({ q: e.target.value }),
      srcFilters, claimRows, noClaims: claimRows.length === 0,
      claimsFoot: 'Menampilkan ' + claimRows.length + ' dari ' + num(matchedClaims.length) + ' klaim',
      batch: { file: BATCH.file, line: num(BATCH.total) + ' klaim diperiksa · ' + num(BATCH.flagged) + ' perlu ditinjau · ' + rp(BATCH.review) + ' dari ' + rp(BATCH.amount) + ' perlu ditinjau' },
      openBatch: () => this.setState({ screen: 'upload', up: Object.assign({}, up, { phase: 'done' }) }),

      up: upV, csvCols, csvSample, pv, run: run2, bd,
      downloadTemplate: () => saveCsv('template_klaim.csv', [csvCols.map((c) => c.name)]),
      downloadIssues: () => saveCsv('daftar_masalah.csv', [['baris', 'nomor_klaim', 'masalah', 'keterangan'], ...(parsed ? parsed.issues : []).map((i) => [i.line, i.claim, i.what, i.text])]),
      downloadResult: () => saveCsv('hasil_' + BATCH.file, [['nomor_klaim', 'faskes', 'tanggal', 'nominal', 'hasil', 'keterangan'], ...batchClaims.map((c) => [c.id, c.facName, c.date, c.amount, s.assess[c.id]?.review_required ? 'Perlu ditinjau' : 'Sesuai', scOf(c).short])]),
      pickFile: () => this.pickLocal(),
      pickDemo: () => this.pickPublic('klaim_contoh_1000.csv'),
      pickBad: () => this.pickPublic('klaim_november.csv'),
      startBatch: () => this.runBatch(),
      finishBatch: () => {},

      cf,
      submit: () => startJob('submit'),

      job,
      failJob: () => this.setState({ job: Object.assign({}, j, { status: 'FAILED' }) }),
      retryJob: () => startJob(j.kind || 'submit'),

      r,
      recheck: () => startJob('recheck'),

      caseFilters, caseRows, noCases: caseRows.length === 0,
      k, decisions,
      reason: s.reason,
      setReason: (e) => this.setState({ reason: e.target.value.slice(0, 2000) }),
      reasonHint: rlen < 10 ? 'Tulis minimal 10 karakter.' : 'Alasan akan tersimpan bersama tindak lanjut.',
      reasonColor: rlen < 10 ? '#8A4206' : '#56625D',
      cannotDecide: !s.decision || rlen < 10,
      decide: async () => {
        if (!s.decision || rlen < 10) return;
        await decideCase(kcase.id, s.decision, s.reason.trim());
        if (s.decision === 'ESCALATE') await assignCase(kcase.id, 'supervisor01');
        this.setState({ decision: null, reason: '' });
        await this.afterDecision(kcase, s.decision);
      }
    };
  }

  render() {
    return <View v={this.renderVals()} />;
  }
}
