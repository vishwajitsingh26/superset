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
import { memo, useMemo } from 'react';
import { t } from '../adapters/supersetAdapter';
import {
  SPARKLINE_FILL_OPACITY,
  SPARKLINE_STROKE_WIDTH,
  SPARKLINE_VIEWBOX,
} from '../constants';
import { TrendPoint } from '../types';
import { buildSparklinePaths } from '../utils/sparkline';

export interface SparklineProps {
  points: TrendPoint[];
  color: string;
}

// Plain SVG: an axis-free area line is faster and more exact than configuring
// a charting library to look like one.
function Sparkline({ points, color }: SparklineProps) {
  const paths = useMemo(() => buildSparklinePaths(points), [points]);
  if (!paths) {
    return null;
  }
  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${SPARKLINE_VIEWBOX} ${SPARKLINE_VIEWBOX}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={t('Spend trend')}
      data-testid="spend-card-sparkline"
    >
      <path
        d={paths.area}
        fill={color}
        fillOpacity={SPARKLINE_FILL_OPACITY}
        stroke="none"
      />
      <path
        d={paths.line}
        fill="none"
        stroke={color}
        strokeWidth={SPARKLINE_STROKE_WIDTH}
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export default memo(Sparkline);
