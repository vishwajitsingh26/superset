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
import { useMemo } from 'react';
import { useTheme } from './adapters/supersetAdapter';
import { CustomKpiCardProps } from './types';
import KpiIcon from './components/KpiIcon';
import Sparkline from './components/Sparkline';
import { formatKpiValue } from './utils/formatKpiValue';
import { CARD_PADDING } from './utils/constants';

export default function CustomKpiCard(props: CustomKpiCardProps) {
  const {
    width,
    height,
    label,
    icon,
    accentColor,
    valueFormat,
    comparisonSuffix,
    value,
    deltaPercent,
    sparkline,
  } = props;
  const theme = useTheme();

  const tint = accentColor || theme.colorPrimary;
  const isDown = (deltaPercent ?? 0) < 0;
  const deltaColor =
    deltaPercent === null
      ? theme.colorTextSecondary
      : isDown
        ? theme.colorSuccess
        : theme.colorError;

  const formattedValue = useMemo(
    () => (value === null ? '\u2014' : formatKpiValue(value, valueFormat)),
    [value, valueFormat],
  );

  const sparklineWidth = Math.max(0, width - CARD_PADDING * 2) * 0.56;
  const sparklineHeight = Math.max(0, height - CARD_PADDING * 2) * 0.42;

  const isEmpty = value === null && sparkline.length === 0;

  if (isEmpty) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          height: '100%',
          color: theme.colorTextTertiary,
          fontSize: 12,
        }}
        data-testid="custom-kpi-card"
      >
        No data
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}
      data-testid="custom-kpi-card"
    >
      {/* Decorative tint wash -- the design's own per-card accent, not a duplicate of the dashboard-wide card border/shadow/radius drawn by the chart holder. */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundColor: tint,
          opacity: 0.1,
        }}
      />
      <div
        style={{
          position: 'absolute',
          right: 0,
          bottom: 0,
          width: sparklineWidth,
          height: sparklineHeight,
        }}
      >
        <Sparkline
          points={sparkline}
          width={sparklineWidth}
          height={sparklineHeight}
          color={tint}
        />
      </div>
      <div
        style={{
          position: 'relative',
          padding: CARD_PADDING,
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <KpiIcon name={icon} color={tint} size={16} />
          <span
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: theme.colorText,
              lineHeight: '20px',
            }}
          >
            {label}
          </span>
        </div>
        <div
          style={{
            fontSize: 28,
            fontWeight: 700,
            color: theme.colorText,
            lineHeight: '36px',
            marginTop: 8,
          }}
        >
          {formattedValue}
        </div>
        {deltaPercent !== null && (
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 4,
              marginTop: 8,
            }}
          >
            <span style={{ fontSize: 14, fontWeight: 600, color: deltaColor }}>
              {isDown ? '\u2193' : '\u2191'} {Math.abs(deltaPercent).toFixed(1)}
              %
            </span>
          </div>
        )}
        <div
          style={{
            fontSize: 12,
            fontWeight: 400,
            color: theme.colorTextSecondary,
            marginTop: 2,
          }}
        >
          {comparisonSuffix}
        </div>
      </div>
    </div>
  );
}
