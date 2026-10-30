// @ts-nocheck -- logic ported verbatim from the design canvas; data comes from src/api.
import {Component} from "react";
import {ApiError, formatDateTime, issueQr, listEncounters, loadVisit, staffScan, submitPatientResponse} from "./api/client";
import {View} from "./design/View";

type AppProps = {auth: {token: () => string | undefined; fresh: () => Promise<string>; login: () => void; logout: () => void}};

const EMPTY_VISIT = {id: '', fac: '', date: '', inT: '', outT: '', ref: '', presence: 'QR', conf: 'INCOMPLETE', month: '', items: [], deadline: ''};

export default class App extends Component<AppProps, any> {
  state = {
    screen: this.props.auth.token() ? 'loading' : 'login', visits: [], active: false, purpose: 'CHECK_IN', remaining: 60,
    qrValue: '', visitId: '', from: 'home', answers: {}, sheet: false
  };

  componentDidMount() {
    this.tick = setInterval(() => {
      const s = this.state;
      if (s.screen === 'qr' && s.remaining > 0) this.setState({ remaining: s.remaining - 1 });
    }, 1000);
    this.poll = setInterval(() => { if (this.state.screen !== 'login') this.refresh(); }, 3000);
    if (this.state.screen !== 'login') this.refresh();
  }

  componentWillUnmount() {
    clearInterval(this.tick);
    clearInterval(this.poll);
  }

  guard(error) {
    if (error instanceof ApiError && error.status === 401) this.setState({ screen: 'expired' });
    else throw error;
  }

  async refresh() {
    try {
      const token = await this.props.auth.fresh();
      const { items } = await listEncounters(token);
      const previous = this.state.visits;
      const visits = [];
      for (const encounter of items) {
        const known = previous.find((v) => v.id === encounter.encounter_id);
        visits.push(await loadVisit(token, encounter, known));
      }
      this.setState((s) => {
        const open = visits.find((v) => v.isOpen);
        const next = { visits, active: !!open };
        if (s.screen === 'loading') next.screen = 'home';
        if (s.screen === 'qr' && s.purpose === 'CHECK_IN' && open && !previous.some((v) => v.id === open.id)) next.screen = 'in';
        if (s.screen === 'qr' && s.purpose === 'CHECK_OUT' && !open) Object.assign(next, { screen: 'out', visitId: visits[0]?.id || '' });
        return next;
      });
    } catch (error) {
      this.guard(error);
    }
  }

  async showQr(purpose) {
    try {
      const token = await this.props.auth.fresh();
      const open = this.state.visits.find((v) => v.isOpen);
      const qr = await issueQr(token, purpose, purpose === 'CHECK_OUT' ? open?.id : undefined);
      this.setState({ screen: 'qr', purpose, remaining: qr.ttl_seconds, qrValue: qr.token });
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) this.setState({ screen: 'expired' });
      else this.setState({ screen: 'qrfail', purpose });
    }
  }

  async simulateStaffScan() {
    try {
      await staffScan(this.state.purpose, this.state.qrValue);
      await this.refresh();
    } catch {
      this.setState({ screen: 'qrfail' });
    }
  }

  async sendResponse(overall, answers, sel) {
    const token = await this.props.auth.fresh();
    const items = sel.items.map((it) => {
      const a = answers[it.id];
      return a.r === 'ok'
        ? { evidence_id: it.id, response: 'CONFIRMED' }
        : { evidence_id: it.id, response: 'DISPUTED', reason: a.reason, note: a.note || undefined };
    });
    const saved = await submitPatientResponse(token, sel.snapshotId, overall, items);
    this.setState({
      screen: 'sent', sheet: false,
      visits: this.state.visits.map((v) => v.id === sel.id ? { ...v, conf: overall, sent: formatDateTime(saved.submitted_at) } : v)
    });
  }

  renderVals() {
    const s = this.state;
    const accent = this.props.accent ?? '#3F5E48';
        const isOutPurpose = s.purpose === 'CHECK_OUT';
    const remaining = s.remaining ?? 60;
    const expired = s.screen === 'qr' && remaining <= 0;
    const answers = s.answers || {};

    const tone = {
      ok: { bg: '#E2EBE4', fg: '#2F4A37' },
      warn: { bg: '#FBEBD7', fg: '#8A4206' },
      info: { bg: '#E1ECF8', fg: '#1E4E8C' },
      neutral: { bg: '#E8ECEA', fg: '#3E4A45' }
    };
    const CONF = {
      READY: ['Menunggu konfirmasi', 'info'],
      INCOMPLETE: ['Ringkasan disiapkan', 'neutral'],
      CONFIRMED: ['Terkonfirmasi', 'ok'],
      PARTIALLY_DISPUTED: ['Sebagian disanggah', 'warn'],
      DISPUTED: ['Disanggah', 'warn'],
      RECONF: ['Perlu konfirmasi ulang', 'info'],
      NO_RESPONSE: ['Tidak ada respons', 'neutral']
    };
    const OVERALL = {
      CONFIRMED: 'Semua sesuai',
      PARTIALLY_DISPUTED: 'Sebagian tidak sesuai',
      DISPUTED: 'Semua tidak sesuai'
    };
    const CONF_TEXT = (v) => ({
      READY: 'Ringkasan layanan sudah siap. Periksa dan beri tanggapan sebelum ' + v.deadline + ' WIB.',
      INCOMPLETE: 'Faskes masih menyelesaikan pengiriman data layanan. Ringkasan akan muncul di sini setelah datanya lengkap.',
      CONFIRMED: 'Respons Anda sudah tersimpan dan tidak dapat diubah.',
      PARTIALLY_DISPUTED: 'Respons Anda sudah tersimpan dan tidak dapat diubah.',
      DISPUTED: 'Respons Anda sudah tersimpan dan tidak dapat diubah.',
      RECONF: 'Faskes memperbarui data layanan setelah Anda memberi respons. Respons sebelumnya tetap tersimpan. Mohon periksa ringkasan terbaru.',
      NO_RESPONSE: 'Batas waktu konfirmasi 72 jam telah lewat. Kunjungan Anda tetap tercatat.'
    }[v.conf]);

    const base = s.visits;
    const PRES = { QR: ['QR terverifikasi', 'ok'], EXC: ['Pengecualian tercatat', 'warn'], UNV: ['Belum terverifikasi', 'warn'] };
    const P_NOTE = {
      EXC: ['Kehadiran dicatat petugas melalui jalur pengecualian, bukan pemindaian QR.', '#3E4A45', '#F3F5F1'],
      UNV: ['Faskes mencatat kunjungan ini tanpa pindai QR Anda dan tanpa pengecualian dari petugas. Karena itu kehadiran Anda belum terverifikasi. Layanan Anda tetap tercatat.', '#5C2D05', '#FBEBD7']
    };
    const visits = base.filter((v) => !v.isOpen);
    const fullHistory = visits.map((v, i) => {
      const c = CONF[v.conf];
      const p = PRES[v.presence];
      return {
        fac: v.fac,
        meta: (v.care || 'Rawat jalan') + ' · ' + v.date + (v.care ? '' : ' · ' + v.inT + '–' + v.outT),
        aLabel: p[0], aBg: tone[p[1]].bg, aFg: tone[p[1]].fg,
        bLabel: c[0], bBg: tone[c[1]].bg, bFg: tone[c[1]].fg,
        month: v.month,
        showMonth: i === 0 || visits[i - 1].month !== v.month,
        open: () => this.setState({ screen: 'detail', visitId: v.id, from: s.screen })
      };
    });

    const sel = base.find((v) => v.id === s.visitId) || base[0] || EMPTY_VISIT;
    const sc = CONF[sel.conf];
    const pres = PRES[sel.presence];
    const pNote = P_NOTE[sel.presence];
    const d = {
      fac: sel.fac, date: sel.date, inT: sel.inT, outT: sel.outT, ref: sel.ref, rev: sel.rev || 1,
      pLabel: pres[0], pBg: tone[pres[1]].bg, pFg: tone[pres[1]].fg,
      isExc: sel.presence === 'EXC', care: sel.care || 'Rawat jalan',
      hasPNote: !!pNote, pNote: pNote ? pNote[0] : '', pNoteFg: pNote ? pNote[1] : '#3E4A45', pNoteBg: pNote ? pNote[2] : '#F3F5F1',
      cLabel: sc[0], cBg: tone[sc[1]].bg, cFg: tone[sc[1]].fg,
      cText: CONF_TEXT(sel),
      hasResponse: !!OVERALL[sel.conf] || (sel.conf === 'RECONF' && !!sel.prev),
      respTitle: sel.conf === 'RECONF' ? 'Respons sebelumnya' : 'Respons Anda',
      respLabel: OVERALL[sel.conf] || OVERALL[sel.prev] || '',
      sent: sel.sent || '',
      canReview: sel.conf === 'READY' || sel.conf === 'RECONF',
      ctaLabel: sel.conf === 'RECONF' ? 'Periksa ringkasan terbaru' : 'Periksa ringkasan layanan',
      isPending: sel.conf === 'INCOMPLETE',
      isReconf: sel.conf === 'RECONF'
    };

    const HEAD = {
      DIAGNOSIS: ['Diagnosis', 'Yang dicatat oleh dokter'],
      PROCEDURE: ['Tindakan', 'Pemeriksaan dan tindakan yang tercatat'],
      MEDICATION_DISPENSE: ['Obat yang diserahkan', 'Obat yang tercatat sudah diserahkan kepada Anda']
    };
    const REASONS = {
      DIAGNOSIS: [],
      PROCEDURE: [['SERVICE_NOT_RECEIVED', 'Tindakan ini tidak saya terima'], ['OTHER', 'Alasan lain']],
      MEDICATION_DISPENSE: [['MEDICATION_NOT_RECEIVED', 'Obat ini tidak saya terima'], ['QUANTITY_DIFFERENT', 'Jumlahnya berbeda'], ['OTHER', 'Alasan lain']]
    };
    const REASON_LABEL = {
      SERVICE_NOT_RECEIVED: 'Tindakan tidak diterima',
      MEDICATION_NOT_RECEIVED: 'Obat tidak diterima',
      QUANTITY_DIFFERENT: 'Jumlah berbeda',
      OTHER: 'Alasan lain'
    };
    const setAns = (id, patch) => {
      const cur = (this.state && this.state.answers) || {};
      this.setState({ answers: Object.assign({}, cur, { [id]: Object.assign({}, cur[id] || {}, patch) }) });
    };

    const list = sel.items || [];
    const items = list.map((it, i) => {
      const a = answers[it.id] || {};
      const isOk = a.r === 'ok';
      const isNo = a.r === 'no';
      const reasonLine = isNo ? [REASON_LABEL[a.reason], a.note].filter(Boolean).join(' — ') : '';
      return {
        name: it.name,
        qty: it.qty,
        showHeader: i === 0 || list[i - 1].kind !== it.kind,
        header: HEAD[it.kind][0],
        sub: HEAD[it.kind][1],
        isNo,
        okPressed: String(isOk),
        noPressed: String(isNo),
        okBorder: isOk ? accent : '#CBD3CF',
        okBg: isOk ? accent : '#FFFFFF',
        okFg: isOk ? '#FFFFFF' : '#1F2A22',
        noBorder: isNo ? '#B45309' : '#CBD3CF',
        noBg: isNo ? '#FBEBD7' : '#FFFFFF',
        noFg: isNo ? '#8A4206' : '#1F2A22',
        cardBorder: isNo ? '#E7B98A' : (isOk ? '#B9CBBE' : '#DDE3DE'),
        hasReasons: REASONS[it.kind].length > 0,
        radioName: 'alasan-' + it.id,
        reasons: REASONS[it.kind].map(([code, label]) => ({
          label,
          checked: a.reason === code,
          pick: () => setAns(it.id, { reason: code })
        })),
        noteLabel: it.kind === 'DIAGNOSIS' ? 'Ceritakan apa yang tidak sesuai (opsional)' : 'Catatan (opsional)',
        note: a.note || '',
        setNote: (e) => setAns(it.id, { note: e.target.value.slice(0, 500) }),
        pickOk: () => setAns(it.id, { r: 'ok', reason: null, note: '' }),
        pickNo: () => { if (!isNo) setAns(it.id, { r: 'no', reason: it.kind === 'DIAGNOSIS' ? 'OTHER' : null }); },
        ansLabel: isNo ? 'Tidak sesuai' : 'Sesuai',
        ansBg: isNo ? tone.warn.bg : tone.ok.bg,
        ansFg: isNo ? tone.warn.fg : tone.ok.fg,
        reasonLine,
        hasReasonLine: !!reasonLine,
        complete: isOk || (isNo && !!a.reason),
        disputed: isNo
      };
    });
    const total = items.length;
    const done = items.filter((x) => x.complete).length;
    const disputed = items.filter((x) => x.disputed).length;
    const overall = disputed === 0 ? 'CONFIRMED' : disputed === total ? 'DISPUTED' : 'PARTIALLY_DISPUTED';
    const missingReason = items.some((x) => x.disputed && !x.complete);
    const fresh = visits[0] || EMPTY_VISIT;

    const v0 = base.find((v) => v.id === s.visitId) || fresh;
    const outConf = CONF[v0.conf];
    return {
      accent,
      isLogin: s.screen === 'login',
      isHome: s.screen === 'home',
      isHistory: s.screen === 'history',
      isQr: s.screen === 'qr',
      isIn: s.screen === 'in',
      isOut: s.screen === 'out',
      isDetail: s.screen === 'detail',
      isSummary: s.screen === 'summary',
      isReview: s.screen === 'review',
      isSent: s.screen === 'sent',
      isProfile: s.screen === 'profile',
      isExpired: s.screen === 'expired',
      isQrFail: s.screen === 'qrfail',
      isLoading: s.screen === 'loading',
      showTabs: s.screen === 'home' || s.screen === 'history' || s.screen === 'profile' || s.screen === 'loading',
      tabProfileColor: s.screen === 'profile' ? accent : '#56625D',
      profileCurrent: s.screen === 'profile' ? 'page' : undefined,
      goProfile: () => this.setState({ screen: 'profile' }),
      tabHomeColor: s.screen === 'home' || s.screen === 'loading' ? accent : '#56625D',
      tabHistoryColor: s.screen === 'history' ? accent : '#56625D',
      homeCurrent: s.screen === 'home' ? 'page' : undefined,
      historyCurrent: s.screen === 'history' ? 'page' : undefined,
      active: !!s.active,
      noActive: !s.active,
      homeHistory: fullHistory.slice(0, 3),
      fullHistory,
      d,
      items,
      sheet: !!s.sheet,

      qrValue: s.qrValue,
      activeFac: (base.find((v) => v.isOpen) || fresh).fac,
      visitRef: (base.find((v) => v.isOpen) || v0).ref,
      activeLine: 'Rawat jalan · Masuk ' + (base.find((v) => v.isOpen) || fresh).inT + ' WIB · QR terverifikasi',
      scanTime: (base.find((v) => v.isOpen) || fresh).date + ', ' + (base.find((v) => v.isOpen) || fresh).inT + ' WIB',
      inText: 'Kunjungan Anda di ' + ((base.find((v) => v.isOpen) || fresh).fac || 'faskes') + ' sudah tercatat.',
      outText: 'Kunjungan Anda di ' + (v0.fac || 'faskes') + ' telah selesai.',
      qrTitle: isOutPurpose ? 'QR Keluar' : 'QR Masuk',
      qrInstruction: isOutPurpose
        ? 'Tunjukkan QR ini kepada petugas saat pelayanan Anda selesai.'
        : 'Tunjukkan QR ini kepada petugas pendaftaran untuk mencatat kedatangan Anda.',
      qrAria: isOutPurpose ? 'Kode QR keluar sekali pakai' : 'Kode QR masuk sekali pakai',
      qrOpacity: expired ? '0.15' : '1',
      expired,
      notExpired: !expired,
      timer: Math.floor(Math.max(remaining, 0) / 60) + ':' + String(Math.max(remaining, 0) % 60).padStart(2, '0'),
      timerLabel: expired ? 'Kode tidak berlaku lagi' : 'Berlaku selama',
      timerColor: remaining <= 15 ? '#B45309' : accent,
      barWidth: (Math.max(remaining, 0) / 60 * 100) + '%',

      outConfLabel: outConf[0],
      outConfBg: tone[outConf[1]].bg,
      outConfFg: tone[outConf[1]].fg,
      outConfText: v0.conf === 'READY' ? 'Ringkasan siap diperiksa' : 'Ringkasan sedang disiapkan',
      outNote: v0.conf === 'READY'
        ? 'Periksa apakah layanan dan obat yang tercatat sesuai dengan yang Anda terima, lalu beri tanggapan sebelum ' + v0.deadline + ' WIB.'
        : 'Faskes masih menyelesaikan pengiriman data layanan. Anda bisa memeriksa ringkasan setelah datanya lengkap. Keluar Anda sudah tercatat.',
      outReady: v0.conf === 'READY',
      outPending: v0.conf === 'INCOMPLETE',

      progressText: done + ' dari ' + total + ' item dijawab',
      progressHint: missingReason ? 'Pilih alasan' : (done === total ? 'Siap ditinjau' : ''),
      progressColor: missingReason ? '#8A4206' : accent,
      progressWidth: (total ? done / total * 100 : 0) + '%',
      notComplete: done !== total,
      reviewOpacity: done === total ? '1' : '0.4',
      overallLabel: OVERALL[overall],
      overallBg: disputed ? tone.warn.bg : tone.ok.bg,
      overallFg: disputed ? tone.warn.fg : tone.ok.fg,
      disputedText: disputed ? disputed + ' tidak sesuai' : 'Tanpa sanggahan',
      sentTitle: 'Respons terkirim',

      showQrIn: () => this.showQr('CHECK_IN'),
      showQrOut: () => this.showQr('CHECK_OUT'),
      regenerate: () => this.showQr(s.purpose),
      copyQr: () => navigator.clipboard?.writeText(s.qrValue),
      simulateScan: () => this.simulateStaffScan(),
      goHome: () => this.setState({ screen: 'home', sheet: false }),
      goHistory: () => this.setState({ screen: 'history' }),
      backFromDetail: () => this.setState({ screen: s.from === 'out' ? 'out' : (s.from || 'history') }),
      openSummary: () => this.setState({ screen: 'summary', answers: {}, sheet: false }),
      openSummaryFromOut: () => this.setState({ screen: 'summary', visitId: v0.id, from: 'out', answers: {}, sheet: false }),
      openV0FromOut: () => this.setState({ screen: 'detail', visitId: v0.id, from: 'out' }),
      openDetailFromSent: () => this.setState({ screen: 'detail', from: 'home' }),
      backToDetail: () => this.setState({ screen: 'detail', sheet: false }),
      backToSummary: () => this.setState({ screen: 'summary' }),
      toReview: () => { if (done === total) this.setState({ screen: 'review' }); },
      send: () => this.sendResponse(overall, answers, sel),
      login: () => this.props.auth.login(),
      logout: () => this.props.auth.logout()
    };
  }

  render() {
    return <View v={this.renderVals()} />;
  }
}
