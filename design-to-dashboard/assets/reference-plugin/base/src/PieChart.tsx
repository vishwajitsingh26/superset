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
/* eslint-disable theme-colors/no-literal-colors */
import { useCallback, useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { PieChart as PieChartType } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  GraphicComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { getCurrencySymbol } from '@superset-ui/core';
import { StableChartInput } from './adapters/supersetAdapter';
import {
  buildProviderMap,
  getTopNSlices,
  parseColors,
  formatNumber,
  FormData,
} from './utils/pieChartUtils';
import { DEFAULT_TOP_N, CHART_COLORS, FONT } from './constants';
import { NoDataScreen } from 'src/components/NoDataScreen';

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
}: StableChartInput) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  // Extract configuration from formData
  const showDecimals: boolean = (formData as any)?.showDecimals ?? false;
  const currencySymbol: string = (formData as any)?.currencyFormat
    ? getCurrencySymbol((formData as any).currencyFormat) || ''
    : '';
  const topN: number = (formData as any)?.topN ?? DEFAULT_TOP_N;
  const tooltipEnabled: boolean = (formData as any)?.tooltipEnabled ?? true;
  const showTotalInTooltip: boolean =
    (formData as any)?.showTotalInTooltip ?? true;
  const customColors: string = (formData as any)?.customColors ?? '';
  const tooltipBreakdownCol: string =
    (formData as any)?.tooltipBreakdownCol ?? '';

  const palette = useMemo(() => parseColors(customColors), [customColors]);

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
        trigger: 'item',
        confine: true,
        backgroundColor: '#FFFFFF',
        borderColor: '#F4F4F4',
        borderWidth: 1,
        borderRadius: 8,
        padding: [10, 12, 10, 12],
        extraCssText:
          'box-shadow: -4px 10.65px 21.3px -10.65px rgba(22,39,66,0.15); max-width: 220px;',
        textStyle: {
          fontFamily: FONT.INTER,
          color: '#202828',
          fontSize: 10,
          fontWeight: 500,
        },
        formatter: (params: any) => {
          const provider = params.name ?? '';
          const providerData = providerMap[provider];
          if (!providerData) return '';
          const colorIndex = pieData.findIndex(d => d.name === provider);
          const color =
            colorIndex >= 0
              ? pieData[colorIndex].itemStyle.color
              : CHART_COLORS.FALLBACK_DOT;

          const hasBreakdown =
            Object.keys(providerData.breakdown).length > 1 ||
            (Object.keys(providerData.breakdown).length === 1 &&
              !providerData.breakdown[provider]);

          let bodyHtml = '';

          if (hasBreakdown) {
            bodyHtml = Object.entries(providerData.breakdown)
              .sort(([, a], [, b]) => b - a)
              .map(
                ([cat, val]) =>
                  `<div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;font-weight:500;line-height:16px;gap:24px;margin-top:12px"><span style="display:flex;align-items:center;gap:6px;overflow:hidden"><span style="width:8px;height:8px;border-radius:1px;background:${color};display:inline-block;flex-shrink:0"></span><span style="color:#737373;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;display:inline-block;vertical-align:middle">${cat}</span></span><span style="color:#050505;font-weight:500;white-space:nowrap;flex-shrink:0">${currencySymbol}${formatNumber(val, showDecimals)}</span></div>`,
              )
              .join('');
          } else {
            bodyHtml = `<div style="display:flex;justify-content:space-between;align-items:center;font-size:10px;font-weight:500;line-height:16px;gap:24px;margin-top:12px"><span style="display:flex;align-items:center;gap:6px;overflow:hidden"><span style="width:8px;height:8px;border-radius:1px;background:${color};display:inline-block;flex-shrink:0"></span><span style="color:#737373;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px;display:inline-block;vertical-align:middle">${provider}</span></span><span style="color:#050505;font-weight:500;white-space:nowrap;flex-shrink:0">${currencySymbol}${formatNumber(providerData.total, showDecimals)}</span></div>`;
          }

          const totalRow =
            showTotalInTooltip && hasBreakdown
              ? `<div style="border-top:1px solid #F4F4F4;margin-top:12px;padding-top:8px;display:flex;justify-content:space-between;align-items:center;font-size:10px;font-weight:500;line-height:16px;gap:24px"><span style="color:#050505;font-weight:600">Total Spend</span><span style="color:#050505;font-weight:600;white-space:nowrap">${currencySymbol}${formatNumber(providerData.total, showDecimals)}</span></div>`
              : '';

          return `<div style="font-family:${FONT.INTER};font-size:11px;font-weight:600;color:#202828;line-height:20px;padding-bottom:8px;margin-bottom:0;border-bottom:1px solid #F4F4F4;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${provider}</div>${bodyHtml}${totalRow}`;
        },
      },
      legend: {
        show: true,
        type: 'scroll',
        bottom: 0,
        left: 'center',
        icon: 'roundRect',
        itemWidth: 9,
        itemHeight: 9,
        itemGap: 12,
        borderRadius: 2,
        textStyle: {
          fontFamily: FONT.INTER,
          fontSize: 10,
          fontWeight: 500,
          lineHeight: 16,
          color: '#2B2B2B',
          padding: [0, 0, 0, 4],
        },
      },
      graphic: [
        {
          type: 'text',
          left: 'center',
          top: '42%',
          style: {
            text: `{label|Total Spend}\n{value|${currencySymbol}${formatNumber(grandTotal, showDecimals)}}`,
            textAlign: 'center',
            rich: {
              label: {
                fontFamily: FONT.INTER,
                fontSize: 10,
                fontWeight: 400,
                lineHeight: 16,
                fill: CHART_COLORS.TOTAL_LABEL,
                align: 'center',
              },
              value: {
                fontFamily: FONT.INTER,
                fontSize: 11,
                fontWeight: 600,
                lineHeight: 18,
                fill: CHART_COLORS.TOTAL_VALUE,
                align: 'center',
              },
            },
          },
          z: 10,
        },
      ] as any,
      series: [
        {
          type: 'pie',
          radius: ['35%', '60%'],
          center: ['50%', '45%'],
          avoidLabelOverlap: true,
          data: pieData,
          itemStyle: {
            borderColor: '#FFFFFF',
            borderWidth: 2,
            borderRadius: 2,
          },
          label: {
            show: true,
            position: 'outer',
            alignTo: 'none',
            bleedMargin: 5,
            opacity: 1,
            fontFamily: FONT.INTER,
            fontSize: 10,
            color: CHART_COLORS.LABEL_PRIMARY,
            formatter: (params: any) =>
              `{value|${currencySymbol}${formatNumber(params.value, showDecimals)}} {percent|(${params.percent}%)}\n{name|${params.name}}`,
            rich: {
              value: {
                fontFamily: FONT.INTER,
                fontWeight: 600,
                fontSize: 10,
                lineHeight: 16,
                color: '#050505',
              },
              percent: {
                fontFamily: FONT.INTER,
                fontWeight: 400,
                fontSize: 10,
                lineHeight: 16,
                color: '#050505',
              },
              name: {
                fontFamily: FONT.INTER,
                fontWeight: 500,
                fontSize: 10,
                lineHeight: 20,
                padding: [4, 0, 0, 0],
                color: '#737373',
              },
            },
          },
          labelLine: {
            show: true,
            smooth: false,
            lineStyle: {
              color: CHART_COLORS.LABEL_PRIMARY,
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
              fontWeight: 'bold',
            },
            itemStyle: {
              shadowBlur: 10,
              shadowColor: 'rgba(0, 0, 0, 0.1)',
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
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          height: '100%',
          color: '#999',
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
        width: '100%',
        height: '100%',
        padding: '16px 12px',
        boxSizing: 'border-box',
      }}
      data-testid="custom-pie-chart"
    >
      <div ref={chartRef} style={{ width: '100%', height: '100%' }} />
    </div>
  );
}
