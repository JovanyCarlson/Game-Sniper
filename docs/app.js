(()=>{'use strict';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const WINS={"15m":900,"1h":3600,"6h":21600,"24h":86400};
let privateKey='', workflowToken='', pendingSend=null, DB={games:[],alerts:[],status:{}},windowKey='1h',platform='all',page='overview',query='',sort='momentum',selected=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>n===null||n===undefined?'—':Number(n).toLocaleString('en-US');
const change=(n,addPct=true)=>n===null||n===undefined?'Collecting…':`${Number(n).toLocaleString('en-US',{signDisplay:'always'})}${addPct?'':''}`;
const fromTs=ts=>ts?new Date(ts*1000).toLocaleString('en-US',{dateStyle:'medium',timeStyle:'short'}):'Awaiting first scan';
const ago=ts=>ts?Math.round((Date.now()/1000-ts)/60)+' min ago':'—';
const tier=g=>g.signal?.tier||'monitoring';
const ageString=g=>{const raw=g.created_at;if(!raw)return 'Date unavailable';const dt=new Date(raw);return isNaN(dt.valueOf())?raw:dt.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});};
const win=(g,w=windowKey)=>g.signal?.windows?.[w]??null;
const growthText=(g,w=windowKey)=>{const x=win(g,w);return x?`${change(x.delta)} / ${x.percent>0?'+':''}${x.percent.toFixed(1)}%`:'Collecting…'};
const rating=g=>{if(g.platform==='roblox'){const up=g.up_votes,down=g.down_votes;return Number.isInteger(up)&&Number.isInteger(down)&&up+down>0?`${Math.round(up/(up+down)*100)}% likes`:'No rating'}const p=g.positive_reviews,n=g.negative_reviews;return Number.isInteger(p)&&Number.isInteger(n)&&p+n>0?`${Math.round(p/(p+n)*100)}% positive`:'No reviews data'};
const safeLink=(g)=>g.platform==='roblox'?`https://www.roblox.com/games/${encodeURIComponent(String(g.url||'').match(/\/games\/(\d+)/)?.[1]||g.gid)}`:`https://store.steampowered.com/app/${encodeURIComponent(g.gid)}/`;
const logo=g=>g.image&&/^https:\/\//.test(g.image)?`<img class="game-icon" src="${esc(g.image)}" loading="lazy" alt="" onerror="this.style.display='none'">`:`<span class="game-fallback">${g.platform==='roblox'?'◇':'●'}</span>`;
const place=g=>g.platform==='roblox'?'◇ Roblox':'● Steam';
function example(){let now=Math.floor(Date.now()/1000);const items=[['roblox','92301421','Skyline Egg Quest',172,45],['roblox','91231042','Build a Jungle',540,190],['steam','3456090','Cozy Deep Sea',390,105],['steam','3551230','Island Survival',730,280],['roblox','9699011','Dream Parkour',115,35]];let games=items.map(([platform,gid,name,current,base],i)=>{let h=[];for(let j=0;j<=32;j++){const p=Math.round(base+(current-base)*Math.pow(j/32,1.9));h.push([now-(32-j)*300,p])}let windows={};for(const [key,sec] of Object.entries(WINS)){let p=h.find(x=>x[0]<=now-sec*.75&&x[0]>=now-sec*1.3);windows[key]=p?{delta:current-p[1],percent:Math.round(100*(current-p[1])/Math.max(10,p[1])*10)/10}:null}return {platform,gid,name,players:current,created_at:new Date(now*1000-3*86400000).toISOString().slice(0,10),visits:platform==='roblox'?115202+i*93120:null,up_votes:platform==='roblox'?255+i*100:null,down_votes:platform==='roblox'?30+i*13:null,positive_reviews:platform==='steam'?120+i*25:null,negative_reviews:platform==='steam'?14+i*5:null,last_polled:now,image:'',history:h,signal:{score:88-i*11,tier:i%2?'scout':'breakout',windows}}});return {games,alerts:[{ts:now-640,key:'roblox:92301421',name:'Skyline Egg Quest',tier:'breakout',players:172,platform:'roblox',url:'https://www.roblox.com/games/92301421'}],status:{tracked:5,last_scan:now,successful_games:5,source_errors:[]},mode:'demo',generated_at:now}}
function table(games){if(!games.length)return '<div class="empty"><span style="font-size:35px">⌖</span><strong>No fresh breakout verified yet</strong>GameSniper only surfaces recent releases. Look under Discover for new games still collecting growth history.</div>';
return `<div style="overflow-x:auto"><table class="game-table"><thead><tr><th>GAME</th><th>ACTIVE NOW</th><th>GROWTH · ${esc(windowKey.toUpperCase())}</th><th>SIGNAL</th><th>RATING</th><th>DATE CREATED / RELEASED</th><th>OPEN</th><th>DISCORD</th></tr></thead><tbody>${games.map(g=>{const w=win(g);return `<tr><td><div class="game-cell">${logo(g)}<div><button class="top-game game-name" data-open="${esc(g.platform+':'+g.gid)}">${esc(g.name||g.gid)}</button><span class="game-meta">${place(g)}</span></div></div></td><td class="number">${num(g.players)}</td><td class="number ${w?(w.delta>=0?'green':'red'):'muted'}">${esc(growthText(g))}</td><td><span class="pill ${esc(tier(g))}">${esc(tier(g).toUpperCase())} · ${g.signal?.score??0}</span></td><td>${esc(rating(g))}</td><td class="data-time">${esc(ageString(g))}</td><td><a class="badge-link" href="${esc(safeLink(g))}" target="_blank" rel="noopener noreferrer">PLAY ↗</a></td><td><button class="send-small" data-send-game="${esc(g.platform+':'+g.gid)}" type="button">Send ↗</button></td></tr>`}).join('')}</tbody></table></div>`}
function ordered(){let games=DB.games.filter(g=>(platform==='all'||g.platform===platform)&&String(g.name||'').toLowerCase().includes(query));const value=g=>{let w=win(g);return sort==='players'?g.players||0:sort==='newest'?(Date.parse(g.created_at)||0):sort==='absolute'?(w?.delta??-Infinity):sort==='percent'?(w?.percent??-Infinity):(tier(g)!=='monitoring'?1000:0)+(g.signal?.score||0)*2+(w?.delta>0?Math.min(100,w.delta)/100:0)};return games.sort((a,b)=>value(b)-value(a));}
function render(){const games=ordered();const active=DB.games.filter(g=>['breakout','viral'].includes(tier(g))).length;$('#stat-tracked').textContent=num(DB.games.length);$('#stat-breakout').textContent=num(active);$('#stat-scout').textContent=num(DB.games.filter(g=>tier(g)==='scout').length);$('#stat-alerts').textContent=num(DB.alerts.length);$('#roblox-count').textContent=`${DB.games.filter(g=>g.platform==='roblox').length} monitored`;$('#steam-count').textContent=`${DB.games.filter(g=>g.platform==='steam').length} monitored`;$('#overview-list').innerHTML=table([...DB.games].filter(g=>['scout','breakout','viral'].includes(tier(g))&&Object.values(g.signal?.windows||{}).some(w=>w?.delta>0)).sort((a,b)=>(b.signal?.score||0)-(a.signal?.score||0)).slice(0,12));$('#discover-list').innerHTML=table(games);$('#game-counter').textContent=`${games.length} games`;$('#last-updated-header').textContent=DB.generated_at?'Updated '+ago(DB.generated_at):'Awaiting first scan';$('#health-scan').textContent=fromTs(DB.status?.last_scan);$('#health-sampled').textContent=num(DB.status?.successful_games);$('#health-tracked').textContent=num(DB.status?.tracked);$('#health-webhook').textContent=DB.status?.webhook_configured?'Yes':'Not configured';const failures=DB.status?.source_errors||[];$('#source-errors').innerHTML=failures.length?failures.map(e=>`<div class="error-line">⚠ ${esc(e)}</div>`).join(''):'<div class="mini-note">No source errors recorded.</div>';$('#alerts-list').innerHTML=(DB.alerts||[]).length?DB.alerts.map(a=>`<div class="alert-card"><div class="alert-icon">⌖</div><div class="alert-info"><strong><a href="${esc(safeLink(a))}" target="_blank" rel="noopener noreferrer">${esc(a.name)} ↗</a> &nbsp; <span class="pill ${esc(a.tier)}">${esc(a.tier?.toUpperCase())}</span></strong><small>${esc(a.platform?.toUpperCase())} · ${num(a.players)} active · ${esc(fromTs(a.ts))}</small></div><span class="badge-link">SENT</span></div>`).join(''):'<div class="empty"><strong>No alerts sent yet</strong>Alerts appear here when growth is sustained and the Discord webhook accepts a message.</div>';const isdemo=DB.mode==='demo',stale=DB.generated_at&&Date.now()/1000-DB.generated_at>1800;$('#mode-indicator').classList.toggle('stale',!!stale);$('#mode-indicator').innerHTML=isdemo?'● PREVIEW':stale?'● STALE SAMPLES':'● LIVE SAMPLES';$('#demo-warning').classList.toggle('hidden',!isdemo);}
function chart(game,w){const recent=game.history?.filter(p=>p[0]>=Date.now()/1000-WINS[w]*1.15)||[];const points=recent.length>=2?recent:game.history?.slice(-30)||[];if(points.length<2)return '<div class="empty">Waiting for enough history to plot this period.</div>';const width=660,height=220,pad=16;const values=points.map(p=>p[1]),lowest=Math.min(...values),highest=Math.max(...values),span=Math.max(1,highest-lowest),xmin=points[0][0],xspan=Math.max(1,points.at(-1)[0]-xmin);const coords=points.map(p=>[(p[0]-xmin)/xspan*(width-pad*2)+pad,height-pad-(p[1]-lowest)/span*(height-pad*2)]);const path=coords.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');const area=`${path} L${coords.at(-1)[0]} ${height-pad} L${coords[0][0]} ${height-pad} Z`;return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Recorded concurrent players"><defs><linearGradient id="chart-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#42e1ad" stop-opacity=".22"/><stop offset="100%" stop-color="#42e1ad" stop-opacity="0"/></linearGradient></defs><line x1="${pad}" x2="${width-pad}" y1="${height-pad}" y2="${height-pad}" stroke="#36505a" stroke-width="1"/><line x1="${pad}" x2="${width-pad}" y1="${pad}" y2="${pad}" stroke="#243f48" stroke-dasharray="4,7"/><path d="${area}" fill="url(#chart-fill)"/><path d="${path}" fill="none" stroke="#45e2ae" stroke-width="3" stroke-linejoin="round"/><circle cx="${coords.at(-1)[0]}" cy="${coords.at(-1)[1]}" r="5" fill="#45e2ae"/><text x="${pad+4}" y="${pad+15}" fill="#879baa" font-size="12">${num(highest)} players</text><text x="${pad+4}" y="${height-pad-9}" fill="#879baa" font-size="12">${num(lowest)}</text></svg>`;}
function modal(game,w=windowKey){selected=game;let stats=[['Active now',num(game.players)],['Visits',game.platform==='roblox'?num(game.visits):'Not public'],[game.platform==='roblox'?'Like ratio':'Steam reviews',rating(game)],[game.platform==='roblox'?'Created':'Released',ageString(game)]];$('#modal-body').innerHTML=`<div class="modal-content"><div class="modal-game">${logo(game)}<div><h2>${esc(game.name)}</h2><span class="modal-meta">${esc(place(game))} · Sniper Score ${game.signal?.score||0}/100 · ${esc(tier(game).toUpperCase())}</span></div></div><div class="detail-stats">${stats.map(([t,v])=>`<div class="detail-stat"><span>${esc(t)}</span><strong>${esc(v)}</strong></div>`).join('')}</div><div class="modal-kpi-label">GROWTH · ${esc(w.toUpperCase())}: ${esc(growthText(game,w))}</div><div class="chart-box"><p class="chart-caption">Sampled concurrent players. Missing readings are not interpolated.</p><div id="modal-chart">${chart(game,w)}</div></div><div class="chart-controls">${Object.keys(WINS).map(t=>`<button data-chart-window="${t}" class="${t===w?'active':''}">${t.toUpperCase()}</button>`).join('')}</div><div class="detail-footer"><button class="send-button" id="send-selected-game" type="button">↗ Send to my Discord</button><a class="external-link" href="${esc(safeLink(game))}" target="_blank" rel="noopener noreferrer">Open ${esc(game.platform==='roblox'?'Roblox game':'Steam store page')} ↗</a><span class="mini-note">Latest sample: ${esc(fromTs(game.last_polled))}</span></div><p id="send-status" class="send-status" role="status"></p></div>`;$('#game-modal').classList.remove('hidden');}
function navigate(id){page=id;$$('.page').forEach(el=>el.classList.toggle('active',el.id==='page-'+id));$$('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===id&&el.classList.contains('nav-item')));$('#breadcrumb-current').textContent={overview:'Overview',discover:'Discover games',alerts:'Discord alerts',sources:'Monitoring status'}[id];window.scrollTo({top:0,behavior:'smooth'});}
function decode64(encoded){const bin=atob(encoded);return Uint8Array.from(bin,c=>c.charCodeAt(0));}
async function decryptEnvelope(envelope,key64){
  if(envelope.version!==1||envelope.alg!=='AES-256-GCM+zlib')throw Error('Unsupported encrypted data format');
  const key=await crypto.subtle.importKey('raw',decode64(key64),'AES-GCM',false,['decrypt']);
  const bytes=await crypto.subtle.decrypt({name:'AES-GCM',iv:decode64(envelope.nonce),additionalData:new TextEncoder().encode('gamesniper-v1')},key,decode64(envelope.ciphertext));
  // Python encrypts with zlib; browser DecompressionStream supports deflate/zlib on modern browsers.
  const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'));
  return JSON.parse(await new Response(stream).text());
}
async function fetchPrivate(key){
  const r=await fetch('secure.enc.json?v='+Date.now(),{cache:'no-store'});
  if(!r.ok){if(r.status===404)throw Error('No history yet. Add both GitHub secrets and run your first workflow.');throw Error('HTTP '+r.status);}
  const unlocked=await decryptEnvelope(await r.json(),key);
  if(!unlocked.dashboard?.games)throw Error('The scan data has an unsupported format');
  return unlocked.dashboard;
}
async function load(){
  if(new URL(location).searchParams.get('demo')==='1'){DB=example();$('#lock-screen').classList.add('hidden');render();return;}
  if(!privateKey)return;
  try{DB=await fetchPrivate(privateKey);$('#lock-screen').classList.add('hidden');render();}
  catch(e){$('#mode-indicator').textContent='● CONNECTION ISSUE';$('#unlock-message').textContent=e.message;$('#lock-screen').classList.remove('hidden');}
}
async function makeKey(){
  const bytes=crypto.getRandomValues(new Uint8Array(32));
  const value=btoa(Array.from(bytes,b=>String.fromCharCode(b)).join(''));
  $('#private-key').type='text';$('#private-key').value=value;
  $('#unlock-message').textContent='New key generated locally. Copy this to GitHub Actions secrets as GAMESNIPER_STATE_KEY, and save a backup. Do NOT put it in a repository file. Then run the workflow.';
  $('#private-key').select();
}
$('#make-key').addEventListener('click',makeKey);
$('#unlock-form').addEventListener('submit',async e=>{
 e.preventDefault();const k=$('#private-key').value.trim();
 $('#unlock-message').textContent='Unlocking your encrypted radar…';
 try{DB=await fetchPrivate(k);privateKey=k;$('#private-key').value='';$('#lock-screen').classList.add('hidden');render();}
 catch(err){$('#unlock-message').textContent=err.name==='OperationError'?'Wrong unlock key, or history was encrypted with a different key.':err.message;}
});
// Owner-only dispatch: the public site NEVER receives the Discord webhook or GitHub secrets.
// GitHub access token stays exclusively in memory until the tab is closed.
async function opaqueSelector(game){
 if(!privateKey)throw Error('Unlock your private live dashboard first.');
 const secret=decode64(privateKey);
 if(secret.length!==32)throw Error('Invalid dashboard key.');
 const imported=await crypto.subtle.importKey('raw',secret,{name:'HMAC',hash:'SHA-256'},false,['sign']);
 const bytes=new TextEncoder().encode('gamesniper:manual-send:v1:'+game.platform+':'+game.gid);
 const proof=new Uint8Array(await crypto.subtle.sign('HMAC',imported,bytes));
 return [...proof].map(b=>b.toString(16).padStart(2,'0')).join('');
}
const isReal=()=>DB.mode==='live'&&Boolean(privateKey);
function showSendStatus(text,error=false){
 const toast=$('#discord-toast');
 if(toast){toast.textContent=text;toast.classList.toggle('send-error',error);toast.classList.remove('hidden');}
 const status=$('#send-status');
 if(status){status.textContent=text;status.classList.toggle('send-error',error);}
}
function requestSend(game){
 if(!game)return;
 if(!isReal()){
  showSendStatus('Discord sending works only in unlocked live mode, not the fictional preview.',true);
  alert('Unlock your live GameSniper dashboard first. Demo games cannot be sent to Discord.');
  return;
 }
 pendingSend=game;
 if(workflowToken){sendSelected().catch(e=>showSendStatus(e.message,true));return;}
 $('#send-dialog-message').textContent='';
 $('#send-discord-dialog').classList.remove('hidden');
 $('#send-discord-token').focus();
}
async function sendSelected(){
 if(!pendingSend||!workflowToken)throw Error('Missing selected game or authorization.');
 const game=pendingSend;
 if(!/^(roblox|steam)$/.test(game.platform)||!/^[0-9]+$/.test(String(game.gid)))throw Error('Invalid game ID.');
 const selector=await opaqueSelector(game);
 $('#send-discord-dialog').classList.add('hidden');
 showSendStatus('Sending request to your GitHub Actions workflow…');
 const button=$('#send-selected-game');if(button)button.disabled=true;
 try{
  const result=await fetch('https://api.github.com/repos/JovanyCarlson/Game-Sniper/actions/workflows/manual-discord.yml/dispatches',{
   method:'POST',headers:{'Authorization':'Bearer '+workflowToken,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'},
   body:JSON.stringify({ref:'main',inputs:{selector}}),cache:'no-store'
  });
  if(result.status===401||result.status===403){
   workflowToken='';throw Error('GitHub denied the token. Check that it has Actions: Read and write for only Game-Sniper.');
  }
  if(!result.ok)throw Error('GitHub could not queue the send ('+result.status+'). Check the Actions workflow.');
  showSendStatus('Queued! GitHub Actions will send this game to your private Discord. Check Actions for delivery status.');
 }catch(error){
  if(error instanceof TypeError)throw Error('GitHub request blocked or offline. Check browser network access to api.github.com.');
  throw error;
 }finally{if(button)button.disabled=false;}
}
$('#authorize-send').addEventListener('click',async()=>{
 const token=$('#send-discord-token').value.trim();
 if(!/^(github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{30,})$/.test(token)){
  const looksLikeEncryptionKey=/^[A-Za-z0-9+/]{43}=$/.test(token);
  $('#send-dialog-message').textContent=looksLikeEncryptionKey
   ? 'This looks like your encryption key, not a GitHub token. Keep the encryption key private; create a separate GitHub fine-grained token beginning with github_pat_.'
   : 'Enter a GitHub Personal Access Token starting with github_pat_. Create it with repository access to Game-Sniper and Actions: Read and write. Do NOT use the encryption key or Discord webhook here.';
  return;
 }
 workflowToken=token;$('#send-discord-token').value='';
 try{await sendSelected();}catch(error){$('#send-discord-dialog').classList.remove('hidden');$('#send-dialog-message').textContent=error.message;}
});
$('#cancel-discord').addEventListener('click',()=>{$('#send-discord-token').value='';$('#send-discord-dialog').classList.add('hidden');});
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-send-game]');
 if(b){const game=DB.games.find(g=>g.platform+':'+g.gid===b.dataset.sendGame);requestSend(game);}
 if(e.target.id==='send-selected-game')requestSend(selected);
});
document.addEventListener('click',e=>{let p=e.target.closest('[data-page]');if(p)navigate(p.dataset.page);let o=e.target.closest('[data-open]');if(o){let g=DB.games.find(g=>g.platform+':'+g.gid===o.dataset.open);if(g)modal(g);}const b=e.target.closest('[data-chart-window]');if(b&&selected)modal(selected,b.dataset.chartWindow);});$$('.time-window').forEach(el=>el.addEventListener('change',e=>{windowKey=e.target.value;$$('.time-window').forEach(other=>other.value=windowKey);render()}));$$('#platform-filters button').forEach(el=>el.addEventListener('click',()=>{platform=el.dataset.platform;$$('#platform-filters button').forEach(b=>b.classList.toggle('selected',b===el));render()}));$('#game-search').addEventListener('input',e=>{query=e.target.value.trim().toLowerCase();render()});$('#sort-order').addEventListener('change',e=>{sort=e.target.value;render()});$('#close-modal').addEventListener('click',()=>$('#game-modal').classList.add('hidden'));$('#game-modal').addEventListener('click',e=>{if(e.target.id==='game-modal')$('#game-modal').classList.add('hidden')});document.addEventListener('keydown',e=>{if(e.key==='Escape')$('#game-modal').classList.add('hidden')});$('#reload').addEventListener('click',load);load();setInterval(load,120000);
})();
