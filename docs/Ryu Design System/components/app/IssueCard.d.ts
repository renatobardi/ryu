import * as React from 'react';

/**
 * Card arrastável do board.
 */
export interface IssueCardProps {
  issueKey?: string;
  title?: React.ReactNode;
  priority?: 'urgent' | 'high' | 'medium' | 'low' | 'none';
  assignee?: string;
  assigneeType?: 'agent' | 'member';
  onClick?: React.MouseEventHandler;
  style?: React.CSSProperties;
}
export declare function IssueCard(props: IssueCardProps): JSX.Element;
