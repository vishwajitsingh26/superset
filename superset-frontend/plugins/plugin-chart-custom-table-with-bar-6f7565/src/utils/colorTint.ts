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
// Produces a light tint of a hex colour for the bar's track background,
// mirroring the house RatioBarCell convention so an unset bar colour still
// reads as a progress bar rather than a flat line. The fallback is passed
// in by the caller (a theme token), never held here as a literal.
export function tintColor(hex: string, fallback: string): string {
  const cleaned = hex.replace('#', '');
  const full =
    cleaned.length === 3
      ? cleaned
          .split('')
          .map(c => c + c)
          .join('')
      : cleaned;
  if (full.length !== 6 || /[^0-9a-fA-F]/.test(full)) {
    return fallback;
  }
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  const mix = (c: number) => Math.round(c + (255 - c) * 0.85);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
}
