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
import { memo, useMemo, useRef } from 'react';
import { SparkPoint } from '../types';

interface SparklineProps {
  points: SparkPoint[];
  width: number;
  height: number;
  color: string;
  label: string;
}

// The gradient needs a document-unique id and React 17 has no `useId`.
let gradientSequence = 0;

const STROKE = 2;
const FILL_OPACITY = 0.28;

function Sparkline({ points, width, height, color, label }: SparklineProps) {
  const idRef = useRef<string | null>(null);
  if (idRef.current === null) {
    gradientSequence += 1;
    idRef.current = `ck-spark-gradient-${gradientSequence}`;
  }
  const gradientId = idRef.current;

  const paths = useMemo(() => {
    if (points.length < 2) return { line: '', area: '' };
    const pad = STROKE;
    const innerWidth = Math.max(width - pad * 2, 1);
    const innerHeight = Math.max(height - pad * 2, 1);
    const coords = points.map(point => ({
      x: pad + point.x * innerWidth,
      y: pad + (1 - point.y) * innerHeight,
    }));
    const line = coords
      .map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x.toFixed(2)},${c.y.toFixed(2)}`)
      .join(' ');
    const first = coords[0];
    const last = coords[coords.length - 1];
    const area = `${line} L${last.x.toFixed(2)},${height} L${first.x.toFixed(2)},${height} Z`;
    return { line, area };
  }, [points, width, height]);

  if (!paths.line) return null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label}
      focusable="false"
      style={{ display: 'block' }}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={FILL_OPACITY} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={paths.area} fill={`url(#${gradientId})`} />
      <path
        d={paths.line}
        fill="none"
        stroke={color}
        strokeWidth={STROKE}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default memo(Sparkline);
