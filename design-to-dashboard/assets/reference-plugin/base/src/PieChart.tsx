/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
/* eslint-disable no-restricted-syntax */
import { useCallback, useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts/core";
import { PieChart as PieChartType } from "echarts/charts";
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  GraphicComponent,
} from "echarts/components";
import type { GraphicComponentOption } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { getCurrencySymbol } from "@superset-ui/core";
import { StableChartInput, useTheme } from "./adapters/supersetAdapter";
import { PieChartQueryFormData } from "./types";
import {
  buildProviderMap,
  getTopNSlices,
  parseColors,
  formatNumber,
  FormData,
} from "./utils/pieChartUtils";
import { DEFAULT_TOP_N, FONT } from "./constants";
import { NoDataScreen } from "src/components/NoDataScreen";

// ECharts types its label callback payload loosely; these are the fields
// this chart actually reads.
interface EChartsLabelParams {
  name?: string;
  value?: number;
  percent?: number;
}

echarts.use([
  PieChartType,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  GraphicComponent,
  CanvasRenderer,
]);

export default function PieChart({
  data,
  width,
  height,
  groupby,
  metric,
  formData,
}: StableChartInput<PieChartQueryFormData>) {
  const theme = useTheme();
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  // Extract configuration from formData. Typed, because the form data type
  // names every control the panel declares.
  const showDecimals: boolean = formData?.showDecimals ?? false;
  const currencySymbol: string = formData?.currencyFormat
    ? getCurrencySymbol(formData.currencyFormat) || ""
    : "";
  const topN: number = formData?.topN ?? DEFAULT_TOP_N;
  const tooltipEnabled: boolean = formData?.tooltipEnabled ?? true;
  const showTotalInTooltip: boolean = formData?.showTotalInTooltip ?? true;
  const customColors: string = formData?.customColors ?? "";
  const tooltipBreakdownCol: string = String(
    formData?.tooltipBreakdownCol ?? "",
  );

  // The design's own hexes arrive through the `customColors` control, which
  // stage D fills from the design system. Unset, the chart falls back to
  // theme tokens rather than to colours written into this file.
  const defaultPalette = useMemo(
    () => [
      theme.colorPrimary,
      theme.colorSuccess,
      theme.colorWarning,
      theme.colorError,
      theme.colorInfo,
    ],
    [theme],
  );
  const palette = useMemo(
    () => parseColors(customColors, defaultPalette),
    [customColors, defaultPalette],
  );

  const pieFormData: FormData = useMemo(
    () => ({
      groupby: groupby?.slice(0, 2) ?? [],
      metric,
      tooltipBreakdownCol: tooltipBreakdownCol || undefined,
    }),
    [groupby, metric, tooltipBreakdownCol],
  );

  // Compute chart data
  const { providerMap, pieData, grandTotal } = useMemo(() => {
    if (!data || data.length === 0 || !groupby || !metric) {
      return { providerMap: {}, pieData: [], grandTotal: 0 };
    }
    const map = buildProviderMap(data, pieFormData);
    const slices = getTopNSlices(map, palette, topN);
    const total = slices.reduce((sum, d) => sum + d.value, 0);
    return { providerMap: map, pieData: slices, grandTotal: total };
  }, [data, pieFormData, palette, topN, groupby, metric]);

  // Build ECharts option
  const buildOption = useCallback(
    (): echarts.EChartsCoreOption => ({
      tooltip: {
        show: tooltipEnabled,
        trigger: "item",
        confine: true,
        backgroundColor: theme.colorBgContainer,
        borderColor: theme.colorBorderSecondary,
        borderWidth: 1,
        borderRadius: 8,
        padding: [10, 12, 10, 12],
        extraCssText: `box-shadow: ${theme.boxShadow}; max-width: 220px;`,
        textStyle: {
          fontFamily: FONT.INTER,
          color: theme.colorText,
          fontSize: 10,
          fontWeight: 500,
        },
        formatter: (params: EChartsLabelParams) => {
          const provider = params.name ?? "";
          const providerData = providerMap[provider];
          if (!providerData) return "";
          const colorIndex = pieData.findIndex((d) => d.name === provider);
          const color =
            colorIndex >= 0
              ? pieData[colorIndex].itemStyle.color
              : theme.colorBorder;

          const hasBreakdown =
            Object.keys(providerData.breakdown).length > 1 ||
            (Object.keys(providerData.breakdown).length === 1 &&
              !providerData.breakdown[provider]);

          let bodyHtml = "";

          if (hasBreakdown) {
            bodyHtml = Object.entries(providerData.breakdown)
              .sort(([, a], [, b]) => b - a)
              .map(
                ([cat, val]) =>
                  `<div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;font-weight:500;line-height:16px;gap:24px;margin-top:12px"><span style="display:flex;align-items:center;gap:6px;overflow:hidden"><span style="width:8px;height:8px;border-radius:1px;background:${color};display:inline-block;flex-shrink:0"></span><span style="color:${theme.colorTextSecondary};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;display:inline-block;vertical-align:middle">${cat}</span></span><span style="color:${theme.colorText};font-weight:500;white-space:nowrap;flex-shrink:0">${currencySymbol}${formatNumber(val, showDecimals)}</span></div>`,
              )
              .join("");
          } else {
            bodyHtml = `<div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;font-weight:500;line-height:16px;gap:24px;margin-top:12px"><span style="display:flex;align-items:center;gap:6px;overflow:hidden"><span style="width:8px;height:8px;border-radius:1px;background:${color};display:inline-block;flex-shrink:0"></span><span style="color:${theme.colorTextSecondary};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;display:inline-block;vertical-align:middle">${provider}</span></span><span style="color:${theme.colorText};font-weight:500;white-space:nowrap;flex-shrink:0">${currencySymbol}${formatNumber(providerData.total, showDecimals)}</span></div>`;
          }

          const totalRow =
            showTotalInTooltip && hasBreakdown
              ? `<div style="border-top:1px solid ${theme.colorBorderSecondary};margin-top:12px;padding-top:8px;display:flex;justify-content:space-between;align-items:center;font-size:10px;font-weight:500;line-height:16px;gap:24px"><span style="color:${theme.colorText};font-weight:600">Total Spend</span><span style="color:${theme.colorText};font-weight:600;white-space:nowrap">${currencySymbol}${formatNumber(providerData.total, showDecimals)}</span></div>`
              : "";

          return `<div style="font-family:${FONT.INTER};font-size:11px;font-weight:600;color:${theme.colorText};line-height:20px;padding-bottom:8px;margin-bottom:0;border-bottom:1px solid ${theme.colorBorderSecondary};overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${provider}</div>${bodyHtml}${totalRow}`;
        },
      },
      legend: {
        show: true,
        type: "scroll",
        bottom: 0,
        left: "center",
        icon: "roundRect",
        itemWidth: 9,
        itemHeight: 9,
        itemGap: 12,
        borderRadius: 2,
        textStyle: {
          fontFamily: FONT.INTER,
          fontSize: 10,
          fontWeight: 500,
          lineHeight: 16,
          color: theme.colorText,
          padding: [0, 0, 0, 4],
        },
      },
      graphic: [
        {
          type: "text",
          left: "center",
          top: "42%",
          style: {
            text: `{label|Total Spend}\n{value|${currencySymbol}${formatNumber(grandTotal, showDecimals)}}`,
            textAlign: "center",
            rich: {
              label: {
                fontFamily: FONT.INTER,
                fontSize: 10,
                fontWeight: 400,
                lineHeight: 16,
                fill: theme.colorTextSecondary,
                align: "center",
              },
              value: {
                fontFamily: FONT.INTER,
                fontSize: 11,
                fontWeight: 600,
                lineHeight: 18,
                fill: theme.colorText,
                align: "center",
              },
            },
          },
          z: 10,
        },
      ] satisfies GraphicComponentOption[],
      series: [
        {
          type: "pie",
          radius: ["35%", "60%"],
          center: ["50%", "45%"],
          avoidLabelOverlap: true,
          data: pieData,
          itemStyle: {
            borderColor: theme.colorBgContainer,
            borderWidth: 2,
            borderRadius: 2,
          },
          label: {
            show: true,
            position: "outer",
            alignTo: "none",
            bleedMargin: 5,
            opacity: 1,
            fontFamily: FONT.INTER,
            fontSize: 10,
            color: theme.colorText,
            formatter: (params: EChartsLabelParams) =>
              `{value|${currencySymbol}${formatNumber(params.value, showDecimals)}} {percent|(${params.percent}%)}\n{name|${params.name}}`,
            rich: {
              value: {
                fontFamily: FONT.INTER,
                fontWeight: 600,
                fontSize: 10,
                lineHeight: 16,
                color: theme.colorText,
              },
              percent: {
                fontFamily: FONT.INTER,
                fontWeight: 400,
                fontSize: 10,
                lineHeight: 16,
                color: theme.colorText,
              },
              name: {
                fontFamily: FONT.INTER,
                fontWeight: 500,
                fontSize: 10,
                lineHeight: 20,
                padding: [4, 0, 0, 0],
                color: theme.colorTextSecondary,
              },
            },
          },
          labelLine: {
            show: true,
            smooth: false,
            lineStyle: {
              color: theme.colorText,
              width: 1,
            },
          },
          labelLayout: {
            hideOverlap: true,
          },
          emphasis: {
            disabled: !tooltipEnabled,
            label: {
              show: true,
              fontWeight: "bold",
            },
            itemStyle: {
              shadowBlur: 10,
              shadowColor: theme.colorBorder,
            },
          },
        },
      ],
    }),
    [
      tooltipEnabled,
      showTotalInTooltip,
      showDecimals,
      currencySymbol,
      providerMap,
      pieData,
      grandTotal,
    ],
  );

  const isReady = Boolean(data && groupby && metric && formData);
  const hasData = isReady && data.length > 0;

  // Single effect: initialize, update options, and handle resize/cleanup
  useEffect(() => {
    if (!chartRef.current || !hasData) {
      // Dispose if chart exists but data is gone
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
      return undefined;
    }

    // Initialize chart if not already created
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }

    // Update chart options and resize
    chartInstance.current.setOption(buildOption(), { notMerge: true });
    chartInstance.current.resize({ width: width - 24, height: height - 32 });

    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, [buildOption, width, height, hasData]);

  if (!isReady) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: "100%",
          height: "100%",
          color: theme.colorTextTertiary,
        }}
        data-testid="custom-pie-chart"
      >
        Loading chart configuration...
      </div>
    );
  }

  if (!hasData) {
    return <NoDataScreen width="100%" height="100%" />;
  }

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        padding: "16px 12px",
        boxSizing: "border-box",
      }}
      data-testid="custom-pie-chart"
    >
      <div ref={chartRef} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}
