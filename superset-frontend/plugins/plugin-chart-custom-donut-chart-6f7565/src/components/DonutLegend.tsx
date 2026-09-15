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
import { useTheme } from '../adapters/supersetAdapter';
import { DonutSliceDatum } from '../types';

interface DonutLegendProps {
  slices: DonutSliceDatum[];
  palette: string[];
}

// A plain vertical list, not the echarts legend: the design's percentage
// column beside each name has no equivalent in echarts' own legend.
export function DonutLegend({ slices, palette }: DonutLegendProps) {
  const theme = useTheme();
  return (
    <div
      style={{
        flex: '1 1 auto',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        gap: theme.sizeUnit * 2,
        paddingLeft: theme.sizeUnit * 3,
        minWidth: 0,
      }}
    >
      {slices.map((slice, index) => (
        <div
          key={slice.name}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: theme.sizeUnit * 2,
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: theme.sizeUnit,
              minWidth: 0,
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: palette[index % palette.length],
                flexShrink: 0,
                display: 'inline-block',
              }}
            />
            <span
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: theme.colorText,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {slice.name}
            </span>
          </div>
          <span
            style={{
              fontSize: 14,
              fontWeight: 500,
              color: theme.colorText,
              flexShrink: 0,
            }}
          >
            {slice.percentLabel}
          </span>
        </div>
      ))}
    </div>
  );
}
