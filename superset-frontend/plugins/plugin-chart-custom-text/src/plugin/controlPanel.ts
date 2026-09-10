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
      label: t('Text'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'bodyText',
            config: {
              type: 'TextAreaControl',
              label: t('Text'),
              default: '',
              language: null,
              renderTrigger: true,
              description: t('The text to display. Newlines are preserved.'),
            },
          },
        ],
        [
          {
            name: 'subText',
            config: {
              type: 'TextControl',
              label: t('Sub-text'),
              default: '',
              renderTrigger: true,
              description: t('Optional smaller line beneath the main text.'),
            },
          },
        ],
      ],
    },
    {
      label: t('Appearance'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'fontSize',
            config: {
              type: 'SliderControl',
              label: t('Font size'),
              default: 24,
              min: 10,
              max: 72,
              step: 1,
              renderTrigger: true,
            },
          },
          {
            name: 'fontWeight',
            config: {
              type: 'SelectControl',
              label: t('Font weight'),
              default: 600,
              freeForm: false,
              clearable: false,
              renderTrigger: true,
              choices: [
                [400, t('Regular')],
                [500, t('Medium')],
                [600, t('Semi-bold')],
                [700, t('Bold')],
              ],
            },
          },
        ],
        [
          {
            name: 'textAlign',
            config: {
              type: 'SelectControl',
              label: t('Alignment'),
              default: 'left',
              freeForm: false,
              clearable: false,
              renderTrigger: true,
              choices: [
                ['left', t('Left')],
                ['center', t('Center')],
                ['right', t('Right')],
              ],
            },
          },
          {
            name: 'textColor',
            config: {
              type: 'TextControl',
              label: t('Text colour'),
              default: '',
              renderTrigger: true,
              description: t(
                'Any CSS colour. Leave empty to follow the dashboard theme.',
              ),
            },
          },
        ],
      ],
    },
  ],
};

export default config;
