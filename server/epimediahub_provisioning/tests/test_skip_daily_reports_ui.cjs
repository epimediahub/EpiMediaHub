// User flows for the actual launcher script, without a browser dependency.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/skip_daily_reports.js'), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));
function page(storage, reply, blocked = false) {
  const handlers = {};
  const elements = {};
  for (const id of ['episcene-report-dialog','episcene-report-state','episcene-report-frame','episcene-report-close']) {
    elements[id] = {open:false,textContent:'',focus(){},addEventListener(name,fn){handlers[id+name]=fn;}};
  }
  const dialog=elements['episcene-report-dialog'];
  dialog.showModal=()=>{dialog.open=true;};
  dialog.close=()=>{dialog.open=false;handlers['episcene-report-dialogclose']();};
  let interval;
  const document={hidden:false,activeElement:{focus(){}},getElementById:id=>elements[id],addEventListener(){}};
  vm.runInNewContext(source,{document,localStorage:{getItem(k){if(blocked)throw Error();return storage[k];},
    setItem(k,v){if(blocked)throw Error();storage[k]=v;}},
    fetch:async()=>({ok:true,headers:{get:()=> 'application/json'},json:async()=>reply}),
    setInterval:fn=>{interval=fn;},encodeURIComponent});
  return {elements,dialog,check:()=>interval(),close:()=>handlers['episcene-report-closeclick']()};
}
(async()=>{
  const storage={};const reply={day:'2026-10-08',expected_day:'2026-10-08'};
  const first=page(storage,reply);await settle();
  assert(first.dialog.open);assert(first.elements['episcene-report-frame'].src.includes('2026-10-08'));
  first.close();assert(!first.dialog.open);first.check();await settle();assert(!first.dialog.open);
  const revisit=page(storage,reply);await settle();assert(!revisit.dialog.open);
  reply.day=reply.expected_day='2026-10-09';revisit.check();await settle();assert(revisit.dialog.open);
  const stale=page({}, {day:'2026-10-08',expected_day:'2026-10-09'});await settle();
  assert(!stale.dialog.open);assert(stale.elements['episcene-report-state'].textContent.includes('fehlt'));
  const privatePage=page({},reply,true);await settle();assert(privatePage.dialog.open);
  privatePage.close();privatePage.check();await settle();assert(!privatePage.dialog.open);
  const empty=page({}, {day:null,expected_day:'2026-10-09'});await settle();
  assert(!empty.dialog.open);assert(empty.elements['episcene-report-state'].textContent.includes('Noch kein'));
  console.log('Launcher flows passed: first open, close, revisit, next day, stale report, blocked storage, empty archive.');
})().catch(e=>{console.error(e);process.exitCode=1;});
