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
import type * as echarts from 'echarts/core';
import { DonutSliceDatum } from '../types';

// The design's exact hexes arrive as data through the `sliceColors` control
// (stage D writes them into saved params); the fallback is theme tokens, so
// an unconfigured chart still follows light and dark.
export function parseSliceColors(
  input: string | undefined,
  fallback: string[],
): string[] {
  if (!input || !input.trim()) return [...fallback];
  const parsed = input
    .split(',')
    .map(color => color.trim())
    .filter(color => /^#[0-9A-Fa-f]{3,8}$/.test(color));
  return parsed.length > 0 ? parsed : [...fallback];
}

interface DonutThemeTokens {
  colorBgContainer: string;
  colorBorderSecondary: string;
  colorText: string;
}

interface DonutTooltipParams {
  name?: string;
}

export function buildDonutOption(
  slices: DonutSliceDatum[],
  palette: string[],
  theme: DonutThemeTokens,
  tooltipEnabled: boolean,
): echarts.EChartsCoreOption {
  const byName = new Map(slices.map(slice => [slice.name, slice]));
  return {
    tooltip: {
      show: tooltipEnabled,
      trigger: 'item',
      confine: true,
      backgroundColor: theme.colorBgContainer,
      borderColor: theme.colorBorderSecondary,
      borderWidth: 1,
      textStyle: { color: theme.colorText, fontSize: 12 },
      formatter: (params: DonutTooltipParams) => {
        const slice = byName.get(params.name ?? '');
        return slice
          ? `${slice.name}: ${slice.valueLabel} (${slice.percentLabel})`
          : '';
      },
    },
    series: [
      {
        type: 'pie',
        radius: ['58%', '90%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: false,
        silent: !tooltipEnabled,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: {
          borderColor: theme.colorBgContainer,
          borderWidth: 2,
        },
        data: slices.map((slice, index) => ({
          name: slice.name,
          value: slice.value,
          itemStyle: { color: palette[index % palette.length] },
        })),
      },
    ],
  };
}
