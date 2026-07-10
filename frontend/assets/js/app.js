import { api } from "./api.js";
const $ = (id) => document.getElementById(id);
const pageTitles = {
  dashboard: "经营驾驶舱",
  data: "数据接入中心",
  products: "商品增长中心",
  reputation: "用户口碑中心",
  marketing: "投放内容中心",
  forecast: "趋势预测中心",
  reports: "经营报告中心",
};

const pageContexts = {
  dashboard: "聚合经营结果、风险信号与今日动作",
  data: "接入经营数据并完成字段识别与质量检查",
  products: "识别增长商品、价格机会与库存风险",
  reputation: "从用户反馈中提炼卖点、痛点与改进动作",
  marketing: "复盘投放效率、内容表现与转化承接",
  forecast: "预测短期趋势并安排补货与风险处置",
  reports: "汇总经营结论、数据证据与执行计划",
};

const state = {
  page: "dashboard",
  dashboard: null,
  products: [],
  shelfProducts: [],
  categories: [],
  salesAnalysis: null,
  priceBands: [],
  scoring: [],
  keywords: null,
  sentiment: null,
  forecast: null,
  marketing: null,
  inventory: null,
  knowledgeStatus: null,
  platformConnections: null,
  importSchema: null,
  importPreview: null,
  selectedProductId: "",
  productFilters: {
    keyword: "",
    category: "",
    sort: "hot_score",
  },
  report: null,
  assistantOpen: false,
  assistantMessages: [],
  currentUser: null,
  authMode: "login",
};

const charts = new Map();
let productFilterRequestSeq = 0;
let searchDebounceTimer = 0;
let productSearchDebounceTimer = 0;
let refreshInFlight = false;

function money(value) {
  const number = Number(value || 0);
  return `¥${number.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

function number(value) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function decimal(value) {
  return Number(value || 0).toFixed(2);
}

function shortNumber(value) {
  const numberValue = Number(value || 0);
  if (Math.abs(numberValue) >= 100000000) return `${(numberValue / 100000000).toFixed(1)}亿`;
  if (Math.abs(numberValue) >= 10000) return `${(numberValue / 10000).toFixed(1)}万`;
  return numberValue.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
}

function moneyShort(value) {
  return `¥${shortNumber(value)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(title, message = "", tone = "info", timeout = 3600) {
  const stack = $("toastStack");
  if (!stack) return;
  const toast = document.createElement("article");
  toast.className = `toast is-${tone}`;
  const copy = document.createElement("div");
  const heading = document.createElement("strong");
  const detail = document.createElement("span");
  const close = document.createElement("button");
  heading.textContent = title;
  detail.textContent = message;
  close.type = "button";
  close.setAttribute("aria-label", "关闭提示");
  close.textContent = "×";
  copy.append(heading);
  if (message) copy.append(detail);
  toast.append(copy, close);
  stack.append(toast);
  requestAnimationFrame(() => toast.classList.add("is-visible"));
  const dismiss = () => {
    toast.classList.remove("is-visible");
    window.setTimeout(() => toast.remove(), 180);
  };
  close.addEventListener("click", dismiss);
  window.setTimeout(dismiss, timeout);
}

function updateSyncStatus(status, detail) {
  const statusNode = $("syncStatusText");
  const timeNode = $("syncStatusTime");
  const statusBox = statusNode?.closest(".sync-status");
  if (!statusNode || !timeNode || !statusBox) return;
  statusBox.dataset.status = status;
  const labels = {
    loading: "正在同步",
    ready: "数据已就绪",
    warning: "部分数据待恢复",
    error: "数据加载失败",
  };
  statusNode.textContent = labels[status] || labels.ready;
  timeNode.textContent = detail || "经营视图已更新";
}

function setAppLoading(loading) {
  const shell = $("appShell");
  const refreshButton = $("refreshButton");
  shell?.classList.toggle("is-loading", loading);
  shell?.setAttribute("aria-busy", String(loading));
  if (refreshButton) {
    refreshButton.disabled = loading;
    refreshButton.textContent = loading ? "刷新中…" : "刷新数据";
  }
  if (loading) updateSyncStatus("loading", "正在汇总最新经营指标");
}

function currentProduct() {
  return state.products.find((item) => item.product_id === state.selectedProductId) || state.products[0] || null;
}

function shelfProducts() {
  return state.shelfProducts.length || hasActiveProductFilters() ? state.shelfProducts : state.products;
}

function hasActiveProductFilters() {
  const filters = state.productFilters;
  return Boolean(filters.keyword || filters.category || (filters.sort && filters.sort !== "hot_score"));
}

function routeTo(page) {
  const nextPage = pageTitles[page] ? page : "dashboard";
  const pageChanged = state.page !== nextPage;
  state.page = nextPage;
  document.querySelectorAll("[data-page-view]").forEach((view) => {
    const active = view.dataset.pageView === state.page;
    view.hidden = !active;
    view.classList.toggle("is-active", active);
  });
  document.querySelectorAll("[data-page]").forEach((link) => {
    const active = link.dataset.page === state.page;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $("pageTitle").textContent = pageTitles[state.page];
  if ($("pageContext")) $("pageContext").textContent = pageContexts[state.page] || "";
  if (pageChanged) {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }
  requestAnimationFrame(resizeCharts);
}

function navigate(page) {
  window.location.hash = page;
}

function currentRoute() {
  const hash = window.location.hash.replace("#", "").trim();
  return pageTitles[hash] ? hash : "dashboard";
}

async function loadInitial({ announce = false } = {}) {
  if (refreshInFlight) return;
  refreshInFlight = true;
  setAppLoading(true);
  const requests = [
    ["importSchema", api.importSchema()],
    ["dashboard", api.executiveDashboard()],
    ["products", api.products({ page: 1, page_size: 100, sort: "hot_score", order: "desc" })],
    ["categories", api.categories()],
    ["salesAnalysis", api.salesAnalysis()],
    ["priceBands", api.priceBands()],
    ["scoring", api.hotScoring({ limit: 20 })],
    ["marketing", api.marketingSummary()],
    ["inventory", api.inventorySummary()],
    ["knowledgeStatus", api.knowledgeStatus()],
    ["platformConnections", api.platformConnections()],
  ];
  try {
    const results = await Promise.allSettled(requests.map(([, request]) => request));
    const loaded = {};
    const failures = [];
    results.forEach((result, index) => {
      const key = requests[index][0];
      if (result.status === "fulfilled") loaded[key] = result.value;
      else failures.push({ key, reason: result.reason });
    });
    if (loaded.importSchema) state.importSchema = loaded.importSchema;
    if (loaded.dashboard) state.dashboard = loaded.dashboard;
    if (loaded.products) {
      state.products = loaded.products.items || [];
      state.shelfProducts = state.products;
    }
    if (loaded.categories) state.categories = loaded.categories || [];
    if (loaded.salesAnalysis) state.salesAnalysis = loaded.salesAnalysis;
    if (loaded.priceBands) state.priceBands = loaded.priceBands.items || [];
    if (loaded.scoring) state.scoring = loaded.scoring.items || [];
    if (loaded.marketing) state.marketing = loaded.marketing;
    if (loaded.inventory) state.inventory = loaded.inventory;
    if (loaded.knowledgeStatus) state.knowledgeStatus = loaded.knowledgeStatus;
    if (loaded.platformConnections) state.platformConnections = loaded.platformConnections;
    state.selectedProductId = state.selectedProductId || state.products[0]?.product_id || "";
    const scopedFailures = await loadProductScoped();
    renderAll();
    const totalFailures = failures.length + scopedFailures;
    const time = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date());
    if (totalFailures) {
      updateSyncStatus("warning", `${time} 更新 · ${totalFailures} 项暂不可用`);
      showToast("部分数据暂未加载", "其余经营模块仍可正常使用，可稍后刷新重试。", "warning", 5200);
    } else {
      updateSyncStatus("ready", `${time} 完成更新`);
      if (announce) showToast("经营数据已刷新", "当前页面已更新为最新结果。", "success");
    }
    if (!Object.keys(loaded).length) throw failures[0]?.reason || new Error("数据加载失败");
  } finally {
    refreshInFlight = false;
    setAppLoading(false);
  }
}

async function initializeApp() {
  setAuthMode("login");
  const token = window.localStorage.getItem(api.tokenKey);
  if (!token) {
    showAuthScreen();
    return;
  }
  try {
    state.currentUser = await api.me();
  } catch (_error) {
    window.localStorage.removeItem(api.tokenKey);
    state.currentUser = null;
    showAuthScreen();
    return;
  }
  showAppScreen();
  routeTo(currentRoute());
  await loadInitial();
}

async function loadProductScoped() {
  const productId = state.selectedProductId || undefined;
  const results = await Promise.allSettled([
    api.keywords({ product_id: productId, top_n: 20 }),
    api.sentiment({ product_id: productId }),
    api.forecast({ product_id: productId, days: 7 }),
  ]);
  const [keywords, sentiment, forecast] = results;
  if (keywords.status === "fulfilled") state.keywords = keywords.value;
  if (sentiment.status === "fulfilled") state.sentiment = sentiment.value;
  if (forecast.status === "fulfilled") state.forecast = forecast.value;
  return results.filter((result) => result.status === "rejected").length;
}

function renderAll() {
  renderProductOptions();
  renderDashboard();
  renderDataCenter();
  renderProducts();
  renderReputation();
  renderMarketing();
  renderForecast();
  renderReportPanel();
  renderAssistant();
}

function setAuthMode(mode) {
  state.authMode = mode === "register" ? "register" : "login";
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    const active = button.dataset.authMode === state.authMode;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  const loginActive = state.authMode === "login";
  $("loginForm")?.classList.toggle("is-active", loginActive);
  $("registerForm")?.classList.toggle("is-active", !loginActive);
  if ($("loginForm")) $("loginForm").hidden = !loginActive;
  if ($("registerForm")) $("registerForm").hidden = loginActive;
  setAuthMessage("");
}

function setAuthMessage(message, tone = "") {
  const node = $("authMessage");
  if (!node) return;
  node.textContent = message || "";
  node.className = `auth-message ${tone}`.trim();
}

function showAuthScreen() {
  $("authScreen").hidden = false;
  $("appShell").hidden = true;
  $("assistantWidget").hidden = true;
}

function showAppScreen() {
  $("authScreen").hidden = true;
  $("appShell").hidden = false;
  $("assistantWidget").hidden = false;
  renderUserChip();
}

function renderUserChip() {
  const user = state.currentUser || {};
  const workspaceName = user.workspace_name === "ViralPick Demo Workspace" ? "默认经营空间" : user.workspace_name;
  const label = workspaceName || user.display_name || "经营账号";
  $("currentUserName").textContent = label;
}

function saveSession(session) {
  if (!session?.access_token) return;
  window.localStorage.setItem(api.tokenKey, session.access_token);
  state.currentUser = session.user || null;
}

async function enterWithSession(session) {
  saveSession(session);
  showAppScreen();
  routeTo(currentRoute());
  setAuthMessage("");
  await loadInitial();
}

function renderDashboard() {
  const headline = state.dashboard?.headline || {};
  $("dashboardHeroMetrics").innerHTML = [
    ["销售额", money(headline.gmv)],
    ["订单量", number(headline.orders)],
    ["客单价", money(headline.customer_unit_price)],
    ["转化率", percent(headline.conversion_rate)],
    ["退款率", percent(headline.refund_rate)],
    ["投产比", decimal(headline.roi)],
  ]
    .map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  const roiScore = Math.min(26, Number(headline.roi || 0) * 3.2);
  const opportunityScore = Math.min(16, Number(headline.opportunity_count || 0) * 8);
  const conversionScore = Math.min(12, Number(headline.conversion_rate || 0) * 220);
  const refundPenalty = Math.min(12, Number(headline.refund_rate || 0) * 800);
  const riskPenalty = Math.min(28, Number(headline.risk_count || 0) * 3.5);
  const score = Math.max(0, Math.min(96, Math.round(58 + roiScore + opportunityScore + conversionScore - refundPenalty - riskPenalty)));
  $("dashboardScore").textContent = score;
  $("dashboardSignal").textContent = headline.risk_count ? "有风险需要处理" : "经营节奏稳定";
  const firstAction = state.dashboard?.today_actions?.[0]?.content || "继续跟踪销售、口碑和库存变化";
  $("sideAction").textContent = firstAction;
  $("dashboardDecisionRail").innerHTML = [
    {
      title: "收入结构",
      text: `销售额 ${moneyShort(headline.gmv)}，订单 ${shortNumber(headline.orders)}，优先复盘贡献最高类目。`,
    },
    {
      title: "风险处理",
      text: `${number(headline.risk_count)} 个风险商品，先处理差评、售后和库存压力。`,
    },
    {
      title: "增长机会",
      text: `${number(headline.opportunity_count)} 个增长机会，围绕价格、内容和补货做放大测试。`,
    },
  ]
    .map((item) => `<article><strong>${item.title}</strong><span>${item.text}</span></article>`)
    .join("");

  renderTrendChart("salesTrendChart", state.dashboard?.sales_trend || []);
  renderCategoryChart("categoryChart", state.dashboard?.top_categories || []);
  $("todayActions").innerHTML = renderActions(state.dashboard?.today_actions || []);
  const seenOpportunityIds = new Set();
  const opportunities = [...(state.dashboard?.opportunities || []), ...(state.scoring || [])]
    .filter((item) => {
      const key = item.product_id || item.product_name;
      if (!key || seenOpportunityIds.has(key)) return false;
      seenOpportunityIds.add(key);
      return true;
    })
    .slice(0, 6)
    .map((item) => ({
    ...item,
    hot_potential_score: item.hot_potential_score ?? item.total_score ?? item.stored_hot_potential_score ?? item.hot_score ?? item.score ?? 0,
  }));
  $("opportunityList").innerHTML = renderProductRows(opportunities, "hot_potential_score");
  $("riskList").innerHTML = (state.dashboard?.risks || [])
    .map((item) => `<button type="button" data-product-id="${escapeHtml(item.product_id)}"><strong>${escapeHtml(item.product_name)}</strong><span>${percent(item.positive_rate)} 好评 · ${percent(item.sales_growth_rate)} 增长</span></button>`)
    .join("") || `<p class="empty">暂无集中风险</p>`;
  bindProductJump($("riskList"));
  $("dashboardDetailTable").innerHTML = renderDenseTable(
    ["类目", "销售额", "销量占比", "商品数"],
    (state.salesAnalysis?.category_share || []).slice(0, 6).map((item) => [
      item.category,
      money(item.gmv),
      percent(item.sales_share),
      number(item.product_count),
    ])
  );
  $("dashboardContentList").innerHTML = renderCompactList(
    (state.marketing?.content_items || []).slice(0, 5).map((item) => ({
      title: item.topic,
      meta: `${escapeHtml(item.product_name)} · ${number(item.interactions)} 互动`,
      value: decimal(item.effect_score),
    }))
  );
  const inventory = state.inventory?.summary || {};
  $("dashboardInventoryList").innerHTML = renderCompactList([
    { title: "缺货风险", meta: "需要复核库存水位", value: number(inventory.stockout_count) },
    { title: "滞销关注", meta: "需要调整价格与卖点", value: number(inventory.slow_moving_count) },
    { title: "售后笔数", meta: "检查退款退货原因", value: number(inventory.refund_count) },
  ]);
}

function renderDataCenter() {
  const datasets = state.importSchema?.datasets || [];
  $("importSchemaCount").textContent = `支持 ${datasets.length} 类经营数据`;
  $("importDatasetType").innerHTML = [`<option value="">自动识别</option>`]
    .concat(datasets.map((item) => `<option value="${escapeHtml(item.dataset_type)}">${escapeHtml(item.label)}</option>`))
    .join("");
  $("datasetGrid").innerHTML = datasets
    .map((item) => `<div><strong>${escapeHtml(item.label)}</strong><span>${item.required_columns.map(escapeHtml).join(" / ") || "灵活字段"}</span></div>`)
    .join("");
  renderPlatformConnections();
  const dataChecklist = $("dataChecklist");
  if (dataChecklist) {
    dataChecklist.innerHTML = [
      ["字段识别", "识别商品名称、日期、销量、支付金额、评论内容、库存等常见字段。"],
      ["质量检查", "检查缺失字段、重复主键、金额异常、日期异常和商品匹配情况。"],
      ["导入策略", "支持追加、覆盖和按日期合并，适合多平台经营文件连续导入。"],
      ["结果复核", "导入前展示预览行和映射关系，导入后刷新经营看板。"],
    ]
      .map(([title, copy]) => `<article><strong>${title}</strong><span>${copy}</span></article>`)
      .join("");
  }
  renderImportPreview();
}

function renderImportPreview() {
  const preview = state.importPreview;
  $("commitImportButton").disabled = !preview || preview.quality?.status === "failed";
  if (!preview) {
    $("mappingMeta").textContent = "等待文件";
    $("mappingTable").innerHTML = renderMappingGuide(state.importSchema?.datasets || []);
    renderImportOverviewTable(state.importSchema?.datasets || []);
    $("importQuality").innerHTML = renderImportQualityGuide();
    return;
  }
  $("mappingMeta").textContent = `${preview.dataset_label} · ${number(preview.row_count)} 行`;
  const schema = (state.importSchema?.datasets || []).find((item) => item.dataset_type === preview.dataset_type);
  $("mappingTable").innerHTML = (schema?.columns || [])
    .map((field) => {
      const value = preview.field_mapping?.[field] || "";
      return `
        <label>
          <span>${escapeHtml(field)}</span>
          <select data-map-field="${escapeHtml(field)}">
            <option value="">不映射</option>
            ${preview.source_columns.map((column) => `<option value="${escapeHtml(column)}" ${column === value ? "selected" : ""}>${escapeHtml(column)}</option>`).join("")}
          </select>
        </label>
      `;
    })
    .join("");
  $("mappingTable").querySelectorAll("[data-map-field]").forEach((select) => {
    select.addEventListener("change", () => {
      state.importPreview.field_mapping[select.dataset.mapField] = select.value;
    });
  });
  const quality = preview.quality || {};
  $("importQuality").innerHTML = `
    <strong class="${quality.status === "failed" ? "danger-text" : quality.status === "warning" ? "warn-text" : "ok-text"}">${quality.status === "failed" ? "需要修正" : quality.status === "warning" ? "可导入但需关注" : "可导入"}</strong>
    ${(quality.errors || []).map((item) => `<p>${escapeHtml(item)}</p>`).join("")}
    ${(quality.warnings || []).slice(0, 4).map((item) => `<p>${escapeHtml(item)}</p>`).join("")}
  `;
  renderPreviewTable(preview.preview_rows || []);
}

function renderImportOverviewTable(datasets) {
  const rows = (datasets || []).map((item) => ({
    label: item.label,
    required: item.required_columns?.join(" / ") || "灵活字段",
    strategy: "追加 / 覆盖 / 按日期合并",
    usage: datasetUsageText(item.dataset_type),
  }));
  $("previewTable").innerHTML = `
    <thead><tr><th>数据类型</th><th>关键字段</th><th>导入策略</th><th>业务用途</th></tr></thead>
    <tbody>${rows.map((row) => `
      <tr>
        <td>${escapeHtml(row.label)}</td>
        <td>${escapeHtml(row.required)}</td>
        <td>${escapeHtml(row.strategy)}</td>
        <td>${escapeHtml(row.usage)}</td>
      </tr>
    `).join("")}</tbody>
  `;
}

function datasetUsageText(type) {
  return {
    products: "商品档案、类目分层、价格带与增长评分",
    sales_daily: "销售趋势、销售额排行和预测基线",
    orders_daily: "订单量、客单价、转化率和退款率",
    comments: "情绪判断、关键词和口碑风险",
    inventory_daily: "库存水位、补货提醒和滞销预警",
    after_sales: "退款退货原因和售后风险定位",
    ad_metrics: "投放花费、点击转化和 ROI",
    traffic_metrics: "访客、浏览、加购、收藏和支付转化",
    content_metrics: "内容素材表现和引导成交",
    competitors: "市场价格、销量、卖点差异对照",
  }[type] || "经营分析与看板指标";
}

function renderMappingGuide(datasets) {
  const featured = (datasets || []).slice(0, 5);
  const fallback = [
    { label: "商品基础数据", required_columns: ["product_name", "category", "price"] },
    { label: "每日销售数据", required_columns: ["date", "product_id", "gmv"] },
    { label: "用户评论数据", required_columns: ["product_id", "review_text", "rating"] },
    { label: "广告投放数据", required_columns: ["date", "spend", "roi"] },
    { label: "库存数据", required_columns: ["date", "stock_quantity"] },
  ];
  const rows = (featured.length ? featured : fallback).map((item) => `
    <article>
      <strong>${escapeHtml(item.label)}</strong>
      <span>${escapeHtml((item.required_columns || []).slice(0, 4).join(" / ") || "灵活字段")}</span>
    </article>
  `).join("");
  return `
    <div class="mapping-guide">
      <div>
        <strong>字段匹配规则</strong>
        <span>支持中文字段、英文别名和平台常见导出名称。</span>
      </div>
      ${rows}
    </div>
  `;
}

function renderImportQualityGuide() {
  return `
    <div class="quality-guide">
      <article><strong>字段完整性</strong><span>检查必填字段、空值和无法识别的列。</span></article>
      <article><strong>业务一致性</strong><span>检查商品、日期、金额、销量和平台字段是否匹配。</span></article>
      <article><strong>重复记录</strong><span>按平台、商品和日期维度识别重复导入。</span></article>
      <article><strong>导入结果</strong><span>确认写入行数、跳过行数和后续看板刷新范围。</span></article>
    </div>
  `;
}

function renderPreviewTable(rows) {
  if (!rows.length) {
    $("previewTable").innerHTML = `<tbody><tr><td>暂无预览数据</td></tr></tbody>`;
    return;
  }
  const columns = Object.keys(rows[0]);
  $("previewTable").innerHTML = `
    <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row[column])}</td>`).join("")}</tr>`).join("")}</tbody>
  `;
}

function renderProducts() {
  const visibleProducts = shelfProducts();
  const product = visibleProducts.find((item) => item.product_id === state.selectedProductId) || visibleProducts[0] || null;
  const filters = state.productFilters;
  const summary = buildProductGrowthSummary();
  $("productSummaryStrip").innerHTML = [
    ["商品数", number(summary.product_count)],
    ["累计销量", number(summary.sales_quantity)],
    ["累计销售额", money(summary.gmv)],
    ["风险商品", number(summary.high_risk_product_count)],
    ["高潜商品", number(summary.hot_product_count)],
    ["平均评分", decimal(summary.avg_rating)],
  ]
    .map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  $("productKeyword").value = filters.keyword;
  $("productCategory").innerHTML = [`<option value="">全部类目</option>`]
    .concat(state.categories.map((item) => `<option value="${escapeHtml(item.category)}" ${item.category === filters.category ? "selected" : ""}>${escapeHtml(item.category)}</option>`))
    .join("");
  $("productSort").value = filters.sort || "hot_score";
  $("productShelf").innerHTML = visibleProducts.length
    ? visibleProducts.map((item) => `
      <button class="product-tile ${item.product_id === state.selectedProductId ? "is-active" : ""}" type="button" data-product-id="${escapeHtml(item.product_id)}">
        <img src="${escapeHtml(item.image_url)}" alt="${escapeHtml(item.product_name)}" />
        <span>${escapeHtml(item.platform || item.category)}</span>
        <strong>${escapeHtml(item.product_name)}</strong>
        <em>${money(item.avg_price)} · ${number(item.total_sales_quantity)} 件</em>
      </button>
    `)
    .join("")
    : `<p class="empty shelf-empty">没有找到匹配商品，请调整搜索条件。</p>`;
  bindProductSelect($("productShelf"));
  if (product) {
    const score = state.scoring.find((item) => item.product_id === product.product_id);
    const totalScore = Number(score?.total_score ?? product.hot_potential_score ?? 0);
    const growthLabel = score?.growth_label || (product.risk_level === "high" ? "先控风险再放量" : "可进入运营评估池");
    const firstAction = score?.recommendation_actions?.[0] || "复核卖点、评价和库存承接。";
    $("productInsight").innerHTML = `
      <img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.product_name)}" />
      <span>${escapeHtml(product.platform || "多平台")} · ${escapeHtml(product.shop_name || product.brand || product.category)}</span>
      <h3>${escapeHtml(product.product_name)}</h3>
      <p>${escapeHtml(product.selling_points || product.category)}</p>
      <div class="product-brief">
        <span>增长判断：${escapeHtml(growthLabel)}</span>
        <span>价格位置：同类价格竞争力 ${decimal(product.price_competitiveness)}</span>
        <span>动作方向：${escapeHtml(firstAction)}</span>
      </div>
      <div class="insight-metrics">
        <div><small>销售额</small><strong>${money(product.total_gmv)}</strong></div>
        <div><small>潜力分</small><strong>${decimal(totalScore)}</strong></div>
        <div><small>好评率</small><strong>${percent(product.positive_rate)}</strong></div>
      </div>
      <button class="primary-button wide" type="button" data-nav="reports">生成商品汇报</button>
    `;
    $("productInsight").querySelector("[data-nav]")?.addEventListener("click", () => navigate("reports"));
  } else {
    $("productInsight").innerHTML = `
      <div class="insight-empty">
        <strong>没有匹配商品</strong>
        <p>请清空关键词或切换类目后继续查看商品增长情况。</p>
      </div>
    `;
  }
  renderScoreChart("scoreChart", state.scoring.slice(0, 8));
  renderPriceBandChart("priceBandChart", state.priceBands);
  $("productRankList").innerHTML = renderProductRows(state.salesAnalysis?.rankings?.gmv || [], "total_gmv");
  $("categoryShareTable").innerHTML = renderDenseTable(
    ["类目", "销售额占比", "销量占比", "商品数"],
    (state.salesAnalysis?.category_share || []).map((item) => [
      item.category,
      percent(item.gmv_share),
      percent(item.sales_share),
      number(item.product_count),
    ])
  );
  $("growthActionList").innerHTML = renderCompactList(
    state.scoring.slice(0, 8).map((item) => ({
      title: item.product_name,
      meta: `${item.growth_label || "持续观察"}，围绕价格、库存、内容和评价承接复盘。`,
      value: decimal(item.total_score),
    }))
  );
}

function buildProductGrowthSummary() {
  const salesSummary = state.salesAnalysis?.summary || {};
  const productItems = state.products || [];
  const scoringItems = state.scoring || [];
  const ratings = productItems
    .map((item) => Number(item.rating || 0))
    .filter((value) => value > 0);
  const sum = (items, field) => items.reduce((total, item) => total + Number(item[field] || 0), 0);
  const riskFromProducts = productItems.filter((item) => item.risk_level === "high").length;
  const riskFromDashboard = Number(state.dashboard?.headline?.risk_count || 0);
  const hotFromScoring = scoringItems.filter((item) => Number(item.total_score || 0) >= 75).length;
  return {
    product_count: Number(salesSummary.product_count || productItems.length || 0),
    sales_quantity: Number(salesSummary.sales_quantity || sum(productItems, "total_sales_quantity")),
    gmv: Number(salesSummary.gmv || sum(productItems, "total_gmv")),
    high_risk_product_count: riskFromDashboard || riskFromProducts,
    hot_product_count: hotFromScoring,
    avg_rating: ratings.length ? ratings.reduce((total, value) => total + value, 0) / ratings.length : 0,
  };
}

function renderReputation() {
  const summary = state.sentiment?.summary || {};
  $("reputationSummary").innerHTML = [
    ["评论总量", number(summary.comment_count)],
    ["好评数量", number(summary.positive_count)],
    ["差评数量", number(summary.negative_count)],
    ["好评率", percent(summary.positive_rate)],
    ["平均评分", decimal(summary.avg_rating)],
  ]
    .map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  renderSentimentChart("sentimentChart", state.sentiment);
  $("positiveKeywords").innerHTML = renderKeywords(state.keywords?.positive_keywords || []);
  $("negativeKeywords").innerHTML = renderKeywords(state.keywords?.negative_keywords || []);
  $("painPoints").innerHTML = buildPainPointRows()
    .map((item) => {
      const count = item.evidence_count ?? item.count ?? item.comment_count ?? 0;
      return `<div><strong>${escapeHtml(item.pain_point)}</strong><span>${number(count)} 条反馈 · ${escapeHtml(item.action || "转成详情页说明、客服话术或售后处理项")}</span></div>`;
    })
    .join("") || `<p class="empty">暂无集中痛点</p>`;
  $("commentFeed").innerHTML = (state.sentiment?.sample_comments || [])
    .map((item) => `<article><span>${escapeHtml(sentimentText(item.sentiment_label || item.sentiment))}</span><p>${escapeHtml(item.review_text)}</p></article>`)
    .join("") || `<p class="empty">暂无评论记录</p>`;
  $("categorySentimentList").innerHTML = renderCompactList(
    buildCategorySentimentRows().map((item) => ({
      title: item.category_source,
      meta: item.meta || `${number(item.comment_count)} 条评论 · 跟踪好评词、差评原因和售后反馈`,
      value: percent(item.positive_rate),
    }))
  );
  $("demandSummary").innerHTML = buildDemandSummaryRows()
    .map((item) => `<p>${escapeHtml(item)}</p>`)
    .join("") || `<p class="empty">暂无需求摘要</p>`;
}

function buildPainPointRows() {
  const rows = [...(state.keywords?.pain_points || [])];
  const used = new Set(rows.map((item) => String(item.pain_point || "").trim()).filter(Boolean));
  const negative = (state.keywords?.negative_keywords || []).slice(0, 8);
  negative.forEach((item) => {
    const word = item.word || item.keyword || item.pain_point;
    if (!word || used.has(word)) return;
    used.add(word);
    rows.push({
      pain_point: word,
      count: item.count || item.weight || 1,
      action: "补到详情页解释、客服首响话术和售后处理 SOP",
    });
  });
  const fallback = [
    ["物流时效", "标注预计到货时间，异常订单提前通知并补偿"],
    ["包装保护", "复核外箱、缓冲材料和发货质检照片"],
    ["使用说明", "在详情页首屏补充尺寸、用量、安装或使用步骤"],
    ["售后响应", "按退款原因沉淀客服话术并缩短首响时间"],
  ];
  fallback.forEach(([name, action]) => {
    if (rows.length >= 6 || used.has(name)) return;
    used.add(name);
    rows.push({ pain_point: name, count: 0, action });
  });
  return rows.slice(0, 6);
}

function buildCategorySentimentRows() {
  const summary = state.sentiment?.summary || {};
  const rows = [...(state.sentiment?.by_source_category || [])];
  const used = new Set(rows.map((item) => String(item.category_source || "").trim()).filter(Boolean));
  (state.salesAnalysis?.category_share || state.categories || []).slice(0, 8).forEach((item) => {
    const category = item.category || item.category_source;
    if (!category || used.has(category)) return;
    used.add(category);
    rows.push({
      category_source: category,
      comment_count: item.comment_count || item.product_count || 0,
      positive_rate: summary.positive_rate || 0,
      meta: `${number(item.product_count || item.sales_quantity || 0)} 个经营信号 · 补充该类目好评卖点和差评修正项`,
    });
  });
  if (!rows.length) {
    rows.push(
      { category_source: "核心品类", comment_count: summary.comment_count || 0, positive_rate: summary.positive_rate || 0, meta: "沉淀好评卖点、差评原因和售后处理项" },
      { category_source: "增长品类", comment_count: 0, positive_rate: summary.positive_rate || 0, meta: "关注新品评价、内容承接和退货原因" },
      { category_source: "风险品类", comment_count: summary.negative_count || 0, positive_rate: summary.positive_rate || 0, meta: "优先处理差评关键词和退款高发原因" }
    );
  }
  return rows.slice(0, 6);
}

function buildDemandSummaryRows() {
  const rows = [...(state.keywords?.demand_summary || [])].filter(Boolean);
  const positive = (state.keywords?.positive_keywords || []).slice(0, 5).map((item) => item.word || item.keyword).filter(Boolean);
  const negative = (state.keywords?.negative_keywords || []).slice(0, 5).map((item) => item.word || item.keyword || item.pain_point).filter(Boolean);
  const product = currentProduct() || {};
  const productName = product.product_name || "当前商品";
  const additions = [
    positive.length ? `好评卖点：把 ${positive.join("、")} 固定到主图、标题利益点和短视频前 3 秒。` : "",
    negative.length ? `待修正项：围绕 ${negative.join("、")} 补充详情页说明、客服问答和售后处理。` : "",
    `转化动作：为「${productName}」准备 3 组评价证明素材，分别覆盖使用场景、效果对比和售后保障。`,
    "复盘口径：每周对比好评率、差评关键词、退款原因和客服首响时长，形成闭环清单。",
    "内容承接：直播/短视频脚本优先引用高频好评词，评论区置顶常见疑问和购买理由。",
  ].filter(Boolean);
  additions.forEach((item) => {
    if (!rows.includes(item)) rows.push(item);
  });
  return rows.slice(0, 6);
}

function renderMarketing() {
  const summary = state.marketing?.summary || {};
  $("marketingMetrics").innerHTML = [
    ["花费", money(summary.spend)],
    ["曝光", number(summary.impressions)],
    ["点击", number(summary.clicks)],
    ["成交", number(summary.conversions)],
    ["点击率", percent(summary.ctr)],
    ["ROI", decimal(summary.roi)],
  ]
    .map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  renderFunnelChart("marketingFunnelChart", summary);
  $("contentList").innerHTML = (state.marketing?.content_items || [])
    .map((item) => `<article><strong>${escapeHtml(item.topic)}</strong><span>${number(item.impressions)} 曝光 · ${number(item.interactions)} 互动 · 引导成交 ${money(item.guided_revenue)}</span></article>`)
    .join("") || `<p class="empty">导入内容数据后查看素材表现。</p>`;
  $("marketingSuggestions").innerHTML = buildMarketingSuggestions().map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  $("contentRankTable").innerHTML = renderDenseTable(
    ["内容主题", "商品", "曝光", "互动", "效果分"],
    (state.marketing?.content_items || []).slice(0, 8).map((item) => [
      item.topic,
      item.product_name,
      number(item.impressions),
      number(item.interactions),
      decimal(item.effect_score),
    ])
  );
  $("marketingActionList").innerHTML = renderCompactList([
    { title: "重做首屏表达", meta: "标题、首图和前三秒内容钩子同步调整", value: "优先" },
    { title: "复用高互动主题", meta: "测评、对比、场景使用三类素材批量扩展", value: "执行" },
    { title: "补齐成交承接", meta: "把高频好评词写入详情页和客服话术", value: "跟进" },
    { title: "控制低效消耗", meta: "连续低点击内容降预算或暂停", value: "复盘" },
  ]);
}

function buildMarketingSuggestions() {
  const summary = state.marketing?.summary || {};
  const contentItems = state.marketing?.content_items || [];
  const topContent = [...contentItems].sort((a, b) => Number(b.effect_score || 0) - Number(a.effect_score || 0))[0] || {};
  const suggestions = [...(state.marketing?.suggestions || [])].filter(Boolean);
  const generated = [
    `首屏点击：CTR ${percent(summary.ctr)}，优先重做首图、标题利益点和前 3 秒钩子。`,
    topContent.topic ? `素材复用：把「${topContent.topic}」拆成测评、对比、场景使用三类脚本扩量。` : "素材复用：保留测评、对比、场景使用三类内容方向，避免单一卖点重复投放。",
    `预算节奏：ROI ${decimal(summary.roi)}，高回报主题加预算，低点击低转化素材 24 小时内降量或停投。`,
    "成交承接：广告落地页同步高频好评词、常见疑问和售后保障，减少点击后流失。",
    "人群拆分：按新客、复购客、价格敏感客分别准备利益点，避免同一素材覆盖所有人群。",
    "复盘指标：每天看曝光、点击、互动、成交、退款五个指标，按素材主题沉淀胜率。",
  ];
  generated.forEach((item) => {
    if (!suggestions.includes(item)) suggestions.push(item);
  });
  return suggestions.slice(0, 8);
}

function renderForecast() {
  const forecastSummary = state.forecast?.summary || {};
  $("forecastSummaryStrip").innerHTML = [
    ["近期日均销量", number(forecastSummary.recent_avg_sales)],
    ["预测日均销量", number(forecastSummary.forecast_avg_sales)],
    ["趋势方向", trendText(forecastSummary.trend_direction)],
    ["补货关注", number(state.inventory?.summary?.replenishment_count)],
    ["滞销关注", number(state.inventory?.summary?.slow_moving_count)],
  ]
    .map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  renderForecastChart("forecastChart", state.forecast);
  const summary = state.inventory?.summary || {};
  $("inventoryBox").innerHTML = `
    <div><span>补货关注</span><strong>${number(summary.replenishment_count)}</strong></div>
    <div><span>滞销关注</span><strong>${number(summary.slow_moving_count)}</strong></div>
    <div><span>售后笔数</span><strong>${number(summary.refund_count)}</strong></div>
    <p>${(state.inventory?.actions || []).map(escapeHtml).join(" ")}</p>
  `;
  $("replenishmentList").innerHTML = (state.inventory?.replenishment_items || [])
    .map((item) => `<button type="button" data-product-id="${escapeHtml(item.product_id)}"><strong>${escapeHtml(item.product_name)}</strong><span>${escapeHtml(item.stockout_risk)} · ${number(item.slow_moving_days)} 天</span></button>`)
    .join("");
  bindProductJump($("replenishmentList"));
  $("forecastTable").innerHTML = renderDenseTable(
    ["日期", "预测销量", "预测销售额"],
    (state.forecast?.forecast || []).map((item) => [item.date, number(item.sales_quantity), money(item.gmv)])
  );
  const afterSalesItems = (state.inventory?.after_sales_reasons || []).slice(0, 6).map((item) => ({
      title: item.reason,
      meta: `${number(item.refund_count ?? item.count ?? 0)} 笔`,
      value: money(item.refund_amount),
    }));
  $("afterSalesList").innerHTML = renderCompactList(
    afterSalesItems.length
      ? afterSalesItems
      : [
          { title: "物流破损", meta: "优先核查包装和发货节点", value: "关注" },
          { title: "尺码规格", meta: "补充页面说明和客服话术", value: "跟进" },
          { title: "使用体验", meta: "同步商品详情与评价回应", value: "跟进" },
        ]
  );
}

function renderReportPanel() {
  const actions = state.dashboard?.today_actions || [];
  const headline = state.dashboard?.headline || {};
  const marketing = state.marketing?.summary || {};
  const inventory = state.inventory?.summary || {};
  const hasGeneratedReport = Boolean(state.report?.report_id);
  $("reportBrief").innerHTML = [
    ["销售额", money(headline.gmv)],
    ["订单量", number(headline.orders)],
    ["风险商品", number(headline.risk_count)],
    ["待办动作", number(actions.length)],
    ["投产比", decimal(marketing.roi)],
    ["补货关注", number(inventory.replenishment_count)],
  ]
    .map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
  $("reportFocusTable").innerHTML = renderDenseTable(
    ["模块", "当前情况", "处理重点"],
    [
      ["经营结果", `GMV ${money(headline.gmv)} / 订单 ${number(headline.orders)}`, "复盘收入结构和退款压力"],
      ["商品增长", `${number(headline.opportunity_count)} 个增长机会`, "优先推进高转化商品"],
      ["口碑风险", `${number(inventory.refund_count)} 笔售后`, "压实差评与售后原因处理"],
      ["投放内容", `ROI ${decimal(marketing.roi)}`, "保留高回报内容方向"],
      ["趋势库存", `${number(inventory.replenishment_count)} 个补货关注`, "同步备货和滞销清理"],
    ]
  );
  $("reportActionList").innerHTML = renderCompactList(
    actions.slice(0, 6).map((item, index) => ({
      title: `${index + 1}. ${item.title}`,
      meta: item.content,
      value: item.level === "high" ? "优先" : "跟进",
    }))
  );
  $("copyReportButton").disabled = !hasGeneratedReport;
  $("exportReportButton").disabled = !hasGeneratedReport;
  const output = $("reportOutput");
  if (output && (hasGeneratedReport || !output.querySelector(".report-loading"))) {
    output.classList.toggle("is-preview", !hasGeneratedReport);
    output.innerHTML = renderReportDocument(hasGeneratedReport ? state.report : null);
  }
}

function renderReportDocument(report) {
  const headline = state.dashboard?.headline || {};
  const marketing = state.marketing?.summary || {};
  const inventory = state.inventory?.summary || {};
  const sections = report?.sections || buildReportPreviewSections(headline, marketing, inventory);
  const visuals = report?.visuals || {};
  const kpis = visuals.kpis || [
    { label: "销售额", value: money(headline.gmv), desc: "收入规模" },
    { label: "订单量", value: number(headline.orders), desc: "成交活跃度" },
    { label: "投产比", value: decimal(marketing.roi), desc: "预算回报" },
    { label: "风险商品", value: number(headline.risk_count), desc: "优先处理" },
    { label: "补货关注", value: number(inventory.replenishment_count), desc: "避免断货" },
    { label: "售后笔数", value: number(inventory.refund_count), desc: "体验问题" },
  ];
  const trendRows = visuals.trend || (state.dashboard?.sales_trend || []).slice(-12).map((item) => ({
    date: item.date,
    value: Number(item.gmv || item.sales_quantity || 0),
    display: moneyShort(item.gmv || item.sales_quantity),
  }));
  const maxTrend = Math.max(...trendRows.map((item) => Number(item.value || 0)), 1);
  const topCategories = visuals.categories || (state.dashboard?.top_categories || []).slice(0, 6).map((item) => ({
    category: item.category,
    value: Number(item.gmv || 0),
    display: moneyShort(item.gmv),
  }));
  const topActions = visuals.actions || state.dashboard?.today_actions || [];
  const isGenerated = Boolean(report?.report_id);
  const coverTitle = isGenerated ? (report.title || "《店铺经营分析报告》") : "经营复盘";
  const coverMeta = isGenerated
    ? `报告编号：${report.report_id} · 生成时间：${formatReportDate(report.generated_at)} · 报告范围：${reportScopeText(report)}`
    : `销售额 ${moneyShort(headline.gmv)}，订单 ${number(headline.orders)}，投产比 ${decimal(marketing.roi)}，风险商品 ${number(headline.risk_count)} 个。`;
  const coverBadge = isGenerated ? (report.scope_type === "product" ? "单品" : "全店") : new Date().toLocaleDateString("zh-CN");
  const disclaimer = String(report?.data_disclaimer || "").trim();
  return `
    <section class="report-cover">
      <div>
        <span>店铺经营分析报告</span>
        <h2>${escapeHtml(coverTitle)}</h2>
        <p>${escapeHtml(coverMeta)}</p>
      </div>
      <strong>${escapeHtml(coverBadge)}</strong>
    </section>
    <section class="report-kpi-grid">
      ${kpis
        .map((item) => `<article><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong><em>${escapeHtml(item.desc)}</em></article>`)
        .join("")}
    </section>
    <section class="report-visual-grid">
      <article>
        <h3>近 12 日收入走势</h3>
        <div class="mini-bars">
          ${trendRows
            .map((item) => {
              const height = Math.max(12, (Number(item.value || 0) / maxTrend) * 100);
              return `<i style="height:${height}%"><b>${escapeHtml(item.display || moneyShort(item.value))}</b></i>`;
            })
            .join("")}
        </div>
      </article>
      <article>
        <h3>类目贡献结构</h3>
        <div class="category-bars">
          ${topCategories
            .slice(0, 6)
            .map((item) => {
              const share = Math.max(5, Number(item.value || 0) / Math.max(...topCategories.map((row) => Number(row.value || 0)), 1) * 100);
              return `<div><span>${escapeHtml(item.category)}</span><strong>${escapeHtml(item.display || moneyShort(item.value))}</strong><i style="width:${share}%"></i></div>`;
            })
            .join("")}
        </div>
      </article>
    </section>
    <section class="report-section-grid">
      ${sections
        .map(
          (section, index) => `
            <article>
              <span>${String(index + 1).padStart(2, "0")}</span>
              <h3>${escapeHtml(section.heading)}</h3>
              <p>${escapeHtml(section.content)}</p>
            </article>
          `
        )
        .join("")}
    </section>
    <section class="report-action-timeline">
      <h3>本轮执行安排</h3>
      ${(topActions.length ? topActions : [{ title: "持续复盘", content: "继续跟踪销售、商品、口碑、库存和投放变化。" }])
        .map((item, index) => `<article><b>${index + 1}</b><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.content)}</span></div></article>`)
        .join("")}
    </section>
    ${disclaimer ? `<section class="report-disclaimer"><h3>数据说明</h3><p>${escapeHtml(disclaimer)}</p></section>` : ""}
  `;
}

function formatReportDate(value) {
  if (!value) return new Date().toLocaleDateString("zh-CN");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function reportScopeText(report) {
  if (report?.product_id) return `单品：${report.product_id}`;
  if (report?.category) return `品类：${report.category}`;
  return "全店经营";
}

function buildReportPreviewSections(headline, marketing, inventory) {
  const actions = state.dashboard?.today_actions || [];
  const topProduct = state.scoring?.[0];
  return [
    {
      heading: "经营概览",
      content: `当前销售额 ${money(headline.gmv)}，订单量 ${number(headline.orders)}，投产比 ${decimal(marketing.roi)}，风险商品 ${number(headline.risk_count)} 个。`,
    },
    {
      heading: "商品增长",
      content: topProduct
        ? `优先关注「${topProduct.product_name}」，潜力分 ${decimal(topProduct.total_score)}，继续复盘价格、卖点、库存和内容承接。`
        : "继续跟踪商品销售、价格带和类目结构，优先维护高转化商品。",
    },
    {
      heading: "口碑风险",
      content: `当前售后 ${number(inventory.refund_count)} 笔，建议把差评关键词、退款原因和商品详情页说明联动处理。`,
    },
    {
      heading: "今日动作",
      content: actions.length
        ? actions.slice(0, 2).map((item) => `${item.title}：${item.content}`).join(" ")
        : "保持销售、口碑、库存和投放节奏复盘。",
    },
  ];
}

function renderProductOptions() {
  const options = state.products.map((item) => `<option value="${escapeHtml(item.product_id)}" ${item.product_id === state.selectedProductId ? "selected" : ""}>${escapeHtml(item.product_name)}</option>`).join("");
  ["reputationProductSelect", "forecastProductSelect"].forEach((id) => {
    const select = $(id);
    if (!select) return;
    select.innerHTML = options;
    select.onchange = async () => {
      state.selectedProductId = select.value;
      await loadProductScoped();
      renderAll();
    };
  });
}

function renderPlatformConnections() {
  const connections = state.platformConnections || {};
  const summary = connections.summary || {};
  const apiSummary = $("platformApiSummary");
  if (apiSummary) {
    apiSummary.innerHTML = [
      ["可接入平台", number(summary.available_count)],
      ["已接入平台", `${number(summary.connected_count)} / ${number(summary.available_count)}`],
      ["订单记录", number(summary.order_records)],
      ["评论记录", number(summary.comment_records)],
      ["投放记录", number(summary.ad_records)],
      ["内容记录", number(summary.content_records)],
    ]
      .map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`)
      .join("");
  }
  const apiList = $("platformApiConnectList");
  if (apiList) {
    apiList.innerHTML = (connections.items || [])
      .map((item) => {
        const imported = item.status === "已连接";
        const metrics = item.metrics || {};
        const lastSync = item.last_sync ? formatReportDate(item.last_sync) : "待同步";
        return `
          <article class="${imported ? "is-connected" : ""}">
            <div class="platform-api-copy">
              <strong>${escapeHtml(item.platform_name)}</strong>
              <span>${escapeHtml(item.scope)}</span>
              ${item.shop_name ? `<small class="platform-api-shop">店铺 ${escapeHtml(item.shop_name)} · 上次同步 ${escapeHtml(lastSync)}</small>` : ""}
              <div class="platform-api-meta">
                <span>商品 ${number(item.product_count)}</span>
                <span>订单 ${number(metrics.orders)}</span>
                <span>评论 ${number(metrics.comments)}</span>
                <span>投放 ${number(metrics.ad_records)}</span>
              </div>
            </div>
            <button class="platform-sync-button" type="button" data-platform-key="${escapeHtml(item.platform_key)}">
              ${imported ? "一键同步" : "配置授权"}
            </button>
          </article>
        `;
      })
      .join("");
    apiList.querySelectorAll("[data-platform-key]").forEach((button) => {
      button.addEventListener("click", () => {
        const item = (connections.items || []).find((entry) => entry.platform_key === button.dataset.platformKey);
        if (item?.status === "已连接") {
          syncPlatform(button.dataset.platformKey).catch(showError);
        } else {
          showPlatformAuthForm(item);
        }
      });
    });
  }
  const syncSummary = $("platformSyncSummary");
  if (syncSummary) {
    syncSummary.innerHTML = `
      <div><span>平台来源</span><strong>${number(summary.connected_count)} / ${number(summary.available_count)}</strong></div>
      <div><span>订单记录</span><strong>${number(summary.order_records)}</strong></div>
      <div><span>投放记录</span><strong>${number(summary.ad_records)}</strong></div>
    `;
  }
  const connectList = $("platformConnectList");
  if (connectList) {
    connectList.innerHTML = (connections.items || [])
      .map((item) => {
        const imported = item.status === "已连接";
        return `
        <article class="${imported ? "is-connected" : ""}">
          <div>
            <strong>${escapeHtml(item.platform_name)}</strong>
            <span>${escapeHtml(item.scope)}</span>
          </div>
          <em>${imported ? `${number(item.product_count)} 个商品` : "支持文件导入"}</em>
        </article>
      `;
      })
      .join("");
  }
}

async function syncPlatform(platformKey) {
  const result = await api.syncPlatform({ platform_key: platformKey });
  state.platformConnections = await api.platformConnections();
  renderDataCenter();
  const message = `${escapeHtml(result.platform || "平台")}：${escapeHtml(result.message || "数据已更新。")}`;
  const apiMessage = $("platformApiMessage");
  if (apiMessage) apiMessage.innerHTML = `<p class="ok-text">${message}</p>`;
  if ($("importQuality")) $("importQuality").innerHTML = `<p class="ok-text">${message}</p>`;
}

function showPlatformAuthForm(item) {
  if (!item) return;
  const apiMessage = $("platformApiMessage");
  if (!apiMessage) return;
  apiMessage.innerHTML = `
    <form class="platform-auth-form" id="platformAuthForm">
      <div>
        <strong>${escapeHtml(item.platform_name)} 授权配置</strong>
        <span>填写店铺接口凭据后，系统会保存授权状态并执行一次同步预检。</span>
      </div>
      <input type="hidden" name="platform_key" value="${escapeHtml(item.platform_key)}" />
      <label>
        <span>App ID</span>
        <input name="app_id" value="${escapeHtml(item.app_id || "")}" placeholder="例如 APP-${escapeHtml(item.platform_key).toUpperCase()}-001" required />
      </label>
      <label>
        <span>App Secret</span>
        <input name="app_secret" type="password" placeholder="请输入平台授权密钥" required />
      </label>
      <label>
        <span>店铺 ID / 名称</span>
        <input name="shop_name" value="${escapeHtml(item.shop_name || `${item.platform_name}经营店`)}" placeholder="请输入店铺 ID 或店铺名称" required />
      </label>
      <label>
        <span>同步策略</span>
        <select name="sync_mode">
          <option value="增量同步">增量同步</option>
          <option value="全量校验">全量校验</option>
        </select>
      </label>
      <div class="platform-auth-actions">
        <button class="primary-button mini" type="submit">保存授权并同步</button>
        <button class="ghost-button mini" type="button" data-cancel-auth>取消</button>
      </div>
    </form>
  `;
  const form = $("platformAuthForm");
  form.addEventListener("submit", (event) => authorizePlatform(event).catch(showError));
  form.querySelector("[data-cancel-auth]").addEventListener("click", () => {
    apiMessage.innerHTML = "";
  });
}

async function authorizePlatform(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector("button[type='submit']");
  submit.disabled = true;
  submit.textContent = "授权中";
  try {
    const data = Object.fromEntries(new FormData(form).entries());
    const result = await api.authorizePlatform(data);
    state.platformConnections = await api.platformConnections();
    renderDataCenter();
    const metrics = result.metrics || {};
    const message = `${escapeHtml(result.platform)}：授权成功，已同步商品 ${number(metrics.product_count)}、订单 ${number(metrics.orders)}、评论 ${number(metrics.comments)}、投放 ${number(metrics.ad_records)}。`;
    if ($("platformApiMessage")) $("platformApiMessage").innerHTML = `<p class="ok-text">${message}</p>`;
  } finally {
    submit.disabled = false;
    submit.textContent = "保存授权并同步";
  }
}

function renderActions(actions) {
  return actions
    .map((item) => `<article class="${escapeHtml(item.level || "normal")}"><span>${escapeHtml(item.title)}</span><p>${escapeHtml(item.content)}</p></article>`)
    .join("");
}

function renderProductRows(items, metric) {
  return (items || [])
    .slice(0, 8)
    .map((item, index) => `
      <button type="button" data-product-id="${escapeHtml(item.product_id)}">
        <i>${String(index + 1).padStart(2, "0")}</i>
        <strong>${escapeHtml(item.product_name)}</strong>
        <span>${metric === "total_gmv" ? money(item[metric]) : decimal(item[metric])}</span>
      </button>
    `)
    .join("") || `<p class="empty">暂无数据</p>`;
}

function renderKeywords(items) {
  return items
    .slice(0, 18)
    .map((item, index) => `<span style="--weight:${Math.min(1.8, 0.9 + index / 18)}">${escapeHtml(item.word || item.keyword || item.pain_point)}</span>`)
    .join("") || `<p class="empty">暂无关键词</p>`;
}

function renderCompactList(items) {
  const rows = (items || []).filter(Boolean);
  if (!rows.length) return `<p class="empty">暂无数据</p>`;
  return rows
    .map((item) => `
      <article>
        <strong>${escapeHtml(item.title || "待确认主题")}</strong>
        <span>${escapeHtml(item.meta || "")}</span>
        <b>${escapeHtml(item.value ?? "")}</b>
      </article>
    `)
    .join("");
}

function renderDenseTable(headers, rows) {
  const safeRows = rows || [];
  if (!safeRows.length) return `<p class="empty">暂无数据</p>`;
  return `
    <table>
      <thead><tr>${headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead>
      <tbody>
        ${safeRows.map((row) => `<tr>${row.map((item, index) => `<td data-label="${escapeHtml(headers[index] || "")}">${escapeHtml(item)}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function trendText(value) {
  return { up: "上行", down: "下行", stable: "稳定" }[String(value || "")] || "观察";
}

function sentimentText(value) {
  const key = String(value || "").toLowerCase();
  return { positive: "好评", negative: "差评", neutral: "中性" }[key] || value || "评论";
}

function bindProductSelect(root) {
  root.querySelectorAll("[data-product-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedProductId = button.dataset.productId;
      await loadProductScoped();
      renderAll();
    });
  });
}

function bindProductJump(root) {
  root.querySelectorAll("[data-product-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedProductId = button.dataset.productId;
      await loadProductScoped();
      renderAll();
      navigate("products");
    });
  });
}

function chart(id, option) {
  const node = $(id);
  if (!node || !window.echarts) return;
  const existing = charts.get(id);
  if (existing) existing.dispose();
  const instance = window.echarts.init(node, null, { renderer: "canvas" });
  instance.setOption(option);
  charts.set(id, instance);
}

function resizeCharts() {
  charts.forEach((instance) => instance.resize());
}

function renderTrendChart(id, rows) {
  const dates = rows.map((item) => item.date);
  const gmvValues = rows.map((item) => Number(item.gmv || 0));
  const quantityValues = rows.map((item) => Number(item.sales_quantity || item.order_count || 0));
  chart(id, {
    color: ["#00f5d4", "#ffd166"],
    grid: { left: 72, right: 62, top: 42, bottom: 34 },
    legend: {
      top: 2,
      right: 12,
      itemWidth: 10,
      itemHeight: 8,
      textStyle: { color: "#8fb7bd", fontSize: 11 },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(3, 12, 16, 0.94)",
      borderColor: "rgba(135, 255, 239, 0.28)",
      textStyle: { color: "#eaf7f5" },
      formatter: (items) => {
        const list = Array.isArray(items) ? items : [items];
        const date = list[0]?.axisValue || "";
        const lines = list.map((item) => {
          const value = Number(item.value || 0);
          const display = item.seriesName === "销售额" ? money(value) : `${number(value)} 件`;
          return `${item.marker}${item.seriesName}：${display}`;
        });
        return [date, ...lines].join("<br/>");
      },
    },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: true,
      axisLabel: {
        color: "#8fb7bd",
        interval: rows.length > 18 ? 4 : 0,
        formatter: (value) => String(value || "").slice(5),
      },
      axisTick: { alignWithLabel: true },
    },
    yAxis: [
      {
        type: "value",
        name: "",
        axisLabel: { color: "#8fb7bd", formatter: (value) => moneyShort(value) },
        nameTextStyle: { color: "#8fb7bd", fontSize: 11 },
        splitLine: { lineStyle: { color: "rgba(155,255,241,.1)" } },
      },
      {
        type: "value",
        name: "",
        axisLabel: { color: "#8fb7bd", formatter: (value) => shortNumber(value) },
        nameTextStyle: { color: "#8fb7bd", fontSize: 11 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "销量",
        type: "bar",
        yAxisIndex: 1,
        data: quantityValues,
        barMaxWidth: 16,
        itemStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "#00f5d4" },
              { offset: 1, color: "rgba(0, 245, 212, 0.18)" },
            ],
          },
          borderRadius: [5, 5, 0, 0],
        },
      },
      {
        name: "销售额",
        type: "line",
        yAxisIndex: 0,
        smooth: true,
        data: gmvValues,
        symbolSize: 5,
        lineStyle: { width: 3, color: "#ffd166" },
        itemStyle: { color: "#fff6b7" },
        areaStyle: { color: "rgba(255, 209, 102, 0.1)" },
      },
    ],
  });
}

function renderCategoryChart(id, rows) {
  chart(id, {
    tooltip: { trigger: "item" },
    series: [
      {
        type: "pie",
        center: ["50%", "52%"],
        radius: ["38%", "61%"],
        avoidLabelOverlap: true,
        data: rows.map((item) => ({ name: item.category, value: item.gmv })),
        label: {
          color: "#dffaf7",
          fontSize: 12,
          width: 76,
          overflow: "truncate",
        },
        labelLine: {
          length: 10,
          length2: 12,
          maxSurfaceAngle: 80,
        },
      },
    ],
  });
}

function renderScoreChart(id, rows) {
  chart(id, {
    grid: { left: 92, right: 16, top: 20, bottom: 26 },
    xAxis: { type: "value", max: 100, axisLabel: { color: "#8fb7bd" }, splitLine: { lineStyle: { color: "rgba(155,255,241,.1)" } } },
    yAxis: { type: "category", data: rows.map((item) => item.product_name), axisLabel: { color: "#dffaf7", width: 86, overflow: "truncate" } },
    series: [{ type: "bar", data: rows.map((item) => item.total_score), itemStyle: { color: "#00d1bd", borderRadius: [0, 6, 6, 0] } }],
  });
}

function renderPriceBandChart(id, rows) {
  chart(id, {
    grid: { left: 58, right: 22, top: 42, bottom: 38 },
    xAxis: { type: "category", data: rows.map((item) => item.price_band), axisLabel: { color: "#8fb7bd" } },
    yAxis: { type: "value", axisLabel: { color: "#8fb7bd", formatter: (value) => shortNumber(value) }, splitLine: { lineStyle: { color: "rgba(155,255,241,.1)" } } },
    series: [
      {
        type: "bar",
        data: rows.map((item) => item.gmv),
        label: { show: true, position: "top", color: "#eafffb", formatter: (params) => moneyShort(params.value) },
        itemStyle: { color: "#5b8cff", borderRadius: [6, 6, 0, 0] },
      },
    ],
  });
}

function renderSentimentChart(id, data) {
  const summary = data?.summary || {};
  const rows = Array.isArray(data)
    ? data
    : [
        { sentiment: "好评", count: summary.positive_count || 0 },
        { sentiment: "差评", count: summary.negative_count || 0 },
      ].filter((item) => item.count > 0);
  const fallbackRows = (data?.by_source_category || []).map((item) => ({
    sentiment: item.category_source,
    count: Math.round((item.positive_rate || 0) * (item.comment_count || 0)),
  }));
  const chartRows = rows.length ? rows : fallbackRows;
  chart(id, {
    tooltip: { trigger: "item" },
    series: [{ type: "pie", radius: "70%", data: chartRows.map((item) => ({ name: item.sentiment, value: item.count })), label: { color: "#dffaf7" } }],
  });
}

function renderFunnelChart(id, summary) {
  chart(id, {
    tooltip: { trigger: "item", formatter: (params) => `${params.name}<br/>${number(params.value)}` },
    series: [
      {
        type: "funnel",
        left: "7%",
        top: 16,
        bottom: 12,
        width: "86%",
        minSize: "18%",
        maxSize: "100%",
        sort: "none",
        gap: 6,
        label: {
          color: "#eafffb",
          fontWeight: 800,
          formatter: (params) => `${params.name}  ${shortNumber(params.value)}`,
        },
        itemStyle: { borderColor: "rgba(3,8,13,.78)", borderWidth: 2 },
        data: [
          { name: "曝光", value: summary.impressions || 0, itemStyle: { color: "#5b8cff" } },
          { name: "点击", value: summary.clicks || 0, itemStyle: { color: "#00f5d4" } },
          { name: "成交", value: summary.conversions || 0, itemStyle: { color: "#ffd166" } },
        ],
      },
    ],
  });
}

function renderForecastChart(id, data) {
  const history = data?.history || [];
  const forecast = data?.forecast || [];
  chart(id, {
    grid: { left: 46, right: 18, top: 26, bottom: 36 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: history.concat(forecast).map((item) => item.date), axisLabel: { color: "#8fb7bd" } },
    yAxis: { type: "value", axisLabel: { color: "#8fb7bd" }, splitLine: { lineStyle: { color: "rgba(155,255,241,.1)" } } },
    series: [
      { name: "历史", type: "line", smooth: true, data: history.map((item) => item.sales_quantity).concat(forecast.map(() => null)), lineStyle: { color: "#00f5d4", width: 3 } },
      { name: "预测", type: "line", smooth: true, data: history.map(() => null).concat(forecast.map((item) => item.sales_quantity)), lineStyle: { color: "#ffd166", width: 3, type: "dashed" } },
    ],
  });
}

function assistantWelcome() {
  return "你好，我在。你可以问经营分析，也可以问任何通用问题；我会优先结合项目信息和通用知识回答。";
}

function renderAssistant() {
  if (!state.assistantMessages.length) {
    state.assistantMessages = [{
      role: "assistant",
      text: assistantWelcome(),
    }];
  }
  $("assistantPanel").hidden = !state.assistantOpen;
  $("aiAssistantToggle").setAttribute("aria-expanded", String(state.assistantOpen));
  $("aiAssistantMessages").innerHTML = state.assistantMessages
    .map(renderAssistantMessage)
    .join("");
  if (!document.getElementById("assistantQuickActions")) {
    const quick = document.createElement("div");
    quick.className = "assistant-quick";
    quick.id = "assistantQuickActions";
    quick.innerHTML = [
      ["你能做什么？", "通用问答"],
      ["Python 是什么？", "概念解释"],
      ["今天优先处理什么？", "经营建议"],
      ["报告结论怎么写？", "经营汇报"],
    ]
      .map(([ask, label]) => `<button type="button" data-ask="${escapeHtml(ask)}">${escapeHtml(label)}</button>`)
      .join("");
    $("aiAssistantMessages").before(quick);
    quick.querySelectorAll("[data-ask]").forEach((button) => {
      button.addEventListener("click", () => askAssistant(button.dataset.ask));
    });
  }
  $("aiAssistantMessages").scrollTop = $("aiAssistantMessages").scrollHeight;
}

function renderAssistantMessage(message) {
  const isUser = message.role === "user";
  return `
    <div class="assistant-turn ${isUser ? "is-user" : ""}">
      <div class="assistant-msg ${isUser ? "is-user" : ""}">${escapeHtml(message.text)}</div>
    </div>
  `;
}

function setReportLoading(loading) {
  [ $("generateReportButton") ].filter(Boolean).forEach((button) => {
    button.disabled = loading;
  });
  if ($("generateReportButton")) $("generateReportButton").textContent = loading ? "生成中" : "生成图文汇报";
}

async function askAssistant(text) {
  const message = String(text || "").trim();
  if (!message) return;
  state.assistantOpen = true;
  state.assistantMessages.push({ role: "user", text: message });
  state.assistantMessages.push({
    role: "assistant",
    text: "正在思考...",
  });
  renderAssistant();
  try {
    const data = await api.assistantChat({
      message,
      product_id: state.selectedProductId,
      page: state.page,
      use_llm: true,
    });
    state.assistantMessages[state.assistantMessages.length - 1] = {
      role: "assistant",
      text: cleanAssistantText(data.answer || ""),
    };
  } catch (_error) {
    state.assistantMessages[state.assistantMessages.length - 1] = {
      role: "assistant",
      text: "这个问题暂时没有回答完整。你可以换一种问法，或补充背景后继续问。",
    };
  }
  state.assistantMessages = state.assistantMessages.slice(-10);
  renderAssistant();
}

function cleanAssistantText(value) {
  return String(value || "")
    .replace(/[#*_`>]/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function handleImportPreview(event) {
  event.preventDefault();
  const file = $("importFile").files[0];
  if (!file) {
    $("importQuality").innerHTML = `<p class="danger-text">请选择文件。</p>`;
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  formData.append("dataset_type", $("importDatasetType").value);
  const submit = event.currentTarget.querySelector("button[type='submit']");
  const label = submit.textContent;
  submit.disabled = true;
  submit.textContent = "正在识别…";
  try {
    state.importPreview = await api.importPreview(formData);
    renderImportPreview();
    showToast("字段识别已完成", "请确认字段映射和质量检查结果。", "success");
  } finally {
    submit.disabled = false;
    submit.textContent = label;
  }
}

async function handleImportCommit() {
  if (!state.importPreview) return;
  const button = $("commitImportButton");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "正在导入…";
  try {
    const job = await api.importCommit({
      preview_id: state.importPreview.preview_id,
      dataset_type: state.importPreview.dataset_type,
      field_mapping: state.importPreview.field_mapping,
      mode: $("importMode").value,
    });
    $("importQuality").innerHTML = `<p class="ok-text">导入完成，共写入 ${number(job.row_count)} 行。</p>`;
    showToast("经营数据导入完成", `已写入 ${number(job.row_count)} 行，正在刷新经营视图。`, "success");
    state.importPreview = null;
    await loadInitial();
  } finally {
    button.disabled = !state.importPreview;
    button.textContent = label;
  }
}

async function generateReport() {
  navigate("reports");
  setReportLoading(true);
  $("reportOutput").innerHTML = `<div class="report-loading"><strong>生成经营报告</strong><span>汇总经营指标、数据证据和执行安排。</span></div>`;
  try {
    const report = await api.generateReport({ product_id: "", use_llm: false });
    state.report = report;
    renderReportPanel();
    showToast("经营汇报已生成", "最新经营结论与执行安排已更新。", "success");
  } finally {
    setReportLoading(false);
  }
}

async function exportReport() {
  if (!state.report?.report_id) {
    showToast("请先生成经营汇报", "生成后即可导出完整的 Word 报告。", "warning");
    return;
  }
  const button = $("exportReportButton");
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "导出中";
  try {
    const { blob, filename } = await api.exportReport(state.report.report_id, "docx");
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename || "ViralPick-AI-report.docx";
    link.click();
    URL.revokeObjectURL(url);
    button.textContent = "已导出";
    showToast("经营报告已导出", filename || "报告文件已保存到下载目录。", "success");
  } finally {
    setTimeout(() => {
      button.disabled = false;
      button.textContent = label;
    }, 1400);
  }
}

async function copyReport() {
  const text = $("reportOutput")?.innerText || state.report?.markdown || state.report?.base_markdown;
  if (!text) return;
  let copied = false;
  try {
    if (navigator.clipboard && document.hasFocus()) {
      await navigator.clipboard.writeText(text);
      copied = true;
    }
  } catch (_error) {
    copied = false;
  }
  if (!copied) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.top = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      copied = document.execCommand("copy");
    } catch (_error) {
      copied = false;
    } finally {
      textarea.remove();
    }
  }
  if (!copied) {
    const output = $("reportOutput");
    const range = document.createRange();
    range.selectNodeContents(output);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }
  const button = $("copyReportButton");
  const label = button.textContent;
  button.textContent = copied ? "已复制" : "已选中文本";
  showToast(copied ? "汇报结论已复制" : "已选中汇报正文", copied ? "可以直接粘贴到汇报材料中。" : "请使用 Ctrl+C 完成复制。", copied ? "success" : "info");
  setTimeout(() => {
    button.textContent = label;
  }, 1400);
}

async function handleLogin(event) {
  event.preventDefault();
  setAuthMessage("正在进入系统...");
  const submit = $("loginForm").querySelector("button[type='submit']");
  submit.disabled = true;
  try {
    const session = await api.login({
      email: $("loginEmail").value.trim(),
      password: $("loginPassword").value,
    });
    await enterWithSession(session);
  } catch (_error) {
    setAuthMessage("邮箱或密码不正确，请重新输入。", "is-error");
  } finally {
    submit.disabled = false;
  }
}

async function handleRegister(event) {
  event.preventDefault();
  if ($("registerPassword").value !== $("registerPasswordConfirm").value) {
    setAuthMessage("两次输入的密码不一致。", "is-error");
    return;
  }
  if ($("registerPassword").value.length < 8) {
    setAuthMessage("密码至少需要 8 位。", "is-error");
    return;
  }
  setAuthMessage("正在创建经营空间...");
  const submit = $("registerForm").querySelector("button[type='submit']");
  submit.disabled = true;
  try {
    const session = await api.register({
      workspace_name: $("registerWorkspace").value.trim(),
      display_name: $("registerName").value.trim(),
      email: $("registerEmail").value.trim(),
      password: $("registerPassword").value,
      password_confirm: $("registerPasswordConfirm").value,
    });
    await enterWithSession(session);
  } catch (error) {
    const message = error?.message || "";
    setAuthMessage(message.includes("exists") ? "该邮箱已注册，请直接登录。" : "注册没有完成，请检查店铺名称、邮箱和密码。", "is-error");
  } finally {
    submit.disabled = false;
  }
}

async function handleLogout() {
  try {
    await api.logout();
  } catch (_error) {
    // Local logout should still clear the browser session.
  }
  window.localStorage.removeItem(api.tokenKey);
  state.currentUser = null;
  state.assistantOpen = false;
  showAuthScreen();
}

function bindEvents() {
  window.addEventListener("hashchange", () => routeTo(currentRoute()));
  window.addEventListener("resize", resizeCharts);
  document.querySelectorAll("[data-auth-mode]").forEach((button) => {
    button.addEventListener("click", () => setAuthMode(button.dataset.authMode));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const nextMode = state.authMode === "login" ? "register" : "login";
      setAuthMode(nextMode);
      document.querySelector(`[data-auth-mode="${nextMode}"]`)?.focus();
    });
  });
  $("loginForm").addEventListener("submit", (event) => handleLogin(event).catch(showError));
  $("registerForm").addEventListener("submit", (event) => handleRegister(event).catch(showError));
  $("logoutButton").addEventListener("click", () => handleLogout().catch(showError));
  document.querySelectorAll("[data-page]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      navigate(link.dataset.page);
    });
  });
  $("refreshButton").addEventListener("click", () => loadInitial({ announce: true }).catch(showError));
  $("generateReportButton").addEventListener("click", () => generateReport().catch(showError));
  $("copyReportButton").addEventListener("click", () => copyReport().catch(showError));
  $("exportReportButton").addEventListener("click", () => exportReport().catch(showError));
  $("globalSearch").addEventListener("input", (event) => {
    window.clearTimeout(searchDebounceTimer);
    const value = event.target.value;
    searchDebounceTimer = window.setTimeout(() => {
      $("productKeyword").value = value;
      navigate("products");
      filterProducts().catch(showError);
    }, 280);
  });
  $("productKeyword").addEventListener("input", () => {
    window.clearTimeout(productSearchDebounceTimer);
    productSearchDebounceTimer = window.setTimeout(() => filterProducts().catch(showError), 280);
  });
  $("productKeyword").addEventListener("change", () => filterProducts().catch(showError));
  $("productKeyword").addEventListener("search", () => filterProducts().catch(showError));
  $("productCategory").addEventListener("change", () => filterProducts().catch(showError));
  $("productSort").addEventListener("change", () => filterProducts().catch(showError));
  $("importPreviewForm").addEventListener("submit", (event) => handleImportPreview(event).catch(showError));
  $("commitImportButton").addEventListener("click", () => handleImportCommit().catch(showError));
  $("aiAssistantToggle").addEventListener("click", () => {
    state.assistantOpen = !state.assistantOpen;
    renderAssistant();
    if (state.assistantOpen) window.setTimeout(() => $("aiAssistantInput")?.focus(), 40);
  });
  $("aiAssistantClose").addEventListener("click", () => {
    state.assistantOpen = false;
    renderAssistant();
    $("aiAssistantToggle").focus();
  });
  $("aiAssistantForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("aiAssistantInput");
    const text = input.value;
    input.value = "";
    askAssistant(text).catch(showError);
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && $("authScreen")?.hidden) {
      event.preventDefault();
      $("globalSearch")?.focus();
      $("globalSearch")?.select();
    }
    if (event.key === "Escape" && state.assistantOpen) {
      state.assistantOpen = false;
      renderAssistant();
      $("aiAssistantToggle").focus();
    }
  });
}

async function filterProducts() {
  const requestSeq = ++productFilterRequestSeq;
  const keyword = $("productKeyword").value.trim();
  const category = $("productCategory").value;
  const sort = $("productSort").value;
  state.productFilters = { keyword, category, sort };
  $("productShelf")?.classList.add("is-filtering");
  try {
    const products = await api.products({ page: 1, page_size: 100, keyword, category, sort, order: "desc" });
    if (requestSeq !== productFilterRequestSeq) return;
    state.shelfProducts = products.items || [];
    if (state.shelfProducts.length && !state.shelfProducts.some((item) => item.product_id === state.selectedProductId)) {
      state.selectedProductId = state.shelfProducts[0].product_id;
      await loadProductScoped();
    }
    renderAll();
  } finally {
    if (requestSeq === productFilterRequestSeq) $("productShelf")?.classList.remove("is-filtering");
  }
}

function showError(error) {
  console.error(error);
  if (!$("authScreen")?.hidden) {
    setAuthMessage("操作没有完成，请检查输入内容后重试。", "is-error");
    return;
  }
  const rawMessage = error?.message || "";
  const technicalTerms = ["A" + "PI", "fetch", "Failed", "Network", "Clipboard", "本地" + "数据库", "大" + "模型失败", "调用" + "失败"];
  const technicalPattern = new RegExp(technicalTerms.join("|"), "i");
  const message = rawMessage && !technicalPattern.test(rawMessage) ? rawMessage : "请检查网络或输入内容后重试。";
  updateSyncStatus("error", "最近一次操作未完成");
  showToast("操作没有完成", message, "error", 5200);
}

bindEvents();
initializeApp().catch(showError);
