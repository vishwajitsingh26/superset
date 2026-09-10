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
import { DataRecord, DataRecordValue } from '../adapters/supersetAdapter';
import { MISSING } from '../constants';
import { NullableNumber, SpendNode, SpendTotals } from '../types';

export interface RowKeys {
  entity: string;
  child?: string;
  provider?: string;
  metric: string;
  mom?: string;
}

interface Acc {
  node: SpendNode;
  momSum: number;
  momWeight: number;
  lastMom: NullableNumber;
  children: Map<string, Acc>;
}

export function toNumber(value: DataRecordValue): NullableNumber {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function label(value: DataRecordValue): string {
  return value === null || value === undefined || value === ''
    ? MISSING
    : String(value);
}

function createAcc(name: string, parentKey: string): Acc {
  return {
    node: {
      key: parentKey ? `${parentKey}\u0000${name}` : name,
      label: name,
      values: {},
      spend: 0,
      mom: null,
      pctOfTotal: null,
      trend: [],
      children: [],
    },
    momSum: 0,
    momWeight: 0,
    lastMom: null,
    children: new Map<string, Acc>(),
  };
}

function accumulate(
  acc: Acc,
  provider: string,
  value: NullableNumber,
  mom: NullableNumber,
): void {
  if (value !== null) {
    acc.node.values[provider] = (acc.node.values[provider] ?? 0) + value;
    acc.node.spend += value;
  }
  if (mom !== null) {
    acc.lastMom = mom;
    acc.momSum += mom * (value ?? 0);
    acc.momWeight += value ?? 0;
  }
}

function finalize(acc: Acc): SpendNode {
  const { node } = acc;
  node.mom = acc.momWeight !== 0 ? acc.momSum / acc.momWeight : acc.lastMom;
  node.children = Array.from(acc.children.values())
    .map(finalize)
    .sort((a, b) => b.spend - a.spend);
  return node;
}

export function collectProviders(
  data: DataRecord[],
  providerKey: string,
): string[] {
  const seen = new Set<string>();
  data.forEach(row => seen.add(label(row[providerKey])));
  return Array.from(seen).sort((a, b) => a.localeCompare(b));
}

export function buildTree(data: DataRecord[], keys: RowKeys): SpendNode[] {
  const roots = new Map<string, Acc>();
  data.forEach(row => {
    const rootName = label(row[keys.entity]);
    let root = roots.get(rootName);
    if (!root) {
      root = createAcc(rootName, '');
      roots.set(rootName, root);
    }
    const provider = keys.provider ? label(row[keys.provider]) : '';
    const value = toNumber(row[keys.metric]);
    const mom = keys.mom ? toNumber(row[keys.mom]) : null;
    accumulate(root, provider, value, mom);
    if (keys.child) {
      const childName = label(row[keys.child]);
      let child = root.children.get(childName);
      if (!child) {
        child = createAcc(childName, root.node.key);
        root.children.set(childName, child);
      }
      accumulate(child, provider, value, mom);
    }
  });
  return Array.from(roots.values())
    .map(finalize)
    .sort((a, b) => b.spend - a.spend);
}

export function computeTotals(
  rows: SpendNode[],
  providers: string[],
): SpendTotals {
  const values: Record<string, NullableNumber> = {};
  let spend = 0;
  rows.forEach(row => {
    spend += row.spend;
    providers.forEach(provider => {
      const cell = row.values[provider];
      if (cell !== null && cell !== undefined) {
        values[provider] = (values[provider] ?? 0) + cell;
      }
    });
  });
  providers.forEach(provider => {
    if (values[provider] === undefined) values[provider] = null;
  });
  return { values, spend };
}

export function applyShare(rows: SpendNode[], total: number): void {
  if (!total) return;
  const walk = (node: SpendNode) => {
    node.pctOfTotal = (node.spend / total) * 100;
    node.children.forEach(walk);
  };
  rows.forEach(walk);
}

export function attachTrends(
  rows: SpendNode[],
  trends: Map<string, number[]>,
): void {
  rows.forEach(row => {
    row.trend = trends.get(row.label) ?? [];
  });
}
