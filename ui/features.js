'use strict';
let featureState = {}, featureBusy = false, savesGameId = null, keyboardTarget = null, keyboardRussian = false;
const featureJobs = new Map();
function element(tag, text, className='') { const el=document.createElement(tag); el.textContent=text; el.className=className; return el; }
function featureButton(text, callback) { const button=element('button',text,'secondary'); button.onclick=()=>safeFeature(callback); return button; }
async function safeFeature(callback) { try { return await callback(); } catch(error) { toast(error.message); } }
async function featureInfo() { featureState=await api('features'); return featureState; }
async function background(action, payload={}, done) {
  const result=await api(action,payload);
  featureJobs.set(result.job, {done, action});
  return result;
}
async function setupFeatureSignals() {
  if(!bridge || !bridge.serviceFinished) return;
  bridge.serviceFinished.connect(raw=>{
    const event=JSON.parse(raw), job=featureJobs.get(event.job);
    featureJobs.delete(event.job);
    if(event.error) {
      toast(event.error);
      if(event.kind==='syncSaves' || event.kind==='beforeLaunch' || event.kind==='afterGame') {
        $('#saves-status').textContent=event.error;
        $('#saves-conflict').hidden=!event.conflict;
      }
      if(['checkUpdate','downloadUpdate'].includes(event.kind)) $('#update-status').textContent=event.error;
    } else {
      job?.done?.(event.result);
      if(event.kind==='afterGame') toast('Сохранения после игры синхронизированы');
    }
    featureBusy=false; updateFeatureButtons();
  });
  bridge.sessionChanged.connect(raw=>toast(JSON.parse(raw).message));
}
function updateFeatureButtons() { for(const id of ['update-check','update-download','saves-sync','saves-config','saves-history']) $('#'+id).disabled=featureBusy; }
async function showFeatures(panel='downloads') {
  await featureInfo();
  $('#settings-dialog').close();
  if(!$('#features-dialog').open) $('#features-dialog').showModal();
  $('#orbit-version').textContent='Orbit '+featureState.version;
  $('#console-enabled').checked=featureState.consoleMode;
  $('#autostart-enabled').checked=featureState.autostart;
  $('#guide-status').textContent=featureState.guideError ? 'Guide недоступен: '+featureState.guideError : '';
  [$('#limit-down').value,$('#limit-up').value]=featureState.limits;
  switchFeature(panel);
}
function switchFeature(panel) {
  document.querySelectorAll('[data-panel]').forEach(el=>el.hidden=el.dataset.panel!==panel);
  document.querySelectorAll('[data-feature]').forEach(el=>el.classList.toggle('active',el.dataset.feature===panel));
  if(panel==='downloads') safeFeature(refreshTorrents);
}
$('#features-button').onclick=()=>safeFeature(()=>showFeatures());
document.querySelectorAll('[data-feature]').forEach(el=>el.onclick=()=>switchFeature(el.dataset.feature));
async function pickInto(selector, action='chooseDirectory') { const result=await api(action); if(result.path) $(selector).value=result.path; }
$('#torrent-file').onclick=()=>safeFeature(()=>pickInto('#torrent-source','chooseTorrent'));
$('#torrent-folder').onclick=()=>safeFeature(()=>pickInto('#torrent-path'));
$('#torrent-add').onclick=()=>safeFeature(async()=>{ await api('torrentAdd',{source:$('#torrent-source').value.trim(),path:$('#torrent-path').value}); $('#torrent-source').value=''; await refreshTorrents(); });
$('#limits-save').onclick=()=>safeFeature(async()=>{ await api('torrentLimits',{download:$('#limit-down').value,upload:$('#limit-up').value}); toast('Ограничения скорости сохранены'); });
async function refreshTorrents() {
  const result=await api('torrentStatus'), list=$('#torrent-list');
  // Keep focus stable while updating download statistics for gamepad users.
  const focus=document.activeElement?.dataset.downloadAction, tid=document.activeElement?.dataset.tid;
  list.replaceChildren();
  if(!result.items.length) list.append(element('p','Очередь пока пуста. Добавь magnet-ссылку или .torrent.','form-note'));
  for(const item of result.items) {
    const row=element('article','','download-row');
    row.append(element('h4',item.name));
    const progress=document.createElement('progress'); progress.max=100; progress.value=item.progress; progress.setAttribute('aria-label','Прогресс загрузки'); row.append(progress);
    row.append(element('p',`${item.progress}% · ${Math.round(item.speed/1024)} КиБ/с · ${item.peers} пиров · ${item.error || (item.paused ? 'Пауза' : item.complete ? 'Готово · раздаётся' : item.queued ? 'В очереди' : 'Загружается')}`));
    const actions=element('div','','download-actions');
    for(const [label, action, fn] of [
      [item.paused?'Продолжить':'Пауза','toggle',()=>api('torrentAction',{id:item.id,action:item.paused?'resume':'pause'}).then(refreshTorrents)],
      ['Открыть папку','folder',()=>api('openFolder',{path:item.path})],
      ['Убрать из очереди','remove',()=>confirmAction('Убрать загрузку?','Скачанные файлы останутся на диске.',async()=>{await api('torrentAction',{id:item.id,action:'remove'}); await refreshTorrents();})]
    ]) { const button=featureButton(label,fn); button.dataset.downloadAction=action; button.dataset.tid=item.id; actions.append(button); }
    row.append(actions); list.append(row);
  }
  if(tid) [...list.querySelectorAll('button')].find(b=>b.dataset.tid===tid && b.dataset.downloadAction===focus)?.focus({preventScroll:true});
  if(result.errorMessage) list.append(element('p',result.errorMessage));
}
setInterval(()=>{ if(bridge && $('#features-dialog').open && !$('[data-panel="downloads"]').hidden && !$('#action-dialog').open) safeFeature(refreshTorrents); },2500);
$('#download-add-game').onclick=()=>{ $('#features-dialog').close(); openAdd(); toast('Выбери установщик или исполняемый файл скачанной игры'); };
$('#update-check').onclick=()=>safeFeature(async()=>{
  featureBusy=true; updateFeatureButtons(); $('#update-status').textContent='Проверяю релизы GitHub…';
  try { await background('checkUpdate',{},result=>{
    $('#update-status').textContent=result.available ? 'Доступна версия '+result.version : 'Установлена последняя версия';
    $('#update-notes').textContent=result.notes;
    $('#update-download').hidden=!result.available;
  }); } catch(e) {featureBusy=false; updateFeatureButtons(); throw e;}
});
$('#update-download').onclick=()=>safeFeature(async()=>{
  featureBusy=true; updateFeatureButtons(); $('#update-status').textContent='Скачиваю пакет и проверяю SHA-256…';
  try { await background('downloadUpdate',{},result=>{ $('#update-status').textContent='Пакет проверен. Запускаю установку…'; $('#update-download').hidden=true; safeFeature(async()=>{try {await api('installUpdate');} catch(e) {$('#update-install').hidden=false;throw e;}}); }); }
  catch(e) {featureBusy=false; updateFeatureButtons(); throw e;}
});
function confirmAction(title, description, action) {
  $('#action-title').textContent=title; $('#action-description').textContent=description;
  $('#action-confirm').onclick=()=>safeFeature(async()=>{ await action(); $('#action-dialog').close(); });
  $('#action-dialog').showModal(); $('#action-dialog .secondary').focus();
}
$('#update-install').onclick=()=>confirmAction('Установить обновление?','Orbit закроется для установки. На Linux появится системный запрос подтверждения.',()=>api('installUpdate'));
$('#console-enabled').onchange=()=>safeFeature(async()=>{await api('consoleSettings',{enabled:$('#console-enabled').checked}); toast('Настройка консольного режима сохранена');});
$('#autostart-enabled').onchange=()=>safeFeature(async()=>{await api('consoleSettings',{autostart:$('#autostart-enabled').checked}); toast('Настройка автозапуска сохранена');});
document.querySelectorAll('[data-power]').forEach(button=>button.onclick=()=>confirmAction(button.dataset.power==='suspend'?'Перевести компьютер в сон?':'Выключить компьютер?','Сохрани работу в других приложениях перед продолжением.',()=>api('power',{action:button.dataset.power})));
window.prepareRunner=async game=>{
  try { const info=await featureInfo(); const select=$('#game-proton'); select.replaceChildren(new Option('Выбери установленный Proton',''));
    for(const version of info.protons) select.add(new Option(version.name,version.path));
    $('#runner-label').hidden=navigator.userAgent.includes('Windows');
    $('#game-runner').value=game?.runner || 'native'; select.value=game?.proton || '';
    $('#proton-label').hidden=$('#game-runner').value!=='proton';
  } catch(e) {toast(e.message);}
};
$('#game-runner').onchange=()=>{$('#proton-label').hidden=$('#game-runner').value!=='proton';};
async function showSaves() {
  if(!selected) return;
  await featureInfo(); savesGameId=selected.id;
  const profile=featureState.saves[savesGameId];
  $('#saves-title').textContent='Сохранения · '+selected.name;
  $('#saves-enabled').checked=!!profile;
  $('#saves-key').value=profile?.key || (selected.source==='steam' ? selected.id : selected.name.toLowerCase().replace(/[^a-z0-9_-]+/g,'-').replace(/^-|-$/g,'') || 'my-game');
  $('#saves-local').value=profile?.local || ''; $('#saves-cloud').value=profile?.cloud || '';
  $('#saves-status').textContent=''; $('#saves-conflict').hidden=true; $('#save-history-list').replaceChildren();
  $('#saves-dialog').showModal();
}
$('#saves-button').onclick=()=>safeFeature(showSaves);
$('#saves-local-browse').onclick=()=>safeFeature(()=>pickInto('#saves-local'));
$('#saves-cloud-browse').onclick=()=>safeFeature(()=>pickInto('#saves-cloud'));
$('#saves-config').onclick=()=>safeFeature(async()=>{
  await api('saveProfile',{id:savesGameId,enabled:$('#saves-enabled').checked,key:$('#saves-key').value,local:$('#saves-local').value,cloud:$('#saves-cloud').value});
  $('#saves-status').textContent='Настройки сохранены. Нажми «Синхронизировать», чтобы проверить первую копию.';
});
async function syncSaves(choice='', snapshot='') {
  featureBusy=true; updateFeatureButtons(); $('#saves-status').textContent='Проверяю сохранения…';
  try {await background('syncSaves',{id:savesGameId,choice,snapshot},result=>{$('#saves-status').textContent=result.message; $('#saves-conflict').hidden=true; renderSaveHistory(result.history);});}
  catch(e) {featureBusy=false; updateFeatureButtons(); throw e;}
}
$('#saves-sync').onclick=()=>safeFeature(()=>syncSaves());
$('#saves-local-wins').onclick=()=>confirmAction('Использовать сохранения компьютера?','Текущая версия будет опубликована в папке облака. Предыдущие копии останутся в истории.',()=>syncSaves('local'));
$('#saves-cloud-wins').onclick=()=>confirmAction('Восстановить облачную версию?','Orbit сначала создаст локальную резервную копию текущих файлов.',()=>syncSaves('cloud'));
function renderSaveHistory(history) {
  const list=$('#save-history-list'); list.replaceChildren();
  if(!history?.length) list.append(element('p','В облаке пока нет версий.'));
  for(const version of history || []) {
    const row=element('div','','download-row'); row.append(element('p',new Date(version.time*1000).toLocaleString('ru-RU')+' · '+Object.keys(version.files).length+' файлов'));
    row.append(featureButton('Восстановить эту версию',()=>confirmAction('Восстановить сохранения?','Текущие файлы сначала попадут в локальную резервную копию.',()=>syncSaves('cloud',version.id)))); list.append(row);
  }
}
$('#saves-history').onclick=()=>safeFeature(()=>background('saveHistory',{id:savesGameId},result=>renderSaveHistory(result.history)));
window.orbitRunningMenu=async()=>{
  await safeFeature(async()=>{await featureInfo(); const list=$('#running-list'); list.replaceChildren();
    if(!featureState.sessions.length) list.append(element('p','Сейчас нет игр, запущенных через Orbit.'));
    for(const session of featureState.sessions) {
      const row=element('div','','download-row'); row.append(element('h3',session.name));
      row.append(featureButton('Вернуться в игру',async()=>{await api('resumeGame',{id:session.id}); $('#running-dialog').close();}));
      row.append(featureButton('Завершить игру…',()=>confirmAction('Завершить '+session.name+'?','Несохранённый прогресс может быть потерян.',()=>api('stopGame',{id:session.id})))); list.append(row);
    }
    if(!$('#running-dialog').open) $('#running-dialog').showModal();
  });
};
$('#running-button').onclick=$('#console-running').onclick=()=>window.orbitRunningMenu();
function keyboardLayout() {
  const keys=$('#keyboard-keys'); keys.replaceChildren();
  const rows=keyboardRussian ? ['1234567890','йцукенгшщзхъ','фывапролджэ','ячсмитьбю'] : ['1234567890','qwertyuiop','asdfghjkl','zxcvbnm'];
  for(const row of rows) { const line=element('div','','keyboard-row'); for(const key of row) line.append(featureButton(key,()=>typeVirtual(key))); keys.append(line); }
  const controls=element('div','','keyboard-row');
  controls.append(featureButton('Пробел',()=>typeVirtual(' ')),featureButton('⌫',()=>typeVirtual('',true)),featureButton('RU / EN',()=>{keyboardRussian=!keyboardRussian; keyboardLayout();}),featureButton('⇧',()=>{keys.querySelectorAll('.keyboard-row:not(:last-child) button').forEach(b=>{b.textContent=b.textContent===b.textContent.toLowerCase()?b.textContent.toUpperCase():b.textContent.toLowerCase(); b.onclick=()=>typeVirtual(b.textContent);});}),featureButton('Готово',()=>$('#keyboard-dialog').close()));
  keys.append(controls);
}
function typeVirtual(text, backspace=false) {
  if(!keyboardTarget) return;
  const target=keyboardTarget, start=target.selectionStart ?? target.value.length, end=target.selectionEnd ?? start;
  const from=backspace && start===end ? Math.max(0,start-1) : start;
  target.value=target.value.slice(0,from)+text+target.value.slice(end);
  target.setSelectionRange?.(from+text.length,from+text.length);
  target.dispatchEvent(new Event('input',{bubbles:true}));
  $('#keyboard-preview').textContent=target.value;
}
window.orbitKeyboard=target=>{ keyboardTarget=target; $('#keyboard-preview').textContent=target.value; keyboardLayout(); $('#keyboard-dialog').showModal(); };
$('#keyboard-dialog').addEventListener('close',()=>keyboardTarget?.focus());
$('#keyboard-open').onclick=()=>{ $('#features-dialog').close(); window.orbitKeyboard($('#search')); };
const featureSignalTimer=setInterval(()=>{if(bridge){clearInterval(featureSignalTimer); setupFeatureSignals();}},100);
