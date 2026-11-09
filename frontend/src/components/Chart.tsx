import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  TitleComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { TrendSeries, MetricDefinition } from "../sdk";
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  TitleComponent,
  CanvasRenderer,
]);
export function Chart({
  series,
  definitions = [],
}: {
  series: TrendSeries[];
  definitions?: MetricDefinition[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    const hasValues = series.some((s) =>
      s.points.some((p) => p.value !== null),
    );
    const units = [
      ...new Set(
        series.map(
          (s) =>
            definitions.find((d) => d.id === s.metricId)?.unit ?? "单位未确认",
        ),
      ),
    ];
    chart.setOption(
      hasValues
        ? {
            color: ["#66aaff", "#69c6b4", "#d8b66a", "#b4a6e5"],
            grid: {
              left: 60,
              right: Math.max(45, units.length * 40),
              top: 55,
              bottom: 62,
            },
            tooltip: {
              trigger: "axis",
              valueFormatter: (value: unknown) =>
                value === null ? "—" : String(value),
            },
            legend: { textStyle: { color: "#91aab4", fontSize: 10 }, top: 4 },
            xAxis: {
              type: "time",
              name: "时间",
              axisLabel: {
                color: "#75919a",
                formatter: (value: number) =>
                  new Intl.DateTimeFormat("zh-CN", {
                    timeZone: "Asia/Shanghai",
                    month: "2-digit",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  }).format(new Date(value)),
              },
              axisLine: { lineStyle: { color: "#27414c" } },
            },
            yAxis: units.map((unit, i) => ({
              type: "value",
              name: unit,
              position: i === 0 ? "left" : "right",
              offset: i > 1 ? (i - 1) * 48 : 0,
              nameTextStyle: { color: "#75919a" },
              axisLabel: { color: "#75919a" },
              splitLine: { show: i === 0, lineStyle: { color: "#18313b" } },
            })),
            dataZoom: [
              { type: "inside" },
              {
                type: "slider",
                bottom: 3,
                height: 15,
                borderColor: "#27414c",
                textStyle: { color: "#75919a" },
              },
            ],
            // 每条曲线使用自身时间戳，不能按第一条曲线下标对齐不同时刻的读数。
            series: series.map((s) => ({
              name: (() => {
                const d = definitions.find((d) => d.id === s.metricId);
                return d ? `${d.name} · ${d.source}` : s.metricId;
              })(),
              type: "line",
              showSymbol: false,
              connectNulls: false,
              yAxisIndex: units.indexOf(
                definitions.find((d) => d.id === s.metricId)?.unit ??
                  "单位未确认",
              ),
              data: s.points.map((p) => [p.timestamp, p.value]),
            })),
          }
        : {
            title: {
              text: "—",
              subtext: "暂无历史数据",
              left: "center",
              top: "39%",
              textStyle: { color: "#78909a", fontSize: 20, fontWeight: 400 },
              subtextStyle: { color: "#4d6b77", fontSize: 11 },
            },
          },
    );
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [series, definitions]);
  return (
    <div
      ref={ref}
      className="chart"
      role="img"
      aria-label={
        series.length ? "各测点历史趋势，按各自时间戳显示" : "暂无历史数据"
      }
    />
  );
}
