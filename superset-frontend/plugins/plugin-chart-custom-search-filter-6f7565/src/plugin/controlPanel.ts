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
import {
  DEFAULT_PLACEHOLDER,
  DEFAULT_SEARCH_COLUMNS,
} from '../utils/searchFilter';

const config: ControlPanelConfig = {
  controlPanelSections: [
    {
      label: t('Search'),
      expanded: true,
      controlSetRows: [
        [
          {
            name: 'searchColumns',
            config: {
              type: 'TextControl',
              label: t('Search columns'),
              default: DEFAULT_SEARCH_COLUMNS.join(','),
              description: t(
                'Comma-separated column names to match against, one per target ' +
                  "chart in this filter's scope (e.g. account_name,service_name," +
                  'region_name). Every keystroke pushes an ILIKE filter on ALL of ' +
                  'these columns to every chart in scope, so scope should include ' +
                  'only the charts that own one of them.',
              ),
              renderTrigger: false,
            },
          },
        ],
        [
          {
            name: 'placeholderText',
            config: {
              type: 'TextControl',
              label: t('Placeholder text'),
              default: DEFAULT_PLACEHOLDER,
              description: t(
                'Placeholder text shown inside the empty search box.',
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
