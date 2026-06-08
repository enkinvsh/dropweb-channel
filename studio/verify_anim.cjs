const path = require('path');
const fs = require('fs');
const { makeAnimX } = require('./studio.js');

const packBases = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'packs', 'dropweb', 'bases.json'), 'utf8'));
const BASES = packBases.bases;
const baseId = packBases.order[0];
const BASE = BASES[baseId];

let invalid = 0;
const fails = [];

function num(v) { return typeof v === 'number' && Number.isFinite(v); }

function checkSArray(label, arr) {
  if (!Array.isArray(arr)) {
    if (!num(arr)) { invalid++; fails.push(`${label}: s not number/array -> ${JSON.stringify(arr)}`); }
    return;
  }
  arr.forEach((v, i) => {
    if (!num(v)) { invalid++; fails.push(`${label}[${i}] not finite number -> ${JSON.stringify(v)}`); }
  });
}

function checkProp(label, prop) {
  if (!prop || typeof prop !== 'object') { invalid++; fails.push(`${label}: missing prop`); return; }
  if (prop.a === 1) {
    if (!Array.isArray(prop.k)) { invalid++; fails.push(`${label}: a:1 but k not array`); return; }
    prop.k.forEach((kf, i) => {
      if (!num(kf.t)) { invalid++; fails.push(`${label}.k[${i}].t not finite -> ${JSON.stringify(kf.t)}`); }
      checkSArray(`${label}.k[${i}].s`, kf.s);
    });
  } else {
    checkSArray(`${label}.k`, prop.k);
  }
}

function checkRig(rigLabel, rig) {
  const ks = rig.ks;
  ['p', 's', 'r', 'o', 'a'].forEach(key => {
    if (ks[key] !== undefined) checkProp(`${rigLabel}.ks.${key}`, ks[key]);
  });
}

function checkAnim(label, anim) {
  const rigs = (anim.layers || []).filter(L => L.ty === 3 && typeof L.ind === 'number' && L.ind >= 9000);
  rigs.forEach(r => checkRig(`${label}/${r.nm || r.ind}`, r));
  return rigs;
}

function parentingOK(anim) {
  const rigs = (anim.layers || []).filter(L => L.ty === 3 && L.ind >= 9000);
  if (!rigs.length) return true; // el_* / static path, no rigs
  const lastInd = Math.max(...rigs.map(r => r.ind));
  const iconLayers = (anim.layers || []).filter(L => L.ty !== 3 && L.ind !== 9999);
  if (!iconLayers.length) return true;
  return iconLayers.every(L => L.parent === lastInd);
}

const cases = [];
// 1. single movement presets at amp=60 (NEW shape, one layer each)
['bounce', 'drop', 'rise', 'hop', 'shake'].forEach(k => {
  cases.push({ name: `single ${k} amp=60`, cfg: { layers: [{ kind: k, amp: 60, ov: 10, dir: 1, phase: 0 }], beats: 2, color: '#00DE52' } });
});
// 2. OLD shape cfg
cases.push({ name: 'OLD {kinds:["bounce"],amp:14,ov:10}', cfg: { kinds: ['bounce'], amp: 14, ov: 10, beats: 1, color: '#00DE52' } });
cases.push({ name: 'OLD 2-kind mix {kinds:["spin","pulse"]}', cfg: { kinds: ['spin', 'pulse'], amp: 20, ov: 12, beats: 2, color: '#38BDF8' } });
// 3. NEW shape with 2-4 layers incl a movement layer
cases.push({ name: 'NEW 2 layers (spin+bounce)', cfg: { layers: [{ kind: 'spin', amp: 30, ov: 10, dir: 1, phase: 0 }, { kind: 'bounce', amp: 14, ov: 8, dir: 1, phase: 0.5 }], beats: 2, color: '#00DE52' } });
cases.push({ name: 'NEW 3 layers (beat+ring+shake)', cfg: { layers: [{ kind: 'beat', amp: 16, ov: 8, dir: 1, phase: 0 }, { kind: 'ring', amp: 24, ov: 10, dir: 1, phase: 0.25 }, { kind: 'shake', amp: 40, ov: 0, dir: 1, phase: 0.6 }], beats: 2, color: '#00DE52' } });
cases.push({ name: 'NEW 4 layers (elastic+ring+bounce+swing)', cfg: { layers: [{ kind: 'elastic', amp: 22, ov: 10, dir: 1, phase: 0 }, { kind: 'ring', amp: 14, ov: 8, dir: 1, phase: 0.3 }, { kind: 'bounce', amp: 30, ov: 6, dir: 1, phase: 0.5 }, { kind: 'swing', amp: 18, ov: 0, dir: 1, phase: 0.75 }], beats: 3, color: '#A78BFA' } });
// 4. dir:-1 + phase:0.5 (rotation negate + vertical reflect + time shift)
cases.push({ name: 'dir:-1 phase:0.5 (spin reversed)', cfg: { layers: [{ kind: 'spin', amp: 0, ov: 0, dir: -1, phase: 0.5 }], beats: 2, color: '#00DE52' } });
cases.push({ name: 'dir:-1 phase:0.5 (bounce reflected)', cfg: { layers: [{ kind: 'bounce', amp: 60, ov: 10, dir: -1, phase: 0.5 }], beats: 2, color: '#00DE52' } });
cases.push({ name: 'dir:-1 phase:0.5 mix (swing+drop)', cfg: { layers: [{ kind: 'swing', amp: 30, ov: 0, dir: -1, phase: 0.5 }, { kind: 'drop', amp: 40, ov: 8, dir: -1, phase: 0.5 }], beats: 2, color: '#00DE52' } });
// 5. el_* layer (applies to icon, not a rig) + mix of el_ + whole-glyph
cases.push({ name: 'el_assemble single', cfg: { layers: [{ kind: 'el_assemble', amp: 18, ov: 10, dir: 1, phase: 0 }], beats: 2, color: '#00DE52' } });
cases.push({ name: 'el_pulse + bounce mix', cfg: { layers: [{ kind: 'el_pulse', amp: 20, ov: 10, dir: 1, phase: 0 }, { kind: 'bounce', amp: 30, ov: 8, dir: 1, phase: 0.4 }], beats: 2, color: '#00DE52' } });
cases.push({ name: 'drawon + spin mix', cfg: { layers: [{ kind: 'drawon', amp: 12, ov: 10, dir: 1, phase: 0 }, { kind: 'spin', amp: 0, ov: 0, dir: 1, phase: 0 }], beats: 2, color: '#38BDF8' } });

let parentFails = 0;
cases.forEach(c => {
  const anim = makeAnimX(BASE, c.cfg);
  checkAnim(c.name, anim);
  if (!parentingOK(anim)) { parentFails++; fails.push(`${c.name}: icon NOT parented to last rig`); }
});

console.log(`Cases run: ${cases.length} (base="${baseId}")`);
console.log(`Invalid transform s-values: ${invalid}`);
console.log(`Parenting failures: ${parentFails}`);
if (fails.length) { console.log('--- failures ---'); fails.slice(0, 40).forEach(f => console.log('  ' + f)); }
const pass = invalid === 0 && parentFails === 0;
console.log(pass ? 'PASS' : 'FAIL');
process.exit(pass ? 0 : 1);
