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
import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { PieChart as EChartsPie } from 'echarts/charts';
import { TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { t, useTheme } from './adapters/supersetAdapter';
import { CustomDonutChartProps } from './types';
import { parseSliceColors, buildDonutOption } from './utils/donutChartUtils';
import { DonutLegend } from './components/DonutLegend';

echarts.use([EChartsPie, TooltipComponent, CanvasRenderer]);

// The donut occupies the left share of the card; the legend list fills the
// rest. Ratio approximated from the crop, not a design-system value.
const DONUT_AREA_RATIO = 0.48;

export default function CustomDonutChart({
  width,
  height,
  slices,
  totalLabel,
  centerLabel,
  sliceColors,
  tooltipEnabled,
}: CustomDonutChartProps) {
  const theme = useTheme();
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);

  const palette = useMemo(
    () =>
      parseSliceColors(sliceColors, [
        theme.colorPrimary,
        theme.colorInfo,
        theme.colorSuccess,
        theme.colorWarning,
        theme.colorError,
        theme.colorTextTertiary,
      ]),
    [sliceColors, theme],
  );

  const option = useMemo(
    () => buildDonutOption(slices, palette, theme, tooltipEnabled),
    [slices, palette, theme, tooltipEnabled],
  );

  const hasData = slices.length > 0;
  const donutWidth = Math.max(0, width * DONUT_AREA_RATIO);

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
    chartInstance.current.setOption(option, { notMerge: true });
    chartInstance.current.resize({ width: donutWidth, height });
    return () => {
      if (chartInstance.current) {
        chartInstance.current.dispose();
        chartInstance.current = null;
      }
    };
  }, [option, donutWidth, height, hasData]);

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
        }}
        data-testid="custom-donut-chart"
      >
        {t('No data')}
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        width: '100%',
        height: '100%',
        alignItems: 'center',
      }}
      data-testid="custom-donut-chart"
    >
      <div
        style={{
          position: 'relative',
          width: donutWidth,
          height: '100%',
          flexShrink: 0,
        }}
      >
        <div ref={chartRef} style={{ width: '100%', height: '100%' }} />
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            textAlign: 'center',
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              fontSize: 28,
              fontWeight: 700,
              lineHeight: '32px',
              color: theme.colorText,
            }}
          >
            {totalLabel}
          </div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 400,
              lineHeight: '16px',
              color: theme.colorTextSecondary,
            }}
          >
            {centerLabel}
          </div>
        </div>
      </div>
      <DonutLegend slices={slices} palette={palette} />
    </div>
  );
}
