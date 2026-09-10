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
import { FC, useMemo } from 'react';
import { Tooltip, t, useTheme } from './adapters/supersetAdapter';
import { TileTablePanelProps } from './types';
import ChildChart from './components/ChildChart';
import ComingSoonTile from './components/ComingSoonTile';
import {
  Card,
  CardHeader,
  CardTitle,
  EmptyState,
  InfoDot,
  SectionTitle,
  TableArea,
  TileRow,
  TileSlot,
} from './PanelStyles';

const HEADER_HEIGHT = 40;
const TILE_HEIGHT = 116;
const SECTION_TITLE_HEIGHT = 30;
const MIN_TILE_WIDTH = 120;
const MIN_TABLE_HEIGHT = 160;

const TileTablePanel: FC<TileTablePanelProps> = ({
  width,
  height,
  panelTitle,
  panelInfo,
  tileChartIds,
  tableTitle,
  tableChartId,
  showPlaceholderTile,
  placeholderLabel,
  placeholderText,
  accentColor,
  dashboardId,
}) => {
  const theme = useTheme();
  const accent = accentColor || theme.colorPrimary;
  const tileCount = tileChartIds.length + (showPlaceholderTile ? 1 : 0);
  const gutter = theme.sizeUnit * 2;

  const tileWidth = useMemo(() => {
    if (tileCount === 0) return 0;
    const inner = width - theme.sizeUnit * 8 - gutter * (tileCount - 1);
    return Math.max(Math.floor(inner / tileCount), MIN_TILE_WIDTH);
  }, [width, tileCount, gutter, theme.sizeUnit]);

  const tableWidth = Math.max(width - theme.sizeUnit * 8, MIN_TILE_WIDTH);
  const tableHeight = Math.max(
    height -
      HEADER_HEIGHT -
      (tileCount > 0 ? TILE_HEIGHT + theme.sizeUnit * 3 : 0) -
      SECTION_TITLE_HEIGHT -
      theme.sizeUnit * 8,
    MIN_TABLE_HEIGHT,
  );

  if (tileCount === 0 && tableChartId === null) {
    return (
      <Card data-test="custom-tile-table-panel">
        <EmptyState>{t('Choose the charts this panel should display.')}</EmptyState>
      </Card>
    );
  }

  return (
    <Card data-test="custom-tile-table-panel">
      <CardHeader>
        <CardTitle>{panelTitle}</CardTitle>
        {panelInfo ? (
          <Tooltip title={panelInfo}>
            <InfoDot $accent={accent}>i</InfoDot>
          </Tooltip>
        ) : null}
      </CardHeader>
      {tileCount > 0 && (
        <TileRow>
          {tileChartIds.map(id => (
            <TileSlot key={id} $w={tileWidth}>
              <ChildChart
                chartId={id}
                dashboardId={dashboardId}
                width={tileWidth}
                height={TILE_HEIGHT}
              />
            </TileSlot>
          ))}
          {showPlaceholderTile && (
            <TileSlot $w={tileWidth}>
              <ComingSoonTile label={placeholderLabel} text={placeholderText} />
            </TileSlot>
          )}
        </TileRow>
      )}
      {tableChartId !== null && (
        <>
          {tableTitle ? <SectionTitle>{tableTitle}</SectionTitle> : null}
          <TableArea>
            <ChildChart
              chartId={tableChartId}
              dashboardId={dashboardId}
              width={tableWidth}
              height={tableHeight}
            />
          </TableArea>
        </>
      )}
    </Card>
  );
};

export default TileTablePanel;
