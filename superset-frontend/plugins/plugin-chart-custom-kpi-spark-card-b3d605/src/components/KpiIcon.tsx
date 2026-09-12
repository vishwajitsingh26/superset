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
import { memo, ReactNode } from 'react';
import { KpiIconGlyph } from '../types';

interface KpiIconProps {
  glyph: KpiIconGlyph;
  color: string;
  size: number;
}

function Glyph({ size, children }: { size: number; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden
      focusable="false"
      style={{ display: 'block', flexShrink: 0 }}
    >
      {children}
    </svg>
  );
}

function KpiIcon({ glyph, color, size }: KpiIconProps) {
  if (glyph === 'currency') {
    return (
      <Glyph size={size}>
        <path
          d="M12 3.2v17.6M15.9 7.6A3.7 3.7 0 0 0 12.4 5.4h-.7C9.7 5.4 8.2 6.6 8.2 8.2s1.5 2.6 3.8 3.1 3.9 1.4 3.9 3.2-1.8 3.1-3.8 3.1h-.5a3.8 3.8 0 0 1-3.7-2.3"
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
        />
      </Glyph>
    );
  }
  if (glyph === 'trend') {
    return (
      <Glyph size={size}>
        <path
          d="M3.5 16.8l4.6-5.1 3.5 2.6 5.2-7.1"
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M13.6 6.6h4.1v4.1"
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </Glyph>
    );
  }
  if (glyph === 'server') {
    return (
      <Glyph size={size}>
        <rect
          x="3.5"
          y="4.5"
          width="17"
          height="6"
          rx="2"
          fill="none"
          stroke={color}
          strokeWidth={2}
        />
        <rect
          x="3.5"
          y="13.5"
          width="17"
          height="6"
          rx="2"
          fill="none"
          stroke={color}
          strokeWidth={2}
        />
        <path
          d="M7 7.5h.01M7 16.5h.01"
          stroke={color}
          strokeWidth={2}
          strokeLinecap="round"
        />
      </Glyph>
    );
  }
  // The design's glyph: a solid, filled cloud in the accent colour.
  return (
    <Glyph size={size}>
      <path
        d="M7.4 18.6h9.9a3.8 3.8 0 0 0 .4-7.57A5.85 5.85 0 0 0 6.7 9.05 4.78 4.78 0 0 0 7.4 18.6Z"
        fill={color}
      />
    </Glyph>
  );
}

export default memo(KpiIcon);
