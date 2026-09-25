const $ = (id) => document.getElementById(id);
const state = {catalog:null, group:'', event:'', kind:'', q:'', page:0, items:[], total:0, hasMore:false, active:0, loading:false};
const favorites = new Set(JSON.parse(localStorage.getItem('hellocolle-favorites') || '[]'));
const esc = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const isRemote = () => Array.isArray(state.catalog?.items);
const media = (id) => isRemote() ? state.catalog.items[id].url : `/media/${id}`;
const thumb = (id) => isRemote() ? `./thumbs/${id}.jpg` : `/thumb/${id}`;
const number = (n) => n.toLocaleString('ja-JP');
const params = () => new URLSearchParams({group:state.group,event:state.event,kind:state.kind,favorites:state.kind==='favorite'?[...favorites].join(','):'',q:state.q,page:String(state.page)});

async function init(){
  try {
    let response = await fetch('/api/catalog');
    if(!response.ok) response = await fetch('./catalog.json');
    state.catalog = await response.json();
    $('rescan').hidden=isRemote();
    renderGroups(); render();
  }
  catch { $('pageTitle').textContent='読み込めませんでした'; $('pageMeta').textContent='サーバーを再起動してください'; }
}
function setGroup(group){state.group=group;state.event='';state.kind='';state.q='';$('search').value='';renderGroups();render();history.replaceState(null,'',location.pathname);}
function renderGroups(){
  const groups=[{name:'すべて',count:state.catalog.total,value:''},...state.catalog.groups.map(g=>({...g,value:g.name}))];
  $('groups').innerHTML=groups.map(g=>`<button class="group ${state.group===g.value?'active':''}" data-group="${esc(g.value)}"><span>${esc(g.name)}</span><span>${number(g.count)}</span></button>`).join('');
  $('mobileGroups').innerHTML=groups.map(g=>`<button class="${state.group===g.value?'active':''}" data-group="${esc(g.value)}">${esc(g.name)}</button>`).join('');
  document.querySelectorAll('[data-group]').forEach(b=>b.onclick=()=>setGroup(b.dataset.group));
  $('totalLabel').textContent=`${number(state.catalog.total)} ファイル`;
  $('groupCount').textContent=state.catalog.groups.length;
}
function render(){
  $('pageTitle').textContent=state.event || state.group || 'すべてのコレクション';
  $('eyebrow').textContent=state.event ? state.group : state.group ? 'GROUP COLLECTION' : 'ALL COLLECTION';
  $('backButton').hidden=!state.event;
  const events=state.catalog.events.filter(e=>!state.group||e.group===state.group).filter(e=>!state.q||(e.group+' '+e.name).toLocaleLowerCase().includes(state.q.toLocaleLowerCase()));
  const eventMode=!state.event && state.kind!=='favorite' && !state.q;
  $('events').hidden=!eventMode;
  $('fileControls').hidden=eventMode;
  $('files').hidden=eventMode;
  $('sectionTitle').textContent=eventMode?'イベント':'ファイル';
  $('pageMeta').textContent=eventMode?`${number(events.length)} イベント · ${number(events.reduce((n,e)=>n+e.count,0))} ファイル`:'';
  if(eventMode){
    $('events').innerHTML=events.map(e=>`<button class="event" data-event="${esc(e.name)}" data-group="${esc(e.group)}"><span class="folder-icon" aria-hidden="true">▰</span><span class="eventbody"><span class="eventname">${esc(e.name)}</span><span class="eventgroup">${esc(e.group)}</span></span><span class="eventmeta">写真 ${number(e.photos)} · 動画 ${number(e.videos)}</span><span class="eventcount">${number(e.count)} 件</span><span class="event-chevron" aria-hidden="true">›</span></button>`).join('');
    document.querySelectorAll('.event').forEach(b=>b.onclick=()=>{state.group=b.dataset.group;state.event=b.dataset.event;state.kind='';renderGroups();render();window.scrollTo(0,0);});
    $('empty').hidden=events.length>0;
    $('loadMore').hidden=true;
  } else {document.querySelectorAll('.segments button').forEach(b=>b.classList.toggle('active',b.dataset.kind===state.kind));loadItems(true);}
}
async function loadItems(reset=false){
  if(state.loading)return;
  if(reset){state.page=0;state.items=[];$('files').innerHTML='';}
  state.loading=true;
  const request=params().toString();
  try{
    let data;
    if(isRemote()){
      const chosen=state.kind==='favorite'?new Set(favorites):null;
      const matches=state.catalog.items.filter(x=>(!state.group||x.group===state.group)&&(!state.event||x.event===state.event)&&(!state.kind||state.kind==='favorite'||x.kind===state.kind)&&(chosen===null||chosen.has(x.id))&&(!state.q||(x.group+' '+x.event+' '+x.name).toLocaleLowerCase().includes(state.q.toLocaleLowerCase())));
      data={items:matches.slice(state.page*72,(state.page+1)*72),total:matches.length,hasMore:(state.page+1)*72<matches.length};
    }else data=await(await fetch('/api/items?'+request)).json();
    if(request!==params().toString())return;
    state.total=data.total;state.hasMore=data.hasMore;
    const newItems=data.items;
    state.items.push(...newItems);
    $('files').insertAdjacentHTML('beforeend',newItems.map(x=>`<button class="file" data-id="${x.id}" title="${esc(x.name)}"><span class="file-image"><img src="${thumb(x.id)}" loading="lazy" alt="">${x.kind==='video'?'<span class="video-badge">▶ 動画</span>':''}${favorites.has(x.id)?'<span class="fav-badge">★</span>':''}</span><span class="file-caption"><span class="file-badges">${x.rarity?`<b class="rarity">★${x.rarity}</b>`:''}<span>${x.kind==='video'?'動画':'写真'}</span></span><strong class="file-member">${esc(x.member||x.name)}</strong></span></button>`).join(''));
    document.querySelectorAll('.file:not([data-ready])').forEach(b=>{b.dataset.ready='1';b.onclick=()=>openViewer(Number(b.dataset.id));});
    $('fileCount').textContent=`${number(state.total)} 件`;
    $('empty').hidden=state.items.length>0 || data.hasMore;
    $('loadMore').hidden=!data.hasMore;
  }catch{$('fileCount').textContent='読み込みに失敗しました';}
  finally{state.loading=false;}
}
function openViewer(id){const index=state.items.findIndex(x=>x.id===id);if(index<0)return;state.active=index;showViewer();$('viewer').showModal();}
function showViewer(){
  const x=state.items[state.active];if(!x)return;
  $('viewerName').textContent=x.name;
  $('fullFilename').textContent=x.name+x.ext;
  $('filenameDetails').open=false;
  $('viewerMeta').textContent=`${x.group} / ${x.event} · ${x.kind==='video'?'動画':'写真'} · ${(x.size/1024/1024).toFixed(1)} MB${x.kind==='video'&&x.rarity===5?' · 音量8%':''}`;
  const previous=$('viewerMedia').querySelector('video');if(previous){previous.pause();previous._audioContext?.close();}
  $('viewerMedia').replaceChildren();
  const el=document.createElement(x.kind==='video'?'video':'img');
  if(x.kind==='video'&&x.rarity===5&&!(isRemote()&&x.url.includes('/releases/')))el.crossOrigin='anonymous';
  if(x.kind==='video'){
    const source=document.createElement('source');source.src=media(x.id);source.type='video/mp4';el.append(source);
    el.controls=true;el.autoplay=true;el.playsInline=true;el.preload='metadata';
    if(x.rarity===5){
      el.volume=0.08;
      if(!(isRemote()&&x.url.includes('/releases/'))){
        try{const context=new (window.AudioContext||window.webkitAudioContext)();const source=context.createMediaElementSource(el);const gain=context.createGain();gain.gain.value=0.08;source.connect(gain).connect(context.destination);context.resume();el.volume=1;el._audioContext=context;}
        catch{el.volume=0.08;}
      }
    }
  }
  else{el.src=media(x.id);el.alt=x.name;}
  el.addEventListener('error',()=>{
    const message=document.createElement('p');message.className='media-error';message.textContent='原本を読み込めませんでした。少し時間をおいて開き直してください。';
    $('viewerMedia').replaceChildren(message);
  });
  $('viewerMedia').append(el);
  $('download').href=media(x.id);$('download').download=x.name+(x.ext|| (x.kind==='video'?'.mp4':'.jpg'));
  $('favorite').textContent=favorites.has(x.id)?'★':'☆';$('favorite').classList.toggle('selected',favorites.has(x.id));
  $('favorite').setAttribute('aria-label',favorites.has(x.id)?'お気に入りから削除':'お気に入りに追加');
  $('viewerPosition').textContent=`${number(state.active+1)} / ${number(state.items.length)}`;
  $('prev').disabled=state.active===0;$('next').disabled=state.active===state.items.length-1&&!state.hasMore;
}
async function move(delta){let next=state.active+delta;if(next>=state.items.length&&state.hasMore){state.page++;await loadItems();}if(next>=0&&next<state.items.length){state.active=next;showViewer();}}
function closeViewer(){const v=$('viewerMedia').querySelector('video');if(v){v.pause();v._audioContext?.close();}$('viewer').close();$('viewerMedia').replaceChildren();}
let searchTimer;$('search').addEventListener('input',e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.q=e.target.value.trim();render();},250);});
$('backButton').onclick=()=>{state.event='';state.kind='';render();};
document.querySelectorAll('.segments button').forEach(b=>b.onclick=()=>{state.kind=b.dataset.kind;render();});
$('loadMore').onclick=()=>{state.page++;loadItems();};
$('close').onclick=closeViewer;$('prev').onclick=()=>move(-1);$('next').onclick=()=>move(1);
$('favorite').onclick=()=>{const id=state.items[state.active].id;favorites.has(id)?favorites.delete(id):favorites.add(id);localStorage.setItem('hellocolle-favorites',JSON.stringify([...favorites]));showViewer();const card=document.querySelector(`.file[data-id="${id}"] .file-image`);if(card){card.querySelector('.fav-badge')?.remove();if(favorites.has(id))card.insertAdjacentHTML('beforeend','<span class="fav-badge">★</span>');}};
$('viewer').addEventListener('cancel',e=>{e.preventDefault();closeViewer();});
document.addEventListener('keydown',e=>{if(e.key==='/'&&document.activeElement!==$('search')&&!$('viewer').open){e.preventDefault();$('search').focus();}if($('viewer').open){if(e.key==='ArrowLeft')move(-1);if(e.key==='ArrowRight')move(1);}});
$('rescan').onclick=async()=>{const b=$('rescan');b.disabled=true;b.textContent='…';try{await fetch('/api/rescan');await init();}finally{b.disabled=false;b.textContent='↻';}};
init();
