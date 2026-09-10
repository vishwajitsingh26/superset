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
import { SupersetThemeType, t } from '../adapters/supersetAdapter';
import {
  headerRow,
  iconButton,
  outlinedIconButton,
  segment,
  title as titleStyle,
} from '../SpendTableStyles';
import {
  BarViewIcon,
  ExpandIcon,
  ListViewIcon,
  TileViewIcon,
} from './TableIcons';

interface CardHeaderProps {
  title: string;
  fullscreen: boolean;
  onToggleFullscreen: () => void;
  theme: SupersetThemeType;
}

// The chart and tile view modes are part of the design's chrome but are not
// implemented by this plugin, so they render disabled rather than inert.
export default function CardHeader({
  title,
  fullscreen,
  onToggleFullscreen,
  theme,
}: CardHeaderProps) {
  return (
    <div style={headerRow}>
      <div style={titleStyle(theme)}>{title}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={segment(theme)}>
          <button
            type="button"
            style={iconButton(theme, true)}
            aria-label={t('List view')}
            aria-pressed
          >
            <ListViewIcon />
          </button>
          <button
            type="button"
            disabled
            style={iconButton(theme, false, true)}
            aria-label={t('Chart view (not available)')}
          >
            <BarViewIcon />
          </button>
          <button
            type="button"
            disabled
            style={iconButton(theme, false, true)}
            aria-label={t('Tile view (not available)')}
          >
            <TileViewIcon />
          </button>
        </div>
        <button
          type="button"
          style={outlinedIconButton(theme)}
          onClick={onToggleFullscreen}
          aria-label={fullscreen ? t('Exit fullscreen') : t('Expand')}
        >
          <ExpandIcon />
        </button>
      </div>
    </div>
  );
}
