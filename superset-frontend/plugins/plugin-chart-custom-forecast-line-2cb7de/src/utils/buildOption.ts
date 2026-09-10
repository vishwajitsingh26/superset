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
import { EChartsCoreOption } from 'echarts/core';
import { FONT_STACK, FORECAST_DASH } from '../constants';
import { ColoredSeries, ViewMode } from '../types';
import { formatAxis, formatDayAxis } from './format';

export interface OptionColors {
  text: string;
  muted: string;
  line: string;
  card: string;
  border: string;
}

export interface OptionInput {
  series: ColoredSeries[];
  categories: number[];
  dividerIndex: number;
  mode: ViewMode;
  showLegend: boolean;
  showScrollbar: boolean;
  showDivider: boolean;
  colors: OptionColors;
  tooltipFormatter: (params: unknown) => string;
}

const DASHED_ICON = 'path://M0,5 L7,5 M11,5 L18,5 M22,5 L29,5';

export default function buildOption(input: OptionInput): EChartsCoreOption {
  const { series, categories, dividerIndex, mode, colors } = input;
  const axisLabel = {
    color: colors.muted,
    fontFamily: FONT_STACK,
    fontSize: 11,
    lineHeight: 14,
  };

  return {
    animation: false,
    grid: {
      left: 8,
      right: 16,
      top: 16,
      bottom: input.showLegend ? 64 : 32,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: colors.card,
      borderColor: colors.border,
      borderWidth: 1,
      borderRadius: 8,
      padding: 12,
      extraCssText: 'min-width: 200px;',
      textStyle: { fontFamily: FONT_STACK, color: colors.text, fontSize: 11 },
      axisPointer: { type: 'line', lineStyle: { color: colors.line, width: 1 } },
      formatter: input.tooltipFormatter,
    },
    legend: {
      show: input.showLegend,
      bottom: input.showScrollbar ? 16 : 0,
      left: 'center',
      itemGap: 16,
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { fontFamily: FONT_STACK, fontSize: 11, color: colors.muted },
      data: series.map(item => ({
        name: item.name,
        icon: item.forecast ? DASHED_ICON : 'roundRect',
      })),
    },
    xAxis: {
      type: 'category',
      data: categories,
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: colors.line } },
      axisLabel: {
        ...axisLabel,
        formatter: (value: string) => formatDayAxis(Number(value)),
      },
    },
    yAxis: {
      type: 'value',
      splitNumber: 5,
      axisLine: { show: false },
      splitLine: { lineStyle: { color: colors.line } },
      axisLabel: { ...axisLabel, formatter: (value: number) => formatAxis(value) },
    },
    dataZoom: input.showScrollbar
      ? [
          { type: 'inside', filterMode: 'none' },
          {
            type: 'slider',
            height: 6,
            bottom: 0,
            handleSize: 0,
            showDetail: false,
            filterMode: 'none',
            borderColor: 'transparent',
            backgroundColor: 'transparent',
            fillerColor: colors.line,
          },
        ]
      : [],
    series: series.map((item, index) => ({
      id: item.id,
      name: item.name,
      type: 'line',
      data: item.values,
      connectNulls: false,
      showSymbol: mode === 'line',
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: {
        width: 2,
        color: item.color,
        type: item.forecast ? FORECAST_DASH : 'solid',
      },
      itemStyle: { color: item.color },
      areaStyle:
        mode === 'area' ? { color: item.color, opacity: 0.12 } : undefined,
      markLine:
        index === 0 && input.showDivider && dividerIndex >= 0
          ? {
              silent: true,
              symbol: 'none',
              label: { show: false },
              lineStyle: { type: 'dashed', color: colors.muted, width: 1 },
              data: [{ xAxis: dividerIndex }],
            }
          : undefined,
    })),
  };
}
