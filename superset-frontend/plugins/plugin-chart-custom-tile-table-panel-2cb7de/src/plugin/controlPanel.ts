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
import { ControlPanelConfig, t } from '../adapters/supersetAdapter';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Panel'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'panel_title',
            config: {
              type: 'TextControl',
              label: t('Panel title'),
              default: '',
              description: t('Bold title shown in the card header.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'panel_info',
            config: {
              type: 'TextControl',
              label: t('Info tooltip'),
              default: '',
              description: t(
                'Text shown by the info icon next to the title. Leave empty to hide the icon.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'accent_color',
            config: {
              type: 'TextControl',
              label: t('Accent color'),
              default: null,
              description: t(
                'Hex color for the info icon. Falls back to the theme primary color when empty.',
              ),
              renderTrigger: true,
            },
          },
        ],
      ],
    },
    {
      label: t('Tiles'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'tile_chart_ids',
            config: {
              type: 'TextControl',
              label: t('Tile charts'),
              default: '',
              description: t(
                'Comma-separated ids of saved charts rendered as sub-tiles, left to right.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'show_placeholder_tile',
            config: {
              type: 'CheckboxControl',
              label: t('Show placeholder tile'),
              default: false,
              description: t(
                'Append a non-data tile after the chart tiles for an unavailable source.',
              ),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'placeholder_label',
            config: {
              type: 'TextControl',
              label: t('Placeholder pill'),
              default: t('Coming Soon'),
              description: t('Text inside the placeholder tile pill.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'placeholder_text',
            config: {
              type: 'TextControl',
              label: t('Placeholder message'),
              default: '',
              description: t('Supporting line under the placeholder pill.'),
              renderTrigger: true,
            },
          },
        ],
      ],
    },
    {
      label: t('Table'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'table_title',
            config: {
              type: 'TextControl',
              label: t('Table heading'),
              default: '',
              description: t('Bold sub-heading shown above the table.'),
              renderTrigger: true,
            },
          },
        ],
        [
          {
            name: 'table_chart_id',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('Table chart'),
              default: null,
              description: t(
                'Id of the saved chart rendered in the lower half of the card.',
              ),
              renderTrigger: true,
            },
          },
        ],
      ],
    },
  ],
};

export default config;
