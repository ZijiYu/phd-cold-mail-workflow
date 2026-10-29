/* 套磁工作台 - vanilla JS client for the dashboard REST API. */
(() => {
  "use strict";

  // ------------------------------------------------------------ constants
  const TOKEN = document.querySelector('meta[name="api-token"]').content;
  const STATUS = {
    researching: "调研中", drafted: "已起草", approved: "已定稿", sent: "已发送",
    replied: "已回复", meeting_scheduled: "已约会谈", apply_and_mention: "申请时提名",
    redirected: "被转介", bounced: "退信", blocked: "卡住", closed: "已结束",
  };
  const ORDER = ["replied", "meeting_scheduled", "apply_and_mention", "redirected", "approved", "sent",
                 "drafted", "researching", "blocked", "bounced", "closed"];
  const STAGES = [
    { key: "research", title: "调研", statuses: ["researching"], cls: "st-researching" },
    { key: "draft", title: "起草", statuses: ["drafted"], cls: "st-drafted" },
    { key: "approve", title: "定稿", statuses: ["approved"], cls: "st-approved" },
    { key: "sent", title: "已发送", statuses: ["sent"], cls: "st-sent" },
    { key: "reply", title: "有回音", statuses: ["replied", "meeting_scheduled", "apply_and_mention", "redirected"], cls: "st-replied" },
  ];
  const OFFRAMP = ["blocked", "bounced", "closed"];
  const CONTACTED = new Set(["sent", "replied", "meeting_scheduled", "apply_and_mention", "redirected", "bounced"]);
  const DRAFT_KIND = { first: "首封", followup: "跟进", reply: "回复" };

  // ------------------------------------------------------------ state
  const S = {
    campaigns: [], campaign: "", summary: null, targets: [], programs: [], gmail: null,
    filter: "all", search: "",
    detail: null, tab: "letter", draftName: "", draft: null, dirty: false, check: null,
  };
  const $ = (sel, root = document) => root.querySelector(sel);
  const main = $("#main");

  // ------------------------------------------------------------ helpers
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const attr = esc;

  async function api(method, path, body) {
    const res = await fetch(`/api${path}`, {
      method,
      headers: { "Authorization": `Bearer ${TOKEN}`, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const data = res.status === 204 ? null : await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).join("；") : data?.detail;
      const err = new Error(detail || `请求失败（${res.status}）`);
      err.code = data?.code || "";
      if (err.code === "gmail_reauth" || err.code === "missing_scope") loadGmail();
      throw err;
    }
    return data;
  }
  const C = () => `/campaigns/${encodeURIComponent(S.campaign)}`;
  const T = (id) => `${C()}/targets/${encodeURIComponent(id)}`;

  let toastTimer;
  function toast(msg, bad = false) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = `toast show${bad ? " bad" : ""}`;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.className = "toast"), bad ? 6000 : 3200);
  }
  const fail = (e) => toast(e.message || String(e), true);

  const todayISO = () => new Date().toISOString().slice(0, 10);
  function daysUntil(iso) {
    if (!iso) return null;
    const d = new Date(iso + "T00:00:00"), t = new Date(todayISO() + "T00:00:00");
    return Math.round((d - t) / 86400000);
  }
  const md = (iso) => (iso ? `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}` : "");
  const statusLabel = (s) => STATUS[s] || s || "未知";
  const dot = (s) => `<span class="dot st-${attr(s)}" aria-hidden="true"></span>`;
  const slug = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[^\w\s-]/g, "").trim().replace(/[\s_]+/g, "-").replace(/-+/g, "-");

  function issuesFor(id) { return (S.summary?.issues || []).filter((i) => i.target_id === id); }
  function isDue(id) { return (S.summary?.due || []).some((d) => d.target_id === id); }

  function actionFor(t) {
    if (t._suggestion) return { kind: "Gmail", tone: "var(--postmark)", text: t._suggestion.reason };
    if (isDue(t.target_id)) return { kind: "该跟进", tone: "var(--s-stop)", text: `跟进日期 ${md(t.follow_up_due)} 已到，首封发于 ${md(t.sent_at)}` };
    switch (t.status) {
      case "replied": return { kind: "回复", tone: "var(--s-replied)", text: t.next_action || "教授回信了，等你回复" };
      case "meeting_scheduled": return { kind: "会谈", tone: "var(--s-replied)", text: t.next_action || t.response_summary || "准备会谈 brief" };
      case "apply_and_mention": return { kind: "申请", tone: "var(--s-replied)", text: t.next_action || "提交申请时把教授列为意向导师" };
      case "redirected": return { kind: "转介", tone: "var(--s-replied)", text: t.next_action || "调研被推荐的老师，单独写信" };
      case "approved": return { kind: "待发送", tone: "var(--s-approved)", text: t.next_action || "推送到 Gmail 草稿箱，检查后发送" };
      case "bounced": return { kind: "退信", tone: "var(--s-stop)", text: "邮箱地址可能有误，先从官方页面重新核实" };
      case "blocked": return { kind: "卡住", tone: "var(--s-stop)", text: t.next_action || "缺少必要信息" };
    }
    const errs = issuesFor(t.target_id).filter((i) => i.level === "error");
    if (errs.length) return { kind: "数据", tone: "var(--s-stop)", text: errs[0].message };
    const stale = issuesFor(t.target_id).find((i) => /re-verify|never verified/.test(i.message));
    if (stale) return { kind: "核实", tone: "var(--s-drafted)", text: "信息超过 30 天没核实，发送前再查一次" };
    return null;
  }

  // ------------------------------------------------------------ loading
  async function loadCampaign() {
    const [summary, targets, programs] = await Promise.all([
      api("GET", `${C()}/summary`), api("GET", `${C()}/targets`), api("GET", `${C()}/programs`),
    ]);
    Object.assign(S, { summary, targets, programs });
    const c = S.campaigns.find((x) => x.id === S.campaign);
    if (c && c.targets !== targets.length) { c.targets = targets.length; renderCampaignSelect(); }
    renderTree();
  }

  async function loadGmail() {
    try { S.gmail = await api("GET", "/gmail/status"); } catch (e) { S.gmail = null; }
    renderGmailPill();
  }

  // ------------------------------------------------------------ sidebar
  function visibleTargets() {
    const q = S.search.trim().toLowerCase();
    return S.targets.filter((t) => {
      if (q && ![t.professor, t.institution, t.department, t.email, t.research_anchor].some((v) => (v || "").toLowerCase().includes(q))) return false;
      if (S.filter === "action") return !!actionFor(t);
      if (S.filter === "active") return t.status !== "closed";
      if (S.filter === "done") return t.status === "closed";
      return true;
    });
  }

  function renderTree() {
    const tree = $("#tree");
    const list = visibleTargets();
    if (!S.targets.length) { tree.innerHTML = `<p class="empty-side">这个申请季还没有教授。点下面的“添加教授”，或让 skill 先跑一遍选导师。</p>`; return; }
    if (!list.length) { tree.innerHTML = `<p class="empty-side">没有符合条件的教授。</p>`; return; }

    const order = (S.summary?.schools || []).map((s) => s.institution);
    const groups = new Map();
    for (const t of list) {
      const k = t.institution || "(未填学校)";
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(t);
    }
    const keys = [...groups.keys()].sort((a, b) => (order.indexOf(a) + 999 * (order.indexOf(a) < 0)) - (order.indexOf(b) + 999 * (order.indexOf(b) < 0)));
    const current = S.detail?.target?.target_id;

    tree.innerHTML = keys.map((inst) => {
      const school = (S.summary?.schools || []).find((s) => s.institution === inst) || {};
      const left = daysUntil(school.deadline);
      const meta = [];
      if (school.tiers?.length) meta.push(school.tiers.map(tierLabel).join("/"));
      if (school.deadline) meta.push(`<span class="${left !== null && left <= 21 ? "soon" : ""}">截止 ${md(school.deadline)}${left !== null && left >= 0 ? `，还剩 ${left} 天` : left < 0 ? "，已过" : ""}</span>`);
      const profs = groups.get(inst).sort((a, b) => ORDER.indexOf(a.status) - ORDER.indexOf(b.status));
      meta.push(`${profs.length} 位`);
      return `<section class="school ${rankClass(school.rank)}">
        <div class="school-head">
          <h2 class="school-name">${esc(inst)}</h2>
          ${rankBadge(school.rank)}
        </div>
        <p class="school-meta">${meta.join("　")}</p>
      </section>
      ${profs.map((t) => {
        const a = actionFor(t);
        const flag = t._suggestion ? `<span class="flag">Gmail</span>` : isDue(t.target_id) ? `<span class="flag warn">该跟进</span>`
          : issuesFor(t.target_id).some((i) => i.level === "error") ? `<span class="flag warn">待修</span>` : "";
        return `<a class="prof${t.target_id === current ? " is-current" : ""}" href="#/t/${encodeURIComponent(t.target_id)}" ${t.target_id === current ? 'aria-current="page"' : ""}>
          ${dot(t.status)}
          <span class="prof-name">${esc(t.professor)}<span class="prof-status">${esc(statusLabel(t.status))}${a && !flag ? "，待处理" : ""}</span></span>
          ${flag}
        </a>`;
      }).join("")}`;
    }).join("");
  }

  const tierLabel = (t) => ({ reach: "冲", match: "稳", safety: "保" }[t] || t);

  // CSRankings (US). Bands: top 20, 21-50, 51+.
  const rankClass = (r) => !r?.cs ? "rank-none" : r.cs <= 20 ? "rank-top" : r.cs <= 50 ? "rank-mid" : "rank-rest";
  function rankTitle(r) {
    const m = S.summary?.rankings || {};
    return `CSRankings 美国排名（${m.years || "近十年"}）：综合 #${r.cs ?? "—"}，AI 方向 #${r.ai ?? "—"}。CSRankings 名称：${r.name}`;
  }
  function rankBadge(r) {
    if (!r) return `<span class="rank-badge is-empty" title="CSRankings 里没有找到这所学校">未排名</span>`;
    return `<span class="rank-badge" title="${attr(rankTitle(r))}"><span class="rk-cs">#${r.cs ?? "—"}</span><span class="rk-ai">AI #${r.ai ?? "—"}</span></span>`;
  }

  // ------------------------------------------------------------ gmail pill
  function renderGmailPill() {
    const el = $("#gmail-pill"), sync = $("#sync-btn");
    const g = S.gmail;
    if (!g) { el.innerHTML = ""; sync.disabled = true; return; }
    if (!g.configured) {
      el.innerHTML = `<button class="btn btn-accent" data-act="gmail-setup">连接 Gmail</button>`;
    } else if (!g.connected && g.reauth) {
      el.innerHTML = `<span class="gmail-pill warn"><span class="dot"></span>Gmail 授权已过期</span> <button class="btn btn-accent" data-act="gmail-connect">重新连接</button>`;
    } else if (!g.connected) {
      el.innerHTML = `<button class="btn btn-accent" data-act="gmail-connect">连接 Gmail</button> <button class="btn btn-quiet" data-act="gmail-menu" aria-label="Gmail 选项">…</button>`;
    } else {
      const partial = !g.can_draft ? `<span class="gmail-pill warn" title="缺少管理草稿权限，重新连接时勾选两项">缺草稿权限</span>` : "";
      el.innerHTML = `<span class="gmail-pill on"><span class="dot"></span>${esc(g.email || "Gmail 已连接")}</span>${partial} <button class="btn btn-quiet" data-act="gmail-menu" aria-label="Gmail 选项">…</button>`;
    }
    sync.disabled = !g.connected;
  }

  // ------------------------------------------------------------ overview
  function renderOverview() {
    S.detail = null;
    $("#crumb").textContent = "总览";
    renderTree();
    const sm = S.summary;
    if (!sm) return;
    if (!sm.total) {
      main.innerHTML = `<div class="lede"><h1>${esc(campaignLabel(S.campaign))} 套磁</h1>
        <p>这个申请季还没有教授。可以在这里手动添加，或者让 skill 跑一遍选校、选导师，把结果写进 <code>outreach/${esc(S.campaign)}/targets.csv</code>，刷新页面就会出现。</p></div>
        <p><button class="btn btn-accent" data-act="add-target">添加教授</button></p>`;
      return;
    }
    const due = sm.due.length;
    const actions = S.targets.map((t) => ({ t, a: actionFor(t) })).filter((x) => x.a);
    const rate = sm.reply_rate === null ? "" : `，回复率 ${Math.round(sm.reply_rate * 100)}%`;

    const STAGE_CAP = 8;
    const stages = STAGES.map((st) => {
      const items = S.targets.filter((t) => st.statuses.includes(t.status));
      const shown = items.slice(0, STAGE_CAP);
      const more = items.length - shown.length;
      return `<div class="stage ${st.cls}${items.length ? " has-items" : ""}">
        <div class="stage-head"><span class="node"></span><span class="stage-title">${st.title}</span><span class="stage-count">${items.length}</span></div>
        <ul class="stage-items">${shown.map((t) => `<li><a href="#/t/${encodeURIComponent(t.target_id)}"><span class="n">${esc(t.professor)}</span><span class="s">${esc(shortSchool(t.institution))}${st.key === "reply" && t.status !== "replied" ? `，${esc(statusLabel(t.status))}` : ""}</span></a></li>`).join("")}${more > 0 ? `<li class="stage-more">还有 ${more} 位，见左侧列表</li>` : ""}</ul>
      </div>`;
    }).join("");
    const off = S.targets.filter((t) => OFFRAMP.includes(t.status));

    main.innerHTML = `
      <div class="lede">
        <h1>${esc(campaignLabel(S.campaign))} 套磁</h1>
        <p>共 <strong>${sm.total}</strong> 位教授，分布在 <strong>${sm.schools.length}</strong> 所学校。已联系 <strong>${sm.contacted}</strong> 位，<strong>${sm.replied}</strong> 位有回音${rate}。${due ? `今天有 <strong>${due}</strong> 封跟进到期。` : "今天没有到期的跟进。"}</p>
      </div>

      <section class="route" aria-label="套磁进度">
        <div class="route-track">${stages}</div>
        ${off.length ? `<div class="offramp"><span>未继续：</span>${off.map((t) => `<a href="#/t/${encodeURIComponent(t.target_id)}">${esc(t.professor)}（${esc(statusLabel(t.status))}）</a>`).join("")}</div>` : ""}
      </section>

      <div class="two-col">
        <section>
          <h2 class="section-title">需要处理</h2>
          ${actions.length ? `<ul class="todo">${actions.map(({ t, a }) => `
            <li><a href="#/t/${encodeURIComponent(t.target_id)}">
              <span class="todo-kind" style="--kind:${a.tone}">${esc(a.kind)}</span>
              <span><span class="todo-who">${esc(t.professor)}</span><span class="todo-what">${esc(shortSchool(t.institution))}：${esc(a.text)}</span></span>
            </a></li>`).join("")}</ul>` : `<p class="todo-empty">没有待处理的事项。</p>`}
          ${sm.issues.filter((i) => !i.target_id).map((i) => `<p class="hint">${i.level === "error" ? "错误" : "提醒"}：${esc(i.message)}</p>`).join("")}
        </section>
        <section>
          <h2 class="section-title">学校</h2>
          <table class="schools">
            <thead><tr><th title="CSRankings 美国：综合 / AI 方向">排名</th><th>学校</th><th>截止</th><th>已联系</th><th>回音</th></tr></thead>
            <tbody>${sm.schools.map((s) => {
              const left = daysUntil(s.deadline);
              return `<tr class="${rankClass(s.rank)}">
                <td class="num rank-cell">${rankBadge(s.rank)}</td>
                <td><span class="inst">${esc(s.institution)}</span><br><span class="tier">${esc((s.tiers || []).map(tierLabel).join("/") || "未分档")}${s.programs.length ? `，${esc(s.programs.join("，"))}` : ""}</span></td>
                <td class="num">${s.deadline ? `${md(s.deadline)}<br><span class="tier">${left >= 0 ? `${left} 天` : "已过"}</span>` : "未填"}</td>
                <td class="num">${s.contacted}/${s.total}<div class="bar"><span style="width:${s.total ? (100 * s.contacted / s.total) : 0}%"></span></div></td>
                <td class="num">${s.replied}</td>
              </tr>`;
            }).join("")}</tbody>
          </table>
          ${sm.rankings?.years ? `<p class="hint">排名来自 CSRankings 美国榜（${esc(sm.rankings.years)}，数据 ${esc(sm.rankings.data_version || "")}）：前一个数字是综合排名，后一个是 AI 方向（AI、视觉、ML、NLP、信息检索）。</p>` : ""}
        </section>
      </div>`;
  }
  const shortSchool = (s) => String(s || "").replace(/\s+(University|Institute of Technology|College of Engineering)$/i, "").trim() || s;

  // ------------------------------------------------------------ detail
  async function openTarget(id, tab) {
    if (S.dirty && S.detail?.target?.target_id !== id && !confirm("当前草稿还没保存，确定离开吗？")) { history.back(); return; }
    try {
      const d = await api("GET", T(id));
      const same = S.detail?.target?.target_id === id;
      const keepDraft = same ? S.draftName : "";
      S.tab = tab || (same && S.tab) || "letter";
      S.detail = d; S.dirty = false;
      const names = d.drafts.map((x) => x.name);
      S.draftName = names.includes(keepDraft) ? keepDraft : (d.drafts.find((x) => x.primary) || d.drafts[0] || {}).name || "";
      S.draft = null; S.check = null;
      $("#crumb").textContent = `总览 / ${d.target.professor}`;
      renderTree();
      renderDetail();
      if (S.tab === "letter" && S.draftName) await loadDraft();
      if (S.tab === "thread") loadThread();
    } catch (e) {
      main.innerHTML = `<div class="empty-main"><h1>找不到这位教授</h1><p>${esc(e.message)}</p><p><a href="#/">回到总览</a></p></div>`;
    }
  }

  function statusActions(t) {
    const b = [];
    switch (t.status) {
      case "researching": if (!S.detail.drafts.length) b.push(["new-first", "开始写首封", "btn-accent"]); break;
      case "drafted": b.push(["set:approved", "确认定稿", "btn-accent"]); break;
      case "approved": b.push(["mark-sent", "标记已发送", "btn-accent"], ["set:drafted", "退回修改", "btn-quiet"]); break;
      case "sent": b.push(["mark-replied", "记录回信", "btn-accent"]); break;
      case "replied": b.push(["set:meeting_scheduled", "已约会谈", "btn-quiet"], ["set:apply_and_mention", "让我申请时提名", "btn-quiet"]); break;
    }
    b.push(["status-dialog", "更改状态", "btn-quiet"]);
    return b.map(([act, label, cls]) => `<button class="btn ${cls}" data-act="${act}">${label}</button>`).join("");
  }

  function renderDetail() {
    const { target: t, gmail } = S.detail;
    const issues = S.detail.issues || [];
    const sug = gmail?.suggestion;
    main.innerHTML = `
      <div class="detail-head">
        <div class="detail-title">
          <h1>${esc(t.professor)}</h1>
          <p class="detail-school">${esc(t.institution)}${t.department ? `，${esc(t.department)}` : ""}${t.program_id ? `（${esc(t.program_id)}）` : ""}
            ${rankBadge((S.summary?.schools || []).find((s) => s.institution === t.institution)?.rank)}</p>
          <div class="contact">
            ${t.email ? `<a href="mailto:${attr(t.email)}">${esc(t.email)}</a>` : `<span class="hint">邮箱未核实</span>`}
            ${t.homepage_url ? `<a href="${attr(safeUrl(t.homepage_url))}" target="_blank" rel="noopener noreferrer">主页</a>` : ""}
            ${t.fit_score ? `<span class="hint">fit ${esc(t.fit_score)}/10</span>` : ""}
          </div>
        </div>
        <div class="status-box">
          <div class="status-line">${dot(t.status)} ${esc(statusLabel(t.status))}</div>
          ${t.sent_at ? `<div class="hint">首封 ${esc(t.sent_at)}${t.follow_up_count && t.follow_up_count !== "0" ? `，已跟进 ${esc(t.follow_up_count)} 次` : ""}${t.follow_up_due ? `，跟进日 ${esc(t.follow_up_due)}` : ""}</div>` : ""}
          <div class="actions">${statusActions(t)}</div>
        </div>
      </div>
      ${sug ? `<div class="banner"><p>${esc(sug.reason)}<small>建议改为：${esc(Object.entries(sug.fields).map(([k, v]) => `${k} = ${v || "（清空）"}`).join("，"))}</small></p>
        <button class="btn btn-accent" data-act="apply-suggestion">应用</button><button class="btn btn-quiet" data-act="dismiss-suggestion">忽略</button></div>` : ""}
      ${t.next_action ? `<p class="hint" style="margin:0 0 12px">下一步：${esc(t.next_action)}</p>` : ""}
      ${issues.length ? `<ul class="issues">${issues.map((i) => `<li class="${i.level}">${esc(i.message)}</li>`).join("")}</ul>` : ""}
      <div class="tabs" role="tablist">
        ${[["letter", "邮件"], ["thread", "往来"], ["profile", "资料"]].map(([k, l]) => `<button class="tab" role="tab" aria-selected="${S.tab === k}" data-tab="${k}">${l}</button>`).join("")}
      </div>
      <div id="tab-body"></div>`;
    renderTab();
  }

  function renderTab() {
    const body = $("#tab-body");
    if (!body) return;
    if (S.tab === "letter") body.innerHTML = letterHTML();
    else if (S.tab === "thread") body.innerHTML = `<p class="hint">正在读取 Gmail…</p>`;
    else body.innerHTML = profileHTML();
  }

  // ---- letter tab
  function letterHTML() {
    const { target: t, drafts, gmail } = S.detail;
    const contacted = CONTACTED.has(t.status);
    const picker = drafts.map((d) => {
      const n = d.kind === "first" ? "首封" : `${DRAFT_KIND[d.kind]} ${(d.name.match(/-(\d+)\.md$/) || [, ""])[1]}`;
      return `<button class="chip-filter${d.name === S.draftName ? " is-on" : ""}" data-draft="${attr(d.name)}">${esc(n)}</button>`;
    }).join("");
    const create = [
      !drafts.some((d) => d.kind === "first") ? `<button class="btn btn-quiet" data-act="new-first">新建首封</button>` : "",
      contacted ? `<button class="btn btn-quiet" data-act="new-followup">新建跟进</button>` : "",
      ["replied", "meeting_scheduled", "apply_and_mention", "redirected"].includes(t.status) ? `<button class="btn btn-quiet" data-act="new-reply">新建回复</button>` : "",
    ].join("");
    if (!drafts.length) {
      return `<div class="empty-main"><p>还没有草稿。可以在这里写，也可以让 skill 生成后放进 <code>drafts/</code>，面板会自动识别。</p><div class="draft-picker">${create}</div></div>`;
    }
    const d = S.draft;
    const kind = (drafts.find((x) => x.name === S.draftName) || {}).kind;
    const pushed = gmail?.drafts?.[S.draftName];
    const gate = gmailGate(t, kind);
    return `
      <div class="draft-picker">${picker}${create}</div>
      <div class="letter-wrap">
        <div class="letter">
          <div class="to">收件人：${t.email ? esc(t.email) : "（邮箱未核实）"}</div>
          <label class="visually-hidden" for="subj">主题</label>
          <input id="subj" class="subject-input" value="${attr(d?.subject ?? "")}" placeholder="主题：申请季 + 研究钩子" ${d ? "" : "disabled"}>
          <label class="visually-hidden" for="body">正文</label>
          <textarea id="body" class="body-input" placeholder="正文" ${d ? "" : "disabled"}>${esc(d?.body ?? "")}</textarea>
        </div>
        <aside class="rail">
          <div class="rail-block">
            <button class="btn" data-act="save-draft" id="save-btn">保存</button>
            <p class="saved-at" id="saved-at">${S.dirty ? "有未保存的修改" : "已保存"}（⌘/Ctrl + S）</p>
          </div>
          <div class="rail-block">
            <h3>检查</h3>
            ${checkHTML()}
          </div>
          <div class="rail-block">
            <h3>Gmail 草稿</h3>
            <button class="btn btn-accent" data-act="push-gmail" ${gate ? "disabled" : ""}>推送到 Gmail 草稿箱</button>
            <p class="hint">${gate ? esc(gate) : "只存为草稿，不会发送。在 Gmail 里检查后手动发送。"}</p>
            ${pushed ? `<p class="hint">上次推送：${esc(pushed.saved_at.replace("T", " ").slice(0, 16))} UTC，<a href="https://mail.google.com/mail/u/0/#drafts" target="_blank" rel="noopener">打开 Gmail 草稿箱</a></p>
              ${d?.modified_at && d.modified_at > pushed.saved_at ? `<p class="hint" style="color:var(--s-stop)">本地草稿在推送后改过，Gmail 里还是旧版本，记得重新推送。</p>` : ""}` : ""}
          </div>
        </aside>
      </div>`;
  }

  function gmailGate(t, kind) {
    if (!S.gmail?.connected) return "先连接 Gmail。";
    if (!t.email) return "这位教授的邮箱还没核实。";
    if (S.dirty) return "先保存修改。";
    if (S.check?.errors?.length) return "先解决检查里的错误。";
    if (kind === "first" && t.status !== "approved") return "首封需要先“确认定稿”。";
    if (kind !== "first" && !CONTACTED.has(t.status)) return "首封发出后才能推送跟进或回复。";
    return "";
  }

  function checkHTML() {
    const c = S.check;
    if (!c) return `<p class="hint">保存后自动检查。</p>`;
    const items = [...c.errors.map((e) => `<li class="error">${esc(e)}</li>`), ...c.warnings.map((w) => `<li>${esc(w)}</li>`)];
    return `<div class="words">${c.words} <small>词</small></div>
      <ul class="checks">${items.length ? items.join("") : `<li class="ok">没有发现问题。证据桥是否具体，仍需你自己判断。</li>`}</ul>`;
  }

  async function loadDraft() {
    if (!S.draftName) return;
    const id = S.detail.target.target_id;
    try {
      const [d, c] = await Promise.all([
        api("GET", `${T(id)}/drafts/${encodeURIComponent(S.draftName)}`),
        api("POST", `${T(id)}/drafts/${encodeURIComponent(S.draftName)}/check`),
      ]);
      S.draft = d; S.check = c; S.dirty = false;
      if (S.tab === "letter") renderTab();
    } catch (e) { fail(e); }
  }

  async function saveDraft() {
    if (!S.draft) return;
    const id = S.detail.target.target_id;
    const subject = $("#subj").value, body = $("#body").value;
    try {
      S.draft = await api("PUT", `${T(id)}/drafts/${encodeURIComponent(S.draftName)}`, { subject, body });
      S.check = await api("POST", `${T(id)}/drafts/${encodeURIComponent(S.draftName)}/check`);
      S.dirty = false;
      toast("已保存");
      await refreshDetail();
    } catch (e) { fail(e); }
  }

  async function refreshDetail() {
    const id = S.detail.target.target_id;
    await loadCampaign();
    S.detail = await api("GET", T(id));
    renderDetail();
  }

  // ---- thread tab
  async function loadThread() {
    const body = $("#tab-body");
    if (!S.gmail?.connected) { body.innerHTML = `<p class="hint">连接 Gmail 后，这里会显示你和这位教授的邮件往来。</p>`; return; }
    try {
      const r = await api("GET", `${T(S.detail.target.target_id)}/thread`);
      if (!r.messages.length) { body.innerHTML = `<p class="hint">${esc(r.note || "没有找到邮件。")}</p>`; return; }
      const me = (S.gmail.email || "").toLowerCase();
      body.innerHTML = `<div class="thread">${r.messages.map((m) => {
        const mine = me && m.from.toLowerCase().includes(me);
        return `<article class="msg ${mine ? "mine" : "theirs"}">
          <div class="msg-head"><strong>${esc(mine ? "我" : m.from)}</strong><span>${esc(m.date)}</span><span>${esc(m.subject)}</span></div>
          <p class="msg-body">${esc(m.body || m.snippet)}</p>
        </article>`;
      }).join("")}</div>`;
    } catch (e) { body.innerHTML = `<p class="hint">${esc(e.message)}</p>`; }
  }

  // ---- profile tab
  const PROFILE_FIELDS = [
    ["email", "邮箱（官方页面核实过的）"], ["homepage_url", "主页"],
    ["department", "院系"], ["program_id", "申请项目"],
    ["research_anchor", "教授的锚点论文/项目", "wide"], ["applicant_anchor", "我的锚点项目", "wide"],
    ["fit_rationale", "证据桥（一句话）", "wide", "textarea"],
    ["recruiting_confirmed", "招生：明确信息"], ["recruiting_signals", "招生：间接信号"],
    ["fit_score", "fit 总分"], ["fit_components", "fit 分项"],
    ["checked_on", "最后核实日期", "", "date"], ["variant", "写法标签（用于统计回复率）"],
    ["follow_up_due", "跟进日", "", "date"], ["follow_up_count", "已跟进次数"],
    ["response_summary", "回信摘要", "wide", "textarea"], ["next_action", "下一步", "wide"],
    ["source_urls", "来源链接（空格分隔）", "wide", "textarea"],
  ];

  function profileHTML() {
    const t = S.detail.target;
    const comps = Object.fromEntries((t.fit_components || "").split(";").map((p) => p.split("=")).filter((p) => p.length === 2));
    const maxes = { topic: 3, contrib: 2, bridge: 2, signals: 2, program: 1 };
    const names = { topic: "主题", contrib: "贡献", bridge: "桥", signals: "招生信号", program: "项目/联系" };
    const fit = Object.keys(comps).length ? `<div class="field wide"><label>fit 分项</label><div class="fit">
      <div class="fit-total">${esc(t.fit_score || "")}</div>
      ${Object.entries(maxes).map(([k, m]) => `<div class="fit-part">${names[k]}<div class="pips">${Array.from({ length: m }, (_, i) => `<i class="${i < Number(comps[k] || 0) ? "on" : ""}"></i>`).join("")}</div></div>`).join("")}
    </div></div>` : "";
    const sources = (t.source_urls || "").split(/\s+/).filter(Boolean);
    return `<form id="profile-form" class="fields">
      ${fit}
      ${PROFILE_FIELDS.map(([k, label, cls = "", type = "text"]) => {
        if (k === "program_id") {
          return `<div class="field ${cls}"><label for="f-${k}">${label}</label><select id="f-${k}" name="${k}">
            <option value="">（无）</option>${S.programs.map((p) => `<option value="${attr(p.program_id)}" ${p.program_id === t.program_id ? "selected" : ""}>${esc(p.program_id)}</option>`).join("")}</select></div>`;
        }
        const v = t[k] || "";
        return `<div class="field ${cls}"><label for="f-${k}">${label}</label>${type === "textarea"
          ? `<textarea id="f-${k}" name="${k}">${esc(v)}</textarea>`
          : `<input id="f-${k}" name="${k}" type="${type}" value="${attr(v)}">`}</div>`;
      }).join("")}
      ${sources.length ? `<div class="field wide sources"><label>来源</label>${sources.map((u) => `<a href="${attr(safeUrl(u))}" target="_blank" rel="noopener noreferrer">${esc(u)}</a>`).join("")}</div>` : ""}
      <div class="field wide"><div class="form-actions"><button class="btn" type="submit">保存资料</button></div></div>
    </form>`;
  }
  const safeUrl = (u) => (/^https?:\/\//i.test(u) ? u : "#");

  async function saveProfile(form) {
    const t = S.detail.target;
    const changed = {};
    for (const el of form.elements) if (el.name && (t[el.name] || "") !== el.value.trim()) changed[el.name] = el.value.trim();
    if (!Object.keys(changed).length) return toast("没有修改");
    try { await api("PATCH", T(t.target_id), changed); toast("资料已保存"); await refreshDetail(); } catch (e) { fail(e); }
  }

  // ------------------------------------------------------------ status changes
  async function setStatus(fields, msg) {
    try {
      await api("PATCH", T(S.detail.target.target_id), fields);
      toast(msg || `状态已改为“${statusLabel(fields.status)}”`);
      await refreshDetail();
    } catch (e) { fail(e); }
  }

  function dialog(html, onSubmit) {
    const dlg = $("#dialog");
    dlg.innerHTML = `<form method="dialog" class="dlg">${html}<p class="form-error" id="dlg-err" hidden></p></form>`;
    const form = dlg.querySelector("form");
    form.addEventListener("submit", async (ev) => {
      if (ev.submitter?.value === "cancel") return;
      ev.preventDefault();
      try { await onSubmit(new FormData(form), ev.submitter?.value); dlg.close(); }
      catch (e) { const er = $("#dlg-err"); er.textContent = e.message; er.hidden = false; }
    });
    dlg.showModal();
    form.querySelector("input, select, textarea")?.focus();
  }
  const cancelBtn = `<button class="btn btn-quiet" value="cancel" formnovalidate>取消</button>`;

  function statusDialog() {
    const t = S.detail.target;
    dialog(`<h2>更改状态</h2>
      <div class="form-grid">
        <label class="wide">状态<select name="status">${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${k === t.status ? "selected" : ""}>${v}（${k}）</option>`).join("")}</select></label>
        <label>首封发送日期<input type="date" name="sent_at" value="${attr(t.sent_at)}"></label>
        <label>跟进日<input type="date" name="follow_up_due" value="${attr(t.follow_up_due)}"></label>
        <label class="wide">结束原因（状态为“已结束”时必填）<input name="close_reason" value="${attr(t.close_reason)}" placeholder="例如 not recruiting / no response after follow-up"></label>
        <label class="wide">下一步 / 卡住原因<input name="next_action" value="${attr(t.next_action)}"></label>
      </div>
      <div class="dlg-actions">${cancelBtn}<button class="btn">保存</button></div>`,
    async (fd) => {
      const fields = Object.fromEntries([...fd.entries()].filter(([k, v]) => (t[k] || "") !== v));
      if (!Object.keys(fields).length) return;
      await api("PATCH", T(t.target_id), fields);
      toast("已更新"); await refreshDetail();
    });
  }

  function markSentDialog() {
    const t = S.detail.target;
    dialog(`<h2>标记为已发送</h2>
      <p>只有在你确实从邮箱发出这封邮件之后再标记。连接了 Gmail 的话，也可以直接点“同步 Gmail”自动识别。</p>
      <div class="form-grid"><label>发送日期<input type="date" name="sent_at" value="${todayISO()}" required></label>
      <label>跟进日（默认 10 天后）<input type="date" name="follow_up_due"></label></div>
      <div class="dlg-actions">${cancelBtn}<button class="btn btn-accent">已发送</button></div>`,
    async (fd) => {
      const f = { status: "sent", sent_at: fd.get("sent_at") };
      if (fd.get("follow_up_due")) f.follow_up_due = fd.get("follow_up_due");
      await api("PATCH", T(t.target_id), f); toast("已标记为发送"); await refreshDetail();
    });
  }

  function markRepliedDialog() {
    const t = S.detail.target;
    dialog(`<h2>记录回信</h2>
      <div class="form-grid">
        <label class="wide">回信类型<select name="status">
          <option value="replied">回复了，需要我回应</option><option value="meeting_scheduled">约了会谈</option>
          <option value="apply_and_mention">让我申请时写他的名字</option><option value="redirected">推荐了别的老师</option>
          <option value="closed">今年不招 / 明确拒绝</option></select></label>
        <label class="wide">回信摘要<input name="response_summary" required></label>
        <label class="wide">下一步<input name="next_action"></label>
      </div>
      <div class="dlg-actions">${cancelBtn}<button class="btn btn-accent">保存</button></div>`,
    async (fd) => {
      const f = Object.fromEntries(fd.entries());
      if (f.status === "closed") f.close_reason = f.close_reason || "not recruiting";
      await api("PATCH", T(t.target_id), f); toast("已记录"); await refreshDetail();
    });
  }

  function addTargetDialog() {
    dialog(`<h2>添加教授</h2>
      <div class="form-grid">
        <label>教授姓名<input name="professor" required></label>
        <label>学校<input name="institution" required list="inst-list"></label>
        <datalist id="inst-list">${[...new Set(S.targets.map((t) => t.institution))].map((i) => `<option value="${attr(i)}">`).join("")}</datalist>
        <label>院系<input name="department"></label>
        <label>申请项目<select name="program_id"><option value="">（无）</option>${S.programs.map((p) => `<option>${esc(p.program_id)}</option>`).join("")}</select></label>
        <label>邮箱<input name="email" type="email"></label>
        <label>主页<input name="homepage_url" type="url"></label>
        <label class="wide">ID（自动生成，可修改）<input name="target_id" required pattern="[A-Za-z0-9][A-Za-z0-9._-]*"></label>
      </div>
      <div class="dlg-actions">${cancelBtn}<button class="btn btn-accent">添加</button></div>`,
    async (fd) => {
      const f = Object.fromEntries([...fd.entries()].map(([k, v]) => [k, v.trim()]));
      const row = await api("POST", `${C()}/targets`, f);
      toast("已添加"); await loadCampaign(); location.hash = `#/t/${encodeURIComponent(row.target_id)}`;
    });
    const form = $("#dialog form");
    const sync = () => {
      const id = form.elements.target_id;
      if (id.dataset.touched) return;
      const inst = slug(form.elements.institution.value).split("-")[0];
      id.value = [inst, slug(form.elements.professor.value)].filter(Boolean).join("--");
    };
    form.elements.professor.addEventListener("input", sync);
    form.elements.institution.addEventListener("input", sync);
    form.elements.target_id.addEventListener("input", (e) => (e.target.dataset.touched = "1"));
  }

  const GC = "https://console.cloud.google.com";
  function gmailSetupDialog() {
    const link = (href, label) => `<a class="btn btn-quiet step-link" href="${href}" target="_blank" rel="noopener">${label}</a>`;
    dialog(`<h2>连接 Gmail</h2>
      <p>Gmail 只允许通过你自己的 Google Cloud 授权客户端访问。下面的设置只需做一次，大约 5 分钟；之后连接、续期都是一键跳转到 Google 授权页。</p>
      <ol class="steps">
        <li><div><strong>启用 Gmail API</strong><span>没有项目会让你先建一个，名字随意，例如 phd-outreach。</span></div>
          ${link(`${GC}/flows/enableapi?apiid=gmail.googleapis.com`, "打开")}</li>
        <li><div><strong>设置授权页面</strong><span>应用名随意；用户类型选 External（外部）；邮箱都填你自己的。不用提交审核。</span></div>
          ${link(`${GC}/auth/overview/create`, "打开")}</li>
        <li><div><strong>把你的 Gmail 加为测试用户</strong><span>Audience → Test users → Add users。漏掉这一步，Google 会提示“应用被阻止”。</span></div>
          ${link(`${GC}/auth/audience`, "打开")}</li>
        <li><div><strong>创建客户端并下载</strong><span>应用类型选<b>桌面应用（Desktop app）</b>，创建后点下载，得到一个 JSON 文件。</span></div>
          ${link(`${GC}/auth/clients/create`, "打开")}</li>
      </ol>
      <label class="dropzone" id="dz">
        <input type="file" id="client-file" accept=".json,application/json" hidden>
        <span id="dz-text">把下载的 JSON 文件拖到这里，或点击选择</span>
      </label>
      <details class="manual"><summary>没有文件？手动填写客户端 ID 和密钥</summary>
        <div class="form-grid">
          <label class="wide">客户端 ID<input name="client_id" placeholder="123456789-xxxx.apps.googleusercontent.com" autocomplete="off"></label>
          <label class="wide">客户端密钥<input name="client_secret" type="password" autocomplete="off"></label>
        </div>
      </details>
      <p class="hint">凭据只保存在你这台电脑上（<code>${esc(S.gmail?.client_file || "~/.phd-outreach-dashboard")}</code>）。授权只申请两项：查看邮件（识别回信）和管理草稿（推送草稿）。面板不会发送邮件。</p>
      <div class="dlg-actions">${cancelBtn}<button class="btn btn-accent" id="save-client">保存并前往 Google 授权</button></div>`,
    async (fd) => {
      const body = S.clientJson ? { json: S.clientJson }
        : { client_id: (fd.get("client_id") || "").trim(), client_secret: (fd.get("client_secret") || "").trim() };
      if (!body.json && !body.client_id) throw new Error("先拖入下载的 JSON 文件，或手动填写客户端 ID 和密钥。");
      const r = await api("PUT", "/gmail/client", body);
      S.clientJson = null;
      location.href = r.auth_url;
    });
    S.clientJson = null;
    const dz = $("#dz"), input = $("#client-file"), text = $("#dz-text");
    const take = async (file) => {
      if (!file) return;
      try {
        const parsed = JSON.parse(await file.text());
        const cfg = parsed.installed || parsed.web || parsed;
        if (!cfg.client_id) throw new Error("文件里没有 client_id");
        S.clientJson = parsed;
        dz.classList.add("ok");
        text.textContent = `已读取：${file.name}（${parsed.installed ? "桌面应用" : parsed.web ? "Web 应用，类型不对" : "客户端"}）`;
      } catch (e) {
        S.clientJson = null; dz.classList.remove("ok");
        text.textContent = `读不出这个文件：${e.message}。请选择从 Google Cloud 下载的 JSON。`;
      }
    };
    input.addEventListener("change", () => take(input.files[0]));
    ["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("over"); }));
    ["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
    dz.addEventListener("drop", (e) => take(e.dataTransfer.files[0]));
  }

  function gmailMenuDialog() {
    const g = S.gmail;
    dialog(`<h2>Gmail</h2>
      <p>${g.connected ? `当前账号：${esc(g.email)}` : "Google 客户端已设置，Gmail 尚未连接。"}</p>
      ${g.connected ? `<p>权限：${g.can_read ? "查看邮件 ✓" : "查看邮件 ✗"}，${g.can_draft ? "管理草稿 ✓" : "管理草稿 ✗"}</p>` : ""}
      <p class="hint">断开会撤销授权并删除本机保存的令牌；同步记录和草稿 ID 会保留。更换客户端会同时断开。</p>
      <div class="dlg-actions">${cancelBtn}
        <button class="btn btn-quiet" value="replace">更换 Google 客户端</button>
        ${g.connected ? `<button class="btn btn-danger" value="disconnect">断开 Gmail</button>` : ""}</div>`,
    async (fd, submitter) => {
      if (submitter === "replace") {
        S.gmail = await api("DELETE", "/gmail/client"); renderGmailPill(); setTimeout(gmailSetupDialog, 0); return;
      }
      S.gmail = await api("POST", "/gmail/disconnect"); renderGmailPill(); toast("已断开 Gmail");
    });
  }


  // ------------------------------------------------------------ events
  document.addEventListener("click", async (ev) => {
    const el = ev.target.closest("[data-act], [data-tab], [data-draft], [data-filter]");
    if (!el) return;
    if (el.dataset.filter) {
      S.filter = el.dataset.filter;
      document.querySelectorAll(".chip-filter[data-filter]").forEach((b) => b.classList.toggle("is-on", b === el));
      return renderTree();
    }
    if (el.dataset.tab) {
      if (S.dirty && el.dataset.tab !== "letter" && !confirm("当前草稿还没保存，确定切换吗？")) return;
      S.tab = el.dataset.tab;
      history.replaceState(null, "", `#/t/${encodeURIComponent(S.detail.target.target_id)}${S.tab === "letter" ? "" : "/" + S.tab}`);
      document.querySelectorAll(".tab").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === S.tab));
      renderTab();
      if (S.tab === "letter") { S.dirty = false; return loadDraft(); }
      if (S.tab === "thread") return loadThread();
      return;
    }
    if (el.dataset.draft) {
      if (S.dirty && !confirm("当前草稿还没保存，确定切换吗？")) return;
      S.draftName = el.dataset.draft; S.draft = null; S.check = null; S.dirty = false;
      renderTab(); return loadDraft();
    }
    const act = el.dataset.act;
    const t = S.detail?.target;
    try {
      if (act.startsWith("set:")) return setStatus({ status: act.slice(4) });
      switch (act) {
        case "add-target": return addTargetDialog();
        case "status-dialog": return statusDialog();
        case "mark-sent": return markSentDialog();
        case "mark-replied": return markRepliedDialog();
        case "save-draft": return saveDraft();
        case "new-first": case "new-followup": case "new-reply": {
          const d = await api("POST", `${T(t.target_id)}/drafts`, { kind: act.slice(4) });
          S.tab = "letter"; S.draftName = d.name;
          await refreshDetail(); await loadDraft(); return toast("已新建草稿");
        }
        case "push-gmail": {
          el.disabled = true;
          const r = await api("POST", `${T(t.target_id)}/drafts/${encodeURIComponent(S.draftName)}/gmail`);
          toast(r.updated ? "已更新 Gmail 里的草稿" : "已存入 Gmail 草稿箱");
          if (r.note && !r.threaded && S.draftName.includes("--")) setTimeout(() => toast(r.note), 3400);
          return refreshDetail();
        }
        case "apply-suggestion": {
          const fields = S.detail.gmail.suggestion.fields;
          await api("PATCH", T(t.target_id), fields);
          toast("已应用 Gmail 建议"); return refreshDetail();
        }
        case "dismiss-suggestion":
          await api("DELETE", `${T(t.target_id)}/suggestion`);
          return refreshDetail();
        case "gmail-setup": return gmailSetupDialog();
        case "gmail-menu": return gmailMenuDialog();
        case "gmail-connect": {
          const r = await api("POST", "/gmail/connect");
          location.href = r.auth_url; return;
        }
      }
    } catch (e) { fail(e); el.disabled = false; }
  });

  document.addEventListener("input", (ev) => {
    if (ev.target.id === "subj" || ev.target.id === "body") {
      if (!S.dirty) { S.dirty = true; const s = $("#saved-at"); if (s) s.textContent = "有未保存的修改（⌘/Ctrl + S）"; }
    }
  });
  document.addEventListener("keydown", (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "s" && S.tab === "letter" && S.detail) { ev.preventDefault(); saveDraft(); }
  });
  document.addEventListener("submit", (ev) => {
    if (ev.target.id === "profile-form") { ev.preventDefault(); saveProfile(ev.target); }
  });
  window.addEventListener("beforeunload", (ev) => { if (S.dirty) { ev.preventDefault(); ev.returnValue = ""; } });

  $("#search").addEventListener("input", (e) => { S.search = e.target.value; renderTree(); });
  $("#add-target").addEventListener("click", addTargetDialog);
  $("#campaign").addEventListener("change", (e) => switchCampaign(e.target.value));
  $("#open-side").addEventListener("click", () => $("#sidebar").classList.add("open"));
  $("#close-side").addEventListener("click", () => $("#sidebar").classList.remove("open"));
  $("#tree").addEventListener("click", (e) => { if (e.target.closest(".prof")) $("#sidebar").classList.remove("open"); });
  $("#sync-btn").addEventListener("click", async (e) => {
    const b = e.currentTarget; b.disabled = true; b.textContent = "同步中…";
    try {
      const r = await api("POST", `${C()}/gmail/sync`, {});
      toast(`检查了 ${r.checked} 位教授，${r.suggestions.length} 条新建议${r.errors.length ? `，${r.errors.length} 位出错` : ""}`);
      await loadCampaign();
      S.detail ? await refreshDetail() : renderOverview();
    } catch (err) { fail(err); }
    finally { b.disabled = !S.gmail?.connected; b.textContent = "同步 Gmail"; }
  });

  // ------------------------------------------------------------ routing
  async function route() {
    const h = location.hash;
    if (h.startsWith("#gmail=")) { toast("Gmail 已连接"); history.replaceState(null, "", "#/"); await loadGmail(); }
    if (h.startsWith("#gmail-error=")) { toast(`Gmail 没有连上：${decodeURIComponent(h.slice(13))}`, true); history.replaceState(null, "", "#/"); await loadGmail(); }
    const m = location.hash.match(/^#\/t\/([^/]+)(?:\/(\w+))?/);
    if (m) return openTarget(decodeURIComponent(m[1]), m[2] || undefined);
    if (S.dirty && !confirm("当前草稿还没保存，确定离开吗？")) { history.back(); return; }
    S.dirty = false;
    renderOverview();
    main.focus({ preventScroll: true });
  }
  window.addEventListener("hashchange", route);

  // ------------------------------------------------------------ campaigns
  const SEASONS = { spring: "Spring", summer: "Summer", fall: "Fall", autumn: "Fall", winter: "Winter" };
  function campaignLabel(id) {
    const m = String(id).match(/^(spring|summer|fall|autumn|winter)-(\d{4})$/i);
    return m ? `${m[2]} ${SEASONS[m[1].toLowerCase()]}` : id;
  }
  const LAST_KEY = "outreach.campaign";
  function rememberCampaign(id) { try { localStorage.setItem(LAST_KEY, id); } catch (e) { /* storage unavailable */ } }
  function lastCampaign() { try { return localStorage.getItem(LAST_KEY); } catch (e) { return null; } }

  function renderCampaignSelect() {
    $("#campaign").innerHTML = S.campaigns.map((c) =>
      `<option value="${attr(c.id)}">${esc(campaignLabel(c.id))}（${c.targets}）</option>`).join("");
    $("#campaign").value = S.campaign;
  }

  async function switchCampaign(id) {
    if (S.dirty && !confirm("当前草稿还没保存，确定切换申请季吗？")) { $("#campaign").value = S.campaign; return; }
    S.dirty = false; S.detail = null; S.campaign = id; rememberCampaign(id);
    await loadCampaign();
    if (location.hash !== "#/") location.hash = "#/"; else renderOverview();
  }

  function newCampaignDialog() {
    const y = new Date().getFullYear() + 1;
    dialog(`<h2>新建申请季</h2>
      <p>每个申请季是 <code>outreach/</code> 下的一个文件夹，有自己的学校、教授和草稿，互不影响。</p>
      <div class="form-grid">
        <label>入学学期<select name="season"><option value="fall">Fall（秋季）</option><option value="spring">Spring（春季）</option></select></label>
        <label>年份<input name="year" type="number" min="2020" max="2100" value="${y}" required></label>
      </div>
      <div class="dlg-actions">${cancelBtn}<button class="btn btn-accent">创建</button></div>`,
    async (fd) => {
      const id = `${fd.get("season")}-${fd.get("year")}`;
      await api("POST", "/campaigns", { id });
      S.campaigns = await api("GET", "/campaigns");
      S.campaign = id;
      renderCampaignSelect();
      await switchCampaign(id);
      toast(`已新建 ${campaignLabel(id)}`);
    });
  }

  // ------------------------------------------------------------ boot
  $("#new-campaign").addEventListener("click", newCampaignDialog);
  (async () => {
    try {
      S.campaigns = await api("GET", "/campaigns");
      loadGmail();
      if (!S.campaigns.length) {
        $("#tree").innerHTML = "";
        main.innerHTML = `<div class="empty-main"><h1>还没有申请季</h1>
          <p>每个申请季是 <code>outreach/</code> 下的一个文件夹。新建一个空的申请季开始记录，或者让 skill 生成 <code>targets.csv</code> 后刷新页面。</p>
          <p><button class="btn btn-accent" id="first-campaign">新建申请季</button></p></div>`;
        $("#first-campaign").addEventListener("click", newCampaignDialog);
        return;
      }
      const remembered = lastCampaign();
      const byTargets = [...S.campaigns].sort((a, b) => b.targets - a.targets)[0].id;
      S.campaign = S.campaigns.some((c) => c.id === remembered) ? remembered : byTargets;
      renderCampaignSelect();
      await loadCampaign();
      route();
    } catch (e) {
      main.innerHTML = `<div class="empty-main"><h1>连不上面板服务</h1><p>${esc(e.message)}</p></div>`;
    }
  })();
})();
