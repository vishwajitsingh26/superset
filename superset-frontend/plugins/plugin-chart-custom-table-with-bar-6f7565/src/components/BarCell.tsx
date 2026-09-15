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
import { useTheme } from '../adapters/supersetAdapter';
import { tintColor } from '../utils/colorTint';

interface BarCellProps {
  pct: number;
  barColor?: string;
}

// The unlabeled 4th column: a proportional bar and nothing else -- no
// numeric text, matching the design's own unusual treatment of this column.
const BarCell: React.FC<BarCellProps> = ({ pct, barColor }) => {
  const theme = useTheme();
  const fill =
    barColor && barColor.trim() ? barColor.trim() : theme.colorPrimary;
  const track = tintColor(fill, theme.colorBorderSecondary);
  const clamped = Math.min(100, Math.max(0, pct));

  return (
    <span
      style={{
        display: 'block',
        width: '100%',
        height: 8,
        borderRadius: 4,
        background: track,
        overflow: 'hidden',
      }}
    >
      <span
        style={{
          display: 'block',
          height: '100%',
          width: `${clamped}%`,
          borderRadius: 4,
          background: fill,
        }}
      />
    </span>
  );
};

export default React.memo(BarCell);
