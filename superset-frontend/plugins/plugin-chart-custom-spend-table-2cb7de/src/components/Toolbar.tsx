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
import { ChangeEvent } from 'react';
import {
  Dropdown,
  Input,
  SupersetThemeType,
  t,
} from '../adapters/supersetAdapter';
import { ColumnDef } from '../types';
import { outlinedIconButton, toolbar } from '../SpendTableStyles';
import { ColumnsIcon, SearchIcon, SettingsIcon } from './TableIcons';

interface ToolbarProps {
  query: string;
  onQueryChange: (value: string) => void;
  showSearch: boolean;
  columns: ColumnDef[];
  hiddenColumns: ReadonlySet<string>;
  onToggleColumn: (key: string) => void;
  showTotalRow: boolean;
  onToggleTotalRow: () => void;
  onCollapseAll: () => void;
  theme: SupersetThemeType;
}

const tick = (on: boolean): string => (on ? '\u2713 ' : '\u2003');

export default function Toolbar({
  query,
  onQueryChange,
  showSearch,
  columns,
  hiddenColumns,
  onToggleColumn,
  showTotalRow,
  onToggleTotalRow,
  onCollapseAll,
  theme,
}: ToolbarProps) {
  const columnItems = columns.map(column => ({
    key: column.key,
    label: `${tick(!hiddenColumns.has(column.key))}${column.label}`,
  }));
  const settingsItems = [
    { key: 'total', label: `${tick(showTotalRow)}${t('Total row')}` },
    { key: 'collapse', label: `${tick(false)}${t('Collapse all rows')}` },
  ];
  return (
    <div style={toolbar}>
      {showSearch ? (
        <Input
          value={query}
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            onQueryChange(event.target.value)
          }
          placeholder={t('Search')}
          prefix={<SearchIcon />}
          allowClear
          style={{ maxWidth: theme.sizeUnit * 60, borderRadius: 999 }}
        />
      ) : (
        <span />
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Dropdown
          trigger={['click']}
          menu={{
            items: columnItems,
            selectable: false,
            onClick: ({ key }: { key: string }) => onToggleColumn(key),
          }}
        >
          <button
            type="button"
            style={outlinedIconButton(theme)}
            aria-label={t('Choose columns')}
          >
            <ColumnsIcon />
          </button>
        </Dropdown>
        <Dropdown
          trigger={['click']}
          menu={{
            items: settingsItems,
            selectable: false,
            onClick: ({ key }: { key: string }) =>
              key === 'total' ? onToggleTotalRow() : onCollapseAll(),
          }}
        >
          <button
            type="button"
            style={outlinedIconButton(theme)}
            aria-label={t('Table settings')}
          >
            <SettingsIcon />
          </button>
        </Dropdown>
      </div>
    </div>
  );
}
