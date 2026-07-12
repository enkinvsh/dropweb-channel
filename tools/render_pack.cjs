#!/usr/bin/env node
const fs=require('fs'), path=require('path'), zlib=require('zlib');
const ROOT=path.resolve(__dirname,'..');
const S=require(path.join(ROOT,'studio','studio.js'));
const pack=process.argv[2]||'dropweb';
const basesP=path.join(ROOT,'packs',pack,'bases.json');
const packP=path.join(ROOT,'packs',pack,'pack.json');
const B=JSON.parse(fs.readFileSync(basesP,'utf8'));
const P=fs.existsSync(packP)?JSON.parse(fs.readFileSync(packP,'utf8')):{emoji:[]};
const specById={}; (P.emoji||[]).forEach(e=>specById[e.id]=e);
function defaultCfg(id){const k=(B.defmap&&B.defmap[id])||'beat';return {kinds:[k],beats:(S.BEATS_DEFAULT[k]||1),amp:14,ov:10,color:'#00DE52',cycle:false,outline:false,width:14,bg:false};}
const outDir=path.join(ROOT,'build',pack,'tgs'); fs.mkdirSync(outDir,{recursive:true});
let ok=0, over=[];
for(const id of (B.order||Object.keys(B.bases||{}))){
  const base=B.bases[id]; if(!base){console.error('no base for',id);continue;}
  const spec=specById[id]||{};
  const cfg=spec.studio || defaultCfg(id);
  const anim=S.toEmoji100(S.makeAnimX(JSON.parse(JSON.stringify(base)), cfg));
  const tgs=zlib.gzipSync(Buffer.from(JSON.stringify(anim)));
  const fp=path.join(outDir, id+'.tgs'); fs.writeFileSync(fp,tgs);
  const kb=tgs.length/1024; ok++; if(kb>64) over.push(id+' '+kb.toFixed(1)+'KB');
  console.log((kb<=64?'  ':'! ')+id.padEnd(10)+kb.toFixed(2)+'KB'+(spec.studio?' [studio]':' [default]'));
}
console.log('rendered '+ok+' tgs -> '+outDir+(over.length?('  OVER 64KB: '+over.join(', ')):''));
