import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

echarts.use([
  BarChart, LineChart, ScatterChart, DataZoomComponent, GridComponent, LegendComponent, MarkLineComponent,
  TooltipComponent, CanvasRenderer,
]);

export const THEME = {
  text: "#c9cdd6",
  muted: "#7d8494",
  grid: "#2a2f3a",
  gold: "#e3b341",
  blue: "#5aa7f0",
  green: "#4cc38a",
  red: "#ef6b6b",
  violet: "#a98bf5",
  teal: "#3cc6c6",
};

export const baseOption = {
  backgroundColor: "transparent",
  textStyle: { color: THEME.text, fontFamily: "Inter, Segoe UI, sans-serif" },
  grid: { left: 64, right: 24, top: 36, bottom: 40 },
  tooltip: { trigger: "axis", backgroundColor: "#151922", borderColor: "#333a48", textStyle: { color: THEME.text } },
  legend: { textStyle: { color: THEME.muted }, top: 0 },
};

export function axisStyle(extra: object = {}) {
  return {
    axisLine: { lineStyle: { color: THEME.grid } },
    axisLabel: { color: THEME.muted },
    splitLine: { lineStyle: { color: THEME.grid } },
    ...extra,
  };
}

export function Chart({ option, height = 320, onClick }: {
  option: echarts.EChartsCoreOption;
  height?: number;
  onClick?: (params: echarts.ECElementEvent) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.current?.dispose();
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option, true);
  }, [option]);

  useEffect(() => {
    const c = chart.current;
    if (!c || !onClick) return;
    c.on("click", onClick);
    return () => {
      c.off("click", onClick);
    };
  }, [onClick]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
