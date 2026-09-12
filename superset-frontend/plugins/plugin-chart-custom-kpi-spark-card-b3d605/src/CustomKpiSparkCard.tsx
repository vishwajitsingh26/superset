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
import { memo, useMemo } from 'react';
import { t, useTheme } from './adapters/supersetAdapter';
import { CustomKpiSparkCardProps } from './types';
import {
  BottomRow,
  Caption,
  Card,
  DeltaBlock,
  DeltaText,
  Label,
  LabelRow,
  Message,
  SparkSlot,
  Value,
} from './CustomKpiSparkCardStyles';
import DeltaArrow from './components/DeltaArrow';
import KpiIcon from './components/KpiIcon';
import Sparkline from './components/Sparkline';
import { SIZES } from './utils/constants';

function CustomKpiSparkCard({
  width,
  height,
  hasMetric,
  hasData,
  label,
  valueText,
  deltaText,
  deltaDirection,
  deltaTone,
  subCaption,
  iconGlyph,
  accentColor,
  favorableColor,
  unfavorableColor,
  showSparkline,
  sparkPoints,
}: CustomKpiSparkCardProps) {
  const theme = useTheme();
  const accent = accentColor ?? theme.colorPrimary;

  const deltaColor = useMemo(() => {
    if (deltaTone === 'favorable') return favorableColor ?? theme.colorSuccess;
    if (deltaTone === 'unfavorable') return unfavorableColor ?? theme.colorError;
    return theme.colorTextSecondary;
  }, [deltaTone, favorableColor, unfavorableColor, theme]);

  // The sparkline sits inline at bottom-right, so it takes the width left over
  // beside the delta block rather than the full card width.
  const spark = useMemo(() => {
    const available =
      width - SIZES.cardPadding * 2 - SIZES.deltaMinWidth - SIZES.bottomGap;
    return {
      width: Math.min(SIZES.sparkWidth, available),
      height: Math.max(
        SIZES.sparkMinHeight,
        Math.min(SIZES.sparkHeight, height - SIZES.cardPadding * 2 - 60),
      ),
      fits: available >= SIZES.sparkMinWidth,
    };
  }, [width, height]);

  if (!hasMetric) {
    return (
      <Card data-testid="custom-kpi-spark-card">
        <Message>{t('Choose a value metric to display this card.')}</Message>
      </Card>
    );
  }

  if (!hasData) {
    return (
      <Card data-testid="custom-kpi-spark-card">
        <Message>{t('No data')}</Message>
      </Card>
    );
  }

  return (
    <Card data-testid="custom-kpi-spark-card">
      <div>
        <LabelRow>
          <KpiIcon glyph={iconGlyph} color={accent} size={SIZES.iconSize} />
          <Label title={label}>{label}</Label>
        </LabelRow>
        <Value>{valueText}</Value>
      </div>
      <BottomRow>
        <DeltaBlock>
          {deltaText === null ? (
            <DeltaText deltaColor={theme.colorTextTertiary}>
              {t('No comparison')}
            </DeltaText>
          ) : (
            <DeltaText deltaColor={deltaColor}>
              <DeltaArrow
                direction={deltaDirection}
                color={deltaColor}
                size={SIZES.arrowSize}
              />
              {deltaText}
            </DeltaText>
          )}
          <Caption>{subCaption}</Caption>
        </DeltaBlock>
        {showSparkline && spark.fits && sparkPoints.length > 1 && (
          <SparkSlot>
            <Sparkline
              points={sparkPoints}
              width={spark.width}
              height={spark.height}
              color={accent}
              label={t('Trend for %s', label)}
            />
          </SparkSlot>
        )}
      </BottomRow>
    </Card>
  );
}

export default memo(CustomKpiSparkCard);
