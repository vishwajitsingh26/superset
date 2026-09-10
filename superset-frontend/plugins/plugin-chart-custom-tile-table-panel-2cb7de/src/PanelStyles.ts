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
import { styled } from './adapters/supersetAdapter';

export const Card = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  overflow: hidden;
  background: ${({ theme }) => theme.colorBgContainer};
  border: 1px solid ${({ theme }) => theme.colorBorderSecondary};
  border-radius: ${({ theme }) => theme.borderRadiusLG}px;
  padding: ${({ theme }) => theme.sizeUnit * 4}px;
`;

export const CardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.sizeUnit}px;
  margin-bottom: ${({ theme }) => theme.sizeUnit * 3}px;
`;

export const CardTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSizeLG}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  color: ${({ theme }) => theme.colorText};
`;

export const InfoDot = styled.span<{ $accent: string }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: ${({ theme }) => theme.sizeUnit * 4}px;
  height: ${({ theme }) => theme.sizeUnit * 4}px;
  border-radius: 50%;
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  font-style: italic;
  cursor: help;
  color: ${({ $accent }) => $accent};
  border: 1px solid ${({ $accent }) => $accent};
`;

export const TileRow = styled.div`
  display: flex;
  align-items: stretch;
  gap: ${({ theme }) => theme.sizeUnit * 2}px;
  margin-bottom: ${({ theme }) => theme.sizeUnit * 3}px;
`;

export const TileSlot = styled.div<{ $w: number }>`
  width: ${({ $w }) => $w}px;
  flex: 0 0 auto;
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.colorBorderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius}px;
  padding: ${({ theme }) => theme.sizeUnit * 2}px;
  box-sizing: border-box;
`;

export const SectionTitle = styled.div`
  font-size: ${({ theme }) => theme.fontSize}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  color: ${({ theme }) => theme.colorText};
  margin-bottom: ${({ theme }) => theme.sizeUnit * 2}px;
`;

export const TableArea = styled.div`
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  border: 1px solid ${({ theme }) => theme.colorBorderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius}px;
`;

export const Pill = styled.span`
  display: inline-block;
  align-self: flex-start;
  padding: 0 ${({ theme }) => theme.sizeUnit * 2}px;
  border-radius: ${({ theme }) => theme.borderRadiusLG}px;
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  font-weight: ${({ theme }) => theme.fontWeightStrong};
  color: ${({ theme }) => theme.colorSuccess};
  background: ${({ theme }) => theme.colorSuccessBg};
`;

export const PlaceholderText = styled.span`
  margin-top: ${({ theme }) => theme.sizeUnit * 2}px;
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  color: ${({ theme }) => theme.colorTextTertiary};
`;

export const PlaceholderBody = styled.div`
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 100%;
`;

export const ChildFallback = styled.div<{ $height: number }>`
  display: flex;
  align-items: center;
  justify-content: center;
  height: ${({ $height }) => $height}px;
  font-size: ${({ theme }) => theme.fontSizeSM}px;
  color: ${({ theme }) => theme.colorTextTertiary};
`;

export const EmptyState = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: ${({ theme }) => theme.colorTextTertiary};
`;
