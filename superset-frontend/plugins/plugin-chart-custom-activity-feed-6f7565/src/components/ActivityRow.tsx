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
import { styled, useTheme } from '../adapters/supersetAdapter';
import ActivityIcon from './ActivityIcon';
import { ActivityItemData } from '../types';

const BADGE_SIZE = 32;
const ICON_SIZE = 16;

const Row = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 12px;
`;

const Badge = styled.div<{ $bg: string; $fg: string }>`
  flex-shrink: 0;
  width: ${BADGE_SIZE}px;
  height: ${BADGE_SIZE}px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${({ $bg }) => $bg};
  color: ${({ $fg }) => $fg};
`;

const TextBlock = styled.div`
  min-width: 0;
  flex: 1;
`;

const Title = styled.div`
  font-size: 14px;
  font-weight: 600;
  line-height: 1.3;
  color: ${({ theme }) => theme.colorText};
`;

const Description = styled.div`
  margin-top: 4px;
  font-size: 13px;
  font-weight: 400;
  line-height: 1.4;
  color: ${({ theme }) => theme.colorTextSecondary};
`;

const Timestamp = styled.div`
  margin-top: 6px;
  font-size: 12px;
  font-weight: 400;
  line-height: 1.4;
  color: ${({ theme }) => theme.colorTextTertiary};
`;

interface ActivityRowProps {
  item: ActivityItemData;
}

export default function ActivityRow({ item }: ActivityRowProps) {
  const theme = useTheme();
  const palette = {
    error: { bg: theme.colorErrorBg, fg: theme.colorError },
    success: { bg: theme.colorSuccessBg, fg: theme.colorSuccess },
    info: { bg: theme.colorInfoBg, fg: theme.colorInfo },
    default: { bg: theme.colorFillSecondary, fg: theme.colorTextTertiary },
  }[item.severity];

  return (
    <Row data-testid="activity-row">
      <Badge $bg={palette.bg} $fg={palette.fg}>
        <ActivityIcon severity={item.severity} size={ICON_SIZE} />
      </Badge>
      <TextBlock>
        <Title>{item.title}</Title>
        {item.description ? (
          <Description>{item.description}</Description>
        ) : null}
        {item.timestamp ? <Timestamp>{item.timestamp}</Timestamp> : null}
      </TextBlock>
    </Row>
  );
}
