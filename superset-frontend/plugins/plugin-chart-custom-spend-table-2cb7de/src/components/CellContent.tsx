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
import { ReactNode } from 'react';
import { ColumnDef, SpendNode } from '../types';
import { ValueFormatter, formatShare } from '../utils/format';
import MomPill from './MomPill';
import Sparkline from './Sparkline';

export interface CellContext {
  money: ValueFormatter;
  accent: string;
}

export default function cellContent(
  column: ColumnDef,
  node: SpendNode,
  ctx: CellContext,
): ReactNode {
  switch (column.kind) {
    case 'entity':
      return node.label;
    case 'provider':
      return ctx.money(node.values[column.key] ?? null);
    case 'mom':
      return <MomPill value={node.mom} />;
    case 'trend':
      return <Sparkline data={node.trend} color={ctx.accent} />;
    case 'pct':
      return formatShare(node.pctOfTotal);
    default:
      return ctx.money(node.spend);
  }
}
