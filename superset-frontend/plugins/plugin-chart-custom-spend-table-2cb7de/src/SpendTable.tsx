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
import { useCallback, useMemo, useState } from 'react';
import { t, useTheme } from './adapters/supersetAdapter';
import {
  ENTITY_KEY,
  MOM_KEY,
  PCT_KEY,
  SPEND_KEY,
  TREND_KEY,
} from './constants';
import { ColumnDef, SortState, SpendTableProps } from './types';
import { card, message } from './SpendTableStyles';
import { makeValueFormatter } from './utils/format';
import { filterRows, sortRows } from './utils/rowsView';
import CardHeader from './components/CardHeader';
import SpendTableGrid from './components/SpendTableGrid';
import Toolbar from './components/Toolbar';

export default function SpendTable(props: SpendTableProps) {
  const {
    rows,
    totals,
    providers,
    entityLabel,
    spendLabel,
    cardTitle,
    valueFormat,
    currency,
    accentColor,
    hasMom,
    hasTrend,
    showPercentOfTotal,
    showTotalRow,
    showSearch,
    hasQuery,
  } = props;
  const theme = useTheme();
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState<SortState>({ key: SPEND_KEY, desc: true });
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [totalsVisible, setTotalsVisible] = useState(showTotalRow);
  const [fullscreen, setFullscreen] = useState(false);

  const allColumns = useMemo<ColumnDef[]>(() => {
    const defs: ColumnDef[] = [
      { key: ENTITY_KEY, label: entityLabel, kind: 'entity', align: 'left' },
    ];
    providers.forEach(provider =>
      defs.push({
        key: provider,
        label: provider,
        kind: 'provider',
        align: 'right',
      }),
    );
    if (hasMom) {
      defs.push({ key: MOM_KEY, label: t('MoM'), kind: 'mom', align: 'center' });
    }
    if (hasTrend) {
      defs.push({
        key: TREND_KEY,
        label: t('Trend'),
        kind: 'trend',
        align: 'left',
      });
    }
    if (showPercentOfTotal) {
      defs.push({
        key: PCT_KEY,
        label: t('% of Total'),
        kind: 'pct',
        align: 'right',
      });
    }
    defs.push({ key: SPEND_KEY, label: spendLabel, kind: 'spend', align: 'right' });
    return defs;
  }, [entityLabel, spendLabel, providers, hasMom, hasTrend, showPercentOfTotal]);

  const columns = useMemo(
    () => allColumns.filter(column => !hidden.has(column.key)),
    [allColumns, hidden],
  );

  const visibleRows = useMemo(
    () => sortRows(filterRows(rows, query), sort, allColumns),
    [rows, query, sort, allColumns],
  );

  const ctx = useMemo(
    () => ({
      money: makeValueFormatter(valueFormat, currency),
      accent: accentColor ?? theme.colorPrimary,
    }),
    [valueFormat, currency, accentColor, theme],
  );

  const onSort = useCallback(
    (key: string) =>
      setSort(current =>
        current.key === key
          ? { key, desc: !current.desc }
          : { key, desc: true },
      ),
    [],
  );

  const onToggle = useCallback((key: string) => {
    setExpanded(current => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const onToggleColumn = useCallback((key: string) => {
    setHidden(current => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const body = () => {
    if (!hasQuery) {
      return (
        <div style={message(theme)}>
          {t('Choose a category column and a value metric to render this table.')}
        </div>
      );
    }
    if (visibleRows.length === 0) {
      return <div style={message(theme)}>{t('No results')}</div>;
    }
    return (
      <SpendTableGrid
        rows={visibleRows}
        columns={columns}
        totals={totals}
        showTotalRow={totalsVisible}
        sort={sort}
        onSort={onSort}
        expanded={expanded}
        onToggle={onToggle}
        ctx={ctx}
        theme={theme}
      />
    );
  };

  return (
    <div style={card(theme, fullscreen)} data-testid="custom-spend-table">
      <CardHeader
        title={cardTitle}
        fullscreen={fullscreen}
        onToggleFullscreen={() => setFullscreen(current => !current)}
        theme={theme}
      />
      <Toolbar
        query={query}
        onQueryChange={setQuery}
        showSearch={showSearch}
        columns={allColumns}
        hiddenColumns={hidden}
        onToggleColumn={onToggleColumn}
        showTotalRow={totalsVisible}
        onToggleTotalRow={() => setTotalsVisible(current => !current)}
        onCollapseAll={() => setExpanded(new Set())}
        theme={theme}
      />
      {body()}
    </div>
  );
}
