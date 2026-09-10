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
import { FC } from 'react';

interface IconProps {
  size?: number;
}

const svgProps = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 16 16',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
});

export const ChevronIcon: FC<IconProps & { open?: boolean }> = ({
  size = 14,
  open = false,
}) => (
  <svg
    {...svgProps(size)}
    style={{ transform: open ? 'rotate(90deg)' : 'none' }}
  >
    <path d="M6 3l5 5-5 5" />
  </svg>
);

export const SearchIcon: FC<IconProps> = ({ size = 14 }) => (
  <svg {...svgProps(size)}>
    <circle cx="7" cy="7" r="4.5" />
    <path d="M10.5 10.5L14 14" />
  </svg>
);

export const ListViewIcon: FC<IconProps> = ({ size = 14 }) => (
  <svg {...svgProps(size)}>
    <path d="M2 4h12M2 8h12M2 12h12" />
  </svg>
);

export const BarViewIcon: FC<IconProps> = ({ size = 14 }) => (
  <svg {...svgProps(size)}>
    <path d="M3 13V8M8 13V3M13 13v-7" />
  </svg>
);

export const TileViewIcon: FC<IconProps> = ({ size = 14 }) => (
  <svg {...svgProps(size)}>
    <rect x="2.5" y="2.5" width="4.5" height="4.5" />
    <rect x="9" y="2.5" width="4.5" height="4.5" />
    <rect x="2.5" y="9" width="4.5" height="4.5" />
    <rect x="9" y="9" width="4.5" height="4.5" />
  </svg>
);

export const ExpandIcon: FC<IconProps> = ({ size = 14 }) => (
  <svg {...svgProps(size)}>
    <path d="M9.5 2.5H13.5V6.5M6.5 13.5H2.5V9.5M13.5 2.5l-4.5 4.5M2.5 13.5l4.5-4.5" />
  </svg>
);

export const ColumnsIcon: FC<IconProps> = ({ size = 14 }) => (
  <svg {...svgProps(size)}>
    <rect x="2.5" y="2.5" width="11" height="11" />
    <path d="M6.5 2.5v11M10 2.5v11" />
  </svg>
);

export const SettingsIcon: FC<IconProps> = ({ size = 14 }) => (
  <svg {...svgProps(size)}>
    <path d="M2 5h8M12.5 5H14M2 11h2M6.5 11H14" />
    <circle cx="11" cy="5" r="1.5" />
    <circle cx="5" cy="11" r="1.5" />
  </svg>
);

export const SortIcon: FC<IconProps & { direction?: 'asc' | 'desc' | null }> = ({
  size = 12,
  direction = null,
}) => (
  <svg {...svgProps(size)} style={{ marginLeft: 4, verticalAlign: 'middle' }}>
    <path d="M8 3l3 3H5z" fill="currentColor" opacity={direction === 'asc' ? 1 : 0.35} />
    <path
      d="M8 13l-3-3h6z"
      fill="currentColor"
      opacity={direction === 'desc' ? 1 : 0.35}
    />
  </svg>
);

export const TriangleIcon: FC<IconProps & { up: boolean }> = ({
  size = 8,
  up,
}) => (
  <svg width={size} height={size} viewBox="0 0 8 8" aria-hidden>
    <path d={up ? 'M4 1l3 6H1z' : 'M4 7L1 1h6z'} fill="currentColor" />
  </svg>
);
