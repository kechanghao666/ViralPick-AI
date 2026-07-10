import { compact, money } from "./format.js";

const chartRegistry = new Map();

function chartOf(elementId) {
  const element = document.getElementById(elementId);
  if (!element || !window.echarts) return null;
  const chart = window.echarts.getInstanceByDom(element) || window.echarts.init(element);
  chartRegistry.set(elementId, chart);
  return chart;
}

const axisText = { color: "#718086", fontSize: 11 };
const splitLine = { lineStyle: { color: "rgba(20, 38, 42, 0.08)" } };
const palette = ["#00a99d", "#ffb020", "#ef5b5b", "#446cff", "#7c5cff", "#2f9e44"];

export function renderCategoryChart(categories = [], metric = "gmv") {
  const chart = chartOf("categoryChart");
  if (!chart) return;
  const rows = [...categories].sort((a, b) => Number(b[metric]) - Number(a[metric])).slice(0, 8);
  chart.setOption({
    color: palette,
    grid: { top: 28, right: 24, bottom: 46, left: 64 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (value) => (metric === "gmv" ? money(value) : compact(value)),
    },
    xAxis: {
      type: "category",
      data: rows.map((row) => row.category),
      axisTick: { show: false },
      axisLabel: {
        ...axisText,
        interval: 0,
        formatter: (value) => (value.length > 4 ? `${value.slice(0, 4)}\n${value.slice(4)}` : value),
      },
      axisLine: { lineStyle: { color: "rgba(20, 38, 42, 0.14)" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { ...axisText, formatter: compact },
      splitLine,
    },
    series: [
      {
        name: metric === "gmv" ? "销售额" : "销量",
        type: "bar",
        data: rows.map((row) => Number(row[metric]) || 0),
        barWidth: 26,
        itemStyle: { borderRadius: [4, 4, 0, 0] },
      },
    ],
  });
}

export function renderTrendChart(items = []) {
  const chart = chartOf("trendChart");
  if (!chart) return;
  chart.setOption({
    color: ["#00a99d", "#ffb020"],
    grid: { top: 36, right: 42, bottom: 42, left: 62 },
    tooltip: { trigger: "axis" },
    legend: { top: 0, left: 4, textStyle: axisText },
    xAxis: {
      type: "category",
      data: items.map((item) => String(item.date).slice(5)),
      axisTick: { show: false },
      axisLabel: axisText,
      axisLine: { lineStyle: { color: "rgba(20, 38, 42, 0.14)" } },
    },
    yAxis: [
      { type: "value", axisLabel: { ...axisText, formatter: compact }, splitLine },
      { type: "value", axisLabel: { ...axisText, formatter: compact }, splitLine: { show: false } },
    ],
    series: [
      {
        name: "销售额",
        type: "line",
        smooth: true,
        data: items.map((item) => Number(item.gmv) || 0),
        symbolSize: 5,
        lineStyle: { width: 3 },
        areaStyle: { opacity: 0.08 },
      },
      {
        name: "销量",
        type: "line",
        yAxisIndex: 1,
        smooth: true,
        data: items.map((item) => Number(item.sales_quantity) || 0),
        symbolSize: 5,
        lineStyle: { width: 2 },
      },
    ],
  });
}

export function renderForecastChart(history = [], forecast = []) {
  const chart = chartOf("forecastChart");
  if (!chart) return;
  const historyTail = history.slice(-21);
  const labels = [...historyTail.map((item) => String(item.date).slice(5)), ...forecast.map((item) => String(item.date).slice(5))];
  chart.setOption({
    color: ["#00a99d", "#446cff"],
    grid: { top: 36, right: 30, bottom: 42, left: 64 },
    tooltip: { trigger: "axis" },
    legend: { top: 0, left: 4, textStyle: axisText },
    xAxis: {
      type: "category",
      data: labels,
      axisTick: { show: false },
      axisLabel: axisText,
      axisLine: { lineStyle: { color: "rgba(20, 38, 42, 0.14)" } },
    },
    yAxis: { type: "value", axisLabel: { ...axisText, formatter: compact }, splitLine },
    series: [
      {
        name: "历史销量",
        type: "line",
        smooth: true,
        data: [...historyTail.map((item) => Number(item.sales_quantity) || 0), ...forecast.map(() => null)],
        lineStyle: { width: 3 },
        symbolSize: 5,
      },
      {
        name: "预测销量",
        type: "line",
        smooth: true,
        data: [...historyTail.map(() => null), ...forecast.map((item) => Number(item.sales_quantity) || 0)],
        lineStyle: { width: 3, type: "dashed" },
        symbolSize: 5,
      },
    ],
  });
}

export function renderScoreChart(items = []) {
  const chart = chartOf("scoreChart");
  if (!chart) return;
  const rows = items.slice(0, 10).reverse();
  chart.setOption({
    color: ["#00a99d"],
    grid: { top: 12, right: 28, bottom: 24, left: 120 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "value",
      max: 100,
      axisLabel: axisText,
      splitLine,
    },
    yAxis: {
      type: "category",
      data: rows.map((row) => row.product_name),
      axisTick: { show: false },
      axisLabel: {
        ...axisText,
        width: 110,
        overflow: "truncate",
      },
    },
    series: [
      {
        type: "bar",
        data: rows.map((row) => Number(row.total_score || row.hot_potential_score || 0)),
        barWidth: 16,
        itemStyle: { borderRadius: [0, 4, 4, 0] },
      },
    ],
  });
}

export function resizeCharts() {
  chartRegistry.forEach((chart) => chart.resize());
}
