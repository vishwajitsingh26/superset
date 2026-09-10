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
import { memo, useMemo } from 'react';
import { t, useTheme } from './adapters/supersetAdapter';
import { RankedBarListProps } from './types';
import {
  BarFill,
  BarLine,
  BarRow,
  BarTrack,
  Card,
  CardTitle,
  CategoryLabel,
  StateMessage,
  ValueCell,
} from './RankedBarListStyles';

function RankedBarList(props: RankedBarListProps) {
  const { width, height, title, items, maxValue, barColor, error } = props;
  const theme = useTheme();
  const fillColor = barColor.length > 0 ? barColor : theme.colorPrimary;

  const rows = useMemo(
    () =>
      items.map(item => ({
        ...item,
        ratio: maxValue > 0 ? item.value / maxValue : 0,
      })),
    [items, maxValue],
  );

  return (
    <Card width={width} height={height} data-testid="custom-ranked-bar-list">
      {title.length > 0 ? <CardTitle>{title}</CardTitle> : null}
      {error !== null ? <StateMessage>{error}</StateMessage> : null}
      {error === null && rows.length === 0 ? (
        <StateMessage>{t('No data')}</StateMessage>
      ) : null}
      {error === null
        ? rows.map(row => (
            <BarRow key={row.label}>
              <CategoryLabel title={row.label}>{row.label}</CategoryLabel>
              <BarLine>
                <BarTrack>
                  <BarFill ratio={row.ratio} fill={fillColor} />
                </BarTrack>
                <ValueCell>{row.formatted}</ValueCell>
              </BarLine>
            </BarRow>
          ))
        : null}
    </Card>
  );
}

export default memo(RankedBarList);
