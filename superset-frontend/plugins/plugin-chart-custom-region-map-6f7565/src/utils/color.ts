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
// No colour literal lives here. The design's own marker hexes arrive as
// *data* -- a control value stage D fills from the design system -- and an
// unset or invalid control falls back to the theme token the caller passes
// in, never to a literal written into this file.
const HEX_PATTERN = /^#[0-9A-Fa-f]{3,8}$/;

export function resolveColor(value: string | undefined, fallback: string): string {
  const trimmed = value?.trim();
  if (trimmed && HEX_PATTERN.test(trimmed)) {
    return trimmed;
  }
  return fallback;
}
