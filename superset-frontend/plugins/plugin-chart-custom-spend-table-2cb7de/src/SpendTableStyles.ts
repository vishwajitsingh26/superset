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
import type { CSSProperties } from 'react';
import { SupersetThemeType } from './adapters/supersetAdapter';

export const card = (
  theme: SupersetThemeType,
  fullscreen: boolean,
): CSSProperties => ({
  display: 'flex',
  flexDirection: 'column',
  boxSizing: 'border-box',
  width: '100%',
  height: '100%',
  gap: theme.sizeUnit * 3,
  padding: theme.sizeUnit * 4,
  background: theme.colorBgContainer,
  border: `1px solid ${theme.colorBorderSecondary}`,
  borderRadius: theme.borderRadiusLG,
  overflow: 'hidden',
  ...(fullscreen
    ? { position: 'fixed', inset: 0, zIndex: 100, borderRadius: 0 }
    : {}),
});

export const headerRow: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
};

export const title = (theme: SupersetThemeType): CSSProperties => ({
  fontSize: theme.fontSizeLG,
  fontWeight: theme.fontWeightStrong,
  color: theme.colorText,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const segment = (theme: SupersetThemeType): CSSProperties => ({
  display: 'inline-flex',
  alignItems: 'center',
  border: `1px solid ${theme.colorBorderSecondary}`,
  borderRadius: theme.borderRadius,
  overflow: 'hidden',
});

export const iconButton = (
  theme: SupersetThemeType,
  active = false,
  disabled = false,
): CSSProperties => ({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: theme.sizeUnit * 7,
  height: theme.sizeUnit * 7,
  padding: 0,
  border: 'none',
  background: active ? theme.colorPrimaryBg : 'transparent',
  color: active ? theme.colorPrimary : theme.colorTextSecondary,
  cursor: disabled ? 'not-allowed' : 'pointer',
  opacity: disabled ? 0.45 : 1,
});

export const outlinedIconButton = (
  theme: SupersetThemeType,
): CSSProperties => ({
  ...iconButton(theme),
  border: `1px solid ${theme.colorBorderSecondary}`,
  borderRadius: theme.borderRadius,
});

export const toolbar: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 8,
};

export const scrollArea: CSSProperties = {
  flex: 1,
  minHeight: 0,
  overflow: 'auto',
};

export const table = (theme: SupersetThemeType): CSSProperties => ({
  width: '100%',
  borderCollapse: 'separate',
  borderSpacing: 0,
  fontSize: theme.fontSizeSM,
  color: theme.colorText,
  border: `1px solid ${theme.colorBorderSecondary}`,
  borderRadius: theme.borderRadius,
});

export const headCell = (
  theme: SupersetThemeType,
  align: CSSProperties['textAlign'],
): CSSProperties => ({
  position: 'sticky',
  top: 0,
  zIndex: 1,
  textAlign: align,
  whiteSpace: 'nowrap',
  padding: `${theme.sizeUnit * 2}px ${theme.sizeUnit * 3}px`,
  background: theme.colorFillAlter,
  color: theme.colorTextSecondary,
  fontWeight: theme.fontWeightStrong,
  borderBottom: `1px solid ${theme.colorBorderSecondary}`,
  cursor: 'pointer',
  userSelect: 'none',
});

export const bodyCell = (
  theme: SupersetThemeType,
  align: CSSProperties['textAlign'],
  depth = 0,
): CSSProperties => ({
  textAlign: align,
  whiteSpace: 'nowrap',
  padding: `${theme.sizeUnit * 2}px ${theme.sizeUnit * 3}px`,
  paddingLeft:
    align === 'left'
      ? theme.sizeUnit * 3 + depth * theme.sizeUnit * 4
      : theme.sizeUnit * 3,
  borderBottom: `1px solid ${theme.colorSplit}`,
});

export const footerCell = (
  theme: SupersetThemeType,
  align: CSSProperties['textAlign'],
): CSSProperties => ({
  ...bodyCell(theme, align),
  background: theme.colorFillAlter,
  fontWeight: theme.fontWeightStrong,
  borderBottom: 'none',
});

export const pill = (
  color: string,
  background: string,
  theme: SupersetThemeType,
): CSSProperties => ({
  display: 'inline-flex',
  alignItems: 'center',
  gap: theme.sizeUnit,
  padding: `0 ${theme.sizeUnit * 1.5}px`,
  borderRadius: theme.borderRadiusSM,
  background,
  color,
  fontSize: theme.fontSizeSM,
  lineHeight: `${theme.sizeUnit * 5}px`,
  whiteSpace: 'nowrap',
});

export const message = (theme: SupersetThemeType): CSSProperties => ({
  display: 'flex',
  flex: 1,
  alignItems: 'center',
  justifyContent: 'center',
  color: theme.colorTextTertiary,
  fontSize: theme.fontSizeSM,
});
