class InterstellarOverviewCard extends HTMLElement {
  setConfig(config) { this.config = { title: "Interstellar Network", ...config }; this.render(); }
  set hass(hass) { this._hass = hass; this.render(); }
  getCardSize() { return 5; }
  static getStubConfig() { return { title: "Interstellar Network" }; }
  _value(group,key) { const s=group.find(x=>x.attributes.interstellar_key===key); return s ? s.state : null; }
  _num(group,key) { const v=parseFloat(this._value(group,key)); return Number.isFinite(v)?v:null; }
  _fmtPct(v){ return v===null?"—":`${v.toFixed(1)}%`; }
  _fmtUptime(sec){ const n=parseFloat(sec); if(!Number.isFinite(n)) return "—"; const d=Math.floor(n/86400),h=Math.floor((n%86400)/3600),m=Math.floor((n%3600)/60); return d?`${d}d ${h}h`:`${h}h ${m}m`; }
  _status(group){ const healthy=group.find(x=>x.attributes.interstellar_key==='system_healthy'); return !healthy||healthy.state==='on'; }
  render(){
    if(!this._hass||!this.config) return;
    const groups={};
    Object.values(this._hass.states).forEach(s=>{ const id=s.attributes.interstellar_network_id; if(!id)return; (groups[id]??=[]).push(s); });
    const servers=Object.values(groups);
    this.innerHTML=`<ha-card><div class="wrap"><div class="title">${this.config.title}</div>${servers.length?`<div class="grid">${servers.map(g=>this._server(g)).join('')}</div>`:'<div class="empty">No Interstellar Network found.</div>'}</div></ha-card><style>
      .wrap{padding:16px}.title{font-size:20px;font-weight:600;margin-bottom:14px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.server{border:1px solid var(--divider-color);border-radius:14px;padding:14px;background:var(--ha-card-background,var(--card-background-color));}.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}.name{font-weight:700;font-size:17px}.dot{width:10px;height:10px;border-radius:50%;background:var(--success-color,#43a047)}.dot.bad{background:var(--error-color,#db4437)}.roles{font-size:12px;color:var(--secondary-text-color);margin-bottom:12px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.metric{background:var(--secondary-background-color);border-radius:10px;padding:8px;text-align:center}.metric .v{font-weight:700}.metric .l{font-size:11px;color:var(--secondary-text-color);margin-top:2px}.footer{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;font-size:12px}.warn{color:var(--warning-color,#ff9800)}.badtext{color:var(--error-color,#db4437)}.empty{color:var(--secondary-text-color)}</style>`;
  }
  _server(g){
    const first=g[0],name=first.attributes.interstellar_hostname||first.attributes.friendly_name||'Server',roles=(first.attributes.interstellar_roles||[]).join(' · ');
    const cpu=this._num(g,'cpu_usage'),ram=this._num(g,'memory_usage'),disk=this._num(g,'root_disk_usage'),up=this._value(g,'uptime');
    const updates=this._value(g,'pending_updates'),security=this._value(g,'pending_security_updates'),failed=this._value(g,'failed_systemd_units');
    const expected=this._value(g,'expected_services_healthy'),reboot=this._value(g,'reboot_required'); const ok=this._status(g);
    let footer=[]; if(parseInt(security||'0')>0)footer.push(`<span class="warn">${security} security update(s)</span>`); if(parseInt(failed||'0')>0)footer.push(`<span class="badtext">${failed} failed unit(s)</span>`); if(expected==='off')footer.push('<span class="badtext">Expected service down</span>'); if(reboot==='on')footer.push('<span class="warn">Reboot required</span>'); if(!footer.length)footer.push(`<span>${updates||0} update(s) pending</span>`);
    return `<div class="server"><div class="head"><div class="name">${name}</div><div class="dot ${ok?'':'bad'}"></div></div><div class="roles">${roles||'general'}</div><div class="metrics"><div class="metric"><div class="v">${this._fmtPct(cpu)}</div><div class="l">CPU</div></div><div class="metric"><div class="v">${this._fmtPct(ram)}</div><div class="l">RAM</div></div><div class="metric"><div class="v">${this._fmtPct(disk)}</div><div class="l">Disk</div></div></div><div class="footer"><span>Uptime ${this._fmtUptime(up)}</span>${footer.join('')}</div></div>`;
  }
}
customElements.define('interstellar-network-card',InterstellarOverviewCard);
window.customCards=window.customCards||[];
window.customCards.push({type:'interstellar-network-card',name:'Interstellar Network',description:'Overview of your Interstellar Network'});
