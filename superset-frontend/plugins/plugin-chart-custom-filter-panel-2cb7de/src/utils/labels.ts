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

// Turns any column label into a human field label, so the panel reads well on
// whatever dataset is attached without hardcoding a single column name.
export function humanizeColumn(column: string): string {
  const words = column.replace(/[_-]+/g, ' ').trim().split(/\s+/);
  return words
    .map(word =>
      word.length > 1 && word === word.toUpperCase()
        ? word
        : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase(),
    )
    .join(' ');
}

export function toStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .filter(item => item !== null && item !== undefined && item !== '')
      .map(item => String(item));
  }
  if (value === null || value === undefined || value === '') return [];
  return [String(value)];
}
