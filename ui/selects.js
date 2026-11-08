'use strict';
// Keep native select values/options for the bridge; render the menu inside Chromium.
// Qt's platform popup can ignore the page palette, fonts and display scaling.
(() => {
  let opened=null, active=0;
  const states=[];
  function sync(state) {
    state.trigger.textContent=state.select.selectedOptions[0]?.textContent || 'Выбрать…';
    state.trigger.disabled=state.select.disabled;
    state.wrapper.hidden=state.select.hidden;
  }
  function close(restore=true) {
    if(!opened)return;
    const state=opened;opened=null;
    if(state.menu.matches(':popover-open'))state.menu.hidePopover();
    state.trigger.setAttribute('aria-expanded','false');
    if(restore)state.trigger.focus({preventScroll:true});
  }
  function focusOption(index) {
    const options=[...opened.menu.children];
    if(!options.length)return;
    active=Math.max(0,Math.min(options.length-1,index));
    const option=options[active];option.focus({preventScroll:true});
    const menu=opened.menu;if(option.offsetTop<menu.scrollTop)menu.scrollTop=option.offsetTop;else if(option.offsetTop+option.offsetHeight>menu.scrollTop+menu.clientHeight)menu.scrollTop=option.offsetTop+option.offsetHeight-menu.clientHeight;
  }
  function choose(index) {
    const state=opened;if(!state)return;
    const option=state.select.options[index];if(!option||option.disabled)return;
    state.select.selectedIndex=index;
    state.select.dispatchEvent(new Event('input',{bubbles:true}));
    state.select.dispatchEvent(new Event('change',{bubbles:true}));
    sync(state);close();
  }
  function position(state) {
    const rect=state.trigger.getBoundingClientRect();
    const below=innerHeight-rect.bottom-12,above=rect.top-12;
    const upwards=below<150&&above>below;
    state.menu.style.width=Math.min(rect.width,innerWidth-24)+'px';
    state.menu.style.left=Math.max(12,Math.min(rect.left,innerWidth-rect.width-12))+'px';
    state.menu.style.maxHeight=Math.max(48,Math.min(300,upwards?above:below))+'px';
    state.menu.style.top=upwards?'auto':rect.bottom+6+'px';
    state.menu.style.bottom=upwards?innerHeight-rect.top+6+'px':'auto';
  }
  function open(state) {
    if(opened===state)return close();
    close(false);sync(state);opened=state;
    state.menu.replaceChildren();
    for(const [index,option] of [...state.select.options].entries()) {
      const button=document.createElement('button');button.type='button';button.role='option';
      button.textContent=option.textContent;button.disabled=option.disabled;
      button.setAttribute('aria-selected',String(index===state.select.selectedIndex));
      button.onclick=event=>{event.preventDefault();choose(index);};state.menu.append(button);
    }
    position(state);
    state.menu.showPopover();state.trigger.setAttribute('aria-expanded','true');
    focusOption(state.select.selectedIndex<0?0:state.select.selectedIndex);
  }
  for(const select of document.querySelectorAll('select')) {
    const wrapper=document.createElement('span');wrapper.className='orbit-select';
    select.before(wrapper);wrapper.append(select);select.classList.add('native-select');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
    const trigger=document.createElement('button');trigger.type='button';trigger.className='select-trigger';trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');
    trigger.setAttribute('aria-label',select.getAttribute('aria-label')||select.closest('label')?.firstChild.textContent.trim()||'Выбор');
    const menu=document.createElement('div');menu.className='select-menu';menu.id=select.id+'-menu';menu.role='listbox';menu.setAttribute('popover','manual');menu.setAttribute('aria-label',trigger.getAttribute('aria-label'));
    trigger.setAttribute('aria-controls',menu.id);wrapper.append(trigger,menu);
    const state={select,wrapper,trigger,menu};states.push(state);
    trigger.onclick=event=>{event.preventDefault();open(state);};
    select.addEventListener('change',()=>sync(state));select.addEventListener('click',event=>event.preventDefault());
    new MutationObserver(()=>sync(state)).observe(select,{childList:true,subtree:true,attributes:true,characterData:true});
    for(const property of ['value','selectedIndex']) {
      const descriptor=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,property);
      Object.defineProperty(select,property,{get(){return descriptor.get.call(this);},set(value){descriptor.set.call(this,value);sync(state);},configurable:true});
    }
    select.form?.addEventListener('reset',()=>setTimeout(()=>sync(state),0));sync(state);
  }
  document.addEventListener('keydown',event=>{
    if(!opened) {
      const state=states.find(s=>s.trigger===document.activeElement);
      if(state&&['ArrowDown','ArrowUp',' ','Enter'].includes(event.key)){event.preventDefault();event.stopImmediatePropagation();open(state);}return;
    }
    if(['ArrowDown','ArrowRight','ArrowUp','ArrowLeft','Home','End','Enter',' ','Escape'].includes(event.key)) {
      event.preventDefault();event.stopImmediatePropagation();
      if(event.key==='Escape')close();
      else if(event.key==='Enter'||event.key===' ')choose(active);
      else if(event.key==='Home')focusOption(0);
      else if(event.key==='End')focusOption(opened.menu.children.length-1);
      else focusOption(active+(['ArrowUp','ArrowLeft'].includes(event.key)?-1:1));
    } else if(event.key==='Tab')close();
  },true);
  document.addEventListener('pointerdown',event=>{if(opened&&!opened.wrapper.contains(event.target))close(false);},true);
  document.addEventListener('scroll',event=>{if(opened&&!opened.menu.contains(event.target))position(opened);},true);
  window.addEventListener('resize',()=>{if(opened)position(opened);});
  document.querySelectorAll('dialog').forEach(d=>d.addEventListener('close',()=>{if(!d.open&&opened&&d.contains(opened.wrapper))close(false);}));
  window.orbitSelectGamepad=(pad,now,previous)=>{
    const pressed=i=>!!pad.buttons[i]?.pressed,fresh=i=>pressed(i)&&!previous[i];
    if(!opened){const state=states.find(s=>s.trigger===document.activeElement);if(state&&fresh(0)){open(state);return true;}return false;}
    if(fresh(1))close();else if(fresh(0))choose(active);
    else if(now>nextMove){const direction=pressed(12)||pressed(14)||(pad.axes[1]||0)<-.6?-1:pressed(13)||pressed(15)||(pad.axes[1]||0)>.6?1:0;if(direction){focusOption(active+direction);nextMove=now+230;}}
    return true;
  };
})();
