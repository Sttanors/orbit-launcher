"""Exercise the real QWebChannel bridge against disposable game/save folders."""
import json
import os
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication,QMainWindow
from PySide6.QtCore import QTimer,QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from launcher import Library,create_bridge

app=QApplication([]); window=QMainWindow(); view=QWebEngineView(); window.setCentralWidget(view); window.resize(1440,1000); window.show()
temp=tempfile.TemporaryDirectory(); root=Path(temp.name); local=root/'saves'; cloud=root/'cloud'; local.mkdir(); cloud.mkdir(); (local/'save.dat').write_text('test progress')
game=root/('game.exe' if os.name=='nt' else 'game'); game.write_text('test')
from unittest.mock import patch
steam_patch=patch('launcher.scan_steam',return_value=[]);steam_patch.start()
library=Library(root/'state'); library.save_custom({'path':str(game),'name':'Test Game'})
bridge=create_bridge(window,library); bridge.updater.check=lambda:{'available':True,'version':'0.2.4','current':'0.2.3','notes':'Test update'}; install_attempts=[]
def fail_install():
    install_attempts.append(1)
    raise ValueError('Test install failure')
bridge.updater.download=lambda:{'ok':True,'ready':True,'cached':True}
bridge.updater.install=fail_install
launches=[];bridge.launch_game=lambda gid: launches.append(gid) or {'ok':True}; channel=QWebChannel(); channel.registerObject('bridge',bridge); view.page().setWebChannel(channel)
script=r'''(async()=>{
const check=(condition,label)=>{if(!condition)throw Error(label)};
try{
await refresh(); check(games.length===1,'real library bridge');
check($('#download-game').getClientRects().length && $('#orbit-updates').getClientRects().length,'visible download and update entry points');
$('#orbit-updates').click();
await new Promise((resolve,reject)=>{const start=Date.now();const timer=setInterval(()=>{if($('#update-home-title').textContent.includes('0.2.4')){clearInterval(timer);resolve()}else if(Date.now()-start>5000){clearInterval(timer);reject(Error('home update shortcut'))}},50)});
check($('#features-dialog').open && !document.querySelector('[data-panel=updates]').hidden,'home shortcut opens and checks updates');
$('#features-dialog').close();
const until=async(predicate,label)=>{const start=Date.now();while(!predicate()){if(Date.now()-start>5000)throw Error(label+' / '+$('#evening-profile-status').textContent);await new Promise(r=>setTimeout(r,30));}};
await window.orbitEvening();check($('#evening-dialog').open,'evening opens');check(!$('#evening-results').children.length,'untagged empty state');
await findEvening(true);check($('#evening-results').children.length===1,'surprise without tags');
$('#evening-edit').click();await until(()=>$('#evening-profile-dialog').open,'tag editor opens');
$('#evening-profile-form').requestSubmit();await until(()=>$('#evening-profile-status').textContent==='Выбери хотя бы одно настроение.' && !$('#evening-profile-save').disabled,'empty tags validated');
$('#evening-profile-moods [data-mood=relax]').click();$('#evening-profile-moods [data-mood=friends]').click();
$('#evening-duration').value='20';$('#evening-profile-form').requestSubmit();
await until(()=>$('#evening-profile-status').textContent.startsWith('Теги сохранены. Выбери'),'tags save');
const saved=await api('eveningInfo');check(Object.values(saved.profiles)[0].moods.length===2,'multiple moods persist via real bridge');
$('#evening-profile-save').focus();document.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));check(document.activeElement.id==='evening-profile-clear','arrow navigation in tag editor');
previousButtons=[];handleGamepad({buttons:Array.from({length:17},(_,i)=>({pressed:i===1})),axes:[0,0,0,0]},10000);
check(!$('#evening-profile-dialog').open && $('#evening-dialog').open,'gamepad B closes nested editor only');previousButtons=[];
await findEvening();check($('#evening-results').children.length===1,'tagged recommendation');
$('#evening-times [data-minutes="20"]').click();check(!$('#evening-results').children.length,'changed filters clear old results');
await findEvening();check($('#evening-results button').textContent==='Играть','launch action');
$('#evening-results button').click();await until(()=>!launching,'recommendation launch');check(!$('#evening-dialog').open,'launch closes evening');
window.requestAutoImport=true;
await new Promise((resolve,reject)=>{const start=Date.now();const timer=setInterval(()=>{if(games.some(g=>g.downloadId==='test-torrent')){clearInterval(timer);resolve()}else if(Date.now()-start>5000){clearInterval(timer);reject(Error('automatic library import'))}},50)});
const imported=games.find(g=>g.downloadId==='test-torrent');check(imported.needsSetup,'completed archive has setup card');
setHero(imported);await launch(imported);check($('#add-dialog').open && editingId===imported.id,'setup card opens editor without executing download');$('#add-dialog').close();
await showFeatures('console'); check($('#features-dialog').open,'features dialog');
check(!document.querySelector('[data-panel="console"]').hidden,'console panel');
$('#features-dialog').close();
await showSaves(); check($('#saves-dialog').open,'saves dialog');
await api('saveProfile',{id:selected.id,enabled:true,key:'test-game',local:LOCAL,cloud:CLOUD});
await new Promise(async(resolve,reject)=>{const r=await api('syncSaves',{id:selected.id}); const done=raw=>{const e=JSON.parse(raw);if(e.job===r.job){bridge.serviceFinished.disconnect(done);e.error?reject(Error(e.error)):resolve(e.result)}};bridge.serviceFinished.connect(done)});
const state=await api('features');check(state.saves[selected.id].key==='test-game','saved profile');
$('#saves-dialog').close();openAdd();
$('#game-name').value='Pad';$('#game-name').setSelectionRange(3,3);window.orbitKeyboard($('#game-name'));typeVirtual('!');check($('#game-name').value==='Pad!','virtual keyboard insertion');typeVirtual('',true);check($('#game-name').value==='Pad','virtual backspace');
$('#keyboard-dialog').close();$('#add-dialog').close();
confirmAction('Test power dialog','No real power action',()=>{});check($('#action-dialog').open,'confirmation dialog');$('#action-dialog').close();
await window.orbitRunningMenu();check($('#running-dialog').open,'running menu');$('#running-dialog').close();
await showFeatures('updates');check(!document.querySelector('[data-panel="updates"]').hidden,'updates panel');
$('#update-download').hidden=false;$('#update-download').click();
await until(()=>$('#update-status').textContent.includes('Test install failure') && !featureBusy,'async install error visible');
check(!$('#update-install').hidden,'installation retry available');
$('#update-install').click();check($('#action-dialog').open,'retry confirmation');$('#action-confirm').click();
await until(()=>!featureBusy && $('#update-status').textContent.includes('Test install failure'),'retry uses verified package');
window.featureTestResult='PASS: real bridge, profiles, async sync, evening picks/tags/pad/launch, feature panels, virtual keyboard, running menu, confirmation';
}catch(e){window.featureTestResult='FAIL: '+e.message}
})();'''.replace('LOCAL',json.dumps(str(local))).replace('CLOUD',json.dumps(str(cloud)))
started=False
imported_once=False

def poll():
    global started,imported_once
    if started and not imported_once:
        def inject(value):
            global imported_once
            if not value or imported_once:return
            imported_once=True
            (root/'download.txt').write_text('test download')
            class CompletedDownload:
                session=True
                error=''
                def status(self):return {'items':[],'errorMessage':''}
                def completed(self):return [{'id':'test-torrent','name':'Downloaded Test','path':str(root),'files':['download.txt']}]
            bridge.torrents=CompletedDownload();bridge.last_session_poll=0;bridge.poll_services()
        view.page().runJavaScript('!!window.requestAutoImport',inject)
    if not started:
        def ready(value):
            global started
            if value:
                started=True; view.page().runJavaScript(script)
        view.page().runJavaScript("typeof bridge !== 'undefined' && !!bridge && typeof showFeatures === 'function'",ready)
    else:
        def result(value):
            if value:
                print(value)
                if value.startswith('PASS:'):
                    view.grab().save(str(root/'features.png'))
                    import shutil
                    shutil.copyfile(root/'features.png','/tmp/orbit-features.png') if os.name!='nt' else None
                app.exit(0 if value.startswith('PASS:') else 1)
        view.page().runJavaScript('window.featureTestResult || null',result)

timer=QTimer();timer.timeout.connect(poll);timer.start(200)
view.setUrl(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1]/'ui/index.html')))
QTimer.singleShot(20000,lambda:app.exit(2))
code=app.exec();
if code==0:
    assert len(install_attempts)==2,'Both install attempts use the already verified package'
    assert len(launches)==1,'Only explicit recommendation click may launch a game'
    assert Library(root/'state').state['eveningProfiles']==library.state['eveningProfiles'],'Evening tags survive restart'
bridge.service_timer.stop();bridge.executor.shutdown(wait=True);temp.cleanup();sys.exit(code)
