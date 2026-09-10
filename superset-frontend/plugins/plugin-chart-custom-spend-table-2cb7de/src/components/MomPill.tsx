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
import { memo } from 'react';
import { useTheme } from '../adapters/supersetAdapter';
import { MISSING } from '../constants';
import { NullableNumber } from '../types';
import { formatSignedPercent } from '../utils/format';
import { pill } from '../SpendTableStyles';
import { TriangleIcon } from './TableIcons';

interface MomPillProps {
  value: NullableNumber;
}

function MomPill({ value }: MomPillProps) {
  const theme = useTheme();
  if (value === null || !Number.isFinite(value)) {
    return <span>{MISSING}</span>;
  }
  const up = value >= 0;
  const color = up ? theme.colorSuccess : theme.colorError;
  const background = up ? theme.colorSuccessBg : theme.colorErrorBg;
  return (
    <span style={pill(color, background, theme)}>
      <TriangleIcon up={up} />
      {formatSignedPercent(value)}
    </span>
  );
}

export default memo(MomPill);
