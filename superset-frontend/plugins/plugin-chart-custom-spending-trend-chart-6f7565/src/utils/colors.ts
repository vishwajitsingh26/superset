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

// Parses the user-configured `seriesColors` control (comma-separated hex)
// into an array. The fallback is passed in by the caller, built from theme
// tokens at render time -- never hardcoded here, which would be a literal
// colour in plugin source.
export function parseColors(
  input: string | undefined,
  fallback: string[],
): string[] {
  if (!input || !input.trim()) return [...fallback];
  const parsed = input
    .split(',')
    .map(c => c.trim())
    .filter(c => /^#[0-9A-Fa-f]{3,8}$/.test(c));
  return parsed.length > 0 ? parsed : [...fallback];
}
