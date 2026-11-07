"""Offscreen interaction checks; run with QT_QPA_PLATFORM=offscreen."""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView

app = QApplication([])
view = QWebEngineView()
view.resize(1440, 920)
view.show()
script = r'''(() => {
  try {
    games = [
      {id:'a',name:'Alpha',source:'steam',installed:true,favorite:false,lastPlayed:10},
      {id:'b',name:'Beta',source:'local',path:'/tmp/my-game',arguments:'--fullscreen',cwd:'/tmp',installed:true,favorite:true,lastPlayed:20},
      {id:'c',name:'Gamma',source:'steam',installed:false,favorite:false,lastPlayed:0}
    ];
    function check(condition, label) { if(!condition) throw new Error(label); }
    render(); check(visible.length===3,'initial library');
    check(selected.id==='a','alphabetical selection');
    document.querySelector('[data-source="local"]').click();
    check(visible.length===1 && selected.id==='b','local source filter');
    document.querySelector('[data-source="all"]').click();
    document.querySelector('[data-tab="favorites"]').click();
    check(visible.length===1 && selected.id==='b','favorite filter');
    document.querySelector('[data-tab="recent"]').click();
    check(visible.length===2 && visible[0].id==='b','recent sort');
    document.querySelector('[data-tab="all"]').click();
    $('#search').value='GAM'; $('#search').dispatchEvent(new Event('input'));
    check(visible.length===1 && selected.id==='c','case insensitive search');
    $('#search').value='not-found'; $('#search').dispatchEvent(new Event('input'));
    check(!$('#empty').hidden && selected===null,'empty state');
    $('#search').value=''; render(); move(1,0);
    check(selected.id==='b','keyboard selection');
    $('#add').click(); check($('#add-dialog').open,'add dialog');
    document.querySelector('[data-close="add-dialog"]').click();
    check(!$('#add-dialog').open,'dialog close');

    function key(key,code,extra={}) { document.dispatchEvent(new KeyboardEvent('keydown',{key,code,bubbles:true,...extra})); }
    key('e','KeyE');
    check($('#add-dialog').open && $('#game-name').value==='Beta' && $('#game-args').value==='--fullscreen','edit prefilled values');
    check(!$('#editor-delete').hidden,'edit delete action');
    key('Escape','Escape');
    key('F1','F1'); check($('#help-dialog').open && document.querySelectorAll('.help-table tr').length>15,'help keyboard');
    key('Escape','Escape');
    key('PageDown','PageDown'); check(tab==='favorites','keyboard tabs');
    key('PageUp','PageUp'); check(tab==='all','keyboard tab back');
    key(']','BracketRight'); check(source==='steam','keyboard source');
    key('[','BracketLeft'); check(source==='all','keyboard source back');
    key('End','End'); check(selected.id==='c','last game');
    key('Home','Home'); check(selected.id==='a','first game');
    key('f','KeyF',{ctrlKey:true}); check(document.activeElement===$('#search'),'search shortcut');
    key('Escape','Escape'); check(document.activeElement!==$('#search'),'exit search');
    accounts=[{id:'second',name:'Second',login:'second-login'}]; games[0].accountId='second';
    setHero(games[0]); key('e','KeyE');
    check($('#steam-dialog').open && $('#steam-account').value==='second','Steam account editor');
    key('Escape','Escape');
    $('#switch-dialog').showModal();
    const cancel = $('#switch-dialog .dialog-actions .secondary');
    cancel.focus(); key('ArrowRight','ArrowRight');
    check(document.activeElement===$('#confirm-switch'),'switch dialog right arrow selects confirm');
    key('ArrowLeft','ArrowLeft');
    check(document.activeElement===cancel,'switch dialog left arrow selects cancel');
    key('ArrowUp','ArrowUp');
    check(document.activeElement===$('#switch-dialog .close'),'dialog up selects close');
    key('ArrowDown','ArrowDown');
    check(document.activeElement===cancel,'dialog down selects cancel');
    key('Escape','Escape');
    openAdd(); $('#game-name').focus();
    key('ArrowLeft','ArrowLeft');
    check(document.activeElement===$('#game-name'),'text field keeps caret arrows');
    key('Escape','Escape');
    function pad(buttons) { return {buttons:Array.from({length:17},(_,i)=>({pressed:buttons.includes(i)})),axes:[0,0]}; }
    $('#switch-dialog').showModal(); cancel.focus();
    previousButtons=[]; handleGamepad(pad([15]),500);
    check(document.activeElement===$('#confirm-switch'),'gamepad right selects confirm');
    handleGamepad(pad([]),750); handleGamepad(pad([14]),1000);
    check(document.activeElement===cancel,'gamepad left selects cancel');
    key('Escape','Escape'); nextMove=0;
    previousButtons=[]; handleGamepad(pad([2]),1000);
    check($('#steam-dialog').open,'gamepad game parameters');
    handleGamepad(pad([]),1100); handleGamepad(pad([1]),1200);
    check(!$('#steam-dialog').open,'gamepad back');
    handleGamepad(pad([]),1300); handleGamepad(pad([8]),1400);
    check($('#help-dialog').open,'gamepad help');
    handleGamepad(pad([]),1500); handleGamepad(pad([1]),1600);
    handleGamepad(pad([]),1700); handleGamepad(pad([5]),1800);
    check(tab==='favorites','gamepad tabs');
    handleGamepad(pad([]),1900); handleGamepad(pad([11]),2000);
    check($('#add-dialog').open && $('#game-name').value==='' && editingId===null,'gamepad add clean form');
    key('Escape','Escape');
    skipShaderPrecache=true; updateShaderSetting();
    check($('#shader-skip-value').textContent==='ВКЛ' && $('#shader-skip').getAttribute('aria-pressed')==='true','shader skip setting display');
    skipShaderPrecache=false; updateShaderSetting();
    check($('#shader-skip-value').textContent==='ВЫКЛ','shader skip disabled display');
    return 'PASS: filters, search, editing, Steam accounts, help, expanded keyboard shortcuts, gamepad buttons, dialogs';
  } catch(error) { return 'FAIL: '+error.message; }
})()'''
def finish(result):
    print(result)
    app.exit(0 if result and result.startswith('PASS:') else 1)
def run():
    view.page().runJavaScript(script, finish)
view.loadFinished.connect(lambda ok: QTimer.singleShot(500, run) if ok else app.exit(1))
view.setUrl(QUrl.fromLocalFile(str(Path(__file__).resolve().parents[1] / 'ui/index.html')))
QTimer.singleShot(15000, lambda: app.exit(2))
sys.exit(app.exec())
