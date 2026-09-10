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
import { FONT_STACK, HEADER_HEIGHT } from './constants';

export const Card = styled.div`
  ${({ theme }) => `
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    font-family: ${FONT_STACK};
    background: ${theme.colorBgContainer};
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadius}px;
    padding: ${theme.sizeUnit * 3}px;
  `}
`;

export const HeaderRow = styled.div`
  ${({ theme }) => `
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: ${HEADER_HEIGHT}px;
    gap: ${theme.sizeUnit * 2}px;
  `}
`;

export const Title = styled.div`
  ${({ theme }) => `
    font-size: ${theme.fontSizeLG}px;
    font-weight: ${theme.fontWeightStrong};
    color: ${theme.colorText};
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  `}
`;

export const Segmented = styled.div`
  ${({ theme }) => `
    display: inline-flex;
    align-items: center;
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadius}px;
    overflow: hidden;

    button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: ${theme.sizeUnit * 7}px;
      height: ${theme.sizeUnit * 7}px;
      border: none;
      border-radius: 0;
      padding: 0;
      box-shadow: none;
      color: ${theme.colorTextTertiary};
      background: ${theme.colorBgContainer};
    }

    button[aria-pressed='true'] {
      color: ${theme.colorPrimary};
      background: ${theme.colorPrimaryBg};
    }
  `}
`;

export const Message = styled.div`
  ${({ theme }) => `
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: ${theme.colorTextTertiary};
    font-size: ${theme.fontSizeSM}px;
  `}
`;

export const TableWrap = styled.div`
  ${({ theme }) => `
    flex: 1;
    overflow: auto;

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: ${theme.fontSizeSM}px;
    }

    th,
    td {
      text-align: right;
      white-space: nowrap;
      padding: ${theme.sizeUnit}px ${theme.sizeUnit * 2}px;
      border-bottom: 1px solid ${theme.colorSplit};
      color: ${theme.colorText};
    }

    th {
      color: ${theme.colorTextTertiary};
      font-weight: ${theme.fontWeightStrong};
    }

    th:first-of-type,
    td:first-of-type {
      text-align: left;
    }
  `}
`;
