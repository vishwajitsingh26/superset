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
import { memo, useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

// Only the modules this chart draws with, so the bundle stays small.
echarts.use([
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

export interface EChartsPanelProps {
  option: echarts.EChartsCoreOption;
  width: number;
  height: number;
}

function EChartsPanel({ option, width, height }: EChartsPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<echarts.ECharts | null>(null);
  const style = useMemo(() => ({ width, height }), [width, height]);

  useEffect(() => {
    if (!containerRef.current) return;
    if (!instanceRef.current) {
      instanceRef.current = echarts.init(containerRef.current);
    }
    instanceRef.current.setOption(option, { notMerge: true });
  }, [option]);

  useEffect(() => {
    instanceRef.current?.resize({ width, height });
  }, [width, height]);

  useEffect(
    () => () => {
      instanceRef.current?.dispose();
      instanceRef.current = null;
    },
    [],
  );

  return <div ref={containerRef} style={style} />;
}

export default memo(EChartsPanel);
