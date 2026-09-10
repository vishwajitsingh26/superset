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
import {
  Behavior,
  ChartMetadata,
  ChartPlugin,
  t,
} from '../adapters/supersetAdapter';
import buildQuery from './buildQuery';
import controlPanel from './controlPanel';
import transformProps from './transformProps';
import thumbnail from '../images/thumbnail';
import { TileTablePanelFormData } from '../types';

const metadata = new ChartMetadata({
  name: t('Custom Tile Table Panel'),
  category: t('Custom Charts'),
  description: t(
    'A card that frames a row of saved KPI sub-tiles, an optional "coming soon" placeholder tile, ' +
      'and a titled saved table chart underneath. The children keep their own queries and interactions.',
  ),
  behaviors: [Behavior.InteractiveChart],
  tags: [t('Custom Charts'), t('Composite'), t('Tiles'), t('Table')],
  thumbnail,
  useLegacyApi: false,
  skipDataFetch: true,
});

export default class CustomTileTablePanelPlugin extends ChartPlugin<TileTablePanelFormData> {
  constructor() {
    super({
      buildQuery,
      controlPanel,
      loadChart: () =>
        import('../TileTablePanel').then(module => module.default),
      metadata,
      transformProps,
    });
  }
}
