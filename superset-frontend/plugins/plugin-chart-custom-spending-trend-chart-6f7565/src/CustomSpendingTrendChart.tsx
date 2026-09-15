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
import { useCallback, useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { useTheme } from './adapters/supersetAdapter';
import { CustomSpendingTrendChartProps } from './types';
import { parseColors } from './utils/colors';
import { formatXAxisLabel, formatYAxisLabel } from './utils/formatters';
import { FONT } from './constants';

echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  CanvasRenderer,
]);

export default function CustomSpendingTrendChart({
  width,
  height,
  categories,
  providers,
  series,
  seriesColors,
}: CustomSpendingTrendChartProps) {
  const theme = useTheme();
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  // Design draws AWS blue, Azure purple, Google Cloud green, Oracle Cloud
  // orange -- that exact palette arrives through `seriesColors` as data.
  // This fallback is only ever seen on an unconfigured chart.
  const fallbackPalette = useMemo(
    () => [
      theme.colorPrimary,
      theme.colorInfo,
      theme.colorSuccess,
      theme.colorWarning,
    ],
    [theme],
  );
  const palette = useMemo(
    () => parseColors(seriesColors, fallbackPalette),
    [seriesColors, fallbackPalette],
  );

  const hasData = categories.length > 0 && providers.length > 0;

  const buildOption = useCallback(
    (): echarts.EChartsCoreOption => ({
      grid: { left: 48, right: 12, top: 16, bottom: 40, containLabel: false },
      tooltip: {
        trigger: 'axis',
        confine: true,
        backgroundColor: theme.colorBgContainer,
        borderColor: theme.colorBorderSecondary,
        borderWidth: 1,
        textStyle: {
          fontFamily: FONT.INTER,
          color: theme.colorText,
          fontSize: 11,
        },
        valueFormatter: (value: number | string) =>
          formatYAxisLabel(Number(value)),
      },
      xAxis: {
        type: 'category',
        data: categories,
        boundaryGap: false,
        axisLine: { lineStyle: { color: theme.colorBorderSecondary } },
        axisTick: { show: false },
        axisLabel: {
          fontFamily: FONT.INTER,
          fontSize: 11,
          color: theme.colorTextSecondary,
          formatter: (value: string) => formatXAxisLabel(value),
        },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: {
          lineStyle: { color: theme.colorBorderSecondary, type: 'solid' },
        },
        axisLabel: {
          fontFamily: FONT.INTER,
          fontSize: 11,
          color: theme.colorTextSecondary,
          formatter: (value: number) => formatYAxisLabel(value),
        },
      },
      legend: {
        show: true,
        bottom: 0,
        left: 'left',
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
        itemGap: 20,
        textStyle: {
          fontFamily: FONT.INTER,
          fontSize: 12,
          fontWeight: 500,
          color: theme.colorText,
        },
        data: providers,
      },
      series: providers.map((provider, index) => ({
        name: provider,
        type: 'line',
        stack: 'total',
        symbol: 'none',
        smooth: false,
        lineStyle: { width: 2, color: palette[index % palette.length] },
        areaStyle: { color: palette[index % palette.length], opacity: 0.55 },
        itemStyle: { color: palette[index % palette.length] },
        data: series[index] ?? [],
      })),
    }),
    [categories, providers, series, palette, theme],
  );

  useEffect(() => {
    if (!chartRef.current || !hasData) {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
      return undefined;
    }
    if (!chartInstance.current) {
      chartInstance.current = echarts.init(chartRef.current);
    }
    chartInstance.current.setOption(buildOption(), { notMerge: true });
    chartInstance.current.resize({ width, height });
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, [buildOption, width, height, hasData]);

  if (!hasData) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          height: '100%',
          color: theme.colorTextTertiary,
          fontFamily: FONT.INTER,
          fontSize: 12,
        }}
        data-testid="custom-spending-trend-chart-empty"
      >
        No spending data available
      </div>
    );
  }

  return (
    <div
      style={{ width: '100%', height: '100%' }}
      data-testid="custom-spending-trend-chart"
    >
      <div ref={chartRef} style={{ width: '100%', height: '100%' }} />
    </div>
  );
}
