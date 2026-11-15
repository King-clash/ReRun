// Browser side of gsc_app/calc_check.py and gsc_app/calc_model_check.py.
//
// Open https://gscompanion.com/damage-calc/ in a browser, paste this whole file into the
// developer console (or run it with a browser tool), then:
//
//   await __digest(555, 1500)      -> "15d9746d errors=0 n=1500"   (compare with
//                                      py -c "from gsc_app import calc, calc_check; ..."  digest())
//   await __oracle(555, 1, 7, 7)   -> scenario 7 in full (to debug a mismatch)
//   await __links([ "~...", ... ]) -> what the page shows for share links made by
//                                      py -m gsc_app.calc_model_check make SEED COUNT
//
// It runs the site's own calculator on random teams (the random numbers and the order they
// are used in are mirrored exactly in calc_check.py) and returns short fingerprints, so the
// Python port can be compared with the real thing. Nothing is sent anywhere.
// (The /_astro/ file names change when the site is rebuilt; look them up in the page source.)

window.__oracle = async (SEED, COUNT, START = 0, FULL = -1, MODE = 'dmg') => {
  const mod = await import('/_astro/damage.CsCQUt5_.js');
  const et = mod.n, Ne = mod.r, J = mod.c;
  const units = JSON.parse(document.getElementById('calc-data').textContent);
  const enemies = JSON.parse(document.getElementById('enemy-data').textContent);
  const crests = JSON.parse(document.getElementById('crest-data').textContent);
  const eqs = await (await fetch('/calc-equips.json')).json();
  const eqMap = new Map(eqs.map(t => [t.id, {...t, effects: t.effects.map(e => ({...e, text: t.tx[e.text]}))}]));
  const uMap = new Map(units.map(u => [u.id, u]));
  let s = SEED >>> 0;
  const rnd = () => (s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296;
  const ri = n => Math.floor(rnd() * n), pick = a => a[ri(a.length)];
  const KINDS = ['skill','arts','trueArts','superArts','crossArts','phantomBullet','originBullet','protagonize','superEquip'];
  const ELS = ['Fire','Water','Earth','Light','Dark'], RACES = ['Human','Demon','God','Spirit','Machine','Dragon','Beast','Giant'];
  const usable = units.filter(u => KINDS.some(k => (u.hits || {})[k]?.length));
  const compat = (sl) => eqs.filter(e => sl.types.includes(e.type) && e.star <= sl.star);
  const fx = x => Number(x).toFixed(6);
  const TK = ['atk','atkFlat','dmg','critDmg','res','defDown','ignoreDef','criRate','superCriRate','multAdd','multFactor'];
  const canon = r => [fx(r.result.final), fx(r.expected), r.result.dealt, r.result.shown, fx(r.rates.criRate), fx(r.rates.superCriRate), r.hitType, ...TK.map(k => fx(r.terms[k])), ...Object.entries(r.status).sort(([a],[b]) => a < b ? -1 : a > b ? 1 : 0).map(([k,v]) => k + '=' + v), String(!!r.negated)].join('|');
  const fnv = str => { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h >>> 0; };
  const out = [];
  for (let n = 0; n < START + COUNT; n++) {
    let rec = null;
    try {
      const size = 1 + ri(4);
      const pos = [0,1,2,3];
      for (let i = 3; i > 0; i--) { const j = ri(i + 1); [pos[i], pos[j]] = [pos[j], pos[i]]; }
      pos.length = size;
      const specs = [null, null, null, null];
      for (const i of pos) {
        const u = pick(usable);
        const active = {}; for (const m of u.moves || []) if (rnd() < 0.5) active[m] = true;
        const stacks = {}; for (const e of J(u).list) if (rnd() < 0.6) stacks[e.id] = 1 + ri(e.max);
        const dream = u.dream?.length && rnd() < 0.5 ? pick(u.dream) : null;
        const equips = (u.slots || []).map(sl => {
          if (rnd() < 0.35) return null;
          const c = compat(sl); if (!c.length) return null;
          const e = pick(c); const row = {id: e.id};
          if (rnd() < 0.3) row.on = false;
          if (e.effects.some(f => f.target === 'target') && rnd() < 0.6) row.to = pick(pos);
          return row;
        });
        specs[i] = {id: u.id, active, stacks, dream, equips};
      }
      if (rnd() < 0.6) specs[pick(pos)].leader = true;
      const att = pick(pos), au = uMap.get(specs[att].id);
      const dream = specs[att].dream;
      let hit;
      const roll = rnd();
      const aeq = (specs[att].equips || []).filter(e => e && eqMap.get(e.id)?.hit);
      if (roll < 0.15 && aeq.length) {
        const e = pick(aeq), q = eqMap.get(e.id);
        hit = {kind: 'equip', equipId: q.id, multiplier: q.hit.multiplier, element: (q.hit.element === 'user' ? au.element : q.hit.element) || null, dmgType: q.hit.dmgType};
      } else if (roll < 0.3) {
        hit = {kind: 'normal', equipId: null, multiplier: 100, element: au.element, dmgType: Object.values(au.hits || {})[0]?.[0]?.dmgType || 'PHY'};
      } else {
        const kinds = KINDS.filter(k => au.hits?.[k]?.length);
        const kind = pick(kinds);
        const list = Ne(kind, au.hits[kind], au.dreamHits?.[dream]);
        const h = pick(list);
        hit = {kind, equipId: null, multiplier: h.multiplier, element: h.element || null, dmgType: h.dmgType};
      }
      let enemy;
      if (rnd() < 0.6) {
        const e = pick(enemies);
        const half = rnd() < 0.5;
        const st = half ? [...(e.statusOn || [])] : Object.keys(e.while || {}).filter(() => rnd() < 0.5);
        const res = rnd() < 0.5 ? 0 : ri(60) - 20;
        enemy = {id: e.id, element: e.element, race: e.race, def: e.def || 0, res, broken: rnd() < 0.3, status: st, resBy: e.resBy, negates: e.negates, while: e.while, cri: e.cri};
      } else {
        const el = rnd() < 0.2 ? '' : pick(ELS), rc = rnd() < 0.2 ? '' : pick(RACES);
        enemy = {id: '', element: el, race: rc, def: ri(4000), res: ri(80) - 30, broken: rnd() < 0.3, status: []};
      }
      const atkBase = 1000 + ri(9000);
      const extra = {atk: rnd() < 0.4 ? ri(80) : 0, dmg: rnd() < 0.4 ? ri(100) : 0, critDmg: rnd() < 0.3 ? ri(80) : 0, res: rnd() < 0.3 ? ri(40) : 0, ignoreDef: rnd() < 0.3 ? ri(60) : 0, criRate: rnd() < 0.4 ? ri(120) : 0};
      const crit = pick(['auto','auto','none','crit','super']);
      let crest = null, crestSpec = null;
      if (rnd() < 0.5) {
        const c = pick(crests), li = ri(c.lv.length), lv = c.lv[li];
        crestSpec = {id: c.id, lv: li};
        if (lv.fx.length) crest = {name: c.name, effects: lv.fx.map(e => ({...e, text: lv.text.replace(/\n/g, ' / ')}))};
      }
      const team = specs.map(sp => sp ? {unit: uMap.get(sp.id), active: sp.active, stacks: sp.stacks, leader: !!sp.leader, dream: sp.dream, equips: (sp.equips || []).filter(e => e && eqMap.has(e.id)).map(e => ({equip: eqMap.get(e.id), on: e.on !== false, ...(Number.isInteger(e.to) ? {to: e.to} : {})}))} : null);
      const call = (ov) => et({team, attackerIdx: att, hit, enemy, atkBase, extra, crit, overrides: ov, crest});
      let r = call({});
      const ov = {};
      if (rnd() < 0.4 && r.mods.length) { for (let k = 0; k < 3; k++) { ov[pick(r.mods).key] = rnd() < 0.5; } r = call(ov); }
      if (MODE === 'aps') {   // the arts gauge per second (after the damage step, so the random numbers stay in step)
        const g = mod.o(team).artsGen;
        const parts = [fx(g.teamAps), ...g.perUnit.map(q => q.slot + '=' + fx(q.aps) + ':' + q.hp)];
        if (n >= START) out.push(n + ':' + fnv(parts.join('|')).toString(16) + ':0');
        continue;
      }
      if (n >= START) rec = n === FULL ? {n, spec: {specs, att, hit, enemy, atkBase, extra, crit, crest: crestSpec, ov}, res: {final: r.result.final, expected: r.expected, rates: r.rates, hitType: r.hitType, terms: r.terms, status: r.status, canon: canon(r)}} : n + ':' + fnv(canon(r)).toString(16) + ':' + r.result.final.toFixed(3);
    } catch (err) { if (n >= START) rec = n + ':ERR:' + String(err).slice(0, 80); }
    if (n >= START) out.push(rec);
  }
  return FULL >= 0 ? out.find(o => o && o.n === FULL) : out.join(' ');
};

// One fingerprint for COUNT teams (what calc_check.digest() computes in Python).
window.__digest = async (seed, count, mode = 'dmg') => {
  const toks = (await window.__oracle(seed, count, 0, -1, mode)).split(' ');
  const str = toks.map(t => t.split(':').slice(0, 2).join(':')).join(' ');
  let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
  return h.toString(16) + ' errors=' + toks.filter(t => t.includes(':ERR:')).length + ' n=' + toks.length;
};

// What the page shows for share links: [damage, modifier rows, applied rows, state fingerprint].
// Pass a few links at a time; each is given 300 ms to load.
window.__links = async (links) => {
  const L = await import('/_astro/link-state.BDujXk1B.js');
  const sortKeys = v => Array.isArray(v) ? v.map(sortKeys) : (v && typeof v === 'object') ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sortKeys(v[k])])) : v;
  const fnv = str => { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h.toString(16); };
  const out = [];
  for (const l of links) {
    location.hash = l;
    await new Promise(r => setTimeout(r, 300));
    const st = L.t(location.hash.slice(1));
    out.push([document.getElementById('big').textContent, document.querySelectorAll('#mods .mod[data-key]').length, document.querySelectorAll('#mods .mod.st-applied[data-key]').length, fnv(JSON.stringify(sortKeys(st)))]);
  }
  return JSON.stringify(out);
};
