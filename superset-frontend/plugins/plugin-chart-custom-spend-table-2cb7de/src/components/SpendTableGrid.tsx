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
import { SupersetThemeType, t } from '../adapters/supersetAdapter';
import { MIN_COLUMN_WIDTH } from '../constants';
import { ColumnDef, SortState, SpendNode, SpendTotals } from '../types';
import {
  footerCell,
  headCell,
  scrollArea,
  table,
} from '../SpendTableStyles';
import { CellContext } from './CellContent';
import SpendTableRow from './SpendTableRow';
import { ChevronIcon, SortIcon } from './TableIcons';

interface SpendTableGridProps {
  rows: SpendNode[];
  columns: ColumnDef[];
  totals: SpendTotals;
  showTotalRow: boolean;
  sort: SortState;
  onSort: (key: string) => void;
  expanded: ReadonlySet<string>;
  onToggle: (key: string) => void;
  ctx: CellContext;
  theme: SupersetThemeType;
}

export default function SpendTableGrid({
  rows,
  columns,
  totals,
  showTotalRow,
  sort,
  onSort,
  expanded,
  onToggle,
  ctx,
  theme,
}: SpendTableGridProps) {
  const minWidth = (columns.length + 1) * MIN_COLUMN_WIDTH;
  return (
    <div style={scrollArea}>
      <table style={{ ...table(theme), minWidth }}>
        <thead>
          <tr>
            <th style={{ ...headCell(theme, 'center'), cursor: 'default' }}>
              <ChevronIcon />
            </th>
            {columns.map(column => (
              <th
                key={column.key}
                style={headCell(theme, column.align)}
                onClick={() => onSort(column.key)}
                title={t('Sort by %s', column.label)}
              >
                {column.label}
                <SortIcon
                  direction={
                    sort.key === column.key ? (sort.desc ? 'desc' : 'asc') : null
                  }
                />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <SpendTableRow
              key={row.key}
              node={row}
              columns={columns}
              depth={0}
              expanded={expanded}
              onToggle={onToggle}
              ctx={ctx}
              theme={theme}
            />
          ))}
        </tbody>
        {showTotalRow ? (
          <tfoot>
            <tr>
              <td style={footerCell(theme, 'center')} />
              {columns.map(column => (
                <td key={column.key} style={footerCell(theme, column.align)}>
                  {column.kind === 'entity' ? t('Total') : null}
                  {column.kind === 'provider'
                    ? ctx.money(totals.values[column.key] ?? null)
                    : null}
                  {column.kind === 'spend' ? ctx.money(totals.spend) : null}
                </td>
              ))}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}
