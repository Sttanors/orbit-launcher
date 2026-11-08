'use strict';
const $ = s => document.querySelector(s);
let bridge, games = [], selected = null, tab = 'all', source = 'all', visible = [], toastTimer, launching = false, accounts = [], activeAccount = '', editingId = null, steamEditingId = null, pendingSwitchId = null, skipShaderPrecache = false;
const api = (action, payload = {}) => new Promise((resolve, reject) => {
  if (!bridge) return reject(new Error('Нет соединения с приложением. Запусти launcher.py.'));
  bridge.request(action, JSON.stringify(payload), raw => {
    try { const result = JSON.parse(raw); result.error ? reject(new Error(result.error)) : resolve(result); }
    catch (error) { reject(error); }
  });
});
function toast(message) {
  const popup = $('#toast');
  popup.textContent = message;
  if(popup.showPopover) { if(popup.matches(':popover-open')) popup.hidePopover(); popup.showPopover(); }
  popup.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { popup.classList.remove('visible'); if(popup.matches(':popover-open')) popup.hidePopover(); }, 4500);
}
function imageURL(value) { try { const u = new URL(value); return u.protocol === 'file:' ? u.href : ''; } catch { return ''; } }
function setHero(game) {
  selected = game;
  $('#hero-name').textContent = game ? game.name : 'Вечер. Время играть.';
  const image = imageURL(game?.hero || game?.cover);
  $('#hero-art').style.backgroundImage = image ? `url(${JSON.stringify(image)})` : '';
  $('#hero-tags').replaceChildren();
  if (game) for (const text of [game.source === 'steam' ? 'STEAM' : 'МОЯ ИГРА', game.needsSetup ? 'НУЖНА НАСТРОЙКА' : game.installed ? 'ГОТОВА К ЗАПУСКУ' : 'НЕДОСТУПНА ЛОКАЛЬНО']) {
    const tag = document.createElement('span'); tag.textContent = text; $('#hero-tags').append(tag);
  }
  $('#hero-description').textContent = game ? (game.needsSetup ? 'Игра скачана и добавлена. Выбери файл запуска в параметрах; установщик или архив сначала нужно установить или распаковать.' : game.installed ? 'Возвращайся туда, где начинается приключение.' : game.source === 'steam' ? 'Диск с игрой недоступен или игра не установлена. Открой Steam, чтобы проверить.' : 'Файл игры недоступен. Проверь подключение диска.') : 'Все твои миры — в одном месте. Добавь первую игру.';
  $('#play-label').textContent = game ? (game.needsSetup ? 'Настроить запуск' : game.installed || game.source === 'local' ? 'Играть' : 'Открыть в Steam') : 'Добавить игру';
  $('#favorite').hidden = !game;
  $('#favorite').textContent = game?.favorite ? '★' : '☆';
  $('#favorite').classList.toggle('favorited', !!game?.favorite);
  $('#favorite').setAttribute('aria-label', game?.favorite ? 'Убрать из избранного' : 'В избранное');
  $('#saves-button').hidden = !game;
  $('#remove').hidden = game?.source !== 'local';
  $('#edit').hidden = !game;
  $('#hero-counter').textContent = game ? `${visible.findIndex(g => g.id === game.id) + 1} / ${visible.length} в этой коллекции` : 'Твоя библиотека начинается здесь';
  document.querySelectorAll('.game').forEach(card => { const active = card.dataset.id === game?.id; card.classList.toggle('selected', active); card.setAttribute('aria-pressed', String(active)); });
}
function render(preferred) {
  const query = $('#search').value.trim().toLocaleLowerCase();
  visible = games.filter(g => (!query || g.name.toLocaleLowerCase().includes(query)) && (tab !== 'favorites' || g.favorite) && (tab !== 'recent' || g.lastPlayed) && (source === 'all' || source === 'installed' ? source !== 'installed' || g.installed : g.source === source));
  visible.sort((a,b) => ($('#sort').value === 'recent' || tab === 'recent' ? b.lastPlayed - a.lastPlayed : 0) || a.name.localeCompare(b.name, 'ru'));
  $('#section-title').firstChild.textContent = ({all:'Все игры ', favorites:'Избранное ', recent:'Недавние '})[tab];
  $('#count').textContent = visible.length;
  $('#empty').hidden = visible.length > 0;
  $('#grid').replaceChildren();
  visible.forEach(game => {
    const card = document.createElement('button'); card.className = 'game'; card.dataset.id = game.id; card.setAttribute('role','listitem'); card.setAttribute('aria-label', game.name + (game.installed ? ', установлена' : ', недоступна локально'));
    const cover = document.createElement('div'); cover.className = 'cover';
    const hash = [...game.name].reduce((h,c) => h + c.charCodeAt(0),0); cover.style.setProperty('--card-color', `hsl(${hash % 360} 20% 25%)`);
    const monogram = document.createElement('span'); monogram.className = 'cover-monogram'; monogram.textContent = game.name.slice(0,1).toUpperCase(); cover.append(monogram);
    const fallback = document.createElement('span'); fallback.className = 'cover-name'; fallback.textContent = game.name; cover.append(fallback);
    const image = imageURL(game.cover);
    if (image) { const img = document.createElement('img'); img.src = image; img.alt = ''; img.loading = 'lazy'; img.onload = () => { fallback.hidden = true; monogram.hidden = true; }; img.onerror = () => img.remove(); cover.append(img); }
    const badge = document.createElement('span'); badge.className = 'source-badge'; badge.textContent = game.source === 'steam' ? 'STEAM' : 'LOCAL'; cover.append(badge);
    if (game.favorite) { const fav = document.createElement('span'); fav.className = 'favorite-badge'; fav.textContent = '★'; cover.append(fav); }
    const play = document.createElement('span'); play.className = 'cover-play'; play.textContent = '▶'; cover.append(play);
    const name = document.createElement('div'); name.className = 'game-name'; name.textContent = game.name;
    const status = document.createElement('div'); status.className = 'game-status' + (game.installed ? ' installed' : ''); const dot = document.createElement('i'); status.append(dot, document.createTextNode(game.needsSetup ? 'Настроить запуск' : game.installed ? 'Установлена' : 'Недоступна локально'));
    card.append(cover, name, status);
    card.onclick = () => setHero(game); card.ondblclick = () => launch(game); card.onfocus = () => setHero(game);
    $('#grid').append(card);
  });
  setHero(visible.find(g => g.id === preferred) || visible.find(g => g.id === selected?.id) || visible[0] || null);
  $('#status').textContent = `${games.length} в библиотеке · ${games.filter(g => g.installed).length} установлено`;
}
async function refresh() { try { const r = await api('library'); games = r.games; accounts = r.accounts || []; activeAccount = r.activeAccount || ''; if(r.platform === 'windows') { $('#executable-help').textContent = 'Выбери файл игры .exe или .com.'; $('#game-path').placeholder = 'C:\\Games\\MyGame\\game.exe'; $('#compatibility-note').textContent = 'Аргументы запуска и рабочая папка доступны в параметрах игры.'; } skipShaderPrecache = !!r.skipShaderPrecache; updateShaderSetting(); render(); } catch (error) { toast(error.message); } }
function updateShaderSetting() {
  $('#shader-skip-value').textContent = skipShaderPrecache ? 'ВКЛ' : 'ВЫКЛ';
  $('#shader-skip').setAttribute('aria-pressed',String(skipShaderPrecache));
}
$('#shader-skip').onclick = async () => {
  try { const r = await api('setShaderSkip',{enabled:!skipShaderPrecache}); skipShaderPrecache = r.skipShaderPrecache; updateShaderSetting(); toast('Настройка сохранена. Нажми «Перезапустить Steam и применить настройку».'); }
  catch(e) { toast(e.message); }
};
async function restartSteamSettings() {
  if(launching) return;
  busy(true);
  try { await api('restartSteam'); $('#settings-dialog').close(); $('#launch-status').hidden = false; $('#launch-status-text').textContent = 'Перезапускаю Steam для применения настройки шейдеров…'; }
  catch(e) { busy(false); toast(e.message); }
}
$('#restart-steam').onclick = restartSteamSettings;
function busy(value) { if(!value) $('#launch-status').hidden = true; launching = value; $('#play').classList.toggle('launch-busy',value); if(value) $('#status').textContent = 'Steam · выполняется запуск'; else $('#status').textContent = `${games.length} в библиотеке · ${games.filter(g=>g.installed).length} установлено`; }
async function launch(game = selected) {
  if (!game) return openAdd();
  if(game.needsSetup) { setHero(game); openEdit(); return; }
  if (launching) return toast('Steam переключает аккаунт. Дождись завершения.');
  busy(true);
  try {
    const result = await api('launch', {id: game.id});
    if(result.needsAccountSwitch) {
      pendingSwitchId = result.gameId;
      $('#switch-description').textContent = `${game.name} будет запущена с аккаунтом ${result.account.name} (${result.account.login}).`;
      $('#switch-dialog').showModal();
      $('#switch-dialog .dialog-actions .secondary').focus();
    } else if(result.preparing) {
      toast('Проверяю сохранения перед запуском…');
    } else {
      game.lastPlayed = Date.now()/1000;
      toast('Запрос на запуск отправлен · ' + game.name);
    }
  } catch (error) { toast(error.message); }
  finally { busy(false); }
}
async function favorite() { if (!selected) return; try { await api('favorite',{id:selected.id}); selected.favorite = !selected.favorite; render(); } catch(error) { toast(error.message); } }
function openAdd() {
  editingId = null; $('#add-form').reset();
  $('#editor-title').textContent = 'Добавить игру';
  $('#editor-submit').textContent = 'Добавить в библиотеку';
  $('#editor-delete').hidden = true;
  window.prepareRunner?.(null);
  $('#add-dialog').showModal();
}
function openEdit() {
  if(!selected) return;
  if(selected.source === 'steam') {
    steamEditingId = selected.id;
    $('#steam-game-name').textContent = selected.name;
    const select = $('#steam-account'); select.replaceChildren(new Option('Текущий аккаунт Steam', ''));
    for(const account of accounts) select.add(new Option(`${account.name} (${account.login})${account.id === activeAccount ? ' · активен' : ''}`, account.id));
    select.value = selected.accountId || '';
    const active = accounts.find(a=>a.id === activeAccount);
    $('#steam-account-status').textContent = active ? `Сейчас в Steam: ${active.name}` : 'Активный аккаунт не определён. После выбора может потребоваться вход в Steam.';
    $('#steam-dialog').showModal();
    return;
  }
  editingId = selected.id; $('#add-form').reset();
  $('#editor-title').textContent = 'Параметры игры'; $('#editor-submit').textContent = 'Сохранить изменения';
  $('#game-path').value = selected.path || ''; $('#game-name').value = selected.name;
  $('#game-args').value = selected.arguments || ''; $('#game-cwd').value = selected.cwd || '';
  $('#game-cover').placeholder = selected.cover ? 'Текущая обложка сохранится' : 'PNG, JPG или WebP';
  $('#editor-delete').hidden = false;
  window.prepareRunner?.(selected);
  $('#add-dialog').showModal();
}
function cycle(selector, step) {
  const buttons = [...document.querySelectorAll(selector)];
  const current = buttons.findIndex(b=>b.classList.contains('active'));
  buttons[(current+step+buttons.length)%buttons.length].click();
}
function openHelp() { if(!$('#help-dialog').open) $('#help-dialog').showModal(); }
function jump(index) { const card = [...document.querySelectorAll('.game')][index]; card?.focus({preventScroll:true}); card?.scrollIntoView({block:'nearest',behavior:'smooth'}); }
function toggleSort() { $('#sort').value = $('#sort').value === 'name' ? 'recent' : 'name'; render(); }

function move(dx, dy) {
  if (!visible.length) return;
  const columns = getComputedStyle($('#grid')).gridTemplateColumns.split(' ').length;
  const index = Math.max(0, visible.findIndex(g => g.id === selected?.id));
  const next = Math.max(0, Math.min(visible.length - 1, index + dx + dy * columns));
  const card = [...document.querySelectorAll('.game')][next]; card?.focus({preventScroll:true}); card?.scrollIntoView({block:'nearest',behavior:'smooth'});
}
$('.brand').onclick = event => { event.preventDefault(); document.querySelector('[data-tab="all"]').click(); window.scrollTo({top:0,behavior:'smooth'}); };
document.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => { tab = button.dataset.tab; document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('active',b === button)); render(); });
document.querySelectorAll('[data-source]').forEach(button => button.onclick = () => { source = button.dataset.source; document.querySelectorAll('[data-source]').forEach(b => b.classList.toggle('active',b === button)); render(); });
$('#search').oninput = () => render(); $('#sort').onchange = () => render(); $('#refresh').onclick = async () => { await refresh(); toast('Библиотека обновлена'); };
$('#play').onclick = () => launch(); $('#favorite').onclick = favorite; $('#edit').onclick = openEdit;
$('#add').onclick = $('#empty-add').onclick = openAdd;
$('#settings-button').onclick = () => $('#settings-dialog').showModal();
$('#help-button').onclick = () => { $('#settings-dialog').close(); openHelp(); };
document.querySelectorAll('[data-close]').forEach(b => b.onclick = () => document.getElementById(b.dataset.close).close());
document.querySelectorAll('dialog').forEach(d => d.onclick = e => { if(e.target === d) { const r = d.getBoundingClientRect(); if(e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) d.close(); } });
for(const action of ['fullscreen','minimize','quit']) $('#'+action).onclick = async () => { try { await api(action); $('#settings-dialog').close(); } catch(e) { toast(e.message); } };
$('#browse').onclick = async () => { try { const r = await api('chooseExecutable'); if(r.path) { $('#game-path').value = r.path; if(!$('#game-name').value) $('#game-name').value = r.name; } } catch(e) { toast(e.message); } };
$('#browse-cover').onclick = async () => { try { const r = await api('chooseCover'); if(r.path) $('#game-cover').value = r.path; } catch(e) { toast(e.message); } };
$('#browse-cwd').onclick = async () => { try { const r = await api('chooseDirectory'); if(r.path) $('#game-cwd').value = r.path; } catch(e) { toast(e.message); } };
$('#add-form').onsubmit = async e => {
  e.preventDefault(); const submit = $('#editor-submit'); submit.disabled = true;
  try {
    const wasEditing = !!editingId;
    const r = await api(wasEditing ? 'edit' : 'add', {id:editingId,name:$('#game-name').value,path:$('#game-path').value,arguments:$('#game-args').value,runner:$('#game-runner').value,proton:$('#game-proton').value,cwd:$('#game-cwd').value,cover:$('#game-cover').value,clearCover:$('#clear-cover').checked});
    games = r.games;
    if(!wasEditing) { tab = 'all'; source = 'all'; $('#search').value=''; document.querySelectorAll('[data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab==='all')); document.querySelectorAll('[data-source]').forEach(b=>b.classList.toggle('active',b.dataset.source==='all')); }
    render(r.id); $('#add-dialog').close(); $('#add-form').reset();
    toast(wasEditing ? 'Параметры игры сохранены' : 'Игра добавлена. Хорошего вечера!');
  } catch(e) { toast(e.message); } finally { submit.disabled = false; }
};
$('#steam-form').onsubmit = async e => {
  e.preventDefault();
  try { games = (await api('setAccount',{id:steamEditingId,accountId:$('#steam-account').value})).games; render(steamEditingId); $('#steam-dialog').close(); toast('Аккаунт для игры сохранён'); }
  catch(e) { toast(e.message); }
};
$('#confirm-switch').onclick = async () => {
  if(launching || !pendingSwitchId) return;
  busy(true);
  try { await api('switchAndLaunch',{id:pendingSwitchId}); $('#switch-dialog').close(); $('#launch-status').hidden = false; $('#launch-status-text').textContent = 'Переключаю Steam. Сначала клиент завершит текущий сеанс.'; toast('Переключаю Steam. При необходимости подтверди вход в его окне.'); }
  catch(e) { busy(false); toast(e.message); }
};
$('#cancel-switch').onclick = async () => { try { await api('cancelSwitch'); busy(false); toast('Отложенный запуск отменён'); } catch(e) { toast(e.message); } };
$('#show-steam').onclick = async () => { try { await api('showSteam'); } catch(e) { toast(e.message); } };
function askRemove() {
  const game = games.find(g=>g.id === (editingId && $('#add-dialog').open ? editingId : selected?.id));
  if(!game || game.source !== 'local') return;
  $('#remove-dialog').dataset.id = game.id;
  $('#remove-description').textContent = `Убрать «${game.name}» из Orbit? Файлы игры останутся на диске.`;
  $('#remove-dialog').showModal();
}
$('#remove').onclick = $('#editor-delete').onclick = askRemove;
$('#confirm-remove').onclick = async () => {
  try { games = (await api('remove',{id:$('#remove-dialog').dataset.id})).games; $('#remove-dialog').close(); $('#add-dialog').close(); render(); toast('Убрано из библиотеки. Файлы игры сохранены.'); }
  catch(e) { toast(e.message); }
};
const HELP = [
  ['Выбрать игру','← ↑ ↓ →','Крестовина / левый стик'],
  ['Запустить игру','Enter','A / ×'],
  ['Избранное','F','Y / △'],
  ['Параметры / аккаунт игры','E или F2','X / □'],
  ['Добавить игру','N или Insert','Нажать правый стик (R3)'],
  ['Удалить свою игру из списка','Delete, с подтверждением','X / □ → Убрать из списка'],
  ['Вкладки библиотеки','PageUp / PageDown','LB / RB (L1 / R1)'],
  ['Фильтры источника','[ / ]','LT / RT (L2 / R2)'],
  ['Первая / последняя игра','Home / End','—'],
  ['Поиск','/ или Ctrl+F','Нажать левый стик (L3)'],
  ['Сортировка','S','—'],
  ['Обновить библиотеку','R или F5','—'],
  ['Меню','F10','Start / Options'],
  ['Эта справка','F1','Back / View / Share'],
  ['Назад / закрыть окно / выйти из поиска','Esc','B / ○'],
  ['Прокрутить справку / окно','PageUp / PageDown внутри окна','Правый стик'],
  ['Следующий / предыдущий элемент','Tab / Shift+Tab','В окнах: крестовина / стик'],
  ['Сохранить форму','Ctrl+Enter','Выбрать «Сохранить» и A / ×'],
  ['При ожидании входа: открыть Steam / отменить','F8 / Esc','X / □ открыть, B / ○ отменить'],
  ['Возврат в Orbit / текущие игры','Меню → Текущие игры','Guide / PS в консольном режиме'],
  ['Экранная клавиатура','Консоль → Экранная клавиатура','A / × в текстовом поле'],
  ['Полный экран','F11','Меню → Полный экран'],
  ['Закрыть Orbit','Ctrl+Q','Меню → Закрыть Orbit']
];
const table = document.createElement('table'); table.className = 'help-table';
for(const [index, row] of [['Действие','Клавиатура','Геймпад'], ...HELP].entries()) {
  const tr = document.createElement('tr');
  for(const text of row) { const cell = document.createElement(index ? 'td' : 'th'); cell.textContent = text; tr.append(cell); }
  table.append(tr);
}
$('#help-table').append(table);
function dialogElements(modal) {
  return [...modal.querySelectorAll('button,input,select,textarea,a[href]')].filter(e => !e.disabled && e.tabIndex !== -1 && e.getClientRects().length);
}
function moveDialogFocus(modal, direction, horizontal = false) {
  let elements = dialogElements(modal);
  const current = document.activeElement;
  const row = current.closest('.dialog-actions');
  if(horizontal && row && modal.contains(row)) elements = elements.filter(e=>row.contains(e));
  if(!elements.length) return;
  const index = elements.indexOf(current);
  const next = index < 0 ? (direction > 0 ? 0 : elements.length-1) : (index+direction+elements.length)%elements.length;
  elements[next].focus();
  elements[next].scrollIntoView({block:'nearest'});
}
document.addEventListener('keydown', e => {
  const modal = document.activeElement.closest('dialog[open]') || [...document.querySelectorAll('dialog[open]')].at(-1);
  const typing = ['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName);
  if(e.key === 'F1') { e.preventDefault(); if($('#help-dialog').open) $('#help-dialog').close(); else openHelp(); return; }
  if(!modal && launching && e.key === 'F8') { e.preventDefault(); $('#show-steam').click(); return; }
  if(e.key === 'Escape') {
    e.preventDefault();
    if(!modal && launching) { $('#cancel-switch').click(); return; }
    if(modal) modal.close();
    else if(typing || $('#search').value) { $('#search').value = ''; render(); $('#search').blur(); jump(Math.max(0,visible.findIndex(g=>g.id === selected?.id))); }
    else { window.scrollTo({top:0,behavior:'smooth'}); $('#play').focus(); }
    return;
  }
  if(modal) {
    if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key) && !typing) {
      e.preventDefault();
      moveDialogFocus(modal, ['ArrowLeft','ArrowUp'].includes(e.key) ? -1 : 1, ['ArrowLeft','ArrowRight'].includes(e.key));
    }
    if(e.ctrlKey && e.key === 'Enter') { e.preventDefault(); modal.querySelector('form')?.requestSubmit(); }
    return;
  }
  if(e.ctrlKey && e.code === 'KeyF') { e.preventDefault(); $('#search').focus(); $('#search').select(); return; }
  if(typing || e.ctrlKey || e.altKey || e.metaKey) return;
  if(e.repeat && !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) { e.preventDefault(); return; }
  let handled = true;
  if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)) move(e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0, e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0);
  else if(e.key === 'Enter' && (document.activeElement.classList.contains('game') || document.activeElement === document.body)) launch();
  else if(e.code === 'KeyF') favorite();
  else if(e.code === 'KeyE' || e.key === 'F2') openEdit();
  else if(e.code === 'KeyN' || e.key === 'Insert') openAdd();
  else if(e.code === 'KeyR' || e.key === 'F5') refresh();
  else if(e.code === 'KeyS') toggleSort();
  else if(e.code === 'Slash') $('#search').focus();
  else if(e.code === 'BracketLeft') cycle('[data-source]',-1);
  else if(e.code === 'BracketRight') cycle('[data-source]',1);
  else if(e.key === 'PageUp') cycle('[data-tab]',-1);
  else if(e.key === 'PageDown') cycle('[data-tab]',1);
  else if(e.key === 'Home') jump(0);
  else if(e.key === 'End') jump(visible.length-1);
  else if(e.key === 'Delete') askRemove();
  else if(e.key === 'F10') $('#settings-dialog').showModal();
  else handled = false;
  if(handled) e.preventDefault();
});
let previousButtons = [], nextMove = 0;
function handleGamepad(pad, now) {
  if(window.orbitSelectGamepad?.(pad,now,previousButtons)) { previousButtons=pad.buttons.map(b=>b.pressed); return; }
  const pressed = i => !!pad.buttons[i]?.pressed;
  const fresh = i => pressed(i) && !previousButtons[i];
  if(fresh(16)) window.orbitRunningMenu?.();
  const modal = document.activeElement.closest('dialog[open]') || [...document.querySelectorAll('dialog[open]')].at(-1);
  if(!modal && launching) {
    if(fresh(1)) $('#cancel-switch').click();
    if(fresh(2)) $('#show-steam').click();
    if(fresh(8)) openHelp();
    if(fresh(9)) $('#settings-dialog').showModal();
    previousButtons = pad.buttons.map(b=>b.pressed);
    return;
  }
  if(modal) {
    if(Math.abs(pad.axes[3] || 0) > .2) modal.scrollTop += pad.axes[3] * 12;
    if(fresh(1)) modal.close();
    else {
      const direction = pressed(12) || (pad.axes[1]||0)<-.6 ? -1 : pressed(13) || (pad.axes[1]||0)>.6 ? 1 : 0;
      if(now > nextMove && direction) {
        moveDialogFocus(modal,direction); nextMove = now+230;
      }
      const horizontal = pressed(14) ? -1 : pressed(15) ? 1 : 0;
      if(now > nextMove && horizontal) {
        if(document.activeElement.tagName === 'SELECT') {
          const select = document.activeElement;
          select.selectedIndex = Math.max(0,Math.min(select.options.length-1,select.selectedIndex+horizontal));
          select.dispatchEvent(new Event('change'));
        } else moveDialogFocus(modal,horizontal,true);
        nextMove = now+230;
      }
      if(fresh(0) && modal.contains(document.activeElement)) {
        if(document.activeElement.matches('input:not([type=checkbox]):not([type=number]),textarea') && window.orbitKeyboard) window.orbitKeyboard(document.activeElement);
        else document.activeElement.click();
      }
    }
  } else {
    const typing = ['INPUT','SELECT','TEXTAREA'].includes(document.activeElement.tagName);
    let dx = pressed(15) ? 1 : pressed(14) ? -1 : Math.abs(pad.axes[0]||0)>.6 ? Math.sign(pad.axes[0]) : 0;
    let dy = pressed(13) ? 1 : pressed(12) ? -1 : Math.abs(pad.axes[1]||0)>.6 ? Math.sign(pad.axes[1]) : 0;
    if(!typing && (dx||dy) && now > nextMove) { move(dx,dy); nextMove = now+230; }
    if(!typing && fresh(0)) launch(); if(fresh(3)) favorite(); if(fresh(2)) openEdit();
    if(fresh(9)) $('#settings-dialog').showModal(); if(fresh(8)) openHelp();
    if(fresh(4)) cycle('[data-tab]',-1); if(fresh(5)) cycle('[data-tab]',1);
    if(fresh(6)) cycle('[data-source]',-1); if(fresh(7)) cycle('[data-source]',1);
    if(fresh(10)) $('#search').focus(); if(fresh(11)) openAdd();
    if(fresh(1)) {
      if(typing || $('#search').value) { $('#search').value=''; render(); $('#search').blur(); jump(0); }
      else { window.scrollTo({top:0,behavior:'smooth'}); $('#play').focus(); }
    }
  }
  previousButtons = pad.buttons.map(b=>b.pressed);
}
function pollGamepad(now) {
  const pad = [...(navigator.getGamepads?.() || [])].find(Boolean);
  $('#gamepad').classList.toggle('connected', !!pad);
  if(pad) handleGamepad(pad,now); else previousButtons = [];
  requestAnimationFrame(pollGamepad);
}
function clock() { $('#clock').textContent = new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}); }
clock(); setInterval(clock,10000); requestAnimationFrame(pollGamepad);
if(typeof qt !== 'undefined' && typeof QWebChannel !== 'undefined') new QWebChannel(qt.webChannelTransport, async channel => { bridge = channel.objects.bridge; bridge.launchProgress.connect(message => { $('#launch-status-text').textContent = message; $('#status').textContent = 'Steam · ожидается вход в выбранный аккаунт'; toast(message); }); bridge.launchFinished.connect(raw => { busy(false); const r=JSON.parse(raw); if(r.error) toast(r.error); else { toast(r.settingsApplied ? 'Настройка шейдеров применена к сеансу Steam' : 'Запрос на запуск отправлен в Steam'); refresh(); } }); await refresh(); if(new URLSearchParams(location.search).has('applySteamSettings')) restartSteamSettings(); });
else { render(); toast('Для запуска игр открой приложение командой python3 launcher.py'); }

window.addEventListener('focus', () => { if(bridge && !launching && !document.querySelector('dialog[open]')) refresh(); });
