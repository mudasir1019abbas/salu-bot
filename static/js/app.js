const $=s=>document.querySelector(s);
const msgsEl=$('#messages'),input=$('#input'),sendBtn=$('#sendBtn');
const storageKey='unibotChats:'+document.body.dataset.userId;
let chats=[];
try{chats=JSON.parse(localStorage.getItem(storageKey)||'[]');if(!Array.isArray(chats))chats=[];}catch(e){chats=[];}
let current=null,busy=false,sound=localStorage.sound!=='off';
const save=()=>localStorage.setItem(storageKey,JSON.stringify(chats));
const icons=()=>window.lucide&&lucide.createIcons();

function newChat(){current={id:Date.now(),title:'New chat',messages:[]};chats.unshift(current);save();render();}
function render(){
  msgsEl.innerHTML='';
  if(!current.messages.length) addBubble('bot',"👋 Hi! I'm **SALUBOT**, your 24/7 campus assistant. Ask me about courses, exams, grading, campus places or assignments.",false);
  current.messages.forEach(m=>addBubble(m.role==='user'?'user':'bot',m.content,false));
  renderHistory();
}
function renderHistory(){
  const ul=$('#historyList');ul.innerHTML='';
  chats.forEach(c=>{const li=document.createElement('li');li.className='hist-row';const b=document.createElement('button');
    b.className='hist'+(c===current?' active':'');b.textContent=c.title;
    b.onclick=()=>{current=c;render();closeSidebar();};li.appendChild(b);ul.appendChild(li);});
  chats.forEach((c,index)=>{
    const row=ul.children[index];
    const button=document.createElement('button');
    button.type='button';
    button.className='hist-delete';
    button.disabled=busy;
    button.title=busy?'Wait for the current reply to finish':'Delete chat: '+c.title;
    button.setAttribute('aria-label','Delete chat: '+c.title);
    button.innerHTML='<i data-lucide="trash-2"></i>';
    button.onclick=()=>deleteChat(c.id);
    row.appendChild(button);
  });
  icons();
}
function deleteChat(chatId){
  if(busy)return;
  const index=chats.findIndex(c=>String(c.id)===String(chatId));
  if(index<0||!confirm('Delete this conversation? This cannot be undone.'))return;
  const wasCurrent=chats[index]===current;
  chats.splice(index,1);
  if(wasCurrent)current=chats[index]||chats[index-1]||null;
  save();
  if(current)render();else newChat();
}
function md(el,text){
  el.innerHTML=marked.parse(text);
  el.querySelectorAll('pre code').forEach(c=>{hljs.highlightElement(c);
    const btn=document.createElement('button');btn.className='copy-btn';btn.textContent='Copy';
    btn.onclick=()=>{navigator.clipboard.writeText(c.innerText);btn.textContent='Copied!';setTimeout(()=>btn.textContent='Copy',1500)};
    c.parentElement.appendChild(btn);});
  if(window.renderMathInElement) renderMathInElement(el,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false},{left:'\\(',right:'\\)',display:false},{left:'\\[',right:'\\]',display:true}],throwOnError:false});
}
function addBubble(role,text,scroll=true){
  const d=document.createElement('div');d.className='msg '+role+(role==='bot'?' glass prose':'');
  role==='user'?d.textContent=text:md(d,text);msgsEl.appendChild(d);
  if(scroll) msgsEl.scrollTop=msgsEl.scrollHeight;return d;
}
function pop(f=600){if(!sound)return;try{const a=new AudioContext(),o=a.createOscillator(),g=a.createGain();
  o.frequency.value=f;o.type='sine';g.gain.setValueAtTime(.15,a.currentTime);g.gain.exponentialRampToValueAtTime(.001,a.currentTime+.15);
  o.connect(g).connect(a.destination);o.start();o.stop(a.currentTime+.15);}catch(e){}}

async function ask(text){
  if(busy||!text.trim())return;busy=true;sendBtn.disabled=true;
  const history=current.messages.slice();
  current.messages.push({role:'user',content:text});
  if(current.title==='New chat'){current.title=text.slice(0,40);}
  save();renderHistory();addBubble('user',text);pop(700);
  const bot=addBubble('bot','');bot.innerHTML='<div class="typing"><span></span><span></span><span></span></div>';
  let full='',srcs=[];
  try{
    const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':window.unibotCsrfToken},body:JSON.stringify({message:text,history})});
    if(!res.ok){const j=await res.json().catch(()=>({}));throw new Error(j.error||('Request failed ('+res.status+')'));}
    const reader=res.body.getReader(),dec=new TextDecoder();let buf='';
    while(true){const {done,value}=await reader.read();if(done)break;buf+=dec.decode(value,{stream:true});
      const parts=buf.split('\n\n');buf=parts.pop();
      for(const p of parts){const line=p.replace(/^data: /,'');if(line==='[DONE]')continue;
        const j=JSON.parse(line);if(j.error)throw new Error(j.error);if(j.sources){srcs=j.sources;continue;}full+=j.text;md(bot,full);msgsEl.scrollTop=msgsEl.scrollHeight;}}
    if(srcs.length){const d=document.createElement('div');d.className='sources';d.textContent='📘 Sources: '+srcs.join(', ');bot.appendChild(d);}
    current.messages.push({role:'assistant',content:full});save();pop(500);
  }catch(e){bot.innerHTML='<span class="error">⚠️ '+e.message+'</span>';current.messages.pop();save();}
  busy=false;sendBtn.disabled=false;renderHistory();
}
function send(){const t=input.value;input.value='';resize();ask(t);}
function resize(){input.style.height='auto';input.style.height=input.scrollHeight+'px';$('#counter').textContent=input.value.length+' / 4000';}
function download(type){
  const name='salubot-chat-'+current.id;let blob;
  if(type==='json')blob=new Blob([JSON.stringify(current,null,2)],{type:'application/json'});
  else blob=new Blob([current.messages.map(m=>(m.role==='user'?'You':'SALUBOT')+': '+m.content).join('\n\n')],{type:'text/plain'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name+'.'+type;a.click();
}
function closeSidebar(){$('#sidebar').classList.add('-translate-x-full');$('#overlay').classList.add('hidden');}
function setThemeIcon(){$('#themeBtn').innerHTML='<i data-lucide="'+(document.documentElement.classList.contains('dark')?'sun':'moon')+'"></i>';icons();}
function setSoundIcon(){$('#soundBtn').innerHTML='<i data-lucide="'+(sound?'volume-2':'volume-x')+'"></i>';icons();}

input.addEventListener('input',resize);
input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
sendBtn.onclick=send;
document.querySelectorAll('.pill').forEach(p=>p.onclick=()=>ask(p.textContent));
document.querySelectorAll('.shortcut').forEach(p=>p.onclick=()=>{ask(p.dataset.q);closeSidebar();});
$('#newChat').onclick=()=>{newChat();closeSidebar();};
$('#clearBtn').onclick=()=>{if(confirm('Clear this conversation?')){current.messages=[];current.title='New chat';save();render();}};
$('#regenBtn').onclick=()=>{if(busy)return;const m=current.messages;
  if(m.length&&m[m.length-1].role==='assistant')m.pop();const last=m.pop();if(last){save();render();ask(last.content);}};
$('#dlTxt').onclick=()=>download('txt');$('#dlJson').onclick=()=>download('json');
$('#themeBtn').onclick=()=>{const d=document.documentElement.classList.toggle('dark');localStorage.theme=d?'dark':'light';setThemeIcon();};
$('#soundBtn').onclick=()=>{sound=!sound;localStorage.sound=sound?'on':'off';setSoundIcon();};
$('#menuBtn').onclick=()=>{$('#sidebar').classList.remove('-translate-x-full');$('#overlay').classList.remove('hidden');};
$('#overlay').onclick=closeSidebar;

const params=new URLSearchParams(window.location.search);
const requestedChatId=params.get('chat');
current=chats.find(c=>String(c.id)===requestedChatId)||chats[0]||null;
if(!current)newChat();else render();
setThemeIcon();setSoundIcon();icons();
const shortcutQuestion=params.get('q');
if(shortcutQuestion||requestedChatId){window.history.replaceState({},'',window.location.pathname);}
if(shortcutQuestion)ask(shortcutQuestion);
