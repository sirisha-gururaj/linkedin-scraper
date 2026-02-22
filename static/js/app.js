const form = document.getElementById('scrapeForm');
const runBtn = document.getElementById('runBtn');
const spinner = document.getElementById('spinner');
const message = document.getElementById('message') || document.getElementById('message');
const downloadArea = document.getElementById('downloadArea');
const downloadLink = document.getElementById('downloadLink');

async function postJSON(url, data){
  const res = await fetch(url, {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data)
  });
  if(!res.ok) throw new Error('Request failed');
  return res.json();
}

const statusDot = document.querySelector('.status-dot');
function setStatus(text, running){
  const statusEl = document.querySelector('.status-text') || document.getElementById('message');
  if(statusEl) statusEl.textContent = text;
  if(!statusDot) return;
  if(running){
    statusDot.classList.remove('idle');
    statusDot.classList.add('running');
  } else {
    statusDot.classList.remove('running');
    statusDot.classList.add('idle');
  }
}

function disableForm(val){
  Array.from(form.querySelectorAll('input, button')).forEach(el=>el.disabled = val);
}

form.addEventListener('submit', async (ev) =>{
  ev.preventDefault();
  if(!form.checkValidity()){
    form.reportValidity();
    return;
  }

  // gather values
  const keyword = document.getElementById('keyword').value.trim();
  let limitVal = document.getElementById('limit').value;
  const limit = limitVal ? parseInt(limitVal,10) : 200; // fallback default
  const headless = document.getElementById('headless').checked;

  // If headless is false, confirm with user before opening a browser window
  if(!headless){
    const ok = window.confirm('This run will open a Chrome browser window on this machine (for you to login if needed). Do you want to continue?');
    if(!ok){
      return;
    }
  }

  disableForm(true);
  setStatus('Starting job...', true);

  try{
    await postJSON('/start', { keyword, limit_records: limit, headless });
  }catch(err){
    setStatus('Failed to start job', false);
    disableForm(false);
    return;
  }

  // clear any previous results while the new job launches
  try{
    const head = document.getElementById('resultsHead');
    const body = document.getElementById('resultsBody');
    const panel = document.getElementById('resultsPanel');
    const dl2 = document.getElementById('downloadLink2');
    if(head) head.innerHTML = '';
    if(body) body.innerHTML = '';
    if(panel) panel.classList.add('hidden');
    if(dl2) dl2.classList.add('hidden');
    if(downloadArea) downloadArea.classList.add('hidden');
  }catch(e){ /* ignore UI clear errors */ }

  // If we started a non-headless run, try to bring the UI tab back into focus.
  // Some OSes will switch focus to the new Chrome window; we attempt to refocus
  // this tab intermittently for a few seconds so the UI remains visible.
  if(!headless){
    let tries = 0;
    const maxTries = 8;
    const refocusInterval = setInterval(()=>{
      try{ window.focus(); }catch(e){}
      tries += 1;
      if(tries >= maxTries) clearInterval(refocusInterval);
    }, 700);
  }

  // poll for status
  const poll = setInterval(async ()=>{
    try{
      const res = await fetch('/status');
      const s = await res.json();
      setStatus(s.message || (s.running? 'Running...' : 'Idle'), s.running);
      if(!s.running){
        clearInterval(poll);
        disableForm(false);
        if(s.last_count && s.last_count>0){
          downloadArea.classList.remove('hidden');
          if(downloadLink) downloadLink.href = '/download';
          // fetch and render results in table
          try{
            const r = await fetch('/results');
            if(r.ok){
              const data = await r.json();
              if(data && data.rows){
                renderResults(data.rows);
              }
            }
          }catch(e){
            console.error('Failed to load results', e);
          }
        }
      }
    }catch(e){
      clearInterval(poll);
      setStatus('Status error', false);
      disableForm(false);
    }
  }, 900);
});

function renderResults(rows){
  if(!rows || !rows.length) return;
  const head = document.getElementById('resultsHead');
  const body = document.getElementById('resultsBody');
  const panel = document.getElementById('resultsPanel');
  const dl2 = document.getElementById('downloadLink2');
  // clear
  head.innerHTML = '';
  body.innerHTML = '';
  // normalize and dedupe keys to avoid double-columns from messy CSV headers
  const rawKeys = Object.keys(rows[0]);
  function normalize(k){
    if(!k) return '';
    return String(k).trim().replace(/^\"|\"$/g,'').toLowerCase().replace(/\s+/g,'_');
  }

  // map normalized -> first original key encountered
  const normToOrig = {};
  const normOrder = [];
  rawKeys.forEach(orig => {
    const n = normalize(orig);
    if(!n) return;
    if(!(n in normToOrig)){
      normToOrig[n] = orig;
      normOrder.push(n);
    }
  });

  const preferred = ['name','location','current_company','current_role','profile_url'];
  const remaining = normOrder.filter(n=>!preferred.includes(n));
  const finalNormKeys = preferred.concat(remaining).filter((v,i,a)=>a.indexOf(v)===i && v);

  // human-friendly header label
  function labelFor(n){
    if(!n) return '';
    const map = {
      'name':'Name','location':'Location','current_company':'Company','current_role':'Role','profile_url':'Profile URL'
    };
    return map[n] || n.replace(/_/g,' ').replace(/\b\w/g,m=>m.toUpperCase());
  }

  const trh = document.createElement('tr');
  finalNormKeys.forEach(n=>{ const th = document.createElement('th'); th.textContent = labelFor(n); trh.appendChild(th); });
  head.appendChild(trh);

  rows.forEach(r=>{
    const tr = document.createElement('tr');
    finalNormKeys.forEach(n=>{
      const td = document.createElement('td');
      const origKey = normToOrig[n];
      const val = (origKey && r[origKey]!==undefined && r[origKey]!==null) ? String(r[origKey]) : '';
      if(n === 'profile_url' && val){
        const a = document.createElement('a');
        a.href = val;
        a.textContent = 'View';
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.className = 'profile-link';
        td.appendChild(a);
      } else {
        td.textContent = val;
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  if(panel) panel.classList.remove('hidden');
  if(dl2) dl2.classList.remove('hidden');
}
