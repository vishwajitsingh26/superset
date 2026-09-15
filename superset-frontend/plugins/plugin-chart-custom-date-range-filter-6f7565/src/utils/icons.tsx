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
// The only spec for these glyphs is the region's own written description:
// "calendar outline, left of text; chevron right" / "downward chevron at
// right edge". Drawn to match that, not swapped for a stock icon.
interface IconProps {
  size: number;
  color: string;
}

export function CalendarIcon({ size, color }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <rect
        x="2"
        y="3"
        width="12"
        height="11"
        rx="1.5"
        stroke={color}
        strokeWidth="1.2"
      />
      <path d="M2 6.5H14" stroke={color} strokeWidth="1.2" />
      <path
        d="M5 1.5V4"
        stroke={color}
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <path
        d="M11 1.5V4"
        stroke={color}
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function ChevronDownIcon({ size, color }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M3 4.5L6 7.5L9 4.5"
        stroke={color}
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
