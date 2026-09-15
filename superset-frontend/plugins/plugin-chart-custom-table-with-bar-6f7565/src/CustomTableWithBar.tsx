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
import React from 'react';
import { useTheme } from './adapters/supersetAdapter';
import BarCell from './components/BarCell';
import PctChangeCell from './components/PctChangeCell';
import { CustomTableWithBarProps } from './types';
import { COLUMN_WIDTHS } from './constants';

const cellBase: React.CSSProperties = {
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

// Superset draws this region's own card and "Spend by Account" title
// (chrome.title is "plain"); this component fills the space it is given
// with the header row and body rows only, no outer border or radius.
const CustomTableWithBar: React.FC<CustomTableWithBarProps> = ({
  width,
  height,
  rows,
  dimensionLabel,
  totalSpendLabel,
  pctChangeLabel,
  barColor,
}) => {
  const theme = useTheme();

  if (rows.length === 0) {
    return (
      <div
        style={{
          width,
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: theme.colorTextTertiary,
          fontSize: 13,
        }}
        data-testid="custom-table-with-bar"
      >
        No data
      </div>
    );
  }

  return (
    <div
      style={{
        width,
        height,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}
      data-testid="custom-table-with-bar"
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          padding: '10px 16px',
          background: theme.colorFillAlter,
          borderBottom: `1px solid ${theme.colorBorderSecondary}`,
          flexShrink: 0,
        }}
      >
        <span
          style={{
            ...cellBase,
            flexBasis: `${COLUMN_WIDTHS.dimension}%`,
            fontSize: 12,
            fontWeight: 500,
            color: theme.colorTextSecondary,
          }}
        >
          {dimensionLabel}
        </span>
        <span
          style={{
            ...cellBase,
            flexBasis: `${COLUMN_WIDTHS.metric}%`,
            fontSize: 12,
            fontWeight: 500,
            color: theme.colorTextSecondary,
          }}
        >
          {totalSpendLabel}
        </span>
        <span
          style={{
            ...cellBase,
            flexBasis: `${COLUMN_WIDTHS.change}%`,
            fontSize: 12,
            fontWeight: 500,
            color: theme.colorTextSecondary,
          }}
        >
          {pctChangeLabel ?? ''}
        </span>
        {/* Rightmost column header is intentionally blank -- the design's own
            unusual treatment: a bar, and nothing named above it. */}
        <span style={{ flexBasis: `${COLUMN_WIDTHS.bar}%` }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
        {rows.map((row, index) => (
          <div
            key={`${row.accountName}-${index}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '0 16px',
              flex: 1,
              borderBottom:
                index === rows.length - 1
                  ? 'none'
                  : `1px solid ${theme.colorBorderSecondary}`,
            }}
          >
            <span
              style={{
                ...cellBase,
                flexBasis: `${COLUMN_WIDTHS.dimension}%`,
                fontSize: 13,
                fontWeight: 500,
                color: theme.colorText,
              }}
            >
              {row.accountName}
            </span>
            <span
              style={{
                ...cellBase,
                flexBasis: `${COLUMN_WIDTHS.metric}%`,
                fontSize: 13,
                fontWeight: 600,
                color: theme.colorText,
              }}
            >
              {row.totalSpendDisplay}
            </span>
            <span style={{ flexBasis: `${COLUMN_WIDTHS.change}%` }}>
              <PctChangeCell value={row.pctChange} />
            </span>
            <span style={{ flexBasis: `${COLUMN_WIDTHS.bar}%`, paddingRight: 8 }}>
              <BarCell pct={row.barPct} barColor={barColor} />
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default React.memo(CustomTableWithBar);
