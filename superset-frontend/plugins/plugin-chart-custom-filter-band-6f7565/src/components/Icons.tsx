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
// The region's `controls[].icon` text is the only spec for these glyphs, so
// they are drawn here as plain outline paths rather than picked from a stock
// icon set that might not have a matching entry. `currentColor` lets the
// caller set colour through CSS (a theme token), never a literal here.
import { CSSProperties } from 'react';

interface IconProps {
  size?: number;
  style?: CSSProperties;
}

function svgProps(size: number) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none' as const,
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  };
}

// cloud outline
export function CloudIcon({ size = 16, style }: IconProps) {
  return (
    <svg {...svgProps(size)} style={style} aria-hidden="true">
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z" />
    </svg>
  );
}

// people outline
export function PeopleIcon({ size = 16, style }: IconProps) {
  return (
    <svg {...svgProps(size)} style={style} aria-hidden="true">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

// map-pin outline
export function PinIcon({ size = 16, style }: IconProps) {
  return (
    <svg {...svgProps(size)} style={style} aria-hidden="true">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 1 1 18 0z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

// stacked layers outline
export function LayersIcon({ size = 16, style }: IconProps) {
  return (
    <svg {...svgProps(size)} style={style} aria-hidden="true">
      <polygon points="12 2 2 7 12 12 22 7 12 2" />
      <polyline points="2 17 12 22 22 17" />
      <polyline points="2 12 12 17 22 12" />
    </svg>
  );
}

export function ChevronDownIcon({ size = 14, style }: IconProps) {
  return (
    <svg {...svgProps(size)} style={style} aria-hidden="true">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}
