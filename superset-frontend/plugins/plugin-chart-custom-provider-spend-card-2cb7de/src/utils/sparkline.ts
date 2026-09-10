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
import {
  SPARKLINE_VERTICAL_PADDING,
  SPARKLINE_VIEWBOX,
} from '../constants';
import { TrendPoint } from '../types';

export interface SparklinePaths {
  line: string;
  area: string;
}

export function buildSparklinePaths(
  points: TrendPoint[],
): SparklinePaths | null {
  if (points.length < 2) {
    return null;
  }
  const size = SPARKLINE_VIEWBOX;
  const pad = size * SPARKLINE_VERTICAL_PADDING;
  const values = points.map(point => point.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const usable = size - pad * 2;
  const coords = values.map((value, index) => {
    const x = (index / (values.length - 1)) * size;
    const y = size - pad - ((value - min) / span) * usable;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const line = `M${coords.join('L')}`;
  const area = `${line}L${size},${size}L0,${size}Z`;
  return { line, area };
}
