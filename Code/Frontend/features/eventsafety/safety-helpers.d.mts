export const DESKTOP_SAFETY_QUERY: '(min-width: 768px)';

export type SafetyCommand = Readonly<{
  contextKey: string;
  path: string;
  body: Readonly<Record<string, unknown>>;
}>;

export function captureSafetyCommand(contextKey: string, path: string, body: Record<string, unknown>): SafetyCommand;
export function matchesSafetyCommand(command: SafetyCommand | null, contextKey: string): boolean;
export function isUncertainSafetyFailure(status: number | null): boolean;
export function eventReportDecisionOutcome(result: unknown, reportId: string, action: unknown, version: unknown): 'applied' | 'expired' | 'uncertain';
export function parseBoundedEventEvidence(evidence: unknown): Record<string, string> | null;
export function eventReportActions(report: {
  status: string;
  stage: string;
  deadline: string;
  evidence: string | null;
}, now?: number): Array<'dismiss' | 'hide' | 'remove' | 'uphold'>;
