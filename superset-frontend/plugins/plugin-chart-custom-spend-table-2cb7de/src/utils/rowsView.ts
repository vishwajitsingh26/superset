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
import { ColumnDef, SortState, SpendNode } from '../types';

export function filterRows(rows: SpendNode[], query: string): SpendNode[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return rows;
  const walk = (node: SpendNode): SpendNode | null => {
    const matches = node.label.toLowerCase().includes(needle);
    if (matches) return node;
    const children = node.children
      .map(walk)
      .filter((child): child is SpendNode => child !== null);
    return children.length ? { ...node, children } : null;
  };
  return rows.map(walk).filter((row): row is SpendNode => row !== null);
}

function cellValue(
  node: SpendNode,
  column: ColumnDef,
): number | string | null {
  switch (column.kind) {
    case 'entity':
      return node.label;
    case 'provider':
      return node.values[column.key] ?? null;
    case 'mom':
      return node.mom;
    case 'pct':
      return node.pctOfTotal;
    case 'trend':
      return node.trend.length ? node.trend[node.trend.length - 1] : null;
    default:
      return node.spend;
  }
}

export function sortRows(
  rows: SpendNode[],
  sort: SortState,
  columns: ColumnDef[],
): SpendNode[] {
  const column = columns.find(candidate => candidate.key === sort.key);
  if (!column) return rows;
  const direction = sort.desc ? -1 : 1;
  const compare = (a: SpendNode, b: SpendNode): number => {
    const left = cellValue(a, column);
    const right = cellValue(b, column);
    if (left === null && right === null) return 0;
    if (left === null) return 1;
    if (right === null) return -1;
    if (typeof left === 'string' || typeof right === 'string') {
      return String(left).localeCompare(String(right)) * direction;
    }
    return (left - right) * direction;
  };
  const sortTree = (list: SpendNode[]): SpendNode[] =>
    [...list]
      .sort(compare)
      .map(node =>
        node.children.length ? { ...node, children: sortTree(node.children) } : node,
      );
  return sortTree(rows);
}
