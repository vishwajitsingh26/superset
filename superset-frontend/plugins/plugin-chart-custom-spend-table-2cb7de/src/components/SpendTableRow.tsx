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
import { Fragment, memo } from 'react';
import { SupersetThemeType, t } from '../adapters/supersetAdapter';
import { ColumnDef, SpendNode } from '../types';
import { bodyCell, iconButton } from '../SpendTableStyles';
import cellContent, { CellContext } from './CellContent';
import { ChevronIcon } from './TableIcons';

interface SpendTableRowProps {
  node: SpendNode;
  columns: ColumnDef[];
  depth: number;
  expanded: ReadonlySet<string>;
  onToggle: (key: string) => void;
  ctx: CellContext;
  theme: SupersetThemeType;
}

function SpendTableRow({
  node,
  columns,
  depth,
  expanded,
  onToggle,
  ctx,
  theme,
}: SpendTableRowProps) {
  const isOpen = expanded.has(node.key);
  const hasChildren = node.children.length > 0;
  return (
    <Fragment>
      <tr>
        <td style={bodyCell(theme, 'center')}>
          {hasChildren ? (
            <button
              type="button"
              style={iconButton(theme)}
              onClick={() => onToggle(node.key)}
              aria-label={isOpen ? t('Collapse row') : t('Expand row')}
              aria-expanded={isOpen}
            >
              <ChevronIcon open={isOpen} />
            </button>
          ) : null}
        </td>
        {columns.map(column => (
          <td
            key={column.key}
            style={bodyCell(
              theme,
              column.align,
              column.kind === 'entity' ? depth : 0,
            )}
          >
            {cellContent(column, node, ctx)}
          </td>
        ))}
      </tr>
      {isOpen
        ? node.children.map(child => (
            <SpendTableRow
              key={child.key}
              node={child}
              columns={columns}
              depth={depth + 1}
              expanded={expanded}
              onToggle={onToggle}
              ctx={ctx}
              theme={theme}
            />
          ))
        : null}
    </Fragment>
  );
}

export default memo(SpendTableRow);
