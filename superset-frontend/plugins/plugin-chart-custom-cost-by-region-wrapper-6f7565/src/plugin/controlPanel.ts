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

// Neither id is validateNonEmpty: a saved chart of this type can be reopened
// before both slots are wired up, and the component draws an explicit
// "not configured" placeholder per slot rather than throwing.
const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Hosted charts'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'mapChartId',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('Map chart ID'),
              description: t(
                'Saved chart id rendered on the left half of this card ' +
                  '(the region point map).',
              ),
              renderTrigger: false,
              validators: [],
            },
          },
        ],
        [
          {
            name: 'listChartId',
            config: {
              type: 'TextControl',
              isInt: true,
              label: t('List chart ID'),
              description: t(
                'Saved chart id rendered on the right half of this card ' +
                  '(the ranked region list).',
              ),
              renderTrigger: false,
              validators: [],
            },
          },
        ],
      ],
    },
  ],
};

export default config;
