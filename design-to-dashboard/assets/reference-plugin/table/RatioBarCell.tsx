/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements. See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership. The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License. You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

import React from 'react';
import type { RatioBarColorRule } from '../../types';

/** Generate a light tint of the bar color for the track background. */
function ratioBarTrackTint(hex: string): string {
  const h = hex.replace(/^#/, '');
  const full =
    h.length === 3
      ? h
          .split('')
          .map(c => c + c)
          .join('')
      : h;
  if (full.length !== 6 || /[^0-9a-fA-F]/.test(full)) {
    return '#EEEEEE';
  }
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  // Blend 88% toward white for a soft track background.
  const mix = (c: number) => Math.round(c + (255 - c) * 0.88);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
}

interface RatioBarCellProps {
  ratioBarPct: number | undefined | null;
  ratioNumerator?: number;
  ratioDenominator?: number;
  colorRules: RatioBarColorRule[];
}

const RatioBarCell: React.FC<RatioBarCellProps> = ({
  ratioBarPct,
  ratioNumerator,
  ratioDenominator,
  colorRules,
}) => {
  if (ratioBarPct === undefined || ratioBarPct === null) {
    return <span style={{ color: '#bfbfbf' }}>—</span>;
  }

  // Label depends on mode:
  //  - Two-column (denominator set): "{numerator}/{denominator}"
  //  - Single-column: "{percentage}%"
  const isFractionMode =
    ratioDenominator !== undefined && ratioDenominator !== null;
  const barLabel = isFractionMode
    ? `${Math.round(ratioNumerator ?? 0)}/${Math.round(ratioDenominator ?? 0)}`
    : `${Math.round(ratioBarPct)}%`;

  const matchedRule = colorRules.find(
    rule => ratioBarPct >= rule.min && ratioBarPct <= rule.max,
  );
  const barColor = matchedRule?.color ?? '#249C45';
  const trackColor = ratioBarTrackTint(barColor);

  return (
    <span
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        width: '100%',
      }}
    >
      <span
        style={{
          width: 75,
          height: 5,
          borderRadius: 3,
          background: trackColor,
          overflow: 'hidden',
          flexShrink: 0,
        }}
      >
        <span
          style={{
            display: 'block',
            height: '100%',
            width: `${Math.min(100, Math.max(0, ratioBarPct))}%`,
            borderRadius: 3,
            background: barColor,
          }}
        />
      </span>
      <span
        style={{
          fontFamily: 'Inter, sans-serif',
          fontWeight: 400,
          fontSize: 11,
          lineHeight: '14px',
          letterSpacing: 0,
          color: '#2B2B2B',
          whiteSpace: 'nowrap',
        }}
      >
        {barLabel}
      </span>
    </span>
  );
};

export default RatioBarCell;
