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
// The `icon` control is freeform text, not a closed enum: a URL renders as an
// image (for a brand mark this shape can't otherwise draw), and a known name
// renders a small line icon. An unrecognised name falls back to the cloud
// glyph rather than throwing.
export type KpiIconName = 'cloud' | 'compute' | 'storage' | 'network';

interface KpiIconProps {
  name: string;
  size?: number;
  color: string;
}

const PATHS: Record<KpiIconName, string> = {
  cloud:
    'M6.5 16.5a3.7 3.7 0 0 1-.4-7.38A4.6 4.6 0 0 1 15 8.3a3.2 3.2 0 0 1 1 6.2v0h-.6',
  compute: 'M4 6.5l6-2.7 6 2.7-6 2.7-6-2.7zm0 0v6.3l6 2.7 6-2.7V6.5M10 9.2v6.3',
  storage:
    'M4 5.8c0-1 2.7-1.8 6-1.8s6 .8 6 1.8-2.7 1.8-6 1.8-6-.8-6-1.8zm0 0v4.4c0 1 2.7 1.8 6 1.8s6-.8 6-1.8V5.8m-12 4.4v4.4c0 1 2.7 1.8 6 1.8s6-.8 6-1.8v-4.4',
  network:
    'M10 3v3.2M5.4 15.4l3.4-5.4M14.6 15.4l-3.4-5.4M5.4 15.4a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 0 0 0-3.2zm9.2 0a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 0 0 0-3.2zm-4.6-12a1.6 1.6 0 1 0 0 3.2 1.6 1.6 0 0 0 0-3.2z',
};

function isKnownIcon(name: string): name is KpiIconName {
  return (
    name === 'cloud' ||
    name === 'compute' ||
    name === 'storage' ||
    name === 'network'
  );
}

export default function KpiIcon({ name, size = 16, color }: KpiIconProps) {
  if (/^https?:\/\//.test(name)) {
    return (
      <img
        src={name}
        alt=""
        width={size}
        height={size}
        style={{ display: 'block', objectFit: 'contain', flexShrink: 0 }}
      />
    );
  }

  const normalized = name.trim().toLowerCase();
  const path = isKnownIcon(normalized) ? PATHS[normalized] : PATHS.cloud;

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke={color}
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={{ flexShrink: 0 }}
    >
      <path d={path} />
    </svg>
  );
}
