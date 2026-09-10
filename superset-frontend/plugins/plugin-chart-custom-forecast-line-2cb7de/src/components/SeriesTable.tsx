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
import { t } from '../adapters/supersetAdapter';
import { TableWrap } from '../ForecastLineStyles';
import { ColoredSeries } from '../types';
import { formatDayLong } from '../utils/format';

export interface SeriesTableProps {
  series: ColoredSeries[];
  categories: number[];
  money: (value: number) => string;
}

const EMPTY_CELL = '\u2014';

function SeriesTable({ series, categories, money }: SeriesTableProps) {
  return (
    <TableWrap>
      <table>
        <thead>
          <tr>
            <th>{t('Date')}</th>
            {series.map(item => (
              <th key={item.id}>{item.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((category, index) => (
            <tr key={category}>
              <td>{formatDayLong(category)}</td>
              {series.map(item => (
                <td key={item.id}>
                  {item.values[index] === null
                    ? EMPTY_CELL
                    : money(Number(item.values[index]))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

export default memo(SeriesTable);
