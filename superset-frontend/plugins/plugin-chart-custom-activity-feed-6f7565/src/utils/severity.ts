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
import { SeverityKind } from '../types';

const ERROR_KEYWORDS = [
  'error',
  'critical',
  'alert',
  'exceed',
  'fail',
  'danger',
  'high',
];
const SUCCESS_KEYWORDS = [
  'success',
  'ok',
  'ready',
  'complete',
  'done',
  'resolved',
  'low',
];
const INFO_KEYWORDS = ['info', 'notice', 'detected', 'update', 'medium'];

// The dataset's own severity values are not in context, so this reads
// intent from the text rather than assuming a fixed enum the real column
// may not share.
export function classifySeverity(value: string | null): SeverityKind {
  if (!value) return 'default';
  const normalized = value.toLowerCase();
  if (ERROR_KEYWORDS.some(keyword => normalized.includes(keyword)))
    return 'error';
  if (SUCCESS_KEYWORDS.some(keyword => normalized.includes(keyword)))
    return 'success';
  if (INFO_KEYWORDS.some(keyword => normalized.includes(keyword)))
    return 'info';
  return 'default';
}
