"""Render every Orbit popup with long content at representative viewport sizes."""
import argparse,json,os,sys
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QTimer,QUrl
parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=Path('/tmp/orbit-audit'));parser.add_argument('--sizes',default='1440x900,1280x720,800x600,480x800');args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
app=QApplication([]);view=QWebEngineView();view.show();results=[];queue=[]
scenes=['library','add','edit','steam','switch','settings','help','remove','downloads','updates','console','saves','running','action','keyboard','nested-keyboard','toast','launch','runner-menu','proton-menu','account-menu','sort-menu']
scenes += ['evening','evening-empty','evening-profile','evening-game-menu','evening-duration-menu','evening-bottom','evening-profile-bottom']
scenes += [name+'-bottom' for name in ('add','edit','settings','help','downloads','saves','updates')]
for size in args.sizes.split(','):
 w,h=map(int,size.split('x'))
 for scene in scenes:queue.append((w,h,scene))
setup=r'''(()=>{
 document.body.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));
 document.querySelectorAll('dialog[open]').forEach(d=>d.close());
 if($('#toast').matches(':popover-open'))$('#toast').hidePopover(); $('#toast').classList.remove('visible'); $('#launch-status').hidden=true;
 games=[{id:'a',name:'Arma 3 — очень длинное название игрового издания',source:'local',installed:true,path:'/games/game.exe',favorite:false,lastPlayed:0},{id:'b',name:'Another world',source:'steam',installed:true,favorite:true,lastPlayed:0}];
 render('a'); window.prepareRunner=()=>{};
 const path='/home/player/Игры/Очень длинное название игры/папка с сохранениями/profile/';
 const name='Очень длинное название игры: полное коллекционное издание';
 const requested=SCENE;const bottom=requested.endsWith('-bottom');const scene=requested.replace(/-bottom$/,'');
 const open=id=>$(id).showModal();
 if(['add','edit','runner-menu','proton-menu'].includes(scene)) { openAdd(); $('#game-path').value=path+'game.exe'; $('#game-name').value=name; $('#game-proton').replaceChildren(new Option('GE-Proton с очень длинным названием версии','x'));$('#game-runner').value='proton';$('#proton-label').hidden=false;if(scene==='edit'){$('#editor-title').textContent='Параметры игры';$('#editor-delete').hidden=false;$('#editor-submit').textContent='Сохранить изменения';} }
 if(scene==='steam'||scene==='account-menu'){$('#steam-game-name').textContent=name;$('#steam-account').replaceChildren(new Option('Очень длинный никнейм игрока (длинный-логин) · активен','x'));$('#steam-account-status').textContent='Сейчас в Steam: длинный никнейм игрока';open('#steam-dialog');}
 if(scene==='switch'){$('#switch-description').textContent=name+' будет запущена с аккаунтом игрока.';open('#switch-dialog');}
 if(scene==='settings')open('#settings-dialog');
 if(scene.startsWith('evening')){
  open('#evening-dialog');
  renderEveningPicks({picks:scene==='evening-empty'?[]:[1,2,3].map(i=>({game:{id:'a'+i,name:name+' '+i,cover:''},reason:'Расслабиться · сессия от 20 мин · последний запуск через Orbit: 01.01.2026'})),matching:3,ready:5,tagged:scene==='evening-empty'?0:3});
  if(['evening-profile','evening-game-menu','evening-duration-menu'].includes(scene)){
   $('#evening-game').replaceChildren(new Option(name,'a'),new Option('Другая игра','b'));eveningProfiles={a:{minutes:60,moods:['relax','friends']}};loadEveningProfile();open('#evening-profile-dialog');
  }
 }

 if(scene==='help')openHelp();
 if(scene==='remove'){$('#remove-description').textContent='Убрать «'+name+'» из Orbit? Файлы игры останутся на диске.';open('#remove-dialog');}
 if(['downloads','updates','console'].includes(scene)) {open('#features-dialog');document.querySelectorAll('[data-panel]').forEach(e=>e.hidden=e.dataset.panel!==scene);document.querySelectorAll('[data-feature]').forEach(e=>e.classList.toggle('active',e.dataset.feature===scene));
 if(scene==='downloads'){$('#torrent-source').value='magnet:?xt=urn:btih:'+('a'.repeat(80));$('#torrent-path').value=path;$('#torrent-list').innerHTML='';const row=element('article','','download-row');row.append(element('h4','Game_'+('VeryLongUnbrokenFilename'.repeat(6))));const progress=document.createElement('progress');progress.value=45;progress.max=100;row.append(progress,element('p','45% · 1200 КиБ/с · 12 пиров · Загружается'));const actions=element('div','','download-actions');actions.append(featureButton('Пауза',()=>{}),featureButton('Открыть папку',()=>{}),featureButton('Убрать из очереди',()=>{}));row.append(actions);$('#torrent-list').append(row);}
 if(scene==='updates'){$('#update-status').textContent='Доступна новая версия';$('#update-notes').textContent=('Описание изменений новой версии. '+path+'\n').repeat(12);$('#update-download').hidden=false;}
 }
 if(scene==='saves'){$('#saves-title').textContent='Сохранения · '+name;$('#saves-local').value=path;$('#saves-cloud').value=path+'облако';$('#saves-key').value='arma-3';$('#saves-enabled').checked=true;$('#saves-conflict').hidden=false;renderSaveHistory([{id:'x',time:Date.now()/1000,files:{one:'x'}}]);open('#saves-dialog');}
 if(scene==='running'){$('#running-list').replaceChildren();const row=element('article','','download-row');row.append(element('h3',name),featureButton('Вернуться в игру',()=>{}),featureButton('Завершить игру…',()=>{}));$('#running-list').append(row);open('#running-dialog');}
 if(scene==='action')confirmAction('Завершить '+name+'?','Несохранённый прогресс может быть потерян.',()=>{});
 if(scene==='keyboard'||scene==='nested-keyboard'){if(scene==='nested-keyboard')openAdd();$('#game-name').value=path;keyboardRussian=true;window.orbitKeyboard($('#game-name'));}
 if(scene==='toast'){open('#settings-dialog');toast('Длинное сообщение об ошибке: '+name);}
 if(scene==='launch'){$('#launch-status').hidden=false;$('#launch-status-text').textContent='Жду входа в выбранный аккаунт Steam. При необходимости открой Steam и подтверди вход / Steam Guard.';}
 window.scrollTo(0,0);document.querySelectorAll('dialog[open]').forEach(d=>d.scrollTop=bottom?d.scrollHeight:0);
 window.auditScene=scene;const menus={'runner-menu':'game-runner','proton-menu':'game-proton','account-menu':'steam-account','sort-menu':'sort','evening-game-menu':'evening-game','evening-duration-menu':'evening-duration'};window.auditMenuId=menus[scene]?menus[scene]+'-menu':null;if(menus[scene])document.getElementById(menus[scene]).closest('.orbit-select').querySelector('.select-trigger').click();
 return true;
})()'''
metrics=r'''(()=>{
 const dialogs=[...document.querySelectorAll('dialog[open]')];
 const top=dialogs.at(-1);const root=top||document.documentElement;
 const visible=e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const bounds=root.getBoundingClientRect();
 const bad=[...root.querySelectorAll('input,select,button,.file-field,.keyboard-row,.download-row,.evening-pick')].filter(visible).filter(e=>{const r=e.getBoundingClientRect();return r.left<bounds.left-2||r.right>bounds.right+2}).map(e=>e.id||e.className);
 return JSON.stringify({menuMissing:window.auditMenuId&&!document.getElementById(window.auditMenuId)?.matches(':popover-open'),viewport:[innerWidth,innerHeight],dialog:top?.id||null,horizontal:root.scrollWidth>root.clientWidth+2,outside:bad,bodyOverflow:document.documentElement.scrollWidth>innerWidth+2,whiteInputs:[...root.querySelectorAll('input:not([type=checkbox])')].filter(visible).filter(e=>getComputedStyle(e).backgroundColor==='rgb(255, 255, 255)').map(e=>e.id)});
})()'''
current=None

def next_scene():
 global current
 if not queue:
  issues=[r for r in results if r['horizontal'] or r['outside'] or r['bodyOverflow'] or r['whiteInputs'] or r['menuMissing']]
  (args.out/'metrics.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps({'screenshots':len(results),'issues':issues},ensure_ascii=False));app.exit(1 if issues else 0);return
 current=queue.pop(0);w,h,scene=current;view.resize(w,h)
 view.page().runJavaScript(setup.replace('SCENE',json.dumps(scene)),lambda _:QTimer.singleShot(350,capture))

def capture():
 w,h,scene=current;view.grab().save(str(args.out/f'{w}x{h}-{scene}.png'))
 def done(value):
  results.append({'scene':scene,**json.loads(value)});QTimer.singleShot(0,next_scene)
 view.page().runJavaScript(metrics,done)
view.loadFinished.connect(lambda ok:QTimer.singleShot(200,next_scene) if ok else app.exit(1))
view.setUrl(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'ui/index.html')))
QTimer.singleShot(90000,lambda:app.exit(2));sys.exit(app.exec())
