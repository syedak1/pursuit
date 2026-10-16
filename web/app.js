/* Incumbent Clock: the browser half.
 *
 * The Python pipeline does the reading and writes window.SITE (web/data/site.js).
 * This file ranks, draws, searches and explains. Everything shown is traceable:
 * any underlined fact opens the evidence behind it.
 *
 * Six tabs:
 *   For Pursuit     a reviewer's brief with a guided tour that drives the other tabs
 *   Where to sell   the seller's profile, then contracts ending soon and the departments buying them
 *   Contract clock  the same contracts on a timeline
 *   Competition     how the city awards contracts: competed or not, by department and vendor
 *   Research        search and filter every record, export CSV
 *   How it works    the manual and the glossary (terms are linked from every tab)
 *
 * No framework, no build step: open web/index.html.
 */
(() => {
  "use strict";

  const SITE = window.SITE;
  const app = document.getElementById("app");
  if (!SITE) {
    app.innerHTML = '<p class="banner">No data yet. Run <code>python3 -m clock refresh</code>, then reload.</p>';
    return;
  }

  // ------------------------------------------------------------------ data

  // "Today" is the viewer's date, never earlier than the build's, so the 18-month window moves forward
  // with the calendar instead of staying fixed at the day the data was built.
  const TODAY = (() => { const built = new Date(SITE.meta.today + "T12:00:00"), now = new Date(); now.setHours(12, 0, 0, 0); return now > built ? now : built; })();
  const WINDOW_MONTHS = 18;
  const EV = new Map(SITE.evidence.map((e) => [e.id, e]));
  const EVENTS = SITE.events;
  const BY_ID = new Map(EVENTS.map((e) => [e.id, e]));
  const BY_FILE = new Map(EVENTS.map((e) => [e.file, e]));
  // Only approved items are in force. Pending ones are on an upcoming agenda (an early signal of their
  // own); defeated, rescinded or filed ones never took effect and appear only in Research.
  const CONTRACTS = EVENTS.filter((e) => e.type === "contract" && e.state === "approved");
  const FUNDING = EVENTS.filter((e) => e.type === "funding" && e.state === "approved");
  const PENDING = EVENTS.filter((e) => e.state === "pending");
  const STATE_LABEL = { approved: "Approved", pending: "Not yet voted on", not_approved: "Did not take effect" };
  const TEXTS = SITE.texts || {};
  const CATS = SITE.categories;
  // Every vendor once (by normalized name), biggest first: the competitor dropdown's choices.
  const VENDORS = (() => {
    const m = new Map();
    for (const e of CONTRACTS) {
      if (!e.vendorKey) continue;
      const v = m.get(e.vendorKey) || { key: e.vendorKey, name: e.vendor, total: 0, n: 0 };
      v.total += e.amount || 0; v.n++;
      m.set(e.vendorKey, v);
    }
    return [...m.values()].sort((a, b) => b.total - a.total);
  })();
  const VENDOR_BY_KEY = new Map(VENDORS.map((v) => [v.key, v]));
  // A vendor's awards from one department, oldest first: how long the incumbent has held the work.
  const HISTORY = new Map();
  for (const e of CONTRACTS) {
    if (!e.vendorKey) continue;
    const k = e.vendorKey + "|" + e.dept;
    if (!HISTORY.has(k)) HISTORY.set(k, []);
    HISTORY.get(k).push(e);
  }
  for (const list of HISTORY.values()) list.sort((a, b) => (a.passed || a.introduced || "").localeCompare(b.passed || b.introduced || ""));
  const historyOf = (e) => (e.vendorKey && HISTORY.get(e.vendorKey + "|" + e.dept)) || [e];
  const hasClock = (e) => e.class !== "one_time";
  const CITY = SITE.meta.city.replace(/, MI$/, "");

  // How each market reads inside a sentence ("I sell ___ to city governments").
  const PHRASE = {
    it_software: "IT and software", public_safety: "public-safety technology", water_utilities: "water and utility work",
    streets_transport: "street and transportation work", facilities_construction: "facilities and construction",
    fleet_equipment: "vehicles and equipment", parks_environment: "parks and environmental work",
    professional_services: "consulting and professional services", housing_community: "housing and human services",
  };
  const phrase = (k) => PHRASE[k] || (CATS[k] || k).toLowerCase();

  // ------------------------------------------------------------------ glossary
  // Every term a reader outside procurement might trip on. Anywhere on the site, term(id) renders the
  // word as a link: pointing previews the definition, clicking opens the entry on How it works.
  // `sec` is the How it works section that explains the idea in depth.
  const GLOSSARY = [
    { id: "resolution", term: "Resolution", sec: "how-data", def: "A formal decision of City Council. In Ann Arbor, contracts over $75,000 need one; the title usually names the vendor, amount and award method." },
    { id: "memo", term: "Staff memo", sec: "how-data", def: "The department's explanation attached to a resolution. Terms, dates, renewal options and sole-source reasons are here." },
    { id: "legistar", term: "Legistar", sec: "how-data", def: "The system Ann Arbor uses to publish agendas, resolutions and memos. Its public API is the source of every record here." },
    { id: "record", term: "Record number", sec: "how-data", def: "Legistar's file number, such as 26-0713: year filed, then sequence. Every fact links back to one." },
    { id: "incumbent", term: "Incumbent", sec: "how-opening", def: "The vendor that holds the contract now." },
    { id: "department", term: "Department", sec: "how-order", def: "The city unit that requested the purchase. It scopes the work, writes the memo and pays." },
    { id: "market", term: "Market", sec: "how-tabs", def: "One of nine kinds of work, such as IT and software. Assigned by keywords in the title and department; a record can be in up to three." },
    { id: "competitive", term: "Competitive bid or RFP", sec: "how-method", def: "The city asked for bids (ITB, usually lowest price wins) or proposals (RFP, scored on more than price) and chose one." },
    { id: "cooperative", term: "Cooperative contract", sec: "how-method", def: "Bought through a contract another public body already competed, such as MiDEAL, Sourcewell or NASPO." },
    { id: "sole-source", term: "Sole source", sec: "how-method", def: "Bought without competition, usually because only one vendor can do the work." },
    { id: "no-method", term: "Method not stated", sec: "how-method", def: "Neither the resolution title nor the memo says how the vendor was chosen, so the site doesn't guess. Most are amendments, change orders and renewals: their memo describes the change, not how the original contract was awarded." },
    { id: "emergency", term: "Emergency purchase", sec: "how-method", def: "Bought without the normal process because of urgency. Counted with sole source here." },
    { id: "purchase-order", term: "Purchase order", sec: "how-classes", def: "A direct order for goods or services, often under a cooperative contract or for a year of software support." },
    { id: "service-contract", term: "Service contract", sec: "how-classes", def: "A contract that runs for a period and is then renewed, rebid or replaced. These have end dates." },
    { id: "one-time", term: "One-time purchase", sec: "how-classes", def: "Equipment, supplies or a construction project. Nothing renews." },
    { id: "amendment", term: "Amendment or change order", sec: "how-classes", def: "A change to an existing contract: more money, time or scope." },
    { id: "renewal-option", term: "Renewal option", sec: "how-opening", def: "An extension the contract already allows, such as \"two additional one-year periods\". Usually exercised without a council vote." },
    { id: "auto-renew", term: "Automatic renewal", sec: "how-opening", def: "A contract that renews on its own each term unless someone gives notice. It has no natural rebid date." },
    { id: "last-end", term: "Last possible end", sec: "how-opening", def: "The end date plus every renewal option. When the work actually opens to competitors." },
    { id: "end-basis", term: "End-date basis", sec: "how-ends", def: "How an end date was found: stated, start plus term, fiscal year, vote plus term, or bid-price expiry." },
    { id: "approval-term", term: "Council vote plus term", sec: "how-ends", def: "A stated term counted from the council vote, when no start date is given. An assumption, always labeled; never used for amendments." },
    { id: "fiscal-year", term: "Fiscal year (FY)", sec: "how-ends", def: "July 1 to June 30 in Ann Arbor. FY2027 ends June 30, 2027." },
    { id: "price-expiry", term: "Bid-price expiry", sec: "how-ends", def: "For supply orders with no stated end: the date bid prices are firm until." },
    { id: "cip", term: "Capital Improvements Plan (CIP)", sec: "how-ends", def: "The city's multi-year plan for capital projects. A CIP range is a plan, not a contract term." },
    { id: "not-to-exceed", term: "Not-to-exceed amount", sec: "how-record", def: "A spending ceiling, not a promise to spend. Amounts are labeled yearly, ceiling, total or increase." },
    { id: "window", term: "18-month window", sec: "how-order", def: "Today to 18 months out: enough lead time to be known before an RFP is written." },
    { id: "pending", term: "Not yet voted on", sec: "how-states", def: "On an upcoming council agenda, no vote yet. Shown separately; not counted elsewhere." },
    { id: "not-approved", term: "Did not take effect", sec: "how-states", def: "Defeated, withdrawn, rescinded, failed, vetoed or filed. Appears only in Research." },
    { id: "intergovernmental", term: "Intergovernmental agreement", sec: "how-states", def: "An agreement with another public body, such as Washtenaw County or the University of Michigan. Not a vendor contract; left out." },
    { id: "held", term: "Held since", sec: "how-tabs", def: "How long the vendor has held this department's work: first award year and number of awards, or an earlier year if the memo states one." },
    { id: "quoted", term: "Quoted fact", sec: "how-provenance", def: "Dotted underline. The sentence was found word for word in the record." },
    { id: "calculated", term: "Calculated fact", sec: "how-provenance", def: "Dashed underline. An end date, sum or count, with its arithmetic or records." },
    { id: "memo-author", term: "Memo author", sec: "how-record", def: "The staff member named as \"Prepared by\" on the memo: usually who scoped the purchase." },
  ];
  const GLOSS = new Map(GLOSSARY.map((g) => [g.id, g]));
  const see0 = (id, text) => `<a href="#${id}" data-howsec="${id}">${esc(text)}</a>`;
  /** A glossary term as a link: previews on hover, opens the glossary entry on click. */
  const term = (id, text) => {
    const g = GLOSS.get(id);
    return g ? `<a href="#g-${id}" class="term" data-term="${id}">${esc(text || g.term.toLowerCase())}</a>` : esc(text || id);
  };

  const ROUTE = { competitive: "competitive bid or RFP", cooperative: "cooperative contract", sole_source: "sole source", emergency: "emergency purchase" };
  const ROUTE_SHORT = { competitive: "Competitive", cooperative: "Cooperative", sole_source: "Sole source", emergency: "Emergency", unknown: "Not stated" };
  const KIND = {
    amendment: "amendment", change_order: "change order", renewal: "renewal", construction: "construction contract",
    professional_services: "professional services agreement", purchase_order: "purchase order",
    services: "services agreement", agreement: "agreement",
  };
  // Example profiles: one click sets the market, so a first-time visitor sees a full page.
  const PRESETS = [
    { label: "Municipal software", cat: "it_software" },
    { label: "Engineering and consulting", cat: "professional_services" },
    { label: "Water infrastructure", cat: "water_utilities" },
    { label: "Civil and street work", cat: "streets_transport" },
    { label: "Facilities", cat: "facilities_construction" },
  ];
  const MIN_SIZES = [[0, "Any size"], [25000, "$25K and up"], [100000, "$100K and up"], [250000, "$250K and up"], [1000000, "$1M and up"]];
  const TABS = [
    { id: "pursuit", label: "For Pursuit" },
    { id: "sell", label: "Where to sell" },
    { id: "clock", label: "Timeline" },
    { id: "compete", label: "Competition" },
    { id: "research", label: "Research" },
    { id: "how", label: "How it works" },
  ];

  // ------------------------------------------------------------------ format

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const d = (iso) => (iso ? new Date(iso + "T12:00:00") : null);
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const fmtDate = (iso) => { const x = d(iso); return x ? `${MONTHS[x.getMonth()]} ${x.getFullYear()}` : "unknown"; };
  const fmtDay = (iso) => { const x = d(iso); return x ? `${MONTHS[x.getMonth()]} ${x.getDate()}, ${x.getFullYear()}` : "unknown"; };
  const money = (n) => {
    if (n == null) return "amount not stated";
    if (n >= 1e6) return "$" + (n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
    if (n >= 1e4) return "$" + Math.round(n / 1e3) + "K";
    return "$" + Math.round(n).toLocaleString("en-US");
  };
  const moneyExact = (n) => (n == null ? "not stated" : "$" + n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 }));
  const monthsFromToday = (iso) => { const x = d(iso); return x ? (x - TODAY) / (1000 * 60 * 60 * 24 * 30.44) : null; };
  const plural = (n, one, many) => `${n.toLocaleString("en-US")} ${n === 1 ? one : many || one + "s"}`;
  const routeOf = (e) => e.route || "unknown";
  const routeClass = (e) => (routeOf(e) === "emergency" ? "sole_source" : routeOf(e));
  const endingSoon = (e) => e.end && monthsFromToday(e.end) > 0 && monthsFromToday(e.end) <= WINDOW_MONTHS;
  const noBid = (e) => e.route === "sole_source" || e.route === "emergency";
  const cap = (html) => html.replace(/^(<[^>]+>)?([a-z])/, (m, tag, ch) => (tag || "") + ch.toUpperCase());
  const recordLink = (e) => `<a href="${esc(e.url)}" target="_blank" rel="noopener" data-file="${esc(e.file)}">${esc(e.file || "Legistar")}</a>`;
  const AMOUNT_BASIS = { annual: "a yearly amount", ceiling: "a not-to-exceed ceiling", total: "a contract total", increase: "an increase to an earlier amount", stated: "the amount in the title" };
  const yrs = (m) => (m % 12 === 0 ? plural(m / 12, "year") : plural(m, "month"));
  const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  // The end of the 18-month window, said as a date ("by April 2028") so headings read as Ann Arbor facts.
  const WINDOW_END = (() => { const x = new Date(TODAY); x.setMonth(x.getMonth() + WINDOW_MONTHS); return x; })();
  const BY = `${MONTHS_LONG[WINDOW_END.getMonth()]} ${WINDOW_END.getFullYear()}`;
  const optsShort = (r) => `${r.count} × ${r.months_each % 12 === 0 ? r.months_each / 12 + " yr" : r.months_each + " mo"}`;

  /**
   * A number that is calculated from records (a sum, a count, a share) and opens the records behind it.
   * `list` is the exact set the number was computed from; the popover lists them, each fact clickable.
   */
  const AGG = new Map();
  let aggSeq = 0;
  function agg(text, label, list, how, order) {
    const id = "a" + (++aggSeq);
    AGG.set(id, { label, list, how, order });
    return `<button type="button" class="ev derived" data-agg="${id}" aria-haspopup="dialog">${esc(text)}</button>`;
  }
  const sum = (list) => list.reduce((s, e) => s + (e.amount || 0), 0);
  function basisMix(list) {
    const c = {};
    for (const e of list) if (e.amount != null) c[e.amountBasis || "stated"] = (c[e.amountBasis || "stated"] || 0) + 1;
    const parts = Object.entries(c).filter(([k]) => k !== "stated").map(([k, n]) => `${n} ${k === "annual" ? "yearly" : k === "ceiling" ? "not-to-exceed" : k} figure${n === 1 ? "" : "s"}`);
    return parts.length ? ` The sum mixes kinds of amounts: ${parts.join(", ")}, the rest as stated in titles.` : "";
  }
  const sumHow = (list) => `The sum of the council-approved amounts in ${plural(list.filter((e) => e.amount != null).length, "resolution title")}.${basisMix(list)}${list.some((e) => e.amount == null) ? ` ${plural(list.filter((e) => e.amount == null).length, "record")} state no amount and add nothing.` : ""}`;

  /** What happens at the end date: renewal options (often approved administratively) or a new award. */
  function afterEnd(e) {
    if (!e.end) return "";
    if (e.renewals && e.maxEnd) return `${plural(e.renewals.count, "renewal option")} of ${yrs(e.renewals.months_each)} could extend it to ${fmtDate(e.maxEnd)} without a new bid`;
    return "no renewal options are stated, so the next step is a new award";
  }

  /** An inline fact that opens its evidence. Falls back to plain text when we have none. */
  function ev(event, field, text) {
    const id = event.fields && event.fields[field];
    if (!id) return esc(text);
    const derived = EV.get(id)?.source === "derived";
    return `<button type="button" class="ev${derived ? " derived" : ""}" data-ev="${id}" aria-haspopup="dialog">${esc(text)}</button>`;
  }

  function staffLine(e, max = 2) {
    if (!e.staff || !e.staff.length) return "";
    return e.staff.slice(0, max).map((s) => `<button type="button" class="ev" data-ev="${s.ev}">${esc(s.name)}</button> <span class="muted">(${esc(s.title)})</span>`).join(", ");
  }

  // ------------------------------------------------------------------ matching

  const normKey = (x) => x.toLowerCase().replace(/[^a-z0-9& ]+/g, " ").replace(/\s+/g, " ").trim();
  function parseCompetitors(s) {
    return s.split(",").map(normKey).filter((x) => x.length >= 3);
  }
  const rivalLabel = (k) => (VENDOR_BY_KEY.get(k) ? VENDOR_BY_KEY.get(k).name : k);
  function vendorMatches(e, competitors) {
    if (!competitors.length || !e.vendorKey) return false;
    return competitors.some((c) => e.vendorKey.includes(c));
  }
  // The smallest deal worth chasing: records below it drop out; records with no stated amount stay,
  // since an unstated amount can be large.
  /** A record held by one of the competitors this viewer is watching. */
  const isRival = (e) => vendorMatches(e, parseCompetitors(state.competitors));
  const RIVAL_TAG = '<span class="rival-tag" title="A competitor you are watching">Competitor</span>';
  const bigEnough = (e) => !state.min || e.amount == null || e.amount >= state.min;
  const inMarket = (e, cat, competitors) => (e.cats.includes(cat) || vendorMatches(e, competitors)) && bigEnough(e);

  // ------------------------------------------------------------------ accounts (departments)

  /**
   * One row per department, with plain measurements instead of a blended score.
   * The default order is the dollar value of contracts in your market that end in the next
   * 18 months: money that will be rebid, renewed or switched soon. Every input is a sourced fact.
   */
  const SORTS = {
    renewal: { label: "dollars ending in the next 18 months", key: (a) => [a.renewalValue, a.total] },
    total: { label: "total spend in your market", key: (a) => [a.total, a.renewalValue] },
    count: { label: "number of purchases", key: (a) => [a.contracts.length, a.total] },
    recent: { label: "most recent purchase", key: (a) => [a.lastDate, a.total] },
  };

  function accounts(cat, competitors) {
    const depts = new Map();
    const get = (name) => {
      if (!depts.has(name)) depts.set(name, { dept: name, contracts: [], funding: [] });
      return depts.get(name);
    };
    for (const e of CONTRACTS) if (inMarket(e, cat, competitors)) get(e.dept).contracts.push(e);
    for (const f of FUNDING) if (f.cats.includes(cat) && depts.has(f.dept)) get(f.dept).funding.push(f);
    return [...depts.values()].map((a) => {
      const ending = a.contracts.filter((e) => hasClock(e) && endingSoon(e)).sort((x, y) => x.end.localeCompare(y.end));
      const known = a.contracts.filter((e) => e.route);
      const staff = new Map();
      for (const e of [...a.contracts].sort((x, y) => (y.introduced || "").localeCompare(x.introduced || ""))) {
        for (const s of e.staff || []) if (s.role === "prepared_by" && !staff.has(s.name)) staff.set(s.name, { ...s, n: 0 });
        for (const s of e.staff || []) if (s.role === "prepared_by") staff.get(s.name).n++;
      }
      return {
        ...a, ending,
        renewalValue: ending.reduce((s, e) => s + (e.amount || 0), 0),
        total: a.contracts.reduce((s, e) => s + (e.amount || 0), 0),
        known: known.length, noBid: known.filter(noBid).length,
        lastDate: a.contracts.map((e) => e.passed || e.introduced || "").sort().pop() || "",
        rivals: a.contracts.filter((e) => vendorMatches(e, competitors)),
        staff: [...staff.values()].sort((x, y) => y.n - x.n),
      };
    });
  }

  function sortAccounts(list, sortKey) {
    const k = SORTS[sortKey].key;
    return [...list].sort((x, y) => {
      const a = k(x), b = k(y);
      for (let i = 0; i < a.length; i++) { if (a[i] < b[i]) return 1; if (a[i] > b[i]) return -1; }
      return x.dept.localeCompare(y.dept);
    });
  }

  // ------------------------------------------------------------------ state & routing

  // State lives here; the URL hash mirrors it when the page is served normally, but is never
  // required, because some hosts (an embedded preview) don't pass hash state through.
  const state = { tab: "pursuit", cat: "it_software", competitors: "", min: 0, dept: null, sort: "renewal", rSort: "",
    q: "", fDept: "", fCat: "", fRoute: "", fEnds: "", fType: "contract", fState: "approved", limit: 40,
    set: null /* {label, ids}: the records behind a number, opened from its popover */ };

  const PROFILE_KEY = "incumbent-clock-profile";
  function readHash() {
    let p;
    try { p = new URLSearchParams(location.hash.slice(1)); } catch { p = new URLSearchParams(); }
    // A link carries its own state; otherwise, the profile this viewer set up last time.
    if (!p.has("cat")) {
      try {
        const saved = JSON.parse(localStorage.getItem(PROFILE_KEY) || "null");
        if (saved && CATS[saved.cat]) Object.assign(state, { cat: saved.cat, competitors: saved.competitors || "", min: Number(saved.min) || 0 });
      } catch { /* storage unavailable: defaults */ }
    }
    if (p.get("cat") && CATS[p.get("cat")]) state.cat = p.get("cat");
    if (p.get("tab") && TABS.some((t) => t.id === p.get("tab"))) state.tab = p.get("tab");
    if (p.has("vs")) state.competitors = p.get("vs") || "";
    if (p.has("min")) state.min = Number(p.get("min")) || 0;
    state.dept = p.get("dept");
  }
  function writeHash() {
    const p = new URLSearchParams();
    p.set("tab", state.tab);
    p.set("cat", state.cat);
    if (state.competitors) p.set("vs", state.competitors);
    if (state.min) p.set("min", String(state.min));
    if (state.dept) p.set("dept", state.dept);
    try { history.replaceState(null, "", "#" + p.toString()); } catch { /* sandboxed host */ }
    try { localStorage.setItem(PROFILE_KEY, JSON.stringify({ cat: state.cat, competitors: state.competitors, min: state.min })); } catch { /* private window */ }
  }
  function go(patch) {
    Object.assign(state, patch);
    writeHash();
    render();
    window.scrollTo({ top: 0 });
  }

  // ------------------------------------------------------------------ frame

  function render() {
    closePop();
    AGG.clear();
    const s = SITE.meta.stats || {};
    const body = state.dept ? deptView(state.dept)
      : state.tab === "pursuit" ? pursuitView()
      : state.tab === "sell" ? sellView()
      : state.tab === "clock" ? clockView()
      : state.tab === "compete" ? competeView()
      : state.tab === "research" ? researchView()
      : howView();
    app.innerHTML = `
      <header class="masthead column">
        <h1>Incumbent Cl${clockFace()}ck</h1>
        <p class="lede">Who holds ${esc(CITY)}'s city contracts, how they won them, and when they end.</p>
        <p class="provenance">From ${plural(s.matters || 0, "City Council resolution")} and ${plural(s.texts || 0, "staff memo")}, ${fmtDate(SITE.meta.since)} to ${fmtDate(SITE.meta.through)}. Updated ${fmtDay((SITE.meta.crawled || SITE.meta.generated || SITE.meta.today).slice(0, 10))}.</p>
      </header>
      <nav class="tabs" role="tablist" aria-label="Sections">
        ${TABS.map((t) => `<button type="button" role="tab" id="tab-${t.id}" aria-selected="${!state.dept && state.tab === t.id}" data-tab="${t.id}">${t.label}</button>`).join("")}
      </nav>
      <div role="tabpanel" aria-labelledby="tab-${state.tab}">${body}</div>
      <footer>Built from public records published by the City of Ann Arbor through Legistar. Check the source before you act on any fact here.</footer>`;
    wire();
  }

  /**
   * The seller's profile: what they sell, who they compete with, the smallest deal worth their time.
   * Every view on the Where to sell and Contract clock tabs is computed from these three settings.
   * Saved in this browser and in the link, so a shared link opens on the same view.
   */
  function profileForm() {
    const keys = parseCompetitors(state.competitors);
    const catOptions = Object.keys(CATS).map((k) => `<option value="${k}"${k === state.cat ? " selected" : ""}>${esc(CATS[k])}</option>`).join("");
    const minOptions = MIN_SIZES.map(([v, l]) => `<option value="${v}"${v === state.min ? " selected" : ""}>${esc(l)}</option>`).join("");
    return `<section class="profile" aria-labelledby="profile-h">
      <h2 id="profile-h" class="panel-title">Your company</h2>
      <form id="profile" class="fields" onsubmit="return false">
        <label class="field"><span>What you sell</span><select id="cat">${catOptions}</select></label>
        <div class="field wide"><label for="vs">Competitors to watch</label>
          <div class="combo">
            <div class="chipbox">${keys.map((k) => `<span class="chip rival"><button type="button" class="chip-go" data-rivalgo="${esc(k)}" title="Show on the timeline">${esc(rivalLabel(k))}</button><button type="button" data-unrival="${esc(k)}" aria-label="Remove ${esc(rivalLabel(k))}">×</button></span>`).join("")}<input id="vs" type="text" role="combobox" aria-expanded="false" aria-controls="vs-list" aria-autocomplete="list" autocomplete="off" placeholder="${keys.length ? "Add another" : `Pick or type a vendor ${esc(CITY)} has paid`}"><button type="button" class="combo-toggle" id="vs-toggle" tabindex="-1" aria-label="Show all vendors">▾</button></div>
            <div class="combo-list" id="vs-list" role="listbox" aria-label="Vendors" hidden></div>
          </div>
        </div>
        <label class="field"><span>Smallest deal worth chasing</span><select id="min">${minOptions}</select></label>
      </form>
      <p class="examples"><span class="muted">Examples:</span> ${PRESETS.map((p) => `<button type="button" data-preset="${p.cat}" aria-pressed="${p.cat === state.cat}">${esc(p.label)}</button>`).join("")}</p>
    </section>`;
  }

  /** "IT and software, $100K and up, plus Tyler Technologies": the profile in words, for headings. */
  function profileWords() {
    const keys = parseCompetitors(state.competitors);
    let w = phrase(state.cat);
    if (state.min) w += ` over ${money(state.min)}`;
    return w;
  }
  /** Headings that list contracts also include the watched competitors' contracts in other markets: say so. */
  function plusRivals() {
    const keys = parseCompetitors(state.competitors);
    return keys.length ? `, plus your ${keys.length === 1 ? "competitor's" : "competitors'"}` : "";
  }

  /** How long a vendor has held work from this department: a dashed number that lists the awards. */
  function heldSince(e) {
    const h = historyOf(e);
    // A memo may say the relationship is older than these records ("in place since 2018").
    const stated = h.map((x) => x.fields && x.fields.since_year && { x, ev: EV.get(x.fields.since_year) }).filter(Boolean)
      .sort((a, b) => a.ev.value - b.ev.value)[0];
    const firstYear = Number((h[0].passed || h[0].introduced || "").slice(0, 4));
    const memo = stated && stated.ev.value < firstYear ? `${ev(stated.x, "since_year", `since ${stated.ev.value}`)}, ` : "";
    if (h.length < 2) return memo ? `${memo}<span class="muted">1 award here</span>` : '<span class="muted">first award</span>';
    const first = h[0], last = h[h.length - 1];
    const sole = h.filter(noBid).length;
    const how = `Every approved award from ${e.dept} to ${e.vendor} since ${fmtDate(SITE.meta.since)}, oldest first. ${sole ? `${sole} of ${h.length} ${sole === 1 ? "was" : "were"} sole source or emergency purchases.` : ""} ${first.amount != null && last.amount != null && first !== last ? `First award ${moneyExact(first.amount)}, latest ${moneyExact(last.amount)}.` : ""}`;
    return memo + agg(memo ? `${h.length} awards` : `since ${firstYear}, ${h.length} awards`, `${e.vendor} at ${e.dept}`, h, how.replace(/\s+/g, " ").trim(), "time");
  }

  // ------------------------------------------------------------------ tab: for Pursuit

  /** The incumbent in a market that has held one department's work the longest (for the tour). */
  function entrenched(cat) {
    const opps = CONTRACTS.filter((e) => e.cats.includes(cat) && hasClock(e) && endingSoon(e));
    return opps.map((e) => ({ e, h: historyOf(e) })).sort((a, b) => b.h.length - a.h.length || b.h.filter(noBid).length - a.h.filter(noBid).length || (b.e.amount || 0) - (a.e.amount || 0))[0];
  }

  const TOUR = [
    { title: "Contracts ending soon, for a software vendor", note: () => {
        const o = CONTRACTS.filter((e) => e.cats.includes("it_software") && hasClock(e) && endingSoon(e));
        return `${plural(o.length, "IT contract")}, ${money(sum(o))}, ending by ${BY}.`;
      }, run: () => { tourProfile(); scrollToId("opp-h"); } },
    { title: "Where an end date comes from", note: () => "The memo sentence behind the first date, and the arithmetic.",
      run: () => { tourProfile(); pinFirst("#opp-h ~ .records-wrap tbody tr:first-child td:first-child [data-ev]"); } },
    { title: "The contracts behind a total", note: () => "Every sum opens the records it adds up.",
      run: () => { tourProfile(); pinFirst("#opp-sum [data-agg]"); } },
    { title: "An entrenched incumbent", note: () => {
        const x = entrenched("it_software");
        if (!x || x.h.length < 2) return "How long each incumbent has held the work.";
        const first = x.h[0], last = x.h[x.h.length - 1], sole = x.h.filter(noBid).length;
        const memoYear = Math.min(...x.h.map((r) => (r.fields.since_year && EV.get(r.fields.since_year).value) || 9999));
        return `${x.e.vendor}: ${x.h.length} awards since ${(first.passed || first.introduced).slice(0, 4)}${sole ? `, ${sole} sole source` : ""}${first.amount && last.amount && last.amount > first.amount ? `, ${money(first.amount)} to ${money(last.amount)}` : ""}${memoYear < 9999 ? `; the memo says since ${memoYear}` : ""}.`;
      }, run: () => {
        tourProfile();
        const x = entrenched("it_software");
        const row = x && [...document.querySelectorAll("#opp-h ~ .records-wrap tbody tr")].find((tr) => tr.querySelector(`a[data-file="${x.e.file}"]`));
        pinFirst(row ? row.querySelector("[data-agg]") : null);
      } },
    { title: "A competitor's contracts", note: () => "Tyler Technologies, added as a competitor to watch.",
      run: () => { tourProfile("tyler technologies"); scrollToId("rival-h"); } },
    { title: "How Ann Arbor awards contracts", note: () => "Competed, cooperative or sole source, by dollars and by department.",
      run: () => { Object.assign(state, { tab: "compete", dept: null, set: null }); writeHash(); render(); window.scrollTo({ top: 0 }); } },
    { title: "Search every record", note: () => `Preloaded: sole-source contracts ending by ${BY}.`,
      run: () => applyQuick(0) },
    { title: "One record, start to finish", note: () => "How a council title becomes vendor, amount, method and end date.",
      run: () => goHow("how-record") },
  ];

  function tourProfile(competitors = "") {
    Object.assign(state, { tab: "sell", dept: null, set: null, cat: "it_software", competitors, min: 0, sort: "renewal" });
    writeHash(); render();
  }
  function scrollToId(id) { const el = document.getElementById(id); if (el) el.scrollIntoView({ block: "start" }); }
  function pinFirst(selOrEl) {
    const el = typeof selOrEl === "string" ? document.querySelector(selOrEl) : selOrEl;
    if (!el) return;
    el.scrollIntoView({ block: "center" });
    openPop(el, true);
  }
  function runTour(i) { const t = TOUR[i]; if (t) t.run(); }

  function pursuitView() {
    const repo = SITE.meta.repo;
    return `<section class="column pursuit">
      <h2 class="how-title">Tour</h2>
      <p class="lead">Eight stops. Each opens the tool in the right place.</p>
      <ol class="tour">${TOUR.map((t, i) => `<li><button type="button" class="tour-step" data-tour="${i}"><span class="tour-title">${esc(t.title)}</span><span class="tour-note">${esc(t.note())}</span></button></li>`).join("")}</ol>
      <p class="small muted">Facts with a dotted or dashed underline show where they came from when you point at them. Click the fact itself to keep its preview open.</p>

      <h2 id="run-h">Run it</h2>
      <p>Python 3.9 or later. No installs; the data is in the repo.${repo ? ` <a href="${esc(repo)}" target="_blank" rel="noopener">${esc(repo.replace(/^https?:\/\//, ""))}</a>` : ""}</p>
      <pre class="code">python3 -m clock serve      # the site at localhost:8000
python3 -m clock refresh    # fetch what changed on Legistar, rebuild
python3 -m pytest -q        # tests</pre>
    </section>`;
  }

  // ------------------------------------------------------------------ tab: where to sell

  function sellView() {
    const competitors = parseCompetitors(state.competitors);
    const accts = sortAccounts(accounts(state.cat, competitors), state.sort);
    const market = CONTRACTS.filter((e) => inMarket(e, state.cat, competitors));
    let opps = market.filter((e) => hasClock(e) && endingSoon(e)).sort((a, b) => a.end.localeCompare(b.end));
    // Nothing ends in the next 18 months? Stretch the window to the last known end date in this market,
    // so a quiet market still shows what's coming (and says the window moved).
    let horizon = WINDOW_END, by = BY, widened = false;
    if (!opps.length) {
      const later = market.filter((e) => hasClock(e) && e.end && monthsFromToday(e.end) > 0).sort((a, b) => a.end.localeCompare(b.end));
      if (later.length) {
        opps = later; widened = true;
        horizon = d(later[later.length - 1].end);
        by = `${MONTHS_LONG[horizon.getMonth()]} ${horizon.getFullYear()}`;
      }
    }
    const label = `${CITY} ${profileWords()} contracts ending by ${by}`;
    const depts = new Set(opps.map((e) => e.dept));
    return `${profileForm()}
      <section aria-labelledby="opp-h">
        <h2 id="opp-h">Contracts ending by ${esc(by)}</h2>
        ${widened ? `<p class="note">None end by ${esc(BY)}, so this shows every known end date ahead in ${esc(phrase(state.cat))}, through ${esc(by)}.</p>` : ""}
        ${opps.length ? `<p class="sub" id="opp-sum">${agg(plural(opps.length, "contract"), label, opps, widened ? `Approved service contracts in this market with a quoted or calculated end date after today. None falls in the next 18 months, so the list runs to the last one.` : "Approved service contracts in this market whose end date, quoted or calculated, falls in the next 18 months.")}, ${agg(money(sum(opps)), label, opps, sumHow(opps))}, ${plural(depts.size, "department")}${widened ? "" : ", in the next 18 months"}. Soonest first.</p>
        ${runway(opps, horizon)}
        <div class="records-wrap">${recordsTable(opps, { dept: true, ends: true, renewals: true, held: true, sortBy: "end" })}</div>
        <p class="small muted">${coverage(market)}</p>
        ${feedLink()}` : `<p class="empty">No ${esc(profileWords())} contract has a known end date ahead. ${state.min ? "Lower the deal size or pick another market." : "Pick another market."}</p>`}
      </section>

      ${pendingSection(competitors)}

      ${recentSection(competitors)}

      ${competitors.length ? rivalSection(competitors) : ""}

      <section aria-labelledby="acct-h">
        <h2 id="acct-h">Departments buying ${esc(phrase(state.cat))}</h2>
        <p class="sub">Ordered by dollars ending by ${esc(BY)}. The ${term("department")} that requests a purchase scopes it, writes the memo and pays. <a href="#how-order" data-howsec="how-order">Why this order</a></p>
        <p class="sortline"><label for="sort">Order by</label> <select id="sort">${Object.entries(SORTS).map(([k, v]) => `<option value="${k}"${k === state.sort ? " selected" : ""}>${esc(v.label)}</option>`).join("")}</select></p>
        ${accts.length ? `<ol class="ranked">${accts.slice(0, 10).map(acctItem).join("")}</ol>` : `<p class="empty">No approved ${esc(profileWords())} purchases. Pick another market${state.min ? " or lower the deal size" : ""}.</p>`}
        ${accts.length > 10 ? `<p class="small muted">${plural(accts.length - 10, "more department")} in this market.</p>` : ""}
        ${accts.length && canSave() ? `<p class="small"><button type="button" class="ev" id="csv">Download departments (CSV)</button></p>` : ""}
      </section>`;
  }

  /**
   * The runway: the next 18 months as a strip, each contract a dot at its end date, sized by amount,
   * colored by how it was awarded. Contracts ending the same month stack. Each dot opens its end date.
   */
  function runway(list, horizon = WINDOW_END) {
    if (!list.length) return "";
    const W = 760, L = 14, R = 14, base = 0;
    const span = (horizon - TODAY);
    const months = Math.max(1, Math.ceil(span / (1000 * 60 * 60 * 24 * 30.44)));
    const step = months <= 18 ? 3 : months <= 36 ? 6 : 12;
    const x = (iso) => L + ((W - L - R) * Math.max(0, Math.min(1, (d(iso) - TODAY) / span)));
    const maxA = Math.max(1, ...list.map((e) => e.amount || 0));
    const rad = (e) => 3.5 + 7.5 * Math.sqrt((e.amount || 0) / maxA);
    const stacks = new Map();
    const dots = [...list].sort((a, b) => (b.amount || 0) - (a.amount || 0)).map((e) => {
      const k = e.end.slice(0, 7);
      const r = rad(e);
      const y0 = stacks.get(k) || 0;
      stacks.set(k, y0 + 2 * r + (isRival(e) ? 9 : 3));
      return { e, r, cx: x(e.end), cy: y0 + r + (isRival(e) ? 3 : 0) };
    });
    const top = Math.max(...[...stacks.values()]) + 22;
    // Name the tall stacks: many contracts ending in one month is itself a finding (often a fiscal year end).
    const counts = new Map();
    for (const e of list) { const k = e.end.slice(0, 7); counts.set(k, (counts.get(k) || 0) + 1); }
    const H = top + 34;
    const Y = (v) => top - v; // stack upward from the axis
    const ticks = [];
    for (let m = 0; m <= months; m += step) {
      const t = new Date(TODAY); t.setMonth(t.getMonth() + m);
      ticks.push({ x: x(t.toISOString().slice(0, 10)), label: m === 0 ? "Today" : `${MONTHS[t.getMonth()]} ${t.getFullYear()}` });
    }
    return `<figure class="runway"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${list.length} contracts by end date">
      <line class="axis" x1="${L}" x2="${W - R}" y1="${top + 2}" y2="${top + 2}"></line>
      ${ticks.map((t) => `<line class="tick" x1="${t.x}" x2="${t.x}" y1="${top + 2}" y2="${top + 8}"></line><text x="${t.x}" y="${top + 24}" text-anchor="${t.x < 40 ? "start" : t.x > W - 60 ? "end" : "middle"}">${t.label}</text>`).join("")}
      ${[...counts].filter(([, c]) => c >= 3).map(([k, c]) => { const cx = x(k + "-15"); return `<text class="stack-label" x="${cx.toFixed(1)}" y="${(top - stacks.get(k) - 6).toFixed(1)}" text-anchor="middle">${c} in ${MONTHS[Number(k.slice(5)) - 1]} ${k.slice(0, 4)}</text>`; }).join("")}
      ${dots.map(({ e, r, cx, cy }) => `${isRival(e) ? `<circle class="rival-ring" cx="${cx.toFixed(1)}" cy="${Y(cy).toFixed(1)}" r="${(r + 3).toFixed(1)}"></circle>` : ""}<circle class="dot r-${routeClass(e)}" cx="${cx.toFixed(1)}" cy="${Y(cy).toFixed(1)}" r="${r.toFixed(1)}" data-ev="${e.fields.expires || ""}" tabindex="0"><title>${esc(e.vendor || "Vendor not stated")}${isRival(e) ? " (competitor)" : ""}, ${esc(money(e.amount))}, ends ${esc(fmtDay(e.end))}</title></circle>`).join("")}
    </svg><figcaption>Each dot is a contract at its end date, sized by amount. ${legendDots()}${list.some(isRival) ? '<span class="lg"><i class="rival"></i>Your competitors (ringed)</span>' : ""}</figcaption></figure>`;
  }
  const legendDots = () => ["competitive", "cooperative", "sole_source", "unknown"].map((r) => `<span class="lg"><i class="r-${r}"></i>${ROUTE_SHORT[r]}</span>`).join("");

  /** Say plainly what the clock can and can't see in a set of contracts. */
  function coverage(list) {
    const svc = list.filter((e) => e.class === "term"), dated = svc.filter((e) => e.end), undated = svc.filter((e) => !e.end);
    const once = list.filter((e) => e.class === "one_time");
    const parts = [];
    if (svc.length) parts.push(`Known end date: ${agg(String(dated.length), "Service contracts with an end date", dated, "Service contracts in this market with an end date that was quoted or calculated from quoted facts.")} of ${svc.length} ${term("service-contract", "service contracts")} in this market; ${agg(`${undated.length} unknown`, "Service contracts without an end date", undated, "The memo doesn't state a term in a form the site can read yet. Unknown means not found, not that the contract never ends.")}.`);
    if (once.length) parts.push(`${agg(plural(once.length, "one-time purchase"), "One-time purchases", once, "Equipment, supplies and construction projects. Nothing renews, so they have no end date to track.")} not shown (${term("one-time", "nothing to renew")}).`);
    return parts.join(" ");
  }

  function feedLink() {
    if (window.EMBEDDED) return "";
    return `<p class="small muted">Get new items in this market as they happen: <a href="feeds/${esc(state.cat)}.xml">subscribe</a> in Slack, Outlook or a feed reader (or <a href="feeds/all.xml">every market</a>).</p>`;
  }

  function pendingSection(competitors) {
    const list = PENDING.filter((e) => inMarket(e, state.cat, competitors))
      .sort((a, b) => (a.agenda || a.introduced || "").localeCompare(b.agenda || b.introduced || ""));
    if (!list.length) return "";
    return `<section aria-labelledby="pend-h">
      <h2 id="pend-h">Upcoming council votes</h2>
      <p class="sub">${agg(plural(list.length, "item"), "Not yet voted on", list, "Resolutions in this market that are on an agenda but have no vote recorded yet. They are not counted anywhere else on this page.")} on the agenda, ${term("pending", "not yet voted on")}.</p>
      <ul class="pending">${list.map((e) => `<li${isRival(e) ? ' class="rival"' : ""}><span class="when">${fmtDay(e.agenda || e.introduced)}</span> ${recordLink(e)} ${e.vendor ? ev(e, "vendor", e.vendor) + (isRival(e) ? " " + RIVAL_TAG : "") + ", " : ""}${e.amount != null ? ev(e, "amount", money(e.amount)) + ". " : ""}<span class="muted">${esc(e.title)}</span></li>`).join("")}</ul>
    </section>`;
  }

  /** Newly approved in this market: new incumbents, and contracts whose clock just started. */
  function recentSection(competitors) {
    const cutoff = new Date(TODAY); cutoff.setDate(cutoff.getDate() - 90);
    const iso = cutoff.toISOString().slice(0, 10);
    const list = CONTRACTS.filter((e) => inMarket(e, state.cat, competitors) && (e.passed || "") >= iso)
      .sort((a, b) => (b.passed || "").localeCompare(a.passed || ""));
    if (!list.length) return "";
    return `<section aria-labelledby="new-h">
      <h2 id="new-h">Approved in the last 90 days</h2>
      <ul class="pending">${list.slice(0, 8).map((e) => `<li${isRival(e) ? ' class="rival"' : ""}><span class="when">${fmtDay(e.passed)}</span> ${e.vendor ? ev(e, "vendor", e.vendor) + (isRival(e) ? " " + RIVAL_TAG : "") : '<span class="muted">vendor not stated</span>'}, ${e.amount != null ? ev(e, "amount", money(e.amount)) : "amount not stated"}, ${esc(e.dept)}${e.end && hasClock(e) ? `, ends ${ev(e, "expires", fmtDate(e.end))}` : ""} ${recordLink(e)}</li>`).join("")}</ul>
      ${list.length > 8 ? `<p class="small muted">${agg(`All ${list.length}`, "Approved in the last 90 days", list, "Approved contracts in this market with a council vote in the last 90 days.")}</p>` : ""}
    </section>`;
  }

  function acctItem(a) {
    const first = a.ending[0];
    return `<li class="acct">
      <div>
        <h3><a href="#" data-dept="${esc(a.dept)}">${esc(a.dept)}</a></h3>
        ${first ? `<p class="verdict">Next: ${first.vendor ? ev(first, "vendor", first.vendor) : "vendor not stated"}, ends ${ev(first, "expires", fmtDate(first.end))}${first.renewals && first.maxEnd ? `, options to ${ev(first, "renewals", fmtDate(first.maxEnd))}` : ""}</p>` : ""}
        <dl class="metrics">
          <div><dt>Ending by ${esc(BY)}</dt><dd>${a.ending.length ? agg(money(a.renewalValue), `${a.dept}: contracts ending by ${BY}`, a.ending, sumHow(a.ending)) : '<span class="muted">none known</span>'}</dd></div>
          <div><dt>Total in market</dt><dd>${a.total ? agg(money(a.total), `${a.dept}: everything in ${phrase(state.cat)}`, a.contracts, sumHow(a.contracts)) : "not stated"}</dd></div>
          <div><dt>Purchases</dt><dd>${agg(String(a.contracts.length), `${a.dept}: purchases in ${phrase(state.cat)}`, a.contracts, "Every approved contract, purchase order and amendment in this market requested by this department.")}</dd></div>
          <div><dt>${term("sole-source", "Not competed")}</dt><dd>${a.known ? agg(`${a.noBid} of ${a.known}`, `${a.dept}: how awards were made`, a.contracts.filter((e) => e.route), `Of the ${plural(a.known, "award")} whose method is stated, ${a.noBid} ${a.noBid === 1 ? "was" : "were"} sole source or emergency purchases.`) : `<span class="muted">${term("no-method", "method not stated")}</span>`}</dd></div>
        </dl>
        ${a.rivals.length ? `<p class="who rival-note">${RIVAL_TAG} ${[...new Set(a.rivals.map((e) => e.vendor))].map(esc).join(", ")} ${a.rivals.length === 1 ? "holds a contract" : `hold ${a.rivals.length} contracts`} here${a.rivals.some((e) => hasClock(e) && endingSoon(e)) ? `, ${a.rivals.filter((e) => hasClock(e) && endingSoon(e)).length} ending by ${esc(BY)}` : ""}.</p>` : ""}
        ${a.staff.length ? `<p class="who">Memo authors: ${a.staff.slice(0, 2).map((s) => `<button type="button" class="ev" data-ev="${s.ev}">${esc(s.name)}</button> <span class="muted">${esc(s.title)}${s.n > 1 ? `, ${s.n} memos` : ""}</span>`).join("; ")}</p>` : ""}
      </div>
    </li>`;
  }

  function rivalSection(competitors) {
    const theirs = CONTRACTS.filter((e) => vendorMatches(e, competitors) && bigEnough(e)).sort((x, y) => (x.end || "9999").localeCompare(y.end || "9999"));
    return `<section aria-labelledby="rival-h">
      <h2 id="rival-h">Competitors' contracts</h2>
      ${theirs.some(hasClock) ? clockChart(theirs.filter(hasClock)) : ""}
      ${theirs.length ? `<div class="records-wrap">${recordsTable(theirs, { dept: true, ends: true, held: true, sortBy: "end", noRival: true })}</div>` : `<p class="empty">No approved contracts match ${parseCompetitors(state.competitors).map((k) => `"${esc(rivalLabel(k))}"`).join(" or ")}. Pick a name from the list or shorten it.</p>`}
    </section>`;
  }

  // ------------------------------------------------------------------ tab: contract clock

  function clockView() {
    const competitors = parseCompetitors(state.competitors);
    return `${profileForm()}
      <section aria-labelledby="clock-h">
        <h2 id="clock-h">Timeline of ${esc(CITY)}'s ${esc(profileWords())} contracts${plusRivals()}</h2>
        <p class="sub">One bar per vendor and department, first award to last known end. Dashed: renewal options. Shaded: now to ${esc(BY)}.</p>
        ${clockChart(CONTRACTS.filter((e) => inMarket(e, state.cat, competitors) && hasClock(e)))}
        ${missingRivals(competitors)}
        <p class="small muted">${coverage(CONTRACTS.filter((e) => inMarket(e, state.cat, competitors)))}</p>
      </section>`;
  }

  /** Watched competitors who can't appear on a timeline, and why, so a missing row is never a mystery. */
  function missingRivals(keys) {
    const out = keys.map((k) => {
      const theirs = CONTRACTS.filter((e) => e.vendorKey && e.vendorKey.includes(k) && bigEnough(e));
      if (theirs.some(hasClock)) return null;
      return `<b>${esc(rivalLabel(k))}</b> ${theirs.length ? `has only one-time purchases (${plural(theirs.length, "council item")}), which don't renew` : "has no approved council contracts"}`;
    }).filter(Boolean);
    return out.length ? `<p class="small" id="rival-missing">Not on the timeline: ${out.join("; ")}.</p>` : "";
  }

  // ------------------------------------------------------------------ tab: competition
  //
  // The same records, read as a resident or a reporter would: how much of what council approved was
  // competed, which departments buy without competition, which vendors keep getting sole-source awards.
  // These follow red-flag indicators used in procurement monitoring (Open Contracting Partnership);
  // a flag is a question to ask, not a finding: some work really has only one supplier.

  function competeView() {
    const all = CONTRACTS;
    const total = sum(all);
    const groups = ["competitive", "cooperative", "sole_source", "unknown"].map((r) => {
      const list = all.filter((e) => routeClass(e) === r);
      return { r, list, amt: sum(list) };
    });
    const known = all.filter((e) => e.route);
    const unknownRoute = all.filter((e) => !e.route);
    const nb = known.filter(noBid);
    // Departments by not-competed dollars.
    const byDept = new Map();
    for (const e of all) {
      if (!byDept.has(e.dept)) byDept.set(e.dept, { dept: e.dept, all: [], nb: [], known: [] });
      const x = byDept.get(e.dept);
      x.all.push(e); if (e.route) x.known.push(e); if (noBid(e)) x.nb.push(e);
    }
    const depts = [...byDept.values()].filter((x) => x.nb.length).sort((a, b) => sum(b.nb) - sum(a.nb));
    const maxNb = Math.max(1, ...depts.map((x) => sum(x.nb)));
    // Repeat sole-source awards to one vendor from one department.
    const repeats = [...HISTORY.values()].map((h) => ({ h, nb: h.filter(noBid) })).filter((x) => x.nb.length >= 2)
      .sort((a, b) => b.nb.length - a.nb.length || sum(b.nb) - sum(a.nb));
    const raised = all.filter((e) => e.class === "change" && e.amountBasis === "increase");
    const soon = all.filter((e) => noBid(e) && hasClock(e) && endingSoon(e)).sort((a, b) => a.end.localeCompare(b.end));
    const pct = (a) => (total ? Math.round((100 * a) / total) : 0);

    return `<section class="compete">
      <h2 class="how-title">How ${esc(CITY)} awards its contracts</h2>
      <p class="lead">Council-approved vendor contracts, ${fmtDate(SITE.meta.since)} to ${fmtDate(SITE.meta.through)}, by how the vendor was chosen.</p>

      <figure class="split">
        <div class="splitbar" role="img" aria-label="${groups.map((g) => `${ROUTE_SHORT[g.r]} ${pct(g.amt)}%`).join(", ")}">${groups.map((g) => `<span class="r-${g.r}" style="flex:${Math.max(g.amt, total * 0.004)}"></span>`).join("")}</div>
        <dl class="splitkey">${groups.map((g) => `<div><dt><i class="r-${g.r}"></i>${g.r === "unknown" ? term("no-method", "Method not stated") : term(g.r === "sole_source" ? "sole-source" : g.r, g.r === "sole_source" ? "Sole source or emergency" : ROUTE_SHORT[g.r])}</dt><dd><b>${agg(money(g.amt), `${ROUTE_SHORT[g.r]} awards`, g.list, sumHow(g.list))}</b> ${pct(g.amt)}% · ${plural(g.list.length, "contract")}</dd></div>`).join("")}</dl>
      </figure>
      <p class="small muted">Of ${known.length} awards with a stated method, ${agg(String(nb.length), "Sole-source and emergency awards", nb, sumHow(nb))} were not competed. ${agg(`${unknownRoute.length} more`, "Contracts whose award method isn't stated", unknownRoute, "Neither the title nor the memo says how the vendor was chosen. Most are amendments, change orders and renewals, whose memo describes the change rather than the original award.")} don't say how the vendor was chosen (${term("no-method", "why")}).</p>

      <h2 id="cmp-dept">Sole-source spending by department</h2>
      <div class="hbars">${depts.slice(0, 10).map((x) => `<div class="hb"><a href="#" data-dept="${esc(x.dept)}" class="hb-name">${esc(x.dept)}</a><span class="hb-track"><span class="hb-fill" style="width:${((100 * sum(x.nb)) / maxNb).toFixed(1)}%"></span></span><span class="hb-val">${agg(money(sum(x.nb)), `${x.dept}: sole-source and emergency awards`, x.nb, sumHow(x.nb))}</span><span class="hb-note">${x.nb.length} of ${x.known.length}</span></div>`).join("")}</div>
      <p class="small muted">Bar: sole-source and emergency dollars. Right: not-competed awards out of those with a stated method.</p>

      <h2 id="cmp-repeat">Repeat sole-source vendors</h2>
      <p class="sub">The same vendor, sole-sourced more than once by the same department.</p>
      ${repeats.length ? `<div class="records-wrap"><table class="records"><thead><tr><th>Vendor</th><th>Department</th><th class="num">Sole-source awards</th><th class="num">Total</th><th>Years</th></tr></thead><tbody>${repeats.slice(0, 12).map(({ h, nb }) => `<tr><td>${ev(nb[nb.length - 1], "vendor", nb[nb.length - 1].vendor)}</td><td><a href="#" data-dept="${esc(nb[0].dept)}">${esc(nb[0].dept)}</a></td><td class="num">${agg(String(nb.length), `${nb[0].vendor} at ${nb[0].dept}`, h, `Every approved award from this department to this vendor, oldest first. ${nb.length} of ${h.length} were sole source or emergency.`, "time")}</td><td class="num">${money(sum(nb))}</td><td class="nw">${(() => { const y0 = (nb[0].passed || nb[0].introduced).slice(0, 4), y1 = (nb[nb.length - 1].passed || nb[nb.length - 1].introduced).slice(0, 4); return y0 === y1 ? y0 : `${y0}–${y1}`; })()}</td></tr>`).join("")}</tbody></table></div>` : `<p class="empty">None.</p>`}
      <p class="small muted">A pattern worth asking about, not evidence of a problem: software support often has only one possible supplier.</p>

      ${soon.length ? `<h2 id="cmp-soon">Sole-source contracts ending by ${esc(BY)}</h2>
      <p class="sub">The next chance to compete this work.</p>
      <div class="records-wrap">${recordsTable(soon, { dept: true, ends: true, renewals: true, held: true, sortBy: "end" })}</div>` : ""}

      ${raised.length ? `<h2 id="cmp-raised">Amendments that raised a contract's value</h2>
      <p class="sub">${agg(plural(raised.length, "amendment"), "Amendments that increased a contract amount", raised, "Amendments and change orders whose title states an increase.")}, ${agg(money(sum(raised)), "Amendments that increased a contract amount", raised, sumHow(raised))} as approved. ${term("amendment", "Amendments")} add money or time without a new bid.</p>` : ""}
    </section>`;
  }

  // ------------------------------------------------------------------ department page

  function deptView(name) {
    const all = CONTRACTS.filter((e) => e.dept === name);
    const mine = all.filter((e) => e.cats.includes(state.cat));
    const list = mine.length ? mine : all;
    const total = list.reduce((s, e) => s + (e.amount || 0), 0);
    const known = list.filter((e) => e.route);
    const byVendor = new Map();
    for (const e of list) {
      const k = e.vendorKey || "(not stated)";
      if (!byVendor.has(k)) byVendor.set(k, { name: e.vendor || "Vendor not stated", total: 0, n: 0, rival: isRival(e) });
      const v = byVendor.get(k); v.total += e.amount || 0; v.n++;
    }
    const vendors = [...byVendor.values()].sort((a, b) => b.total - a.total);
    const top = vendors.slice(0, 8);
    const rest = vendors.slice(8);
    if (rest.length) top.push({ other: true, name: plural(rest.length, "other vendor"), total: rest.reduce((s, v) => s + v.total, 0), n: rest.reduce((s, v) => s + v.n, 0) });
    const max = Math.max(1, ...top.map((v) => v.total));
    const routes = ["competitive", "cooperative", "sole_source", "unknown"].map((r) => ({
      r, n: list.filter((e) => routeClass(e) === r).length,
    })).filter((x) => x.n);
    const staff = new Map();
    for (const e of all) for (const s of e.staff || []) {
      const k = s.name;
      if (!staff.has(k)) staff.set(k, { ...s, n: 0, last: "" });
      const x = staff.get(k); x.n++;
      if ((e.introduced || "") > x.last) Object.assign(x, { last: e.introduced, title: s.title, ev: s.ev });
    }
    const people = [...staff.values()].sort((a, b) => b.n - a.n || b.last.localeCompare(a.last)).slice(0, 8);

    return `
      <p class="back"><a href="#" data-dept="">Back to ${esc(TABS.find((t) => t.id === state.tab).label)}</a></p>
      <header class="column">
        <h2 class="dept-title">${esc(name)}</h2>
        <p class="sub">${mine.length ? `${plural(mine.length, "purchase")} in ${esc(phrase(state.cat))}` : `No purchases in ${esc(phrase(state.cat))}; showing all ${plural(all.length, "purchase")}`} approved by City Council since ${fmtDate(SITE.meta.since)}.</p>
      </header>

      <div class="stats">
        <div class="stat"><b>${agg(money(total), `${name}: approved in total`, list, sumHow(list))}</b><span>approved in total</span></div>
        <div class="stat"><b>${agg(String(list.length), `${name}: contracts and purchase orders`, list, "Every approved contract, purchase order and amendment counted on this page.")}</b><span>contracts and purchase orders</span></div>
        <div class="stat"><b>${known.length ? agg(Math.round((100 * known.filter(noBid).length) / known.length) + "%", `${name}: awards that were not competed`, known.filter(noBid), `${known.filter(noBid).length} of the ${plural(known.length, "award")} whose method is stated were sole source or emergency purchases.`) : "n/a"}</b><span>sole source or emergency, of ${plural(known.length, "award")} with a stated method</span></div>
        <div class="stat"><b>${agg(money(sum(list.filter((e) => hasClock(e) && endingSoon(e)))), `${name}: ending in the next 18 months`, list.filter((e) => hasClock(e) && endingSoon(e)), sumHow(list.filter((e) => hasClock(e) && endingSoon(e))))}</b><span>in contracts ending in the next 18 months</span></div>
      </div>

      ${people.length ? `<h3>Who writes the memos</h3>
      <p class="small muted">The staff named as "Prepared by" or "Reviewed by" on this department's council items: usually the people who scoped the purchase.</p>
      <ul class="people">${people.map((p) => `<li><button type="button" class="ev" data-ev="${p.ev}">${esc(p.name)}</button>, ${esc(p.title)} <span class="muted">(${plural(p.n, "memo")}, latest ${fmtDate(p.last)})</span></li>`).join("")}</ul>` : ""}

      <h3>Who they buy from</h3>
      <div class="bars" role="list">${top.map((v) => `<div class="b${v.rival ? " rival" : ""}" role="listitem"><span class="name" title="${esc(v.name)}${v.rival ? " (competitor)" : ""}">${v.rival ? "◆ " : ""}${esc(v.name)}</span><span class="track"><span class="fill${v.other ? " other" : ""}" style="width:${(100 * v.total) / max}%"></span></span><span class="v">${money(v.total)}</span></div>`).join("")}</div>

      <h3>How they buy</h3>
      <div class="mix" role="img" aria-label="${routes.map((x) => `${ROUTE_SHORT[x.r]}: ${x.n}`).join(", ")}">${routes.map((x) => `<span class="r-${x.r}" style="flex:${x.n}" title="${ROUTE_SHORT[x.r]}: ${x.n}"></span>`).join("")}</div>
      <div class="legend">${routes.map((x) => `<span><i class="r-${x.r}"></i>${ROUTE_SHORT[x.r]} (${x.n})</span>`).join("")}</div>

      <h3>The clock</h3>
      ${clockChart(list.filter(hasClock), true)}

      <h3>Every record</h3>
      <div class="records-wrap">${recordsTable(list, { ends: true })}</div>`;
  }

  // ------------------------------------------------------------------ records table (shared)

  function recordsTable(list, o = {}) {
    const rows = [...list];
    if (o.sortBy === "end") rows.sort((a, b) => (a.end || "9999").localeCompare(b.end || "9999"));
    else if (!o.keepOrder) rows.sort((a, b) => (b.introduced || "").localeCompare(a.introduced || ""));
    const ns = '<span class="muted">not stated</span>';
    return `<table class="records"><thead><tr>
      ${o.ends && o.sortBy === "end" ? `<th>${term("end-basis", "Ends")}</th>` : "<th>Approved</th>"}<th>Vendor</th>${o.dept ? "<th>Department</th>" : ""}<th class="num">Amount</th><th>How awarded</th>${o.ends && o.sortBy !== "end" ? "<th>Ends</th>" : ""}${o.renewals ? `<th>${term("last-end", "Options, then")}</th>` : ""}${o.held ? `<th>${term("held", "Held")}</th>` : ""}<th>Record</th>
    </tr></thead><tbody>${rows.map((e) => `<tr${o.noRival || !isRival(e) ? "" : ' class="rival"'}>
      ${o.ends && o.sortBy === "end" ? `<td class="nw">${e.end ? ev(e, "expires", fmtDate(e.end)) : ns}</td>` : `<td class="nw">${fmtDate(e.passed || e.introduced)}</td>`}
      <td>${e.vendor ? ev(e, "vendor", e.vendor) : ns}${!o.noRival && isRival(e) ? " " + RIVAL_TAG : ""}</td>
      ${o.dept ? `<td><a href="#" data-dept="${esc(e.dept)}">${esc(e.dept)}</a></td>` : ""}
      <td class="num">${e.amount != null ? ev(e, "amount", money(e.amount)) : ns}</td>
      <td class="nw"><span class="route-dot r-${routeClass(e)}"></span>${e.route ? ev(e, "route", ROUTE_SHORT[e.route]) : ns}</td>
      ${o.ends && o.sortBy !== "end" ? `<td class="nw">${e.end && hasClock(e) ? ev(e, "expires", fmtDate(e.end)) : e.class === "one_time" ? '<span class="muted">one-time</span>' : ns}</td>` : ""}
      ${o.renewals ? `<td class="nw">${e.renewals ? `${ev(e, "renewals", optsShort(e.renewals))} → ${ev(e, "expires", fmtDate(e.maxEnd))}` : e.fields.auto_renews ? ev(e, "auto_renews", "renews automatically") : '<span class="muted">none stated</span>'}</td>` : ""}
      ${o.held ? `<td class="nw small">${heldSince(e)}</td>` : ""}
      <td class="nw">${recordLink(e)}</td>
    </tr>`).join("")}</tbody></table>`;
  }

  // ------------------------------------------------------------------ tab: research

  // Ready-made searches: each sets every filter, so the result is the same whatever was set before.
  const QUICK = [
    { label: () => `Sole-source contracts ending by ${BY}`, set: { fRoute: "sole_source", fEnds: "18", rSort: "ending" } },
    { label: () => "Cooperative purchases (MiDEAL, Sourcewell…)", set: { fRoute: "cooperative", rSort: "amount" } },
    { label: () => "Largest IT and software contracts", set: { fCat: "it_software", rSort: "amount" } },
    { label: () => "Everything from Tyler Technologies", set: { q: "tyler", rSort: "newest" } },
    { label: () => "Memos that mention cybersecurity", set: { q: "cyber", rSort: "newest" } },
    { label: () => "On upcoming council agendas", set: { fState: "pending", fType: "all", rSort: "newest" } },
    { label: () => "Service contracts with no end date stated", set: { fEnds: "unknown", rSort: "amount" } },
  ];
  const RESEARCH_DEFAULTS = { q: "", fType: "contract", fDept: "", fCat: "", fRoute: "", fEnds: "", fState: "approved", rSort: "", limit: 40, set: null };
  function applyQuick(i) {
    const qk = QUICK[i];
    if (!qk) return;
    Object.assign(state, RESEARCH_DEFAULTS, qk.set, { tab: "research", dept: null, quick: i });
    writeHash(); render();
    const el = document.getElementById("search-h");
    if (el) el.scrollIntoView({ block: "start" });
  }
  const RSORTS = { "": "Best match", newest: "Newest first", ending: "Ending soonest", amount: "Largest first" };

  function filtered() {
    const terms = state.q.toLowerCase().split(/\s+/).filter((t) => t.length >= 2);
    if (state.set) {
      const ids = new Set(state.set.ids);
      return EVENTS.filter((e) => ids.has(e.id)).map((e) => ({ e, hits: 0 }));
    }
    let list = EVENTS.filter((e) => (state.fType === "all" || e.type === state.fType) && (!state.fState || e.state === state.fState));
    list = list.filter((e) => {
      if (state.fDept && e.dept !== state.fDept) return false;
      if (state.fCat && !e.cats.includes(state.fCat)) return false;
      if (state.fRoute && routeClass(e) !== state.fRoute) return false;
      if (state.fEnds) {
        const m = monthsFromToday(e.end);
        if (state.fEnds === "unknown") { if (e.end) return false; }
        else if (state.fEnds === "past") { if (!(m != null && m <= 0)) return false; }
        else if (!(m != null && m > 0 && m <= Number(state.fEnds))) return false;
      }
      return true;
    });
    const order = (rows) => {
      const k = state.rSort;
      if (k === "newest") return rows.sort((a, b) => (b.e.passed || b.e.introduced || "").localeCompare(a.e.passed || a.e.introduced || ""));
      if (k === "ending") return rows.sort((a, b) => (a.e.end || "9999").localeCompare(b.e.end || "9999"));
      if (k === "amount") return rows.sort((a, b) => (b.e.amount || 0) - (a.e.amount || 0));
      return rows.sort((a, b) => b.hits - a.hits || (b.e.passed || b.e.introduced || "").localeCompare(a.e.passed || a.e.introduced || ""));
    };
    if (state.fEnds === "unknown") list = list.filter((e) => e.class !== "one_time");
    if (!terms.length) return order(list.map((e) => ({ e, hits: 0 })));
    const out = [];
    for (const e of list) {
      const hay = `${e.title} ${e.vendor || ""} ${e.dept} ${e.file}`.toLowerCase();
      const text = (TEXTS[e.id] || "").toLowerCase();
      let ok = true, hits = 0;
      for (const t of terms) {
        const inMeta = hay.includes(t), inText = text.includes(t);
        if (!inMeta && !inText) { ok = false; break; }
        hits += inMeta ? 3 : 1;
      }
      if (ok) out.push({ e, hits });
    }
    return order(out);
  }

  function snippet(e) {
    const terms = state.q.toLowerCase().split(/\s+/).filter((t) => t.length >= 2);
    const text = TEXTS[e.id];
    if (!terms.length || !text) return "";
    const low = text.toLowerCase();
    const i = Math.min(...terms.map((t) => low.indexOf(t)).filter((x) => x >= 0));
    if (!isFinite(i)) return "";
    let lo = Math.max(0, i - 120), hi = Math.min(text.length, i + 220);
    while (lo > 0 && text[lo - 1] !== " ") lo--;
    while (hi < text.length && text[hi] !== " ") hi++;
    let s = esc(text.slice(lo, hi));
    for (const t of terms) s = s.replace(new RegExp(t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi"), (m) => `<mark>${m}</mark>`);
    return `${lo > 0 ? "… " : ""}${s}${hi < text.length ? " …" : ""}`;
  }

  function researchView() {
    const rows = filtered();
    const list = rows.map((r) => r.e);
    const total = list.reduce((s, e) => s + (e.amount || 0), 0);
    const routes = ["competitive", "cooperative", "sole_source", "unknown"].map((r) => ({ r, n: list.filter((e) => routeClass(e) === r).length })).filter((x) => x.n);
    const depts = [...new Set(EVENTS.map((e) => e.dept))].sort();
    const opt = (v, cur, label) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label)}</option>`;
    const shown = rows.slice(0, state.limit);
    const quickOn = (i) => state.quick === i;
    return `
      <section class="column research-intro">
        <h2 class="how-title">Research</h2>
        <p class="lead">Search all ${EVENTS.length.toLocaleString()} ${esc(CITY)} council records (${plural(EVENTS.filter((e) => e.type === "contract").length, "contract")}, ${plural(EVENTS.filter((e) => e.type === "funding").length, "funding action")}) and the text of ${plural(Object.keys(TEXTS).length, "staff memo")}. Ignores your company settings.</p>
        <p class="quick-label">Example searches</p>
        <div class="quick">${QUICK.map((qk, i) => `<button type="button" data-quick="${i}" aria-pressed="${quickOn(i)}">${esc(qk.label())}</button>`).join("")}</div>
        <details class="howsearch"><summary>How search works</summary>
          <p>Every word must appear in the title, vendor, department, record number or memo. Title matches rank first. The totals, the bar and the CSV cover exactly the records listed. ${see0("how-research", "More")}</p>
        </details>
      </section>

      <section aria-labelledby="search-h">
        <h2 id="search-h">Search and filter</h2>
        ${state.set ? `<p class="banner">Showing the ${plural(state.set.ids.length, "record")} behind “${esc(state.set.label)}”. <button type="button" class="ev" id="clear-set">Back to search</button></p>` : ""}
        <form id="search" class="filters" onsubmit="return false" ${state.set ? "hidden" : ""}>
          <label class="wide-field"><span>Words (all must appear)</span><input id="q" type="search" value="${esc(state.q)}" placeholder="body camera, MiDEAL, Tyler, renewal…"></label>
          <label><span>Show</span><select id="fType">${opt("contract", state.fType, "Contracts")}${opt("funding", state.fType, "Funding actions")}${opt("all", state.fType, "Both")}</select></label>
          <label><span>Department</span><select id="fDept">${opt("", state.fDept, "Any")}${depts.map((x) => opt(x, state.fDept, x)).join("")}</select></label>
          <label><span>Market</span><select id="fCat">${opt("", state.fCat, "Any")}${Object.keys(CATS).map((k) => opt(k, state.fCat, CATS[k])).join("")}</select></label>
          <label><span>How awarded</span><select id="fRoute">${opt("", state.fRoute, "Any")}${["competitive", "cooperative", "sole_source", "unknown"].map((k) => opt(k, state.fRoute, ROUTE_SHORT[k])).join("")}</select></label>
          <label><span>Council vote</span><select id="fState">${opt("approved", state.fState, "Approved")}${opt("pending", state.fState, "Not yet voted on")}${opt("not_approved", state.fState, "Did not take effect")}${opt("", state.fState, "Any")}</select></label>
          <label><span>Ends</span><select id="fEnds">${opt("", state.fEnds, "Any time")}${opt("6", state.fEnds, "Within 6 months")}${opt("12", state.fEnds, "Within 12 months")}${opt("18", state.fEnds, `By ${BY}`)}${opt("past", state.fEnds, "Already ended")}${opt("unknown", state.fEnds, "Not stated (service contracts)")}</select></label>
          <label><span>Sort</span><select id="rSort">${Object.entries(RSORTS).map(([k, v]) => opt(k, state.rSort, v)).join("")}</select></label>
        </form>
        <p class="summary">${plural(list.length, "record")}${total ? `, ${agg(money(total), "Search results", list, sumHow(list))} in stated amounts` : ""}.${list.length > shown.length ? ` Showing ${shown.length}, ${!state.rSort && !state.q.trim() ? "newest first" : RSORTS[state.rSort].toLowerCase()}.` : ""}${canSave() ? ` <button type="button" class="ev" id="csv-records">Download ${list.length === 1 ? "it" : `all ${list.length}`} as CSV</button>` : ""}</p>
        ${routes.length && list.length ? `<div class="mix" role="img" aria-label="${routes.map((x) => `${ROUTE_SHORT[x.r]}: ${x.n}`).join(", ")}">${routes.map((x) => `<span class="r-${x.r}" style="flex:${x.n}" title="${ROUTE_SHORT[x.r]}: ${x.n}"></span>`).join("")}</div>
        <div class="legend">${routes.map((x) => `<span><i class="r-${x.r}"></i>${ROUTE_SHORT[x.r]} (${x.n})</span>`).join("")}</div>` : ""}
        ${shown.length ? `<ol class="results">${shown.map(({ e }) => resultItem(e)).join("")}</ol>` : `<p class="empty">No ${esc(CITY)} record matches. Remove a word or a filter${state.fState === "approved" ? `, or set Council vote to "Any"` : ""}.</p>`}
        ${rows.length > shown.length ? `<p><button type="button" class="btn quiet" id="more">Show ${Math.min(40, rows.length - shown.length)} more</button></p>` : ""}
      </section>`;
  }

  function resultItem(e) {
    const sn = snippet(e);
    const facts = [];
    if (e.vendor) facts.push(ev(e, "vendor", e.vendor));
    if (e.amount != null) facts.push(ev(e, "amount", money(e.amount)));
    facts.push(e.route ? ev(e, "route", ROUTE[e.route]) : '<span class="muted">award method not stated</span>');
    if (e.end) facts.push("ends " + ev(e, "expires", fmtDate(e.end)) + (e.renewals ? `, options to ${ev(e, "renewals", fmtDate(e.maxEnd))}` : ""));
    return `<li>
      <p class="r-title">${recordLink(e)} <span class="muted">${fmtDate(e.passed || e.introduced)}, <a href="#" data-dept="${esc(e.dept)}">${esc(e.dept)}</a></span>${e.state !== "approved" ? ` <span class="tag">${esc(STATE_LABEL[e.state])}</span>` : ""}</p>
      <p class="r-head">${esc(e.title)}</p>
      ${e.type === "contract" ? `<p class="r-facts">${facts.join(", ")}.${e.staff && e.staff.length ? ` Memo by ${staffLine(e, 1)}.` : ""}</p>` : ""}
      ${sn ? `<p class="r-snip">${sn}</p>` : ""}
    </li>`;
  }

  // ------------------------------------------------------------------ tab: how it works

  const HOW_SECTIONS = [
    { id: "how-data", title: "The pipeline" },
    { id: "how-record", title: "One record, start to finish" },
    { id: "how-tabs", title: "The tabs" },
    { id: "how-provenance", title: "Reading the underlines" },
    { id: "how-classes", title: "Which contracts have an end date" },
    { id: "how-ends", title: "How end dates are decided" },
    { id: "how-opening", title: "Renewal options" },
    { id: "how-states", title: "What counts" },
    { id: "how-order", title: "Department order" },
    { id: "how-method", title: "How the award method is read" },
    { id: "how-research", title: "Research" },
    { id: "how-limits", title: "Limits" },
    { id: "glossary", title: "Glossary" },
    { id: "how-numbers", title: "By the numbers" },
  ];

  const FIELD_RULE = {
    kind: "Title pattern: the contract type words", vendor: "Title pattern: the name after \"with\", \"to\" or \"from\"",
    amount: "Title pattern: the dollar figure", amount_basis: "Words around the amount (annual, not to exceed, total)",
    fy_range: "Title or memo pattern: \"for FY 2027\"", route: "Title or memo pattern: sole source, RFP, ITB, MiDEAL…",
    term_months: "Memo pattern: \"a three-year agreement\"", start_date: "Memo pattern: a start date", end_date: "Memo pattern: \"through June 30, 2027\"",
    renewals: "Memo pattern: \"two additional one-year periods\"", prepared_by: "Memo header: \"Prepared by:\"", reviewed_by: "Memo header: \"Reviewed by:\"",
    prices_until: "Memo pattern: \"prices firm through\"", since_year: "Memo pattern: \"in place since 2018\" near the vendor's name", auto_renews: "Memo pattern: \"automatically renews\"", expires: "Calculated in code from the facts above",
  };

  /** A real council record, annotated: which words became which fact, and how. */
  function recordTrace() {
    const e = CONTRACTS.find((x) => x.file === "26-0713") || CONTRACTS.find((x) => x.vendor && x.route && x.end && x.amount);
    if (!e) return "";
    const evs = Object.entries(e.fields).map(([f, id]) => ({ f, x: EV.get(id) })).filter((o) => o.x);
    // Title spans: title evidence carries the matched words as its quote, with the rest of the title around it.
    const spans = evs.filter((o) => o.x.source === "title" && o.x.ctx && o.f !== "amount_basis")
      .map((o) => ({ f: o.f, id: o.x.id, start: (o.x.ctx.before || "").replace(/^…\s*/, "").length, text: o.x.ctx.quote }))
      .filter((sp) => e.title.substr(sp.start, sp.text.length) === sp.text)
      .sort((a, b) => a.start - b.start);
    let html = "", at = 0;
    for (const sp of spans) {
      if (sp.start < at) continue;
      html += esc(e.title.slice(at, sp.start)) + `<span class="ann ann-${sp.f}" data-ev="${sp.id}"><span class="ann-text">${esc(sp.text)}</span><span class="ann-tag">${esc(FIELD[sp.f] || sp.f)}</span></span>`;
      at = sp.start + sp.text.length;
    }
    html += esc(e.title.slice(at));
    const rows = evs.filter((o) => o.f !== "amount_basis" || true).map((o) => `<tr><td>${esc(FIELD[o.f] || o.f)}</td><td>${ev(e, o.f, valueText(o.x))}</td><td class="muted">${o.x.source === "title" ? "Title" : o.x.source === "derived" ? "Calculated" : "Memo"}</td><td class="muted small">${esc(FIELD_RULE[o.f] || o.x.rule)}</td></tr>`).join("");
    const memoFact = evs.find((o) => o.x.source === "text" && o.f === "route") || evs.find((o) => o.x.source === "text" && o.x.ctx);
    return `<figure class="trace">
      <p class="trace-step"><span class="step-n">1</span><span>The council record, as Legistar's API returns it: record ${recordLink(e)}, requested by ${esc(e.dept)}, approved ${esc(fmtDay(e.passed || e.introduced))}.</span></p>
      <p class="trace-title">${html}</p>
      ${memoFact ? `<p class="trace-step"><span class="step-n">2</span><span>The staff memo adds what the title leaves out:</span></p>${quoteHtml(memoFact.x.ctx)}` : ""}
      <p class="trace-step"><span class="step-n">3</span><span>Each fact is checked against the text, then stored with its quote. Dates are calculated in code.</span></p>
      <div class="records-wrap"><table class="records trace-table"><thead><tr><th>Fact</th><th>Value</th><th>From</th><th>Found by</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="trace-step"><span class="step-n">4</span><span>On the site this record is one row: ${esc(e.vendor)}, ${esc(money(e.amount))}, ${esc(ROUTE_SHORT[e.route] || "method not stated").toLowerCase()}, ends ${esc(fmtDate(e.end))}, ${heldSince(e)}.</span></p>
    </figure>`;
  }

  function howView() {
    const s = SITE.meta.stats || {};
    const contracts = CONTRACTS.length;
    const withEnd = CONTRACTS.filter((e) => e.end).length;
    const withRoute = CONTRACTS.filter((e) => e.route).length;
    const llm = SITE.evidence.filter((e) => e.method === "llm").length;
    const byBasis = (b) => CONTRACTS.filter((e) => e.endBasis === b);
    const n = (list, label, how) => agg(list.length.toLocaleString("en-US"), label, list, how);
    const svc = CONTRACTS.filter((e) => e.class === "term");
    const withOpts = svc.filter((e) => e.renewals && e.maxEnd);
    const svcOpts = svc.filter((e) => e.renewals);
    const notApproved = EVENTS.filter((e) => e.state === "not_approved");
    const undatedAmendments = s.amendment_terms_not_dated || 0;
    const H = (id) => { const x = HOW_SECTIONS.find((h) => h.id === id); return `<h2 id="${id}" class="anchor">${esc(x.title)}</h2>`; };
    const asOf = fmtDay((SITE.meta.crawled || SITE.meta.generated || SITE.meta.today).slice(0, 10));
    const noMethod = CONTRACTS.filter((e) => !e.route);
    const noMethodChanges = noMethod.filter((e) => e.class === "change" || e.kind === "renewal");

    return `<section class="how">
      <h2 class="how-title">How it works</h2>
      <p class="lead">Council records in, checked facts out. Every fact on the site is a sentence found word for word in a council record, or a calculation from such facts.</p>
      <nav class="toc" aria-label="On this page"><ol>${HOW_SECTIONS.map((h) => `<li><a href="#${h.id}" data-howsec="${h.id}">${esc(h.title)}</a></li>`).join("")}</ol></nav>

      ${H("how-data")}
      <ol class="flow">
        <li><b>${term("legistar", "Legistar")} API</b><span>${(s.matters || 0).toLocaleString()} council ${term("resolution", "resolutions")} since ${fmtDate(SITE.meta.since)}</span></li>
        <li><b>Fetch</b><span>${(s.texts || 0).toLocaleString()} ${term("memo", "staff memos")} for items that look like purchases; only changed items re-fetched</span></li>
        <li><b>Read</b><span>Patterns pull vendor, amount, method, term, dates, options, author</span></li>
        <li class="optional"><b>Fill gaps</b><span>Optional: Claude reads memos the patterns missed, quoting its source${llm ? ` (${llm} facts in this build)` : " (not used in this build)"}</span></li>
        <li><b>Check</b><span>A fact is kept only if its quote is in the record</span></li>
        <li><b>Calculate</b><span>End dates, totals and history, in code</span></li>
        <li><b>Publish</b><span>This site</span></li>
      </ol>
      <p class="small muted">Council records as of ${asOf}. Purchases over $75,000 need a council vote in ${esc(CITY)} (<a href="https://www2.a2gov.org/HRWebshare/Admin%20Policies/APP%20204%20Purchase%20of%20Goods%20and%20Services.pdf" target="_blank" rel="noopener">purchasing policy 204</a>); smaller ones never reach these records.</p>

      ${H("how-record")}
      ${recordTrace()}

      ${H("how-tabs")}
      <table class="plain"><thead><tr><th>Tab</th><th>Shows</th><th>Computed from</th></tr></thead><tbody>
        <tr><td><button type="button" class="ev" data-tab="sell">Where to sell</button></td><td>Contracts ending in the next 18 months (by ${esc(BY)}), upcoming votes, recent approvals, competitors' contracts, departments buying</td><td>Your company: market, competitors, smallest deal. Saved in the link and this browser</td></tr>
        <tr><td><button type="button" class="ev" data-tab="clock">Timeline</button></td><td>One bar per vendor and department, competitors marked</td><td>The same profile; contracts with a known end date, plus every competitor's</td></tr>
        <tr><td><button type="button" class="ev" data-tab="compete">Competition</button></td><td>How the city awards contracts: competed or not, by department and vendor</td><td>Every approved contract, citywide</td></tr>
        <tr><td><button type="button" class="ev" data-tab="research">Research</button></td><td>Any record, with filters, memo search and export</td><td>Every record, ignoring the profile</td></tr>
        <tr><td><button type="button" class="ev" data-tab="pursuit">For Pursuit</button></td><td>A guided tour</td><td>Each stop sets a tab and opens a source</td></tr>
      </tbody></table>

      ${H("how-provenance")}
      <dl class="prov">
        <div><dt><span class="ev" style="cursor:default">dotted</span></dt><dd>${term("quoted", "Quoted")}: the source sentence, highlighted in its record.</dd></div>
        <div><dt><span class="ev derived" style="cursor:default">dashed</span></dt><dd>${term("calculated", "Calculated")}: the arithmetic, or the list of records a total adds up.</dd></div>
        <div><dt><a href="#" onclick="return false" style="cursor:default">26-0713</a></dt><dd>Record number: previews the record; click opens Legistar.</dd></div>
        <div><dt><span class="term" style="cursor:default">grey</span></dt><dd>Glossary term: definition on hover; click for the entry below.</dd></div>
      </dl>
      <p class="small muted">Point at an underlined fact, total, record number or term to preview it; click it to keep the preview open. Underlined items inside a preview open their own previews.</p>

      ${H("how-classes")}
      <table class="plain counts-table"><tbody>
        <tr><td class="num">${n(svc, "Service contracts", "Contracts that run for a period and come up for renewal.")}</td><td>${term("service-contract", "Service contracts")}</td><td>Run for a period, then renewed, rebid or replaced. ${svc.filter((e) => e.end).length} have a known end date.</td></tr>
        <tr><td class="num">${n(CONTRACTS.filter((e) => e.class === "change"), "Amendments and change orders", "Changes to existing contracts.")}</td><td>${term("amendment", "Amendments")}</td><td>Change an existing contract. Merged into its bar on the timeline.</td></tr>
        <tr><td class="num">${n(CONTRACTS.filter((e) => e.class === "one_time"), "One-time purchases", "Equipment, supplies and construction projects.")}</td><td>${term("one-time", "One-time purchases")}</td><td>Equipment, supplies, construction. Nothing renews.</td></tr>
      </tbody></table>

      ${H("how-ends")}
      <p>First match wins. Each date shows which rule made it.</p>
      <table class="plain counts-table"><thead><tr><th class="num">Contracts</th><th>${term("end-basis", "Basis")}</th><th>Example</th></tr></thead><tbody>
        <tr><td class="num">${n(byBasis("stated"), "End dates stated in the memo", "Each is quoted from its memo.")}</td><td>Stated</td><td>"through June 30, 2027"</td></tr>
        <tr><td class="num">${n(byBasis("start+term"), "End dates from a stated start plus a stated term", "Start date + term, both quoted, minus one day.")}</td><td>Start + term</td><td>July 1, 2025 + 24 months = June 30, 2027</td></tr>
        <tr><td class="num">${n(byBasis("fiscal_years"), "End dates from the fiscal years an agreement covers", "June 30 of the last fiscal year the title or memo names.")}</td><td>${term("fiscal-year", "Fiscal year")}</td><td>"for FY 2027" = June 30, 2027</td></tr>
        <tr><td class="num">${n(byBasis("approval+term"), "End dates counted from the council vote", "Council vote + stated term. An assumption: work may start later.")}</td><td>${term("approval-term", "Vote + term")}</td><td>"a three-year agreement", counted from the vote. Labeled as an assumption; never used for amendments${undatedAmendments ? ` (${undatedAmendments} left undated)` : ""}</td></tr>
        <tr><td class="num">${n(byBasis("price_expiry"), "Supply orders dated by when their bid prices expire", "No contract end stated; the date the memo says bid prices are firm until.")}</td><td>${term("price-expiry", "Price expiry")}</td><td>Supply orders only: "prices firm through May 2027"</td></tr>
        <tr><td class="num">${(contracts - withEnd).toLocaleString()}</td><td>None</td><td>No readable term. Not on the timeline</td></tr>
      </tbody></table>
      <p class="small">Never read as an end date: "bid prices are firm through…" (for anything but supply orders), "the FY23-28 ${term("cip", "Capital Improvements Plan")}", "the original lease expired…" (any date before the vote), "a two (2)-year extension" (one extension, two years).</p>

      ${H("how-opening")}
      <p>${n(svcOpts, "Service contracts with renewal options", "Each memo states the options.")} service contracts have ${term("renewal-option", "renewal options")}, which the city usually exercises without a new council vote. For the ${n(withOpts, "Service contracts with renewal options and a known end date", "The last possible end assumes every option is used.")} whose end date is also known, "Options, then" shows the ${term("last-end", "last possible end")}: when the work is actually open to competitors. "Held" shows how long the ${term("incumbent")} has had the department's work.</p>

      ${H("how-states")}
      <ul class="tight">
        <li><b>Counted:</b> resolutions council approved.</li>
        <li><b>Shown separately:</b> ${PENDING.length ? n(PENDING, "On an upcoming agenda", "On an agenda without a vote yet.") : "0"} ${term("pending", "not yet voted on")}.</li>
        <li><b>Research only:</b> ${notApproved.length ? n(notApproved, "Resolutions that did not take effect", "Defeated, withdrawn or filed, per Legistar's status.") : "0"} defeated, withdrawn or filed.</li>
        <li><b>Left out:</b> ${s.intergovernmental_skipped || 0} ${term("intergovernmental", "agreements with other governments")}.</li>
      </ul>

      ${H("how-order")}
      <ul class="tight">
        <li><b>Default:</b> dollars of contracts in your market ending by ${esc(BY)}. Ties: total spend in your market. No weights, no blended score.</li>
        <li><b>Why ${term("department", "departments")}:</b> the requesting department scopes the work, writes the memo and pays.</li>
        <li><b>Why 18 months:</b> a city usually starts planning a replacement about a year before a contract ends, so 18 months gives a seller time to be known before the request for proposals is written. The window starts today, so its end date (${esc(BY)} right now) moves forward with the calendar.</li>
        <li><b>Other orders:</b> total spend, number of purchases, most recent purchase.</li>
      </ul>

      ${H("how-method")}
      <p>The title or memo usually says how the vendor was chosen. A bid or RFP number means ${term("competitive", "competitive")}; MiDEAL, Sourcewell or another public body's contract means ${term("cooperative", "cooperative")}; "sole source" means ${term("sole-source", "sole source")}. When neither says, the site shows <b>not stated</b> instead of guessing.</p>
      <p>${n(noMethod, "Contracts whose award method isn't stated", "Neither the title nor the memo says how the vendor was chosen.")} of ${contracts.toLocaleString()} approved contracts don't say. ${n(noMethodChanges, "Amendments, change orders and renewals with no stated method", "Their memo describes the change, not how the original contract was awarded.")} of them are amendments, change orders and renewals, whose memo describes the change rather than the original award. Most of the rest are agreements with service providers and consultants whose memo doesn't say how they were picked.</p>

      ${H("how-research")}
      <ul class="tight">
        <li><b>Filters</b> narrow by type, department, market, award method, vote and end date.</li>
        <li><b>Words</b> must all appear in the title, vendor, department, record number or memo. Title matches rank first.</li>
        <li><b>Example searches</b> load a search you can then adjust.</li>
        <li><b>"Open all in Research"</b> in any preview loads exactly the records behind that number.</li>
        <li><b>Download</b> any result set as a spreadsheet (CSV), with the quotes behind each vendor and end date.</li>
      </ul>

      ${H("how-limits")}
      <ul class="tight">
        <li>${esc(CITY)} only; council-approved purchases only (over $75,000).</li>
        <li>End dates known for ${svc.filter((e) => e.end).length} of ${svc.length} service contracts (${Math.round((100 * svc.filter((e) => e.end).length) / Math.max(1, svc.length))}%). Attached contract PDFs aren't read yet. Unknown means not found, not "never ends".</li>
        <li>Amounts are what council approved: often a ceiling or multi-year total, not what was paid.</li>
        <li>"Vote + term" assumes work starts at the vote; "Options, then" assumes every option is used.</li>
        <li>Markets are keyword rules.</li>
      </ul>

      ${H("glossary")}
      <dl class="glossary">${[...GLOSSARY].sort((a, b) => a.term.localeCompare(b.term)).map((g) => {
        const sec = HOW_SECTIONS.find((x) => x.id === g.sec);
        return `<div id="g-${g.id}" class="anchor"><dt>${esc(g.term)}</dt><dd>${esc(g.def)}${sec ? ` <a href="#${sec.id}" data-howsec="${sec.id}" class="more">${esc(sec.title)}</a>` : ""}</dd></div>`;
      }).join("")}</dl>

      ${H("how-numbers")}
      <table class="plain counts-table"><tbody>
        <tr><td class="num">${(s.matters || 0).toLocaleString()}</td><td>council resolutions read</td></tr>
        <tr><td class="num">${n(CONTRACTS, "Approved vendor contracts and purchase orders", "Every approved contract, purchase order, amendment and change order.")}</td><td>approved vendor contracts and purchase orders</td></tr>
        <tr><td class="num">${withRoute.toLocaleString()}</td><td>with a stated award method (${contracts ? Math.round((100 * withRoute) / contracts) : 0}%)</td></tr>
        <tr><td class="num">${withEnd.toLocaleString()}</td><td>with a known end date (all kinds)</td></tr>
        <tr><td class="num">${FUNDING.length.toLocaleString()}</td><td>funding actions (appropriations, grants, bonds)</td></tr>
        <tr><td class="num">${(s.quotes_verified || 0).toLocaleString()}</td><td>quoted facts, each found word for word</td></tr>
      </tbody></table>
      ${(SITE.quality || []).length ? `<h3>Problems found in the source data</h3><ul class="tight">${qualityLines(SITE.quality)}</ul>` : ""}
    </section>`;
  }

  function qualityLines(q) {
    const by = new Map();
    for (const r of q) { if (!by.has(r.issue)) by.set(r.issue, []); by.get(r.issue).push(r); }
    const say = {
      bad_date: (rs) => `${plural(rs.length, "record")} with an impossible date in Legistar (one says the year ${esc(String(rs[0].detail).slice(0, 4))}). We used the agenda date instead.`,
      end_before_approval: (rs) => `${plural(rs.length, "memo")} stated an end date earlier than the vote itself. That date belongs to the previous contract, so we ignored it rather than show a wrong clock.`,
      no_title: (rs) => `${plural(rs.length, "record")} had no title and were skipped.`,
      amendment_term_not_dated: (rs) => `${plural(rs.length, "amendment")} restated the original agreement's term without saying when it started. We left those undated rather than count the term from the amendment's vote.`,
    };
    return [...by].map(([k, rs]) => `<li>${(say[k] || ((x) => `${esc(k)}: ${x.length}`))(rs)}</li>`).join("");
  }

  // ------------------------------------------------------------------ the clock chart (SVG)

  function clockChart(list, oneDept = false) {
    // One row per relationship: a vendor's renewals and amendments with a department are one thread.
    // A watched competitor's thread is drawn even with no known end date, so adding a competitor
    // always shows where they are; its bar runs to today, marked "end not stated".
    const threads = new Map();
    for (const e of list) {
      const rival = isRival(e);
      if (!e.end && !rival) continue;
      const k = (e.vendorKey || "id" + e.id) + "|" + e.dept;
      const t = threads.get(k);
      const start = e.start || e.passed || e.introduced;
      if (!t) threads.set(k, { ...e, firstStart: start, records: 1 });
      else {
        t.records++;
        if (start < t.firstStart) t.firstStart = start;
        if ((e.end || "") > (t.end || "") || (!t.end && (e.passed || "") > (t.passed || ""))) Object.assign(t, { ...e, firstStart: t.firstStart, records: t.records });
      }
    }
    // Up to 40 rows, soonest end first. A watched competitor's rows are always kept, whenever they end.
    const all = [...threads.values()];
    const inRange = all.filter((e) => isRival(e) || (monthsFromToday(e.end) > -6 && monthsFromToday(e.end) < 48))
      .sort((a, b) => (a.end || "9999").localeCompare(b.end || "9999"));
    const keepIds = new Set([...inRange.filter(isRival), ...inRange.filter((e) => !isRival(e))].slice(0, 40).map((e) => e.id));
    const rows = inRange.filter((e) => keepIds.has(e.id));
    if (!rows.length) {
      return `<p class="empty">None of these ${plural(list.length, "contract")} has an end date we could source yet. Most Ann Arbor titles don't state a term; when the memo does, it's sometimes worded in a way the site can't read yet.</p>`;
    }
    const W = 880, L = 250, R = oneDept ? 20 : 130, rowH = 26, top = 34;
    const H = top + rows.length * rowH + 16;
    // The axis covers a year back to 3.5 years ahead, stretched to fit any competitor row outside that.
    const t0 = new Date(TODAY); t0.setMonth(t0.getMonth() - 12);
    const t1 = new Date(TODAY); t1.setMonth(t1.getMonth() + 42);
    for (const e of rows.filter(isRival)) {
      if (e.end && d(e.end) < t0) { t0.setTime(d(e.end).getTime()); t0.setMonth(t0.getMonth() - 6); }
      const last = e.maxEnd || e.end;
      if (last && d(last) > t1) { t1.setTime(d(last).getTime()); t1.setMonth(t1.getMonth() + 3); }
    }
    const x = (date) => L + ((date - t0) / (t1 - t0)) * (W - L - R);
    const clamp = (v) => Math.max(L, Math.min(W - R, v));
    const ticks = [];
    const years = t1.getFullYear() - t0.getFullYear(), every = years > 8 ? 2 : 1;
    for (let y = t0.getFullYear(); y <= t1.getFullYear() + 1; y++) { const dt = new Date(y, 0, 1); if (dt >= t0 && dt <= t1 && y % every === 0) ticks.push(dt); }
    const win1 = new Date(TODAY); win1.setMonth(win1.getMonth() + WINDOW_MONTHS);
    const svg = `<svg class="clock" viewBox="0 0 ${W} ${H}" role="group" aria-label="Timeline of ${rows.length} contracts by end date">
      <rect class="window" x="${x(TODAY)}" y="${top - 8}" width="${x(win1) - x(TODAY)}" height="${H - top}" />
      <g class="axis">${ticks.map((t) => `<line x1="${x(t)}" x2="${x(t)}" y1="${top - 8}" y2="${H - 8}"/><text x="${x(t) + 4}" y="${top - 14}">${t.getFullYear()}</text>`).join("")}</g>
      ${rows.map((e, i) => {
        const y = top + i * rowH;
        const noEnd = !e.end;
        const s = clamp(x(d(e.firstStart))), en = clamp(x(noEnd ? TODAY : d(e.end)));
        const opt = e.maxEnd ? clamp(x(d(e.maxEnd))) : null;
        const r = routeClass(e);
        const label = (e.vendor || "Vendor not stated") + (e.records > 1 ? ` (${e.records})` : "");
        const lab = label.length > 32 ? label.slice(0, 31) + "…" : label;
        const dept = e.dept.length > 18 ? e.dept.slice(0, 17) + "…" : e.dept;
        const rival = isRival(e);
        const src = e.fields.expires ? `data-ev="${e.fields.expires}"` : `data-file="${esc(e.file)}"`;
        return `<g class="row${rival ? " rival" : ""}" tabindex="0" role="button" ${src} data-vk="${esc(e.vendorKey || "")}" aria-label="${esc(label)}${rival ? " (competitor)" : ""}, ${esc(e.dept)}, ${noEnd ? "end date not stated" : "ends " + fmtDay(e.end)}. Show the evidence.">
          <rect class="hit" x="0" y="${y - 2}" width="${W}" height="${rowH - 2}" />
          ${rival ? `<rect class="rival-band" x="0" y="${y - 1}" width="${W}" height="${rowH - 4}" /><rect class="rival-edge" x="0" y="${y - 1}" width="4" height="${rowH - 4}" />` : ""}
          <text class="lab" x="${L - 10}" y="${y + 14}" text-anchor="end">${rival ? "◆ " : ""}${esc(lab)}</text>
          ${opt && opt > en ? `<line class="opt r-${r}" x1="${en}" x2="${opt}" y1="${y + 10}" y2="${y + 10}" />` : ""}
          <rect class="bar r-${r}${rival ? " rival" : ""}${noEnd ? " noend" : ""}" x="${s}" y="${y + 4}" width="${Math.max(3, en - s)}" height="12" />
          ${noEnd ? `<text class="noend-lab" x="${Math.min(en + 6, W - R - 90)}" y="${y + 14}">end not stated</text>` : ""}
          ${oneDept ? "" : `<text class="dept" x="${W - R + 8}" y="${y + 14}">${esc(dept)}</text>`}
        </g>`;
      }).join("")}
      <g class="today"><line x1="${x(TODAY)}" x2="${x(TODAY)}" y1="${top - 8}" y2="${H - 8}"/><text x="${x(TODAY) + 4}" y="${H - 1}">Today</text></g>
    </svg>`;
    const used = [...new Set(rows.map(routeClass))];
    const nRival = rows.filter(isRival).length;
    return `<div class="clock-wrap">${svg}</div>
      <div class="legend">${["competitive", "cooperative", "sole_source", "unknown"].filter((r) => used.includes(r)).map((r) => `<span><i class="r-${r}"></i>${ROUTE_SHORT[r]}</span>`).join("")}
        <span><i class="dash"></i>Renewal options</span><span><i class="win"></i>Next 18 months</span>${nRival ? '<span><b class="rival-dia">◆</b>Your competitors</span>' : ""}${rows.some((e) => !e.end) ? '<span><i class="noend"></i>End not stated: bar runs to today</span>' : ""}</div>
      <p class="small muted">${plural(rows.length, "vendor relationship")} shown${nRival ? `, ${nRival} of them your competitors' (shown whenever they end)` : ""}; a number in parentheses counts the council records in that thread (renewals, amendments).</p>`;
  }

  function clockFace() {
    // The "o" of Clock: hand points at today's place in the fiscal year (July = 12 o'clock).
    const fyMonth = (TODAY.getMonth() + 6) % 12;
    const a = ((fyMonth + TODAY.getDate() / 31) / 12) * 2 * Math.PI;
    const hx = 50 + 30 * Math.sin(a), hy = 50 - 30 * Math.cos(a);
    return `<svg class="tick" viewBox="0 0 100 100" role="img" aria-label="o"><circle cx="50" cy="50" r="42" fill="none" stroke="currentColor" stroke-width="7"/><line x1="50" y1="50" x2="${hx.toFixed(1)}" y2="${hy.toFixed(1)}" stroke="currentColor" stroke-width="7" stroke-linecap="round"/><circle cx="50" cy="50" r="5" fill="currentColor"/></svg>`;
  }

  // ------------------------------------------------------------------ provenance popovers
  //
  // Every fact, sum and record number on the page explains itself, in the manner of gwern.net's
  // popups: point at it and a preview opens after a short pause; move into the preview and it
  // stays; click to pin it. Links inside a preview open their own previews beside it, so a sum
  // leads to its records, a record to its facts, a fact to the sentence it was quoted from.
  // On touch screens there is no hover: a tap opens the popover pinned, as a sheet from the bottom.

  const HOVER = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const OPEN_DELAY = 280, CLOSE_DELAY = 320;
  const stack = []; // [{el, anchor, pinned, timer}]
  let openTimer = null;

  const FIELD = { vendor: "Vendor", amount: "Amount", route: "How it was awarded", kind: "Contract type", term_months: "Term", start_date: "Start date", end_date: "End date", renewals: "Renewal options", fy_range: "Funded years", expires: "Ends", prepared_by: "Memo prepared by", reviewed_by: "Memo reviewed by", prices_until: "Bid prices firm until", amount_basis: "Kind of amount", since_year: "Vendor's work for the city since", auto_renews: "Renews automatically" };

  function valueText(e) {
    const v = e.value;
    switch (e.field) {
      case "amount": return moneyExact(v);
      case "route": return ROUTE[v] || v;
      case "kind": return KIND[v] || v;
      case "term_months": return yrs(v);
      case "start_date": case "end_date": case "expires": case "prices_until": return fmtDay(v);
      case "renewals": return `${plural(v.count, "renewal")} of ${yrs(v.months_each)} each`;
      case "fy_range": return v.from === v.to ? `FY${v.from}` : `FY${v.from} to FY${v.to}`;
      case "prepared_by": case "reviewed_by": return `${v.name}, ${v.title}`;
      case "amount_basis": return AMOUNT_BASIS[v] || v;
      case "auto_renews": return v ? "yes, unless someone acts" : "no";
      default: return String(v);
    }
  }

  function quoteHtml(c) {
    if (!c) return "";
    let q = esc(c.quote);
    if (c.mark) {
      const [a, b] = c.mark;
      q = esc(c.quote.slice(0, a)) + "<u>" + esc(c.quote.slice(a, b)) + "</u>" + esc(c.quote.slice(b));
    }
    return `<blockquote><span class="ctx">${esc(c.before)}</span><mark>${q}</mark><span class="ctx">${esc(c.after)}</span></blockquote>`;
  }

  function openLinks(event) {
    return `<p class="open"><a href="${esc(event.url)}" target="_blank" rel="noopener">Open ${esc(event.file || "the record")} on Legistar</a>${event.attachments && event.attachments.length ? `, or the attached ${event.attachments.slice(0, 2).map((a) => `<a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.name || "file")}</a>`).join(" and ")}` : ""}</p>`;
  }

  function evidenceBody(id) {
    const e = EV.get(Number(id));
    if (!e) return null;
    const event = BY_ID.get(e.event);
    let body = `<p class="kicker">${recordLink(event)} · ${esc(event.dept)}${event.state !== "approved" ? ` · <span class="tag">${esc(STATE_LABEL[event.state])}</span>` : ""}</p>
      <p class="claim">${esc(FIELD[e.field] || e.field)}: <b>${esc(valueText(e))}</b></p>`;
    if (e.source === "derived") {
      const inputs = ["end_date", "start_date", "term_months", "fy_range", "prices_until"].map((f) => event.fields[f]).filter(Boolean).map((i) => EV.get(i));
      body += `<p class="where">Calculated, not quoted.</p><p class="derive">${esc(e.derivation)}</p>`;
      if (event.renewals && event.maxEnd) body += `<p class="how">Then ${ev(event, "renewals", `${plural(event.renewals.count, "renewal option")} of ${yrs(event.renewals.months_each)}`)} could run it to <b>${esc(fmtDay(event.maxEnd))}</b>. Options like these are usually approved by the City Administrator without a new council vote, so a competitor's real opening is after the last one.</p>`;
      body += inputs.map((i) => `<p class="how">${esc(FIELD[i.field])}: <b>${esc(valueText(i))}</b>, from the ${i.source === "title" ? "resolution title" : "staff memo"}:</p>${quoteHtml(i.ctx)}`).join("");
      if (e.rule === "approval+term") body += `<p class="how">Approved by council: <b>${esc(fmtDay(event.passed || event.introduced))}</b> (Legistar record).</p>`;
    } else {
      body += `<p class="where">From the ${e.source === "title" ? "resolution title" : "staff memo and resolution text"}:</p>${quoteHtml(e.ctx)}`;
      if (e.field === "amount" && event.fields.amount_basis) body += `<p class="how">This is ${esc(AMOUNT_BASIS[EV.get(event.fields.amount_basis).value] || "the amount in the title")}, judged from the words around it.</p>`;
      body += `<p class="how">${e.method === "llm" ? "Read by Claude, then checked: the highlighted words appear exactly in the source." : `Found by a pattern (${esc((FIELD_RULE[e.field] || "a text pattern").replace(/^(Title|Memo|Title or memo) (pattern|header): /, "").replace(/^./, (c) => c.toLowerCase()))}). The highlighted words appear exactly in the source${e.ctx && e.ctx.mark ? "; the underlined part is what the pattern matched" : ""}.`}</p>`;
    }
    return body + openLinks(event);
  }

  function recordBody(file) {
    const e = BY_FILE.get(file);
    if (!e) return null;
    const facts = [];
    if (e.vendor) facts.push(`Vendor: ${ev(e, "vendor", e.vendor)}`);
    if (e.amount != null) facts.push(`Amount: ${ev(e, "amount", moneyExact(e.amount))}${e.amountBasis && e.amountBasis !== "stated" ? ` (${esc(AMOUNT_BASIS[e.amountBasis])})` : ""}`);
    if (e.type === "contract") facts.push(`How awarded: ${e.route ? ev(e, "route", ROUTE[e.route]) : "not stated"}`);
    if (e.type === "contract") facts.push(`Ends: ${e.end ? ev(e, "expires", fmtDay(e.end)) + (e.renewals ? `, options to ${ev(e, "renewals", fmtDay(e.maxEnd))}` : "") : e.class === "one_time" ? "one-time purchase, nothing renews" : "not stated"}`);
    if (e.staff && e.staff.length) facts.push(`Memo: ${staffLine(e)}`);
    return `<p class="kicker">${esc(e.file)} · ${esc(e.dept)} · ${esc(fmtDay(e.passed || e.agenda || e.introduced))}${e.state !== "approved" ? ` · <span class="tag">${esc(STATE_LABEL[e.state])}</span>` : ""}</p>
      <p class="where">${esc(e.title)}</p>
      <ul class="rec-facts">${facts.map((f) => `<li>${f}</li>`).join("")}</ul>${openLinks(e)}`;
  }

  function aggBody(id) {
    const a = AGG.get(id);
    if (!a) return null;
    const byTime = a.order === "time";
    const rows = byTime ? [...a.list] : [...a.list].sort((x, y) => (y.amount || 0) - (x.amount || 0));
    const shown = rows.slice(0, 12);
    return `<p class="claim">${esc(a.label)}</p><p class="derive">${esc(a.how)}</p>
      <table class="mini"><tbody>${shown.map((e) => `<tr><td class="nw">${recordLink(e)}${byTime ? `<br><span class="muted">${esc(fmtDate(e.passed || e.introduced))}</span>` : ""}</td><td>${e.vendor ? ev(e, "vendor", e.vendor) : `<span class="muted">${e.type === "funding" ? "funding" : "vendor not stated"}</span>`}</td><td class="num">${e.amount != null ? ev(e, "amount", money(e.amount)) : '<span class="muted">none</span>'}</td><td class="nw">${e.end && hasClock(e) ? ev(e, "expires", fmtDate(e.end)) : ""}</td></tr>`).join("")}</tbody></table>
      ${rows.length > shown.length ? `<p class="how">and ${plural(rows.length - shown.length, "more record")}.</p>` : ""}
      <p class="open"><button type="button" class="ev" data-openset="${id}">Open ${rows.length === 1 ? "this record" : `all ${rows.length}`} in Research</button></p>`;
  }

  function termBody(id) {
    const g = GLOSS.get(id);
    if (!g) return null;
    const sec = HOW_SECTIONS.find((x) => x.id === g.sec);
    return `<p class="kicker">Glossary</p><p class="claim">${esc(g.term)}</p><p>${esc(g.def)}</p>
      <p class="open"><a href="#g-${id}" data-glossary="${id}">Open in the glossary</a>${sec ? ` · <a href="#${sec.id}" data-howsec="${sec.id}">How it works: ${esc(sec.title.toLowerCase())}</a>` : ""}</p>`;
  }

  function bodyFor(anchor) {
    if (anchor.dataset.term) return termBody(anchor.dataset.term);
    if (anchor.dataset.ev) return evidenceBody(anchor.dataset.ev);
    if (anchor.dataset.agg) return aggBody(anchor.dataset.agg);
    if (anchor.dataset.file) return recordBody(anchor.dataset.file);
    return null;
  }

  function levelOf(anchor) {
    const host = anchor.closest(".pop");
    return host ? stack.findIndex((p) => p.el === host) + 1 : 0;
  }

  function closeFrom(level) {
    while (stack.length > level) {
      const p = stack.pop();
      clearTimeout(p.timer);
      p.el.remove();
      if (p.anchor && document.contains(p.anchor)) p.anchor.setAttribute("aria-expanded", "false");
    }
  }
  function closePop() { closeFrom(0); }

  function openPop(anchor, pinned) {
    const html = bodyFor(anchor);
    if (!html) return;
    const level = levelOf(anchor);
    const existing = stack[level];
    if (pinned) pinUpTo(level - 1); // keeping a nested preview keeps the ones it came from
    if (existing && existing.anchor === anchor) {
      if (pinned) { pinUpTo(level); existing.el.querySelector(".close")?.focus({ preventScroll: true }); }
      return;
    }
    closeFrom(level);
    const el = document.createElement("div");
    el.className = "pop" + (pinned ? " pinned" : "") + (level ? " nested" : "");
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", "Source");
    el.innerHTML = `<button type="button" class="close" aria-label="Close">×</button>${html}${HOVER && !pinned ? `<p class="hint">${anchor.dataset.term ? "Click the term to open the glossary." : anchor.tagName === "A" ? "Click the record number to open it on Legistar." : "Click the underlined item to keep this open."}</p>` : ""}`;
    document.body.appendChild(el);
    const p = { el, anchor, pinned, timer: null };
    stack.push(p);
    anchor.setAttribute("aria-expanded", "true");
    place(el, anchor, level);
    el.querySelector(".close").addEventListener("click", () => closeFrom(level));
    el.addEventListener("mouseenter", () => keep(level));
    el.addEventListener("mouseleave", () => scheduleClose(level));
    if (pinned) el.querySelector(".close").focus({ preventScroll: true });
  }

  function pinUpTo(level) {
    for (let i = 0; i <= level && i < stack.length; i++) {
      const p = stack[i];
      clearTimeout(p.timer);
      if (!p.pinned) { p.pinned = true; p.el.classList.add("pinned"); p.el.querySelector(".hint")?.remove(); }
    }
  }
  function keep(level) {
    for (let i = 0; i <= level && i < stack.length; i++) clearTimeout(stack[i].timer);
  }
  function scheduleClose(level) {
    const p = stack[level];
    if (!p || p.pinned) return;
    clearTimeout(p.timer);
    p.timer = setTimeout(() => { if (stack[level] === p && !p.el.matches(":hover")) closeFrom(level); }, CLOSE_DELAY);
  }

  function place(el, anchor, level) {
    if (window.matchMedia("(max-width: 640px)").matches) return; // a bottom sheet, from CSS
    const r = anchor.getBoundingClientRect();
    const pw = el.offsetWidth, ph = el.offsetHeight;
    let left = Math.min(Math.max(16, r.left), window.innerWidth - pw - 16);
    let top = r.bottom + 8;
    if (level) { // beside its parent when there is room, so both stay readable
      const parent = stack[level - 1].el.getBoundingClientRect();
      if (parent.right + 12 + pw < window.innerWidth - 8) { left = parent.right + 12; top = Math.max(16, r.top - 24); }
      else if (parent.left - 12 - pw > 8) { left = parent.left - 12 - pw; top = Math.max(16, r.top - 24); }
    }
    if (top + ph > window.innerHeight - 16) top = Math.max(16, (level ? window.innerHeight - ph - 16 : r.top - ph - 8));
    el.style.left = left + "px";
    el.style.top = top + "px";
  }

  const ANCHOR = "[data-ev],[data-agg],[data-file],[data-term]";
  if (HOVER) {
    document.addEventListener("mouseover", (evt) => {
      const a = evt.target.closest(ANCHOR);
      if (!a || (a.dataset.ev === "")) return;
      const level = levelOf(a);
      keep(level - 1);
      clearTimeout(openTimer);
      openTimer = setTimeout(() => openPop(a, false), OPEN_DELAY);
    });
    document.addEventListener("mouseout", (evt) => {
      const a = evt.target.closest(ANCHOR);
      if (!a || a.contains(evt.relatedTarget)) return;
      clearTimeout(openTimer);
      const level = levelOf(a);
      if (stack[level] && stack[level].anchor === a) scheduleClose(level);
    });
  }

  // ------------------------------------------------------------------ competitor picker
  // A scrollable list of every vendor council has approved a contract with, filtered as you type.
  // Vendors in the viewer's market come first. (A native <datalist> can't be scrolled in every browser.)

  function vendorOptions(q) {
    const keys = new Set(parseCompetitors(state.competitors));
    const inMkt = new Set(CONTRACTS.filter((e) => e.cats.includes(state.cat) && e.vendorKey).map((e) => e.vendorKey));
    const t = normKey(q || "");
    const hits = VENDORS.filter((v) => !keys.has(v.key) && (!t || v.key.includes(t) || v.name.toLowerCase().includes(t)));
    return { mine: hits.filter((v) => inMkt.has(v.key)), rest: hits.filter((v) => !inMkt.has(v.key)) };
  }

  function wireVendorPicker(vs) {
    const list = document.getElementById("vs-list");
    const toggle = document.getElementById("vs-toggle");
    let active = -1;
    const items = () => [...list.querySelectorAll("[role=option]")];
    const fill = () => {
      const { mine, rest } = vendorOptions(vs.value);
      const opt = (v) => `<div role="option" id="vs-o-${esc(v.key).replace(/\W+/g, "-")}" class="combo-opt" data-pick="${esc(v.name)}"><span>${esc(v.name)}</span><span class="muted">${plural(v.n, "contract")}, ${esc(money(v.total))}</span></div>`;
      list.innerHTML = (mine.length ? `<p class="combo-h">In ${esc(CATS[state.cat])}</p>${mine.map(opt).join("")}` : "")
        + (rest.length ? `<p class="combo-h">${mine.length ? "Other vendors" : "All vendors"}</p>${rest.map(opt).join("")}` : "")
        + (!mine.length && !rest.length ? `<p class="combo-h">No vendor matches. Press Enter to watch "${esc(vs.value)}" anyway.</p>` : "");
      active = -1;
    };
    const open = () => { fill(); list.hidden = false; vs.setAttribute("aria-expanded", "true"); };
    const close = () => { list.hidden = true; vs.setAttribute("aria-expanded", "false"); vs.removeAttribute("aria-activedescendant"); };
    const setActive = (i) => {
      const its = items();
      if (!its.length) return;
      active = (i + its.length) % its.length;
      its.forEach((el, k) => el.classList.toggle("on", k === active));
      its[active].scrollIntoView({ block: "nearest" });
      vs.setAttribute("aria-activedescendant", its[active].id);
    };
    const add = (name) => {
      const val = (name || "").trim();
      if (!val) return;
      const hit = VENDORS.find((v) => v.name.toLowerCase() === val.toLowerCase());
      const key = hit ? hit.key : normKey(val);
      const keys = parseCompetitors(state.competitors);
      if (key.length >= 3 && !keys.includes(key)) keys.push(key);
      state.competitors = keys.join(",");
      writeHash(); render();
      document.getElementById("vs").focus();
    };
    vs.addEventListener("focus", open);
    vs.addEventListener("input", open);
    vs.addEventListener("blur", () => setTimeout(close, 150));
    vs.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); if (list.hidden) open(); setActive(active + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); if (list.hidden) open(); setActive(active - 1); }
      else if (e.key === "Enter") { e.preventDefault(); const its = items(); add(active >= 0 && its[active] ? its[active].dataset.pick : vs.value); }
      else if (e.key === "Escape") { if (!list.hidden) { e.stopPropagation(); close(); } }
    });
    // mousedown, not click: picking must happen before the input's blur closes the list.
    list.addEventListener("mousedown", (e) => { const o = e.target.closest("[data-pick]"); e.preventDefault(); if (o) add(o.dataset.pick); });
    toggle.addEventListener("mousedown", (e) => { e.preventDefault(); if (list.hidden) { vs.focus(); open(); } else close(); });
    vs.parentElement.addEventListener("mousedown", (e) => { if (e.target === vs.parentElement) { e.preventDefault(); vs.focus(); } });
  }

  // ------------------------------------------------------------------ events

  function wire() {
    const catEl = document.getElementById("cat");
    if (catEl) catEl.addEventListener("change", () => { go({ cat: catEl.value }); document.getElementById("cat").focus(); });
    const minEl = document.getElementById("min");
    if (minEl) minEl.addEventListener("change", () => { state.min = Number(minEl.value) || 0; writeHash(); render(); document.getElementById("min").focus(); });
    const vs = document.getElementById("vs");
    if (vs) wireVendorPicker(vs);
    const sort = document.getElementById("sort");
    if (sort) sort.addEventListener("change", () => { state.sort = sort.value; render(); document.getElementById("sort").focus(); });
    const csv = document.getElementById("csv");
    if (csv) csv.addEventListener("click", () => saveCsv(`incumbent-clock-${state.cat}-departments.csv`, departmentRows()));
    const csvR = document.getElementById("csv-records");
    if (csvR) csvR.addEventListener("click", () => saveCsv(`incumbent-clock-records.csv`, recordRows(filtered().map((r) => r.e))));
    const clearSet = document.getElementById("clear-set");
    if (clearSet) clearSet.addEventListener("click", () => go({ set: null }));

    // Research filters re-render the results in place, keeping focus where the person is typing.
    const form = document.getElementById("search");
    if (form) {
      let t;
      form.addEventListener("input", (evt) => {
        const id = evt.target.id;
        clearTimeout(t);
        t = setTimeout(() => {
          state[id] = evt.target.value;
          state.limit = 40;
          state.quick = null;
          const pos = evt.target.selectionStart;
          render();
          const el = document.getElementById(id);
          el.focus();
          if (id === "q" && pos != null) el.setSelectionRange(pos, pos);
        }, id === "q" ? 250 : 0);
      });
    }
    const more = document.getElementById("more");
    if (more) more.addEventListener("click", () => { const y = window.scrollY; state.limit += 40; render(); window.scrollTo({ top: y }); });
  }

  /** Go to a place on How it works (a section or a glossary entry) and mark it briefly. */
  function goHow(anchorId) {
    state.tab = "how"; state.dept = null; state.set = null;
    writeHash(); render();
    const el = document.getElementById(anchorId);
    if (!el) { window.scrollTo({ top: 0 }); return; }
    el.scrollIntoView({ block: "start" });
    el.classList.add("flash");
    setTimeout(() => el.classList.remove("flash"), 1800);
  }

  document.addEventListener("click", (evt) => {
    const t = evt.target.closest("[data-term],[data-glossary],[data-howsec]");
    if (t) {
      evt.preventDefault();
      clearTimeout(openTimer);
      goHow(t.dataset.howsec || "g-" + (t.dataset.term || t.dataset.glossary));
      return;
    }
    const tour = evt.target.closest("[data-tour]");
    if (tour) { evt.preventDefault(); runTour(Number(tour.dataset.tour)); return; }
    const quick = evt.target.closest("[data-quick]");
    if (quick) { evt.preventDefault(); applyQuick(Number(quick.dataset.quick)); return; }
    const tab = evt.target.closest("[data-tab]");
    if (tab) { go({ tab: tab.dataset.tab, dept: null, set: null }); return; }
    const goto = evt.target.closest("[data-goto]");
    if (goto) { evt.preventDefault(); go({ tab: goto.dataset.goto, dept: null }); return; }
    const openset = evt.target.closest("[data-openset]");
    if (openset) {
      const a = AGG.get(openset.dataset.openset);
      if (a) go({ tab: "research", dept: null, set: { label: a.label, ids: a.list.map((e) => e.id) }, limit: 40 });
      return;
    }
    const nav = evt.target.closest("a[data-dept]");
    if (nav) { evt.preventDefault(); go({ dept: nav.dataset.dept || null }); return; }
    const rivalGo = evt.target.closest("[data-rivalgo]");
    if (rivalGo) {
      const k = rivalGo.dataset.rivalgo;
      go({ tab: "clock", dept: null, set: null });
      const row = [...document.querySelectorAll("#clock-h ~ .clock-wrap g.row.rival")].find((g) => (g.dataset.vk || "").includes(k));
      if (row) { row.scrollIntoView({ block: "center" }); row.classList.add("flash"); setTimeout(() => row.classList.remove("flash"), 1800); }
      else { const m = document.getElementById("rival-missing"); if (m) { m.scrollIntoView({ block: "center" }); m.classList.add("flash"); setTimeout(() => m.classList.remove("flash"), 1800); } }
      return;
    }
    const unrival = evt.target.closest("[data-unrival]");
    if (unrival) { state.competitors = parseCompetitors(state.competitors).filter((k) => k !== unrival.dataset.unrival).join(","); writeHash(); render(); return; }
    const preset = evt.target.closest("[data-preset]");
    if (preset) { go({ cat: preset.dataset.preset }); return; }
    // A record number that is a real link goes to Legistar; hovering it previews the record.
    const a = evt.target.closest(ANCHOR);
    if (a && !(a.tagName === "A" && a.href)) {
      if (a.dataset.ev === "") return;
      evt.preventDefault();
      clearTimeout(openTimer);
      openPop(a, true);
      return;
    }
    if (stack.length && !evt.target.closest(".pop")) closePop();
  });
  document.addEventListener("keydown", (evt) => {
    if (evt.key === "Escape" && stack.length) { closeFrom(stack.length - 1); return; }
    if ((evt.key === "Enter" || evt.key === " ") && evt.target.matches("g.row[data-ev]")) { evt.preventDefault(); openPop(evt.target, true); }
    if (evt.target.matches('[role="tab"]') && (evt.key === "ArrowRight" || evt.key === "ArrowLeft")) {
      const i = TABS.findIndex((t) => t.id === evt.target.dataset.tab);
      const next = TABS[(i + (evt.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
      go({ tab: next.id, dept: null });
      document.getElementById("tab-" + next.id).focus();
    }
  });
  window.addEventListener("resize", () => stack.forEach((p, i) => place(p.el, p.anchor, i)));
  window.addEventListener("hashchange", () => { readHash(); render(); });

  // ------------------------------------------------------------------ CSV export
  // Files for a CRM import or a spreadsheet. On the hosted demo the viewer's browser can't download
  // on its own, so the save goes through the artifact's downloads capability; elsewhere, a normal link.

  let downloadsFn = null;
  // Served or opened from disk, a plain download link works. Inside the hosted artifact only the
  // downloads capability can save, so the buttons appear once it answers.
  function canSave() { return !window.EMBEDDED || !!downloadsFn; }
  if (window.claude && typeof window.claude.use === "function") {
    window.claude.use("downloads").then((d) => {
      downloadsFn = d;
      if (d && window.EMBEDDED && !stack.length && (state.tab === "research" || state.tab === "sell")) render();
    }).catch(() => {});
  }

  function toCsv(rows) {
    return rows.map((r) => r.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  }
  function quoteOf(e, f) { const i = e.fields && e.fields[f]; const x = i && EV.get(i); return x && x.ctx ? x.ctx.quote : ""; }

  function departmentRows() {
    const competitors = parseCompetitors(state.competitors);
    const accts = sortAccounts(accounts(state.cat, competitors), state.sort);
    const rows = [["department", "ending_18mo_value", "ending_18mo_count", "total_in_market", "purchases", "not_competed", "with_stated_method", "next_end", "next_incumbent", "next_record", "memo_author", "memo_author_title"]];
    for (const a of accts) {
      const e = a.ending[0];
      rows.push([a.dept, a.renewalValue, a.ending.length, a.total, a.contracts.length, a.noBid, a.known, e?.end || "", e?.vendor || "", e?.url || "", a.staff[0]?.name || "", a.staff[0]?.title || ""]);
    }
    return rows;
  }

  function recordRows(list) {
    const rows = [["record", "council_vote", "approved", "department", "vendor", "amount", "amount_kind", "award_method", "contract_kind", "end_date", "end_basis", "renewal_options", "end_if_all_options_used", "memo_author", "legistar_url", "title", "vendor_quote", "end_quote"]];
    for (const e of list) {
      rows.push([e.file, STATE_LABEL[e.state], e.passed || "", e.dept, e.vendor || "", e.amount ?? "", e.amountBasis || "", e.route || "", e.class || e.type, e.end || "", e.endBasis || "",
        e.renewals ? optsShort(e.renewals) : "", e.maxEnd || "", (e.staff || [])[0]?.name || "", e.url, e.title, quoteOf(e, "vendor"), quoteOf(e, "end_date") || quoteOf(e, "term_months") || quoteOf(e, "fy_range")]);
    }
    return rows;
  }

  async function saveCsv(filename, rows) {
    const data = toCsv(rows);
    if (downloadsFn) {
      try { await downloadsFn.save({ filename, data }); }
      catch (e) { if (e && (e.code === "unavailable" || e.code === "not_granted" || e.code === "capability_disabled")) { downloadsFn = null; render(); } }
      return;
    }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([data], { type: "text/csv" }));
    a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
  }

  readHash();
  render();
})();
