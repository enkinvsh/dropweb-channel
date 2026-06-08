// ===== dropweb emoji studio v4 — категории + крутые + draw-on =====
const CATS={
 "Пульс/масштаб":["beat","throb","breathe","heartbeat","pulse","zoom","pop","elastic","neon"],
 "Трансформ":["squash","stretchV","stretchH","jelly","rubber","flip","cardflip","cardflipV","spin3d","tumble"],
 "Вращение":["spin","popspin","tick","swing","ring","wobble"],
 "Движение":["bounce","hop","drop","rise","vibrate","shake"],
 "Поэлементно":["el_stagger","el_sequential","el_type","el_pulse","el_lead","el_assemble","el_segment","el_orbit"],
 "FX":["drawon","twinkle","blink","flicker","glitch"],
 "—":["none"]
};
const KINDS=Object.values(CATS).flat();
const BEATS_DEFAULT={spin:2,popspin:2,blink:2,swing:2,spin3d:2,flip:2,cardflip:2,cardflipV:2,tick:2,drop:2,rise:2,pop:2,glitch:2,tumble:2,drawon:2,elastic:1};
const EZ={o:{x:[0.25],y:[0]},i:{x:[0.4],y:[1]}}, ES={o:{x:[0.33],y:[0]},i:{x:[0.67],y:[1]}}, EI={o:{x:[0.6],y:[0]},i:{x:[0.9],y:[1]}};
const EOV={o:{x:[0.2],y:[0]},i:{x:[0.3],y:[1.7]}}; // overshoot (supernormal y)
function kf(t,v,e){v=Array.isArray(v)?v:[v];return {t:Math.round(t),s:v,o:(e||ES).o,i:(e||ES).i};}
function kfh(t,v){v=Array.isArray(v)?v:[v];return {t:Math.round(t),s:v,h:1};}
function A(a){return {a:1,k:a};} function K(v){return {a:0,k:v};}

function buildProps(kind,B,amp,ov){
  const a=amp,u=ov; let s=K([100,100,100]),r=K(0),o=K(100),p=K([256,256,0]);
  const SC=q=>A(q.map(([f,v,e])=>kf(f*B,[v,v,100],e)));
  const XY=q=>A(q.map(([f,x,y,e])=>kf(f*B,[x,y,100],e)));
  const RO=q=>A(q.map(([f,v,e])=>kf(f*B,[v],e)));
  const PO=q=>A(q.map(([f,y,e])=>kf(f*B,[256,Math.max(96,Math.min(416,y)),0],e)));
  switch(kind){
   case"beat": s=SC([[0,100,EZ],[0.17,100+a,EZ],[0.4,100-u*0.4,ES],[0.66,100+u*0.1,ES],[1,100]]);break;
   case"throb": s=SC([[0,100,ES],[0.5,100+a*0.6,ES],[1,100]]);break;
   case"breathe": s=SC([[0,100,ES],[0.5,100+a*0.35,ES],[1,100]]);break;
   case"heartbeat": s=SC([[0,100,EZ],[0.1,100+a*1.6,EZ],[0.22,100,EZ],[0.34,100+a,EZ],[0.5,100-u*0.2,ES],[1,100]]);break;
   case"pulse": s=SC([[0,100,EZ],[0.5,100+a*1.4,EZ],[1,100]]);o=A([kf(0,[100]),kf(0.5*B,[100-u*1.5]),kf(B,[100])]);break;
   case"zoom": s=SC([[0,100,ES],[0.5,100+a*2,ES],[1,100]]);break;
   case"pop": s=SC([[0,60,EZ],[0.22,100+a,EI],[0.4,100-u*0.3,ES],[0.6,100,ES],[1,100]]);o=A([kf(0,[0]),kf(0.1*B,[100]),kf(0.9*B,[100]),kf(B,[0])]);break;
   case"elastic": s=SC([[0,100,EZ],[0.15,100+a*1.8,EZ],[0.32,100-a*0.9,EZ],[0.48,100+a*0.9,EZ],[0.64,100-a*0.4,EZ],[0.8,100+a*0.15,ES],[1,100]]);break;
   case"neon": s=SC([[0,100,EZ],[0.12,100+a*1.6,EI],[0.3,100,ES],[1,100]]);o=A([kf(0,[100]),kf(0.06*B,[35],EZ),kf(0.14*B,[100],EZ),kf(0.5*B,[100]),kf(0.56*B,[55]),kf(0.62*B,[100]),kf(B,[100])]);break;
   case"squash": s=XY([[0,100,100,EZ],[0.18,100+a,100-a,EZ],[0.4,100-a*0.5,100+a*0.5,ES],[0.6,100,100,ES],[1,100,100]]);break;
   case"stretchV": s=XY([[0,100,100,ES],[0.5,100-a*0.5,100+a,ES],[1,100,100]]);break;
   case"stretchH": s=XY([[0,100,100,ES],[0.5,100+a,100-a*0.5,ES],[1,100,100]]);break;
   case"jelly": s=XY([[0,100,100,EZ],[0.15,100+a,100-a,EZ],[0.32,100-a*0.7,100+a*0.7,ES],[0.5,100+a*0.4,100-a*0.4,ES],[0.7,100-a*0.2,100+a*0.2,ES],[1,100,100]]);break;
   case"rubber": s=XY([[0,100,100,EZ],[0.2,100+a*1.4,100-a,EZ],[0.4,100-a*0.8,100+a*1.2,EZ],[0.6,100+a*0.5,100-a*0.4,ES],[0.8,100-a*0.15,100+a*0.15,ES],[1,100,100]]);break;
   case"flip": s=XY([[0,100,100,ES],[0.5,-100,100,ES],[1,100,100]]);break;
   case"cardflip": s=XY([[0,100,100,EI],[0.5,6,100,EZ],[1,100,100]]);break;
   case"cardflipV": s=XY([[0,100,100,EI],[0.5,100,6,EZ],[1,100,100]]);break;
   case"spin3d": s=XY([[0,100,100,ES],[0.25,6,100,ES],[0.5,-100,100,ES],[0.75,6,100,ES],[1,100,100]]);break;
   case"tumble": r=A([kf(0,[0],{o:{x:[0.5],y:[0.5]},i:{x:[0.5],y:[0.5]}}),kf(B,[360])]);s=XY([[0,100,100,ES],[0.5,8,100,ES],[1,100,100]]);break;
   case"spin": r=A([kf(0,[0],{o:{x:[0.5],y:[0.5]},i:{x:[0.5],y:[0.5]}}),kf(B,[360])]);break;
   case"popspin": r=A([kf(0,[0],{o:{x:[0.5],y:[0.5]},i:{x:[0.5],y:[0.5]}}),kf(B,[360])]);s=SC([[0,55,EZ],[0.3,100+a,EI],[0.5,100,ES],[1,100]]);break;
   case"tick": r=A([kfh(0,[0]),kfh(0.25*B,[90]),kfh(0.5*B,[180]),kfh(0.75*B,[270]),kf(B,[360])]);break;
   case"ring": r=RO([[0,0,EZ],[0.1,a*1.3,EZ],[0.28,-a,EZ],[0.45,a*0.6,EZ],[0.62,-a*0.35,EZ],[0.8,a*0.15,EZ],[1,0]]);break;
   case"swing": r=RO([[0,0,ES],[0.25,a,ES],[0.5,0,ES],[0.75,-a,ES],[1,0]]);break;
   case"wobble": r=RO([[0,0,ES],[0.25,a*0.5,ES],[0.5,0,ES],[0.75,-a*0.5,ES],[1,0]]);s=XY([[0,100,100,ES],[0.5,100+a*0.3,100-a*0.3,ES],[1,100,100]]);break;
   case"bounce": p=PO([[0,256,EZ],[0.32,256-a*2.6,EI],[0.55,256,EZ],[0.7,256-a*0.8,ES],[1,256]]);s=XY([[0,100,100,ES],[0.5,100+a*0.5,100-a*0.5,EZ],[0.62,100,100,ES],[1,100,100]]);break;
   case"hop": p=PO([[0,256,EZ],[0.5,256-a*3,EI],[1,256]]);s=XY([[0,100,100,ES],[0.5,100-a*0.3,100+a*0.3,ES],[1,100,100]]);break;
   case"drop": p=PO([[0,256-a*5,ES],[0.55,256,EI],[0.7,256-a*1.2,ES],[0.85,256,EI],[1,256]]);break;
   case"rise": p=PO([[0,256+a*5,ES],[0.6,256,EZ],[1,256]]);o=A([kf(0,[0]),kf(0.5*B,[100]),kf(B,[100])]);break;
   case"vibrate": p=A(Array.from({length:9},(_,i)=>kf(i/8*B,[256+(i%2?a*0.4:-a*0.4),256,0],ES)));break;
   case"shake": p=PO([[0,256,ES],[0.12,256-a*0.6,ES],[0.26,256+a*0.6,ES],[0.4,256-a*0.4,ES],[0.54,256+a*0.4,ES],[0.7,256,ES],[1,256]]);break;
   case"twinkle": s=SC([[0,100,EZ],[0.5,100+a*1.6,EZ],[1,100]]);r=RO([[0,0,ES],[0.5,22,ES],[1,0]]);break;
   case"blink": s=XY([[0,100,100,ES],[0.78,100,100,ES],[0.86,100,8,EZ],[0.94,100,100,EZ],[1,100,100]]);break;
   case"flicker": s=SC([[0,100,ES],[0.2,100+a,ES],[0.38,100-a*0.5,ES],[0.55,100+a*1.1,ES],[0.72,100-a*0.2,ES],[1,100]]);break;
   case"glitch": p=A([kfh(0,[256,256,0]),kfh(0.12*B,[256+a*0.5,256-a*0.2,0]),kfh(0.2*B,[256-a*0.4,256,0]),kfh(0.28*B,[256,256,0]),kfh(0.6*B,[256,256,0]),kfh(0.66*B,[256-a*0.5,256+a*0.2,0]),kfh(0.72*B,[256,256,0]),kf(B,[256,256,0])]);s=A([kfh(0,[100,100,100]),kfh(0.12*B,[100+a*0.4,100-a*0.3,100]),kfh(0.2*B,[100,100,100]),kfh(0.66*B,[100-a*0.3,100+a*0.3,100]),kfh(0.72*B,[100,100,100]),kf(B,[100,100,100])]);break;
  }
  return {s,r,o,p};
}

function hexRGB(h){h=h.replace('#','');return [parseInt(h.slice(0,2),16)/255,parseInt(h.slice(2,4),16)/255,parseInt(h.slice(4,6),16)/255];}
const PALCYC=[[0,0.871,0.322],[0.22,0.74,0.97],[0.655,0.545,0.98],[0.937,0.267,0.267],[0.96,0.62,0.04]];
function cycleColor(N){const k=PALCYC.map((c,i)=>kf(i/PALCYC.length*N,[c[0],c[1],c[2],1],ES));k.push(kf(N,[PALCYC[0][0],PALCYC[0][1],PALCYC[0][2],1]));return {a:1,k};}
function recolor(o,rgb,cyc,N){if(Array.isArray(o)){o.forEach(x=>recolor(x,rgb,cyc,N));return;}if(o&&typeof o==='object'){if((o.ty==='fl'||o.ty==='st')&&o.c)o.c=cyc?cycleColor(N):{a:0,k:[rgb[0],rgb[1],rgb[2],1]};for(const k in o)if(k!=='c'&&typeof o[k]==='object')recolor(o[k],rgb,cyc,N);}}

// draw-on + обводка (premium) — корректный порядок: path -> trim -> stroke -> fill -> tr
function lastPathIdx(it){let idx=-1;it.forEach((x,k)=>{if(['sh','rc','el','sr'].includes(x.ty))idx=k;});return idx;}
function toOutline(shapes,rgb,width){(shapes||[]).forEach(sh=>{if(sh.ty!=='gr'||!sh.it)return;const pi=lastPathIdx(sh.it);const fill=sh.it.find(x=>x.ty==='fl');if(pi>=0&&fill){fill.o={a:0,k:0};if(!sh.it.find(x=>x.ty==='st'))sh.it.splice(pi+1,0,{ty:'st',c:{a:0,k:[rgb[0],rgb[1],rgb[2],1]},o:{a:0,k:100},w:{a:0,k:width},lc:2,lj:2,ml:1,nm:'ol'});}else toOutline(sh.it,rgb,width);});}
function drawOn(shapes,N,col,outline){const EE={i:{x:[0.6],y:[1]},o:{x:[0.4],y:[0]}};const kf=a=>({a:1,k:a.map((p,x)=>x<a.length-1?Object.assign({t:p.t,s:p.s},EE):{t:p.t,s:p.s})});const H=v=>Math.round(N*v);(shapes||[]).forEach(sh=>{if(sh.ty!=='gr'||!sh.it)return;let pi=-1;sh.it.forEach((x,k)=>{if(['sh','rc','el','sr'].includes(x.ty))pi=k;});if(pi<0){drawOn(sh.it,N,col,outline);return;}const fill=sh.it.find(x=>x.ty==='fl');let st=sh.it.find(x=>x.ty==='st');const c=col||(fill&&fill.c.k)||(st&&st.c.k)||[0,0.871,0.322,1];const trim=outline?{ty:'tm',m:1,o:{a:0,k:0},nm:'dr',s:kf([{t:0,s:[0]},{t:H(0.5),s:[0]},{t:N,s:[100]}]),e:kf([{t:0,s:[0]},{t:H(0.5),s:[100]},{t:N,s:[100]}])}:{ty:'tm',m:1,o:{a:0,k:0},nm:'dr',s:{a:0,k:0},e:kf([{t:0,s:[0]},{t:H(0.6),s:[100]},{t:N,s:[100]}])};if(outline){if(fill)fill.o={a:0,k:0};if(!st)sh.it.splice(pi+1,0,{ty:'st',c:{a:0,k:c},o:{a:0,k:100},w:{a:0,k:12},lc:2,lj:2,ml:1,nm:'ds'});}else{if(!st)sh.it.splice(pi+1,0,{ty:'st',c:{a:0,k:c},o:{a:0,k:100},w:{a:0,k:10},lc:2,lj:2,ml:1,nm:'ds'});if(fill)fill.o={a:1,k:[Object.assign({t:0,s:[0]},EE),Object.assign({t:H(0.5),s:[0]},EE),Object.assign({t:H(0.68),s:[100]},EE),{t:N,s:[100]}]};}sh.it.splice(pi+1,0,trim);});}
function elementGroups(layers){const out=[];function walk(items){(items||[]).forEach(x=>{if(!x||x.ty!=="gr"||!x.it)return;const hasPath=x.it.some(y=>y&&y.ty==="sh");if(hasPath)out.push(x);else walk(x.it);});}(layers||[]).forEach(L=>walk(L.shapes));return out;}
function elementBBox(g){let minx=Infinity,miny=Infinity,maxx=-Infinity,maxy=-Infinity;function walk(items){(items||[]).forEach(x=>{if(!x)return;if(x.ty==="sh"&&x.ks&&x.ks.k&&Array.isArray(x.ks.k.v)){x.ks.k.v.forEach(p=>{if(!Array.isArray(p))return;minx=Math.min(minx,p[0]);miny=Math.min(miny,p[1]);maxx=Math.max(maxx,p[0]);maxy=Math.max(maxy,p[1]);});}else if(x.ty==="gr"&&x.it)walk(x.it);});}walk(g.it);if(!isFinite(minx))return null;return {cx:(minx+maxx)/2,cy:(miny+maxy)/2,w:Math.max(1,maxx-minx),h:Math.max(1,maxy-miny)};}
function elementTr(g){let tr=g.it&&g.it.find(x=>x.ty==="tr");if(!tr){tr={ty:"tr",a:K([0,0]),p:K([0,0]),s:K([100,100]),r:K(0),o:K(100)};g.it.push(tr);}return tr;}
function applyElementAnim(base,kind,N,amp,ov){const layers=Array.isArray(base)?base:(base&&base.layers)||[];const groups=elementGroups(layers).map(g=>({g,b:elementBBox(g)})).filter(x=>x.b).sort((a,b)=>a.b.cx-b.b.cx);const count=groups.length;if(!count)return base;const step=Math.max(1,Math.round(N*0.12)),dur=Math.max(1,Math.round(N*0.22));const env=t=>0.5*(1-Math.cos(2*Math.PI*t));const wavePeak=t=>0.5*(1+Math.cos(2*Math.PI*t));const q=t=>Math.max(0,Math.min(N,Math.round(t)));const clean=pts=>{const out=[];pts.forEach(p=>{const kk=(p[3]?kfh:kf)(q(p[0]),p[1],p[2]);if(out.length&&out[out.length-1].t===kk.t&&JSON.stringify(out[out.length-1].s)===JSON.stringify(kk.s))return;out.push(kk);});return A(out);};const samples=fn=>A(Array.from({length:13},(_,i)=>{const t=i/12*N;return kf(t,fn(i/12));}));groups.forEach(({g,b},index)=>{const tr=elementTr(g),cx=b.cx,cy=b.cy,w=b.w,h=b.h,m=Math.max(w,h),d=Math.min(N-1,Math.round((index/count)*Math.max(1,N-dur))),tin=Math.min(N,d+dur),tout=Math.max(tin,N-dur);if(["el_pulse","el_lead","el_segment"].includes(kind)){tr.a=K([cx,cy]);tr.p=K([cx,cy]);}switch(kind){case"el_sequential":tr.o=clean([[0,[25]],[d,[25]],[tin,[100],EZ],[tout,[100]],[N,[25]]]);break;case"el_type":tr.o=clean([[0,[25],null,true],[d,[25],null,true],[Math.min(N,d+1),[100],null,true],[N-1,[100],null,true],[N,[25]]]);break;case"el_pulse":{const phase=index/count;tr.s=samples(t=>{const v=100+amp*0.6*wavePeak(t-phase);return [v,v];});break;}case"el_stagger":tr.a=K([cx,cy]);tr.p=clean([[0,[cx,cy+0.8*h]],[d,[cx,cy+0.8*h]],[tin,[cx,cy],EZ],[tout,[cx,cy]],[N,[cx,cy+0.8*h]]]);tr.o=clean([[0,[15]],[d,[15]],[tin,[100],EZ],[tout,[100]],[N,[15]]]);break;case"el_lead":tr.r=samples(t=>[amp*0.5*env((t-(d/N)+1)%1)]);break;case"el_assemble":{const ang=2*Math.PI*index/count,dx=Math.cos(ang)*0.6*m,dy=Math.sin(ang)*0.6*m;tr.a=K([cx,cy]);tr.p=clean([[0,[cx+dx,cy+dy]],[d,[cx+dx,cy+dy]],[tin,[cx,cy],EZ],[tout,[cx,cy]],[N,[cx+dx,cy+dy]]]);tr.o=clean([[0,[10]],[d,[10]],[tin,[100],EZ],[tout,[100]],[N,[10]]]);break;}case"el_segment":tr.r=clean([[0,[amp*0.6]],[d,[amp*0.6]],[tin,[0],EZ],[tout,[0]],[N,[amp*0.6]]]);tr.o=clean([[0,[20]],[d,[20]],[tin,[100],EZ],[tout,[100]],[N,[20]]]);break;case"el_orbit":{const rad=0.22*m,phase=index/count;tr.a=K([cx,cy]);tr.p=samples(t=>[cx+Math.cos(2*Math.PI*(t+phase))*rad,cy+Math.sin(2*Math.PI*(t+phase))*rad]);break;}}});return base;}
function bgLayer(w,h,N,rxFrac,fillHex){
  const rx=Math.round(Math.min(w,h)*(rxFrac!=null?rxFrac:0.16));   // ~16% smooth bento radius (default)
  const fill=hexRGB(fillHex||'#08090C');            // default #08090C
  return { ty:4, ind:9999, ip:0, op:N, st:0, sr:1, bm:0,
    ks:{ a:{a:0,k:[0,0]}, p:{a:0,k:[0,0]}, s:{a:0,k:[100,100]}, r:{a:0,k:0}, o:{a:0,k:100} },
    shapes:[ { ty:'gr', it:[
      { ty:'rc', d:1, s:{a:0,k:[w,h]}, p:{a:0,k:[w/2,h/2]}, r:{a:0,k:rx} },
      { ty:'fl', c:{a:0,k:fill}, o:{a:0,k:100}, r:1 },
      { ty:'tr', a:{a:0,k:[0,0]}, p:{a:0,k:[0,0]}, s:{a:0,k:[100,100]}, r:{a:0,k:0}, o:{a:0,k:100} }
    ]} ] };
}
// ===== LAYER STACK: нормализация cfg + generic dir/phase пост-обработка ks рига =====
// Back-compat: принимает старую форму {kinds:[...],amp,ov} И новую {layers:[{kind,amp,ov,dir,phase}]}.
function cfgLayers(opt){
  if(Array.isArray(opt.layers)&&opt.layers.length){
    return opt.layers.map(L=>({kind:(L&&L.kind)||"none",amp:(L&&L.amp!=null)?L.amp:(opt.amp!=null?opt.amp:12),ov:(L&&L.ov!=null)?L.ov:(opt.ov!=null?opt.ov:10),dir:(L&&L.dir===-1)?-1:1,phase:(L&&L.phase)?L.phase:0}));
  }
  const kinds=(opt.kinds&&opt.kinds.length?opt.kinds:["beat"]);
  const amp=opt.amp!=null?opt.amp:12,ov=opt.ov!=null?opt.ov:10;
  return kinds.map(k=>({kind:k,amp,ov,dir:1,phase:0}));
}
// dir (-1): разворот вращения (r→-r) и вертикали движения (y→512-y), generic пост-обработка.
function applyDir(ks,dir){
  if(dir!==-1)return;
  if(ks.r){if(ks.r.a===1)ks.r.k.forEach(f=>{if(Array.isArray(f.s))f.s=f.s.map(v=>typeof v==='number'?-v:v);});else if(typeof ks.r.k==='number')ks.r.k=-ks.r.k;else if(Array.isArray(ks.r.k))ks.r.k=ks.r.k.map(v=>typeof v==='number'?-v:v);}
  if(ks.p){const ref=p=>(Array.isArray(p)?[p[0],512-p[1],p[2]!=null?p[2]:0]:p);if(ks.p.a===1)ks.p.k.forEach(f=>{if(Array.isArray(f.s))f.s=ref(f.s);});else if(Array.isArray(ks.p.k))ks.p.k=ref(ks.p.k);}
}
// phase (0..1): циклический сдвиг времени keyframes слоя для разнообразия в миксе.
// Сохраняет бесшовный луп: сдвигает t→(t+phase*N)%N, пересортировывает, дублирует крайние кадры на 0 и N.
function shiftProp(prop,phase,N){
  if(!prop||prop.a!==1||!Array.isArray(prop.k)||!prop.k.length||phase<=0)return prop;
  const off=((phase%1)+1)%1*N;
  const src=prop.k.map(f=>({t:f.t,s:Array.isArray(f.s)?f.s.slice():f.s,o:f.o,i:f.i,h:f.h}));
  const valAt=tt=>{let cur=src[0];for(const f of src){if(f.t<=tt)cur=f;else break;}return cur;};
  const out=src.map(f=>{let nt=(f.t+off)%N;if(nt<0)nt+=N;return Object.assign({},f,{t:Math.round(nt)});});
  out.sort((x,y)=>x.t-y.t);
  const startVal=valAt(((0- off)%N+N)%N);
  const endVal=valAt(((N- off)%N+N)%N);
  if(!out.length||out[0].t!==0)out.unshift(Object.assign({},startVal,{t:0,o:ES.o,i:ES.i}));
  if(out[out.length-1].t!==N)out.push(Object.assign({},endVal,{t:N}));
  const dedup=[];out.forEach(f=>{if(dedup.length&&dedup[dedup.length-1].t===f.t)dedup[dedup.length-1]=f;else dedup.push(f);});
  return {a:1,k:dedup};
}
function applyPhase(ks,phase,N){if(!phase)return;["p","s","r","o"].forEach(key=>{if(ks[key])ks[key]=shiftProp(ks[key],phase,N);});}

function makeAnimX(base,opt){
  let layers=cfgLayers(opt).filter(L=>L.kind&&L.kind!=="none");
  const beats=opt.beats||1;const a=JSON.parse(JSON.stringify(base));const N=beats*30;a.fr=60;a.ip=0;a.op=N;a.w=512;a.h=512;
  const icon=(a.layers||[]).slice();icon.forEach(L=>{L.ip=0;L.op=N;L.st=0;});
  const rgb=hexRGB(opt.color||"#00DE52");if(opt.color||opt.cycle)recolor(icon,rgb,!!opt.cycle,N);if(opt.outline)icon.forEach(L=>toOutline(L.shapes,rgb,opt.width||14));
  if(layers.some(L=>L.kind==="drawon")){icon.forEach(L=>drawOn(L.shapes,N,[rgb[0],rgb[1],rgb[2],1],!!opt.outline));layers=layers.filter(L=>L.kind!=="drawon");}
  const elLayers=layers.filter(L=>L.kind.startsWith("el_"));const wholeLayers=layers.filter(L=>!L.kind.startsWith("el_"));
  elLayers.forEach(L=>applyElementAnim(icon,L.kind,N,L.amp,L.ov));
  if(!wholeLayers.length){a.layers=icon;if(opt.bg)a.layers.push(bgLayer(a.w,a.h,N, opt.bgrx, opt.bgfill));return a;}
  let prev=null;
  wholeLayers.forEach((L,i)=>{
    const ind=9000+i;const pr=buildProps(L.kind,N,L.amp,L.ov);
    const ks={a:K([256,256,0]),p:pr.p,s:pr.s,r:pr.r,o:pr.o};
    applyDir(ks,L.dir);applyPhase(ks,L.phase,N);
    const rig={ddd:0,ind,ty:3,nm:"rig"+i,sr:1,ip:0,op:N,st:0,bm:0,ks};
    if(prev!==null)rig.parent=prev;a.layers.push(rig);prev=ind;
  });
  icon.forEach(L=>{L.parent=prev;});
  if(opt.bg)a.layers.push(bgLayer(a.w,a.h,N, opt.bgrx, opt.bgfill));
  return a;
}

// ===== Бренд-пресеты (сюжеты из docs/animation-playbook.md). Только данные: layer-stack + цвет. =====
const PRESETS_BRAND={
  "db-пульс":      {layers:[{kind:"beat",amp:16,ov:8,dir:1,phase:0},{kind:"shake",amp:6,ov:0,dir:1,phase:0.5}],color:"#00DE52"},
  "ON-кольцо":     {layers:[{kind:"ring",amp:24,ov:10,dir:1,phase:0}],color:"#00DE52"},
  "monitor-загрузка":{layers:[{kind:"drawon",amp:12,ov:10,dir:1,phase:0}],color:"#38BDF8"},
  "new-курсор":    {layers:[{kind:"blink",amp:12,ov:8,dir:1,phase:0}],color:"#00DE52"},
  "shield-удар":   {layers:[{kind:"elastic",amp:22,ov:10,dir:1,phase:0},{kind:"ring",amp:14,ov:8,dir:1,phase:0.3}],color:"#38BDF8"},
  "update-вращение":{layers:[{kind:"spin",amp:0,ov:0,dir:1,phase:0}],color:"#00DE52"}
};

function randomCfg(crazy){const pick=()=>KINDS[Math.floor(Math.random()*(KINDS.length-1))];const k1=pick();const mix=crazy?Math.random()<0.8:Math.random()<0.4;const k2=mix?pick():null;const pal=["#00DE52","#00DE52","#38BDF8","#A78BFA","#EF4444","#F59E0B","#FFFFFF"];const mk=k=>({kind:k,amp:(crazy?20:8)+Math.floor(Math.random()*30),ov:Math.floor(Math.random()*(crazy?30:22)),dir:Math.random()<0.5?1:-1,phase:mix?Math.round(Math.random()*100)/100:0});const layers=k2?[mk(k1),mk(k2)]:[mk(k1)];return {layers,beats:(BEATS_DEFAULT[k1]||1),color:pal[Math.floor(Math.random()*pal.length)],cycle:crazy?Math.random()<0.5:Math.random()<0.15,outline:crazy?Math.random()<0.6:Math.random()<0.25,width:10+Math.floor(Math.random()*14)};}
if (typeof window !== 'undefined') { window.makeAnimX=makeAnimX;window.KINDS=KINDS;window.CATS=CATS;window.BEATS_DEFAULT=BEATS_DEFAULT;window.randomCfg=randomCfg;window.applyElementAnim=applyElementAnim;window.PRESETS_BRAND=PRESETS_BRAND;window.cfgLayers=cfgLayers; }
if (typeof module !== 'undefined' && module.exports) { module.exports = {makeAnimX, KINDS, CATS, BEATS_DEFAULT, randomCfg, applyElementAnim, PRESETS_BRAND, cfgLayers}; }
