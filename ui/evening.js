'use strict';
let eveningProfiles={}, eveningMinutes=60, eveningMood='relax', eveningExclude=[], eveningBusy=false;
function eveningPressed(container, predicate) {
  document.querySelectorAll(container+' button').forEach(b=>b.setAttribute('aria-pressed',String(predicate(b))));
}
function renderEveningPicks(result) {
  const list=$('#evening-results'); list.replaceChildren();
  $('#evening-status').textContent=result.picks.length ? (result.surprise?'Твой случайный выбор на сегодня':`Подходит игр: ${result.matching} · показано ${result.picks.length}`) : !result.ready?'Нет готовых к запуску игр. Установи игру или настрой её запуск в библиотеке.':!result.tagged?'Начни с тегов: укажи настроение и длительность сессии для нескольких игр.':'Совпадений пока нет. Попробуй другое настроение, больше времени или добавь теги другим играм.';
  for(const {game,reason} of result.picks) {
    const row=element('article','','evening-pick');
    const art=element('div','','evening-art'), url=imageURL(game.cover);
    if(url){const img=document.createElement('img');img.src=url;img.alt='';img.onerror=()=>img.remove();art.append(img);}else art.textContent='☾';
    const info=element('div','','evening-pick-info');info.append(element('h3',game.name),element('p',reason,'form-note'));
    const play=featureButton('Играть',async()=>{ $('#evening-dialog').close(); setHero(game); await launch(game); });play.className='primary';play.setAttribute('aria-label','Играть: '+game.name);
    row.append(art,info,play);list.append(row);
  }
}
async function findEvening(surprise=false) {
  if(eveningBusy)return;
  eveningBusy=true;$('#evening-find').disabled=true;$('#evening-surprise').disabled=true;
  document.querySelectorAll('#evening-times button,#evening-moods button').forEach(b=>b.disabled=true);
  $('#evening-status').textContent='Выбираю игры…';
  try {
    const result=await api('eveningPicks',{minutes:eveningMinutes,mood:eveningMood,surprise,exclude:eveningExclude});
    eveningExclude=result.picks.map(p=>p.game.id);renderEveningPicks(result);
  } catch(e) {$('#evening-status').textContent=e.message;}
  finally {eveningBusy=false;$('#evening-find').disabled=false;$('#evening-surprise').disabled=false;document.querySelectorAll('#evening-times button,#evening-moods button').forEach(b=>b.disabled=false);}
}
window.orbitEvening=()=>safeFeature(async()=>{
  eveningProfiles=(await api('eveningInfo')).profiles;
  $('#settings-dialog').close();
  if(!$('#evening-dialog').open)$('#evening-dialog').showModal();
  $('#evening-find').focus();await findEvening();
});
$('#evening-open').onclick=window.orbitEvening;$('#evening-menu').onclick=window.orbitEvening;
$('#evening-times').querySelectorAll('button').forEach(b=>b.onclick=()=>{eveningMinutes=Number(b.dataset.minutes);eveningPressed('#evening-times',x=>x===b);$('#evening-results').replaceChildren();$('#evening-status').textContent='Нажми «Подобрать игры» для новых условий.';});
$('#evening-moods').querySelectorAll('button').forEach(b=>b.onclick=()=>{eveningMood=b.dataset.mood;eveningPressed('#evening-moods',x=>x===b);$('#evening-results').replaceChildren();$('#evening-status').textContent='Нажми «Подобрать игры» для новых условий.';});
$('#evening-find').onclick=()=>findEvening();$('#evening-surprise').onclick=()=>findEvening(true);
function loadEveningProfile() {
  const profile=eveningProfiles[$('#evening-game').value];
  $('#evening-duration').value=String(profile?.minutes || 20);
  eveningPressed('#evening-profile-moods',b=>!!profile?.moods.includes(b.dataset.mood));
  $('#evening-profile-status').textContent=profile?'Теги сохранены. Можно изменить их или выбрать другую игру.':'Теги ещё не заданы. Выбери хотя бы одно настроение.';
  $('#evening-profile-clear').disabled=!profile;
}
$('#evening-edit').onclick=()=>safeFeature(async()=>{
  await refresh();eveningProfiles=(await api('eveningInfo')).profiles;
  const select=$('#evening-game');select.replaceChildren();
  for(const game of [...games].sort((a,b)=>a.name.localeCompare(b.name,'ru')))select.append(new Option(game.name,game.id));
  if(!games.length)return toast('Сначала добавь игру в библиотеку');
  select.value=games.some(g=>g.id===selected?.id)?selected.id:games[0].id;
  loadEveningProfile();$('#evening-profile-dialog').showModal();
});
$('#evening-game').onchange=loadEveningProfile;
$('#evening-profile-moods').querySelectorAll('button').forEach(b=>b.onclick=()=>b.setAttribute('aria-pressed',String(b.getAttribute('aria-pressed')!=='true')));
$('#evening-profile-form').onsubmit=async event=>{
  event.preventDefault();const button=$('#evening-profile-save');if(button.disabled)return;button.disabled=true;
  try {
    const moods=[...$('#evening-profile-moods').querySelectorAll('[aria-pressed=true]')].map(b=>b.dataset.mood);
    const result=await api('eveningProfile',{id:$('#evening-game').value,minutes:Number($('#evening-duration').value),moods});
    eveningProfiles=result.profiles;loadEveningProfile();$('#evening-profile-status').textContent='Теги сохранены. Выбери следующую игру или вернись к подбору.';
    await findEvening();
  }catch(e){$('#evening-profile-status').textContent=e.message;}finally{button.disabled=false;}
};
$('#evening-profile-clear').onclick=()=>safeFeature(async()=>{eveningProfiles=(await api('eveningProfile',{id:$('#evening-game').value,clear:true})).profiles;loadEveningProfile();await findEvening();});
