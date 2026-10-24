import type {components} from '@/lib/api.generated';

export type SafetyAuditOut = components['schemas']['SafetyAuditOut'];
export type EventReportReceipt = components['schemas']['EventReportReceipt'];
export type EventReportReview = components['schemas']['EventReportReview'];
export type EventSafetyOut = components['schemas']['EventSafetyOut'];
export type SuspensionOut = components['schemas']['SuspensionOut'];

export type EventReportInput = components['schemas']['EventReportCreateInput'];
export type EventReportDecisionInput = components['schemas']['EventReportDecisionInput'];
export type EventSafetyInput = components['schemas']['EventSafetyActionInput'];
export type SuspensionInput = components['schemas']['SuspensionActionInput'];

export type SafetyReportStatus = EventReportReceipt['status'];
export type SafetyReportStage = EventReportReceipt['stage'];
export type SafetyReportReason = EventReportInput['reason'];
export type SafetyReportAction = EventReportDecisionInput['action'];
export type EventSafetyAction = EventSafetyInput['action'];
export type SuspensionAction = SuspensionInput['action'];
