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
import { memo, ReactElement } from 'react';
import { Button, t } from '../adapters/supersetAdapter';
import { HeaderRow, Segmented, Title } from '../ForecastLineStyles';
import { ViewMode } from '../types';

export interface ChartHeaderProps {
  title: string;
  mode: ViewMode;
  showToggle: boolean;
  onChange: (mode: ViewMode) => void;
}

const SVG_PROPS = {
  width: 14,
  height: 14,
  viewBox: '0 0 16 16',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

const LineIcon = (
  <svg {...SVG_PROPS}>
    <path d="M1 13l4-5 3 3 7-8" />
  </svg>
);

const AreaIcon = (
  <svg {...SVG_PROPS}>
    <path d="M1 13l4-5 3 3 7-8v10z" />
  </svg>
);

const ListIcon = (
  <svg {...SVG_PROPS}>
    <path d="M2 4h12M2 8h12M2 12h12" />
  </svg>
);

const MODES: { mode: ViewMode; label: string; icon: ReactElement }[] = [
  { mode: 'line', label: t('Line view'), icon: LineIcon },
  { mode: 'area', label: t('Area view'), icon: AreaIcon },
  { mode: 'list', label: t('List view'), icon: ListIcon },
];

function ChartHeader({ title, mode, showToggle, onChange }: ChartHeaderProps) {
  return (
    <HeaderRow>
      <Title title={title}>{title}</Title>
      {showToggle && (
        <Segmented>
          {MODES.map(entry => (
            <Button
              key={entry.mode}
              aria-label={entry.label}
              aria-pressed={mode === entry.mode}
              onClick={() => onChange(entry.mode)}
            >
              {entry.icon}
            </Button>
          ))}
        </Segmented>
      )}
    </HeaderRow>
  );
}

export default memo(ChartHeader);
