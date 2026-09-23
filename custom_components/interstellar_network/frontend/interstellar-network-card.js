const INTERSTELLAR_CARD_VERSION = "0.5.1";

const ESC = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const NUM = (v) => v === null || v === undefined || v === "" ? null : Number.isFinite(Number(v)) ? Number(v) : null;
const LIST = (v) => Array.isArray(v) ? v : [];
const NORM = (v) => String(v ?? "").trim().toLocaleLowerCase();
const REPORTED = (v) => v === null || v === undefined || v === "" ? "Not reported" : v;
const BYTES = (v) => { const n=NUM(v); if(n===null)return "Not reported"; let x=n,u=0; while(Math.abs(x)>=1024&&u<4){x/=1024;u++;} return `${x.toFixed(u?1:0)} ${["B","KiB","MiB","GiB","TiB"][u]}`; };
const AGE = (v) => { if(!v)return "Not reported"; const n=Math.max(0,Math.round((Date.now()-Date.parse(v))/1000)); if(!Number.isFinite(n))return "Not reported"; return n<60?`${n}s ago`:n<3600?`${Math.round(n/60)}m ago`:n<86400?`${Math.round(n/3600)}h ago`:`${Math.round(n/86400)}d ago`; };
const UPTIME = (v) => { const n=NUM(v); if(n===null)return "Not reported"; const d=Math.floor(n/86400),h=Math.floor(n%86400/3600),m=Math.floor(n%3600/60); return d?`${d}d ${h}h`:`${h}h ${m}m`; };
const DATE_TIME = (v) => v&&Number.isFinite(Date.parse(v))?new Date(v).toLocaleString():"Not reported";
const SERVICE_LABEL = (v) => ({ssh:"SSH",sshd:"SSH",tailscaled:"Tailscale",docker:"Docker",plex:"Plex",sonarr:"Sonarr",radarr:"Radarr",bazarr:"Bazarr",overseerr:"Overseerr"}[NORM(v)] || String(v).replace(/[-_]/g," ").replace(/\b\w/g,c=>c.toUpperCase()));
const DEFAULT_SHOW = {resources:true,system:true,updates:true,services:true,docker:true,network:true,disks:true,temperatures:true,actions:true,manage:true};
const DEFAULT_COMPACT = {services:true,max_services:8,show_updates:true,show_uptime:true};
const SECTION_KEYS = ["system","updates","services","docker","network","disks","temperatures","actions","manage"];
const DANGEROUS = new Set(["install_security_updates","install_all_updates","reboot","shutdown"]);

class InterstellarNetworkCard extends HTMLElement {
  constructor(){
    super(); this.attachShadow({mode:"open"});
    this._expandedSections=new Map(); this._filter="all"; this._role="all"; this._pendingWake=new Map();
    this._confirmation=null; this._selectedServer=null; this._mode=null; this._notice="";
    this.shadowRoot.addEventListener("click",e=>this._click(e));
    this.shadowRoot.addEventListener("change",e=>this._change(e));
    this.shadowRoot.addEventListener("input",e=>this._input(e));
    this.shadowRoot.addEventListener("keydown",e=>{if(e.key==="Escape"&&this._confirmation){e.stopPropagation();this._confirmation=null;this.render();}});
  }
  setConfig(config){
    const mode=["compact","detailed","fleet"].includes(config.mode)?config.mode:"detailed";
    const next={title:"InterstellarNetwork",full_width:true,default_expanded:{},...config,mode,show:{...DEFAULT_SHOW,...(config.show||{})},compact:{...DEFAULT_COMPACT,...(config.compact||{})}};
    const identity=JSON.stringify({servers:next.servers||null,roles:next.roles||null,mode:next.mode,default_expanded:next.default_expanded});
    if(this._configIdentity!==undefined&&this._configIdentity!==identity){this._expandedSections.clear();this._selectedServer=null;this._filter="all";this._role="all";}
    if(this._mode===null||this._configIdentity!==identity)this._mode=next.mode;
    this._configIdentity=identity; this.config=next; this.render();
  }
  set hass(hass){this._hass=hass;this.render();}
  getCardSize(){return 8;}
  getGridOptions(){return {columns:this.config?.full_width===false?12:"full",min_columns:6};}
  static getStubConfig(){return {title:"InterstellarNetwork",mode:"compact",full_width:true};}

  _model(){
    const states=Object.values(this._hass?.states||{}).filter(s=>s?.attributes?.interstellar_network_id||s?.attributes?.interstellar_key==="server_snapshot");
    const groups=new Map(),aliases=new Map();
    for(const state of states){
      if(state.attributes.interstellar_key!=="server_snapshot")continue;
      const snap=state.attributes.snapshot||{},raw=state.attributes.interstellar_network_id;
      const id=snap.host?.machine_id||raw||state.attributes.interstellar_hostname;
      if(!id)continue; aliases.set(raw,id); if(!groups.has(id))groups.set(id,[]); groups.get(id).push(state);
    }
    for(const state of states){
      if(state.attributes.interstellar_key==="server_snapshot")continue;
      const raw=state.attributes.interstellar_network_id,id=aliases.get(raw)||raw||state.attributes.interstellar_hostname;
      if(!id)continue; if(!groups.has(id))groups.set(id,[]); groups.get(id).push(state);
    }
    const all=[...groups.entries()].map(([id,entities])=>{
      const snap=entities.find(e=>e.attributes.interstellar_key==="server_snapshot");
      const wolEntity=entities.find(e=>e.attributes.interstellar_key==="wake_on_lan_enabled");
      const data=snap?.attributes?.snapshot||{},host=data.host||{},control=data.control||{},policy=control.policy||{},docker=control.docker||{};
      const online=snap?.state==="online",wake={...(wolEntity?.attributes||{}),...(data.wake_on_lan||{})};
      const name=host.hostname||snap?.attributes?.interstellar_hostname||entities[0]?.attributes?.interstellar_hostname||id;
      const roles=LIST(host.roles).length?host.roles:LIST(entities[0]?.attributes?.interstellar_roles);
      const warning=LIST(data.service_policy?.problems).length>0||(NUM(data.system?.failed_systemd_units)||0)>0||(NUM(data.disk_root?.used_percent)||0)>=90||(NUM(data.updates?.pending_security)||0)>0||LIST(docker.containers).some(c=>c.health==="unhealthy")||!!data.system?.reboot_required;
      const available=online&&(control.available===true||control.control_available===true);
      const manageableServices=LIST(policy.manageable_services),manageableContainers=LIST(policy.manageable_containers);
      const wakeTime=Math.max(Date.parse(data.wake_sent_at)||0,this._pendingWake.get(id)||0),waking=!online&&wake.configured===true&&Date.now()-wakeTime<120000;
      const capabilities={
        canRefresh:true,canInstallSecurityUpdates:available,canInstallUpdates:available,
        canManageServices:available&&manageableServices.length>0,canManageDocker:available&&manageableContainers.length>0,
        canRestartHealthAgent:available,canRestartControlAgent:available,canRestartMdns:available,
        canRestartTailscale:available&&LIST(policy.sensitive_services_opt_in).includes("tailscaled"),
        canReboot:available,canShutdown:available,canWake:wake.configured===true,
      };
      if(online&&this._pendingWake.has(id)){this._pendingWake.delete(id);this._notice=`${name} is online.`;}
      return {id,name,roles,entities,data,control,policy,docker,wake,online,waking,status:online?(warning?"problem":"healthy"):"offline",capabilities,manageableServices:new Set(manageableServices),manageableContainers:new Set(manageableContainers)};
    });
    const requested=Array.isArray(this.config?.servers)?this.config.servers.map(v=>({raw:String(v),normalized:NORM(v)})):[];
    let servers=requested.length?all.filter(s=>requested.some(v=>v.normalized===NORM(s.id)||v.normalized===NORM(s.name))):all;
    if(Array.isArray(this.config?.roles)){const roles=new Set(this.config.roles.map(NORM));servers=servers.filter(s=>s.roles.some(r=>roles.has(NORM(r))));}
    const missing=requested.filter(v=>!all.some(s=>v.normalized===NORM(s.id)||v.normalized===NORM(s.name))).map(v=>v.raw);
    servers.sort((a,b)=>({problem:0,offline:1,healthy:2}[a.status]-{problem:0,offline:1,healthy:2}[b.status])||a.name.localeCompare(b.name));
    return {servers,missing};
  }
  _expanded(id,key){
    const state=this._expandedSections.get(id); if(state)return state.has(key);
    const defaults=this.config?.default_expanded; return defaults===true||!!(defaults&&typeof defaults==="object"&&defaults[key]);
  }
  _section(server,key,title,body){return body?`<details class="section" data-server-id="${ESC(server.id)}" data-section="${ESC(key)}" ${this._expanded(server.id,key)?"open":""}><summary>${ESC(title)}</summary><div class="section-body">${body}</div></details>`:"";}
  _pair(k,v){return `<div class="pair"><span>${ESC(k)}</span><strong>${ESC(REPORTED(v))}</strong></div>`;}
  _button(server,action,label,target="",options={}){return `<button class="action ${options.danger?"danger":""}" data-action="${ESC(action)}" data-id="${ESC(server.id)}" data-target="${ESC(target)}" ${options.disabled?"disabled":""} aria-label="${ESC(label)} ${ESC(target||server.name)}">${ESC(label)}</button>`;}
  _bar(label,value,sub=""){const n=NUM(value),width=n===null?0:Math.min(100,Math.max(0,n));return `<div class="bar-row"><div class="bar-head"><span>${ESC(label)}</span><strong>${n===null?"Not reported":`${n.toFixed(0)}%`}</strong></div><div class="track" role="meter" aria-label="${ESC(label)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${width}"><div class="fill ${n>=90?"critical":n>=75?"warning":""}" style="width:${width}%"></div></div>${sub?`<small>${ESC(sub)}</small>`:""}</div>`;}
  _chip(name,state,expected=false){const active=["active","running","healthy","on"].includes(NORM(state)),problem=expected&&!active;return `<span class="service-chip ${active?"active":problem?"problem":"inactive"}"><span aria-hidden="true">${active?"●":"○"}</span> ${ESC(SERVICE_LABEL(name))}</span>`;}

  _compactServices(server){
    if(!this.config.compact.services)return "";
    const expected=new Set(LIST(server.data.service_policy?.expected_services)),expectedContainers=new Set(LIST(server.policy.expected_containers)),items=[];
    for(const [name,state] of Object.entries(server.data.services||{})){
      const relevant=expected.has(name)||server.manageableServices.has(name)||["ssh","sshd","tailscaled","docker"].includes(name)||name.startsWith("interstellar-");
      if(relevant)items.push({name,state,expected:expected.has(name),priority:expected.has(name)?0:server.manageableServices.has(name)?1:2});
    }
    for(const c of LIST(server.docker.containers)){
      if(!c.name||items.some(i=>NORM(i.name)===NORM(c.name)))continue;
      const exp=expectedContainers.has(c.name)||server.manageableContainers.has(c.name); if(exp||c.project)items.push({name:c.name,state:c.health||c.state,expected:exp,priority:exp?0:2});
    }
    const max=Math.max(0,Number(this.config.compact.max_services)||0);
    return `<div class="service-chips">${items.sort((a,b)=>a.priority-b.priority||a.name.localeCompare(b.name)).slice(0,max).map(i=>this._chip(i.name,i.state,i.expected)).join("")}</div>`;
  }
  _compact(server){
    const d=server.data,offline=!server.online,cpu=offline?null:d.cpu?.used_percent,ram=offline?null:d.memory?.used_percent,disk=d.disk_root?.used_percent;
    const statusLabel=server.waking?"Waking…":server.status[0].toUpperCase()+server.status.slice(1);
    return `<button class="compact-server ${server.status}" data-select-server="${ESC(server.id)}" aria-label="Open details for ${ESC(server.name)}"><div class="compact-head"><strong>${ESC(server.name)}</strong><span class="status ${server.status}">${offline?"○":"●"} ${ESC(statusLabel)}</span></div><div class="compact-meta"><span>${ESC(server.roles.join(" · ")||"general")}</span><span>${server.capabilities.canReboot?"🔐 Managed":"👁 Read-only"}</span></div>${offline?`<div class="stale-line">Last seen ${ESC(AGE(d.timestamp_utc))}</div>`:""}<div class="compact-resources"><div><span>CPU</span><strong>${NUM(cpu)===null?"—":`${NUM(cpu).toFixed(0)}%`}</strong></div><div><span>RAM</span><strong>${NUM(ram)===null?"—":`${NUM(ram).toFixed(0)}%`}</strong></div><div><span>Disk</span><strong>${NUM(disk)===null?"—":`${NUM(disk).toFixed(0)}%${offline?"*":""}`}</strong></div></div>${this._compactServices(server)}<div class="compact-footer">${this.config.compact.show_updates?`<span>Updates ${ESC(d.updates?.pending??"—")} · Security ${ESC(d.updates?.pending_security??"—")}</span>`:""}${this.config.compact.show_uptime?`<span>Uptime ${ESC(UPTIME(d.host?.uptime_seconds))}</span>`:""}</div>${offline&&NUM(disk)!==null?"<small>* last known</small>":""}</button>`;
  }

  _system(server){
    if(!this.config.show.system)return ""; const d=server.data,h=d.host||{},sys=d.system||{},c=server.control;
    const failedUnits=LIST(sys.failed_units).map(x=>x.unit).filter(Boolean),failed=failedUnits.length?failedUnits.join(", "):(NUM(sys.failed_systemd_units)||0)>0?`${sys.failed_systemd_units} reported`:"None";
    const reboot=c.last_reboot_action,duration=c.last_reboot_duration_seconds??reboot?.reboot_duration_seconds;
    const rows=[["Hostname",server.name],["Roles",server.roles.join(" · ")||"general"],["Boot time",DATE_TIME(h.boot_time_utc||c.boot_time_utc)],["Uptime",UPTIME(h.uptime_seconds)],["OS",h.os],["Kernel",h.kernel],["Architecture",h.architecture],["Virtualization",h.virtualization],["CPU",d.cpu?.model?`${d.cpu.model} · ${REPORTED(d.cpu?.count)} cores`:null],["Health agent",d.agent_version],["Toolbox",c.toolbox_version],["Control",c.version||c.control_version],["Tailscale",c.tailscale_version||d.network?.tailscale?.version],["Last seen",AGE(d.timestamp_utc)],["Failed units",failed],["OOM kills",sys.oom_kills_since_boot??0],["Last reboot",reboot?`${DATE_TIME(reboot.timestamp)} · ${REPORTED(reboot.status)}`:null],["Reboot duration",duration!==null&&duration!==undefined?UPTIME(duration):null]];
    return this._section(server,"system","System",`<div class="system-grid">${rows.map(([k,v])=>this._pair(k,v)).join("")}</div>`);
  }
  _updates(server){
    if(!this.config.show.updates)return ""; const up=server.data.updates||{},can=server.capabilities;
    const packages=LIST(up.packages).map(p=>`<div class="package"><strong>${ESC(p.name)}</strong><span>${ESC(p.installed_version||"?")} → ${ESC(p.available_version||p.version||"?")}</span><small>${ESC(p.repository||"")}${p.security?" · SECURITY":""}</small></div>`).join("");
    const actions=can.canInstallUpdates?`<div class="actions">${this._button(server,"refresh_packages","Refresh package info")}${can.canInstallSecurityUpdates?this._button(server,"install_security_updates","Install security updates","",{danger:true}):""}${this._button(server,"install_all_updates","Install all updates","",{danger:true})}</div>`:"";
    return this._section(server,"updates","Updates",`<div class="facts">${this._pair("Pending",up.pending??0)}${this._pair("Security",up.pending_security??0)}${this._pair("Apt cache",AGE(up.last_cache_update_utc))}${this._pair("Last updated",AGE(up.last_successful_update_utc))}${this._pair("Reboot required",server.data.system?.reboot_required?"Yes":"No")}</div>${packages?`<details class="nested"><summary>Packages (${LIST(up.packages).length})</summary><div class="package-list">${packages}</div></details>`:""}${actions}`);
  }
  _services(server){
    const names=Object.keys(server.data.services||{}); if(!this.config.show.services||!names.length)return "";
    const expected=new Set(LIST(server.data.service_policy?.expected_services));
    return this._section(server,"services","Services",names.map(name=>{const state=server.data.services[name],manageable=server.capabilities.canManageServices&&server.manageableServices.has(name),last=LIST(server.control.actions).find(a=>a.target===name&&a.action?.startsWith("service_"));return `<div class="service ${expected.has(name)&&state!=="active"?"issue":""}"><strong>${ESC(name)}</strong><span>${ESC(state)}</span><small>${expected.has(name)?"Expected":"Known"}${manageable?" · Manageable":""}${last?` · last ${ESC(last.action.replaceAll("_"," "))}: ${ESC(last.status)}`:""}</small>${manageable?`<span class="inline-actions">${state==="active"?this._button(server,"stop_service","Stop",name,{danger:true}):this._button(server,"start_service","Start",name)}${this._button(server,"restart_service","Restart",name)}</span>`:""}</div>`;}).join(""));
  }
  _docker(server){
    if(!this.config.show.docker||!server.docker.installed)return ""; const d=server.docker;
    const containers=LIST(d.containers).map(c=>{const manageable=server.capabilities.canManageDocker&&server.manageableContainers.has(c.name),last=LIST(server.control.actions).find(a=>a.target===c.name&&a.action?.startsWith("container_"));return `<div class="container ${c.health==="unhealthy"?"issue":""}"><strong>${ESC(c.name)}</strong><span>${ESC(c.state)}${c.health?` · ${ESC(c.health)}`:""}</span><small>${ESC(c.image||"")}${c.project?` · ${ESC(c.project)}`:""}</small><small>${ESC(c.ports||"")}${last?` · last ${ESC(last.action.replaceAll("_"," "))}: ${ESC(last.status)}`:""}</small>${manageable?`<span class="inline-actions">${c.state==="running"?this._button(server,"stop_container","Stop",c.name,{danger:true}):this._button(server,"start_container","Start",c.name)}${this._button(server,"restart_container","Restart",c.name)}</span>`:""}</div>`;}).join("");
    const daemon=server.capabilities.canRestartHealthAgent&&server.manageableServices.has("docker")?`<div class="actions">${this._button(server,"restart_docker","Restart Docker","",{danger:true})}</div>`:"";
    return this._section(server,"docker",`Docker · ${d.version||"version not reported"}`,`<div class="facts">${this._pair("Running",d.running??0)}${this._pair("Stopped",d.stopped??0)}${this._pair("Images",d.images)}${this._pair("Compose",d.compose_version)}${this._pair("Daemon",d.daemon_running?"Running":"Stopped")}</div>${containers}${daemon}`);
  }
  _network(server){
    if(!this.config.show.network)return ""; const n=server.data.network||{},addresses=LIST(n.addresses);
    const interfaces=LIST(n.interfaces).map(i=>`<div class="interface"><strong>${ESC(i.interface)}</strong><span>↓ ${ESC(BYTES(i.rx_bytes_per_second))}/s · ↑ ${ESC(BYTES(i.tx_bytes_per_second))}/s</span>${i.rx_errors||i.tx_errors?`<small>${ESC(i.rx_errors||0)} RX / ${ESC(i.tx_errors||0)} TX errors</small>`:""}</div>`).join("");
    return this._section(server,"network","Network",`${this._pair("LAN",addresses.find(a=>a.kind==="lan")?.address)}${this._pair("Tailscale IP",n.tailscale_ipv4)}${this._pair("MagicDNS",n.tailscale?.magicdns_name)}${this._pair("Connected",n.tailscale?.connected===true?"Yes":n.tailscale?.connected===false?"No":null)}${this._pair("Serve",n.tailscale?.serve_enabled?"Enabled":"Off")}${interfaces}`);
  }
  _disks(server){
    if(!this.config.show.disks)return ""; const files=LIST(server.data.filesystems).map(f=>`<div class="filesystem"><strong>${ESC(f.mountpoint)}</strong>${this._bar("Usage",f.used_percent,`${BYTES(f.used_bytes)} / ${BYTES(f.total_bytes)} · inodes ${REPORTED(f.inode_used_percent)}%`)}</div>`).join(""),io=LIST(server.data.disk_io).map(i=>`<div class="interface"><strong>${ESC(i.device)}</strong><span>Read ${ESC(BYTES(i.read_bytes_per_second))}/s · Write ${ESC(BYTES(i.write_bytes_per_second))}/s</span></div>`).join("");
    return this._section(server,"disks","Disks",files||io?`${files}${io}`:`<p class="muted">Not reported</p>`);
  }
  _manage(server){
    if(!this.config.show.manage)return ""; const can=server.capabilities,managed=Object.entries(can).some(([k,v])=>!["canRefresh","canWake"].includes(k)&&v);
    const quick=`<div class="manage-group"><h4>Quick actions</h4><div class="actions">${this._button(server,"refresh_stats","Refresh stats")}${can.canInstallUpdates?this._button(server,"refresh_packages","Refresh package info"):""}</div></div>`;
    const updates=can.canInstallUpdates?`<div class="manage-group"><h4>Updates</h4><div class="actions">${can.canInstallSecurityUpdates?this._button(server,"install_security_updates","Install security updates","",{danger:true}):""}${this._button(server,"install_all_updates","Install all updates","",{danger:true})}</div></div>`:"";
    const interstellar=managed?`<div class="manage-group"><h4>Interstellar</h4><div class="actions">${can.canRestartHealthAgent?this._button(server,"restart_health_agent","Restart health agent"):""}${can.canRestartControlAgent?this._button(server,"restart_control_agent","Restart control API"):""}${can.canRestartMdns?this._button(server,"restart_mdns","Restart mDNS"):""}${can.canRestartTailscale?this._button(server,"restart_tailscaled","Restart Tailscale"):""}</div></div>`:"";
    const power=can.canReboot||can.canShutdown?`<div class="manage-group"><h4>Server</h4><div class="actions">${can.canReboot?this._button(server,"reboot","Reboot server","",{danger:true}):""}${can.canShutdown?this._button(server,"shutdown","Shutdown server","",{danger:true}):""}</div></div>`:"";
    const wake=!server.online&&can.canWake?`<div class="manage-group"><h4>Server</h4><div class="actions">${this._button(server,"wake",server.waking?"Waking…":"Wake server","",{disabled:server.waking})}</div></div>`:"";
    const readonly=!managed?`<p class="read-only">This server is currently read-only.${server.control.unavailable_reason?` ${ESC(server.control.unavailable_reason)}`:""}</p>`:"";
    return this._section(server,"manage","Manage",`${readonly}${quick}${updates}${interstellar}${power}${wake}`);
  }

  _detailed(server){
    const d=server.data,badges=[]; if((NUM(d.updates?.pending_security)||0)>0)badges.push(`${d.updates.pending_security} security`); if(d.system?.reboot_required)badges.push("Reboot required"); if(LIST(d.service_policy?.problems).length)badges.push("Service down"); if((NUM(d.disk_root?.used_percent)||0)>=90)badges.push("Disk warning"); if((NUM(d.system?.oom_kills_since_boot)||0)>0)badges.push("OOM");
    const resources=this.config.show.resources?`<div class="resources">${this._bar("CPU",d.cpu?.used_percent)}${this._bar("RAM",d.memory?.used_percent,`${BYTES(d.memory?.used_bytes)} / ${BYTES(d.memory?.total_bytes)}`)}${this._bar("Root disk",d.disk_root?.used_percent,`${BYTES(d.disk_root?.used_bytes)} / ${BYTES(d.disk_root?.total_bytes)}`)}${this._bar("Inodes",d.disk_root?.inode_used_percent)}</div>`:"";
    const temperatures=this.config.show.temperatures&&LIST(d.temperatures).length?this._section(server,"temperatures","Temperatures",LIST(d.temperatures).map(t=>this._pair(t.name,`${t.celsius}°C`)).join("")):"";
    const actions=this.config.show.actions&&LIST(server.control.actions).length?this._section(server,"actions","Recent actions",LIST(server.control.actions).slice(0,5).map(a=>`<div class="history"><time>${ESC(AGE(a.timestamp))}</time><strong>${ESC(a.action?.replaceAll("_"," "))}</strong><span>${ESC(a.status)}${a.error?` · ${ESC(a.error)}`:""}</span></div>`).join("")):"";
    return `<article class="detailed-server ${server.status} ${this._selectedServer===server.id?"selected":""}" data-server="${ESC(server.id)}"><header class="server-head"><div><div class="server-title"><h3>${ESC(server.name)}</h3><span class="status ${server.status}">${server.online?"●":"○"} ${ESC(server.waking?"Waking…":server.status)}</span><span class="access" title="${ESC(server.control.unavailable_reason||"")}">${server.capabilities.canReboot?"🔐 Managed":"👁 Read-only"}</span></div><div class="muted">${ESC(server.roles.join(" · ")||"general")} · Last seen ${ESC(AGE(d.timestamp_utc))}</div></div><div class="head-metrics"><span>CPU ${ESC(d.cpu?.used_percent??"—")}%</span><span>RAM ${ESC(d.memory?.used_percent??"—")}%</span><span>Disk ${ESC(d.disk_root?.used_percent??"—")}%</span></div></header><div class="server-body">${!server.online?'<div class="stale-banner">Offline · values below are last reported data.</div>':""}${badges.length?`<div class="badges">${badges.map(x=>`<span>${ESC(x)}</span>`).join("")}</div>`:""}${resources}${this._system(server)}${this._updates(server)}${this._services(server)}${this._docker(server)}${this._network(server)}${this._disks(server)}${temperatures}${actions}${this._manage(server)}</div></article>`;
  }
  _confirmMarkup(servers){
    if(!this._confirmation)return ""; const server=servers.find(s=>s.id===this._confirmation.serverId); if(!server)return "";
    const action=this._confirmation.action,power=["reboot","shutdown"].includes(action); let text=`Apply ${action.replaceAll("_"," ")} to ${server.name}?`;
    if(action==="shutdown")text=server.capabilities.canWake?"The server will go offline. Server can be woken again from Home Assistant.":"The server will go offline. Wake-on-LAN is unavailable; external or physical access may be needed to start it again.";
    if(action==="reboot")text="The server will go offline while it restarts."; if(action==="install_security_updates")text="Install all currently reported security updates?"; if(action==="install_all_updates")text="Install all currently reported package updates?";
    return `<dialog class="confirm-dialog" aria-labelledby="confirm-title"><h3 id="confirm-title">Confirm ${ESC(action.replaceAll("_"," "))}</h3><p id="confirm-text">${ESC(text)}</p>${power?`<label class="confirm-label">Type the hostname <strong>${ESC(server.name)}</strong><input id="confirm-input" value="${ESC(this._confirmation.input||"")}" autocomplete="off"></label>`:""}<div class="modal-actions"><button data-modal="cancel">Cancel</button><button data-modal="confirm" class="danger">Confirm</button></div></dialog>`;
  }

  render(){
    if(!this._hass||!this.config)return; const {servers,missing}=this._model();
    if(this._selectedServer&&!servers.some(s=>s.id===this._selectedServer))this._selectedServer=null; if(!this._selectedServer&&servers.length)this._selectedServer=servers[0].id;
    const visible=servers.filter(s=>(this._filter==="all"||s.status===this._filter)&&(this._role==="all"||s.roles.includes(this._role))),roles=[...new Set(servers.flatMap(s=>s.roles))].sort();
    const totals={healthy:servers.filter(s=>s.status==="healthy").length,problem:servers.filter(s=>s.status==="problem").length,offline:servers.filter(s=>s.status==="offline").length,updates:servers.reduce((n,s)=>n+(NUM(s.data.updates?.pending)||0),0),security:servers.reduce((n,s)=>n+(NUM(s.data.updates?.pending_security)||0),0)};
    const compact=`<div class="compact-grid">${visible.map(s=>this._compact(s)).join("")}</div>`,detailedServers=this._mode==="fleet"?visible.filter(s=>s.id===this._selectedServer):visible,detailed=`<div class="detailed-grid">${detailedServers.map(s=>this._detailed(s)).join("")}</div>`,content=this._mode==="compact"?compact:this._mode==="fleet"?`${compact}${detailed}`:detailed;
    this.shadowRoot.innerHTML=`<ha-card><div class="wrap"><header class="card-head"><div><h2>${ESC(this.config.title)}</h2><div class="muted">${servers.length} servers · ${totals.healthy} healthy · ${totals.problem} warning · ${totals.offline} offline</div></div><div class="mode-switch" role="group" aria-label="Card layout">${["compact","detailed","fleet"].map(m=>`<button data-mode="${m}" aria-pressed="${this._mode===m}">${m}</button>`).join("")}</div></header>${this._notice?`<div class="notice" role="status">${ESC(this._notice)}</div>`:""}${missing.map(s=>`<div class="config-warning" role="alert">Configured server not found: ${ESC(s)}</div>`).join("")}<div class="fleet-summary"><div><strong>${totals.updates}</strong><span>Updates</span></div><div><strong>${totals.security}</strong><span>Security</span></div></div><div class="filters"><div role="group" aria-label="Status filter">${["all","healthy","problem","offline"].map(f=>`<button data-filter="${f}" aria-pressed="${this._filter===f}">${f}</button>`).join("")}</div>${roles.length>1?`<label>Role <select id="role"><option value="all">All roles</option>${roles.map(r=>`<option value="${ESC(r)}" ${this._role===r?"selected":""}>${ESC(r)}</option>`).join("")}</select></label>`:""}</div>${visible.length?content:'<p class="muted empty">No matching servers.</p>'}</div></ha-card>${this._confirmMarkup(servers)}<style>${this._css()}</style>`;
    const dialog=this.shadowRoot.querySelector(".confirm-dialog"); if(dialog){if(typeof dialog.showModal==="function")dialog.showModal();else dialog.setAttribute("open","");}
  }
  _setExpanded(id,key,open){let set=this._expandedSections.get(id);if(!set){set=new Set(SECTION_KEYS.filter(k=>this._expanded(id,k)));this._expandedSections.set(id,set);}if(open)set.add(key);else set.delete(key);}
  _change(e){if(e.target.id!=="role")return;e.stopPropagation();this._role=e.target.value;this.render();}
  _input(e){if(e.target.id==="confirm-input"&&this._confirmation)this._confirmation.input=e.target.value;}
  async _click(e){
    const summary=e.target.closest("summary"); const section=summary?.closest("details.section");
    if(section){e.preventDefault();e.stopPropagation();const id=section.dataset.serverId,key=section.dataset.section,open=!section.open;section.open=open;this._setExpanded(id,key,open);this.render();return;}
    const el=e.target.closest("button,[data-action]"); if(!el)return; e.stopPropagation();
    if(el.dataset.mode){this._mode=el.dataset.mode;this.render();return;} if(el.dataset.filter){this._filter=el.dataset.filter;this.render();return;}
    if(el.dataset.selectServer){this._selectedServer=el.dataset.selectServer;if(this._mode==="compact")this._mode="detailed";this.render();return;}
    if(el.dataset.modal){e.preventDefault();if(el.dataset.modal==="cancel"){this._confirmation=null;this.render();return;}const pending=this._confirmation,server=this._model().servers.find(s=>s.id===pending?.serverId);if(!pending||!server)return;const power=["reboot","shutdown"].includes(pending.action);if(power&&pending.input!==server.name){this._notice=`Type ${server.name} to confirm.`;this.render();return;}this._confirmation=null;await this._perform(server,pending.action,pending.target,power?server.name:"");return;}
    if(!el.dataset.action)return;e.preventDefault();const server=this._model().servers.find(s=>s.id===el.dataset.id);if(!server)return;const action=el.dataset.action,target=el.dataset.target||"";if(DANGEROUS.has(action)){this._confirmation={serverId:server.id,action,target,input:""};this.render();return;}await this._perform(server,action,target);
  }
  async _perform(server,action,target="",confirmation=""){
    if(action==="wake"){if(!server.capabilities.canWake)return;try{await this._hass.callService("interstellar_network","wake",{server:server.id});this._pendingWake.set(server.id,Date.now());this._notice=`Wake packet sent to ${server.name}. Waiting for the health agent.`;this.render();setTimeout(()=>{if(this._pendingWake.has(server.id)){this._notice=`Wake packet sent to ${server.name}; the server has not returned yet.`;this.render();}},120000);}catch(err){this._notice=`Wake failed: ${err.message||err}`;this.render();}return;}
    try{await this._hass.callService("interstellar_network","manage",{server:server.id,action,target,confirmation});this._notice=`${action.replaceAll("_"," ")} submitted for ${server.name}.`;}catch(err){this._notice=`Action failed: ${err.message||err}`;}this.render();
  }
  _css(){return `:host{display:block;width:100%;max-width:none;color:var(--primary-text-color)}*{box-sizing:border-box}ha-card{display:block;width:100%;max-width:none;overflow:hidden}.wrap{width:100%;padding:20px}.card-head,.server-head,.compact-head,.compact-meta,.bar-head,.pair,.interface,.history{display:flex;justify-content:space-between;gap:10px}.card-head{align-items:flex-start;flex-wrap:wrap}h2,h3,h4{margin:0}h2{font-size:1.35rem}h3{font-size:1.1rem}.muted,small{color:var(--secondary-text-color);font-size:.8rem}.notice,.config-warning,.stale-banner{margin-top:12px;padding:10px;border-radius:8px;background:var(--secondary-background-color);font-size:.82rem}.config-warning{border-left:4px solid var(--warning-color,#f9a825)}.stale-banner{margin:0 0 12px}.mode-switch,.filters>div,.actions,.inline-actions,.service-chips{display:flex;gap:6px;flex-wrap:wrap}button,select{font:inherit;color:var(--primary-text-color);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:8px;min-height:40px;padding:7px 11px;cursor:pointer}button:hover{background:var(--secondary-background-color)}button[aria-pressed=true]{border-color:var(--primary-color);color:var(--primary-color)}button:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}button.danger{color:var(--error-color,#c62828)}button:disabled{cursor:wait;opacity:.65}.fleet-summary{display:flex;gap:8px;margin:16px 0}.fleet-summary>div{display:flex;gap:7px;align-items:baseline;background:var(--secondary-background-color);padding:8px 12px;border-radius:9px}.fleet-summary span{font-size:.76rem;color:var(--secondary-text-color)}.filters{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px}.compact-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,270px),1fr));gap:12px}.compact-server{display:block;text-align:left;width:100%;min-height:0;padding:15px;border-radius:12px;background:var(--card-background-color);border:1px solid var(--divider-color)}.compact-server.problem,.detailed-server.problem{border-left:4px solid var(--warning-color,#f9a825)}.compact-server.offline,.detailed-server.offline{border-left:4px solid var(--error-color,#c62828)}.compact-head{align-items:center}.compact-head strong{font-size:1.05rem}.compact-meta,.stale-line,.compact-footer{margin-top:5px;color:var(--secondary-text-color);font-size:.76rem}.compact-resources{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}.compact-resources>div{background:var(--secondary-background-color);border-radius:8px;padding:8px;text-align:center;display:grid;gap:2px}.compact-resources span{font-size:.7rem;color:var(--secondary-text-color)}.service-chips{margin:10px 0}.service-chip{padding:4px 7px;border-radius:99px;background:var(--secondary-background-color);font-size:.74rem}.service-chip.active{color:var(--success-color,#2e7d32)}.service-chip.problem{color:var(--error-color,#c62828)}.service-chip.inactive{color:var(--secondary-text-color)}.compact-footer{display:flex;justify-content:space-between;flex-wrap:wrap;gap:5px}.detailed-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:14px}.compact-grid+.detailed-grid{margin-top:16px}.detailed-server{border:1px solid var(--divider-color);border-radius:12px;min-width:0;overflow:hidden}.detailed-server.selected{box-shadow:0 0 0 1px var(--primary-color)}.server-head{padding:15px;align-items:flex-start}.server-title{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:5px}.status{font-size:.76rem;text-transform:capitalize}.status.healthy{color:var(--success-color,#2e7d32)}.status.problem{color:var(--warning-color,#b8860b)}.status.offline{color:var(--error-color,#c62828)}.access{font-size:.74rem;color:var(--secondary-text-color)}.head-metrics{display:flex;flex-direction:column;gap:4px;text-align:right;white-space:nowrap;color:var(--secondary-text-color);font-size:.72rem}.server-body{padding:0 15px 15px}.badges{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:10px}.badges span{font-size:.68rem;padding:3px 6px;border-radius:5px;background:var(--warning-color,#f9a825);color:var(--text-primary-color,#fff)}.resources{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:9px}.bar-head,.pair{font-size:.8rem}.track{height:7px;border-radius:9px;background:var(--divider-color);overflow:hidden;margin:5px 0}.fill{height:100%;background:var(--primary-color);border-radius:9px}.fill.warning{background:var(--warning-color,#f9a825)}.fill.critical{background:var(--error-color,#c62828)}.section{border-top:1px solid var(--divider-color);padding:9px 0}.section>summary{cursor:pointer;font-weight:600;padding:2px 0}.section-body{padding-top:10px;display:grid;gap:8px}.system-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px 18px}.pair span{color:var(--secondary-text-color)}.pair strong{text-align:right;overflow-wrap:anywhere}.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.package,.service,.container{display:grid;gap:3px;border-top:1px solid var(--divider-color);padding:8px 0;font-size:.82rem}.service{grid-template-columns:1fr auto}.service small,.service .inline-actions{grid-column:1/-1}.issue{color:var(--error-color,#c62828)}.actions{margin-top:7px}.action{font-size:.78rem}.interface,.history{font-size:.8rem;flex-wrap:wrap}.interface small{width:100%}.filesystem{padding-bottom:7px}.filesystem>.bar-row{margin-top:5px}.nested summary{cursor:pointer}.package-list{max-height:280px;overflow:auto}.manage-group{display:grid;gap:2px}.manage-group h4{font-size:.8rem;color:var(--secondary-text-color)}.read-only{margin:0;color:var(--secondary-text-color);font-size:.84rem}.empty{padding:20px 0}.confirm-dialog{border:1px solid var(--divider-color);border-radius:12px;background:var(--card-background-color);color:var(--primary-text-color);max-width:min(90vw,430px);padding:20px;box-shadow:0 8px 24px #0004}.confirm-dialog::backdrop{background:#0009}.confirm-dialog h3{margin-bottom:8px}.confirm-label{display:grid;gap:6px}.confirm-label input{font:inherit;padding:10px;background:var(--secondary-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:8px}.modal-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}@media(max-width:700px){.wrap{padding:12px}.detailed-grid,.compact-grid{grid-template-columns:1fr}.server-head{padding:12px}.server-body{padding:0 12px 12px}.system-grid{grid-template-columns:1fr}.resources{gap:8px}.mode-switch{width:100%}.mode-switch button{flex:1}}`;}
}

if(!customElements.get("interstellar-network-card"))customElements.define("interstellar-network-card",InterstellarNetworkCard);
if(!customElements.get("interstellar-overview-card"))customElements.define("interstellar-overview-card",class extends InterstellarNetworkCard{});
window.customCards=window.customCards||[];
for(const type of ["interstellar-network-card","interstellar-overview-card"]){if(!window.customCards.some(card=>card.type===type))window.customCards.push({type,name:"InterstellarNetwork",description:`Monitor and manage Interstellar servers (v${INTERSTELLAR_CARD_VERSION})`});}
window.interstellarNetworkCardVersion=INTERSTELLAR_CARD_VERSION;
console.info(`InterstellarNetwork card v${INTERSTELLAR_CARD_VERSION}`);
