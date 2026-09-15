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
import { FC } from 'react';

interface SearchGlyphProps {
  size?: number;
}

// The control's own spec names this exact glyph: "magnifying glass outline,
// left-aligned". Drawn here rather than swapped for a stock icon, since that
// description is the only specification of it anywhere in the pipeline.
// `currentColor` (not a literal) lets the enclosing element's CSS `color`
// drive the stroke, so the icon still follows the theme.
const SearchGlyph: FC<SearchGlyphProps> = ({ size = 16 }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 16 16"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
    data-test="custom-search-filter-glyph"
  >
    <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5" />
    <line
      x1="10.8"
      y1="10.8"
      x2="14"
      y2="14"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);

export default SearchGlyph;
