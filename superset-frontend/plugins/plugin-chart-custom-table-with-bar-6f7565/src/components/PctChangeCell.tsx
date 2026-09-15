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

interface PctChangeCellProps {
  value: number | null;
}

// Increase = cost went up = red with an up arrow; decrease = green with a
// down arrow -- the sign convention the crop's five rows all agree on.
const PctChangeCell: React.FC<PctChangeCellProps> = ({ value }) => {
  const theme = useTheme();
  if (value === null || Number.isNaN(value)) {
    return <span style={{ color: theme.colorTextTertiary }}>—</span>;
  }
  const isUp = value >= 0;
  const color = isUp ? theme.colorError : theme.colorSuccess;
  const arrow = isUp ? '\u2191' : '\u2193';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 2,
        color,
        fontSize: 12,
        fontWeight: 500,
        whiteSpace: 'nowrap',
      }}
    >
      <span>{arrow}</span>
      <span>{Math.abs(value).toFixed(1)}%</span>
    </span>
  );
};

export default React.memo(PctChangeCell);
